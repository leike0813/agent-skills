from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

from workspace_db import connect_db


CHANGES_PACKAGE_RE = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{changes\}")
DOCUMENTCLASS_RE = re.compile(r"(\\documentclass(?:\[[^\]]*\])?\{[^\}]+\}\s*)", re.MULTILINE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export marked or clean manuscript variants from review-master export patches."
    )
    parser.add_argument("--artifact-root", required=True, help="Path to the runtime workspace.")
    parser.add_argument("--patch-set-id", required=True, help="Patch set id to export.")
    return parser.parse_args()


def emit(payload: dict[str, Any], *, exit_code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    return exit_code


def copy_source_tree(source_root: Path, output_root: Path) -> list[str]:
    if not source_root.exists():
        raise FileNotFoundError(f"source_root does not exist: {source_root}")
    if source_root.is_file():
        output_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root, output_root)
        return [str(output_root)]
    if output_root.exists():
        shutil.rmtree(output_root)
    shutil.copytree(source_root, output_root)
    return [str(path) for path in output_root.rglob("*") if path.is_file()]


def apply_operation(content: str, *, anchor_text: str, replacement_text: str, operation: str, target_file: Path) -> str:
    if anchor_text not in content:
        raise ValueError(f"anchor_text not found in {target_file}")
    if operation == "replace":
        return content.replace(anchor_text, replacement_text, 1)
    if operation == "insert_after":
        return content.replace(anchor_text, anchor_text + replacement_text, 1)
    if operation == "insert_before":
        return content.replace(anchor_text, replacement_text + anchor_text, 1)
    raise ValueError(f"unsupported operation '{operation}' for {target_file}")


def ensure_changes_package(main_entry_path: Path) -> bool:
    content = main_entry_path.read_text(encoding="utf-8")
    if CHANGES_PACKAGE_RE.search(content):
        return False
    insertion = "\\usepackage[markup=default]{changes}\n"
    if match := DOCUMENTCLASS_RE.search(content):
        updated = content[: match.end()] + insertion + content[match.end() :]
    else:
        updated = insertion + content
    main_entry_path.write_text(updated, encoding="utf-8")
    return True


def load_patch_set(connection: sqlite3.Connection, patch_set_id: str) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT patch_set_id, artifact_kind, source_root, output_root, status
        FROM export_patch_sets
        WHERE patch_set_id = ?
        """,
        (patch_set_id,),
    ).fetchone()


def load_patches(connection: sqlite3.Connection, patch_set_id: str) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            """
            SELECT patch_order, comment_id, action_order, location_order, target_file,
                   anchor_text, operation, marked_text, clean_text, notes
            FROM export_patches
            WHERE patch_set_id = ?
            ORDER BY patch_order
            """,
            (patch_set_id,),
        ).fetchall()
    )


def main() -> int:
    args = parse_args()
    artifact_root = Path(args.artifact_root).expanduser().resolve()
    db_path = artifact_root / "review-master.db"
    if not db_path.exists():
        return emit({"status": "error", "error": f"database does not exist: {db_path}"}, exit_code=1)

    try:
        with connect_db(db_path) as connection:
            patch_set = load_patch_set(connection, args.patch_set_id)
            if patch_set is None:
                return emit({"status": "error", "error": f"patch set not found: {args.patch_set_id}"}, exit_code=1)
            patches = load_patches(connection, args.patch_set_id)
            if not patches:
                return emit({"status": "error", "error": f"patch set has no patches: {args.patch_set_id}"}, exit_code=1)
            main_entry_row = connection.execute(
                "SELECT main_entry FROM manuscript_summary WHERE id = 1"
            ).fetchone()
    except sqlite3.DatabaseError as exc:
        return emit({"status": "error", "error": f"sqlite error: {exc}"}, exit_code=1)

    source_root = Path(str(patch_set["source_root"])).expanduser()
    output_root = Path(str(patch_set["output_root"])).expanduser()
    artifact_kind = str(patch_set["artifact_kind"])
    main_entry = str(main_entry_row["main_entry"]) if main_entry_row is not None else ""

    try:
        copied_files = copy_source_tree(source_root, output_root)
        applied: list[dict[str, Any]] = []
        for patch in patches:
            target_file = output_root / str(patch["target_file"])
            if not target_file.exists():
                raise FileNotFoundError(f"target_file does not exist in export copy: {target_file}")
            content = target_file.read_text(encoding="utf-8")
            replacement_text = str(patch["marked_text"] if artifact_kind == "marked_manuscript" else patch["clean_text"])
            updated = apply_operation(
                content,
                anchor_text=str(patch["anchor_text"]),
                replacement_text=replacement_text,
                operation=str(patch["operation"]),
                target_file=target_file,
            )
            target_file.write_text(updated, encoding="utf-8")
            applied.append(
                {
                    "patch_order": int(patch["patch_order"]),
                    "target_file": str(target_file),
                    "comment_id": str(patch["comment_id"]),
                    "action_order": int(patch["action_order"]),
                    "location_order": int(patch["location_order"]),
                    "operation": str(patch["operation"]),
                }
            )

        changes_package_added = False
        if artifact_kind == "marked_manuscript" and main_entry:
            main_entry_path = output_root / main_entry
            if not main_entry_path.exists():
                raise FileNotFoundError(f"main_entry does not exist in exported manuscript: {main_entry_path}")
            changes_package_added = ensure_changes_package(main_entry_path)

    except (OSError, ValueError) as exc:
        return emit({"status": "error", "error": str(exc), "patch_set_id": args.patch_set_id}, exit_code=1)

    return emit(
        {
            "status": "ok",
            "patch_set_id": args.patch_set_id,
            "artifact_kind": artifact_kind,
            "source_root": str(source_root),
            "output_root": str(output_root),
            "copied_files": copied_files,
            "applied_patches": applied,
            "changes_package_added": changes_package_added,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())

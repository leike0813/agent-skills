from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

from workspace_db import connect_db, ensure_runtime_schema_compatibility


def emit(payload: dict[str, Any], exit_code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    return exit_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture one Stage 6 revision round into review-master runtime truth.")
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--change-note", default="")
    parser.add_argument("--response-note", default="")
    parser.add_argument("--status", default="completed")
    parser.add_argument("--operator-role", default="collaborative")
    parser.add_argument("--plan-action-id", action="append", default=[])
    parser.add_argument("--thread-id", action="append", default=[])
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")


def compact_diff(before_text: str, after_text: str, *, limit: int = 24) -> str:
    lines = list(
        difflib.unified_diff(
            before_text.splitlines(),
            after_text.splitlines(),
            fromfile="before",
            tofile="after",
            lineterm="",
        )
    )
    if len(lines) > limit:
        lines = lines[:limit]
    return "\n".join(lines)


def collect_file_changes(snapshot_root: Path, working_root: Path) -> list[dict[str, str]]:
    snapshot_files = {str(path.relative_to(snapshot_root)): path for path in snapshot_root.rglob("*") if path.is_file()} if snapshot_root.exists() else {}
    working_files = {str(path.relative_to(working_root)): path for path in working_root.rglob("*") if path.is_file()} if working_root.exists() else {}
    all_paths = sorted(set(snapshot_files) | set(working_files))
    changes: list[dict[str, str]] = []
    for relative_path in all_paths:
        snapshot_path = snapshot_files.get(relative_path)
        working_path = working_files.get(relative_path)
        if snapshot_path is None and working_path is not None:
            changes.append(
                {
                    "relative_path": relative_path,
                    "change_kind": "added",
                    "before_excerpt": "",
                    "after_excerpt": load_text(working_path)[:500],
                    "diff_excerpt": compact_diff("", load_text(working_path)),
                    "snapshot_sha256": "",
                    "current_sha256": file_sha256(working_path),
                }
            )
            continue
        if snapshot_path is not None and working_path is None:
            before_text = load_text(snapshot_path)
            changes.append(
                {
                    "relative_path": relative_path,
                    "change_kind": "deleted",
                    "before_excerpt": before_text[:500],
                    "after_excerpt": "",
                    "diff_excerpt": compact_diff(before_text, ""),
                    "snapshot_sha256": file_sha256(snapshot_path),
                    "current_sha256": "",
                }
            )
            continue
        assert snapshot_path is not None and working_path is not None
        snapshot_hash = file_sha256(snapshot_path)
        current_hash = file_sha256(working_path)
        if snapshot_hash == current_hash:
            continue
        before_text = load_text(snapshot_path)
        after_text = load_text(working_path)
        changes.append(
            {
                "relative_path": relative_path,
                "change_kind": "modified",
                "before_excerpt": before_text[:500],
                "after_excerpt": after_text[:500],
                "diff_excerpt": compact_diff(before_text, after_text),
                "snapshot_sha256": snapshot_hash,
                "current_sha256": current_hash,
            }
        )
    return changes


def main() -> int:
    args = parse_args()
    artifact_root = Path(args.artifact_root).expanduser().resolve()
    db_path = artifact_root / "review-master.db"
    if not db_path.exists():
        return emit({"status": "error", "error": f"missing database: {db_path}"}, exit_code=1)

    log_id = f"log_{uuid.uuid4().hex[:12]}"
    created_at = dt.datetime.now(dt.timezone.utc).isoformat()
    with connect_db(db_path) as connection:
        ensure_runtime_schema_compatibility(connection)
        copy_rows = {
            str(row["copy_role"]): row
            for row in connection.execute(
                """
                SELECT copy_role, copy_root
                FROM workspace_manuscript_copies
                """
            ).fetchall()
        }
        snapshot_row = copy_rows.get("source_snapshot")
        working_row = copy_rows.get("working_manuscript")
        snapshot_root = Path(str(snapshot_row["copy_root"])) if snapshot_row is not None else artifact_root / "manuscript-copies" / "source-snapshot"
        working_root = Path(str(working_row["copy_root"])) if working_row is not None else artifact_root / "manuscript-copies" / "working-manuscript"
        changes = collect_file_changes(snapshot_root, working_root)
        max_log_order = connection.execute("SELECT COALESCE(MAX(log_order), 0) FROM revision_action_logs").fetchone()[0]
        connection.execute(
            """
            INSERT INTO revision_action_logs (
                log_id, log_order, status, operator_role, summary, change_note, response_note, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log_id,
                int(max_log_order) + 1,
                str(args.status),
                str(args.operator_role),
                str(args.summary),
                str(args.change_note),
                str(args.response_note),
                created_at,
            ),
        )
        for index, plan_action_id in enumerate(args.plan_action_id, start=1):
            connection.execute(
                "INSERT INTO revision_action_log_plan_links (log_id, plan_action_id) VALUES (?, ?)",
                (log_id, str(plan_action_id)),
            )
        for index, thread_id in enumerate(args.thread_id, start=1):
            connection.execute(
                "INSERT INTO revision_action_log_thread_links (log_id, thread_id) VALUES (?, ?)",
                (log_id, str(thread_id)),
            )
            connection.execute(
                "INSERT OR REPLACE INTO response_thread_action_log_links (thread_id, log_id, link_order) VALUES (?, ?, ?)",
                (str(thread_id), log_id, index),
            )
        for index, change in enumerate(changes, start=1):
            connection.execute(
                """
                INSERT INTO revision_action_log_file_diffs (
                    log_id, file_order, relative_path, change_kind, diff_excerpt, before_excerpt, after_excerpt
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    index,
                    change["relative_path"],
                    change["change_kind"],
                    change["diff_excerpt"],
                    change["before_excerpt"],
                    change["after_excerpt"],
                ),
            )
            connection.execute(
                """
                INSERT INTO working_copy_file_state (
                    relative_path, snapshot_sha256, last_audited_sha256, current_sha256, last_log_id
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(relative_path) DO UPDATE SET
                    snapshot_sha256 = excluded.snapshot_sha256,
                    last_audited_sha256 = excluded.last_audited_sha256,
                    current_sha256 = excluded.current_sha256,
                    last_log_id = excluded.last_log_id
                """,
                (
                    change["relative_path"],
                    change["snapshot_sha256"],
                    change["current_sha256"],
                    change["current_sha256"],
                    log_id,
                ),
            )
        connection.execute(
            """
            INSERT INTO export_artifacts (artifact_name, artifact_status, output_path)
            VALUES ('working_manuscript', 'ready', ?)
            ON CONFLICT(artifact_name) DO UPDATE SET artifact_status = 'ready', output_path = excluded.output_path
            """,
            (str(working_root),),
        )
        connection.commit()
    return emit(
        {
            "status": "ok",
            "log_id": log_id,
            "captured_files": [change["relative_path"] for change in changes],
            "created_at": created_at,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())

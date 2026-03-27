from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from runtime_localization import load_localization_bundle, seed_workspace_localization_overlay
from workspace_db import (
    DB_FILENAME,
    MANUSCRIPT_COPY_ROOT,
    SOURCE_SNAPSHOT_DIR,
    WORKING_MANUSCRIPT_DIR,
    connect_db,
    initialize_database,
    render_workspace,
)


DEFAULT_WORKSPACE_NAME = "review-master-workspace"


def emit(payload: dict[str, Any], exit_code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    return exit_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize a DB-first runtime artifact workspace for review-master.")
    parser.add_argument("--artifact-root", help="Target workspace path. If omitted, create review-master-workspace with auto-numbering.")
    parser.add_argument("--document-language", required=True, help="Confirmed document language tag for final manuscript and response outputs.")
    parser.add_argument("--working-language", required=True, help="Confirmed working language tag for intermediate views and operator-facing instructions.")
    parser.add_argument("--manuscript-source", help="Optional manuscript source path to copy into workspace-local source_snapshot and working_manuscript roots.")
    parser.add_argument("--main-entry-relative-path", default="", help="Optional main entry relative path inside the manuscript source/project.")
    return parser.parse_args()


def resolve_default_workspace(base_dir: Path) -> Path:
    candidate = base_dir / DEFAULT_WORKSPACE_NAME
    if not candidate.exists():
        return candidate
    suffix = 1
    while True:
        candidate = base_dir / f"{DEFAULT_WORKSPACE_NAME}-{suffix}"
        if not candidate.exists():
            return candidate
        suffix += 1


def ensure_target_root(args: argparse.Namespace, cwd: Path) -> tuple[Path, list[str]]:
    warnings: list[str] = []
    if args.artifact_root:
        target = Path(args.artifact_root).expanduser()
        if not target.is_absolute():
            target = cwd / target
        return target, warnings
    target = resolve_default_workspace(cwd)
    if target.name != DEFAULT_WORKSPACE_NAME:
        warnings.append(f"default workspace name was occupied; using '{target.name}' instead")
    return target, warnings


def validate_target(target: Path) -> tuple[bool, str | None]:
    if target.exists():
        if not target.is_dir():
            return False, f"target exists and is not a directory: {target}"
        if any(target.iterdir()):
            return False, f"target directory is not empty: {target}"
    return True, None


def initialize_manuscript_copies(target_root: Path, manuscript_source: str | None, main_entry_relative_path: str) -> dict[str, str]:
    copy_root = target_root / MANUSCRIPT_COPY_ROOT
    source_snapshot_root = copy_root / SOURCE_SNAPSHOT_DIR
    working_manuscript_root = copy_root / WORKING_MANUSCRIPT_DIR
    source_snapshot_root.mkdir(parents=True, exist_ok=True)
    working_manuscript_root.mkdir(parents=True, exist_ok=True)

    source_kind = "single_tex_file"
    source_root = ""
    if manuscript_source:
        source_path = Path(manuscript_source).expanduser().resolve()
        source_root = str(source_path)
        if source_path.is_dir():
            source_kind = "project_directory"
            shutil.copytree(source_path, source_snapshot_root, dirs_exist_ok=True)
            shutil.copytree(source_path, working_manuscript_root, dirs_exist_ok=True)
        else:
            source_kind = "single_tex_file"
            shutil.copy2(source_path, source_snapshot_root / source_path.name)
            shutil.copy2(source_path, working_manuscript_root / source_path.name)
            if not main_entry_relative_path:
                main_entry_relative_path = source_path.name

    return {
        "source_kind": source_kind,
        "source_root": source_root,
        "source_snapshot_root": str(source_snapshot_root),
        "working_manuscript_root": str(working_manuscript_root),
        "main_entry_relative_path": main_entry_relative_path,
    }


def main() -> int:
    args = parse_args()
    cwd = Path.cwd()
    target_root, warnings = ensure_target_root(args, cwd)
    target_root = target_root.resolve()
    is_valid, error = validate_target(target_root)
    if not is_valid:
        return emit({"status": "error", "error": error}, exit_code=1)

    try:
        target_root.mkdir(parents=True, exist_ok=True)
        db_path = target_root / DB_FILENAME
        initialize_database(db_path)
        copy_info = initialize_manuscript_copies(
            target_root,
            str(args.manuscript_source) if args.manuscript_source else None,
            str(args.main_entry_relative_path),
        )
        seed_workspace_localization_overlay(
            target_root,
            working_language=str(args.working_language),
            document_language=str(args.document_language),
        )
        localization = load_localization_bundle(
            target_root,
            runtime_context={
                "document_language": str(args.document_language),
                "working_language": str(args.working_language),
                "manuscript_detected_language": str(args.document_language),
                "review_comments_detected_language": str(args.document_language),
                "prompt_detected_language": str(args.working_language),
                "document_language_source": "manuscript",
                "working_language_source": "prompt",
                "languages_confirmed": "yes",
            },
        )
        with connect_db(db_path) as connection:
            connection.executemany(
                """
                INSERT INTO workspace_manuscript_copies (
                    copy_role, source_kind, source_root, copy_root, main_entry_relative_path
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(copy_role) DO UPDATE SET
                    source_kind = excluded.source_kind,
                    source_root = excluded.source_root,
                    copy_root = excluded.copy_root,
                    main_entry_relative_path = excluded.main_entry_relative_path
                """,
                [
                    (
                        "source_snapshot",
                        copy_info["source_kind"],
                        copy_info["source_root"],
                        copy_info["source_snapshot_root"],
                        copy_info["main_entry_relative_path"],
                    ),
                    (
                        "working_manuscript",
                        copy_info["source_kind"],
                        copy_info["source_root"],
                        copy_info["working_manuscript_root"],
                        copy_info["main_entry_relative_path"],
                    ),
                ],
            )
            connection.execute(
                """
                UPDATE runtime_language_context
                SET document_language = ?,
                    working_language = ?,
                    manuscript_detected_language = ?,
                    review_comments_detected_language = ?,
                    prompt_detected_language = ?,
                    document_language_source = 'manuscript',
                    working_language_source = 'prompt',
                    languages_confirmed = 'yes'
                WHERE id = 1
                """,
                (
                    str(args.document_language),
                    str(args.working_language),
                    str(args.document_language),
                    str(args.document_language),
                    str(args.working_language),
                ),
            )
            connection.execute(
                """
                UPDATE resume_brief
                SET current_objective = ?,
                    current_focus = ?,
                    why_paused = ?,
                    next_operator_action = ?
                WHERE id = 1
                """,
                (
                    localization.msg("bootstrap.resume.current_objective"),
                    localization.msg("bootstrap.resume.current_focus"),
                    localization.msg("bootstrap.resume.why_paused"),
                    localization.msg("bootstrap.resume.next_operator_action"),
                ),
            )
            connection.commit()
        rendered_paths = render_workspace(db_path, target_root)
    except (OSError, RuntimeError) as exc:
        return emit({"status": "error", "error": str(exc)}, exit_code=1)

    created_paths = [
        str(target_root),
        str(db_path),
        str(target_root / MANUSCRIPT_COPY_ROOT),
        str(target_root / MANUSCRIPT_COPY_ROOT / SOURCE_SNAPSHOT_DIR),
        str(target_root / MANUSCRIPT_COPY_ROOT / WORKING_MANUSCRIPT_DIR),
        str(target_root / "runtime-localization"),
        *[str(path) for path in rendered_paths],
        str(target_root / "response-strategy-cards"),
    ]
    return emit(
        {
            "status": "ok",
            "artifact_root": str(target_root),
            "created_paths": created_paths,
            "warnings": warnings,
            "document_language": str(args.document_language),
            "working_language": str(args.working_language),
            "manuscript_copy_info": copy_info,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())

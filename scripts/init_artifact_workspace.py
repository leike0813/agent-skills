from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from workspace_db import DB_FILENAME, initialize_database, render_workspace


DEFAULT_WORKSPACE_NAME = "review-master-workspace"


def emit(payload: dict[str, Any], exit_code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    return exit_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize a DB-first runtime artifact workspace for review-master.")
    parser.add_argument("--artifact-root", help="Target workspace path. If omitted, create review-master-workspace with auto-numbering.")
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
        rendered_paths = render_workspace(db_path, target_root)
    except (OSError, RuntimeError) as exc:
        return emit({"status": "error", "error": str(exc)}, exit_code=1)

    created_paths = [str(target_root), str(db_path), *[str(path) for path in rendered_paths], str(target_root / "response-strategy-cards")]
    return emit(
        {
            "status": "ok",
            "artifact_root": str(target_root),
            "created_paths": created_paths,
            "warnings": warnings,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())

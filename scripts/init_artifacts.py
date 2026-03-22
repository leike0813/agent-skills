#!/usr/bin/env python3
"""Initialize a task-local artifact workspace from package templates."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REQUIRED_TEMPLATES = (
    "manuscript-profile.json",
    "target-settings.json",
    "style-profile.md",
    "condensation-plan.md",
)


def resolve_template_root(script_path: Path) -> Path:
    package_root = script_path.resolve().parent.parent
    return package_root / "assets" / "artifact-templates"


def validate_template_root(template_root: Path) -> None:
    missing = [name for name in REQUIRED_TEMPLATES if not (template_root / name).is_file()]
    if missing:
        raise FileNotFoundError(
            "Missing required template file(s): " + ", ".join(missing)
        )


def validate_artifact_root(artifact_root: Path) -> Path:
    resolved = artifact_root.resolve(strict=False)
    if resolved.exists() and not resolved.is_dir():
        raise NotADirectoryError(f"Artifact root is not a directory: {resolved}")
    return resolved


def initialize_workspace(template_root: Path, artifact_root: Path) -> dict[str, object]:
    artifact_root.mkdir(parents=True, exist_ok=True)

    created_files: list[str] = []
    skipped_files: list[str] = []

    for name in REQUIRED_TEMPLATES:
        source = template_root / name
        target = artifact_root / name
        if target.exists():
            skipped_files.append(str(target))
            continue
        shutil.copy2(source, target)
        created_files.append(str(target))

    return {
        "artifact_root": str(artifact_root),
        "created_files": created_files,
        "skipped_files": skipped_files,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Initialize artifact workspace from package templates."
    )
    parser.add_argument(
        "--artifact-root",
        required=True,
        help="Target artifact directory to initialize.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        artifact_root = validate_artifact_root(Path(args.artifact_root))
        template_root = resolve_template_root(Path(__file__))
        validate_template_root(template_root)
        result = initialize_workspace(template_root, artifact_root)
    except Exception as exc:  # pragma: no cover - CLI error path
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

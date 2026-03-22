#!/usr/bin/env python3
"""Initialize the Stage 5 final LaTeX draft from a selected preset."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REQUIRED_CORE_FILES = (
    "manuscript-profile.json",
    "target-settings.json",
    "style-profile.md",
    "condensation-plan.md",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Initialize final-draft.tex from the selected LaTeX preset."
    )
    parser.add_argument(
        "--artifact-root",
        required=True,
        help="Artifact workspace root.",
    )
    return parser.parse_args()


def validate_artifact_root(artifact_root: Path) -> Path:
    resolved = artifact_root.resolve(strict=True)
    if not resolved.is_dir():
        raise NotADirectoryError(f"Artifact root is not a directory: {resolved}")
    return resolved


def validate_core_files(artifact_root: Path) -> None:
    missing = [name for name in REQUIRED_CORE_FILES if not (artifact_root / name).is_file()]
    if missing:
        raise FileNotFoundError("Missing required core file(s): " + ", ".join(missing))


def load_target_settings(artifact_root: Path) -> dict[str, object]:
    target_path = artifact_root / "target-settings.json"
    with target_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("user_confirmed") is not True:
        raise ValueError("target-settings.json is not confirmed yet")
    template_id = data.get("latex_template_id")
    if not isinstance(template_id, str) or not template_id:
        raise ValueError("target-settings.json is missing a valid latex_template_id")
    return data


def validate_approved_plan(artifact_root: Path) -> None:
    plan_path = artifact_root / "condensation-plan.md"
    plan_text = plan_path.read_text(encoding="utf-8")
    if "Status: approved" not in plan_text:
        raise ValueError("condensation-plan.md is not approved yet")


def resolve_template_root(script_path: Path) -> Path:
    package_root = script_path.resolve().parent.parent
    return package_root / "assets" / "latex-templates"


def resolve_template_path(template_root: Path, template_id: str) -> Path:
    template_path = template_root / f"{template_id}.tex"
    if not template_path.is_file():
        raise FileNotFoundError(f"Missing LaTeX preset template: {template_path}")
    return template_path


def initialize_final_draft(
    artifact_root: Path,
    template_path: Path,
) -> Path:
    final_draft_path = artifact_root / "final-draft.tex"
    if final_draft_path.exists():
        raise FileExistsError(f"final-draft.tex already exists: {final_draft_path}")
    shutil.copy2(template_path, final_draft_path)
    return final_draft_path


def main() -> int:
    args = parse_args()
    try:
        artifact_root = validate_artifact_root(Path(args.artifact_root))
        validate_core_files(artifact_root)
        target_settings = load_target_settings(artifact_root)
        validate_approved_plan(artifact_root)
        template_root = resolve_template_root(Path(__file__))
        template_id = str(target_settings["latex_template_id"])
        template_path = resolve_template_path(template_root, template_id)
        final_draft_path = initialize_final_draft(artifact_root, template_path)
        result = {
            "artifact_root": str(artifact_root),
            "template_id": template_id,
            "template_path": str(template_path),
            "final_draft_path": str(final_draft_path),
        }
    except Exception as exc:  # pragma: no cover - CLI error path
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Final contract validation entrypoint for converted skill package."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from embedded_skill_package_validator import EmbeddedSkillPackageValidator


def _validate_directory(path: Path, require_version: bool) -> dict[str, object]:
    validator = EmbeddedSkillPackageValidator()
    if not path.exists() or not path.is_dir():
        raise ValueError(f"Invalid skill directory: {path}")
    top_level = path.name
    skill_id, version = validator.validate_skill_dir(
        path,
        top_level_dir=top_level,
        require_version=require_version,
    )
    return {
        "valid": True,
        "source_type": "directory",
        "skill_id": skill_id,
        "version": version,
    }


def _validate_zip(path: Path, require_version: bool) -> dict[str, object]:
    validator = EmbeddedSkillPackageValidator()
    if not path.exists() or not path.is_file():
        raise ValueError(f"Invalid skill package zip: {path}")
    top_level = validator.inspect_zip_top_level_from_path(path)
    with tempfile.TemporaryDirectory(prefix="embedded-skill-validate-") as tmp:
        extracted_root = Path(tmp) / "extracted"
        validator.extract_zip_safe(path, extracted_root)
        skill_dir = extracted_root / top_level
        if not skill_dir.exists():
            raise ValueError("Extracted package missing top-level skill directory")
        skill_id, version = validator.validate_skill_dir(
            skill_dir,
            top_level_dir=top_level,
            require_version=require_version,
        )
    return {
        "valid": True,
        "source_type": "zip",
        "skill_id": skill_id,
        "version": version,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-path", required=True, help="Path to converted skill directory or zip.")
    parser.add_argument(
        "--source-type",
        default="auto",
        choices=["auto", "directory", "zip"],
        help="How to treat --skill-path.",
    )
    parser.add_argument(
        "--require-version",
        default="true",
        choices=["true", "false"],
        help="Whether version in runner.json is required.",
    )
    args = parser.parse_args()

    skill_path = Path(args.skill_path).expanduser().resolve()
    require_version = args.require_version == "true"

    try:
        if args.source_type == "directory":
            payload = _validate_directory(skill_path, require_version=require_version)
        elif args.source_type == "zip":
            payload = _validate_zip(skill_path, require_version=require_version)
        else:
            if skill_path.is_file():
                payload = _validate_zip(skill_path, require_version=require_version)
            elif skill_path.is_dir():
                payload = _validate_directory(skill_path, require_version=require_version)
            else:
                raise ValueError(f"Invalid skill path: {skill_path}")
        print(json.dumps(payload, ensure_ascii=False))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "valid": False,
                    "reason": str(exc),
                    "skill_path": str(skill_path),
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()


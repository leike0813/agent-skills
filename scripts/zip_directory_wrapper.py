#!/usr/bin/env python3
"""Directory-first zip wrapper for skill-converter-agent."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

from embedded_skill_package_validator import EmbeddedSkillPackageValidator


def _unpack(zip_path: Path, dest_dir: Path) -> dict[str, str]:
    validator = EmbeddedSkillPackageValidator()
    if not zip_path.exists() or not zip_path.is_file():
        raise ValueError(f"Invalid zip path: {zip_path}")
    top_level = validator.inspect_zip_top_level_from_path(zip_path)
    validator.extract_zip_safe(zip_path, dest_dir)
    extracted_dir = (dest_dir / top_level).resolve()
    if not extracted_dir.exists() or not extracted_dir.is_dir():
        raise ValueError("Extracted skill directory missing")
    return {
        "mode": "unpack",
        "zip_path": str(zip_path.resolve()),
        "dest_dir": str(dest_dir.resolve()),
        "top_level_dir": top_level,
        "skill_dir": str(extracted_dir),
    }


def _pack(source_dir: Path, output_zip: Path, top_level_name: str | None) -> dict[str, str]:
    if not source_dir.exists() or not source_dir.is_dir():
        raise ValueError(f"Invalid source directory: {source_dir}")
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    root_name = top_level_name.strip() if top_level_name else source_dir.name
    if not root_name:
        raise ValueError("Top-level name must be non-empty")
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in source_dir.rglob("*"):
            if path.is_dir():
                continue
            rel = path.relative_to(source_dir)
            archive.write(path, arcname=f"{root_name}/{rel.as_posix()}")
    return {
        "mode": "pack",
        "source_dir": str(source_dir.resolve()),
        "zip_path": str(output_zip.resolve()),
        "top_level_dir": root_name,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=["unpack", "pack"])
    parser.add_argument("--zip-path", help="Input zip for unpack, output zip for pack.")
    parser.add_argument("--dest-dir", help="Destination directory for unpack.")
    parser.add_argument("--source-dir", help="Source directory for pack.")
    parser.add_argument("--top-level-name", default="", help="Optional top-level directory name in zip.")
    args = parser.parse_args()

    try:
        if args.mode == "unpack":
            if not args.zip_path or not args.dest_dir:
                raise ValueError("unpack mode requires --zip-path and --dest-dir")
            payload = _unpack(
                zip_path=Path(args.zip_path).expanduser().resolve(),
                dest_dir=Path(args.dest_dir).expanduser().resolve(),
            )
        else:
            if not args.source_dir or not args.zip_path:
                raise ValueError("pack mode requires --source-dir and --zip-path")
            payload = _pack(
                source_dir=Path(args.source_dir).expanduser().resolve(),
                output_zip=Path(args.zip_path).expanduser().resolve(),
                top_level_name=args.top_level_name,
            )
        print(json.dumps(payload, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "reason": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == "__main__":
    main()

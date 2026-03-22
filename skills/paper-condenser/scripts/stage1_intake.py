#!/usr/bin/env python3
"""Perform deterministic Stage 1 intake on an initialized artifact workspace."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SUPPORTED_SOURCE_TYPES = {"single_file:md", "single_file:txt", "single_file:tex"}
PREVIEW_CHAR_LIMIT = 500


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run deterministic Stage 1 intake for an artifact workspace."
    )
    parser.add_argument(
        "--artifact-root",
        required=True,
        help="Initialized artifact workspace root.",
    )
    return parser.parse_args()


def validate_artifact_root(artifact_root: Path) -> Path:
    resolved = artifact_root.resolve(strict=True)
    if not resolved.is_dir():
        raise NotADirectoryError(f"Artifact root is not a directory: {resolved}")
    return resolved


def load_manuscript_profile(artifact_root: Path) -> tuple[Path, dict[str, object]]:
    profile_path = artifact_root / "manuscript-profile.json"
    if not profile_path.is_file():
        raise FileNotFoundError(f"Missing manuscript profile: {profile_path}")
    with profile_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return profile_path, data


def validate_source_metadata(profile: dict[str, object]) -> Path:
    source_path_value = profile.get("source_path")
    source_type_value = profile.get("source_type")
    if not isinstance(source_path_value, str) or not source_path_value:
        raise ValueError("manuscript-profile.json is missing a valid source_path")
    if not isinstance(source_type_value, str) or not source_type_value:
        raise ValueError("manuscript-profile.json is missing a valid source_type")
    if source_type_value not in SUPPORTED_SOURCE_TYPES:
        raise ValueError(f"Unsupported source_type for Stage 1 intake: {source_type_value}")

    source_path = Path(source_path_value).resolve(strict=True)
    if not source_path.is_file():
        raise FileNotFoundError(f"Source path is not a file: {source_path}")
    return source_path


def read_source_text(source_path: Path) -> str:
    return source_path.read_text(encoding="utf-8")


def build_source_stats(source_path: Path, text: str) -> dict[str, int]:
    return {
        "char_count": len(text),
        "line_count": len(text.splitlines()),
        "file_size_bytes": source_path.stat().st_size,
    }


def build_content_preview(text: str) -> str:
    normalized = text.strip()
    if len(normalized) <= PREVIEW_CHAR_LIMIT:
        return normalized
    return normalized[:PREVIEW_CHAR_LIMIT].rstrip() + "..."


def update_manuscript_profile(
    profile_path: Path,
    profile: dict[str, object],
    content_preview: str,
    source_stats: dict[str, int],
) -> list[str]:
    profile["content_preview"] = content_preview
    profile["source_stats"] = source_stats
    profile["intake_status"] = "complete"

    with profile_path.open("w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
        f.write("\n")

    return ["content_preview", "source_stats", "intake_status"]


def main() -> int:
    args = parse_args()
    try:
        artifact_root = validate_artifact_root(Path(args.artifact_root))
        profile_path, profile = load_manuscript_profile(artifact_root)
        source_path = validate_source_metadata(profile)
        source_text = read_source_text(source_path)
        source_stats = build_source_stats(source_path, source_text)
        content_preview = build_content_preview(source_text)
        updated_fields = update_manuscript_profile(
            profile_path,
            profile,
            content_preview,
            source_stats,
        )
        result = {
            "artifact_root": str(artifact_root),
            "updated_fields": updated_fields,
            "source_stats": source_stats,
        }
    except Exception as exc:  # pragma: no cover - CLI error path
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Bootstrap a runtime artifact workspace from a manuscript file path."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from init_artifacts import (
    initialize_workspace,
    resolve_template_root,
    validate_template_root,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap a runtime artifact workspace from a source file."
    )
    parser.add_argument(
        "--source-path",
        required=True,
        help="Source manuscript file path.",
    )
    return parser.parse_args()


def validate_source_path(source_path: Path) -> Path:
    resolved = source_path.resolve(strict=True)
    if not resolved.is_file():
        raise FileNotFoundError(f"Source path is not a file: {resolved}")
    return resolved


def slugify_source_name(source_path: Path) -> str:
    raw = source_path.stem.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw)
    slug = slug.strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        raise ValueError(f"Cannot derive a valid document slug from: {source_path.name}")
    return slug


def resolve_artifact_root(script_path: Path, document_slug: str) -> Path:
    _ = script_path
    project_root = Path.cwd().resolve()
    return project_root / ".paper-condenser-tmp" / document_slug


def detect_source_type(source_path: Path) -> str:
    suffix = source_path.suffix.lower()
    if suffix:
        return f"single_file:{suffix.lstrip('.')}"
    return "single_file:unknown"


def seed_manuscript_profile(
    artifact_root: Path,
    document_slug: str,
    source_path: Path,
) -> None:
    profile_path = artifact_root / "manuscript-profile.json"
    with profile_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    data["source_id"] = document_slug
    data["source_path"] = str(source_path)
    data["source_type"] = detect_source_type(source_path)
    data["scope"] = "full_document"
    data["status"] = "initialized"

    with profile_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main() -> int:
    args = parse_args()
    try:
        source_path = validate_source_path(Path(args.source_path))
        document_slug = slugify_source_name(source_path)
        artifact_root = resolve_artifact_root(Path(__file__), document_slug)
        if artifact_root.exists():
            raise FileExistsError(
                f"Artifact root already exists for document slug '{document_slug}': {artifact_root}"
            )

        template_root = resolve_template_root(Path(__file__))
        validate_template_root(template_root)
        init_result = initialize_workspace(template_root, artifact_root)
        seed_manuscript_profile(artifact_root, document_slug, source_path)

        result = {
            "document_slug": document_slug,
            "artifact_root": str(artifact_root),
            "created_files": init_result["created_files"],
        }
    except Exception as exc:  # pragma: no cover - CLI error path
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

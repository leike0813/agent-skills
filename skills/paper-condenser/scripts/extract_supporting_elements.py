#!/usr/bin/env python3
"""Extract deterministic figure, table, citation, and bibliography inventory."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SUPPORTED_SOURCE_TYPES = {"single_file:tex"}
CAPTION_PREVIEW_LIMIT = 160

FIGURE_PATTERN = re.compile(r"\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}", re.DOTALL)
TABLE_PATTERN = re.compile(r"\\begin\{table\*?\}(.*?)\\end\{table\*?\}", re.DOTALL)
CAPTION_PATTERN = re.compile(r"\\caption(?:\[[^\]]*\])?\{([^}]*)\}", re.DOTALL)
LABEL_PATTERN = re.compile(r"\\label\{([^}]*)\}")
INCLUDEGRAPHICS_PATTERN = re.compile(
    r"\\includegraphics(?:\[[^\]]*\])?\{([^}]*)\}"
)
CITE_PATTERN = re.compile(
    r"\\[A-Za-z]*cite[a-zA-Z*]*\s*(?:\[[^\]]*\]\s*){0,2}\{([^}]*)\}"
)
BIBLIOGRAPHY_PATTERN = re.compile(r"\\bibliography\{([^}]*)\}")
ADDBIBRESOURCE_PATTERN = re.compile(
    r"\\addbibresource(?:\[[^\]]*\])?\{([^}]*)\}"
)
BIBITEM_PATTERN = re.compile(r"\\bibitem(?:\[[^\]]*\])?\{([^}]*)\}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract deterministic supporting-elements inventory."
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


def load_manuscript_profile(artifact_root: Path) -> tuple[Path, dict[str, object]]:
    profile_path = artifact_root / "manuscript-profile.json"
    if not profile_path.is_file():
        raise FileNotFoundError(f"Missing manuscript profile: {profile_path}")
    with profile_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return profile_path, data


def validate_source_metadata(profile: dict[str, object]) -> Path:
    source_path_value = profile.get("source_path")
    source_type_value = profile.get("source_type")
    if not isinstance(source_path_value, str) or not source_path_value:
        raise ValueError("manuscript-profile.json is missing a valid source_path")
    if not isinstance(source_type_value, str) or not source_type_value:
        raise ValueError("manuscript-profile.json is missing a valid source_type")
    if source_type_value not in SUPPORTED_SOURCE_TYPES:
        raise ValueError(
            "Unsupported source_type for supporting-elements extraction: "
            f"{source_type_value}"
        )

    source_path = Path(source_path_value).resolve(strict=True)
    if not source_path.is_file():
        raise FileNotFoundError(f"Source path is not a file: {source_path}")
    return source_path


def line_number(text: str, char_index: int) -> int:
    return text.count("\n", 0, char_index) + 1


def normalize_preview(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    if len(normalized) <= CAPTION_PREVIEW_LIMIT:
        return normalized
    return normalized[:CAPTION_PREVIEW_LIMIT].rstrip() + "..."


def extract_caption(block: str) -> str:
    match = CAPTION_PATTERN.search(block)
    if not match:
        return ""
    return normalize_preview(match.group(1))


def extract_label(block: str) -> str:
    match = LABEL_PATTERN.search(block)
    if not match:
        return ""
    return match.group(1).strip()


def extract_graphics_paths(block: str) -> list[str]:
    return [match.group(1).strip() for match in INCLUDEGRAPHICS_PATTERN.finditer(block)]


def extract_float_inventory(
    text: str, pattern: re.Pattern[str], kind: str
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for index, match in enumerate(pattern.finditer(text), start=1):
        block = match.group(0)
        items.append(
            {
                "index": index,
                "kind": kind,
                "label": extract_label(block),
                "caption_preview": extract_caption(block),
                "asset_paths": extract_graphics_paths(block),
                "source_line_start": line_number(text, match.start()),
                "source_line_end": line_number(text, match.end()),
            }
        )
    return items


def extract_citations(text: str) -> list[dict[str, object]]:
    citations: list[dict[str, object]] = []
    for index, match in enumerate(CITE_PATTERN.finditer(text), start=1):
        raw_keys = match.group(1)
        keys = [key.strip() for key in raw_keys.split(",") if key.strip()]
        citations.append(
            {
                "index": index,
                "command": match.group(0).split("{", 1)[0].strip(),
                "keys": keys,
                "source_line": line_number(text, match.start()),
            }
        )
    return citations


def extract_bibliography(text: str) -> dict[str, object]:
    resources: list[str] = []
    for pattern in (BIBLIOGRAPHY_PATTERN, ADDBIBRESOURCE_PATTERN):
        for match in pattern.finditer(text):
            resources.extend(
                resource.strip() for resource in match.group(1).split(",") if resource.strip()
            )

    bibitems = [match.group(1).strip() for match in BIBITEM_PATTERN.finditer(text)]
    mode = "none"
    if resources:
        mode = "bibtex"
    elif "\\begin{thebibliography}" in text:
        mode = "thebibliography"

    return {
        "mode": mode,
        "resources": resources,
        "entries": bibitems,
    }


def build_inventory(text: str) -> dict[str, object]:
    return {
        "figures": extract_float_inventory(text, FIGURE_PATTERN, "figure"),
        "tables": extract_float_inventory(text, TABLE_PATTERN, "table"),
        "citations": extract_citations(text),
        "bibliography": extract_bibliography(text),
    }


def update_manuscript_profile(
    profile_path: Path,
    profile: dict[str, object],
    inventory: dict[str, object],
) -> list[str]:
    profile["supporting_elements_status"] = "complete"
    profile["supporting_elements"] = inventory

    with profile_path.open("w", encoding="utf-8") as handle:
        json.dump(profile, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    return ["supporting_elements_status", "supporting_elements"]


def main() -> int:
    args = parse_args()
    try:
        artifact_root = validate_artifact_root(Path(args.artifact_root))
        profile_path, profile = load_manuscript_profile(artifact_root)
        source_path = validate_source_metadata(profile)
        source_text = source_path.read_text(encoding="utf-8")
        inventory = build_inventory(source_text)
        updated_fields = update_manuscript_profile(profile_path, profile, inventory)
        figures = inventory["figures"]
        tables = inventory["tables"]
        citations = inventory["citations"]
        bibliography = inventory["bibliography"]
        if not isinstance(figures, list) or not isinstance(tables, list):
            raise ValueError("supporting-elements inventory has invalid float lists")
        if not isinstance(citations, list):
            raise ValueError("supporting-elements inventory has invalid citation list")
        if not isinstance(bibliography, dict):
            raise ValueError("supporting-elements inventory has invalid bibliography block")
        bibliography_mode = bibliography.get("mode")
        if not isinstance(bibliography_mode, str):
            raise ValueError("supporting-elements inventory has invalid bibliography mode")
        result = {
            "artifact_root": str(artifact_root),
            "updated_fields": updated_fields,
            "figure_count": len(figures),
            "table_count": len(tables),
            "citation_count": len(citations),
            "bibliography_mode": bibliography_mode,
        }
    except Exception as exc:  # pragma: no cover - CLI error path
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TMP_DIRNAME = ".literature_digest_tmp"
REFERENCES_SCOPE_FILENAME = "references_scope.json"
REFERENCES_PARTS_DIRNAME = "references.parts"
REFERENCES_MERGED_FILENAME = "references_merged.json"
DEFAULT_BATCH_SIZE = 15

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
REFERENCE_HEADING_RE = re.compile(r"^(references|bibliography|works cited|参考文献)$", re.IGNORECASE)
ENTRY_START_RES = [
    re.compile(r"^\s*\[\d+\]\s+"),
    re.compile(r"^\s*\d+\.\s+"),
    re.compile(r"^\s*\d+\)\s+"),
]
AUTHOR_YEAR_START_RE = re.compile(
    r"^\s*[A-ZÀ-ÖØ-öø-ÿ][^.\n]{0,120}(?:\((?:19|20)\d{2}[a-z]?\)|,\s*(?:19|20)\d{2}[a-z]?)"
)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
DOI_RE = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s)]+", re.IGNORECASE)
ARXIV_RE = re.compile(r"(arXiv:\d{4}\.\d{4,5}|arxiv\.org/abs/[^\s)]+)", re.IGNORECASE)


@dataclass
class ReferencesScope:
    section_title: str
    line_start: int
    line_end: int


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _atomic_publish(src_path: Path, publish_path: Path) -> None:
    publish_path.parent.mkdir(parents=True, exist_ok=True)
    temp_publish = publish_path.with_suffix(publish_path.suffix + ".tmp")
    temp_publish.write_text(src_path.read_text(encoding="utf-8"), encoding="utf-8")
    os.replace(temp_publish, publish_path)


def _normalize_heading(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip())


def find_references_scope(lines: list[str]) -> ReferencesScope | None:
    headings: list[tuple[int, int, str]] = []
    for idx, line in enumerate(lines, start=1):
        match = HEADING_RE.match(line.strip())
        if match is None:
            continue
        headings.append((idx, len(match.group(1)), match.group(2).strip()))

    candidates: list[ReferencesScope] = []
    for idx, level, title in headings:
        if REFERENCE_HEADING_RE.match(_normalize_heading(title)) is None:
            continue
        end_line = len(lines)
        for next_idx, next_level, _ in headings:
            if next_idx <= idx:
                continue
            if next_level <= level:
                end_line = next_idx - 1
                break
        if end_line > idx:
            candidates.append(ReferencesScope(section_title=title, line_start=idx + 1, line_end=end_line))

    if not candidates:
        return None

    reasonable = [scope for scope in candidates if sum(bool(lines[i - 1].strip()) for i in range(scope.line_start, scope.line_end + 1)) >= 3]
    return reasonable[-1] if reasonable else candidates[-1]


def _is_entry_start(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if any(regex.match(stripped) for regex in ENTRY_START_RES):
        return True
    return AUTHOR_YEAR_START_RE.match(stripped) is not None


def split_reference_entries(lines: list[str]) -> list[str]:
    entries: list[str] = []
    current: list[str] = []
    saw_explicit_start = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                current.append("")
            continue

        if _is_entry_start(line):
            saw_explicit_start = True
            if current:
                entries.append(_collapse_entry_lines(current))
                current = []
            current.append(stripped)
            continue

        if not current:
            current.append(stripped)
        else:
            current.append(stripped)

    if current:
        entries.append(_collapse_entry_lines(current))

    if saw_explicit_start:
        return [entry for entry in entries if entry]

    return _split_by_blank_groups(lines)


def _split_by_blank_groups(lines: list[str]) -> list[str]:
    groups: list[str] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                groups.append(_collapse_entry_lines(current))
                current = []
            continue
        current.append(stripped)
    if current:
        groups.append(_collapse_entry_lines(current))
    return [group for group in groups if group]


def _collapse_entry_lines(lines: list[str]) -> str:
    text = " ".join(part.strip() for part in lines if part.strip())
    return re.sub(r"\s+", " ", text).strip()


def _extract_year(raw: str) -> int | None:
    match = YEAR_RE.search(raw)
    if match is None:
        return None
    return int(match.group(0))


def build_reference_placeholder(raw: str) -> dict[str, Any]:
    item: dict[str, Any] = {
        "author": [],
        "title": "",
        "year": _extract_year(raw),
        "raw": raw,
        "confidence": 0.1,
    }

    doi_match = DOI_RE.search(raw)
    url_match = URL_RE.search(raw)
    arxiv_match = ARXIV_RE.search(raw)

    if doi_match is not None:
        item["DOI"] = doi_match.group(1)
        item["confidence"] = 0.2
    if url_match is not None:
        item["url"] = url_match.group(0)
        item["confidence"] = max(float(item["confidence"]), 0.2)
    if arxiv_match is not None:
        item["arxiv"] = arxiv_match.group(1)
        item["confidence"] = max(float(item["confidence"]), 0.2)

    return item


def _normalize_reference_item(item: object) -> dict[str, Any]:
    if isinstance(item, str):
        return build_reference_placeholder(item)
    if not isinstance(item, dict):
        return build_reference_placeholder("")

    normalized = dict(item)
    normalized["author"] = [str(author) for author in normalized.get("author", []) if author is not None]
    normalized["title"] = "" if normalized.get("title") is None else str(normalized.get("title"))
    year = normalized.get("year")
    if isinstance(year, bool):
        year = None
    elif isinstance(year, float) and year.is_integer():
        year = int(year)
    elif not isinstance(year, int):
        year = _extract_year(str(year)) if year is not None else None
    normalized["year"] = year
    normalized["raw"] = "" if normalized.get("raw") is None else str(normalized.get("raw"))
    confidence = normalized.get("confidence", 0.1)
    if not isinstance(confidence, (int, float)):
        confidence = 0.1
    normalized["confidence"] = max(0.0, min(1.0, float(confidence)))
    return normalized


def _part_sort_key(path: Path) -> tuple[int, str]:
    match = re.search(r"part-(\d+)\.json$", path.name)
    if match is None:
        return (10**9, path.name)
    return (int(match.group(1)), path.name)


def stage_references(md_path: Path, tmp_dir: Path, batch_size: int) -> dict[str, Any]:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    scope = find_references_scope(lines)
    if scope is None:
        return {
            "references_scope_path": "",
            "parts_dir": "",
            "part_count": 0,
            "entry_count": 0,
            "error": {"code": "references_stage_failed", "message": "references section not found"},
        }

    scope_path = tmp_dir / REFERENCES_SCOPE_FILENAME
    parts_dir = tmp_dir / REFERENCES_PARTS_DIRNAME
    parts_dir.mkdir(parents=True, exist_ok=True)
    for old_part in parts_dir.glob("part-*.json"):
        old_part.unlink()

    scope_payload = {
        "section_title": scope.section_title,
        "line_start": scope.line_start,
        "line_end": scope.line_end,
    }
    _write_json(scope_path, scope_payload)

    reference_lines = lines[scope.line_start - 1 : scope.line_end]
    entries = split_reference_entries(reference_lines)
    for batch_index, start in enumerate(range(0, len(entries), batch_size), start=1):
        batch_entries = entries[start : start + batch_size]
        part_payload = [build_reference_placeholder(entry) for entry in batch_entries]
        _write_json(parts_dir / f"part-{batch_index:03d}.json", part_payload)

    return {
        "references_scope_path": str(scope_path),
        "parts_dir": str(parts_dir),
        "part_count": len(list(parts_dir.glob("part-*.json"))),
        "entry_count": len(entries),
        "error": None,
    }


def merge_references(parts_dir: Path, merged_path: Path, publish_path: Path | None) -> dict[str, Any]:
    part_paths = sorted(parts_dir.glob("part-*.json"), key=_part_sort_key)
    if not part_paths:
        return {
            "references_merged_path": "",
            "references_path": "",
            "item_count": 0,
            "error": {"code": "references_merge_failed", "message": "no reference part files found"},
        }

    merged_items: list[dict[str, Any]] = []
    for part_path in part_paths:
        try:
            part_obj = json.loads(part_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return {
                "references_merged_path": "",
                "references_path": "",
                "item_count": 0,
                "error": {
                    "code": "references_merge_failed",
                    "message": f"unable to parse {part_path.name}: {exc}",
                },
            }
        if not isinstance(part_obj, list):
            return {
                "references_merged_path": "",
                "references_path": "",
                "item_count": 0,
                "error": {"code": "references_merge_failed", "message": f"{part_path.name} must be a JSON array"},
            }
        merged_items.extend(_normalize_reference_item(item) for item in part_obj)

    _write_json(merged_path, merged_items)
    published = ""
    if publish_path is not None:
        _atomic_publish(merged_path, publish_path)
        published = str(publish_path)

    return {
        "references_merged_path": str(merged_path),
        "references_path": published,
        "item_count": len(merged_items),
        "error": None,
    }


def _default_tmp_dir() -> Path:
    return Path.cwd() / TMP_DIRNAME


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage and merge reference artifacts for literature-digest.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    stage_parser = subparsers.add_parser("stage")
    stage_parser.add_argument("--md-path", required=True)
    stage_parser.add_argument("--tmp-dir", default="")
    stage_parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)

    merge_parser = subparsers.add_parser("merge")
    merge_parser.add_argument("--parts-dir", required=True)
    merge_parser.add_argument("--merged-path", default="")
    merge_parser.add_argument("--publish-path", default="")

    args = parser.parse_args()

    if args.command == "stage":
        tmp_dir = Path(args.tmp_dir) if args.tmp_dir else _default_tmp_dir()
        result = stage_references(Path(args.md_path), tmp_dir, max(1, args.batch_size))
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["error"] is None else 2

    merged_path = Path(args.merged_path) if args.merged_path else _default_tmp_dir() / REFERENCES_MERGED_FILENAME
    publish_path = Path(args.publish_path) if args.publish_path else None
    result = merge_references(Path(args.parts_dir), merged_path, publish_path)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["error"] is None else 2


if __name__ == "__main__":
    raise SystemExit(main())

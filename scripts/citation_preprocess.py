from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


TMP_DIRNAME = ".literature_digest_tmp"
TMP_FILENAME = "citation_preprocess.json"

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
BRACKET_NUMERIC_RE = re.compile(r"\[([^\[\]\n]{1,160})\]")
AUTHOR_YEAR_PARENS_RE = re.compile(r"\(([^()\n]{0,200}(?:19|20)\d{2}[a-z]?[^()\n]{0,200})\)")
AUTHOR_YEAR_NARRATIVE_RE = re.compile(r"\b([A-Z][A-Za-z'`-]+(?:\s+et al\.)?)\s*\(((?:19|20)\d{2}[a-z]?)\)")
YEAR_RE = re.compile(r"\b((?:19|20)\d{2})[a-z]?\b")
RANGE_RE = re.compile(r"^(\d+)\s*[-–—]\s*(\d+)$")
NUMBER_RE = re.compile(r"^\d+$")
SURNAME_RE = re.compile(r"[A-Za-z][A-Za-z'`-]+")


@dataclass
class Scope:
    section_title: str
    line_start: int
    line_end: int
    source: str


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_heading_title(title: str) -> str:
    stripped = title.strip()
    stripped = re.sub(r"^\s*(?:\d+(?:\.\d+)*|[IVXLCMivxlcm]+)[\.\)\-:]?\s+", "", stripped)
    return stripped.strip()


def _is_introduction_title(title: str) -> bool:
    normalized = _normalize_heading_title(title)
    lowered = normalized.lower()
    return lowered.startswith("introduction") or normalized.startswith("引言") or normalized.startswith("绪论")


def _find_intro_scope(lines: list[str]) -> Scope | None:
    headings: list[tuple[int, int, str]] = []
    for idx, line in enumerate(lines, start=1):
        match = HEADING_RE.match(line.strip())
        if not match:
            continue
        level = len(match.group(1))
        title = match.group(2).strip()
        headings.append((idx, level, title))

    intro: tuple[int, int, str] | None = None
    for heading in headings:
        if _is_introduction_title(heading[2]):
            intro = heading
            break

    if intro is None:
        return None

    intro_line, intro_level, intro_title = intro
    scope_end = len(lines)
    for line_no, level, _ in headings:
        if line_no <= intro_line:
            continue
        if level <= intro_level:
            scope_end = line_no - 1
            break

    return Scope(section_title=intro_title, line_start=intro_line, line_end=max(intro_line, scope_end), source="intro_fallback")


def _scope_from_obj(obj: object) -> Scope | None:
    if not isinstance(obj, dict):
        return None
    section_title = obj.get("section_title")
    line_start = obj.get("line_start")
    line_end = obj.get("line_end")
    if not isinstance(section_title, str):
        return None
    if not isinstance(line_start, int) or not isinstance(line_end, int):
        return None
    return Scope(section_title=section_title, line_start=line_start, line_end=line_end, source="agent")


def _load_scope_from_file(path: Path) -> Scope | None:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None

    direct = _scope_from_obj(obj)
    if direct is not None:
        return direct

    if isinstance(obj, dict):
        for key in ["analysis_scope", "review_scope", "scope"]:
            candidate = _scope_from_obj(obj.get(key))
            if candidate is not None:
                return candidate
        meta = obj.get("meta")
        if isinstance(meta, dict):
            candidate = _scope_from_obj(meta.get("scope"))
            if candidate is not None:
                return candidate
    return None


def _validate_scope(scope: Scope, total_lines: int) -> str | None:
    if scope.line_start <= 0 or scope.line_end <= 0:
        return "line_start/line_end must be positive integers"
    if scope.line_start > scope.line_end:
        return "line_start must be <= line_end"
    if scope.line_end > total_lines:
        return f"line_end out of range: {scope.line_end} > {total_lines}"
    return None


def _resolve_scope(args: argparse.Namespace, lines: list[str]) -> tuple[Scope | None, str | None]:
    if args.scope_start is not None or args.scope_end is not None:
        if args.scope_start is None or args.scope_end is None:
            return None, "both --scope-start and --scope-end are required when one is provided"
        scope = Scope(
            section_title=args.scope_title or "Review Scope",
            line_start=args.scope_start,
            line_end=args.scope_end,
            source="agent",
        )
        return scope, _validate_scope(scope, len(lines))

    if args.scope_file:
        scope_file = Path(args.scope_file)
        if not scope_file.exists():
            return None, f"scope file not found: {scope_file}"
        parsed_scope = _load_scope_from_file(scope_file)
        if parsed_scope is None:
            return None, f"unable to parse scope from file: {scope_file}"
        return parsed_scope, _validate_scope(parsed_scope, len(lines))

    fallback = _find_intro_scope(lines)
    if fallback is None:
        return None, "no agent scope provided and introduction fallback failed"
    return fallback, _validate_scope(fallback, len(lines))


def _expand_numeric_part(part: str) -> list[int]:
    cleaned = part.strip()
    if not cleaned:
        return []

    range_match = RANGE_RE.match(cleaned)
    if range_match:
        start = int(range_match.group(1))
        end = int(range_match.group(2))
        if start > end:
            start, end = end, start
        if end - start > 200:
            return []
        return list(range(start, end + 1))

    if NUMBER_RE.match(cleaned):
        return [int(cleaned)]
    return []


def _extract_numeric_mentions(line: str, line_no: int, mention_seed: int) -> tuple[list[dict[str, Any]], int]:
    mentions: list[dict[str, Any]] = []
    current = mention_seed
    for bracket_match in BRACKET_NUMERIC_RE.finditer(line):
        inside = bracket_match.group(1)
        if not re.search(r"\d", inside):
            continue

        expanded: list[int] = []
        for part in re.split(r"[;,]", inside):
            expanded.extend(_expand_numeric_part(part))

        for ref_number in expanded:
            mention = {
                "mention_id": f"m{current:05d}",
                "marker": f"[{ref_number}]",
                "style": "numeric",
                "line_start": line_no,
                "line_end": line_no,
                "snippet": line.strip(),
                "ref_number_hint": ref_number,
            }
            mentions.append(mention)
            current += 1

    return mentions, current


def _extract_surname(segment: str) -> str | None:
    candidate = segment.strip()
    if not candidate:
        return None

    candidate = candidate.split(",")[0].strip()
    candidate = re.split(r"\bet al\.?\b", candidate, flags=re.IGNORECASE)[0].strip()
    candidate = re.split(r"\band\b|&", candidate, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    surname_matches = SURNAME_RE.findall(candidate)
    if not surname_matches:
        return None
    return surname_matches[-1]


def _extract_author_year_mentions(line: str, line_no: int, mention_seed: int) -> tuple[list[dict[str, Any]], int]:
    mentions: list[dict[str, Any]] = []
    current = mention_seed

    seen: set[tuple[str, int]] = set()
    for parenthetical in AUTHOR_YEAR_PARENS_RE.finditer(line):
        group_text = parenthetical.group(1)
        for segment in [seg.strip() for seg in group_text.split(";") if seg.strip()]:
            year_match = YEAR_RE.search(segment)
            if year_match is None:
                continue
            year = int(year_match.group(1))
            surname = _extract_surname(segment)
            marker = f"({segment})"
            key = (marker, year)
            if key in seen:
                continue
            seen.add(key)
            mention = {
                "mention_id": f"m{current:05d}",
                "marker": marker,
                "style": "author-year",
                "line_start": line_no,
                "line_end": line_no,
                "snippet": line.strip(),
                "year_hint": year,
                "surname_hint": surname,
            }
            mentions.append(mention)
            current += 1

    for narrative in AUTHOR_YEAR_NARRATIVE_RE.finditer(line):
        surname_candidate = narrative.group(1).strip()
        year_text = narrative.group(2)
        year = int(year_text[:4])
        surname = _extract_surname(surname_candidate)
        marker = f"{surname_candidate} ({year_text})"
        key = (marker, year)
        if key in seen:
            continue
        seen.add(key)
        mention = {
            "mention_id": f"m{current:05d}",
            "marker": marker,
            "style": "author-year",
            "line_start": line_no,
            "line_end": line_no,
            "snippet": line.strip(),
            "year_hint": year,
            "surname_hint": surname,
        }
        mentions.append(mention)
        current += 1

    return mentions, current


def _extract_mentions(lines: list[str], scope: Scope) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    counter = 1
    for line_no in range(scope.line_start, scope.line_end + 1):
        line = lines[line_no - 1]
        numeric_mentions, counter = _extract_numeric_mentions(line, line_no, counter)
        author_year_mentions, counter = _extract_author_year_mentions(line, line_no, counter)
        mentions.extend(numeric_mentions)
        mentions.extend(author_year_mentions)
    return mentions


def _default_output_path() -> Path:
    return Path.cwd() / TMP_DIRNAME / TMP_FILENAME


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic citation preprocess for literature-digest.")
    parser.add_argument("--md-path", required=True, help="Path to source markdown file.")
    parser.add_argument("--language", default="zh-CN", help="Target language hint.")
    parser.add_argument("--references-path", default="", help="Path to references.json (optional).")
    parser.add_argument("--out", dest="out_path", default="", help="Output preprocess JSON path.")
    parser.add_argument("--scope-file", default="", help="Optional JSON file that contains analysis scope.")
    parser.add_argument("--scope-start", type=int, default=None, help="Optional analysis scope start line (1-based).")
    parser.add_argument("--scope-end", type=int, default=None, help="Optional analysis scope end line (1-based).")
    parser.add_argument("--scope-title", default="", help="Optional scope title when --scope-start/--scope-end are set.")
    args = parser.parse_args()

    md_path = Path(args.md_path)
    out_path = Path(args.out_path) if args.out_path else _default_output_path()
    references_path = Path(args.references_path) if args.references_path else None

    payload: dict[str, Any] = {
        "meta": {
            "generated_at": utc_now_iso(),
            "md_path": str(md_path),
            "language": args.language,
            "references_path": str(references_path) if references_path else "",
            "scope": None,
            "scope_source": "",
        },
        "mentions": [],
        "stats": {
            "total_mentions": 0,
            "numeric_mentions": 0,
            "author_year_mentions": 0,
        },
        "error": None,
    }

    if not md_path.exists():
        payload["error"] = {"code": "FILE_NOT_FOUND", "message": f"md_path not found: {md_path}"}
        print(json.dumps(payload, ensure_ascii=False))
        return 2

    try:
        text = md_path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        payload["error"] = {"code": "READ_FAILED", "message": str(exc)}
        print(json.dumps(payload, ensure_ascii=False))
        return 2

    lines = text.splitlines()
    scope, scope_error = _resolve_scope(args, lines)
    if scope_error is not None or scope is None:
        payload["error"] = {"code": "SCOPE_NOT_FOUND", "message": scope_error or "analysis scope not found."}
    else:
        mentions = _extract_mentions(lines, scope)
        payload["meta"]["scope"] = {
            "section_title": scope.section_title,
            "line_start": scope.line_start,
            "line_end": scope.line_end,
        }
        payload["meta"]["scope_source"] = scope.source
        payload["mentions"] = mentions
        payload["stats"]["total_mentions"] = len(mentions)
        payload["stats"]["numeric_mentions"] = sum(1 for mention in mentions if mention.get("style") == "numeric")
        payload["stats"]["author_year_mentions"] = sum(
            1 for mention in mentions if mention.get("style") == "author-year"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"preprocess_path": str(out_path), "error": payload["error"]}, ensure_ascii=False))
    return 0 if payload["error"] is None else 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from jsonschema import validate  # type: ignore[import-untyped]

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from runtime_db import (  # noqa: E402
    add_runtime_warning,
    add_runtime_warning_once,
    build_citation_render_context,
    build_citation_report_render_context,
    build_digest_render_context,
    build_public_output_payload,
    build_references_render_context,
    connect_db,
    count_citation_mentions,
    default_db_path,
    fetch_artifact_registry,
    fetch_citation_items,
    fetch_citation_mention_links,
    fetch_citation_mentions,
    fetch_citation_summary,
    fetch_citation_timeline,
    fetch_citation_unmapped_mentions,
    fetch_citation_workset_items,
    fetch_latest_error,
    fetch_reference_entries,
    fetch_reference_items,
    fetch_reference_parse_candidates,
    fetch_runtime_inputs,
    fetch_section_scope,
    fetch_source_document,
    initialize_database,
    register_artifact,
    set_runtime_error,
    set_runtime_input,
    set_workflow_state,
    store_citation_batch,
    store_citation_items,
    store_citation_mention_links,
    store_citation_mentions,
    store_citation_summary,
    store_citation_timeline,
    store_citation_unmapped_mentions,
    store_citation_workset_items,
    store_digest_section_summaries,
    store_digest_slots,
    store_outline_nodes,
    store_reference_batch,
    store_reference_entries,
    store_reference_items,
    store_reference_parse_candidates,
    store_section_scope,
    store_source_document,
)


TMP_DIRNAME = ".literature_digest_tmp"
SOURCE_MD_FILENAME = "source.md"
SOURCE_META_FILENAME = "source_meta.json"
CITATION_EXPORT_FILENAME = "citation_workset_export.json"
CITATION_REVIEW_EXPORT_FILENAME = "citation_workset_review.json"
REFERENCES_EXPORT_FILENAME = "references_workset_export.json"
REFERENCES_REVIEW_EXPORT_FILENAME = "references_workset_review.json"
PDF_SIGNATURE = b"%PDF-"

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
BRACKET_NUMERIC_RE = re.compile(r"\[([^\[\]\n]{1,160})\]")
AUTHOR_YEAR_PARENS_RE = re.compile(r"\(([^()\n]{0,200}(?:19|20)\d{2}[a-z]?[^()\n]{0,200})\)")
AUTHOR_YEAR_NARRATIVE_RE = re.compile(r"\b([A-Z][A-Za-z'`-]+(?:\s+et al\.)?)\s*\(((?:19|20)\d{2}[a-z]?)\)")
YEAR_RE = re.compile(r"\b((?:19|20)\d{2})[a-z]?\b")
RANGE_RE = re.compile(r"^(\d+)\s*[-–—]\s*(\d+)$")
NUMBER_RE = re.compile(r"^\d+$")
SURNAME_RE = re.compile(r"[A-Za-z][A-Za-z'`-]+")
REFERENCES_RE = re.compile(r"\b(references|bibliography)\b|参考文献", re.IGNORECASE)
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)\n]+\)")
URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
RESOURCE_PATH_RE = re.compile(r"(?:[A-Za-z]:\\|\.{0,2}/|/)\S+\.(?:png|jpe?g|gif|svg|pdf)\b", re.IGNORECASE)
RESOURCE_SUFFIX_RE = re.compile(r"\.(?:png|jpe?g|gif|svg|pdf)\b", re.IGNORECASE)
DATE_LIKE_RE = re.compile(
    r"\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|"
    r"January|February|March|April|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)
TERMINAL_PUBLICATION_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b(?!\.\d)")
REFERENCE_ENTRY_START_RE = re.compile(r"^(?:\[\d+\]|\d+[\.\)])\s*")
COMMA_STYLE_AUTHOR_RE = re.compile(r"[A-Z][A-Za-z'`-]+,\s*(?:[A-Z][A-Za-z.-]*\.?(?:\s*[A-Z][A-Za-z.-]*\.?)*)")
LEADING_PUNCTUATION_RE = re.compile(r"^[,.;:]\s*")

OUTLINE_NODE_REQUIRED_KEYS = (
    "node_id",
    "heading_level",
    "title",
    "line_start",
    "line_end",
    "parent_node_id",
)
SCOPE_REQUIRED_KEYS = (
    "section_title",
    "line_start",
    "line_end",
    "metadata",
)

WARNING_REFERENCE_LOW_CONFIDENCE = "reference_parse_low_confidence"
WARNING_REFERENCE_PATTERN_AMBIGUOUS = "reference_pattern_ambiguous"
WARNING_REFERENCE_TITLE_BOUNDARY_SUSPECT = "reference_title_boundary_suspect"
WARNING_REFERENCE_AUTHOR_OVERSPLIT = "reference_author_oversplit_detected"
WARNING_CITATION_FALSE_POSITIVE_FILTERED = "citation_false_positive_filtered"
WARNING_CITATION_TIMELINE_MISSING_YEAR = "citation_timeline_missing_year"
WARNING_SCOPE_FALLBACK_USED = "scope_fallback_used"
WARNING_DIGEST_UNDERCOVERAGE = "digest_undercoverage"
LITERAL_STRING_RE = re.compile(r"\((?:\\.|[^\\)])*\)")
TJ_ARRAY_RE = re.compile(r"\[(.*?)\]\s*TJ", re.DOTALL)
TJ_SINGLE_RE = re.compile(r"(\((?:\\.|[^\\)])*\))\s*Tj")
TEXT_BLOCK_RE = re.compile(r"BT(.*?)ET", re.DOTALL)

DIGEST_FILENAME = "digest.md"
REFERENCES_FILENAME = "references.json"
CITATION_ANALYSIS_FILENAME = "citation_analysis.json"
CITATION_ANALYSIS_REPORT_FILENAME = "citation_analysis.md"
STAGE_ERROR_CODES = {
    "digest_stage_failed",
    "references_stage_failed",
    "references_merge_failed",
    "citation_scope_failed",
    "citation_semantics_failed",
    "citation_timeline_failed",
    "citation_report_failed",
    "citation_merge_failed",
    "normalize_source_failed",
}
ALLOWED_CITATION_FUNCTIONS = {
    "background",
    "baseline",
    "contrast",
    "component",
    "dataset",
    "tooling",
    "historical",
    "uncategorized",
}

ASSETS_DIR = SCRIPT_DIR.parent / "assets"
TEMPLATES_DIR = ASSETS_DIR / "templates"
RENDER_SCHEMAS_DIR = ASSETS_DIR / "render_schemas"


@dataclass
class DispatchPaths:
    source_md_path: Path
    source_meta_path: Path


@dataclass
class Scope:
    section_title: str
    line_start: int
    line_end: int
    source: str


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha.update(chunk)
    return f"sha256:{sha.hexdigest()}"


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json_payload(path_value: str) -> dict[str, Any]:
    if path_value:
        return json.loads(Path(path_value).read_text(encoding="utf-8"))
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    return json.loads(raw)


def _default_dispatch_paths() -> DispatchPaths:
    tmp_dir = Path.cwd() / TMP_DIRNAME
    return DispatchPaths(
        source_md_path=tmp_dir / SOURCE_MD_FILENAME,
        source_meta_path=tmp_dir / SOURCE_META_FILENAME,
    )


def _detect_source_type(source_path: Path) -> tuple[str | None, str | None, str | None]:
    try:
        head = source_path.read_bytes()[:8]
    except Exception as exc:  # noqa: BLE001
        return None, None, f"read source failed: {exc}"

    if head.startswith(PDF_SIGNATURE):
        return "pdf", "pdf_signature", None

    try:
        source_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None, None, "input is neither PDF signature nor UTF-8 text"
    except Exception as exc:  # noqa: BLE001
        return None, None, f"read source as utf-8 failed: {exc}"

    return "markdown", "utf8_text", None


def _extension_warning(source_path: Path, source_type: str) -> list[str]:
    suffix = source_path.suffix.lower()
    if not suffix:
        return []
    if source_type == "pdf" and suffix != ".pdf":
        return [f"source_path extension '{suffix}' ignored; content detected as PDF"]
    if source_type == "markdown" and suffix not in (".md", ".markdown", ".txt"):
        return [f"source_path extension '{suffix}' ignored; content detected as UTF-8 text"]
    return []


def _quality_metrics(markdown_text: str) -> dict[str, int]:
    lines = markdown_text.splitlines()
    return {
        "char_count": len(markdown_text),
        "non_empty_lines": sum(1 for line in lines if line.strip()),
        "heading_lines": sum(1 for line in lines if re.search(r"^\s*#{1,6}\s+", line)),
        "references_keyword_hits": len(REFERENCES_RE.findall(markdown_text)),
    }


def _quality_markers(markdown_text: str) -> dict[str, Any]:
    lines = markdown_text.splitlines()
    non_empty_lines = [line for line in lines if line.strip()]
    heading_lines = sum(1 for line in lines if HEADING_RE.match(line.strip()))
    table_like_lines = sum(1 for line in lines if line.count("|") >= 2)
    noisy_lines = sum(1 for line in non_empty_lines if re.search(r"(?:\b[A-Za-z]\b\s+){4,}", line))
    total_non_empty = max(1, len(non_empty_lines))

    if heading_lines >= 4:
        heading_reliability = "high"
    elif heading_lines >= 2:
        heading_reliability = "medium"
    else:
        heading_reliability = "low"

    return {
        "heading_reliability": heading_reliability,
        "table_noise_presence": table_like_lines > 0,
        "ocr_noise_likely": noisy_lines / total_non_empty >= 0.2,
        "reference_numbering_reliability": "unknown",
    }


def _convert_markdown_source(source_path: Path) -> str:
    return source_path.read_text(encoding="utf-8")


def _convert_pdf_with_pymupdf4llm(source_path: Path) -> str:
    try:
        import pymupdf4llm  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"pymupdf4llm unavailable: {exc}") from exc

    try:
        markdown = pymupdf4llm.to_markdown(str(source_path))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"pymupdf4llm conversion failed: {exc}") from exc

    if isinstance(markdown, bytes):
        markdown = markdown.decode("utf-8", errors="replace")
    elif not isinstance(markdown, str):
        markdown = str(markdown)

    normalized = markdown.strip()
    if not normalized:
        raise RuntimeError("pymupdf4llm returned empty markdown")
    return normalized + "\n"


def _decode_pdf_literal(token: str) -> str:
    body = token[1:-1]
    chars: list[str] = []
    index = 0
    while index < len(body):
        char = body[index]
        if char != "\\":
            chars.append(char)
            index += 1
            continue
        if index + 1 >= len(body):
            break
        nxt = body[index + 1]
        if nxt in "()\\":
            chars.append(nxt)
            index += 2
            continue
        if nxt == "n":
            chars.append("\n")
            index += 2
            continue
        if nxt == "r":
            chars.append("\r")
            index += 2
            continue
        if nxt == "t":
            chars.append("\t")
            index += 2
            continue
        if nxt == "b":
            chars.append("\b")
            index += 2
            continue
        if nxt == "f":
            chars.append("\f")
            index += 2
            continue
        if nxt.isdigit():
            octal = nxt
            step = 2
            while index + step < len(body) and len(octal) < 3 and body[index + step].isdigit():
                octal += body[index + step]
                step += 1
            chars.append(chr(int(octal, 8)))
            index += step
            continue
        chars.append(nxt)
        index += 2
    return "".join(chars)


def _extract_text_from_pdf_stream(stream_bytes: bytes) -> str:
    stripped = stream_bytes.strip(b"\r\n")
    decoded_candidates: list[bytes] = [stripped]
    try:
        decoded_candidates.insert(0, zlib.decompress(stripped))
    except Exception:  # noqa: BLE001
        pass

    extracted_blocks: list[str] = []
    for candidate in decoded_candidates:
        try:
            text = candidate.decode("latin-1", errors="ignore")
        except Exception:  # noqa: BLE001
            continue

        text_blocks = TEXT_BLOCK_RE.findall(text) or [text]
        for block in text_blocks:
            fragments: list[str] = []
            for array_match in TJ_ARRAY_RE.finditer(block):
                fragments.extend(_decode_pdf_literal(item) for item in LITERAL_STRING_RE.findall(array_match.group(1)))
            for single_match in TJ_SINGLE_RE.finditer(block):
                fragments.append(_decode_pdf_literal(single_match.group(1)))
            if not fragments:
                fragments.extend(_decode_pdf_literal(item) for item in LITERAL_STRING_RE.findall(block))
            cleaned = " ".join(part.strip() for part in fragments if part.strip()).strip()
            if cleaned:
                extracted_blocks.append(cleaned)
        if extracted_blocks:
            break

    return "\n\n".join(extracted_blocks)


def _convert_pdf_with_stdlib(source_path: Path) -> str:
    pdf_bytes = source_path.read_bytes()
    stream_pattern = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
    text_parts: list[str] = []
    for match in stream_pattern.finditer(pdf_bytes):
        extracted = _extract_text_from_pdf_stream(match.group(1))
        if extracted:
            text_parts.append(extracted)

    if not text_parts:
        raise RuntimeError("stdlib fallback could not recover any text from PDF streams")

    deduped: list[str] = []
    seen: set[str] = set()
    for part in text_parts:
        normalized = part.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)

    markdown = "\n\n".join(deduped).strip()
    if not markdown:
        raise RuntimeError("stdlib fallback produced empty markdown")
    return markdown + "\n"


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
        headings.append((idx, len(match.group(1)), match.group(2).strip()))

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


def _coerce_scope_metadata(
    metadata: object,
    *,
    section_title: str,
    source: str = "agent",
    fallback_from: dict[str, Any] | None = None,
    fallback_reason: str = "",
) -> dict[str, Any]:
    meta = dict(metadata) if isinstance(metadata, dict) else {}
    covered_sections = meta.get("covered_sections")
    if isinstance(covered_sections, list):
        normalized_covered = [str(item) for item in covered_sections if str(item).strip()]
    elif isinstance(covered_sections, str) and covered_sections.strip():
        normalized_covered = [covered_sections.strip()]
    else:
        normalized_covered = [section_title]
    meta["scope_source"] = str(meta.get("scope_source", source or "agent"))
    meta["selection_reason"] = str(meta.get("selection_reason", ""))
    meta["covered_sections"] = normalized_covered
    meta["fallback_from"] = meta.get("fallback_from", fallback_from)
    meta["fallback_reason"] = str(meta.get("fallback_reason", fallback_reason))
    return meta


def _scope_from_obj(obj: object) -> Scope | None:
    if not isinstance(obj, dict):
        return None
    section_title = obj.get("section_title")
    line_start = obj.get("line_start")
    line_end = obj.get("line_end")
    if not isinstance(section_title, str) or not isinstance(line_start, int) or not isinstance(line_end, int):
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


def _db_scope_to_scope(scope_row: dict[str, Any]) -> Scope:
    return Scope(
        section_title=str(scope_row["section_title"]),
        line_start=int(scope_row["line_start"]),
        line_end=int(scope_row["line_end"]),
        source=str(dict(scope_row.get("metadata", {})).get("scope_source", "db")),
    )


def _resolve_db_citation_scope(
    *,
    scope_row: dict[str, Any] | None,
    lines: list[str],
) -> tuple[Scope | None, dict[str, Any], str | None]:
    if scope_row is None:
        return None, {}, "section_scopes.citation_scope missing; gate should have blocked this action"

    metadata = _coerce_scope_metadata(
        scope_row.get("metadata", {}),
        section_title=str(scope_row["section_title"]),
        source="db",
    )
    stored_scope = {
        "section_title": str(scope_row["section_title"]),
        "line_start": int(scope_row["line_start"]),
        "line_end": int(scope_row["line_end"]),
    }
    scope = _db_scope_to_scope(scope_row)
    validation_error = _validate_scope(scope, len(lines))
    if validation_error is None:
        return scope, metadata, None

    fallback = _find_intro_scope(lines)
    if fallback is None:
        return None, metadata, f"stored citation_scope invalid and introduction fallback failed: {validation_error}"

    fallback_metadata = _coerce_scope_metadata(
        metadata,
        section_title=fallback.section_title,
        source="db_fallback",
        fallback_from=stored_scope,
        fallback_reason=validation_error,
    )
    fallback.source = "db_fallback"
    return fallback, fallback_metadata, None


def _resolve_scope_from_args(args: argparse.Namespace, lines: list[str], payload_scope: object = None) -> tuple[Scope | None, str | None]:
    payload_candidate = _scope_from_obj(payload_scope)
    if payload_candidate is not None:
        return payload_candidate, _validate_scope(payload_candidate, len(lines))
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


def _validate_outline_nodes_payload(outline_nodes: object) -> tuple[list[dict[str, Any]] | None, str | None]:
    if not isinstance(outline_nodes, list):
        return None, "outline_nodes must be array"
    normalized_nodes: list[dict[str, Any]] = []
    seen_node_ids: set[str] = set()
    for index, node in enumerate(outline_nodes):
        if not isinstance(node, dict):
            return None, f"outline_nodes[{index}] must be object"
        missing = [key for key in OUTLINE_NODE_REQUIRED_KEYS if key not in node]
        if missing:
            return None, f"outline_nodes[{index}] missing required keys: {', '.join(missing)}"
        node_id = str(node["node_id"]).strip()
        if not node_id:
            return None, f"outline_nodes[{index}].node_id must be non-empty string"
        if node_id in seen_node_ids:
            return None, f"outline_nodes[{index}].node_id must be unique"
        seen_node_ids.add(node_id)
        title = str(node["title"]).strip()
        if not title:
            return None, f"outline_nodes[{index}].title must be non-empty string"
        try:
            heading_level = int(node["heading_level"])
            line_start = int(node["line_start"])
            line_end = int(node["line_end"])
        except (TypeError, ValueError):
            return None, f"outline_nodes[{index}] heading_level/line_start/line_end must be integers"
        if heading_level < 1:
            return None, f"outline_nodes[{index}].heading_level must be >= 1"
        if line_start < 1 or line_end < line_start:
            return None, f"outline_nodes[{index}] line range must satisfy 1 <= line_start <= line_end"
        metadata = node.get("metadata", {})
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            return None, f"outline_nodes[{index}].metadata must be object when provided"
        parent_node_id = node.get("parent_node_id")
        normalized_nodes.append(
            {
                "node_id": node_id,
                "heading_level": heading_level,
                "title": title,
                "line_start": line_start,
                "line_end": line_end,
                "parent_node_id": None if parent_node_id in (None, "") else str(parent_node_id),
                "metadata": dict(metadata),
            }
        )
    return normalized_nodes, None


def _validate_scope_payload(scope_obj: object, scope_name: str) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(scope_obj, dict):
        return None, f"{scope_name} must be object"
    missing = [key for key in SCOPE_REQUIRED_KEYS if key not in scope_obj]
    if missing:
        return None, f"{scope_name} missing required keys: {', '.join(missing)}"
    section_title = str(scope_obj["section_title"]).strip()
    if not section_title:
        return None, f"{scope_name}.section_title must be non-empty string"
    try:
        line_start = int(scope_obj["line_start"])
        line_end = int(scope_obj["line_end"])
    except (TypeError, ValueError):
        return None, f"{scope_name}.line_start and {scope_name}.line_end must be integers"
    if line_start < 1 or line_end < line_start:
        return None, f"{scope_name} line range must satisfy 1 <= line_start <= line_end"
    metadata = scope_obj.get("metadata")
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        return None, f"{scope_name}.metadata must be object"
    return {
        "section_title": section_title,
        "line_start": line_start,
        "line_end": line_end,
        "metadata": dict(metadata),
    }, None


def _sanitize_citation_line(line: str) -> str:
    sanitized = MARKDOWN_IMAGE_RE.sub(" ", line)
    sanitized = URL_RE.sub(" ", sanitized)
    sanitized = RESOURCE_PATH_RE.sub(" ", sanitized)
    return sanitized


def _count_false_positive_noise(line: str) -> int:
    count = 0
    count += len(MARKDOWN_IMAGE_RE.findall(line))
    count += len(URL_RE.findall(line))
    count += len(RESOURCE_PATH_RE.findall(line))
    count += len(DATE_LIKE_RE.findall(line))
    return count


def _is_false_positive_mention(mention: dict[str, Any]) -> bool:
    marker = str(mention.get("marker", "")).strip()
    snippet = str(mention.get("snippet", "")).strip()
    if not marker and not snippet:
        return True
    if DATE_LIKE_RE.search(marker) or DATE_LIKE_RE.search(snippet):
        return True
    if RESOURCE_SUFFIX_RE.search(marker) or RESOURCE_SUFFIX_RE.search(snippet):
        return True
    if URL_RE.search(marker) or URL_RE.search(snippet):
        return True
    if MARKDOWN_IMAGE_RE.search(snippet):
        return True
    if str(mention.get("style", "")).lower() == "author-year":
        surname_hint = str(mention.get("surname_hint", "")).strip()
        if not surname_hint:
            return True
    return False


def _extract_terminal_publication_year(raw: str) -> int | None:
    matches = [int(match.group(1)) for match in TERMINAL_PUBLICATION_YEAR_RE.finditer(raw)]
    if not matches:
        return None
    return matches[-1]


def _strip_reference_number_prefix(raw: str) -> tuple[str, int | None]:
    text = raw.strip()
    detected_ref_number = _extract_detected_reference_number(text)
    if detected_ref_number is not None:
        text = REFERENCE_ENTRY_START_RE.sub("", text, count=1).strip()
    return text, detected_ref_number


def _normalize_reference_entry_text(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.strip())


def _split_reference_entries(lines: list[str], scope: Scope) -> list[dict[str, Any]]:
    start_index = max(scope.line_start - 1, 0)
    end_index = min(scope.line_end, len(lines))
    scoped_lines = lines[start_index:end_index]
    if scoped_lines:
        first_stripped = scoped_lines[0].strip()
        first_title = re.sub(r"^#{1,6}\s+", "", first_stripped).strip()
        if first_title.lower() == scope.section_title.strip().lower():
            scoped_lines = scoped_lines[1:]
            start_index += 1
    chunks: list[dict[str, Any]] = []
    current_lines: list[str] = []
    current_start: int | None = None

    def flush(entry_end_line: int) -> None:
        nonlocal current_lines, current_start
        if not current_lines or current_start is None:
            current_lines = []
            current_start = None
            return
        raw = _normalize_reference_entry_text(" ".join(current_lines))
        if raw:
            chunks.append(
                {
                    "raw": raw,
                    "line_start": current_start,
                    "line_end": entry_end_line,
                }
            )
        current_lines = []
        current_start = None

    for offset, line in enumerate(scoped_lines, start=scope.line_start):
        stripped = line.strip()
        if not stripped:
            flush(offset - 1)
            continue
        is_new_entry = REFERENCE_ENTRY_START_RE.match(stripped) is not None
        if is_new_entry and current_lines:
            flush(offset - 1)
        if current_start is None:
            current_start = offset
        current_lines.append(stripped)
    flush(scope.line_end)

    if not chunks:
        for offset, line in enumerate(scoped_lines, start=scope.line_start):
            stripped = line.strip()
            if stripped:
                chunks.append({"raw": _normalize_reference_entry_text(stripped), "line_start": offset, "line_end": offset})

    entries: list[dict[str, Any]] = []
    for entry_index, chunk in enumerate(chunks):
        raw = str(chunk["raw"])
        normalized_text, detected_ref_number = _strip_reference_number_prefix(raw)
        entries.append(
            {
                "entry_index": entry_index,
                "raw": raw,
                "year": _extract_terminal_publication_year(raw),
                "metadata": {
                    "line_start": int(chunk["line_start"]),
                    "line_end": int(chunk["line_end"]),
                    "normalized_entry_text": normalized_text,
                    "detected_ref_number": detected_ref_number,
                },
            }
        )
    return entries


def _split_author_candidates(author_text: str) -> list[str]:
    text = author_text.strip().strip(" ,;:")
    if not text:
        return []
    comma_style = [match.group(0).strip().rstrip(" ,;:") for match in COMMA_STYLE_AUTHOR_RE.finditer(text)]
    if comma_style:
        return comma_style
    if ";" in text:
        return [part.strip().rstrip(" ,;:") for part in text.split(";") if part.strip()]
    if " and " in text.lower():
        return [part.strip().rstrip(" ,;:") for part in re.split(r"\band\b|&", text, flags=re.IGNORECASE) if part.strip()]
    return [text]


def _normalize_author_boundary_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _candidate_author_boundaries_are_stable(candidate_authors: list[str]) -> bool:
    normalized = [_normalize_author_boundary_text(author) for author in candidate_authors if _normalize_author_boundary_text(author)]
    if not normalized:
        return False
    return len(normalized) > 1 or any("," in author for author in candidate_authors)


def _detect_reference_author_oversplit(submitted_authors: list[str], candidate_authors: list[str]) -> str | None:
    if not _candidate_author_boundaries_are_stable(candidate_authors):
        return None

    submitted_norm = [_normalize_author_boundary_text(author) for author in submitted_authors if _normalize_author_boundary_text(author)]
    candidate_norm = [_normalize_author_boundary_text(author) for author in candidate_authors if _normalize_author_boundary_text(author)]
    if not submitted_norm or not candidate_norm or submitted_norm == candidate_norm:
        return None

    submitted_index = 0
    segment_counts: list[int] = []
    for candidate in candidate_norm:
        combined = ""
        start = submitted_index
        while submitted_index < len(submitted_norm) and len(combined) < len(candidate):
            combined += submitted_norm[submitted_index]
            submitted_index += 1
            if combined == candidate:
                break
        if combined != candidate:
            return None
        segment_counts.append(submitted_index - start)

    if submitted_index != len(submitted_norm):
        return None
    if not any(count > 1 for count in segment_counts):
        return None
    return (
        "author[] must preserve prepared candidate boundaries; reuse pattern_candidate.author_candidates "
        "and only lightly normalize formatting instead of splitting surnames and initials into separate elements"
    )


def _make_reference_candidate(
    *,
    entry_index: int,
    pattern: str,
    author_text: str,
    title_candidate: str,
    container_candidate: str,
    year_candidate: int | None,
    confidence: float,
    split_basis: str,
) -> dict[str, Any]:
    return {
        "entry_index": entry_index,
        "pattern": pattern,
        "author_text": author_text.strip().strip(" ,;:"),
        "author_candidates": _split_author_candidates(author_text),
        "title_candidate": title_candidate.strip().strip(" ."),
        "container_candidate": container_candidate.strip().strip(" ."),
        "year_candidate": year_candidate,
        "confidence": confidence,
        "metadata": {
            "split_basis": split_basis,
        },
    }


def _candidate_authors_colon_title_in_year(entry_index: int, text: str, terminal_year: int | None) -> dict[str, Any] | None:
    match = re.match(
        r"^(?P<authors>.+?):\s*(?P<title>.+?)(?:\.\s*In:\s*(?P<container>.+?))?\s*\((?P<year>(?:19|20)\d{2})\)\s*\.?$",
        text,
    )
    if match is None:
        return None
    return _make_reference_candidate(
        entry_index=entry_index,
        pattern="authors_colon_title_in_year",
        author_text=match.group("authors"),
        title_candidate=match.group("title"),
        container_candidate=match.group("container") or "",
        year_candidate=int(match.group("year")),
        confidence=0.92 if terminal_year == int(match.group("year")) else 0.84,
        split_basis="authors block before ':' and title before optional In:/year tail",
    )


def _candidate_authors_period_title_period_venue_year(entry_index: int, text: str, terminal_year: int | None) -> dict[str, Any] | None:
    match = re.match(
        r"^(?P<authors>.+?)\.\s+(?P<title>.+?)\.(?:\s+(?P<container>.+?))?(?:\s*\(?((?P<year>(?:19|20)\d{2}))\)?)?\.?$",
        text,
    )
    if match is None:
        return None
    year = int(match.group("year")) if match.group("year") else terminal_year
    return _make_reference_candidate(
        entry_index=entry_index,
        pattern="authors_period_title_period_venue_year",
        author_text=match.group("authors"),
        title_candidate=match.group("title"),
        container_candidate=match.group("container") or "",
        year_candidate=year,
        confidence=0.75 if year is not None else 0.62,
        split_basis="first sentence as authors, second sentence as title, trailing sentence/year as container",
    )


def _candidate_authors_year_paren_title_venue(entry_index: int, text: str, terminal_year: int | None) -> dict[str, Any] | None:
    match = re.match(
        r"^(?P<authors>.+?)\s*\((?P<year>(?:19|20)\d{2})\)\.?\s+(?P<title>.+?)(?:\.\s+(?P<container>.+))?$",
        text,
    )
    if match is None:
        return None
    return _make_reference_candidate(
        entry_index=entry_index,
        pattern="authors_year_paren_title_venue",
        author_text=match.group("authors"),
        title_candidate=match.group("title"),
        container_candidate=match.group("container") or "",
        year_candidate=int(match.group("year")) if match.group("year") else terminal_year,
        confidence=0.8,
        split_basis="authors before year parentheses, title after year marker",
    )


def _candidate_thesis_or_book_tail_year(entry_index: int, text: str, terminal_year: int | None) -> dict[str, Any] | None:
    if terminal_year is None:
        return None
    head = re.sub(rf"[\s,.;:()]*{terminal_year}[\s,.;:()]*$", "", text).strip()
    if not head:
        return None
    if ":" in head:
        author_text, title_candidate = head.split(":", 1)
    elif ". " in head:
        author_text, title_candidate = head.split(". ", 1)
    else:
        return None
    return _make_reference_candidate(
        entry_index=entry_index,
        pattern="thesis_or_book_tail_year",
        author_text=author_text,
        title_candidate=title_candidate,
        container_candidate="",
        year_candidate=terminal_year,
        confidence=0.58,
        split_basis="tail year stripped first, remaining text split on ':' or first period",
    )


def _candidate_fallback_raw_split(entry_index: int, text: str, terminal_year: int | None) -> dict[str, Any]:
    if ":" in text:
        author_text, title_candidate = text.split(":", 1)
    elif ". " in text:
        author_text, title_candidate = text.split(". ", 1)
    else:
        author_text, title_candidate = text, ""
    return _make_reference_candidate(
        entry_index=entry_index,
        pattern="fallback_raw_split",
        author_text=author_text,
        title_candidate=title_candidate,
        container_candidate="",
        year_candidate=terminal_year,
        confidence=0.35,
        split_basis="fallback split using ':' or first sentence boundary",
    )


def _generate_reference_candidates(entry: dict[str, Any]) -> list[dict[str, Any]]:
    raw = str(entry.get("raw", ""))
    text, _ = _strip_reference_number_prefix(raw)
    text = _normalize_reference_entry_text(text)
    entry_index = int(entry["entry_index"])
    terminal_year = _extract_terminal_publication_year(raw)
    candidate_builders = [
        _candidate_authors_period_title_period_venue_year,
        _candidate_authors_colon_title_in_year,
        _candidate_authors_year_paren_title_venue,
        _candidate_thesis_or_book_tail_year,
    ]
    seen: set[tuple[str, str, str, int | None]] = set()
    candidates: list[dict[str, Any]] = []
    for candidate_index, builder in enumerate(candidate_builders, start=0):
        candidate = builder(entry_index, text, terminal_year)
        if candidate is None:
            continue
        key = (
            str(candidate["pattern"]),
            str(candidate["author_text"]),
            str(candidate["title_candidate"]),
            candidate.get("year_candidate"),
        )
        if key in seen:
            continue
        seen.add(key)
        candidate["candidate_index"] = len(candidates)
        candidates.append(candidate)
    fallback = _candidate_fallback_raw_split(entry_index, text, terminal_year)
    fallback_key = (
        str(fallback["pattern"]),
        str(fallback["author_text"]),
        str(fallback["title_candidate"]),
        fallback.get("year_candidate"),
    )
    if fallback_key not in seen:
        fallback["candidate_index"] = len(candidates)
        candidates.append(fallback)
    return candidates


def _build_reference_workset_export(
    *,
    entries: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    batches: list[dict[str, Any]],
) -> dict[str, Any]:
    candidates_by_entry: dict[int, list[dict[str, Any]]] = {}
    for candidate in candidates:
        candidates_by_entry.setdefault(int(candidate["entry_index"]), []).append(candidate)
    export_entries: list[dict[str, Any]] = []
    for entry in entries:
        metadata = dict(entry.get("metadata", {}))
        numbering = dict(metadata.get("numbering", {}))
        export_entries.append(
            {
                "entry_index": int(entry["entry_index"]),
                "raw": str(entry["raw"]),
                "detected_ref_number": numbering.get("detected_ref_number"),
                "numbering": numbering,
                "patterns": candidates_by_entry.get(int(entry["entry_index"]), []),
            }
        )
    return {
        "meta": {
            "generated_at": utc_now_iso(),
            "entry_count": len(export_entries),
            "candidate_count": len(candidates),
            "batch_count": len(batches),
        },
        "entries": export_entries,
        "batches": batches,
    }


def _build_reference_review_view(workset_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "meta": dict(workset_payload.get("meta", {})),
        "entries": [
            {
                "entry_index": entry.get("entry_index"),
                "detected_ref_number": entry.get("detected_ref_number"),
                "raw": entry.get("raw", ""),
                "pattern_summaries": [
                    {
                        "candidate_index": pattern.get("candidate_index"),
                        "pattern": pattern.get("pattern"),
                        "author_text": pattern.get("author_text", ""),
                        "title_candidate": pattern.get("title_candidate", ""),
                        "year_candidate": pattern.get("year_candidate"),
                        "confidence": pattern.get("confidence"),
                    }
                    for pattern in entry.get("patterns", [])
                ],
            }
            for entry in workset_payload.get("entries", [])
        ],
    }


def _build_citation_review_view(workset_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "meta": {
            "generated_at": workset_payload.get("meta", {}).get("generated_at", ""),
            "scope": workset_payload.get("meta", {}).get("scope"),
            "scope_source": workset_payload.get("meta", {}).get("scope_source", ""),
            "total_items": len(workset_payload.get("workset_items", [])),
        },
        "items": [
            {
                "ref_index": item.get("ref_index"),
                "title": dict(item.get("reference", {})).get("title", ""),
                "mention_count": item.get("mention_count", len(item.get("mentions", []))),
                "snippets": [str(mention.get("snippet", "")).strip() for mention in item.get("mentions", []) if str(mention.get("snippet", "")).strip()],
            }
            for item in workset_payload.get("workset_items", [])
        ],
    }


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
            mentions.append(
                {
                    "mention_id": f"m{current:05d}",
                    "marker": f"[{ref_number}]",
                    "style": "numeric",
                    "line_start": line_no,
                    "line_end": line_no,
                    "snippet": line.strip(),
                    "ref_number_hint": ref_number,
                }
            )
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
        for segment in [seg.strip() for seg in parenthetical.group(1).split(";") if seg.strip()]:
            year_match = YEAR_RE.search(segment)
            if year_match is None:
                continue
            year = int(year_match.group(1))
            marker = f"({segment})"
            key = (marker, year)
            if key in seen:
                continue
            seen.add(key)
            mentions.append(
                {
                    "mention_id": f"m{current:05d}",
                    "marker": marker,
                    "style": "author-year",
                    "line_start": line_no,
                    "line_end": line_no,
                    "snippet": line.strip(),
                    "year_hint": year,
                    "surname_hint": _extract_surname(segment),
                }
            )
            current += 1

    for narrative in AUTHOR_YEAR_NARRATIVE_RE.finditer(line):
        surname_candidate = narrative.group(1).strip()
        year_text = narrative.group(2)
        year = int(year_text[:4])
        marker = f"{surname_candidate} ({year_text})"
        key = (marker, year)
        if key in seen:
            continue
        seen.add(key)
        mentions.append(
            {
                "mention_id": f"m{current:05d}",
                "marker": marker,
                "style": "author-year",
                "line_start": line_no,
                "line_end": line_no,
                "snippet": line.strip(),
                "year_hint": year,
                "surname_hint": _extract_surname(surname_candidate),
            }
        )
        current += 1
    return mentions, current


def _extract_mentions(lines: list[str], scope: Scope) -> tuple[list[dict[str, Any]], int]:
    mentions: list[dict[str, Any]] = []
    filtered_count = 0
    counter = 1
    for line_no in range(scope.line_start, scope.line_end + 1):
        original_line = lines[line_no - 1]
        filtered_count += _count_false_positive_noise(original_line)
        line = _sanitize_citation_line(original_line)
        numeric_mentions, counter = _extract_numeric_mentions(line, line_no, counter)
        author_year_mentions, counter = _extract_author_year_mentions(line, line_no, counter)
        for mention in [*numeric_mentions, *author_year_mentions]:
            mention["snippet"] = original_line.strip()
            if _is_false_positive_mention(mention):
                filtered_count += 1
                continue
            mentions.append(mention)
    return mentions, filtered_count


def _build_citation_workset(
    *,
    scope: Scope,
    mentions: list[dict[str, Any]],
    reference_items: list[dict[str, Any]],
) -> dict[str, Any]:
    reference_index: list[dict[str, Any]] = []
    by_ref_number: dict[int, dict[str, Any]] = {}
    by_author_year: list[dict[str, Any]] = []
    for item in reference_items:
        ref_number = item.get("detected_ref_number")
        if ref_number is None:
            numbering = dict(item.get("numbering", {}))
            ref_number = numbering.get("detected_ref_number")
        if ref_number is None:
            ref_number = _extract_detected_reference_number(str(item.get("raw", "")))
        entry = {
            "ref_index": item.get("entry_index", item.get("ref_index")),
            "ref_number": ref_number,
            "title": item.get("title", ""),
            "author": item.get("author", []),
            "year": item.get("year"),
        }
        reference_index.append(entry)
        if isinstance(ref_number, int):
            by_ref_number[ref_number] = entry
        authors = entry.get("author", [])
        if isinstance(authors, list) and authors and entry.get("year") is not None:
            surname = re.split(r"[, ]", str(authors[0]).strip())[0]
            by_author_year.append({**entry, "surname_hint": surname.lower()})

    grouped: dict[int, dict[str, Any]] = {}
    mention_links: list[dict[str, Any]] = []
    unresolved_mentions: list[dict[str, Any]] = []
    for mention in mentions:
        candidate_reference: dict[str, Any] | None = None
        resolution_method = "unresolved"
        resolution_confidence = 0.0
        if mention.get("ref_number_hint") in by_ref_number:
            candidate_reference = by_ref_number[int(mention["ref_number_hint"])]
            resolution_method = "ref_number_hint"
            resolution_confidence = 1.0
        elif mention.get("surname_hint") and mention.get("year_hint") is not None:
            surname = str(mention["surname_hint"]).lower()
            year = int(mention["year_hint"])
            for candidate in by_author_year:
                if candidate.get("surname_hint") == surname and candidate.get("year") == year:
                    candidate_reference = candidate
                    resolution_method = "author_year_hint"
                    resolution_confidence = 0.85
                    break
        if candidate_reference is None:
            mention_links.append(
                {
                    "mention_id": str(mention["mention_id"]),
                    "ref_index": None,
                    "status": "unmapped",
                    "resolution_method": resolution_method,
                    "resolution_confidence": resolution_confidence,
                    "evidence": {
                        "marker": mention.get("marker"),
                        "ref_number_hint": mention.get("ref_number_hint"),
                        "year_hint": mention.get("year_hint"),
                        "surname_hint": mention.get("surname_hint"),
                    },
                }
            )
            unresolved_mentions.append(mention)
            continue
        ref_index = int(candidate_reference["ref_index"])
        mention_links.append(
            {
                "mention_id": str(mention["mention_id"]),
                "ref_index": ref_index,
                "status": "mapped",
                "resolution_method": resolution_method,
                "resolution_confidence": resolution_confidence,
                "evidence": {
                    "marker": mention.get("marker"),
                    "ref_number_hint": mention.get("ref_number_hint"),
                    "year_hint": mention.get("year_hint"),
                    "surname_hint": mention.get("surname_hint"),
                },
            }
        )
        if ref_index not in grouped:
            grouped[ref_index] = {
                "ref_index": ref_index,
                "ref_number": candidate_reference.get("ref_number"),
                "reference": {
                    "author": candidate_reference.get("author", []),
                    "title": candidate_reference.get("title", ""),
                    "year": candidate_reference.get("year"),
                },
                "mentions": [],
                "metadata": {
                    "resolution_methods": [],
                    "resolution_confidence_max": resolution_confidence,
                },
            }
        grouped[ref_index]["mentions"].append(mention)
        grouped[ref_index]["metadata"]["resolution_methods"].append(resolution_method)
        grouped[ref_index]["metadata"]["resolution_confidence_max"] = max(
            float(grouped[ref_index]["metadata"]["resolution_confidence_max"]),
            resolution_confidence,
        )

    suggested_items = [grouped[key] for key in sorted(grouped)]
    suggested_batches: list[dict[str, Any]] = []
    batch_index = 0
    item_start = 0
    while item_start < len(suggested_items):
        item_end = item_start
        mention_total = 0
        while item_end < len(suggested_items):
            next_mentions = len(suggested_items[item_end]["mentions"])
            item_count = item_end - item_start + 1
            if item_count > 12 or (mention_total + next_mentions) > 30:
                break
            mention_total += next_mentions
            item_end += 1
        if item_end == item_start:
            mention_total = len(suggested_items[item_start]["mentions"])
            item_end += 1
        batch = {
            "batch_index": batch_index,
            "item_start": item_start,
            "item_end": item_end - 1,
            "mention_start": 0 if not suggested_items[item_start]["mentions"] else int(suggested_items[item_start]["mentions"][0]["line_start"]),
            "mention_end": 0 if not suggested_items[item_end - 1]["mentions"] else int(suggested_items[item_end - 1]["mentions"][-1]["line_end"]),
            "item_count": item_end - item_start,
            "mention_count": mention_total,
        }
        suggested_batches.append(batch)
        for grouped_item in suggested_items[item_start:item_end]:
            grouped_item["batch_hint"] = batch_index
            grouped_item["mention_count"] = len(grouped_item["mentions"])
        batch_index += 1
        item_start = item_end

    return {
        "meta": {
            "scope": {
                "section_title": scope.section_title,
                "line_start": scope.line_start,
                "line_end": scope.line_end,
            },
            "generated_at": utc_now_iso(),
            "total_mentions": len(mentions),
        },
        "mentions": mentions,
        "mention_links": mention_links,
        "reference_index": reference_index,
        "workset_items": suggested_items,
        "unresolved_mentions": unresolved_mentions,
        "suggested_batches": suggested_batches,
    }


def _schema(schema_name: str) -> dict[str, Any]:
    return json.loads((RENDER_SCHEMAS_DIR / schema_name).read_text(encoding="utf-8"))


def _template_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=False,
        trim_blocks=False,
        lstrip_blocks=False,
        keep_trailing_newline=False,
        undefined=StrictUndefined,
    )
    env.filters["to_pretty_json"] = lambda value: json.dumps(value, ensure_ascii=False, indent=2)
    return env


def _render_template(template_name: str, context: dict[str, Any]) -> str:
    return _template_env().get_template(template_name).render(**context)


def _validate_context(context: dict[str, Any], schema_name: str) -> None:
    validate(instance=context, schema=_schema(schema_name))


def _render_json(template_name: str, context: dict[str, Any], schema_name: str) -> str:
    _validate_context(context, schema_name)
    rendered = _render_template(template_name, context)
    json.loads(rendered)
    return rendered + ("" if rendered.endswith("\n") else "\n")


def _render_markdown(template_name: str, context: dict[str, Any], schema_name: str, *, ensure_trailing_newline: bool) -> str:
    _validate_context(context, schema_name)
    rendered = _render_template(template_name, context)
    if ensure_trailing_newline:
        rendered = rendered.rstrip("\n")
        if rendered:
            rendered += "\n"
    return rendered


def _digest_template_name(language: str) -> str:
    if language.lower().startswith("en"):
        return "digest.en-US.md.j2"
    return "digest.zh-CN.md.j2"


def _resolve_output_root(explicit_out_dir: Path | None, source_path: Path | None) -> Path:
    if source_path is not None:
        return source_path.parent
    if explicit_out_dir is not None:
        return explicit_out_dir
    env = os.environ.get("LITERATURE_DIGEST_OUTPUT_DIR")
    if env:
        return Path(env).expanduser()
    return Path.cwd()


def _as_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    if isinstance(value, str):
        return [value]
    return [str(value)]


def _as_int_or_none(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer():
            return int(value)
        return None
    if isinstance(value, str):
        s = value.strip()
        if re.fullmatch(r"(19|20)\d{2}", s):
            return int(s)
    return None


def _as_confidence(value: object, default: float = 0.1) -> float:
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        f = float(value)
        if math.isfinite(f):
            return float(min(1.0, max(0.0, f)))
        return default
    if isinstance(value, str):
        try:
            f = float(value.strip())
        except ValueError:
            return default
        if math.isfinite(f):
            return float(min(1.0, max(0.0, f)))
    return default


def _require_string_list(value: object, field_name: str) -> tuple[list[str] | None, str | None]:
    if not isinstance(value, list):
        return None, f"{field_name} must be an array of strings"
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None, f"{field_name} must be an array of strings"
        out.append(item)
    return out, None


def _normalize_keyword_list(value: object, field_name: str) -> tuple[list[str] | None, str | None]:
    keywords, error = _require_string_list(value, field_name)
    if error is not None or keywords is None:
        return None, error
    normalized: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        stripped = keyword.strip()
        if not stripped:
            continue
        dedupe_key = stripped.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(stripped)
    if not normalized:
        return None, f"{field_name} must contain at least one non-empty keyword"
    return normalized, None


def _validate_digest_payload(payload: dict[str, Any]) -> tuple[dict[str, dict[str, Any]] | None, list[dict[str, Any]] | None, str | None]:
    if "sections" in payload:
        return None, None, "deprecated payload key 'sections' is not supported; use digest_slots + section_summaries"

    digest_slots_obj = payload.get("digest_slots")
    section_summaries_obj = payload.get("section_summaries")
    if not isinstance(digest_slots_obj, dict):
        return None, None, "digest_slots must be object"
    if not isinstance(section_summaries_obj, list):
        return None, None, "section_summaries must be array"

    normalized_slots: dict[str, dict[str, Any]] = {}

    tldr = digest_slots_obj.get("tldr")
    if not isinstance(tldr, dict):
        return None, None, "digest_slots.tldr must be object"
    paragraphs, error = _require_string_list(tldr.get("paragraphs"), "digest_slots.tldr.paragraphs")
    if error is not None:
        return None, None, error
    normalized_slots["tldr"] = {"paragraphs": paragraphs}

    research = digest_slots_obj.get("research_question_and_contributions")
    if not isinstance(research, dict):
        return None, None, "digest_slots.research_question_and_contributions must be object"
    research_question = research.get("research_question")
    if not isinstance(research_question, str):
        return None, None, "digest_slots.research_question_and_contributions.research_question must be string"
    contributions, error = _require_string_list(
        research.get("contributions"),
        "digest_slots.research_question_and_contributions.contributions",
    )
    if error is not None:
        return None, None, error
    normalized_slots["research_question_and_contributions"] = {
        "research_question": research_question,
        "contributions": contributions,
    }

    for slot_key in ("method_highlights", "key_results", "limitations_and_reproducibility"):
        slot_value = digest_slots_obj.get(slot_key)
        if not isinstance(slot_value, dict):
            return None, None, f"digest_slots.{slot_key} must be object"
        items, error = _require_string_list(slot_value.get("items"), f"digest_slots.{slot_key}.items")
        if error is not None:
            return None, None, error
        normalized_slots[slot_key] = {"items": items}

    normalized_summaries: list[dict[str, Any]] = []
    for index, summary in enumerate(section_summaries_obj, start=1):
        if not isinstance(summary, dict):
            return None, None, "section_summaries items must be objects"
        source_heading = summary.get("source_heading")
        if not isinstance(source_heading, str):
            return None, None, "section_summaries.source_heading must be string"
        items, error = _require_string_list(summary.get("items"), "section_summaries.items")
        if error is not None:
            return None, None, error
        normalized_summaries.append(
            {
                "position": int(summary.get("position", index)),
                "source_heading": source_heading,
                "items": items,
            }
        )

    return normalized_slots, normalized_summaries, None


def _validate_digest_coverage(connection, digest_slots: dict[str, dict[str, Any]], section_summaries: list[dict[str, Any]]) -> tuple[list[str], str | None]:  # type: ignore[no-untyped-def]
    for slot_key, slot_value in digest_slots.items():
        if slot_key == "tldr":
            if not slot_value.get("paragraphs"):
                return [], f"digest slot '{slot_key}' must be non-empty"
        elif slot_key == "research_question_and_contributions":
            if not str(slot_value.get("research_question", "")).strip():
                return [], "digest slot 'research_question_and_contributions.research_question' must be non-empty"
            if not slot_value.get("contributions"):
                return [], "digest slot 'research_question_and_contributions.contributions' must be non-empty"
        else:
            if not slot_value.get("items"):
                return [], f"digest slot '{slot_key}.items' must be non-empty"

    outline_rows = connection.execute(
        "SELECT title, heading_level FROM outline_nodes ORDER BY position ASC"
    ).fetchall()
    major_headings = [
        str(row["title"])
        for row in outline_rows
        if int(row["heading_level"]) == 1 and not REFERENCES_RE.search(str(row["title"]))
    ]
    if not major_headings:
        return [], None

    covered = {
        str(summary.get("source_heading", "")).strip()
        for summary in section_summaries
        if str(summary.get("source_heading", "")).strip()
    }
    minimum_required = min(3, len(major_headings))
    if len(covered) < minimum_required:
        return [], f"section_summaries must cover at least {minimum_required} major headings"

    warnings: list[str] = []
    if len(covered) < len(major_headings):
        warnings.append(WARNING_DIGEST_UNDERCOVERAGE)
    return warnings, None


def _normalize_function_value(function_value: object) -> tuple[str, str | None]:
    normalized = str(function_value or "").strip().lower()
    if normalized in ALLOWED_CITATION_FUNCTIONS:
        return normalized, None
    if not normalized:
        return "uncategorized", "citation function missing; normalized to uncategorized"
    return "uncategorized", f"citation function '{function_value}' normalized to uncategorized"


def _validate_citation_semantics_payload(
    payload: dict[str, Any],
    workset_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]] | None, str | None]:
    if "report_md" in payload:
        return None, "deprecated payload key 'report_md' is not supported; report_md is renderer-derived"
    if "batches" in payload or "unmapped_mentions" in payload:
        return None, "persist_citation_semantics now accepts only items[] keyed by ref_index"

    items = payload.get("items", [])
    if not isinstance(items, list):
        return None, "items must be array"

    expected_ref_indexes = {int(item["ref_index"]) for item in workset_items}
    normalized_items: list[dict[str, Any]] = []
    seen_ref_indexes: set[int] = set()
    for item in items:
        if not isinstance(item, dict):
            return None, "items entries must be objects"
        if "reference" in item or "mentions" in item or "ref_number" in item:
            return None, "persist_citation_semantics items must not include reference/mentions/ref_number; those come from DB workset"
        ref_index = item.get("ref_index")
        if not isinstance(ref_index, int):
            return None, "items.ref_index must be integer"
        topic = item.get("topic")
        if not isinstance(topic, str) or not topic.strip():
            return None, "items.topic must be non-empty string"
        usage = item.get("usage")
        if not isinstance(usage, str) or not usage.strip():
            return None, "items.usage must be non-empty string"
        summary = item.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            return None, "items.summary must be non-empty string"
        keywords, keyword_error = _normalize_keyword_list(item.get("keywords"), "items.keywords")
        if keyword_error is not None or keywords is None:
            return None, keyword_error or "items.keywords invalid"
        is_key_reference = item.get("is_key_reference")
        if not isinstance(is_key_reference, bool):
            return None, "items.is_key_reference must be boolean"
        if ref_index in seen_ref_indexes:
            return None, "duplicate ref_index in citation semantics payload"
        seen_ref_indexes.add(ref_index)
        normalized_item = dict(item)
        normalized_item["topic"] = topic.strip()
        normalized_item["usage"] = usage.strip()
        normalized_item["summary"] = summary.strip()
        normalized_item["keywords"] = keywords
        normalized_items.append(normalized_item)

    if seen_ref_indexes != expected_ref_indexes:
        missing = sorted(expected_ref_indexes - seen_ref_indexes)
        extra = sorted(seen_ref_indexes - expected_ref_indexes)
        details: list[str] = []
        if missing:
            details.append(f"missing ref_index values: {missing}")
        if extra:
            details.append(f"unknown ref_index values: {extra}")
        return None, "; ".join(details) if details else "citation semantics payload does not match workset items"
    return normalized_items, None


def _validate_citation_summary_basis(
    basis: object,
    workset_items: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(basis, dict):
        return None, "basis must be object"

    research_threads_raw = basis.get("research_threads")
    if not isinstance(research_threads_raw, list):
        return None, "basis.research_threads must be array"
    research_threads = [str(item).strip() for item in research_threads_raw if str(item).strip()]
    if len(research_threads) < 2:
        return None, "basis.research_threads must contain at least 2 non-empty strings"

    argument_shape_raw = basis.get("argument_shape")
    if not isinstance(argument_shape_raw, list):
        return None, "basis.argument_shape must be array"
    argument_shape = [str(item).strip() for item in argument_shape_raw if str(item).strip()]
    if len(argument_shape) < 2:
        return None, "basis.argument_shape must contain at least 2 non-empty strings"

    key_ref_indexes_raw = basis.get("key_ref_indexes")
    if not isinstance(key_ref_indexes_raw, list) or not key_ref_indexes_raw:
        return None, "basis.key_ref_indexes must be non-empty integer array"
    key_ref_indexes: list[int] = []
    for item in key_ref_indexes_raw:
        if not isinstance(item, int):
            return None, "basis.key_ref_indexes must be non-empty integer array"
        key_ref_indexes.append(item)

    expected_ref_indexes = {int(item["ref_index"]) for item in workset_items}
    unknown = sorted(index for index in key_ref_indexes if index not in expected_ref_indexes)
    if unknown:
        return None, f"basis.key_ref_indexes contains unknown ref_index values: {unknown}"

    normalized_basis = dict(basis)
    normalized_basis["research_threads"] = research_threads
    normalized_basis["argument_shape"] = argument_shape
    normalized_basis["key_ref_indexes"] = key_ref_indexes
    return normalized_basis, None


def _validate_citation_timeline_payload(
    payload: dict[str, Any],
    workset_items: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[str], str | None]:
    timeline = payload.get("timeline")
    if not isinstance(timeline, dict):
        return None, [], "timeline must be object"

    known_ref_indexes = {int(item["ref_index"]) for item in workset_items}
    dated_ref_indexes: set[int] = set()
    undated_ref_indexes: set[int] = set()
    for item in workset_items:
        reference = dict(item.get("reference", {}))
        ref_index = int(item["ref_index"])
        if isinstance(reference.get("year"), int):
            dated_ref_indexes.add(ref_index)
        else:
            undated_ref_indexes.add(ref_index)

    normalized_timeline: dict[str, Any] = {}
    seen_ref_indexes: dict[int, str] = {}
    bucketed_ref_indexes: set[int] = set()

    for bucket_name in ("early", "mid", "recent"):
        bucket = timeline.get(bucket_name)
        if not isinstance(bucket, dict):
            return None, [], f"timeline.{bucket_name} must be object"
        summary = bucket.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            return None, [], f"timeline.{bucket_name}.summary must be non-empty string"
        ref_indexes = bucket.get("ref_indexes")
        if not isinstance(ref_indexes, list):
            return None, [], f"timeline.{bucket_name}.ref_indexes must be array"
        normalized_ref_indexes: list[int] = []
        for ref_index in ref_indexes:
            if not isinstance(ref_index, int):
                return None, [], f"timeline.{bucket_name}.ref_indexes must contain integers"
            if ref_index not in known_ref_indexes:
                return None, [], f"timeline.{bucket_name}.ref_indexes contains unknown ref_index {ref_index}"
            if ref_index in seen_ref_indexes:
                return None, [], f"ref_index {ref_index} appears in multiple timeline buckets: {seen_ref_indexes[ref_index]} and {bucket_name}"
            seen_ref_indexes[ref_index] = bucket_name
            normalized_ref_indexes.append(ref_index)
            bucketed_ref_indexes.add(ref_index)
        normalized_timeline[bucket_name] = {
            "summary": summary.strip(),
            "ref_indexes": normalized_ref_indexes,
        }

    missing_dated = sorted(dated_ref_indexes - bucketed_ref_indexes)
    if missing_dated:
        return None, [], f"timeline must include every dated citation item exactly once; missing ref_index values: {missing_dated}"

    warnings: list[str] = []
    missing_year_refs = sorted(undated_ref_indexes - bucketed_ref_indexes)
    if missing_year_refs:
        warnings.append(f"{WARNING_CITATION_TIMELINE_MISSING_YEAR}: ref_indexes={missing_year_refs}")
    return normalized_timeline, warnings, None


def _collect_render_semantic_warnings(connection) -> list[str]:  # type: ignore[no-untyped-def]
    warnings: list[str] = []
    scope = fetch_section_scope(connection, "citation_scope")
    if scope is not None:
        metadata = dict(scope.get("metadata", {}))
        if metadata.get("fallback_from"):
            warnings.append(WARNING_SCOPE_FALLBACK_USED)

    reference_items = fetch_reference_items(connection)
    if any(dict(item).get("numbering", {}).get("has_anomaly") for item in reference_items):
        warnings.append("reference_numbering_anomaly_detected")

    scope_title = str(scope["section_title"]).lower() if scope is not None else ""
    if any(token in scope_title for token in ("related", "review", "background", "prior", "survey")):
        mention_count = connection.execute("SELECT COUNT(*) AS count FROM citation_mentions").fetchone()
        if mention_count is not None and int(mention_count["count"]) == 0:
            warnings.append("no_mentions_found_in_review_scope")

    outline_rows = connection.execute(
        "SELECT title, heading_level FROM outline_nodes ORDER BY position ASC"
    ).fetchall()
    major_headings = [
        str(row["title"])
        for row in outline_rows
        if int(row["heading_level"]) == 1 and not REFERENCES_RE.search(str(row["title"]))
    ]
    summary_count = connection.execute("SELECT COUNT(*) AS count FROM digest_section_summaries").fetchone()
    if major_headings and summary_count is not None and int(summary_count["count"]) < len(major_headings):
        warnings.append(WARNING_DIGEST_UNDERCOVERAGE)
    return warnings


def _validate_error_obj(error_val: object) -> list[str]:
    if error_val is None:
        return []
    if not isinstance(error_val, dict):
        return ["error must be object or null"]
    code = error_val.get("code")
    message = error_val.get("message")
    errors: list[str] = []
    if not isinstance(code, str) or not code.strip():
        errors.append("error.code must be non-empty string")
    if not isinstance(message, str) or not message.strip():
        errors.append("error.message must be non-empty string")
    if isinstance(code, str) and code and code not in STAGE_ERROR_CODES:
        pass
    return errors


def _normalize_reference_item(item: object, warnings: list[str]) -> dict[str, Any]:
    out = dict(item) if isinstance(item, dict) else {"raw": str(item)}
    if "doi" in out and "DOI" not in out:
        out["DOI"] = out.pop("doi")
        warnings.append("references: migrated field 'doi' -> 'DOI'")
    out.setdefault("author", [])
    out.setdefault("title", "")
    out.setdefault("year", None)
    out.setdefault("raw", "")
    out.setdefault("confidence", 0.1)
    out["author"] = _as_str_list(out.get("author"))
    out["title"] = "" if out.get("title") is None else str(out.get("title"))
    out["year"] = _as_int_or_none(out.get("year"))
    out["raw"] = "" if out.get("raw") is None else str(out.get("raw"))
    out["confidence"] = _as_confidence(out.get("confidence"), 0.1)
    return out


def _extract_detected_reference_number(raw: str) -> int | None:
    text = raw.strip()
    for pattern in (
        re.compile(r"^\[(\d+)\]"),
        re.compile(r"^(\d+)[\.\)]"),
        re.compile(r"^(\d+)\s"),
    ):
        match = pattern.match(text)
        if match is not None:
            return int(match.group(1))
    return None


def _detect_reference_numbering(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str], bool]:
    numbered: list[tuple[int, int]] = []
    for entry in entries:
        detected = _extract_detected_reference_number(str(entry.get("raw", "")))
        if detected is not None:
            numbered.append((int(entry["entry_index"]), detected))

    warnings: list[str] = []
    numbering_by_index = {entry_index: detected for entry_index, detected in numbered}
    anomaly_indices: set[int] = set()
    if len(numbered) > 1:
        previous: int | None = None
        for entry_index, detected in numbered:
            entry_warnings: list[str] = []
            if previous is None:
                if detected != 1:
                    entry_warnings.append("reference numbering does not start at 1")
            else:
                if detected <= previous:
                    entry_warnings.append("reference numbering is not strictly increasing")
                if detected != previous + 1:
                    entry_warnings.append("reference numbering is not continuous")
            previous = detected
            if entry_warnings:
                anomaly_indices.add(entry_index)
                warnings.extend(
                    [f"reference entry {entry_index}: {message} (detected_ref_number={detected})" for message in entry_warnings]
                )

    normalized_entries: list[dict[str, Any]] = []
    for entry in entries:
        entry_obj = dict(entry)
        entry_index = int(entry_obj["entry_index"])
        metadata = dict(entry_obj.get("metadata", {}))
        numbering_warning_messages = [
            warning for warning in warnings if warning.startswith(f"reference entry {entry_index}:")
        ]
        numbering = {
            "detected_ref_number": numbering_by_index.get(entry_index),
            "has_anomaly": entry_index in anomaly_indices,
            "warnings": numbering_warning_messages,
        }
        metadata["numbering"] = numbering
        entry_obj["metadata"] = metadata
        normalized_entries.append(entry_obj)
    return normalized_entries, warnings, bool(anomaly_indices)


def _normalize_reference_items_with_entry_metadata(
    items: list[dict[str, Any]],
    entries: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    entry_metadata = {
        int(entry["entry_index"]): dict(dict(entry.get("metadata", {})).get("numbering", {}))
        for entry in entries
    }
    normalized_items: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, item in enumerate(items):
        item_obj = _normalize_reference_item(item, warnings)
        ref_index = int(item_obj.get("ref_index", index))
        metadata = dict(item_obj.get("metadata", {}))
        numbering = dict(entry_metadata.get(ref_index, {}))
        if numbering:
            metadata["numbering"] = numbering
            metadata.setdefault("entry_index", ref_index)
            if numbering.get("detected_ref_number") is not None:
                metadata.setdefault("detected_ref_number", numbering.get("detected_ref_number"))
            if numbering.get("warnings"):
                metadata.setdefault("warnings", list(numbering["warnings"]))
        raw = str(item_obj.get("raw", ""))
        detected_terminal_year = _extract_terminal_publication_year(raw)
        existing_year = _as_int_or_none(item_obj.get("year"))
        if detected_terminal_year is not None and existing_year != detected_terminal_year:
            metadata.setdefault("normalization_notes", []).append(
                f"publication year normalized from {existing_year} to trailing year {detected_terminal_year}"
            )
            item_obj["year"] = detected_terminal_year
        elif existing_year is not None:
            item_obj["year"] = existing_year

        if item_obj.get("confidence", 0.0) < 0.6 or not item_obj.get("title") or item_obj.get("year") is None:
            metadata.setdefault("warnings", []).append(WARNING_REFERENCE_LOW_CONFIDENCE)
            warnings.append(WARNING_REFERENCE_LOW_CONFIDENCE)
        author_list = _as_str_list(item_obj.get("author"))
        if len(author_list) <= 1:
            metadata.setdefault("author_parse_mode", "conservative")
        item_obj["author"] = author_list
        item_obj["metadata"] = metadata
        normalized_items.append(item_obj)
    deduped_warnings = list(dict.fromkeys(warnings))
    return normalized_items, deduped_warnings


def _validate_references_items(items: object) -> list[str]:
    if not isinstance(items, list):
        return ["references must be a JSON array"]
    errors: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"references[{index}] must be object")
            continue
        if not isinstance(item.get("author"), list):
            errors.append(f"references[{index}].author must be array")
        if not isinstance(item.get("title"), str):
            errors.append(f"references[{index}].title must be string")
        year = item.get("year")
        if year is not None and _as_int_or_none(year) is None:
            errors.append(f"references[{index}].year must be int|null")
        if not isinstance(item.get("raw"), str):
            errors.append(f"references[{index}].raw must be string")
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)):
            errors.append(f"references[{index}].confidence must be number")
    return errors


def _validate_citation_analysis_obj(obj: object) -> list[str]:
    if not isinstance(obj, dict):
        return ["citation_analysis must be a JSON object"]
    errors: list[str] = []
    meta = obj.get("meta")
    if not isinstance(meta, dict):
        return ["citation_analysis.meta must be object"]
    scope = meta.get("scope")
    if not isinstance(scope, dict):
        errors.append("citation_analysis.meta.scope must be object")
        scope = {}
    if not isinstance(meta.get("language"), str):
        errors.append("citation_analysis.meta.language must be string")
    if not isinstance(scope.get("section_title"), str):
        errors.append("citation_analysis.meta.scope.section_title must be string")
    line_start = _as_int_or_none(scope.get("line_start"))
    line_end = _as_int_or_none(scope.get("line_end"))
    if line_start is None or line_end is None:
        errors.append("citation_analysis.meta.scope.line_start/line_end must be int")
    elif line_start <= 0 or line_end <= 0 or line_start > line_end:
        errors.append("citation_analysis.meta.scope line range invalid")

    items = obj.get("items")
    unmapped = obj.get("unmapped_mentions")
    if not isinstance(items, list):
        errors.append("citation_analysis.items must be array")
        items = []
    if not isinstance(unmapped, list):
        errors.append("citation_analysis.unmapped_mentions must be array")
        unmapped = []
    if not isinstance(obj.get("summary"), str) or not str(obj.get("summary", "")).strip():
        errors.append("citation_analysis.summary must be non-empty string")
    if not isinstance(obj.get("report_md"), str):
        errors.append("citation_analysis.report_md must be string")

    seen_mention_ids: set[str] = set()
    for ref_pos, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"citation_analysis.items[{ref_pos}] must be object")
            continue
        mentions = item.get("mentions")
        if not isinstance(mentions, list):
            errors.append(f"citation_analysis.items[{ref_pos}].mentions must be array")
            continue
        for mention in mentions:
            if not isinstance(mention, dict):
                errors.append(f"citation_analysis.items[{ref_pos}].mentions item must be object")
                continue
            mention_id = mention.get("mention_id")
            if not isinstance(mention_id, str):
                errors.append("citation mention_id must be string")
                continue
            if mention_id in seen_mention_ids:
                errors.append("mention_id must be unique")
            seen_mention_ids.add(mention_id)

    for mention in unmapped:
        if not isinstance(mention, dict):
            errors.append("citation_analysis.unmapped_mentions item must be object")
            continue
        mention_id = mention.get("mention_id")
        if not isinstance(mention_id, str):
            errors.append("unmapped mention_id must be string")
            continue
        if mention_id in seen_mention_ids:
            errors.append("mention_id must be unique")
        seen_mention_ids.add(mention_id)
    return errors


def _count_citation_mentions(citation_analysis_obj: object) -> int | None:
    if not isinstance(citation_analysis_obj, dict):
        return None
    items = citation_analysis_obj.get("items")
    unmapped = citation_analysis_obj.get("unmapped_mentions")
    if not isinstance(items, list) or not isinstance(unmapped, list):
        return None
    consumed = 0
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("mentions"), list):
            return None
        consumed += len(item["mentions"])
    return consumed + len(unmapped)


def _extract_preprocess_expected_mentions(preprocess_artifact: Path | None) -> tuple[int | None, str | None]:
    if preprocess_artifact is None:
        return None, None
    if not preprocess_artifact.exists():
        return None, f"preprocess artifact does not exist: {preprocess_artifact}"
    try:
        obj = json.loads(preprocess_artifact.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return None, f"preprocess artifact unreadable JSON: {exc}"
    stats = obj.get("stats")
    if not isinstance(stats, dict):
        return None, "preprocess artifact missing stats"
    total_mentions = _as_int_or_none(stats.get("total_mentions"))
    if total_mentions is None:
        return None, "preprocess artifact missing stats.total_mentions"
    return total_mentions, None


def _materialize_outputs(candidate: dict[str, Any], source_path: Path | None, output_root: Path, warnings: list[str]) -> dict[str, Any]:
    digest_content = ""
    references_items: list[dict[str, Any]] = []
    citation_obj: dict[str, Any] = {
        "meta": {"language": "zh-CN", "scope": {"section_title": "Introduction", "line_start": 1, "line_end": 1}},
        "summary": "",
        "items": [],
        "unmapped_mentions": [],
        "report_md": "",
    }

    digest_val = candidate.get("digest")
    if isinstance(digest_val, dict):
        digest_content = str(digest_val.get("md", ""))
    elif isinstance(candidate.get("digest_path"), str) and candidate["digest_path"]:
        try:
            digest_content = Path(candidate["digest_path"]).read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            digest_content = ""

    refs_val = candidate.get("references")
    if isinstance(refs_val, dict) and isinstance(refs_val.get("items"), list):
        references_items = [_normalize_reference_item(item, warnings) for item in refs_val["items"]]
    elif isinstance(refs_val, list):
        references_items = [_normalize_reference_item(item, warnings) for item in refs_val]

    citation_val = candidate.get("citation_analysis")
    if isinstance(citation_val, dict):
        citation_obj = citation_val

    digest_path = output_root / DIGEST_FILENAME
    references_path = output_root / REFERENCES_FILENAME
    citation_path = output_root / CITATION_ANALYSIS_FILENAME
    citation_report_path = output_root / CITATION_ANALYSIS_REPORT_FILENAME

    _write_text(digest_path, digest_content)
    _write_json(references_path, references_items)
    _write_json(citation_path, citation_obj)
    if str(citation_obj.get("report_md", "")).strip():
        _write_text(citation_report_path, str(citation_obj["report_md"]))

    provenance = candidate.get("provenance")
    provenance_obj = provenance if isinstance(provenance, dict) else {}
    model = provenance_obj.get("model", "")
    generated_at = provenance_obj.get("generated_at", utc_now_iso())
    input_hash = provenance_obj.get("input_hash", "")
    if source_path is not None and source_path.exists() and (not isinstance(input_hash, str) or not input_hash.startswith("sha256:")):
        input_hash = sha256_file(source_path)

    out: dict[str, Any] = {
        "digest_path": str(digest_path),
        "references_path": str(references_path),
        "citation_analysis_path": str(citation_path),
        "provenance": {
            "generated_at": str(generated_at),
            "input_hash": str(input_hash),
            "model": str(model),
        },
        "warnings": _as_str_list(candidate.get("warnings")) + warnings,
        "error": candidate.get("error"),
    }
    if citation_report_path.exists():
        out["citation_analysis_report_path"] = str(citation_report_path)
    return out


def _validate_public_output(
    payload: dict[str, Any],
    *,
    preprocess_artifact: Path | None,
    db_path: Path | None,
) -> list[str]:
    required = ["digest_path", "references_path", "citation_analysis_path", "provenance", "warnings", "error"]
    errors: list[str] = []
    for key in required:
        if key not in payload:
            errors.append(f"missing required key: {key}")
    provenance = payload.get("provenance")
    if isinstance(provenance, dict):
        for key in ["generated_at", "input_hash", "model"]:
            if key not in provenance:
                errors.append(f"missing required key: provenance.{key}")
    else:
        errors.append("provenance must be object")

    errors.extend(_validate_error_obj(payload.get("error")))

    references_path = payload.get("references_path", "")
    if isinstance(references_path, str) and references_path:
        path = Path(references_path)
        if not path.exists():
            errors.append(f"references_path does not exist: {path}")
        else:
            try:
                refs_obj = json.loads(path.read_text(encoding="utf-8"))
                errors.extend(_validate_references_items(refs_obj))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"references_path unreadable JSON: {exc}")

    citation_path = payload.get("citation_analysis_path", "")
    citation_obj: dict[str, Any] | None = None
    if isinstance(citation_path, str) and citation_path:
        path = Path(citation_path)
        if not path.exists():
            errors.append(f"citation_analysis_path does not exist: {path}")
        else:
            try:
                citation_obj = json.loads(path.read_text(encoding="utf-8"))
                errors.extend(_validate_citation_analysis_obj(citation_obj))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"citation_analysis_path unreadable JSON: {exc}")

    if citation_obj is not None and "citation_analysis_report_path" in payload:
        report_path_value = payload.get("citation_analysis_report_path")
        if isinstance(report_path_value, str) and report_path_value:
            report_path = Path(report_path_value)
            if not report_path.exists():
                errors.append(f"citation_analysis_report_path does not exist: {report_path}")
            else:
                try:
                    if report_path.read_text(encoding="utf-8") != str(citation_obj.get("report_md", "")):
                        errors.append("citation_analysis_report_path content must equal citation_analysis.report_md")
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"citation_analysis_report_path unreadable text: {exc}")

    expected_mentions, preprocess_error = _extract_preprocess_expected_mentions(preprocess_artifact)
    if preprocess_error is not None:
        errors.append(preprocess_error)
    if expected_mentions is not None and citation_obj is not None:
        actual_mentions = _count_citation_mentions(citation_obj)
        if actual_mentions is None or actual_mentions != expected_mentions:
            errors.append("mention coverage mismatch")

    if db_path is not None and db_path.exists():
        try:
            with connect_db(db_path) as connection:
                db_payload = build_public_output_payload(connection)
            for key in ["digest_path", "references_path", "citation_analysis_path", "citation_analysis_report_path"]:
                if key in db_payload and payload.get(key, "") != db_payload.get(key, ""):
                    errors.append(f"{key} does not match runtime DB artifact registry")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"runtime DB unreadable: {exc}")

    return errors


def _set_success_state(connection, *, stage: str, substep: str, next_action: str, status: str) -> None:  # type: ignore[no-untyped-def]
    set_workflow_state(
        connection,
        current_stage=stage,
        current_substep=substep,
        stage_gate="ready",
        next_action=next_action,
        status_summary=status,
    )


def _handle_bootstrap_runtime_db(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path) if args.db_path else default_db_path()
    initialize_database(db_path)
    with connect_db(db_path) as connection:
        if args.source_path:
            set_runtime_input(connection, "source_path", args.source_path)
        if args.language:
            set_runtime_input(connection, "language", args.language)
        if args.input_hash:
            set_runtime_input(connection, "input_hash", args.input_hash)
        elif args.source_path and Path(args.source_path).exists():
            set_runtime_input(connection, "input_hash", sha256_file(Path(args.source_path)))
        if args.generated_at:
            set_runtime_input(connection, "generated_at", args.generated_at)
        else:
            set_runtime_input(connection, "generated_at", utc_now_iso())
        if args.model:
            set_runtime_input(connection, "model", args.model)
        _set_success_state(
            connection,
            stage="stage_1_normalize_source",
            substep="normalize_source",
            next_action="normalize_source",
            status="runtime database bootstrapped",
        )
        connection.commit()
    print(json.dumps({"db_path": str(db_path), "error": None}, ensure_ascii=False))
    return 0


def _handle_normalize_source(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path) if args.db_path else default_db_path()
    initialize_database(db_path)
    defaults = _default_dispatch_paths()
    output_paths = DispatchPaths(
        source_md_path=Path(args.out_md) if args.out_md else defaults.source_md_path,
        source_meta_path=Path(args.out_meta) if args.out_meta else defaults.source_meta_path,
    )

    with connect_db(db_path) as connection:
        inputs = fetch_runtime_inputs(connection)
        source_path_value = inputs.get("source_path", "")
        language = inputs.get("language", "zh-CN")
        model = inputs.get("model", "")
    if not source_path_value:
        payload = {
            "source_md_path": str(output_paths.source_md_path),
            "source_meta_path": str(output_paths.source_meta_path),
            "warnings": [],
            "error": {
                "code": "normalize_source_failed",
                "message": "runtime_inputs.source_path missing; gate should have blocked normalize_source",
            },
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 2
    source_path = Path(source_path_value) if source_path_value else Path()

    payload, code = _dispatch_source(
        source_path=source_path,
        output_paths=output_paths,
        disable_pymupdf4llm=bool(os.environ.get("LITERATURE_DIGEST_DISABLE_PYMUPDF4LLM")),
        db_path=db_path,
        persist_db_only=args.persist_db_only,
        language=language,
        model=model,
    )
    print(json.dumps(payload, ensure_ascii=False))
    return code


def _dispatch_source(
    *,
    source_path: Path,
    output_paths: DispatchPaths,
    disable_pymupdf4llm: bool,
    db_path: Path,
    persist_db_only: bool,
    language: str,
    model: str,
) -> tuple[dict[str, Any], int]:
    warnings: list[str] = []
    meta: dict[str, Any] = {
        "generated_at": utc_now_iso(),
        "source_path": str(source_path),
        "source_type": "",
        "detection_method": "",
        "conversion_backend": "",
        "fallback_reason": "",
        "quality": {"char_count": 0, "non_empty_lines": 0, "heading_lines": 0, "references_keyword_hits": 0},
        "error": None,
    }
    payload: dict[str, Any] = {
        "source_md_path": str(output_paths.source_md_path),
        "source_meta_path": str(output_paths.source_meta_path),
        "warnings": warnings,
        "error": None,
    }
    if not source_path.exists():
        missing_message = "runtime_inputs.source_path missing; gate should have blocked normalize_source"
        if not str(source_path):
            error = {"code": "normalize_source_failed", "message": missing_message}
        else:
            error = {"code": "FILE_NOT_FOUND", "message": f"source_path not found: {source_path}"}
        meta["error"] = error
        payload["error"] = error
        if not persist_db_only:
            _write_json(output_paths.source_meta_path, meta)
        with connect_db(db_path) as connection:
            set_runtime_error(connection, error["code"], error["message"], "stage_1_normalize_source")
            connection.commit()
        return payload, 2

    source_type, detection_method, detect_error = _detect_source_type(source_path)
    if detect_error is not None or source_type is None or detection_method is None:
        error = {"code": "UNSUPPORTED_INPUT", "message": detect_error or "unable to detect source format"}
        meta["error"] = error
        payload["error"] = error
        if not persist_db_only:
            _write_json(output_paths.source_meta_path, meta)
        with connect_db(db_path) as connection:
            set_runtime_error(connection, error["code"], error["message"], "stage_1_normalize_source")
            connection.commit()
        return payload, 2

    warnings.extend(_extension_warning(source_path, source_type))
    meta["source_type"] = source_type
    meta["detection_method"] = detection_method
    try:
        if source_type == "markdown":
            markdown = _convert_markdown_source(source_path)
            meta["conversion_backend"] = "direct_copy"
        else:
            warnings.append("source input detected as PDF")
            markdown = ""
            fallback_reason = ""
            if disable_pymupdf4llm:
                fallback_reason = "pymupdf4llm disabled by environment"
            else:
                try:
                    markdown = _convert_pdf_with_pymupdf4llm(source_path)
                    meta["conversion_backend"] = "pymupdf4llm"
                except Exception as exc:  # noqa: BLE001
                    fallback_reason = str(exc)
            if not markdown:
                warnings.append("PDF conversion fell back to stdlib text extraction")
                warnings.append("fallback markdown quality may be low for multi-column/layout-heavy PDFs")
                markdown = _convert_pdf_with_stdlib(source_path)
                meta["conversion_backend"] = "stdlib_fallback"
                meta["fallback_reason"] = fallback_reason
    except Exception as exc:  # noqa: BLE001
        error = {"code": "CONVERT_FAILED", "message": str(exc)}
        meta["error"] = error
        payload["error"] = error
        if not persist_db_only:
            _write_json(output_paths.source_meta_path, meta)
        with connect_db(db_path) as connection:
            set_runtime_error(connection, error["code"], error["message"], "stage_1_normalize_source")
            connection.commit()
        return payload, 2

    if not persist_db_only:
        _write_text(output_paths.source_md_path, markdown)
    meta["quality"] = _quality_metrics(markdown)
    meta.update(_quality_markers(markdown))
    if not persist_db_only:
        _write_json(output_paths.source_meta_path, meta)

    with connect_db(db_path) as connection:
        inputs = fetch_runtime_inputs(connection)
        if not inputs.get("generated_at"):
            set_runtime_input(connection, "generated_at", meta["generated_at"])
        if not inputs.get("input_hash"):
            set_runtime_input(connection, "input_hash", sha256_file(source_path))
        if not inputs.get("language"):
            set_runtime_input(connection, "language", language or "zh-CN")
        if model and not inputs.get("model"):
            set_runtime_input(connection, "model", model)
        store_source_document(connection, doc_key="normalized_source", content=markdown, metadata=meta)
        _set_success_state(
            connection,
            stage="stage_2_outline_and_scopes",
            substep="persist_outline_and_scopes",
            next_action="persist_outline_and_scopes",
            status="normalized source persisted",
        )
        connection.commit()
    return payload, 0


def _handle_persist_outline_and_scopes(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path) if args.db_path else default_db_path()
    payload = _read_json_payload(args.payload_file)
    outline_nodes, outline_error = _validate_outline_nodes_payload(payload.get("outline_nodes", []))
    references_scope, references_scope_error = _validate_scope_payload(payload.get("references_scope"), "references_scope")
    citation_scope, citation_scope_error = _validate_scope_payload(payload.get("citation_scope"), "citation_scope")

    with connect_db(db_path) as connection:
        first_error = outline_error or references_scope_error or citation_scope_error
        if first_error is not None or outline_nodes is None or references_scope is None or citation_scope is None:
            set_runtime_error(connection, "citation_scope_failed", first_error or "invalid outline/scope payload", "stage_2_outline_and_scopes")
            connection.commit()
            print(json.dumps({"error": {"code": "citation_scope_failed", "message": first_error or "invalid outline/scope payload"}}, ensure_ascii=False))
            return 2
        store_outline_nodes(connection, outline_nodes)
        store_section_scope(
            connection,
            scope_key="references_scope",
            section_title=str(references_scope["section_title"]),
            line_start=int(references_scope["line_start"]),
            line_end=int(references_scope["line_end"]),
            metadata=_coerce_scope_metadata(
                references_scope.get("metadata", {}),
                section_title=str(references_scope["section_title"]),
                source="agent",
            ),
        )
        store_section_scope(
            connection,
            scope_key="citation_scope",
            section_title=str(citation_scope["section_title"]),
            line_start=int(citation_scope["line_start"]),
            line_end=int(citation_scope["line_end"]),
            metadata=_coerce_scope_metadata(
                citation_scope.get("metadata", {}),
                section_title=str(citation_scope["section_title"]),
                source="agent",
            ),
        )
        _set_success_state(connection, stage="stage_3_digest", substep="persist_digest", next_action="persist_digest", status="outline and scopes persisted")
        connection.commit()
    print(
        json.dumps(
            {
                "stored_outline_nodes": len(outline_nodes),
                "references_scope": references_scope,
                "citation_scope": citation_scope,
                "error": None,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _handle_persist_digest(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path) if args.db_path else default_db_path()
    payload = _read_json_payload(args.payload_file)
    digest_slots, section_summaries, error = _validate_digest_payload(payload)
    with connect_db(db_path) as connection:
        if error is not None or digest_slots is None or section_summaries is None:
            set_runtime_error(connection, "digest_stage_failed", error or "invalid digest payload", "stage_3_digest")
            connection.commit()
            print(json.dumps({"error": {"code": "digest_stage_failed", "message": error or "invalid digest payload"}}, ensure_ascii=False))
            return 2
        coverage_warnings, coverage_error = _validate_digest_coverage(connection, digest_slots, section_summaries)
        if coverage_error is not None:
            set_runtime_error(connection, "digest_stage_failed", coverage_error, "stage_3_digest")
            connection.commit()
            print(json.dumps({"error": {"code": "digest_stage_failed", "message": coverage_error}}, ensure_ascii=False))
            return 2
        store_digest_slots(connection, digest_slots)
        store_digest_section_summaries(connection, section_summaries)
        for warning in coverage_warnings:
            add_runtime_warning_once(connection, warning)
        _set_success_state(
            connection,
            stage="stage_4_references",
            substep="prepare_references_workset",
            next_action="prepare_references_workset",
            status="digest sections persisted",
        )
        connection.commit()
    print(
        json.dumps(
            {
                "stored_digest_slots": len(digest_slots),
                "stored_section_summaries": len(section_summaries),
                "error": None,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _handle_prepare_references_workset(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path) if args.db_path else default_db_path()
    out_path = Path(args.out_path) if args.out_path else Path.cwd() / TMP_DIRNAME / REFERENCES_EXPORT_FILENAME
    review_path = out_path.with_name(
        REFERENCES_REVIEW_EXPORT_FILENAME if out_path.name == REFERENCES_EXPORT_FILENAME else f"{out_path.stem}_review{out_path.suffix or '.json'}"
    )
    with connect_db(db_path) as connection:
        source_doc = fetch_source_document(connection, "normalized_source")
        scope_row = fetch_section_scope(connection, "references_scope")
        if source_doc is None:
            set_runtime_error(connection, "references_stage_failed", "normalized source missing", "stage_4_references")
            connection.commit()
            print(json.dumps({"workset_path": "", "review_path": "", "error": {"code": "references_stage_failed", "message": "normalized source missing"}}, ensure_ascii=False))
            return 2
        if scope_row is None:
            set_runtime_error(connection, "references_stage_failed", "references_scope missing", "stage_4_references")
            connection.commit()
            print(json.dumps({"workset_path": "", "review_path": "", "error": {"code": "references_stage_failed", "message": "references_scope missing"}}, ensure_ascii=False))
            return 2
        scope = _db_scope_to_scope(scope_row)
        lines = str(source_doc["content"]).splitlines()
        if scope.line_start < 1 or scope.line_end < scope.line_start or scope.line_end > len(lines):
            message = "references_scope is out of bounds for normalized source"
            set_runtime_error(connection, "references_stage_failed", message, "stage_4_references")
            connection.commit()
            print(json.dumps({"workset_path": "", "review_path": "", "error": {"code": "references_stage_failed", "message": message}}, ensure_ascii=False))
            return 2
        entries = _split_reference_entries(lines, scope)
        normalized_entries, numbering_warnings, has_numbering_anomaly = _detect_reference_numbering(entries)
        candidates: list[dict[str, Any]] = []
        ambiguity_warnings: list[str] = []
        boundary_warnings: list[str] = []
        for entry in normalized_entries:
            entry_candidates = _generate_reference_candidates(entry)
            if len(entry_candidates) > 1:
                ambiguity_warnings.append(f"{WARNING_REFERENCE_PATTERN_AMBIGUOUS}: entry_index={entry['entry_index']}")
            for candidate in entry_candidates:
                title_candidate = str(candidate.get("title_candidate", "")).strip()
                if not title_candidate or LEADING_PUNCTUATION_RE.match(title_candidate):
                    boundary_warnings.append(f"{WARNING_REFERENCE_TITLE_BOUNDARY_SUSPECT}: entry_index={entry['entry_index']} pattern={candidate['pattern']}")
                candidates.append(candidate)
        batches: list[dict[str, Any]] = []
        if normalized_entries:
            chunk_size = 15
            for batch_index, start in enumerate(range(0, len(normalized_entries), chunk_size)):
                end = min(start + chunk_size - 1, len(normalized_entries) - 1)
                batches.append(
                    {
                        "batch_kind": "references_workset",
                        "batch_index": batch_index,
                        "status": "prepared",
                        "entry_start": start,
                        "entry_end": end,
                        "metadata": {"entry_count": end - start + 1},
                    }
                )
        store_reference_entries(connection, normalized_entries)
        for batch in batches:
            store_reference_batch(
                connection,
                batch_kind=str(batch["batch_kind"]),
                batch_index=int(batch["batch_index"]),
                status=str(batch["status"]),
                entry_start=int(batch["entry_start"]),
                entry_end=int(batch["entry_end"]),
                metadata=dict(batch.get("metadata", {})),
            )
        store_reference_parse_candidates(connection, candidates)
        for warning in [*numbering_warnings, *ambiguity_warnings, *boundary_warnings]:
            add_runtime_warning_once(connection, warning)
        metadata = dict(source_doc.get("metadata", {}))
        metadata["reference_numbering_reliability"] = "low" if has_numbering_anomaly else "high"
        store_source_document(connection, doc_key="normalized_source", content=str(source_doc["content"]), metadata=metadata)
        _set_success_state(
            connection,
            stage="stage_4_references",
            substep="persist_references",
            next_action="persist_references",
            status="reference workset prepared",
        )
        connection.commit()

    workset_payload = _build_reference_workset_export(entries=normalized_entries, candidates=candidates, batches=batches)
    review_payload = _build_reference_review_view(workset_payload)
    if not args.persist_db_only:
        _write_json(out_path, workset_payload)
        _write_json(review_path, review_payload)
    print(
        json.dumps(
            {
                "stored_reference_entries": len(normalized_entries),
                "stored_reference_candidates": len(candidates),
                "numbering_warnings": numbering_warnings,
                "warnings": list(dict.fromkeys([*numbering_warnings, *ambiguity_warnings, *boundary_warnings])),
                "workset_path": str(out_path) if not args.persist_db_only else "",
                "review_path": str(review_path) if not args.persist_db_only else "",
                "error": None,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _handle_persist_references(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path) if args.db_path else default_db_path()
    payload = _read_json_payload(args.payload_file)
    items = payload.get("items", [])
    with connect_db(db_path) as connection:
        if "entries" in payload or "batches" in payload:
            message = "persist_references now accepts only items[] keyed by entry_index + selected_pattern"
            set_runtime_error(connection, "references_stage_failed", message, "stage_4_references")
            connection.commit()
            print(json.dumps({"error": {"code": "references_stage_failed", "message": message}}, ensure_ascii=False))
            return 2
        if not isinstance(items, list):
            set_runtime_error(connection, "references_stage_failed", "items must be array", "stage_4_references")
            connection.commit()
            print(json.dumps({"error": {"code": "references_stage_failed", "message": "items must be array"}}, ensure_ascii=False))
            return 2

        entries = fetch_reference_entries(connection)
        candidates = fetch_reference_parse_candidates(connection)
        if not entries or not candidates:
            message = "reference workset missing; prepare_references_workset must run first"
            set_runtime_error(connection, "references_stage_failed", message, "stage_4_references")
            connection.commit()
            print(json.dumps({"error": {"code": "references_stage_failed", "message": message}}, ensure_ascii=False))
            return 2

        entry_metadata = {int(entry["entry_index"]): dict(entry.get("metadata", {})) for entry in entries}
        candidates_by_entry: dict[int, dict[str, dict[str, Any]]] = {}
        for candidate in candidates:
            candidates_by_entry.setdefault(int(candidate["entry_index"]), {})[str(candidate["pattern"])] = candidate

        normalized_items: list[dict[str, Any]] = []
        warnings: list[str] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                message = f"items[{index}] must be object"
                set_runtime_error(connection, "references_stage_failed", message, "stage_4_references")
                connection.commit()
                print(json.dumps({"error": {"code": "references_stage_failed", "message": message}}, ensure_ascii=False))
                return 2
            required_keys = ("entry_index", "selected_pattern", "author", "title", "year", "raw", "confidence")
            missing = [key for key in required_keys if key not in item]
            if missing:
                message = f"items[{index}] missing required keys: {missing}"
                set_runtime_error(connection, "references_stage_failed", message, "stage_4_references")
                connection.commit()
                print(json.dumps({"error": {"code": "references_stage_failed", "message": message}}, ensure_ascii=False))
                return 2
            entry_index = item.get("entry_index")
            selected_pattern = str(item.get("selected_pattern"))
            if not isinstance(entry_index, int):
                message = f"items[{index}].entry_index must be integer"
                set_runtime_error(connection, "references_stage_failed", message, "stage_4_references")
                connection.commit()
                print(json.dumps({"error": {"code": "references_stage_failed", "message": message}}, ensure_ascii=False))
                return 2
            if entry_index not in candidates_by_entry:
                message = f"items[{index}].entry_index has no prepared candidates"
                set_runtime_error(connection, "references_stage_failed", message, "stage_4_references")
                connection.commit()
                print(json.dumps({"error": {"code": "references_stage_failed", "message": message}}, ensure_ascii=False))
                return 2
            if not selected_pattern:
                message = f"items[{index}].selected_pattern must be non-empty"
                set_runtime_error(connection, "references_stage_failed", message, "stage_4_references")
                connection.commit()
                print(json.dumps({"error": {"code": "references_stage_failed", "message": message}}, ensure_ascii=False))
                return 2
            if selected_pattern not in candidates_by_entry[entry_index]:
                message = f"items[{index}].selected_pattern does not match prepared candidates"
                set_runtime_error(connection, "references_stage_failed", message, "stage_4_references")
                connection.commit()
                print(json.dumps({"error": {"code": "references_stage_failed", "message": message}}, ensure_ascii=False))
                return 2

            title = str(item.get("title", "")).strip()
            if not title:
                message = f"items[{index}].title must be non-empty"
                set_runtime_error(connection, "references_stage_failed", message, "stage_4_references")
                connection.commit()
                print(json.dumps({"error": {"code": "references_stage_failed", "message": message}}, ensure_ascii=False))
                return 2
            if LEADING_PUNCTUATION_RE.match(title):
                message = f"items[{index}].title has suspicious leading punctuation"
                set_runtime_error(connection, "references_stage_failed", message, "stage_4_references")
                connection.commit()
                print(json.dumps({"error": {"code": "references_stage_failed", "message": message}}, ensure_ascii=False))
                return 2

            candidate_obj = candidates_by_entry[entry_index][selected_pattern]
            author = _as_str_list(item.get("author"))
            oversplit_message = _detect_reference_author_oversplit(
                author,
                _as_str_list(candidate_obj.get("author_candidates")),
            )
            if oversplit_message is not None:
                warning = f"{WARNING_REFERENCE_AUTHOR_OVERSPLIT}: entry_index={entry_index} pattern={selected_pattern}"
                add_runtime_warning_once(connection, warning)
                message = f"items[{index}].author invalid: {oversplit_message}"
                set_runtime_error(connection, "reference_author_refinement_invalid", message, "stage_4_references")
                connection.commit()
                print(
                    json.dumps(
                        {
                            "error": {
                                "code": "reference_author_refinement_invalid",
                                "message": message,
                            }
                        },
                        ensure_ascii=False,
                    )
                )
                return 2
            year = _as_int_or_none(item.get("year"))
            raw = str(item.get("raw", ""))
            confidence = _as_confidence(item.get("confidence"), 0.1)
            metadata = dict(item.get("metadata", {}))
            metadata["entry_index"] = entry_index
            metadata["selected_pattern"] = selected_pattern
            metadata["pattern_candidate"] = candidate_obj
            numbering = dict(entry_metadata.get(entry_index, {}).get("numbering", {}))
            if numbering:
                metadata["numbering"] = numbering
                metadata["detected_ref_number"] = numbering.get("detected_ref_number")
                if numbering.get("warnings"):
                    metadata.setdefault("warnings", []).extend(list(numbering.get("warnings", [])))
            normalized_item = {
                "ref_index": entry_index,
                "author": author,
                "title": title,
                "year": year,
                "raw": raw,
                "confidence": confidence,
                "metadata": metadata,
            }
            normalized_item = _normalize_reference_item(normalized_item, warnings)
            normalized_metadata_obj = normalized_item.get("metadata", {})
            normalized_metadata = dict(normalized_metadata_obj) if isinstance(normalized_metadata_obj, dict) else {}
            detected_terminal_year = _extract_terminal_publication_year(raw)
            if detected_terminal_year is not None and normalized_item.get("year") != detected_terminal_year:
                normalized_metadata.setdefault("normalization_notes", []).append(
                    f"publication year normalized from {normalized_item.get('year')} to trailing year {detected_terminal_year}"
                )
                normalized_item["year"] = detected_terminal_year
            normalized_confidence = _as_confidence(normalized_item.get("confidence"), 0.1)
            normalized_item["confidence"] = normalized_confidence
            if normalized_confidence < 0.6 or normalized_item.get("year") is None:
                normalized_metadata.setdefault("warnings", []).append(WARNING_REFERENCE_LOW_CONFIDENCE)
                warnings.append(WARNING_REFERENCE_LOW_CONFIDENCE)
            normalized_item["metadata"] = normalized_metadata
            normalized_items.append(normalized_item)

        store_reference_items(connection, normalized_items)
        for warning in list(dict.fromkeys(warnings)):
            add_runtime_warning_once(connection, warning)
        _set_success_state(connection, stage="stage_5_citation", substep="prepare_citation_workset", next_action="prepare_citation_workset", status="references persisted")
        connection.commit()
    print(json.dumps({"stored_reference_items": len(normalized_items), "warnings": list(dict.fromkeys(warnings)), "error": None}, ensure_ascii=False))
    return 0


def _handle_prepare_citation_workset(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path) if args.db_path else default_db_path()
    payload = _read_json_payload(args.payload_file)
    out_path = Path(args.out_path) if args.out_path else Path.cwd() / TMP_DIRNAME / CITATION_EXPORT_FILENAME
    review_path = out_path.with_name(CITATION_REVIEW_EXPORT_FILENAME if out_path.name == CITATION_EXPORT_FILENAME else f"{out_path.stem}_review{out_path.suffix or '.json'}")

    with connect_db(db_path) as connection:
        inputs = fetch_runtime_inputs(connection)
        source_doc = fetch_source_document(connection, "normalized_source")
        scope_row = fetch_section_scope(connection, "citation_scope")
        reference_items = fetch_reference_items(connection)
        if source_doc is None:
            set_runtime_error(connection, "citation_scope_failed", "normalized source missing", "stage_5_citation")
            connection.commit()
            print(json.dumps({"workset_path": "", "error": {"code": "citation_scope_failed", "message": "normalized source missing"}}, ensure_ascii=False))
            return 2
        if "scope" in payload:
            message = "prepare_citation_workset no longer accepts scope override payload; use section_scopes.citation_scope from DB"
            set_runtime_error(connection, "citation_scope_failed", message, "stage_5_citation")
            connection.commit()
            print(json.dumps({"workset_path": "", "error": {"code": "citation_scope_failed", "message": message}}, ensure_ascii=False))
            return 2
        text = str(source_doc["content"])
        md_path = Path(inputs.get("source_path", "")) if inputs.get("source_path", "") else None

    lines = text.splitlines()
    scope, scope_metadata, scope_error = _resolve_db_citation_scope(scope_row=scope_row, lines=lines)
    workset_payload: dict[str, Any] = {
        "meta": {
            "generated_at": utc_now_iso(),
            "md_path": str(md_path) if md_path is not None else "",
            "language": inputs.get("language", "zh-CN"),
            "scope": None,
            "scope_source": "",
            "scope_decision": {},
        },
        "mentions": [],
        "mention_links": [],
        "workset_items": [],
        "reference_index": [],
        "suggested_batches": [],
        "unresolved_mentions": [],
        "stats": {
            "total_mentions": 0,
            "numeric_mentions": 0,
            "author_year_mentions": 0,
            "resolved_items": 0,
            "unresolved_mentions": 0,
            "filtered_false_positive_mentions": 0,
        },
        "error": None,
    }
    if scope_error is not None or scope is None:
        workset_payload["error"] = {"code": "citation_scope_failed", "message": scope_error or "analysis scope not found."}
    else:
        mentions, filtered_false_positive_mentions = _extract_mentions(lines, scope)
        workset = _build_citation_workset(
            scope=scope,
            mentions=mentions,
            reference_items=reference_items,
        )
        workset_payload["meta"]["scope"] = {
            "section_title": scope.section_title,
            "line_start": scope.line_start,
            "line_end": scope.line_end,
        }
        workset_payload["meta"]["scope_source"] = str(scope_metadata.get("scope_source", scope.source))
        workset_payload["meta"]["scope_decision"] = {
            "selection_reason": str(scope_metadata.get("selection_reason", "")),
            "covered_sections": list(scope_metadata.get("covered_sections", [scope.section_title])),
            "fallback_from": scope_metadata.get("fallback_from"),
            "fallback_reason": str(scope_metadata.get("fallback_reason", "")),
        }
        workset_payload.update(
            {
                "mentions": workset["mentions"],
                "mention_links": workset["mention_links"],
                "workset_items": workset["workset_items"],
                "reference_index": workset["reference_index"],
                "suggested_batches": workset["suggested_batches"],
                "unresolved_mentions": workset["unresolved_mentions"],
            }
        )
        workset_payload["stats"]["total_mentions"] = len(mentions)
        workset_payload["stats"]["numeric_mentions"] = sum(1 for mention in mentions if mention.get("style") == "numeric")
        workset_payload["stats"]["author_year_mentions"] = sum(1 for mention in mentions if mention.get("style") == "author-year")
        workset_payload["stats"]["resolved_items"] = len(workset["workset_items"])
        workset_payload["stats"]["unresolved_mentions"] = len(workset["unresolved_mentions"])
        workset_payload["stats"]["filtered_false_positive_mentions"] = filtered_false_positive_mentions
        workset_payload["review_items"] = _build_citation_review_view(workset_payload)["items"]

    if not args.persist_db_only:
        _write_json(out_path, workset_payload)
        _write_json(review_path, _build_citation_review_view(workset_payload))

    with connect_db(db_path) as connection:
        if workset_payload["error"] is not None:
            error = dict(workset_payload["error"])
            set_runtime_error(connection, "citation_scope_failed", str(error["message"]), "stage_5_citation")
            connection.commit()
            print(
                json.dumps(
                    {
                        "workset_path": str(out_path) if not args.persist_db_only else "",
                        "review_path": str(review_path) if not args.persist_db_only else "",
                        "error": error,
                    },
                    ensure_ascii=False,
                )
            )
            return 2
        scope_payload = dict(workset_payload["meta"]["scope"])
        store_section_scope(
            connection,
            scope_key="citation_scope",
            section_title=str(scope_payload["section_title"]),
            line_start=int(scope_payload["line_start"]),
            line_end=int(scope_payload["line_end"]),
            metadata=_coerce_scope_metadata(
                workset_payload["meta"]["scope_decision"],
                section_title=str(scope_payload["section_title"]),
                source=workset_payload["meta"]["scope_source"],
                fallback_from=workset_payload["meta"]["scope_decision"].get("fallback_from"),
                fallback_reason=str(workset_payload["meta"]["scope_decision"].get("fallback_reason", "")),
            ),
        )
        connection.execute("DELETE FROM citation_batches")
        connection.execute("DELETE FROM citation_items")
        connection.execute("DELETE FROM citation_summary")
        store_citation_mentions(connection, [dict(mention) for mention in workset_payload["mentions"]])
        store_citation_mention_links(connection, [dict(link) for link in workset_payload["mention_links"]])
        store_citation_workset_items(connection, [dict(item) for item in workset_payload["workset_items"]])
        store_citation_unmapped_mentions(connection, [dict(mention) for mention in workset_payload["unresolved_mentions"]])
        for batch in workset_payload["suggested_batches"]:
            batch_obj = dict(batch)
            store_citation_batch(
                connection,
                batch_kind="citation_workset",
                batch_index=int(batch_obj["batch_index"]),
                status="prepared",
                mention_start=int(batch_obj["mention_start"]),
                mention_end=int(batch_obj["mention_end"]),
                metadata={
                    "item_start": int(batch_obj["item_start"]),
                    "item_end": int(batch_obj["item_end"]),
                    "item_count": int(batch_obj["item_count"]),
                    "mention_count": int(batch_obj["mention_count"]),
                },
            )
        reference_items = fetch_reference_items(connection)
        numeric_mentions_present = workset_payload["stats"]["numeric_mentions"] > 0
        if numeric_mentions_present and any(dict(item).get("numbering", {}).get("has_anomaly") for item in reference_items):
            add_runtime_warning_once(connection, "reference_numbering_anomaly_detected")
            add_runtime_warning_once(connection, WARNING_REFERENCE_LOW_CONFIDENCE)
        if int(workset_payload["stats"].get("filtered_false_positive_mentions", 0)) > 0:
            add_runtime_warning_once(connection, WARNING_CITATION_FALSE_POSITIVE_FILTERED)
        if workset_payload["meta"]["scope_decision"].get("fallback_reason"):
            add_runtime_warning_once(connection, WARNING_SCOPE_FALLBACK_USED)
        _set_success_state(connection, stage="stage_5_citation", substep="persist_citation_semantics", next_action="persist_citation_semantics", status="citation workset prepared")
        connection.commit()
    print(
        json.dumps(
            {
                "workset_path": str(out_path) if not args.persist_db_only else "",
                "review_path": str(review_path) if not args.persist_db_only else "",
                "scope": workset_payload["meta"]["scope"],
                "scope_source": workset_payload["meta"]["scope_source"],
                "scope_decision": workset_payload["meta"]["scope_decision"],
                "resolved_items": workset_payload["stats"]["resolved_items"],
                "unresolved_mentions": workset_payload["stats"]["unresolved_mentions"],
                "filtered_false_positive_mentions": workset_payload["stats"].get("filtered_false_positive_mentions", 0),
                "error": None,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _handle_export_citation_workset(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path) if args.db_path else default_db_path()
    with connect_db(db_path) as connection:
        scope_row = fetch_section_scope(connection, "citation_scope")
        if scope_row is None:
            error = {"code": "citation_scope_failed", "message": "citation_scope missing"}
            print(json.dumps({"error": error}, ensure_ascii=False))
            return 2
        mentions = fetch_citation_mentions(connection)
        workset_items = fetch_citation_workset_items(connection)
        if not mentions or not workset_items:
            error = {"code": "citation_scope_failed", "message": "citation workset missing; prepare_citation_workset must run first"}
            print(json.dumps({"error": error}, ensure_ascii=False))
            return 2
        scope = _db_scope_to_scope(scope_row)
        workset = {
            "meta": {
                "scope": {
                    "section_title": scope.section_title,
                    "line_start": scope.line_start,
                    "line_end": scope.line_end,
                },
                "generated_at": utc_now_iso(),
                "total_mentions": len(mentions),
            },
            "mentions": mentions,
            "mention_links": fetch_citation_mention_links(connection),
            "reference_index": fetch_reference_items(connection),
            "workset_items": workset_items,
            "unresolved_mentions": fetch_citation_unmapped_mentions(connection),
            "suggested_batches": [
                {
                    "batch_index": int(row["batch_index"]),
                    "batch_kind": str(row["batch_kind"]),
                    "status": str(row["status"]),
                    "mention_start": int(row["mention_start"]),
                    "mention_end": int(row["mention_end"]),
                    "metadata": json.loads(str(row["metadata_json"])),
                }
                for row in connection.execute(
                    "SELECT batch_kind, batch_index, status, mention_start, mention_end, metadata_json FROM citation_batches ORDER BY batch_index ASC"
                ).fetchall()
            ],
        }
        review_view = _build_citation_review_view(workset)
    if args.out_path:
        _write_json(Path(args.out_path), workset)
        review_out = Path(args.out_path).with_name(f"{Path(args.out_path).stem}_review{Path(args.out_path).suffix or '.json'}")
        _write_json(review_out, review_view)
    workset["review_items"] = review_view["items"]
    print(json.dumps(workset, ensure_ascii=False))
    return 0


def _handle_persist_citation_semantics(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path) if args.db_path else default_db_path()
    payload = _read_json_payload(args.payload_file)

    with connect_db(db_path) as connection:
        workset_items = fetch_citation_workset_items(connection)
        if not workset_items:
            set_runtime_error(connection, "citation_semantics_failed", "citation workset missing; prepare_citation_workset must run first", "stage_5_citation")
            connection.commit()
            print(json.dumps({"error": {"code": "citation_semantics_failed", "message": "citation workset missing; prepare_citation_workset must run first"}}, ensure_ascii=False))
            return 2
        normalized_items, error = _validate_citation_semantics_payload(payload, workset_items)
        if error is not None or normalized_items is None:
            set_runtime_error(connection, "citation_semantics_failed", error or "invalid citation semantics payload", "stage_5_citation")
            connection.commit()
            print(json.dumps({"error": {"code": "citation_semantics_failed", "message": error or "invalid citation semantics payload"}}, ensure_ascii=False))
            return 2
        final_items: list[dict[str, Any]] = []
        for item in normalized_items:
            item_obj = dict(item)
            normalized_function, warning = _normalize_function_value(item_obj.get("function"))
            metadata = dict(item_obj.get("metadata", {}))
            if warning is not None:
                metadata["original_function"] = item_obj.get("function")
                add_runtime_warning_once(connection, warning)
            item_obj["function"] = normalized_function
            item_obj["metadata"] = metadata
            final_items.append(item_obj)
        store_citation_items(connection, final_items)
        _set_success_state(connection, stage="stage_5_citation", substep="persist_citation_timeline", next_action="persist_citation_timeline", status="citation semantics persisted")
        connection.commit()
    print(json.dumps({"stored_citation_items": len(final_items), "error": None}, ensure_ascii=False))
    return 0


def _handle_persist_citation_timeline(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path) if args.db_path else default_db_path()
    payload = _read_json_payload(args.payload_file)

    with connect_db(db_path) as connection:
        citation_items = fetch_citation_items(connection)
        if not citation_items:
            set_runtime_error(connection, "citation_semantics_failed", "citation semantics missing; persist_citation_semantics must run first", "stage_5_citation")
            connection.commit()
            print(json.dumps({"error": {"code": "citation_semantics_failed", "message": "citation semantics missing; persist_citation_semantics must run first"}}, ensure_ascii=False))
            return 2
        workset_items = fetch_citation_workset_items(connection)
        normalized_timeline, warnings, error = _validate_citation_timeline_payload(payload, workset_items)
        if error is not None or normalized_timeline is None:
            set_runtime_error(connection, "citation_timeline_failed", error or "invalid citation timeline payload", "stage_5_citation")
            connection.commit()
            print(json.dumps({"error": {"code": "citation_timeline_failed", "message": error or "invalid citation timeline payload"}}, ensure_ascii=False))
            return 2
        store_citation_timeline(connection, normalized_timeline)
        for warning in warnings:
            add_runtime_warning_once(connection, warning)
        _set_success_state(connection, stage="stage_5_citation", substep="persist_citation_summary", next_action="persist_citation_summary", status="citation timeline persisted")
        connection.commit()
    print(json.dumps({"stored_citation_timeline": True, "warnings": warnings, "error": None}, ensure_ascii=False))
    return 0


def _handle_persist_citation_summary(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path) if args.db_path else default_db_path()
    payload = _read_json_payload(args.payload_file)
    summary = payload.get("summary")
    basis = payload.get("basis")

    with connect_db(db_path) as connection:
        citation_items = fetch_citation_items(connection)
        if not citation_items:
            set_runtime_error(connection, "citation_semantics_failed", "citation semantics missing; persist_citation_semantics must run first", "stage_5_citation")
            connection.commit()
            print(json.dumps({"error": {"code": "citation_semantics_failed", "message": "citation semantics missing; persist_citation_semantics must run first"}}, ensure_ascii=False))
            return 2
        citation_timeline = fetch_citation_timeline(connection)
        if citation_timeline is None:
            set_runtime_error(connection, "citation_timeline_failed", "citation timeline missing; persist_citation_timeline must run first", "stage_5_citation")
            connection.commit()
            print(json.dumps({"error": {"code": "citation_timeline_failed", "message": "citation timeline missing; persist_citation_timeline must run first"}}, ensure_ascii=False))
            return 2
        if not isinstance(summary, str) or not summary.strip():
            set_runtime_error(connection, "citation_semantics_failed", "summary must be non-empty string", "stage_5_citation")
            connection.commit()
            print(json.dumps({"error": {"code": "citation_semantics_failed", "message": "summary must be non-empty string"}}, ensure_ascii=False))
            return 2
        workset_items = fetch_citation_workset_items(connection)
        normalized_basis, error = _validate_citation_summary_basis(basis, workset_items)
        if error is not None or normalized_basis is None:
            set_runtime_error(connection, "citation_semantics_failed", error or "invalid citation summary basis", "stage_5_citation")
            connection.commit()
            print(json.dumps({"error": {"code": "citation_semantics_failed", "message": error or "invalid citation summary basis"}}, ensure_ascii=False))
            return 2
        store_citation_summary(connection, summary.strip(), normalized_basis)
        _set_success_state(connection, stage="stage_6_render_and_validate", substep="render_and_validate", next_action="render_and_validate", status="citation summary persisted")
        connection.commit()
    print(json.dumps({"stored_citation_summary": True, "error": None}, ensure_ascii=False))
    return 0


def _render_public_artifacts(db_path: Path, *, explicit_out_dir: Path | None = None) -> dict[str, Any]:
    with connect_db(db_path) as connection:
        for warning in _collect_render_semantic_warnings(connection):
            add_runtime_warning_once(connection, warning)
        inputs = fetch_runtime_inputs(connection)
        source_path = inputs.get("source_path", "")
        if not source_path:
            raise RuntimeError("runtime_inputs.source_path missing")
        output_root = explicit_out_dir if explicit_out_dir is not None else Path(source_path).parent

        digest_context = build_digest_render_context(connection)
        references_context = build_references_render_context(connection)
        citation_report_context = build_citation_report_render_context(connection)

        digest_md = _render_markdown(_digest_template_name(str(digest_context["language"])), digest_context, "digest.schema.json", ensure_trailing_newline=True)
        references_json = _render_json("references.json.j2", references_context, "references.schema.json")
        report_md = _render_markdown("citation_analysis.md.j2", citation_report_context, "citation_analysis_report.schema.json", ensure_trailing_newline=False)
        citation_context = build_citation_render_context(connection, report_md)
        citation_analysis_json = _render_json("citation_analysis.json.j2", citation_context, "citation_analysis.schema.json")

        digest_path = output_root / DIGEST_FILENAME
        references_path = output_root / REFERENCES_FILENAME
        citation_analysis_path = output_root / CITATION_ANALYSIS_FILENAME
        citation_report_path = output_root / CITATION_ANALYSIS_REPORT_FILENAME

        _write_text(digest_path, digest_md)
        _write_text(references_path, references_json)
        _write_text(citation_analysis_path, citation_analysis_json)

        register_artifact(connection, artifact_key="digest_path", path=digest_path, is_required=True, media_type="text/markdown", source_table="digest_slots")
        register_artifact(connection, artifact_key="references_path", path=references_path, is_required=True, media_type="application/json", source_table="reference_items")
        register_artifact(connection, artifact_key="citation_analysis_path", path=citation_analysis_path, is_required=True, media_type="application/json", source_table="citation_summary")
        if report_md.strip():
            _write_text(citation_report_path, report_md)
            register_artifact(connection, artifact_key="citation_analysis_report_path", path=citation_report_path, is_required=False, media_type="text/markdown", source_table="citation_summary")
        connection.commit()
        return build_public_output_payload(connection)


def _handle_render_and_validate(args: argparse.Namespace) -> int:
    mode = args.mode
    db_path = Path(args.db_path) if args.db_path else default_db_path()

    if mode == "render":
        if args.source_path or args.preprocess_artifact or args.in_path:
            payload = {
                "digest_path": "",
                "references_path": "",
                "citation_analysis_path": "",
                "provenance": {"generated_at": "", "input_hash": "", "model": ""},
                "warnings": [],
                "error": {
                    "code": "citation_report_failed",
                    "message": "render mode does not accept explicit source/preprocess/stdin inputs; render is DB-authoritative and only optionally accepts --out-dir",
                },
            }
            print(json.dumps(payload, ensure_ascii=False))
            return 2
        out_dir = Path(args.out_dir).expanduser() if args.out_dir else None
        try:
            payload = _render_public_artifacts(db_path, explicit_out_dir=out_dir)
            errors = _validate_public_output(payload, preprocess_artifact=None, db_path=db_path)
        except Exception as exc:  # noqa: BLE001
            payload = {
                "digest_path": "",
                "references_path": "",
                "citation_analysis_path": "",
                "provenance": {"generated_at": "", "input_hash": "", "model": ""},
                "warnings": [],
                "error": {
                    "code": "citation_report_failed",
                    "message": f"render mode failed before validation: {exc}",
                },
            }
            print(json.dumps(payload, ensure_ascii=False))
            return 2
        with connect_db(db_path) as connection:
            if errors:
                set_runtime_error(connection, "citation_merge_failed", "; ".join(errors), "stage_6_render_and_validate")
                connection.commit()
                print(json.dumps(payload, ensure_ascii=False))
                return 2
            _set_success_state(connection, stage="stage_7_completed", substep="render_and_validate", next_action="render_and_validate", status="artifacts rendered and validated")
            connection.commit()
            payload = build_public_output_payload(connection)
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if payload.get("error") is None else 2

    in_path = Path(args.in_path) if args.in_path else None
    if in_path is not None:
        obj = json.loads(in_path.read_text(encoding="utf-8"))
    else:
        raw = sys.stdin.read() if sys.stdin.readable() and not sys.stdin.isatty() else ""
        obj = json.loads(raw) if raw.strip() else {}

    source_path = Path(args.source_path) if args.source_path else None
    if source_path is not None and not source_path.exists():
        source_path = None
    out_dir = Path(args.out_dir).expanduser() if args.out_dir else None
    output_root = _resolve_output_root(out_dir, source_path)
    preprocess_artifact = Path(args.preprocess_artifact).expanduser() if args.preprocess_artifact else None

    if mode == "fix":
        warnings: list[str] = []
        fixed = _materialize_outputs(dict(obj) if isinstance(obj, dict) else {}, source_path, output_root, warnings)
        errors = _validate_public_output(fixed, preprocess_artifact=preprocess_artifact, db_path=db_path if args.db_path else None)
        if errors:
            fixed.setdefault("warnings", [])
            fixed["warnings"] = _as_str_list(fixed["warnings"]) + [f"render_and_validate: still invalid: {error}" for error in errors]
            print(json.dumps(fixed, ensure_ascii=False))
            return 2
        print(json.dumps(fixed, ensure_ascii=False))
        return 0

    errors = _validate_public_output(dict(obj) if isinstance(obj, dict) else {}, preprocess_artifact=preprocess_artifact, db_path=db_path if args.db_path else None)
    report = {"ok": len(errors) == 0, "errors": errors}
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified stage runtime for literature-digest.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap = subparsers.add_parser("bootstrap_runtime_db")
    bootstrap.add_argument("--db-path", default="")
    bootstrap.add_argument("--source-path", default="")
    bootstrap.add_argument("--language", default="")
    bootstrap.add_argument("--input-hash", default="")
    bootstrap.add_argument("--generated-at", default="")
    bootstrap.add_argument("--model", default="")
    bootstrap.set_defaults(handler=_handle_bootstrap_runtime_db)

    normalize = subparsers.add_parser("normalize_source")
    normalize.add_argument("--db-path", default="")
    normalize.add_argument("--out-md", default="")
    normalize.add_argument("--out-meta", default="")
    normalize.add_argument("--persist-db-only", action="store_true")
    normalize.set_defaults(handler=_handle_normalize_source)

    outline = subparsers.add_parser("persist_outline_and_scopes")
    outline.add_argument("--db-path", default="")
    outline.add_argument("--payload-file", default="")
    outline.set_defaults(handler=_handle_persist_outline_and_scopes)

    digest = subparsers.add_parser("persist_digest")
    digest.add_argument("--db-path", default="")
    digest.add_argument("--payload-file", default="")
    digest.set_defaults(handler=_handle_persist_digest)

    references_workset = subparsers.add_parser("prepare_references_workset")
    references_workset.add_argument("--db-path", default="")
    references_workset.add_argument("--out", dest="out_path", default="")
    references_workset.add_argument("--persist-db-only", action="store_true")
    references_workset.set_defaults(handler=_handle_prepare_references_workset)

    references = subparsers.add_parser("persist_references")
    references.add_argument("--db-path", default="")
    references.add_argument("--payload-file", default="")
    references.set_defaults(handler=_handle_persist_references)

    mentions = subparsers.add_parser("prepare_citation_workset")
    mentions.add_argument("--db-path", default="")
    mentions.add_argument("--payload-file", default="")
    mentions.add_argument("--out", dest="out_path", default="")
    mentions.add_argument("--persist-db-only", action="store_true")
    mentions.set_defaults(handler=_handle_prepare_citation_workset)

    workset = subparsers.add_parser("export_citation_workset")
    workset.add_argument("--db-path", default="")
    workset.add_argument("--out", dest="out_path", default="")
    workset.set_defaults(handler=_handle_export_citation_workset)

    citation = subparsers.add_parser("persist_citation_semantics")
    citation.add_argument("--db-path", default="")
    citation.add_argument("--payload-file", default="")
    citation.set_defaults(handler=_handle_persist_citation_semantics)

    citation_timeline = subparsers.add_parser("persist_citation_timeline")
    citation_timeline.add_argument("--db-path", default="")
    citation_timeline.add_argument("--payload-file", default="")
    citation_timeline.set_defaults(handler=_handle_persist_citation_timeline)

    citation_summary = subparsers.add_parser("persist_citation_summary")
    citation_summary.add_argument("--db-path", default="")
    citation_summary.add_argument("--payload-file", default="")
    citation_summary.set_defaults(handler=_handle_persist_citation_summary)

    render = subparsers.add_parser("render_and_validate")
    render.add_argument("--db-path", default="")
    render.add_argument("--mode", choices=["render", "fix", "check"], default="render")
    render.add_argument("--in", dest="in_path", default="")
    render.add_argument("--source-path", default="")
    render.add_argument("--out-dir", default="")
    render.add_argument("--preprocess-artifact", default="")
    render.set_defaults(handler=_handle_render_and_validate)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())

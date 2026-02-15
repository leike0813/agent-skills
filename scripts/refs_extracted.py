from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from normalize import coerce_int, extract_arxiv_id, extract_doi, extract_first_url, extract_year


@dataclass(frozen=True)
class RefsExtracted:
    meta: dict[str, Any]
    refs: list[dict[str, Any]]
    warnings: list[str]


def _first_present(mapping: dict[str, Any], keys: list[str]) -> Any:
    for k in keys:
        if k in mapping:
            return mapping.get(k)
    return None


def _extract_line_range(obj: dict[str, Any], warnings: list[str]) -> tuple[int, int]:
    line_start = _first_present(obj, ["line_start", "start_line", "startLine", "lineStart"])
    line_end = _first_present(obj, ["line_end", "end_line", "endLine", "lineEnd"])

    if line_start is None and line_end is None:
        line_range = obj.get("line_range") or obj.get("lineRange")
        if isinstance(line_range, list) and len(line_range) == 2:
            line_start, line_end = line_range[0], line_range[1]

    if line_start is None and line_end is None:
        lines = obj.get("lines")
        if isinstance(lines, dict):
            line_start = _first_present(lines, ["start", "line_start", "start_line"])
            line_end = _first_present(lines, ["end", "line_end", "end_line"])

    if line_start is None and line_end is None:
        single = obj.get("line")
        if single is not None:
            line_start = single
            line_end = single

    start_i = coerce_int(line_start, default=-1)
    end_i = coerce_int(line_end, default=-1)
    if start_i >= 0 and end_i >= 0 and end_i < start_i:
        warnings.append(f"Swapped line range: start={start_i} end={end_i}")
        start_i, end_i = end_i, start_i
    return start_i, end_i


def _normalize_parsed(raw_text: str, parsed: Any) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        parsed = {}

    doi = parsed.get("doi")
    url = parsed.get("url")
    arxiv = parsed.get("arxiv")
    year = parsed.get("year")
    title_guess = parsed.get("title_guess")
    author_guess = parsed.get("author_guess")

    if not doi:
        doi = extract_doi(raw_text)
    if not url:
        url = extract_first_url(raw_text)
    if not arxiv:
        arxiv = extract_arxiv_id(raw_text) or extract_arxiv_id(str(doi) if doi else "") or extract_arxiv_id(str(url) if url else "")
    if not year:
        year = extract_year(raw_text)

    def clean(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None

    return {
        "doi": clean(doi),
        "url": clean(url),
        "arxiv": clean(arxiv),
        "year": clean(year),
        "title_guess": clean(title_guess),
        "author_guess": clean(author_guess),
    }


def _normalize_ref(ref: Any, warnings: list[str]) -> dict[str, Any] | None:
    if isinstance(ref, str):
        raw_text = ref.strip()
        if not raw_text:
            return None
        parsed = _normalize_parsed(raw_text, {})
        return {
            "ref_id": "",
            "line_start": -1,
            "line_end": -1,
            "raw_text": raw_text,
            "parsed": parsed,
        }

    if not isinstance(ref, dict):
        warnings.append(f"Skipped non-object ref entry: {type(ref).__name__}")
        return None

    ref_id = _first_present(ref, ["ref_id", "id", "refId", "number"])
    ref_id_str = str(ref_id).strip() if ref_id is not None else ""

    raw_text = _first_present(ref, ["raw_text", "rawText", "text", "raw"])
    if raw_text is None:
        raw_lines = _first_present(ref, ["raw_lines", "rawLines", "lines_raw", "rawLinesText"])
        if isinstance(raw_lines, list):
            raw_text = "\n".join(str(x) for x in raw_lines if str(x).strip())
    raw_text_str = str(raw_text).strip() if raw_text is not None else ""
    if not raw_text_str:
        warnings.append(f"Skipped ref with no raw_text (ref_id={ref_id_str!r})")
        return None

    line_start, line_end = _extract_line_range(ref, warnings)
    parsed = _normalize_parsed(raw_text_str, ref.get("parsed"))

    return {
        "ref_id": ref_id_str,
        "line_start": line_start,
        "line_end": line_end,
        "raw_text": raw_text_str,
        "parsed": parsed,
    }


def load_refs_extracted(path: str) -> RefsExtracted:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    warnings: list[str] = []
    meta: dict[str, Any] = {}
    refs_raw: Any = None

    if isinstance(data, dict):
        meta_raw = data.get("meta")
        if isinstance(meta_raw, dict):
            meta = dict(meta_raw)
        refs_raw = _first_present(data, ["refs", "references", "items"])
    else:
        warnings.append(f"Unexpected top-level JSON type: {type(data).__name__}")

    if refs_raw is None:
        refs_raw = []
        warnings.append("No refs found in refs_extracted.json (expected one of: refs/references/items)")

    if not isinstance(refs_raw, list):
        warnings.append(f"refs is not a list (got {type(refs_raw).__name__}); treating as empty")
        refs_raw = []

    refs: list[dict[str, Any]] = []
    for r in refs_raw:
        normalized = _normalize_ref(r, warnings)
        if normalized is not None:
            refs.append(normalized)

    meta.setdefault("warnings", [])
    if isinstance(meta.get("warnings"), list):
        meta["warnings"].extend(warnings)
    else:
        meta["warnings"] = warnings

    return RefsExtracted(meta=meta, refs=refs, warnings=warnings)

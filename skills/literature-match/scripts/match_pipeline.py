from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from bbt_library import LibraryIndex, build_library_index, load_betterbibtexjson_from_endpoint, load_betterbibtexjson_from_file
from normalize import extract_arxiv_id, normalize_doi, normalize_url
from refs_extracted import load_refs_extracted
from retrieval_tfidf import TfidfRetrievalIndex, build_tfidf_index, retrieve_top_k


@dataclass(frozen=True)
class MatchParams:
    top_k: int = 10
    tfidf_auto_match_threshold: float = 0.90
    tfidf_auto_match_gap: float = 0.10
    tfidf_needs_llm_threshold: float = 0.25
    year_boost: float = 0.03
    author_boost: float = 0.03


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _candidate_from_record(record: dict[str, Any], score: float) -> dict[str, Any]:
    return {
        "citekey": record.get("citekey") or "",
        "itemKey": record.get("itemKey") or "",
        "score": float(score),
        "title": record.get("title") or "",
        "year": record.get("year"),
        "authors": record.get("authors") or [],
        "doi": record.get("doi"),
        "url": record.get("url"),
        "zotero_tags": record.get("zotero_tags") or [],
        "pdf_attachments": record.get("pdf_attachments") or [],
    }


def _apply_light_boosts(
    base_score: float, *, ref_year: str | None, ref_author_guess: str | None, cand_year: str | None, cand_authors: list[str], params: MatchParams
) -> float:
    score = float(base_score)
    if ref_year and cand_year and str(ref_year) == str(cand_year):
        score += params.year_boost
    if ref_author_guess:
        needle = ref_author_guess.strip().lower()
        if needle:
            hay = " ".join(cand_authors).lower()
            if needle in hay:
                score += params.author_boost
    return score


def _deterministic_match(
    ref: dict[str, Any], library: LibraryIndex
) -> tuple[str | None, list[str], float]:
    parsed = ref.get("parsed") or {}
    doi_norm = normalize_doi(parsed.get("doi"))
    if doi_norm and doi_norm in library.by_doi:
        citekeys = library.by_doi[doi_norm]
        return "doi", citekeys, 0.99 if len(citekeys) == 1 else 0.80

    arxiv_id = parsed.get("arxiv")
    arxiv_norm = extract_arxiv_id(str(arxiv_id)) if arxiv_id else None
    if arxiv_norm and arxiv_norm in library.by_arxiv:
        citekeys = library.by_arxiv[arxiv_norm]
        return "arxiv", citekeys, 0.99 if len(citekeys) == 1 else 0.80

    url_norm = normalize_url(parsed.get("url"))
    if url_norm and url_norm in library.by_url:
        citekeys = library.by_url[url_norm]
        return "url", citekeys, 0.99 if len(citekeys) == 1 else 0.80

    return None, [], 0.0


def _select_query_text(ref: dict[str, Any]) -> str:
    parsed = ref.get("parsed") or {}
    title_guess = parsed.get("title_guess")
    if isinstance(title_guess, str) and title_guess.strip():
        return title_guess.strip()
    raw = ref.get("raw_text") or ""
    return str(raw).strip()


def build_initial_match_result(
    *,
    refs_extracted_path: str,
    zotero_endpoint: str | None = None,
    library_cache_path: str | None = None,
    params: MatchParams | None = None,
) -> dict[str, Any]:
    params = params or MatchParams()

    refs_extracted = load_refs_extracted(refs_extracted_path)
    doc_path = str(refs_extracted.meta.get("doc_path") or "")

    if library_cache_path:
        library_data = load_betterbibtexjson_from_file(library_cache_path)
        endpoint_used = None
    else:
        endpoint_used = zotero_endpoint or "http://127.0.0.1:23119/better-bibtex/export/library?/1/library.betterbibtexjson"
        library_data = load_betterbibtexjson_from_endpoint(endpoint_used)

    library = build_library_index(library_data)
    retrieval_index = build_tfidf_index(library.records)

    warnings: list[str] = []
    meta_warnings = refs_extracted.meta.get("warnings")
    if isinstance(meta_warnings, list):
        warnings.extend(str(w) for w in meta_warnings if str(w).strip())
    warnings.extend(library.warnings)

    refs_out: list[dict[str, Any]] = []
    stats = {"total": 0, "matched": 0, "needs_llm": 0, "needs_review": 0, "unmatched": 0}

    for ref in refs_extracted.refs:
        stats["total"] += 1
        parsed = ref.get("parsed") or {}

        status = "unmatched"
        method = "none"
        confidence = 0.0
        match_citekey: str | None = None
        match_itemkey: str | None = None

        candidates: list[dict[str, Any]] = []

        det_method, det_citekeys, det_conf = _deterministic_match(ref, library)
        if det_method:
            method = det_method
            confidence = det_conf
            for ck in det_citekeys:
                record = library.records.get(ck)
                if record:
                    candidates.append(_candidate_from_record(record, score=1.0))
            if len(det_citekeys) == 1:
                match_citekey = det_citekeys[0]
                match_itemkey = (library.records.get(match_citekey) or {}).get("itemKey") or None
                status = "matched"
            else:
                status = "needs_llm" if candidates else "needs_review"
        else:
            query = _select_query_text(ref)
            retrieved = retrieve_top_k(retrieval_index, query, params.top_k)

            ref_year = parsed.get("year")
            ref_author_guess = parsed.get("author_guess")
            for ck, base_score in retrieved:
                record = library.records.get(ck)
                if not record:
                    continue
                score = _apply_light_boosts(
                    base_score,
                    ref_year=str(ref_year) if ref_year is not None else None,
                    ref_author_guess=str(ref_author_guess) if ref_author_guess is not None else None,
                    cand_year=record.get("year"),
                    cand_authors=record.get("authors") or [],
                    params=params,
                )
                candidates.append(_candidate_from_record(record, score=score))

            candidates.sort(key=lambda c: (c["score"], c.get("citekey") or ""), reverse=True)

            if candidates:
                method = "tfidf"
                top1 = float(candidates[0]["score"])
                top2 = float(candidates[1]["score"]) if len(candidates) > 1 else 0.0
                confidence = top1

                if top1 >= params.tfidf_auto_match_threshold and (top1 - top2) >= params.tfidf_auto_match_gap:
                    match_citekey = str(candidates[0].get("citekey") or "") or None
                    match_itemkey = str(candidates[0].get("itemKey") or "") or None
                    status = "matched"
                elif top1 >= params.tfidf_needs_llm_threshold:
                    status = "needs_llm"
                else:
                    status = "needs_review"

        stats[status] += 1

        refs_out.append(
            {
                "ref_id": ref.get("ref_id") or "",
                "line_start": int(ref.get("line_start") or -1),
                "line_end": int(ref.get("line_end") or -1),
                "raw_text": ref.get("raw_text") or "",
                "parsed": {
                    "doi": parsed.get("doi"),
                    "url": parsed.get("url"),
                    "arxiv": parsed.get("arxiv"),
                    "year": parsed.get("year"),
                    "title_guess": parsed.get("title_guess"),
                    "author_guess": parsed.get("author_guess"),
                },
                "match": {
                    "status": status,
                    "citekey": match_citekey,
                    "itemKey": match_itemkey,
                    "method": method,
                    "confidence": float(confidence),
                },
                "candidates": candidates,
            }
        )

    meta = {
        "doc_path": doc_path,
        "generated_at": _utc_now_iso(),
        "zotero_endpoint": endpoint_used,
        "library_cache_path": library_cache_path,
        "library_item_count": library.indexed_items,
        "library_total_item_count": library.total_items,
        "warnings": warnings,
    }

    return {"meta": meta, "refs": refs_out, "stats": stats}


def write_match_result(path: str, match_result: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(match_result, f, ensure_ascii=False, indent=2)
        f.write("\n")

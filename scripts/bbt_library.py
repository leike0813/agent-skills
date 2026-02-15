from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable

from normalize import extract_arxiv_id, normalize_doi, normalize_url


@dataclass(frozen=True)
class LibraryIndex:
    records: dict[str, dict[str, Any]]
    by_doi: dict[str, list[str]]
    by_arxiv: dict[str, list[str]]
    by_url: dict[str, list[str]]
    total_items: int
    indexed_items: int
    warnings: list[str]


def load_betterbibtexjson_from_file(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_betterbibtexjson_from_endpoint(url: str, timeout_s: float = 10.0) -> dict[str, Any]:
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    opener.addheaders = [("User-Agent", "literature-match/0.1")]
    urllib.request.install_opener(opener)

    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception as e:
        raise RuntimeError(
            "Failed to fetch Better BibTeX export from Zotero. "
            "Ensure Zotero is running and Better BibTeX export endpoint is available.\n"
            f"endpoint: {url}\n"
            f"error: {e}"
        ) from e


def iter_library_items(data: Any) -> Iterable[dict[str, Any]]:
    if isinstance(data, dict):
        items = data.get("items")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    yield item
        return

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                yield item


def _extract_year(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    return match.group(1) if match else None


def _format_creators(creators: Any) -> list[str]:
    if not isinstance(creators, list):
        return []
    authors: list[str] = []
    for c in creators:
        if not isinstance(c, dict):
            continue
        if (c.get("creatorType") or "").lower() not in ("author", ""):
            continue
        last = str(c.get("lastName") or "").strip()
        first = str(c.get("firstName") or "").strip()
        if last and first:
            authors.append(f"{last}, {first}")
        elif last:
            authors.append(last)
        elif first:
            authors.append(first)
    return authors


def _normalize_tags(tags: Any) -> list[str]:
    if not isinstance(tags, list):
        return []
    out: list[str] = []
    for t in tags:
        if isinstance(t, str):
            tag = t.strip()
        elif isinstance(t, dict):
            tag = str(t.get("tag") or "").strip()
        else:
            tag = str(t).strip()
        if tag:
            out.append(tag)
    return out


def _is_pdf_attachment(att: dict[str, Any]) -> bool:
    path = str(att.get("path") or "")
    title = str(att.get("title") or "")
    url = str(att.get("url") or "")

    for value in (path, title, url):
        if value.lower().endswith(".pdf"):
            return True
    lowered = url.lower()
    if "arxiv.org/pdf/" in lowered:
        return True
    if "/pdf/" in lowered:
        return True
    return False


def _extract_pdf_attachments(attachments: Any) -> list[dict[str, str]]:
    if not isinstance(attachments, list):
        return []
    out: list[dict[str, str]] = []
    for att in attachments:
        if not isinstance(att, dict):
            continue
        if not _is_pdf_attachment(att):
            continue
        out.append(
            {
                "title": str(att.get("title") or ""),
                "path": str(att.get("path") or ""),
                "url": str(att.get("url") or ""),
            }
        )
    return out


def summarize_item(item: dict[str, Any]) -> dict[str, Any] | None:
    citekey = item.get("citationKey")
    if not isinstance(citekey, str) or not citekey.strip():
        return None

    title = str(item.get("title") or "").strip()
    date = item.get("date")
    year = _extract_year(date) or _extract_year(item.get("issued")) or _extract_year(item.get("year"))

    doi = str(item.get("DOI") or item.get("doi") or "").strip()
    url = str(item.get("url") or item.get("URL") or "").strip()

    creators = item.get("creators")
    authors = _format_creators(creators)

    tags = _normalize_tags(item.get("tags"))
    pdf_attachments = _extract_pdf_attachments(item.get("attachments"))

    return {
        "citekey": citekey,
        "itemKey": str(item.get("itemKey") or ""),
        "title": title,
        "year": year,
        "authors": authors,
        "doi": doi or None,
        "url": url or None,
        "zotero_tags": tags,
        "pdf_attachments": pdf_attachments,
    }


def build_library_index(data: Any) -> LibraryIndex:
    records: dict[str, dict[str, Any]] = {}
    by_doi: dict[str, list[str]] = {}
    by_arxiv: dict[str, list[str]] = {}
    by_url: dict[str, list[str]] = {}
    warnings: list[str] = []

    items = list(iter_library_items(data))
    total_items = len(items)

    for item in items:
        summary = summarize_item(item)
        if summary is None:
            continue
        citekey = summary["citekey"]
        records[citekey] = summary

        doi_norm = normalize_doi(summary.get("doi"))
        if doi_norm:
            by_doi.setdefault(doi_norm, []).append(citekey)

        url_norm = normalize_url(summary.get("url"))
        if url_norm:
            by_url.setdefault(url_norm, []).append(citekey)

        arxiv_id = extract_arxiv_id(summary.get("doi")) or extract_arxiv_id(summary.get("url"))
        if not arxiv_id:
            extra = item.get("extra")
            arxiv_id = extract_arxiv_id(str(extra)) if extra else None
        if arxiv_id:
            by_arxiv.setdefault(arxiv_id, []).append(citekey)

    for key, citekeys in list(by_doi.items()):
        if len(citekeys) > 1:
            warnings.append(f"Duplicate DOI index for {key}: {citekeys}")

    for key, citekeys in list(by_arxiv.items()):
        if len(citekeys) > 1:
            warnings.append(f"Duplicate arXiv index for {key}: {citekeys}")

    for key, citekeys in list(by_url.items()):
        if len(citekeys) > 1:
            warnings.append(f"Duplicate URL index for {key}: {citekeys}")

    return LibraryIndex(
        records=records,
        by_doi=by_doi,
        by_arxiv=by_arxiv,
        by_url=by_url,
        total_items=total_items,
        indexed_items=len(records),
        warnings=warnings,
    )


def is_readable_file(path: str) -> bool:
    try:
        return os.path.isfile(path) and os.access(path, os.R_OK)
    except Exception:
        return False

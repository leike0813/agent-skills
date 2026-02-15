from __future__ import annotations

import re
from typing import Any

DOI_PATTERN = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.IGNORECASE)
ARXIV_PATTERN = re.compile(r"\b(?:arxiv:)?(\d{4}\.\d{4,5})(?:v\d+)?\b", re.IGNORECASE)
YEAR_PATTERN = re.compile(r"\b(19\d{2}|20\d{2})\b")
URL_PATTERN = re.compile(r"(https?://[^\s\)\]\}>,;]+)", re.IGNORECASE)
ACCESS_YEAR_CONTEXT_PATTERN = re.compile(r"\b(accessed|retrieved|visited)\b", re.IGNORECASE)


def normalize_doi(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None

    text = text.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:", "doi "):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    return text.strip().strip(".,;:()[]{}<>")


def normalize_url(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None

    text = text.strip().strip(".,;:()[]{}<>")
    text = text.lower()
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    if text.startswith("www."):
        text = text[4:]
    text = text.rstrip("/")
    return text


def extract_first_url(text: str | None) -> str | None:
    if not text:
        return None
    match = URL_PATTERN.search(text)
    if not match:
        return None
    return match.group(1).rstrip(").,;]")


def extract_doi(text: str | None) -> str | None:
    if not text:
        return None
    match = DOI_PATTERN.search(text)
    if not match:
        return None
    return match.group(1).rstrip(").,;]")


def extract_arxiv_id(text: str | None) -> str | None:
    if not text:
        return None
    match = ARXIV_PATTERN.search(text)
    return match.group(1) if match else None


def extract_year(text: str | None) -> str | None:
    if not text:
        return None

    ignore_spans: list[tuple[int, int]] = []
    for pattern in (URL_PATTERN, DOI_PATTERN, ARXIV_PATTERN):
        for m in pattern.finditer(text):
            ignore_spans.append((m.start(), m.end()))

    def is_ignored(start: int, end: int) -> bool:
        for s, e in ignore_spans:
            if start < e and end > s:
                return True
        return False

    candidates: list[tuple[str, int, int]] = []
    for m in YEAR_PATTERN.finditer(text):
        start, end = m.start(1), m.end(1)
        if is_ignored(start, end):
            continue
        candidates.append((m.group(1), start, end))

    if not candidates:
        return None

    def is_access_year(start: int) -> bool:
        window_start = max(0, start - 80)
        window = text[window_start:start]
        last = None
        for m in ACCESS_YEAR_CONTEXT_PATTERN.finditer(window):
            last = m
        if not last:
            return False
        return (len(window) - last.start()) <= 50

    def in_parentheses(start: int, end: int) -> bool:
        i = start - 1
        while i >= 0 and text[i].isspace():
            i -= 1
        j = end
        while j < len(text) and text[j].isspace():
            j += 1
        return i >= 0 and j < len(text) and text[i] == "(" and text[j] == ")"

    non_access = [(y, s, e) for (y, s, e) in candidates if not is_access_year(s)]
    if not non_access:
        return None

    paren = [(y, s, e) for (y, s, e) in non_access if in_parentheses(s, e)]
    if paren:
        paren.sort(key=lambda t: t[1], reverse=True)
        return paren[0][0]

    non_access.sort(key=lambda t: t[1], reverse=True)
    return non_access[0][0]


def coerce_int(value: Any, default: int = -1) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except Exception:
        return default

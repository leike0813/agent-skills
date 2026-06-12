from __future__ import annotations

import re
from typing import Any

CANONICAL_METADATA_FIELDS = (
    "publicationTitle",
    "conferenceName",
    "archiveID",
    "university",
    "volume",
    "issue",
    "pages",
    "numPages",
    "DOI",
    "url",
    "publisher",
    "place",
    "ISBN",
    "ISSN",
    "itemType",
    "date",
)

METADATA_ALIASES = {
    "journal": "publicationTitle",
    "journalTitle": "publicationTitle",
    "journal_title": "publicationTitle",
    "doi": "DOI",
    "isbn": "ISBN",
    "issn": "ISSN",
    "arxiv": "archiveID",
    "arXiv": "archiveID",
    "arxivId": "archiveID",
    "arxiv_id": "archiveID",
    "archiveId": "archiveID",
}

ARXIV_ID_RE = re.compile(
    r"^(?:arXiv:)?(?:(?:[a-z-]+(?:\.[A-Z]{2})?/\d{7})|(?:\d{4}\.\d{4,5})(?:v\d+)?)$",
    flags=re.IGNORECASE,
)


def _is_empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False


def normalize_reference_metadata(metadata: object, *, context: str) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(metadata, dict):
        return {}, []

    normalized: dict[str, Any] = {}
    warnings: list[str] = []
    for raw_key, raw_value in metadata.items():
        key = str(raw_key)
        if _is_empty(raw_value):
            continue

        canonical = METADATA_ALIASES.get(key, key)
        value = raw_value.strip() if isinstance(raw_value, str) else raw_value
        if canonical != key:
            warnings.append(f"reference_metadata_alias_normalized: {context}.metadata.{key} -> {canonical}")

        if canonical == "archiveID" and isinstance(value, str):
            value = value.strip()
            if ARXIV_ID_RE.match(value) and not value.lower().startswith("arxiv:"):
                value = f"arXiv:{value}"
                warnings.append(f"reference_metadata_alias_normalized: {context}.metadata.archiveID prefixed with arXiv:")

        if canonical not in CANONICAL_METADATA_FIELDS:
            warnings.append(f"reference_metadata_field_unrecognized: {context}.metadata.{key}")
            continue

        normalized[canonical] = value

    return normalized, list(dict.fromkeys(warnings))


def merge_warnings(*warning_groups: list[str] | tuple[str, ...] | None) -> list[str]:
    merged: list[str] = []
    for warnings in warning_groups:
        if not warnings:
            continue
        for warning in warnings:
            text = str(warning).strip()
            if text and text not in merged:
                merged.append(text)
    return merged

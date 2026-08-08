from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlparse
from urllib.request import Request, urlopen


DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
ARXIV_NEW_RE = re.compile(r"^(\d{4}\.\d{4,5})(?:v\d+)?$", re.IGNORECASE)
ARXIV_OLD_RE = re.compile(r"^([a-z][a-z0-9.-]*/\d{7})(?:v\d+)?$", re.IGNORECASE)
YEAR_RE = re.compile(r"^(?:1[5-9]\d{2}|20\d{2}|21\d{2})$")
DOI_IN_TEXT_RE = re.compile(r"10\.\d{4,9}/[^\s\]\[(){}<>\"']+", re.IGNORECASE)
ARXIV_IN_TEXT_RE = re.compile(
    r"(?:arxiv\s*:\s*)?((?:\d{4}\.\d{4,5}|[a-z][a-z0-9.-]*/\d{7})(?:v\d+)?)",
    re.IGNORECASE,
)

HTTP_TIMEOUT_SECONDS = 10.0
HTTP_MAX_ATTEMPTS = 2
HTTP_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
RETRY_AFTER_CAP_SECONDS = 5.0
SEMANTIC_SCHOLAR_PAGE_SIZE = 100
SEMANTIC_SCHOLAR_MAX_RECORDS = 2000
TITLE_MATCH_THRESHOLD = 0.90
SEMANTIC_SCHOLAR_ARXIV_TITLE_MATCH_THRESHOLD = 0.95
MUTUAL_BEST_MARGIN = 0.05
USER_AGENT = "literature-analysis/1.2 (+public-bibliography-resolution)"

HttpGet = Callable[[str, dict[str, str], float], "HttpResponse"]
Sleeper = Callable[[float], None]


@dataclass(frozen=True)
class Identifier:
    kind: str
    value: str
    canonical: str
    raw: str


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class ProviderFetch:
    provider: str
    status: str
    http_status: int | None
    response: Any
    candidates: list[dict[str, Any]]
    error: dict[str, Any] | None


def normalize_identifier(value: object) -> Identifier | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    text = unquote(raw).strip()
    lowered = text.casefold()
    if lowered.startswith(("http://", "https://")):
        parsed = urlparse(text)
        host = parsed.netloc.casefold()
        path = parsed.path.strip("/")
        if host in {"doi.org", "dx.doi.org"}:
            text = path
        elif host in {"arxiv.org", "www.arxiv.org"}:
            if path.startswith("abs/"):
                text = path.removeprefix("abs/")
            elif path.startswith("pdf/"):
                text = path.removeprefix("pdf/")
            if text.casefold().endswith(".pdf"):
                text = text[:-4]
    text = re.sub(r"^doi\s*:\s*", "", text, flags=re.IGNORECASE).strip()
    if DOI_RE.fullmatch(text):
        normalized = text.rstrip(".,;)").casefold()
        if DOI_RE.fullmatch(normalized):
            return Identifier(kind="doi", value=normalized, canonical=f"DOI:{normalized}", raw=raw)
    text = re.sub(r"^arxiv\s*:\s*", "", text, flags=re.IGNORECASE).strip()
    match = ARXIV_NEW_RE.fullmatch(text) or ARXIV_OLD_RE.fullmatch(text)
    if match is not None:
        normalized = match.group(1).casefold()
        return Identifier(kind="arxiv", value=normalized, canonical=f"ARXIV:{normalized}", raw=raw)
    return None


def identifier_in_text(identifier: Identifier, text: str) -> bool:
    normalized_text = unicodedata.normalize("NFKC", text).casefold()
    if identifier.kind == "doi":
        return identifier.value in normalized_text
    return identifier.value in re.sub(r"v\d+\b", "", normalized_text)


def extract_identifiers(text: str) -> set[str]:
    found: set[str] = set()
    for match in DOI_IN_TEXT_RE.finditer(text):
        normalized = normalize_identifier(match.group(0).rstrip(".,;"))
        if normalized is not None:
            found.add(normalized.canonical)
    for match in ARXIV_IN_TEXT_RE.finditer(text):
        normalized = normalize_identifier(f"arXiv:{match.group(1)}")
        if normalized is not None:
            found.add(normalized.canonical)
    return found


def default_http_get(url: str, headers: dict[str, str], timeout: float) -> HttpResponse:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed public providers only
            return HttpResponse(
                status=int(response.status),
                headers={str(key).casefold(): str(value) for key, value in response.headers.items()},
                body=response.read(HTTP_MAX_RESPONSE_BYTES + 1),
            )
    except HTTPError as exc:
        return HttpResponse(
            status=int(exc.code),
            headers={str(key).casefold(): str(value) for key, value in exc.headers.items()},
            body=exc.read(),
        )
    except URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def _retry_delay(headers: dict[str, str], attempt: int) -> float:
    raw = headers.get("retry-after", "").strip()
    try:
        return min(max(float(raw), 0.0), RETRY_AFTER_CAP_SECONDS)
    except ValueError:
        return min(float(2**attempt), RETRY_AFTER_CAP_SECONDS)


def _request_json(
    url: str,
    *,
    http_get: HttpGet,
    sleeper: Sleeper,
) -> tuple[Any | None, int | None, dict[str, Any] | None]:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    last_error: dict[str, Any] | None = None
    for attempt in range(HTTP_MAX_ATTEMPTS):
        try:
            response = http_get(url, headers, HTTP_TIMEOUT_SECONDS)
        except Exception as exc:  # noqa: BLE001 - provider failures are data, not workflow errors
            last_error = {"kind": "network_error", "message": str(exc)}
            if attempt + 1 < HTTP_MAX_ATTEMPTS:
                sleeper(min(float(2**attempt), RETRY_AFTER_CAP_SECONDS))
            continue
        if response.status == 200:
            if len(response.body) > HTTP_MAX_RESPONSE_BYTES:
                return None, response.status, {
                    "kind": "response_too_large",
                    "message": f"response exceeds {HTTP_MAX_RESPONSE_BYTES} bytes",
                }
            try:
                return json.loads(response.body.decode("utf-8")), response.status, None
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                return None, response.status, {"kind": "invalid_json", "message": str(exc)}
        last_error = {
            "kind": "http_error",
            "status": response.status,
            "message": response.body[:500].decode("utf-8", errors="replace"),
        }
        if response.status not in {408, 425, 429, 500, 502, 503, 504} or attempt + 1 >= HTTP_MAX_ATTEMPTS:
            break
        sleeper(_retry_delay(response.headers, attempt))
    return None, last_error.get("status") if last_error else None, last_error


def _clean_authors(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    authors: list[str] = []
    for author in value:
        if isinstance(author, dict):
            text = str(author.get("name", "")).strip()
        else:
            text = str(author).strip()
        if text and text not in authors:
            authors.append(text)
    return authors


def _clean_year(value: object) -> int | None:
    text = str(value or "").strip()
    return int(text) if YEAR_RE.fullmatch(text) else None


def _clean_identifier_map(doi: object = None, arxiv: object = None) -> dict[str, str]:
    identifiers: dict[str, str] = {}
    normalized_doi = normalize_identifier(doi)
    if normalized_doi is not None and normalized_doi.kind == "doi":
        identifiers["DOI"] = normalized_doi.value
    normalized_arxiv = normalize_identifier(f"arXiv:{arxiv}") if arxiv else None
    if normalized_arxiv is not None and normalized_arxiv.kind == "arxiv":
        identifiers["arXiv"] = normalized_arxiv.value
    return identifiers


def crossref_candidates(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("reference"), list):
        return []
    candidates: list[dict[str, Any]] = []
    for index, row in enumerate(payload["reference"]):
        if not isinstance(row, dict):
            continue
        identifiers = _clean_identifier_map(row.get("DOI"))
        metadata: dict[str, Any] = {}
        mapping = {
            "DOI": identifiers.get("DOI"),
            "publicationTitle": row.get("journal-title"),
            "volume": row.get("volume"),
            "issue": row.get("issue"),
            "pages": row.get("first-page") or row.get("pages"),
            "publisher": row.get("publisher"),
            "url": row.get("URL") or row.get("url"),
        }
        for key, value in mapping.items():
            if value not in (None, "", []):
                metadata[key] = value
        candidates.append(
            {
                "providers": ["crossref"],
                "provider_record_ids": [str(row.get("key") or identifiers.get("DOI") or f"crossref-{index}")],
                "identifiers": identifiers,
                "title": str(row.get("article-title") or "").strip(),
                "authors": _clean_authors(row.get("author")),
                "year": _clean_year(row.get("year")),
                "metadata": metadata,
                "response_positions": {"crossref": index},
            }
        )
    return candidates


def semantic_scholar_candidates(rows: object) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    candidates: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        cited = row.get("citedPaper") if isinstance(row, dict) else None
        if not isinstance(cited, dict):
            continue
        external_ids = cited.get("externalIds") if isinstance(cited.get("externalIds"), dict) else {}
        identifiers = _clean_identifier_map(external_ids.get("DOI"), external_ids.get("ArXiv"))
        metadata: dict[str, Any] = {}
        mapping = {
            "DOI": identifiers.get("DOI"),
            "archiveID": identifiers.get("arXiv"),
            "publicationTitle": cited.get("venue"),
            "date": cited.get("publicationDate"),
            "url": cited.get("url"),
        }
        for key, value in mapping.items():
            if value not in (None, "", []):
                metadata[key] = value
        candidates.append(
            {
                "providers": ["semantic_scholar"],
                "provider_record_ids": [str(cited.get("paperId") or f"semantic-scholar-{index}")],
                "identifiers": identifiers,
                "title": str(cited.get("title") or "").strip(),
                "authors": _clean_authors(cited.get("authors")),
                "year": _clean_year(cited.get("year")),
                "metadata": metadata,
                "response_positions": {"semantic_scholar": index},
            }
        )
    return candidates


def fetch_crossref(
    identifier: Identifier,
    *,
    http_get: HttpGet = default_http_get,
    sleeper: Sleeper = time.sleep,
) -> ProviderFetch:
    if identifier.kind != "doi":
        return ProviderFetch("crossref", "not_applicable", None, None, [], None)
    encoded = quote(identifier.value, safe="")
    url = f"https://api.crossref.org/works/{encoded}/transform/application/vnd.citationstyles.csl+json"
    payload, status, error = _request_json(url, http_get=http_get, sleeper=sleeper)
    candidates = crossref_candidates(payload)
    outcome = "succeeded" if candidates else ("failed" if error else "empty")
    return ProviderFetch("crossref", outcome, status, payload, candidates, error)


def fetch_semantic_scholar(
    identifier: Identifier,
    *,
    http_get: HttpGet = default_http_get,
    sleeper: Sleeper = time.sleep,
) -> ProviderFetch:
    paper_id = f"DOI:{identifier.value}" if identifier.kind == "doi" else f"ARXIV:{identifier.value}"
    fields = "title,authors,year,externalIds,venue,publicationDate,url"
    offset = 0
    all_rows: list[dict[str, Any]] = []
    pages: list[Any] = []
    last_status: int | None = None
    while len(all_rows) < SEMANTIC_SCHOLAR_MAX_RECORDS:
        encoded = quote(paper_id, safe="")
        url = (
            f"https://api.semanticscholar.org/graph/v1/paper/{encoded}/references"
            f"?offset={offset}&limit={SEMANTIC_SCHOLAR_PAGE_SIZE}&fields={quote(fields, safe=',')}"
        )
        payload, last_status, error = _request_json(url, http_get=http_get, sleeper=sleeper)
        if error is not None:
            return ProviderFetch("semantic_scholar", "failed", last_status, pages or payload, semantic_scholar_candidates(all_rows), error)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            return ProviderFetch(
                "semantic_scholar",
                "failed",
                last_status,
                pages or payload,
                semantic_scholar_candidates(all_rows),
                {"kind": "invalid_shape", "message": "response.data must be an array"},
            )
        pages.append(payload)
        all_rows.extend(row for row in payload["data"] if isinstance(row, dict))
        next_offset = payload.get("next")
        if not isinstance(next_offset, int) or next_offset <= offset or not payload["data"]:
            break
        offset = next_offset
    candidates = semantic_scholar_candidates(all_rows[:SEMANTIC_SCHOLAR_MAX_RECORDS])
    return ProviderFetch(
        "semantic_scholar",
        "succeeded" if candidates else "empty",
        last_status,
        pages,
        candidates,
        None,
    )


def _normalized_title(title: object) -> str:
    text = unicodedata.normalize("NFKC", str(title or "")).casefold()
    normalized = "".join(" " if unicodedata.category(char).startswith(("P", "S")) else char for char in text)
    return re.sub(r"\s+", " ", normalized).strip()


def _compact_title(title: object) -> str:
    return "".join(char for char in _normalized_title(title) if char.isalnum())


def _title_tokens(title: object) -> list[str]:
    return re.findall(r"\w+", _normalized_title(title), flags=re.UNICODE)


def _stable_id_set(candidate: dict[str, Any]) -> set[str]:
    identifiers = candidate.get("identifiers") if isinstance(candidate.get("identifiers"), dict) else {}
    result: set[str] = set()
    if identifiers.get("DOI"):
        result.add(f"DOI:{str(identifiers['DOI']).casefold()}")
    if identifiers.get("arXiv"):
        result.add(f"ARXIV:{str(identifiers['arXiv']).casefold()}")
    return result


def _same_work(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_ids = _stable_id_set(left)
    right_ids = _stable_id_set(right)
    if left_ids and right_ids:
        return bool(left_ids & right_ids)
    left_title = _compact_title(left.get("title"))
    right_title = _compact_title(right.get("title"))
    if not left_title or left_title != right_title:
        return False
    left_year = left.get("year")
    right_year = right.get("year")
    return left_year is None or right_year is None or left_year == right_year


def merge_provider_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for candidate in candidates:
        target = next((item for item in merged if _same_work(item, candidate)), None)
        if target is None:
            merged.append(json.loads(json.dumps(candidate, ensure_ascii=False)))
            continue
        prefer_candidate_title = (
            "crossref" in candidate.get("providers", [])
            and "crossref" not in target.get("providers", [])
        )
        target["providers"] = list(dict.fromkeys([*target.get("providers", []), *candidate.get("providers", [])]))
        target["provider_record_ids"] = list(
            dict.fromkeys([*target.get("provider_record_ids", []), *candidate.get("provider_record_ids", [])])
        )
        target.setdefault("response_positions", {}).update(candidate.get("response_positions", {}))
        target.setdefault("identifiers", {}).update(
            {key: value for key, value in candidate.get("identifiers", {}).items() if value}
        )
        if not target.get("title") or prefer_candidate_title:
            target["title"] = candidate.get("title", "")
        if len(candidate.get("authors", [])) > len(target.get("authors", [])):
            target["authors"] = list(candidate.get("authors", []))
        if target.get("year") is None:
            target["year"] = candidate.get("year")
        target_metadata = target.setdefault("metadata", {})
        for key, value in candidate.get("metadata", {}).items():
            if key not in target_metadata or target_metadata[key] in (None, "", []):
                target_metadata[key] = value
    return merged


def _title_score(local_title: str, api_title: str) -> float:
    local_compact = _compact_title(local_title)
    api_compact = _compact_title(api_title)
    if not local_compact or not api_compact:
        return 0.0
    if local_compact == api_compact:
        return 0.99
    local_tokens = set(_title_tokens(local_title))
    api_tokens = set(_title_tokens(api_title))
    if min(len(local_tokens), len(api_tokens)) < 3:
        return 0.0
    return len(local_tokens & api_tokens) / min(len(local_tokens), len(api_tokens))


def _candidate_complete(candidate: dict[str, Any]) -> bool:
    return bool(
        str(candidate.get("title", "")).strip()
        and candidate.get("authors")
        and isinstance(candidate.get("year"), int)
        and YEAR_RE.fullmatch(str(candidate.get("year")))
    )


def _title_match_threshold(candidate: dict[str, Any]) -> float:
    providers = {str(provider) for provider in candidate.get("providers", [])}
    identifiers = dict(candidate.get("identifiers", {}))
    arxiv_identifier = identifiers.get("arXiv")
    if (
        "semantic_scholar" in providers
        and arxiv_identifier
        and normalize_identifier(f"arXiv:{arxiv_identifier}") is not None
    ):
        return SEMANTIC_SCHOLAR_ARXIV_TITLE_MATCH_THRESHOLD
    return TITLE_MATCH_THRESHOLD


def resolve_candidates(
    entries: list[dict[str, Any]],
    parse_candidates: list[dict[str, Any]],
    provider_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    parsed_by_entry: dict[int, list[dict[str, Any]]] = {}
    for candidate in parse_candidates:
        parsed_by_entry.setdefault(int(candidate["entry_index"]), []).append(candidate)
    api_candidates = merge_provider_candidates(provider_candidates)
    score_rows: list[dict[str, Any]] = []
    for entry in entries:
        entry_index = int(entry["entry_index"])
        local_ids = extract_identifiers(str(entry.get("raw", "")))
        local_candidates = parsed_by_entry.get(entry_index, [])
        for api_index, api_candidate in enumerate(api_candidates):
            if not _candidate_complete(api_candidate):
                continue
            api_ids = _stable_id_set(api_candidate)
            identifier_match = bool(local_ids & api_ids)
            best_pattern: dict[str, Any] | None = None
            score = 1.0 if identifier_match else 0.0
            for parsed in local_candidates:
                parsed_year = parsed.get("year_candidate")
                api_year = api_candidate.get("year")
                if not identifier_match and parsed_year is not None and api_year is not None and parsed_year != api_year:
                    continue
                candidate_score = _title_score(str(parsed.get("title_candidate", "")), str(api_candidate.get("title", "")))
                if candidate_score > score or (identifier_match and best_pattern is None):
                    score = 1.0 if identifier_match else candidate_score
                    best_pattern = parsed
            if best_pattern is None and identifier_match and local_candidates:
                best_pattern = max(local_candidates, key=lambda item: float(item.get("confidence", 0.0)))
            threshold = _title_match_threshold(api_candidate)
            if best_pattern is not None and (identifier_match or score >= threshold):
                score_rows.append(
                    {
                        "entry_index": entry_index,
                        "api_index": api_index,
                        "score": score,
                        "match_basis": "identifier" if identifier_match else "title",
                        "selected_candidate": best_pattern,
                    }
                )

    decisions: list[dict[str, Any]] = []
    for entry in entries:
        entry_index = int(entry["entry_index"])
        local_scores = sorted(
            (row for row in score_rows if row["entry_index"] == entry_index),
            key=lambda row: (-float(row["score"]), int(row["api_index"])),
        )
        if not local_scores:
            decisions.append({"entry_index": entry_index, "status": "unresolved", "reason": "no_confident_api_match"})
            continue
        best = local_scores[0]
        runner_up = float(local_scores[1]["score"]) if len(local_scores) > 1 else 0.0
        api_scores = sorted(
            (row for row in score_rows if row["api_index"] == best["api_index"]),
            key=lambda row: (-float(row["score"]), int(row["entry_index"])),
        )
        api_runner_up = float(api_scores[1]["score"]) if len(api_scores) > 1 else 0.0
        if best["match_basis"] != "identifier" and (
            float(best["score"]) - runner_up < MUTUAL_BEST_MARGIN
            or float(best["score"]) - api_runner_up < MUTUAL_BEST_MARGIN
        ):
            decisions.append({"entry_index": entry_index, "status": "unresolved", "reason": "ambiguous_api_match"})
            continue
        api_candidate = api_candidates[int(best["api_index"])]
        selected = dict(best["selected_candidate"])
        entry_metadata = dict(entry.get("metadata", {}))
        selected_metadata = dict(selected.get("metadata", {}))
        metadata = dict(api_candidate.get("metadata", {}))
        metadata.update(
            {
                "entry_index": entry_index,
                "selected_pattern": str(selected.get("pattern", "")),
                "pattern_candidate": selected,
                "resolution_source": "reference_api",
                "reference_api_providers": list(api_candidate.get("providers", [])),
                "reference_api_record_ids": list(api_candidate.get("provider_record_ids", [])),
                "reference_api_match_basis": str(best["match_basis"]),
                "reference_api_match_score": float(best["score"]),
            }
        )
        for key in ("citekey", "bibitem_key"):
            value = selected_metadata.get(key)
            if isinstance(value, str) and value.strip():
                metadata.setdefault(key, value.strip())
        for key in ("detected_ref_label", "normalized_ref_label", "citation_label_aliases"):
            value = entry_metadata.get(key, selected_metadata.get(key))
            if value not in (None, "", []):
                metadata.setdefault(key, value)
        numbering = entry_metadata.get("numbering")
        if isinstance(numbering, dict) and numbering:
            metadata["numbering"] = numbering
            metadata["detected_ref_number"] = numbering.get("detected_ref_number")
        item = {
            "ref_index": entry_index,
            "author": list(api_candidate.get("authors", [])),
            "title": str(api_candidate.get("title", "")).strip(),
            "year": int(api_candidate["year"]),
            "raw": str(entry.get("raw", "")),
            "confidence": min(max(float(best["score"]), TITLE_MATCH_THRESHOLD), 1.0),
            "metadata": metadata,
        }
        decisions.append(
            {
                "entry_index": entry_index,
                "status": "accepted",
                "reason": "matched",
                "providers": list(api_candidate.get("providers", [])),
                "provider_record_ids": list(api_candidate.get("provider_record_ids", [])),
                "match_basis": str(best["match_basis"]),
                "match_score": float(best["score"]),
                "item": item,
            }
        )
    return decisions

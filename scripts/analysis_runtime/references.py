from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Any

from .algorithm_adapter import call_algorithm_handler, reference_hard_quality_reason_codes
from . import agent_work
from . import runtime_db
from . import reference_api
from .payload_normalization import CANONICAL_METADATA_FIELDS, merge_warnings, normalize_reference_metadata


REFERENCE_FORBIDDEN_FIELDS = ["items", "selected_pattern", "ref_index", "raw", "confidence", "metadata_enrichment_items"]
REFERENCE_REVIEW_FORBIDDEN_FIELDS = ["raw", "confidence", "ref_index", "selected_pattern", "metadata"]
METADATA_EVIDENCE_STATUSES = {"fields_extracted", "existing_fields_confirmed", "no_local_evidence"}
INTERNAL_METADATA_STATUS = {
    "fields_extracted": "enriched",
    "existing_fields_confirmed": "confirmed_existing",
    "no_local_evidence": "no_metadata_found",
}
EVIDENCE_MATCHED_METADATA_FIELDS = {"DOI", "url", "archiveID", "ISBN", "ISSN", "pages", "volume", "issue"}
METADATA_REVIEW_FORBIDDEN_FIELDS = ["author", "authors", "title", "year", "raw", "raw_reference", "reference", "confidence", "ref_index"]


def _reference_core_payload_shape() -> dict[str, Any]:
    return {
        "reference_reviews": [
            {
                "reference_key": "reference-0",
                "selected_parse_pattern": "one value from allowed_parse_patterns",
                "authors": ["Author"],
                "title": "Original title",
                "publication_year": 2024,
                "review_notes": "optional",
            }
        ],
        "note": "Submit metadata_evidence_reviews only after runtime returns metadata_evidence_packages.",
    }


def _reference_core_field_guidance() -> dict[str, Any]:
    return {
        "reference_key": "Stable work key from reference core batch files; do not use ref_index.",
        "selected_parse_pattern": "Required parse hypothesis. Must be one of allowed_parse_patterns for the same reference_key in the batch file.",
        "authors": "Array of author strings in source order.",
        "title": "Title in original language/script.",
        "publication_year": "Integer year or null if not supported by source text.",
        "metadata": "Do not submit metadata in reference_reviews. Runtime returns metadata_evidence_packages after core references are stored.",
        "batch_inputs": "Read reference_core_batch_paths; stdout does not inline reference_review_packages.",
    }


def _reference_core_subagent_policy() -> str:
    return "Default to delegating reference core review by batch when reference_core_batch_paths exist and subagents are available. Skip only when subagents are unavailable, the batch is trivially small, or context cannot be split; record the reason. Metadata review happens in the next returned work packages. Subagents draft only; main agent is the single DB writer and payload submitter."


def _reference_core_prompt() -> str:
    return (
        "Read the provided reference core batch JSON file. Return JSON with reference_reviews[] only. "
        "Use only the reference_review_packages and allowed_parse_patterns_by_reference_key in that file. "
        "Each review must include reference_key, selected_parse_pattern, authors, title, publication_year, and review_notes. "
        "Keep reference_key unchanged. Do not include metadata, raw, confidence, ref_index, selected_pattern, database fields, renderer fields, or entries outside this batch. "
        "If file writing is available, write the draft to suggested_draft_output_path and return that path. "
        "Do not write DB, run runtime commands, submit payloads, or generate final artifacts."
    )


def _reference_core_merge_contract() -> dict[str, Any]:
    return {
        "single_writer": "main_agent",
        "required_payload_keys": ["reference_reviews"],
        "optional_payload_keys": ["split_reviews"],
        "forbidden_submit_keys": REFERENCE_FORBIDDEN_FIELDS,
        "merge_notes": "Subagents return core batch drafts only. Main agent is the single DB writer, keeps stable keys unchanged, combines arrays, resolves duplicate keys, and submits one core payload. Metadata is submitted in the next round.",
    }


def _metadata_evidence_payload_shape() -> dict[str, Any]:
    return {
        "metadata_evidence_reviews": [
            {
                "reference_key": "reference-0",
                "status": "fields_extracted | existing_fields_confirmed | no_local_evidence",
                "metadata": {},
                "evidence_note": "required evidence or reason",
            }
        ]
    }


def _metadata_evidence_policy() -> dict[str, Any]:
    return {
        "external_lookup_allowed": False,
        "allowed_evidence_sources": [
            "locked_reference",
            "existing_metadata",
            "metadata_context_text",
            "raw/source text explicitly present in this batch file",
        ],
        "forbidden_actions": [
            "web search",
            "Crossref lookup",
            "arXiv lookup",
            "Google Scholar lookup",
            "Zotero lookup",
            "Semantic Scholar lookup",
            "DOI resolver lookup",
            "infer venue from general knowledge",
            "guess DOI from title",
            "guess publisher or venue from author/year",
        ],
    }


def _metadata_subagent_policy() -> str:
    return "Default to delegating reference metadata evidence review by batch when metadata_evidence_batch_paths exist and subagents are available. Skip only when subagents are unavailable, the batch is trivially small, or context cannot be split; record the reason. Subagents draft only from local batch evidence; main agent is the single DB writer and submits one final metadata_evidence_reviews[] payload."


def _metadata_prompt() -> str:
    return (
        "This is not a metadata discovery task. Read the provided reference metadata evidence batch JSON file. "
        "Return JSON with metadata_evidence_reviews[] only. "
        "Use only evidence visible in the batch JSON file; external_lookup_allowed is false. "
        "Do not use web search, Crossref, arXiv, Google Scholar, Zotero, Semantic Scholar, DOI resolvers, or other external databases. "
        "Use reference_key as the key. Status must be fields_extracted, existing_fields_confirmed, or no_local_evidence. "
        f"Allowed metadata fields: {', '.join(CANONICAL_METADATA_FIELDS)}. "
        "Only include metadata for status=fields_extracted. If information is not visible in locked_reference, existing_metadata, or metadata_context_text, use no_local_evidence. "
        "For each added field, evidence_note must name the batch JSON field that supports it. "
        "Do not modify locked reference fields, stable keys, selected_parse_pattern, raw text, confidence, or include ref_index. "
        "If file writing is available, write the draft to suggested_draft_output_path and return that path. "
        "Do not write DB, run runtime commands, submit payloads, or generate final artifacts."
    )


def _metadata_merge_contract(required_coverage: list[str]) -> dict[str, Any]:
    return {
        "single_writer": "main_agent",
        "required_payload_keys": ["metadata_evidence_reviews"],
        "forbidden_submit_keys": ["reference_reviews", *REFERENCE_FORBIDDEN_FIELDS],
        "required_coverage": required_coverage,
        "merge_notes": "Subagents return metadata evidence batch drafts only. Main agent is the single DB writer and must submit exactly one metadata_evidence review per metadata evidence package item.",
    }


def _reference_key(entry_index: int) -> str:
    return f"reference-{entry_index}"


def _entry_index_from_key(reference_key: object) -> int | None:
    value = str(reference_key or "").strip()
    if not value.startswith("reference-"):
        return None
    suffix = value.removeprefix("reference-")
    return int(suffix) if suffix.isdigit() else None


def _pattern_names(entry: dict[str, Any]) -> list[str]:
    return [str(pattern.get("pattern")) for pattern in entry.get("patterns", []) if str(pattern.get("pattern", "")).strip()]


def _candidate_by_pattern(entry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(pattern.get("pattern")): pattern for pattern in entry.get("patterns", []) if str(pattern.get("pattern", "")).strip()}


def _load_reference_workset_from_db(db_path: Path) -> dict[str, Any]:
    with runtime_db.connect_db(db_path) as connection:
        entries = runtime_db.fetch_reference_entries(connection)
        candidates = runtime_db.fetch_reference_parse_candidates(connection)
    candidates_by_entry: dict[int, list[dict[str, Any]]] = {}
    for candidate in candidates:
        candidates_by_entry.setdefault(int(candidate["entry_index"]), []).append(candidate)
    workset_entries: list[dict[str, Any]] = []
    for entry in entries:
        metadata = dict(entry.get("metadata", {}))
        numbering = dict(metadata.get("numbering", {}))
        workset_entries.append(
            {
                "entry_index": int(entry["entry_index"]),
                "raw": str(entry["raw"]),
                "detected_ref_number": numbering.get("detected_ref_number"),
                "patterns": candidates_by_entry.get(int(entry["entry_index"]), []),
            }
        )
    return {"entries": workset_entries}


def _unresolved_reference_workset(db_path: Path, workset: dict[str, Any] | None = None) -> dict[str, Any]:
    current = workset or _load_reference_workset_from_db(db_path)
    accepted = _accepted_reference_entry_indexes(db_path)
    return {
        **current,
        "entries": [
            entry
            for entry in current.get("entries", [])
            if int(entry["entry_index"]) not in accepted
        ],
    }


def _accepted_reference_entry_indexes(db_path: Path) -> set[int]:
    with runtime_db.connect_db(db_path) as connection:
        return {
            int(item["entry_index"])
            for item in runtime_db.fetch_reference_api_resolutions(connection)
            if item.get("status") == "accepted"
        }


def _runtime_warnings(db_path: Path) -> list[str]:
    with runtime_db.connect_db(db_path) as connection:
        return runtime_db.fetch_runtime_warnings(connection)


def _split_block_coverage(
    block: dict[str, Any],
    accepted_entry_indexes: set[int],
) -> tuple[list[int], list[str], list[str]]:
    entry_indexes = sorted({int(item) for item in block.get("entry_indexes", [])})
    accepted_keys = [
        _reference_key(entry_index)
        for entry_index in entry_indexes
        if entry_index in accepted_entry_indexes
    ]
    unresolved_keys = [
        _reference_key(entry_index)
        for entry_index in entry_indexes
        if entry_index not in accepted_entry_indexes
    ]
    return entry_indexes, accepted_keys, unresolved_keys


def _reference_packages(workset: dict[str, Any]) -> list[dict[str, Any]]:
    packages: list[dict[str, Any]] = []
    for entry in workset.get("entries", []):
        entry_index = int(entry["entry_index"])
        patterns = _pattern_names(entry)
        candidate_lookup = _candidate_by_pattern(entry)
        recommended = patterns[0] if patterns else ""
        packages.append(
            {
                "reference_key": _reference_key(entry_index),
                "source_reference_number": entry.get("detected_ref_number"),
                "source_text": str(entry.get("raw", "")),
                "selected_parse_pattern_required": True,
                "allowed_parse_patterns": patterns,
                "recommended_parse_pattern": recommended,
                "parse_candidates": [
                    {
                        "selected_parse_pattern": name,
                        "authors_hint": candidate_lookup[name].get("author_candidates", []),
                        "title_hint": candidate_lookup[name].get("title_candidate", ""),
                        "publication_year_hint": candidate_lookup[name].get("year_candidate"),
                        "confidence_hint": candidate_lookup[name].get("confidence"),
                    }
                    for name in patterns
                ],
            }
        )
    return packages


def _batch_packages(workset: dict[str, Any], packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_entry_index = {
        int(pkg["reference_key"].removeprefix("reference-")): pkg["reference_key"]
        for pkg in packages
    }
    batches: list[dict[str, Any]] = []
    source_batches = workset.get("batches", [])
    if source_batches:
        for batch in source_batches:
            start = int(batch.get("entry_start", 0))
            end = int(batch.get("entry_end", start))
            batches.append(
                {
                    "batch_id": f"reference-batch-{batch.get('batch_index', len(batches))}",
                    "batch_key": f"reference-batch-{batch.get('batch_index', len(batches))}",
                    "reference_keys": [key for index, key in by_entry_index.items() if start <= index <= end],
                    "required_return_shape": {
                        "reference_reviews": [
                            {
                                "reference_key": "copy from this batch",
                                "selected_parse_pattern": "one value from allowed_parse_patterns for the same reference_key",
                                "authors": ["author names in source order"],
                                "title": "title in original language",
                                "publication_year": 2024,
                                "review_notes": "brief evidence note",
                            }
                        ]
                    },
                    "forbidden_fields": REFERENCE_REVIEW_FORBIDDEN_FIELDS,
                    "allowed_enum_values": {
                        "selected_parse_pattern": "Use allowed_parse_patterns_by_reference_key for each reference_key."
                    },
                    "minimal_valid_example": {
                        "reference_reviews": [
                            {
                                "reference_key": "reference-0",
                                "selected_parse_pattern": "exact allowed pattern",
                                "authors": ["Smith"],
                                "title": "Original Source Title",
                                "publication_year": 2024,
                                "review_notes": "Parsed from the batch source text.",
                            }
                        ]
                    },
                    "merge_notes": "Default to delegating this batch when subagents are available. Subagent drafts only this batch. Main agent is the single DB writer, keeps reference_key unchanged, merges batches into one reference_reviews[] payload, and submits once.",
                    "subagent_prompt": (
                        "Review this reference batch. Return JSON with reference_reviews[] only. "
                        "Use each package's allowed_parse_patterns; do not invent patterns, metadata, raw text, confidence, or ref_index. "
                        "Keep reference_key unchanged. Do not write DB, run runtime commands, submit payloads, or generate final artifacts. "
                        "Reference metadata evidence is reviewed in the next metadata_evidence_packages round."
                    ),
                }
            )
    else:
        keys = [pkg["reference_key"] for pkg in packages]
        for offset in range(0, len(keys), 12):
            batches.append(
                {
                    "batch_id": f"reference-batch-{offset // 12}",
                    "batch_key": f"reference-batch-{offset // 12}",
                    "reference_keys": keys[offset : offset + 12],
                    "required_return_shape": {
                        "reference_reviews": [
                            {
                                "reference_key": "copy from this batch",
                                "selected_parse_pattern": "one value from allowed_parse_patterns for the same reference_key",
                                "authors": ["author names in source order"],
                                "title": "title in original language",
                                "publication_year": 2024,
                                "review_notes": "brief evidence note",
                            }
                        ]
                    },
                    "forbidden_fields": REFERENCE_REVIEW_FORBIDDEN_FIELDS,
                    "allowed_enum_values": {
                        "selected_parse_pattern": "Use allowed_parse_patterns_by_reference_key for each reference_key."
                    },
                    "minimal_valid_example": {
                        "reference_reviews": [
                            {
                                "reference_key": "reference-0",
                                "selected_parse_pattern": "exact allowed pattern",
                                "authors": ["Smith"],
                                "title": "Original Source Title",
                                "publication_year": 2024,
                                "review_notes": "Parsed from the batch source text.",
                            }
                        ]
                    },
                    "merge_notes": "Default to delegating this batch when subagents are available. Subagent drafts only this batch. Main agent is the single DB writer, keeps reference_key unchanged, merges batches into one reference_reviews[] payload, and submits once.",
                    "subagent_prompt": (
                        "Review this reference batch. Return JSON with reference_reviews[] only. "
                        "Use each package's allowed_parse_patterns; do not invent patterns, metadata, raw text, confidence, or ref_index. "
                        "Keep reference_key unchanged. Do not write DB, run runtime commands, submit payloads, or generate final artifacts. "
                        "Reference metadata evidence is reviewed in the next metadata_evidence_packages round."
                    ),
                }
            )
    return batches


def _split_review_packages(
    payload: dict[str, Any],
    *,
    accepted_entry_indexes: set[int] | None = None,
) -> list[dict[str, Any]]:
    accepted_indexes = accepted_entry_indexes or set()
    packages: list[dict[str, Any]] = []
    for block in payload.get("suspect_blocks", []):
        block_index = int(block.get("block_index", len(packages)))
        entry_indexes, accepted_keys, unresolved_keys = _split_block_coverage(block, accepted_indexes)
        if entry_indexes and not unresolved_keys:
            continue
        packages.append(
            {
                "block_key": f"block-{block_index}",
                "block_index": block_index,
                "source_text": str(block.get("source_text", "")),
                "current_fragments": list(block.get("proposed_entries", [])),
                "entry_indexes": entry_indexes,
                "accepted_reference_keys": accepted_keys,
                "unresolved_reference_keys": unresolved_keys,
                "allowed_actions": ["keep", "replace_with_corrected_reference_texts"],
            }
        )
    return packages


def _reference_core_agent_work(db_path: Path, packages: list[dict[str, Any]]) -> dict[str, Any]:
    def build_batch(batch_id: str, batch_packages: list[dict[str, Any]]) -> dict[str, Any]:
        reference_keys = [str(package["reference_key"]) for package in batch_packages]
        return {
            "reference_keys": reference_keys,
            "reference_review_packages": batch_packages,
            "allowed_parse_patterns_by_reference_key": {
                str(package["reference_key"]): list(package.get("allowed_parse_patterns", []))
                for package in batch_packages
            },
            "required_return_shape": _reference_core_payload_shape(),
            "forbidden_fields": REFERENCE_REVIEW_FORBIDDEN_FIELDS,
            "allowed_enum_values": {
                "selected_parse_pattern_by_reference_key": {
                    str(package["reference_key"]): list(package.get("allowed_parse_patterns", []))
                    for package in batch_packages
                }
            },
            "minimal_valid_example": {
                "reference_reviews": [
                    {
                        "reference_key": reference_keys[0] if reference_keys else "reference-0",
                        "selected_parse_pattern": (
                            str(batch_packages[0].get("recommended_parse_pattern", ""))
                            if batch_packages
                            else "exact allowed pattern"
                        ),
                        "authors": ["Smith"],
                        "title": "Original Source Title",
                        "publication_year": 2024,
                        "review_notes": "Parsed from the batch source text.",
                    }
                ]
            },
            "merge_notes": "Default to delegating this runtime-precut batch when subagents are available. Subagent drafts only this batch. Main agent merges all batch drafts into one reference_reviews[] payload and submits once.",
            "subagent_prompt": _reference_core_prompt(),
        }

    return agent_work.write_manifest(
        db_path=db_path,
        kind="reference_core",
        batch_kind="reference_core_review",
        package_key="reference_review_packages",
        packages=packages,
        package_key_field="reference_key",
        batch_payload_builder=build_batch,
        subagent_policy=_reference_core_subagent_policy(),
        merge_contract=_reference_core_merge_contract(),
        payload_submit_shape=_reference_core_payload_shape(),
        batch_prefix="reference-core-batch",
    )


def _metadata_agent_work(
    db_path: Path,
    packages: list[dict[str, Any]],
    instructions: dict[str, Any],
) -> dict[str, Any]:
    required_coverage = [str(package["reference_key"]) for package in packages]

    def build_batch(batch_id: str, batch_packages: list[dict[str, Any]]) -> dict[str, Any]:
        reference_keys = [str(package["reference_key"]) for package in batch_packages]
        return {
            "reference_keys": reference_keys,
            "metadata_evidence_packages": batch_packages,
            "allowed_metadata_fields": list(instructions["allowed_metadata_fields"]),
            "locked_fields": list(instructions["locked_fields"]),
            "required_return_shape": _metadata_evidence_payload_shape(),
            "canonical_metadata_fields": list(CANONICAL_METADATA_FIELDS),
            "forbidden_fields": METADATA_REVIEW_FORBIDDEN_FIELDS,
            "allowed_enum_values": {"status": sorted(METADATA_EVIDENCE_STATUSES)},
            "evidence_policy": _metadata_evidence_policy(),
            "external_lookup_allowed": False,
            "allowed_evidence_sources": _metadata_evidence_policy()["allowed_evidence_sources"],
            "forbidden_actions": _metadata_evidence_policy()["forbidden_actions"],
            "minimal_valid_example": {
                "metadata_evidence_reviews": [
                    {
                        "reference_key": reference_keys[0] if reference_keys else "reference-0",
                        "status": "no_local_evidence",
                        "evidence_note": "No DOI, URL, archive id, container, volume, issue, or pages are visible in this batch JSON file.",
                    }
                ]
            },
            "merge_notes": "Default to delegating this runtime-precut metadata evidence batch when subagents are available. Subagent drafts only from this batch JSON file. Main agent merges all metadata_evidence_reviews[] and submits once.",
            "subagent_prompt": _metadata_prompt(),
        }

    return agent_work.write_manifest(
        db_path=db_path,
        kind="reference_metadata_evidence",
        batch_kind="reference_metadata_evidence_review",
        package_key="metadata_evidence_packages",
        packages=packages,
        package_key_field="reference_key",
        batch_payload_builder=build_batch,
        subagent_policy=_metadata_subagent_policy(),
        merge_contract=_metadata_merge_contract(required_coverage),
        payload_submit_shape=_metadata_evidence_payload_shape(),
        batch_prefix="reference-metadata-evidence-batch",
        manifest_extra={
            "evidence_policy": _metadata_evidence_policy(),
            "external_lookup_allowed": False,
            "allowed_evidence_sources": _metadata_evidence_policy()["allowed_evidence_sources"],
            "forbidden_actions": _metadata_evidence_policy()["forbidden_actions"],
        },
    )


def _effective_identifier(connection) -> tuple[reference_api.Identifier | None, str]:  # type: ignore[no-untyped-def]
    inputs = runtime_db.fetch_runtime_inputs(connection)
    parameter_identifier = reference_api.normalize_identifier(inputs.get("identifier_canonical", ""))
    if parameter_identifier is not None:
        return parameter_identifier, "parameter"
    plan_identity = runtime_db.fetch_source_identity(connection)
    if plan_identity is None:
        return None, "none"
    identifier = reference_api.normalize_identifier(plan_identity.get("canonical_identifier", ""))
    return identifier, "analysis_plan" if identifier is not None else "none"


def _candidates_from_cached_fetch(provider: str, response: object) -> list[dict[str, Any]]:
    if provider == "crossref":
        return reference_api.crossref_candidates(response)
    rows: list[dict[str, Any]] = []
    pages = response if isinstance(response, list) else [response]
    for page in pages:
        if isinstance(page, dict) and isinstance(page.get("data"), list):
            rows.extend(item for item in page["data"] if isinstance(item, dict))
    return reference_api.semantic_scholar_candidates(rows)


def _provider_fetch(
    connection,  # type: ignore[no-untyped-def]
    identifier: reference_api.Identifier,
    provider: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cached = runtime_db.fetch_reference_api_fetch(
        connection,
        canonical_identifier=identifier.canonical,
        provider=provider,
    )
    if cached is not None:
        candidates = _candidates_from_cached_fetch(provider, cached.get("response"))
        return candidates, {
            "provider": provider,
            "status": cached["status"],
            "http_status": cached["http_status"],
            "candidate_count": len(candidates),
            "cached": True,
            "response_sha256": cached["response_sha256"],
            "error": cached["error"],
        }
    fetched = (
        reference_api.fetch_crossref(identifier)
        if provider == "crossref"
        else reference_api.fetch_semantic_scholar(identifier)
    )
    response_text = json.dumps(fetched.response, ensure_ascii=False, sort_keys=True)
    response_sha256 = hashlib.sha256(response_text.encode("utf-8")).hexdigest()
    runtime_db.store_reference_api_fetch(
        connection,
        canonical_identifier=identifier.canonical,
        provider=provider,
        status=fetched.status,
        http_status=fetched.http_status,
        response=fetched.response,
        response_sha256=response_sha256,
        error=fetched.error,
    )
    return list(fetched.candidates), {
        "provider": provider,
        "status": fetched.status,
        "http_status": fetched.http_status,
        "candidate_count": len(fetched.candidates),
        "cached": False,
        "response_sha256": response_sha256,
        "error": fetched.error or {},
    }


def _write_reference_api_audit(
    db_path: Path,
    *,
    identifier: reference_api.Identifier | None,
    identifier_source: str,
    provider_summaries: list[dict[str, Any]],
    resolutions: list[dict[str, Any]],
) -> str:
    with runtime_db.connect_db(db_path) as connection:
        inputs = runtime_db.fetch_runtime_inputs(connection)
    tmp_dir = Path(inputs.get("tmp_dir", db_path.parent)).expanduser().resolve()
    audit_path = tmp_dir / "reference_api_audit.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(
            {
                "kind": "reference_api_audit",
                "identifier": identifier.canonical if identifier is not None else "",
                "identifier_source": identifier_source,
                "providers": provider_summaries,
                "resolutions": [
                    {
                        key: value
                        for key, value in resolution.items()
                        if key != "item"
                    }
                    for resolution in resolutions
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return str(audit_path)


def _algorithm_items_from_api_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items:
        metadata = dict(item.get("metadata", {}))
        for key, value in item.items():
            if key not in {"ref_index", "author", "title", "year", "raw", "confidence", "metadata"}:
                metadata[key] = value
        normalized.append(
            {
                "entry_index": int(item["ref_index"]),
                "selected_pattern": str(metadata.get("selected_pattern", "")),
                "author": list(item.get("author", [])),
                "title": str(item.get("title", "")),
                "year": item.get("year"),
                "raw": str(item.get("raw", "")),
                "confidence": float(item.get("confidence", 0.9)),
                "metadata": metadata,
            }
        )
    return normalized


def _resolve_reference_api(db_path: Path) -> dict[str, Any]:
    with runtime_db.connect_db(db_path) as connection:
        entries = runtime_db.fetch_reference_entries(connection)
        parse_candidates = runtime_db.fetch_reference_parse_candidates(connection)
        identifier, identifier_source = _effective_identifier(connection)
        provider_summaries: list[dict[str, Any]] = []
        provider_candidates: list[dict[str, Any]] = []
        if identifier is None:
            resolutions = [
                {"entry_index": int(entry["entry_index"]), "status": "unresolved", "reason": "no_effective_identifier"}
                for entry in entries
            ]
        else:
            providers = ["semantic_scholar"] if identifier.kind == "arxiv" else ["crossref", "semantic_scholar"]
            resolutions = []
            for provider in providers:
                candidates, summary = _provider_fetch(connection, identifier, provider)
                provider_candidates.extend(candidates)
                provider_summaries.append(summary)
                if summary["status"] == "failed":
                    runtime_db.add_runtime_warning_once(
                        connection,
                        f"reference_api_provider_failed: provider={provider} status={summary.get('http_status')}",
                    )
                resolutions = reference_api.resolve_candidates(entries, parse_candidates, provider_candidates)
                if resolutions and all(item.get("status") == "accepted" for item in resolutions):
                    break
        if not resolutions:
            resolutions = reference_api.resolve_candidates(entries, parse_candidates, provider_candidates)
        for resolution in resolutions:
            if resolution.get("status") != "accepted" or not isinstance(resolution.get("item"), dict):
                continue
            quality_reasons = reference_hard_quality_reason_codes(resolution["item"])
            if quality_reasons:
                resolution["status"] = "unresolved"
                resolution["reason"] = f"api_quality_hard_block:{','.join(quality_reasons)}"
                resolution["quality_reason_codes"] = quality_reasons
                resolution.pop("item", None)
        runtime_db.store_reference_api_resolutions(connection, resolutions)
        accepted_items = [dict(item["item"]) for item in resolutions if item.get("status") == "accepted"]
        runtime_db.store_reference_items(connection, accepted_items)
        accepted_count = len(accepted_items)
        unresolved_count = len(entries) - accepted_count
        runtime_db.store_action_receipt(
            connection,
            action_name="resolve_reference_api",
            stage="stage_5_references",
            status="skipped" if identifier is None else ("succeeded" if unresolved_count == 0 else "partial"),
            metadata={
                "identifier": identifier.canonical if identifier is not None else "",
                "identifier_source": identifier_source,
                "accepted_count": accepted_count,
                "unresolved_count": unresolved_count,
                "providers": provider_summaries,
            },
        )
        connection.commit()
    audit_path = _write_reference_api_audit(
        db_path,
        identifier=identifier,
        identifier_source=identifier_source,
        provider_summaries=provider_summaries,
        resolutions=resolutions,
    )
    return {
        "identifier": identifier.canonical if identifier is not None else "",
        "identifier_source": identifier_source,
        "provider_summaries": provider_summaries,
        "accepted_count": accepted_count,
        "unresolved_count": unresolved_count,
        "audit_path": audit_path,
        "complete": bool(entries) and unresolved_count == 0,
    }


def _persist_complete_api_resolution(
    db_path: Path,
    api_summary: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    if not api_summary.get("complete"):
        return None, []
    with runtime_db.connect_db(db_path) as connection:
        api_items = runtime_db.fetch_reference_items(connection)
    persisted, persist_code = call_algorithm_handler(
        "_handle_persist_references",
        db_path,
        payload={"items": _algorithm_items_from_api_items(api_items)},
    )
    if persist_code != 0:
        api_summary["complete"] = False
        api_summary["unresolved_count"] = len(api_items)
        with runtime_db.connect_db(db_path) as connection:
            runtime_db.store_reference_items(connection, [])
            runtime_db.clear_reference_api_resolutions(connection)
            connection.commit()
        return None, ["reference_api_quality_gate_failed: API items returned to local review"]

    metadata_result, metadata_code = prepare_reference_metadata_enrichment(db_path)
    if metadata_code != 0 or not metadata_result.get("skipped"):
        return None, list(metadata_result.get("warnings", []))
    return {
        "stored_reference_items": persisted.get("stored_reference_items", len(api_items)),
        "next_action": "persist_citation_analysis",
        "metadata_evidence_review": metadata_result,
    }, []


def _sync_api_aware_split_state(db_path: Path, prepared: dict[str, Any]) -> None:
    workset = _read_workset_from_prepare_payload(prepared)
    accepted_entry_indexes = _accepted_reference_entry_indexes(db_path)
    active_suspect_blocks: list[dict[str, Any]] = []
    skipped_block_count = 0
    for block in workset.get("suspect_blocks", []):
        entry_indexes, accepted_keys, unresolved_keys = _split_block_coverage(block, accepted_entry_indexes)
        if entry_indexes and not unresolved_keys:
            skipped_block_count += 1
            continue
        active_suspect_blocks.append(
            {
                **block,
                "entry_indexes": entry_indexes,
                "accepted_reference_keys": accepted_keys,
                "unresolved_reference_keys": unresolved_keys,
            }
        )

    requires_split_review = bool(active_suspect_blocks)
    prepared.update(
        {
            "suspect_blocks": active_suspect_blocks,
            "requires_split_review": requires_split_review,
            "grouping_suspect_count": len(active_suspect_blocks),
            "split_review_package_count": len(active_suspect_blocks),
            "skipped_split_review_block_count": skipped_block_count,
            "next_action": "persist_references",
        }
    )

    raw_next_action = "persist_reference_entry_splits" if requires_split_review else "persist_references"
    status_summary = (
        "reference entry split review required for API-unresolved blocks"
        if requires_split_review
        else "reference API resolution completed before semantic review"
    )
    with runtime_db.connect_db(db_path) as connection:
        receipts = runtime_db.fetch_action_receipts(connection)
        receipt_metadata = dict(receipts.get("prepare_references_workset", {}).get("metadata", {}))
        receipt_metadata.update(
            {
                "requires_split_review": requires_split_review,
                "grouping_suspect_count": len(active_suspect_blocks),
                "split_review_package_count": len(active_suspect_blocks),
                "skipped_split_review_block_count": skipped_block_count,
                "api_accepted_entry_count": len(accepted_entry_indexes),
            }
        )
        runtime_db.store_action_receipt(
            connection,
            action_name="prepare_references_workset",
            stage="stage_5_references",
            metadata=receipt_metadata,
        )
        runtime_db.set_workflow_state(
            connection,
            current_stage="stage_5_references",
            current_substep=raw_next_action,
            stage_gate="ready",
            next_action=raw_next_action,
            status_summary=status_summary,
        )
        connection.commit()


def prepare_reference_workset(db_path: Path) -> tuple[dict[str, Any], int]:
    prepared, code = call_algorithm_handler("_handle_prepare_references_workset", db_path)
    if code != 0 or prepared.get("file_quality_low"):
        return prepared, code
    api_summary = _resolve_reference_api(db_path)
    prepared["reference_api"] = api_summary
    prepared["reference_api_audit_path"] = api_summary["audit_path"]
    prepared["warnings"] = merge_warnings(
        list(prepared.get("warnings", [])),
        _runtime_warnings(db_path),
    )
    _sync_api_aware_split_state(db_path, prepared)
    completion, completion_warnings = _persist_complete_api_resolution(db_path, api_summary)
    if completion is not None:
        prepared.update(completion)
    if completion_warnings:
        prepared["warnings"] = merge_warnings(list(prepared.get("warnings", [])), completion_warnings)
    return prepared, code


def _read_workset_from_prepare_payload(payload: dict[str, Any]) -> dict[str, Any]:
    workset_path = str(payload.get("workset_path", ""))
    return json.loads(Path(workset_path).read_text(encoding="utf-8")) if workset_path else {"entries": []}


def enrich_reference_workset_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("error"):
        db_path = Path(str(payload.get("db_path", ""))).expanduser().resolve()
        workset = _read_workset_from_prepare_payload(payload)
        packages = _reference_packages(_unresolved_reference_workset(db_path, workset))
        split_packages = _split_review_packages(
            workset,
            accepted_entry_indexes=_accepted_reference_entry_indexes(db_path),
        )
        core_agent_work = _reference_core_agent_work(db_path, packages)
        split_review_packages_path = agent_work.write_package_file(
            db_path,
            "reference_core",
            "split_review_packages.json",
            {
                "kind": "reference_split_review_packages",
                "split_review_packages": split_packages,
                "package_count": len(split_packages),
                "instructions": "Use split_reviews[] only when requires_split_review is true. This file is not a subagent batch input.",
            },
        )
        payload.update(
            {
                "runtime_backend": "analysis_runtime.references",
                "allowed_payload_shape": _reference_core_payload_shape(),
                "field_guidance": _reference_core_field_guidance(),
                "reference_core_review_manifest_path": core_agent_work["manifest_path"],
                "reference_core_batch_paths": core_agent_work["batch_paths"],
                "reference_core_package_count": core_agent_work["package_count"],
                "reference_core_batch_count": core_agent_work["batch_count"],
                "reference_core_required_coverage_keys": core_agent_work["required_coverage_keys"],
                "split_review_packages_path": split_review_packages_path,
                "split_review_package_count": len(split_packages),
                "batch_max_items": agent_work.BATCH_MAX_ITEMS,
                "subagent_policy": _reference_core_subagent_policy(),
                "subagent_prompt_template": _reference_core_prompt(),
                "merge_contract": _reference_core_merge_contract(),
            }
        )
    return payload


def _split_review_payload_errors(
    split_reviews: object,
    split_packages: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]], bool]:
    errors: list[str] = []
    if not split_packages:
        if split_reviews not in (None, [], ""):
            errors.append("split_reviews provided but no split_review_packages are active")
        return errors, [], False
    if not isinstance(split_reviews, list) or not split_reviews:
        missing = [str(package["block_key"]) for package in split_packages]
        return [f"missing split_reviews for block_key values: {missing}"], [], False

    packages_by_key = {str(package["block_key"]): package for package in split_packages}
    expected_keys = set(packages_by_key)
    seen: set[str] = set()
    blocks: list[dict[str, Any]] = []
    boundary_changed = False

    for index, review in enumerate(split_reviews):
        if not isinstance(review, dict):
            errors.append(f"split_reviews[{index}] must be object")
            continue
        block_key = str(review.get("block_key", "")).strip()
        if block_key in seen:
            errors.append(f"duplicate block_key: {block_key}")
            continue
        seen.add(block_key)
        package = packages_by_key.get(block_key)
        if package is None:
            errors.append(f"unknown block_key: {block_key}")
            continue

        action = str(review.get("action", "")).strip()
        allowed_actions = list(package.get("allowed_actions", []))
        if action not in allowed_actions:
            errors.append(f"{block_key}.action must be one of {allowed_actions}; got {action!r}")
            continue

        if action == "keep":
            entries = [
                str(item).strip()
                for item in package.get("current_fragments", [])
                if str(item).strip()
            ] or [str(package.get("source_text", "")).strip()]
            resolution = "keep"
        else:
            corrected = review.get("corrected_reference_texts")
            if not isinstance(corrected, list) or not corrected:
                errors.append(f"{block_key}.corrected_reference_texts must be a non-empty string array")
                continue
            entries = [str(item).strip() for item in corrected if str(item).strip()]
            if len(entries) != len(corrected):
                errors.append(f"{block_key}.corrected_reference_texts must not contain empty strings")
                continue
            resolution = "split" if len(entries) > 1 else "merge"
            boundary_changed = True

        blocks.append(
            {
                "block_index": int(package["block_index"]),
                "resolution": resolution,
                "entries": entries,
            }
        )

    missing = sorted(expected_keys - seen)
    if missing:
        errors.append(f"missing split_reviews for block_key values: {missing}")
    return errors, blocks, boundary_changed


def _run_split_reviews(db_path: Path, payload: dict[str, Any]) -> tuple[dict[str, Any], int, bool]:
    prepared, code = prepare_reference_workset(db_path)
    if code != 0:
        return prepared, code, False
    workset = _read_workset_from_prepare_payload(prepared)
    accepted_entry_indexes = _accepted_reference_entry_indexes(db_path)
    split_packages = _split_review_packages(
        workset,
        accepted_entry_indexes=accepted_entry_indexes,
    )
    errors, blocks, boundary_changed = _split_review_payload_errors(payload.get("split_reviews"), split_packages)
    if errors:
        return (
            {
                "error": {
                    "code": "reference_split_review_invalid",
                    "message": "reference split review failed validation",
                    "details": errors,
                },
                "split_review_packages": split_packages,
            },
            2,
            False,
        )
    active_block_indexes = {int(package["block_index"]) for package in split_packages}
    entries_by_index = {
        int(entry["entry_index"]): entry
        for entry in workset.get("entries", [])
    }
    for block in workset.get("suspect_blocks", []):
        block_index = int(block.get("block_index", -1))
        if block_index in active_block_indexes:
            continue
        entry_indexes, _accepted_keys, unresolved_keys = _split_block_coverage(block, accepted_entry_indexes)
        if not entry_indexes or unresolved_keys:
            continue
        retained_entries = [
            str(entries_by_index[entry_index].get("raw", "")).strip()
            for entry_index in entry_indexes
            if entry_index in entries_by_index and str(entries_by_index[entry_index].get("raw", "")).strip()
        ]
        blocks.append(
            {
                "block_index": block_index,
                "resolution": "keep",
                "entries": retained_entries or list(block.get("proposed_entries", [])) or [str(block.get("source_text", ""))],
            }
        )
    blocks.sort(key=lambda block: int(block["block_index"]))
    result, code = call_algorithm_handler(
        "_handle_persist_reference_entry_splits",
        db_path,
        payload={"blocks": blocks},
    )
    if code == 0:
        api_summary = _resolve_reference_api(db_path)
        result["reference_api"] = api_summary
        result["reference_api_audit_path"] = api_summary["audit_path"]
        result["db_path"] = str(db_path)
        result["warnings"] = merge_warnings(
            list(result.get("warnings", [])),
            _runtime_warnings(db_path),
        )
        completion, completion_warnings = _persist_complete_api_resolution(db_path, api_summary)
        if completion is not None:
            result.update(completion)
        else:
            result["next_action"] = "persist_references"
            result = enrich_reference_workset_payload(result)
        if completion_warnings:
            result["warnings"] = merge_warnings(list(result.get("warnings", [])), completion_warnings)
    return result, code, boundary_changed


def _split_review_completed(db_path: Path) -> bool:
    with runtime_db.connect_db(db_path) as connection:
        return "persist_reference_entry_splits" in runtime_db.fetch_action_receipts(connection)


def _ensure_split_review_not_required(db_path: Path) -> tuple[dict[str, Any] | None, int]:
    if _split_review_completed(db_path):
        return None, 0
    prepared, code = prepare_reference_workset(db_path)
    if code != 0:
        return prepared, code
    workset = _read_workset_from_prepare_payload(prepared)
    split_packages = _split_review_packages(
        workset,
        accepted_entry_indexes=_accepted_reference_entry_indexes(db_path),
    )
    if split_packages:
        return (
            {
                "error": {
                    "code": "reference_split_review_required",
                    "message": "reference split review is required before reference_reviews can be persisted",
                    "details": [
                        f"missing split_reviews for block_key values: {[str(package['block_key']) for package in split_packages]}"
                    ],
                },
                "split_review_packages": split_packages,
                "allowed_payload_shape": {
                    "split_reviews": [
                        {
                            "block_key": split_packages[0]["block_key"],
                            "action": "keep or replace_with_corrected_reference_texts",
                            "corrected_reference_texts": ["required for replace_with_corrected_reference_texts"],
                        }
                    ]
                },
            },
            2,
        )
    return None, 0


def _metadata_review_packages(workset: dict[str, Any]) -> list[dict[str, Any]]:
    packages: list[dict[str, Any]] = []
    for row in workset.get("items", []):
        if "ref_index" in row:
            ref_index = int(row["ref_index"])
            reference_key = _reference_key(ref_index)
        else:
            reference_key = str(row.get("reference_key", "")).strip()
            parsed = _entry_index_from_key(reference_key)
            ref_index = int(parsed) if parsed is not None else -1
        packages.append(
            {
                "reference_key": reference_key,
                "locked_reference": dict(row.get("locked_reference", {})),
                "existing_metadata": dict(row.get("existing_metadata", {})),
                "metadata_context_text": str(row.get("metadata_context_text", "")),
                "batch_id": str(row.get("batch_id", f"metadata-batch-{int(row.get('batch_index', 0))}")),
                "status": str(row.get("status", "pending")),
            }
        )
    return packages


def enrich_metadata_workset_payload(payload: dict[str, Any]) -> dict[str, Any]:
    workset_path = str(payload.get("workset_path", ""))
    if payload.get("error") or not workset_path:
        return payload
    db_path = Path(str(payload.get("db_path", ""))).expanduser().resolve()
    workset = json.loads(Path(workset_path).read_text(encoding="utf-8"))
    packages = _metadata_review_packages(workset)
    instructions = dict(workset.get("instructions", {}))
    instructions.setdefault("locked_fields", ["author", "title", "year", "raw", "confidence"])
    instructions.setdefault("allowed_metadata_fields", list(CANONICAL_METADATA_FIELDS))
    metadata_agent_work = _metadata_agent_work(db_path, packages, instructions)
    payload.update(
        {
            "runtime_backend": "analysis_runtime.references",
            "next_action": "persist_references",
            "instructions": instructions,
            "allowed_payload_shape": _metadata_evidence_payload_shape(),
            "field_guidance": {
                "reference_key": "Stable key from metadata evidence batch files; do not use ref_index.",
                "status": "Must be fields_extracted, existing_fields_confirmed, or no_local_evidence.",
                "metadata": "Only allowed when status=fields_extracted. Use only metadata visible in locked_reference, existing_metadata, or metadata_context_text.",
                "evidence_note": "Required evidence note naming the batch JSON field that supports each extracted value.",
                "external_lookup_allowed": "false. Do not use web search, Crossref, arXiv, Google Scholar, Zotero, Semantic Scholar, DOI resolvers, or any external database.",
                "locked_fields": instructions["locked_fields"],
                "allowed_metadata_fields": instructions["allowed_metadata_fields"],
                "batch_inputs": "Read metadata_evidence_batch_paths; stdout does not inline metadata_evidence_packages.",
            },
            "metadata_evidence_review_manifest_path": metadata_agent_work["manifest_path"],
            "metadata_evidence_batch_paths": metadata_agent_work["batch_paths"],
            "metadata_evidence_package_count": metadata_agent_work["package_count"],
            "metadata_evidence_batch_count": metadata_agent_work["batch_count"],
            "metadata_evidence_required_coverage_keys": metadata_agent_work["required_coverage_keys"],
            "batch_max_items": agent_work.BATCH_MAX_ITEMS,
            "subagent_policy": _metadata_subagent_policy(),
            "subagent_prompt_template": _metadata_prompt(),
            "merge_contract": _metadata_merge_contract(metadata_agent_work["required_coverage_keys"]),
            "evidence_policy": _metadata_evidence_policy(),
            "external_lookup_allowed": False,
        }
    )
    return payload


def prepare_reference_metadata_enrichment(db_path: Path) -> tuple[dict[str, Any], int]:
    prepared, code = call_algorithm_handler("_handle_prepare_reference_metadata_enrichment", db_path)
    if code == 0:
        prepared.update(
            {
                "db_path": str(db_path),
                "next_action": "persist_citation_analysis" if prepared.get("skipped") else "persist_references",
            }
        )
        if not prepared.get("skipped"):
            prepared = enrich_metadata_workset_payload(prepared)
    return prepared, code


def _stringify_evidence(value: object) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value or "")


def _metadata_evidence_text(package: dict[str, Any]) -> str:
    return "\n".join(
        [
            _stringify_evidence(package.get("locked_reference")),
            _stringify_evidence(package.get("existing_metadata")),
            _stringify_evidence(package.get("metadata_context_text")),
        ]
    )


def _compact_evidence_text(text: str) -> str:
    return re.sub(r"[\s{}()\[\]<>\"'`.,;:/\\_-]+", "", text.casefold())


def _metadata_value_supported_by_local_evidence(key: str, value: object, evidence_text: str) -> bool:
    if key not in EVIDENCE_MATCHED_METADATA_FIELDS:
        return True
    if isinstance(value, list):
        return all(_metadata_value_supported_by_local_evidence(key, item, evidence_text) for item in value if item)
    text = str(value or "").strip()
    if not text:
        return True
    evidence = evidence_text.casefold()
    text_cf = text.casefold()
    if text_cf in evidence:
        return True
    compact_evidence = _compact_evidence_text(evidence_text)
    compact_value = _compact_evidence_text(text)
    if compact_value and compact_value in compact_evidence:
        return True
    if key == "archiveID" and text_cf.startswith("arxiv:"):
        bare = text_cf.removeprefix("arxiv:").strip()
        return bare in evidence or _compact_evidence_text(bare) in compact_evidence
    return False


def _metadata_local_evidence_errors(reference_key: str, metadata: dict[str, Any], package: dict[str, Any]) -> list[str]:
    evidence_text = _metadata_evidence_text(package)
    errors: list[str] = []
    for key, value in metadata.items():
        if not _metadata_value_supported_by_local_evidence(key, value, evidence_text):
            errors.append(
                f"{reference_key}.metadata.{key} has no local evidence in locked_reference, existing_metadata, or metadata_context_text"
            )
    return errors


def _metadata_payload_errors(payload: dict[str, Any], workset: dict[str, Any]) -> tuple[list[str], dict[str, Any], list[str]]:
    errors: list[str] = []
    if "reference_reviews" in payload:
        errors.append("metadata submit must not include reference_reviews")
    forbidden_top = sorted(key for key in REFERENCE_FORBIDDEN_FIELDS if key in payload)
    if forbidden_top:
        errors.append(f"forbidden top-level keys for current metadata payload: {forbidden_top}")
    if "metadata_reviews" in payload:
        errors.append("metadata_reviews[] is not accepted; use metadata_evidence_reviews[] for Reference Metadata Evidence Review")
    reviews = payload.get("metadata_evidence_reviews")
    if not isinstance(reviews, list):
        return [*errors, "metadata_evidence_reviews must be an array"], {"items": []}, []

    packages = _metadata_review_packages(workset)
    packages_by_key = {str(package["reference_key"]): package for package in packages}
    expected_keys = set(packages_by_key)
    seen: set[str] = set()
    internal_items: list[dict[str, Any]] = []
    warnings: list[str] = []

    for index, review in enumerate(reviews):
        if not isinstance(review, dict):
            errors.append(f"metadata_evidence_reviews[{index}] must be object")
            continue
        forbidden_fields = sorted(field for field in METADATA_REVIEW_FORBIDDEN_FIELDS if field in review)
        if forbidden_fields:
            errors.append(f"{review.get('reference_key', f'metadata_evidence_reviews[{index}')} attempts to modify locked/internal fields: {forbidden_fields}")
        reference_key = str(review.get("reference_key", "")).strip()
        if reference_key in seen:
            errors.append(f"duplicate reference_key: {reference_key}")
            continue
        seen.add(reference_key)
        package = packages_by_key.get(reference_key)
        if package is None:
            errors.append(f"unknown reference_key: {reference_key}")
            continue

        status = str(review.get("status", "")).strip()
        if status not in METADATA_EVIDENCE_STATUSES:
            errors.append(f"{reference_key}.status must be one of {sorted(METADATA_EVIDENCE_STATUSES)}")
            continue
        metadata, metadata_warnings = normalize_reference_metadata(review.get("metadata", {}), context=reference_key)
        warnings = merge_warnings(warnings, metadata_warnings)
        evidence_note = str(review.get("evidence_note") or review.get("reason") or "").strip()
        ref_index = _entry_index_from_key(reference_key)
        if ref_index is None:
            errors.append(f"{reference_key}.reference_key is invalid")
            continue

        if status == "fields_extracted":
            if not metadata:
                errors.append(f"{reference_key}.metadata must contain at least one allowed field when status=fields_extracted")
                continue
            evidence_errors = _metadata_local_evidence_errors(reference_key, metadata, package)
            if evidence_errors:
                errors.extend([f"metadata_without_local_evidence: {error}" for error in evidence_errors])
                continue
            internal_items.append({"ref_index": ref_index, "status": INTERNAL_METADATA_STATUS[status], "metadata": metadata, "evidence_note": evidence_note})
        else:
            if metadata:
                errors.append(f"{reference_key}.metadata is only allowed when status=fields_extracted")
                continue
            reason = evidence_note or ("existing metadata confirmed" if status == "existing_fields_confirmed" else "no local metadata evidence")
            internal_items.append({"ref_index": ref_index, "status": INTERNAL_METADATA_STATUS[status], "reason": reason, "evidence_note": evidence_note})

    missing = sorted(expected_keys - seen)
    if missing:
        errors.append(f"missing metadata_evidence_reviews for reference_key values: {missing}")
    return errors, {"items": internal_items}, warnings


def persist_reference_metadata_reviews(db_path: Path, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    prepared, prepare_code = prepare_reference_metadata_enrichment(db_path)
    if prepare_code != 0:
        return prepared, prepare_code
    workset_path = str(prepared.get("workset_path", ""))
    workset = json.loads(Path(workset_path).read_text(encoding="utf-8")) if workset_path else {"items": []}
    errors, internal_payload, normalization_warnings = _metadata_payload_errors(payload, workset)
    if errors:
        return {
            "error": {
                "code": "reference_metadata_payload_invalid",
                "message": "reference metadata evidence payload failed validation",
                "details": errors,
            },
            "metadata_evidence_review_manifest_path": prepared.get("metadata_evidence_review_manifest_path"),
            "metadata_evidence_batch_paths": prepared.get("metadata_evidence_batch_paths", []),
            "instructions": prepared.get("instructions", {}),
            "evidence_policy": prepared.get("evidence_policy", {}),
            "warnings": normalization_warnings,
        }, 2
    persisted, code = call_algorithm_handler(
        "_handle_persist_reference_metadata_enrichment",
        db_path,
        payload=internal_payload,
    )
    all_warnings = merge_warnings(
        normalization_warnings,
        list(persisted.get("warnings", [])) if isinstance(persisted.get("warnings"), list) else [],
    )
    _persist_runtime_warnings(db_path, all_warnings)
    return {
        "metadata_evidence_review": {"prepared": prepared, "persisted": persisted},
        "warnings": all_warnings,
        "db_path": str(db_path),
        "runtime_backend": "analysis_runtime.references",
        "next_action": "persist_citation_analysis" if code == 0 else "persist_references",
        "error": persisted.get("error"),
    }, code


def _reference_payload_errors(payload: dict[str, Any], workset: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    normalization_warnings: list[str] = []
    forbidden = sorted(key for key in REFERENCE_FORBIDDEN_FIELDS if key in payload)
    if forbidden:
        errors.append(f"forbidden top-level keys for current reference payload: {forbidden}")
    reviews = payload.get("reference_reviews")
    if not isinstance(reviews, list):
        return [*errors, "reference_reviews must be an array"], [], []

    entries_by_key = {_reference_key(int(entry["entry_index"])): entry for entry in workset.get("entries", [])}
    expected_keys = set(entries_by_key)
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, review in enumerate(reviews):
        if not isinstance(review, dict):
            errors.append(f"reference_reviews[{index}] must be object")
            continue
        forbidden_review = sorted(key for key in REFERENCE_REVIEW_FORBIDDEN_FIELDS if key in review)
        if forbidden_review:
            errors.append(f"{review.get('reference_key', f'reference_reviews[{index}')} contains forbidden fields: {forbidden_review}")
            if "metadata" in forbidden_review:
                errors.append(f"{review.get('reference_key', f'reference_reviews[{index}')} metadata must be submitted through metadata_evidence_reviews after metadata_evidence_packages are returned")
        reference_key = str(review.get("reference_key", "")).strip()
        if reference_key in seen:
            errors.append(f"duplicate reference_key: {reference_key}")
            continue
        seen.add(reference_key)
        entry = entries_by_key.get(reference_key)
        if entry is None:
            errors.append(f"unknown reference_key: {reference_key}")
            continue
        selected = str(review.get("selected_parse_pattern", "")).strip()
        allowed = _pattern_names(entry)
        if selected not in allowed:
            errors.append(f"{reference_key}.selected_parse_pattern must be one of {allowed}; got {selected!r}")
        authors = review.get("authors")
        if not isinstance(authors, list) or not all(isinstance(item, str) and item.strip() for item in authors):
            errors.append(f"{reference_key}.authors must be a non-empty string array")
        title = review.get("title")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"{reference_key}.title must be non-empty string")
        year = review.get("publication_year")
        if year is not None and not isinstance(year, int):
            errors.append(f"{reference_key}.publication_year must be integer or null")
        if selected in _candidate_by_pattern(entry):
            candidate = _candidate_by_pattern(entry)[selected]
            normalized.append(
                {
                    "entry_index": int(entry["entry_index"]),
                    "selected_pattern": selected,
                    "author": authors if isinstance(authors, list) else [],
                    "title": title.strip() if isinstance(title, str) else "",
                    "year": year,
                    "raw": str(entry.get("raw", "")),
                    "confidence": candidate.get("confidence", 0.9),
                    "metadata": {},
                }
            )
    missing = sorted(expected_keys - seen)
    if missing:
        errors.append(f"missing reference_reviews for reference_key values: {missing}")
    return errors, normalized, normalization_warnings


def _persist_runtime_warnings(db_path: Path, warnings: list[str]) -> None:
    if not warnings:
        return
    with runtime_db.connect_db(db_path) as connection:
        for warning in warnings:
            runtime_db.add_runtime_warning_once(connection, warning)


def persist_references(db_path: Path, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    if "metadata_reviews" in payload:
        return {
            "error": {
                "code": "reference_metadata_payload_invalid",
                "message": "metadata_reviews[] is not accepted in the current Reference Metadata Evidence Review contract",
                "details": ["Use metadata_evidence_reviews[] with status fields_extracted, existing_fields_confirmed, or no_local_evidence."],
            }
        }, 2
    if "reference_reviews" in payload and "metadata_evidence_reviews" in payload:
        return {
            "error": {
                "code": "reference_payload_invalid",
                "message": "reference payload failed validation",
                "details": ["reference_reviews and metadata_evidence_reviews must be submitted in separate persist_references rounds"],
            }
        }, 2
    if "metadata_evidence_reviews" in payload:
        return persist_reference_metadata_reviews(db_path, payload)

    if "split_reviews" in payload:
        split_result, split_code, boundary_changed = _run_split_reviews(db_path, payload)
        if split_code != 0:
            return split_result, split_code
        if boundary_changed or "reference_reviews" not in payload:
            split_result.setdefault("next_action", "persist_references")
            split_result["reference_reviews_ignored"] = bool(boundary_changed and payload.get("reference_reviews"))
            return split_result, split_code
    else:
        split_required, split_code = _ensure_split_review_not_required(db_path)
        if split_required is not None:
            return split_required, split_code

    workset = _unresolved_reference_workset(db_path)
    errors, normalized_items, normalization_warnings = _reference_payload_errors(payload, workset)
    if errors:
        return {
            "error": {
                "code": "reference_payload_invalid",
                "message": "reference payload failed validation",
                "details": errors,
            },
            "allowed_parse_patterns_by_reference_key": {
                pkg["reference_key"]: pkg["allowed_parse_patterns"]
                for pkg in _reference_packages(workset)
            },
            "warnings": normalization_warnings,
        }, 2
    with runtime_db.connect_db(db_path) as connection:
        api_items = [
            dict(item["item"])
            for item in runtime_db.fetch_reference_api_resolutions(connection)
            if item.get("status") == "accepted" and isinstance(item.get("item"), dict)
        ]
    reference_payload = {
        "items": sorted(
            [*_algorithm_items_from_api_items(api_items), *normalized_items],
            key=lambda item: int(item["entry_index"]),
        )
    }
    result, code = call_algorithm_handler("_handle_persist_references", db_path, payload=reference_payload)
    if code != 0:
        return result, code
    metadata_workset, metadata_code = prepare_reference_metadata_enrichment(db_path)
    all_warnings = merge_warnings(
        normalization_warnings,
        list(result.get("warnings", [])) if isinstance(result.get("warnings"), list) else [],
        list(metadata_workset.get("warnings", [])) if isinstance(metadata_workset.get("warnings"), list) else [],
    )
    _persist_runtime_warnings(db_path, all_warnings)
    if metadata_code != 0:
        return {
            **result,
            "metadata_evidence_review": {
                "workset_path": metadata_workset.get("workset_path", ""),
                "item_count": metadata_workset.get("item_count", metadata_workset.get("metadata_evidence_package_count", 0)),
                "batch_count": metadata_workset.get("metadata_evidence_batch_count", 0),
            },
            "warnings": all_warnings,
            "error": metadata_workset.get("error"),
        }, metadata_code
    return (
        {
            **result,
            "metadata_evidence_review": {
                "workset_path": metadata_workset.get("workset_path", ""),
                "item_count": metadata_workset.get("item_count", metadata_workset.get("metadata_evidence_package_count", 0)),
                "batch_count": metadata_workset.get("metadata_evidence_batch_count", 0),
            },
            "metadata_evidence_review_manifest_path": metadata_workset.get("metadata_evidence_review_manifest_path"),
            "metadata_evidence_batch_paths": metadata_workset.get("metadata_evidence_batch_paths", []),
            "metadata_evidence_package_count": metadata_workset.get("metadata_evidence_package_count", 0),
            "metadata_evidence_batch_count": metadata_workset.get("metadata_evidence_batch_count", 0),
            "metadata_evidence_required_coverage_keys": metadata_workset.get("metadata_evidence_required_coverage_keys", []),
            "instructions": metadata_workset.get("instructions", {}),
            "allowed_payload_shape": metadata_workset.get("allowed_payload_shape"),
            "field_guidance": metadata_workset.get("field_guidance"),
            "subagent_policy": metadata_workset.get("subagent_policy"),
            "subagent_prompt_template": metadata_workset.get("subagent_prompt_template"),
            "merge_contract": metadata_workset.get("merge_contract"),
            "evidence_policy": metadata_workset.get("evidence_policy"),
            "external_lookup_allowed": metadata_workset.get("external_lookup_allowed"),
            "batch_max_items": metadata_workset.get("batch_max_items", agent_work.BATCH_MAX_ITEMS),
            "warnings": all_warnings,
            "db_path": str(db_path),
            "runtime_backend": "analysis_runtime.references",
            "next_action": "persist_references",
            "error": None,
        },
        0,
    )

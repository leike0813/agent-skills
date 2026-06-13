from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .algorithm_adapter import call_algorithm_handler
from . import runtime_db
from .payload_normalization import CANONICAL_METADATA_FIELDS, merge_warnings, normalize_reference_metadata


REFERENCE_FORBIDDEN_FIELDS = ["items", "selected_pattern", "ref_index", "raw", "confidence", "metadata_enrichment_items"]
REFERENCE_REVIEW_FORBIDDEN_FIELDS = ["raw", "confidence", "ref_index", "selected_pattern", "metadata"]
METADATA_REVIEW_STATUSES = {"enriched", "confirmed_existing", "no_metadata_found"}
METADATA_REVIEW_FORBIDDEN_FIELDS = ["author", "authors", "title", "year", "raw", "raw_reference", "reference", "confidence", "ref_index"]


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
                        "Rich metadata is reviewed in the next metadata_review_packages round."
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
                        "Rich metadata is reviewed in the next metadata_review_packages round."
                    ),
                }
            )
    return batches


def _split_review_packages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    packages: list[dict[str, Any]] = []
    for block in payload.get("suspect_blocks", []):
        block_index = int(block.get("block_index", len(packages)))
        packages.append(
            {
                "block_key": f"block-{block_index}",
                "block_index": block_index,
                "source_text": str(block.get("source_text", "")),
                "current_fragments": list(block.get("proposed_entries", [])),
                "allowed_actions": ["keep", "replace_with_corrected_reference_texts"],
            }
        )
    return packages


def prepare_reference_workset(db_path: Path) -> tuple[dict[str, Any], int]:
    return call_algorithm_handler("_handle_prepare_references_workset", db_path)


def _read_workset_from_prepare_payload(payload: dict[str, Any]) -> dict[str, Any]:
    workset_path = str(payload.get("workset_path", ""))
    return json.loads(Path(workset_path).read_text(encoding="utf-8")) if workset_path else {"entries": []}


def enrich_reference_workset_payload(payload: dict[str, Any]) -> dict[str, Any]:
    workset_path = str(payload.get("workset_path", ""))
    review_path = str(payload.get("review_path", ""))
    if not payload.get("error"):
        workset = _read_workset_from_prepare_payload(payload)
        packages = _reference_packages(workset)
        payload.update(
            {
                "runtime_backend": "analysis_runtime.references",
                "allowed_payload_shape": {
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
                    "note": "Submit metadata_reviews only after runtime returns metadata_review_packages.",
                },
                "field_guidance": {
                    "reference_key": "Stable work key from reference_review_packages; do not use ref_index.",
                    "selected_parse_pattern": "Required parse hypothesis. Must be one of allowed_parse_patterns for the same reference_key.",
                    "authors": "Array of author strings in source order.",
                    "title": "Title in original language/script.",
                    "publication_year": "Integer year or null if not supported by source text.",
                    "metadata": "Do not submit metadata in reference_reviews. Runtime returns metadata_review_packages after core references are stored.",
                },
                "reference_review_packages": packages,
                "allowed_parse_patterns_by_reference_key": {
                    pkg["reference_key"]: pkg["allowed_parse_patterns"]
                    for pkg in packages
                },
                "split_review_packages": _split_review_packages(workset),
                "batch_work_packages": _batch_packages(workset, packages),
                "subagent_policy": "Default to delegating reference core review by batch when batch_work_packages exist and subagents are available. Skip only when subagents are unavailable, the batch is trivially small, or context cannot be split; record the reason. Metadata review happens in the next returned work packages. Subagents draft only; main agent is the single DB writer and payload submitter.",
                "subagent_prompt_template": (
                    "You are reviewing one reference batch for literature-analysis. "
                    "Use only the provided reference_review_packages. Return JSON with reference_reviews[]; "
                    "each review must include reference_key, selected_parse_pattern, authors, title, publication_year, and review_notes. "
                    "Keep reference_key unchanged. Do not include metadata, raw, confidence, ref_index, selected_pattern, database fields, renderer fields, or entries outside this batch. "
                    "Do not write DB, run runtime commands, submit payloads, or generate final artifacts."
                ),
                "merge_contract": {
                    "single_writer": "main_agent",
                    "required_payload_keys": ["reference_reviews"],
                    "optional_payload_keys": ["split_reviews"],
                    "forbidden_submit_keys": REFERENCE_FORBIDDEN_FIELDS,
                    "merge_notes": "Subagents return core batch drafts only. Main agent is the single DB writer, keeps stable keys unchanged, combines arrays, resolves duplicate keys, and submits one core payload. Metadata is submitted in the next round.",
                },
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
    split_packages = _split_review_packages(workset)
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
    result, code = call_algorithm_handler(
        "_handle_persist_reference_entry_splits",
        db_path,
        payload={"blocks": blocks},
    )
    if code == 0:
        result.update({"db_path": str(db_path), "next_action": "persist_references"})
        result = enrich_reference_workset_payload(result)
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
    split_packages = _split_review_packages(workset)
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


def _metadata_batch_packages(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_batch: dict[str, list[str]] = {}
    for package in packages:
        by_batch.setdefault(str(package["batch_id"]), []).append(str(package["reference_key"]))
    batches: list[dict[str, Any]] = []
    for batch_id, reference_keys in sorted(by_batch.items()):
        batches.append(
            {
                "batch_id": batch_id,
                "reference_keys": reference_keys,
                "required_return_shape": {
                    "metadata_reviews": [
                        {
                            "reference_key": "copy from this batch",
                            "status": "enriched | confirmed_existing | no_metadata_found",
                            "metadata": {},
                            "evidence_note": "brief source/context evidence",
                        }
                    ]
                },
                "canonical_metadata_fields": list(CANONICAL_METADATA_FIELDS),
                "forbidden_fields": METADATA_REVIEW_FORBIDDEN_FIELDS,
                "allowed_enum_values": {"status": sorted(METADATA_REVIEW_STATUSES)},
                "minimal_valid_example": {
                    "metadata_reviews": [
                        {
                            "reference_key": reference_keys[0] if reference_keys else "reference-0",
                            "status": "no_metadata_found",
                            "evidence_note": "No additional metadata is supported by metadata_context_text.",
                        }
                    ]
                },
                "merge_notes": "Default to delegating this metadata batch when subagents are available. Subagent drafts only this metadata batch. Main agent is the single DB writer, keeps reference_key unchanged, merges all metadata_reviews[], and submits once.",
                "subagent_prompt": (
                    "Review metadata for this literature-analysis batch. Return JSON with metadata_reviews[] only. "
                    "Use reference_key as the key. Do not modify locked fields or include ref_index. "
                    f"Allowed metadata fields: {', '.join(CANONICAL_METADATA_FIELDS)}. "
                    "Do not write DB, run runtime commands, submit payloads, modify stable keys, or generate final artifacts."
                ),
            }
        )
    return batches


def enrich_metadata_workset_payload(payload: dict[str, Any]) -> dict[str, Any]:
    workset_path = str(payload.get("workset_path", ""))
    if payload.get("error") or not workset_path:
        return payload
    workset = json.loads(Path(workset_path).read_text(encoding="utf-8"))
    packages = _metadata_review_packages(workset)
    instructions = dict(workset.get("instructions", {}))
    instructions.setdefault("locked_fields", ["author", "title", "year", "raw", "confidence"])
    instructions.setdefault("allowed_metadata_fields", list(CANONICAL_METADATA_FIELDS))
    payload.update(
        {
            "runtime_backend": "analysis_runtime.references",
            "next_action": "persist_references",
            "instructions": instructions,
            "allowed_payload_shape": {
                "metadata_reviews": [
                    {
                        "reference_key": "reference-0",
                        "status": "enriched | confirmed_existing | no_metadata_found",
                        "metadata": {},
                        "evidence_note": "required evidence or reason",
                    }
                ]
            },
            "field_guidance": {
                "reference_key": "Stable key from metadata_review_packages; do not use ref_index.",
                "status": "Must be enriched, confirmed_existing, or no_metadata_found.",
                "metadata": "Only allowed when status=enriched. Use canonical metadata fields; deterministic aliases are normalized with warnings.",
                "locked_fields": instructions["locked_fields"],
                "allowed_metadata_fields": instructions["allowed_metadata_fields"],
            },
            "metadata_review_packages": packages,
            "batch_work_packages": _metadata_batch_packages(packages),
            "subagent_policy": "Default to delegating metadata review by batch when batch_work_packages exist and subagents are available. Skip only when subagents are unavailable, the batch is trivially small, or context cannot be split; record the reason. Subagents draft only; main agent is the single DB writer and submits one final metadata_reviews[] payload.",
            "subagent_prompt_template": (
                "You are enriching one literature-analysis metadata batch. "
                "Return JSON with metadata_reviews[] only. Use reference_key as the key. "
                "Status must be enriched, confirmed_existing, or no_metadata_found. "
                f"Allowed metadata fields: {', '.join(CANONICAL_METADATA_FIELDS)}. "
                "Do not modify locked reference fields, stable keys, selected_parse_pattern, raw text, confidence, or include ref_index. "
                "Do not write DB, run runtime commands, submit payloads, or generate final artifacts."
            ),
            "merge_contract": {
                "single_writer": "main_agent",
                "required_payload_keys": ["metadata_reviews"],
                "forbidden_submit_keys": ["reference_reviews", *REFERENCE_FORBIDDEN_FIELDS],
                "required_coverage": [package["reference_key"] for package in packages],
                "merge_notes": "Subagents return metadata batch drafts only. Main agent is the single DB writer and must submit exactly one metadata review per metadata_review_packages item.",
            },
        }
    )
    return payload


def prepare_reference_metadata_enrichment(db_path: Path) -> tuple[dict[str, Any], int]:
    prepared, code = call_algorithm_handler("_handle_prepare_reference_metadata_enrichment", db_path)
    if code == 0:
        prepared.update({"db_path": str(db_path), "next_action": "persist_references"})
        prepared = enrich_metadata_workset_payload(prepared)
    return prepared, code


def _metadata_payload_errors(payload: dict[str, Any], workset: dict[str, Any]) -> tuple[list[str], dict[str, Any], list[str]]:
    errors: list[str] = []
    if "reference_reviews" in payload:
        errors.append("metadata submit must not include reference_reviews")
    forbidden_top = sorted(key for key in REFERENCE_FORBIDDEN_FIELDS if key in payload)
    if forbidden_top:
        errors.append(f"forbidden top-level keys for current metadata payload: {forbidden_top}")
    reviews = payload.get("metadata_reviews")
    if not isinstance(reviews, list):
        return [*errors, "metadata_reviews must be an array"], {"items": []}, []

    packages = _metadata_review_packages(workset)
    packages_by_key = {str(package["reference_key"]): package for package in packages}
    expected_keys = set(packages_by_key)
    seen: set[str] = set()
    internal_items: list[dict[str, Any]] = []
    warnings: list[str] = []

    for index, review in enumerate(reviews):
        if not isinstance(review, dict):
            errors.append(f"metadata_reviews[{index}] must be object")
            continue
        forbidden_fields = sorted(field for field in METADATA_REVIEW_FORBIDDEN_FIELDS if field in review)
        if forbidden_fields:
            errors.append(f"{review.get('reference_key', f'metadata_reviews[{index}')} attempts to modify locked/internal fields: {forbidden_fields}")
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
        if status not in METADATA_REVIEW_STATUSES:
            errors.append(f"{reference_key}.status must be one of {sorted(METADATA_REVIEW_STATUSES)}")
            continue
        metadata, metadata_warnings = normalize_reference_metadata(review.get("metadata", {}), context=reference_key)
        warnings = merge_warnings(warnings, metadata_warnings)
        evidence_note = str(review.get("evidence_note") or review.get("reason") or "").strip()
        ref_index = _entry_index_from_key(reference_key)
        if ref_index is None:
            errors.append(f"{reference_key}.reference_key is invalid")
            continue

        if status == "enriched":
            if not metadata:
                errors.append(f"{reference_key}.metadata must contain at least one allowed field when status=enriched")
                continue
            internal_items.append({"ref_index": ref_index, "status": status, "metadata": metadata, "evidence_note": evidence_note})
        else:
            if metadata:
                errors.append(f"{reference_key}.metadata is only allowed when status=enriched")
                continue
            reason = evidence_note or ("existing metadata confirmed" if status == "confirmed_existing" else "no additional metadata found")
            internal_items.append({"ref_index": ref_index, "status": status, "reason": reason, "evidence_note": evidence_note})

    missing = sorted(expected_keys - seen)
    if missing:
        errors.append(f"missing metadata_reviews for reference_key values: {missing}")
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
                "message": "reference metadata payload failed validation",
                "details": errors,
            },
            "metadata_review_packages": prepared.get("metadata_review_packages", []),
            "instructions": prepared.get("instructions", {}),
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
        "metadata_enrichment": {"prepared": prepared, "persisted": persisted},
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
                errors.append(f"{review.get('reference_key', f'reference_reviews[{index}')} metadata must be submitted through metadata_reviews after metadata_review_packages are returned")
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
    if "reference_reviews" in payload and "metadata_reviews" in payload:
        return {
            "error": {
                "code": "reference_payload_invalid",
                "message": "reference payload failed validation",
                "details": ["reference_reviews and metadata_reviews must be submitted in separate persist_references rounds"],
            }
        }, 2
    if "metadata_reviews" in payload:
        return persist_reference_metadata_reviews(db_path, payload)

    if "split_reviews" in payload:
        split_result, split_code, boundary_changed = _run_split_reviews(db_path, payload)
        if split_code != 0:
            return split_result, split_code
        if boundary_changed or "reference_reviews" not in payload:
            split_result["next_action"] = "persist_references"
            split_result["reference_reviews_ignored"] = bool(boundary_changed and payload.get("reference_reviews"))
            return split_result, split_code
    else:
        split_required, split_code = _ensure_split_review_not_required(db_path)
        if split_required is not None:
            return split_required, split_code

    workset = _load_reference_workset_from_db(db_path)
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
    reference_payload = {"items": normalized_items}
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
        return {**result, "metadata_enrichment": metadata_workset, "warnings": all_warnings, "error": metadata_workset.get("error")}, metadata_code
    return (
        {
            **result,
            "metadata_enrichment": metadata_workset,
            "metadata_review_packages": metadata_workset.get("metadata_review_packages", []),
            "instructions": metadata_workset.get("instructions", {}),
            "allowed_payload_shape": metadata_workset.get("allowed_payload_shape"),
            "field_guidance": metadata_workset.get("field_guidance"),
            "batch_work_packages": metadata_workset.get("batch_work_packages", []),
            "subagent_policy": metadata_workset.get("subagent_policy"),
            "subagent_prompt_template": metadata_workset.get("subagent_prompt_template"),
            "merge_contract": metadata_workset.get("merge_contract"),
            "warnings": all_warnings,
            "db_path": str(db_path),
            "runtime_backend": "analysis_runtime.references",
            "next_action": "persist_references",
            "error": None,
        },
        0,
    )

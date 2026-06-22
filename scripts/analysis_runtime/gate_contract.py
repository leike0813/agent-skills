from __future__ import annotations

from pathlib import Path
from typing import Any

from . import runtime_db
from .payload_normalization import CANONICAL_METADATA_FIELDS


INSTRUCTION_REF_BY_ACTION = {
    "init_runtime": "references/source_and_plan.md",
    "persist_analysis_plan": "references/source_and_plan.md",
    "persist_digest": "references/digest_generation.md",
    "persist_references": "references/reference_extraction.md",
    "persist_citation_analysis": "references/citation_analysis.md",
    "finalize_outputs": "references/finalization_and_recovery.md",
}


def _local_next_action(raw_next_action: str) -> str:
    mapping = {
        "confirm_runtime_paths": "init_runtime",
        "bootstrap_runtime_db": "init_runtime",
        "persist_render_templates": "init_runtime",
        "normalize_source": "init_runtime",
        "persist_outline_and_scopes": "persist_analysis_plan",
        "persist_digest": "persist_digest",
        "prepare_references_workset": "persist_references",
        "persist_reference_entry_splits": "persist_references",
        "decide_reference_extraction": "persist_references",
        "persist_references": "persist_references",
        "review_reference_quality": "persist_references",
        "prepare_reference_metadata_enrichment": "persist_references",
        "persist_reference_metadata_enrichment": "persist_references",
        "prepare_citation_workset": "persist_citation_analysis",
        "persist_citation_semantics": "persist_citation_analysis",
        "persist_citation_timeline": "persist_citation_analysis",
        "persist_citation_summary": "persist_citation_analysis",
        "render_and_validate": "finalize_outputs",
    }
    return mapping.get(raw_next_action or "", raw_next_action or "init_runtime")


def _execution_note(next_action: str) -> str:
    notes = {
        "init_runtime": "Initialize runtime paths, templates, DB state, source hash, and normalized source.",
        "persist_analysis_plan": "Persist outline_nodes, references_scope, citation_scope, and literature_matching_metadata in one structured payload.",
        "persist_digest": "Persist structured digest_slots, section_summaries, and optional representative_image only.",
        "persist_references": "Prepare references, delegate using returned reference core and metadata evidence batch paths, submit core reference_reviews first, then submit metadata_evidence_reviews; keep one main-agent writer.",
        "persist_citation_analysis": "Prepare or persist citation semantics, timeline, summary, and basis from DB-backed citation workset items.",
        "finalize_outputs": "Render public artifacts from DB state and runtime templates; do not submit business payload.",
    }
    return notes.get(next_action, "Inspect status and continue with the local literature-analysis command sequence.")


def _instruction_refs(next_action: str) -> list[dict[str, str]]:
    path = INSTRUCTION_REF_BY_ACTION.get(next_action, "references/finalization_and_recovery.md")
    return [{"path": path, "section": next_action}]


def _allowed_payload_shape(next_action: str) -> dict[str, Any] | None:
    if next_action == "persist_references":
        return {
            "core_submit": {
                "reference_reviews": [
                    {
                        "reference_key": "reference-0",
                        "selected_parse_pattern": "one allowed parse pattern",
                        "authors": ["Author"],
                        "title": "Original title",
                        "publication_year": 2024,
                        "review_notes": "optional",
                    }
                ]
            },
            "metadata_evidence_submit": {
                "metadata_evidence_reviews": [
                    {
                        "reference_key": "reference-0",
                        "status": "fields_extracted",
                        "metadata": {"publicationTitle": "Venue or container"},
                        "evidence_note": "value appears in metadata_context_text",
                    }
                ]
            },
            "split_repair": {
                "split_reviews": [
                    {"block_key": "block-0", "action": "replace_with_corrected_reference_texts", "corrected_reference_texts": ["..."]}
                ]
            },
        }
    if next_action == "persist_citation_analysis":
        return {
            "citation_semantic_reviews": [
                {
                    "citation_work_key": "citation-work-0",
                    "topic": "topic in current scope",
                    "usage": "how the source uses this citation",
                    "role_in_context": "natural language role",
                    "keywords": ["keyword"],
                    "summary": "citation role summary",
                    "key_reference_reason": "optional",
                }
            ],
            "timeline_summaries": {"early": "...", "middle": "...", "recent": "..."},
            "summary": "global citation analysis summary",
        }
    return None


def _field_guidance(next_action: str) -> dict[str, str] | None:
    if next_action == "persist_references":
        return {
            "reference_key": "Stable key from reference_core_batch_paths files.",
            "selected_parse_pattern": "Required parse hypothesis; use only allowed_parse_patterns from the assigned reference core batch file.",
            "core_submit": "Submit reference_reviews[] first. Do not include metadata in reference_reviews.",
            "metadata_evidence_submit": "After core submit returns metadata_evidence_batch_paths, submit metadata_evidence_reviews[] covering every package in those batch files.",
            "metadata_evidence_status": "metadata_evidence_reviews[].status must be fields_extracted, existing_fields_confirmed, or no_local_evidence.",
            "canonical_metadata_fields": ", ".join(CANONICAL_METADATA_FIELDS),
            "forbidden_fields": "Do not submit items, selected_pattern, ref_index, raw, confidence, metadata evidence workset internals, or reference_reviews[].metadata.",
            "evidence_policy": "Reference Metadata Evidence Review is not metadata discovery. external_lookup_allowed=false; do not use web search, Crossref, arXiv, Google Scholar, Zotero, Semantic Scholar, DOI resolvers, or external databases.",
            "subagents": "Default to subagent delegation when reference_core_batch_paths or metadata_evidence_batch_paths exist and subagents are available. Runtime owns batch splitting; pass each batch JSON file path directly to a subagent. Subagents draft only from local batch evidence; main agent is the single DB writer, keeps stable keys unchanged, merges one payload per submit round, and records a reason if delegation is skipped.",
        }
    if next_action == "persist_citation_analysis":
        return {
            "citation_work_key": "Stable key from citation_batch_paths files.",
            "source_reference_number": "Original reference number for orientation only.",
            "role_in_context": "Natural language role; runtime maps it to internal renderer categories.",
            "timeline_summaries": "Narrative summaries only; runtime derives bucket membership from dated references. Undated references may warn but do not require manual bucket membership.",
            "forbidden_fields": "Do not submit items, timeline, basis, ref_index, function, mentions, or timeline ref indexes.",
            "subagents": "Default to subagent delegation when citation_batch_paths exist and subagents are available. Runtime owns batch splitting; pass each batch JSON file path directly to a subagent. Subagents draft only; main agent is the single DB writer, keeps citation_work_key unchanged, merges reviews, and writes global timeline_summaries/summary.",
        }
    return None


def _missing_prerequisites(connection: Any, next_action: str) -> list[str]:
    missing: list[str] = []
    source_doc = runtime_db.fetch_source_document(connection, "normalized_source")
    state = runtime_db.fetch_workflow_state(connection) or {}
    if next_action != "init_runtime" and not source_doc:
        missing.append("source_documents.normalized_source")
    if next_action in {"persist_digest", "persist_references", "persist_citation_analysis", "finalize_outputs"}:
        if not runtime_db.has_outline_nodes(connection):
            missing.append("outline_nodes")
        if not runtime_db.fetch_section_scope(connection, "references_scope"):
            missing.append("section_scopes.references_scope")
        if not runtime_db.fetch_section_scope(connection, "citation_scope"):
            missing.append("section_scopes.citation_scope")
    if next_action in {"persist_citation_analysis", "finalize_outputs"} and not runtime_db.fetch_reference_items(connection):
        if not runtime_db.is_reference_extraction_abandoned(connection):
            missing.append("reference_items")
    if next_action == "finalize_outputs":
        if not runtime_db.fetch_digest_slots(connection):
            missing.append("digest_slots")
        if not runtime_db.fetch_digest_section_summaries(connection):
            missing.append("digest_section_summaries")
        if not runtime_db.fetch_citation_items(connection):
            missing.append("citation_items")
        if not runtime_db.fetch_citation_timeline(connection):
            missing.append("citation_timeline")
        if not runtime_db.fetch_citation_summary(connection):
            missing.append("citation_summary")
    if not state:
        missing.append("workflow_state")
    return missing


def _quality_directives(connection: Any) -> dict[str, Any] | None:
    issues = runtime_db.fetch_active_reference_quality_issues(connection)
    if not issues:
        return None
    severity = "hard_block" if any(issue.get("severity") == "hard_block" for issue in issues) else "warning"
    return {
        "kind": "stage4_reference_quality",
        "severity": severity,
        "instruction": (
            "Repair hard reference rows and resubmit persist_references."
            if severity == "hard_block"
            else "Review reference warnings; correct rows when possible or explicitly accept warnings."
        ),
        "issues": issues,
    }


def status_payload(db_path: Path) -> dict[str, Any]:
    with runtime_db.connect_db(db_path) as connection:
        state = runtime_db.fetch_workflow_state(connection) or {}
        raw_next_action = str(state.get("next_action") or "")
        next_action = _local_next_action(raw_next_action)
        payload = {
            "db_path": str(db_path),
            "workflow_state": state,
            "next_action": next_action,
            "raw_next_action": raw_next_action,
            "missing_prerequisites": _missing_prerequisites(connection, next_action),
            "execution_note": _execution_note(next_action),
            "instruction_refs": _instruction_refs(next_action),
            "allowed_payload_shape": _allowed_payload_shape(next_action),
            "field_guidance": _field_guidance(next_action),
            "quality_directives": _quality_directives(connection),
            "warnings": runtime_db.fetch_runtime_warnings(connection),
            "error": runtime_db.fetch_latest_error(connection),
            "receipts": sorted(runtime_db.fetch_action_receipts(connection)),
            "runtime_backend": "analysis_runtime.gate_contract",
        }
    return payload

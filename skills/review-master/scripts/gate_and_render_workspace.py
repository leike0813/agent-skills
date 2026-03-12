from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from runtime_localization import LocalizationBundle, fetch_runtime_language_context, load_localization_bundle
from workspace_db import (
    AGENT_RESUME_MD,
    ACTION_COPY_VARIANTS_MD,
    ALLOWED_EVIDENCE_GAP,
    ALLOWED_ARTIFACT_STATUS,
    ALLOWED_LOCATION_ROLE,
    ALLOWED_PRIORITY,
    ALLOWED_PROFILE_TARGET,
    ALLOWED_RESPONSE_ROLE,
    ALLOWED_RESUME_STATUS,
    ALLOWED_SOURCE_KIND,
    ALLOWED_SPAN_ROLE,
    ALLOWED_SOURCE_TYPE,
    ALLOWED_STAGE,
    ALLOWED_STAGE_GATE,
    ALLOWED_STATUS,
    ALLOWED_SUPPLEMENT_DECISION,
    ALLOWED_SUPPLEMENT_SUGGESTION_STATUS,
    ALLOWED_VARIANT_LABEL,
    ALLOWED_YES_NO,
    ATOMIC_COMMENTS_MD,
    ATOMIC_WORKBOARD_MD,
    DB_FILENAME,
    EXPORT_PATCH_PLAN_MD,
    FINAL_CHECKLIST_MD,
    MANUSCRIPT_SUMMARY_MD,
    RAW_REVIEW_THREADS_MD,
    REPAIR_PRIORITY,
    REVIEW_COMMENT_COVERAGE_MD,
    RESPONSE_LETTER_OUTLINE_MD,
    SUPPLEMENT_SUGGESTION_PLAN_MD,
    SUPPLEMENT_INTAKE_PLAN_MD,
    RESPONSE_TABLE_PREVIEW_MD,
    RESPONSE_TABLE_PREVIEW_TEX,
    STAGE3_COVERAGE_HARD_THRESHOLD,
    STAGE3_COVERAGE_SOFT_THRESHOLD,
    STYLE_PROFILE_MD,
    STRATEGY_CARD_DIR,
    TARGET_LOCATION_RE,
    THREAD_TO_ATOMIC_MAPPING_MD,
    artifact_paths,
    build_stage3_character_coverage_metrics,
    connect_db,
    ensure_runtime_schema_compatibility,
    fetch_all,
    fetch_one,
    load_runtime_digest,
    render_workspace,
    required_tables,
    table_exists,
)


def emit(payload: dict[str, Any], exit_code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    return exit_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the gate-and-render core script for a DB-first review-master artifact workspace.")
    parser.add_argument("--artifact-root", required=True, help="Path to the runtime workspace.")
    return parser.parse_args()


def add_issue(
    issues: list[dict[str, Any]],
    artifact: str,
    issue: str,
    detail: str,
    *,
    path: Path | None = None,
    comment_id: str | None = None,
    thread_id: str | None = None,
) -> None:
    payload: dict[str, Any] = {"artifact": artifact, "issue": issue, "detail": detail}
    if path is not None:
        payload["path"] = str(path)
    if comment_id:
        payload["comment_id"] = comment_id
    if thread_id:
        payload["thread_id"] = thread_id
    issues.append(payload)


def make_action(
    action_id: str,
    instruction: str,
    reason: str,
    target_artifacts: list[str],
    *,
    recipe_id: str | None = None,
) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "instruction": instruction,
        "reason": reason,
        "target_artifacts": target_artifacts,
        "recipe_id": recipe_id,
    }


def workflow_stage_number(workflow_state: sqlite3.Row | None) -> int:
    if workflow_state is None:
        return 0
    stage = str(workflow_state["current_stage"])
    if stage not in ALLOWED_STAGE:
        return 0
    return int(stage.split("_")[1])


def build_presence_report(artifact_root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Path]]:
    paths = artifact_paths(artifact_root)
    presence: dict[str, dict[str, Any]] = {
        "database": {"path": str(paths["db"]), "status": "present" if paths["db"].exists() else "missing"},
        "agent_resume_view": {
            "path": str(paths["agent_resume_md"]),
            "status": "present" if paths["agent_resume_md"].exists() else "missing",
        },
        "manuscript_summary_view": {
            "path": str(paths["manuscript_summary_md"]),
            "status": "present" if paths["manuscript_summary_md"].exists() else "missing",
        },
        "raw_review_threads_view": {
            "path": str(paths["raw_review_threads_md"]),
            "status": "present" if paths["raw_review_threads_md"].exists() else "missing",
        },
        "atomic_comments_view": {
            "path": str(paths["atomic_comments_md"]),
            "status": "present" if paths["atomic_comments_md"].exists() else "missing",
        },
        "thread_to_atomic_mapping_view": {
            "path": str(paths["thread_to_atomic_mapping_md"]),
            "status": "present" if paths["thread_to_atomic_mapping_md"].exists() else "missing",
        },
        "review_comment_coverage_view": {
            "path": str(paths["review_comment_coverage_md"]),
            "status": "present" if paths["review_comment_coverage_md"].exists() else "missing",
        },
        "atomic_workboard_view": {
            "path": str(paths["atomic_workboard_md"]),
            "status": "present" if paths["atomic_workboard_md"].exists() else "missing",
        },
        "style_profile_view": {
            "path": str(paths["style_profile_md"]),
            "status": "present" if paths["style_profile_md"].exists() else "missing",
        },
        "action_copy_variants_view": {
            "path": str(paths["action_copy_variants_md"]),
            "status": "present" if paths["action_copy_variants_md"].exists() else "missing",
        },
        "response_letter_outline_view": {
            "path": str(paths["response_letter_outline_md"]),
            "status": "present" if paths["response_letter_outline_md"].exists() else "missing",
        },
        "export_patch_plan_view": {
            "path": str(paths["export_patch_plan_md"]),
            "status": "present" if paths["export_patch_plan_md"].exists() else "missing",
        },
        "response_letter_table_preview_md_view": {
            "path": str(paths["response_table_preview_md"]),
            "status": "present" if paths["response_table_preview_md"].exists() else "missing",
        },
        "response_letter_table_preview_tex_view": {
            "path": str(paths["response_table_preview_tex"]),
            "status": "present" if paths["response_table_preview_tex"].exists() else "missing",
        },
        "supplement_suggestion_plan_view": {
            "path": str(paths["supplement_suggestion_plan_md"]),
            "status": "present" if paths["supplement_suggestion_plan_md"].exists() else "missing",
        },
        "supplement_intake_plan_view": {
            "path": str(paths["supplement_intake_plan_md"]),
            "status": "present" if paths["supplement_intake_plan_md"].exists() else "missing",
        },
        "final_checklist_view": {
            "path": str(paths["final_checklist_md"]),
            "status": "present" if paths["final_checklist_md"].exists() else "missing",
        },
        "response_strategy_cards": {
            "path": str(paths["strategy_card_dir"]),
            "status": "present" if paths["strategy_card_dir"].exists() else "missing",
            "count": len(list(paths["strategy_card_dir"].glob("*.md"))) if paths["strategy_card_dir"].exists() else 0,
        },
        "runtime_localization": {
            "path": str(paths["localization_root"]),
            "status": "present" if paths["localization_root"].exists() else "missing",
        },
        "working_messages": {
            "path": str(paths["localization_working_messages"]),
            "status": "present" if paths["localization_working_messages"].exists() else "missing",
        },
        "document_messages": {
            "path": str(paths["localization_document_messages"]),
            "status": "present" if paths["localization_document_messages"].exists() else "missing",
        },
    }
    return presence, paths


def validate_schema(connection: sqlite3.Connection, db_path: Path, format_errors: list[dict[str, Any]]) -> bool:
    ok = True
    for table_name in required_tables():
        if not table_exists(connection, table_name):
            add_issue(format_errors, "database", "missing_table", f"required table '{table_name}' is missing", path=db_path)
            ok = False
    return ok


def validate_target_location(
    issues: list[dict[str, Any]],
    artifact: str,
    path: Path,
    *,
    comment_id: str | None,
    value: str,
) -> None:
    if not value:
        return
    if value == "N/A":
        return
    if not TARGET_LOCATION_RE.match(value):
        add_issue(
            issues,
            artifact,
            "invalid_target_location",
            f"target_location='{value}' must follow path::section::anchor",
            path=path,
            comment_id=comment_id,
        )


def normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def compact_excerpt(value: str, *, limit: int = 120) -> str:
    compact = " ".join(value.split())
    if len(compact) > limit:
        return f"{compact[: limit - 3]}..."
    return compact


def load_supporting_maps(connection: sqlite3.Connection) -> dict[str, Any]:
    raw_thread_links = fetch_all(
        connection,
        "SELECT thread_id, comment_id, link_order FROM raw_thread_atomic_links ORDER BY thread_id, link_order, comment_id",
    )
    review_comment_source_documents = fetch_all(
        connection,
        """
        SELECT source_document_id, source_kind, document_order, source_label, source_path, original_text
        FROM review_comment_source_documents
        ORDER BY document_order, source_document_id
        """,
    )
    raw_thread_source_spans = fetch_all(
        connection,
        """
        SELECT thread_id, source_document_id, span_order, span_role, start_offset, end_offset, span_text
        FROM raw_thread_source_spans
        ORDER BY source_document_id, start_offset, end_offset, thread_id, span_order
        """,
    )
    atomic_source_spans = fetch_all(
        connection,
        "SELECT comment_id, thread_id, excerpt_text, note FROM atomic_comment_source_spans ORDER BY comment_id, thread_id",
    )
    target_locations = fetch_all(
        connection,
        "SELECT comment_id, location_order, target_location, location_role FROM atomic_comment_target_locations ORDER BY comment_id, location_order",
    )
    analysis_links = fetch_all(
        connection,
        """
        SELECT comment_id, analysis_order, manuscript_claim_or_section, existing_evidence, gap_summary, dependency_comment_id
        FROM atomic_comment_analysis_links
        ORDER BY comment_id, analysis_order
        """,
    )
    strategy_action_locations = fetch_all(
        connection,
        """
        SELECT comment_id, action_order, location_order, target_location
        FROM strategy_action_target_locations
        ORDER BY comment_id, action_order, location_order
        """,
    )
    strategy_action_manuscript_drafts = fetch_all(
        connection,
        """
        SELECT comment_id, action_order, location_order, draft_text, rationale
        FROM strategy_action_manuscript_drafts
        ORDER BY comment_id, action_order, location_order
        """,
    )
    comment_response_drafts = fetch_all(
        connection,
        """
        SELECT comment_id, draft_text, rationale
        FROM comment_response_drafts
        ORDER BY comment_id
        """,
    )
    response_links = fetch_all(
        connection,
        """
        SELECT thread_id, comment_id, response_order, response_role
        FROM response_thread_resolution_links
        ORDER BY thread_id, response_order, comment_id
        """,
    )
    style_profiles = fetch_all(
        connection,
        "SELECT profile_target, profile_summary, anti_ai_focus FROM style_profiles ORDER BY profile_target",
    )
    style_rules = fetch_all(
        connection,
        "SELECT profile_target, rule_order, rule_type, rule_text FROM style_profile_rules ORDER BY profile_target, rule_order",
    )
    action_copy_variants = fetch_all(
        connection,
        """
        SELECT comment_id, action_order, location_order, variant_label, variant_text, rationale
        FROM action_copy_variants
        ORDER BY comment_id, action_order, location_order, variant_label
        """,
    )
    selected_action_copy_variants = fetch_all(
        connection,
        """
        SELECT comment_id, action_order, location_order, variant_label
        FROM selected_action_copy_variants
        ORDER BY comment_id, action_order, location_order
        """,
    )
    response_thread_rows = fetch_all(
        connection,
        """
        SELECT thread_id, original_comment, modification_scope, key_revision_excerpt, response_explanation, latex_excerpt, latex_response_text
        FROM response_thread_rows
        ORDER BY thread_id
        """,
    )
    export_artifacts = fetch_all(
        connection,
        """
        SELECT artifact_name, artifact_status, output_path
        FROM export_artifacts
        ORDER BY artifact_name
        """,
    )
    export_patch_sets = fetch_all(
        connection,
        """
        SELECT patch_set_id, artifact_kind, source_root, output_root, status
        FROM export_patch_sets
        ORDER BY patch_set_id
        """,
    )
    export_patches = fetch_all(
        connection,
        """
        SELECT patch_set_id, patch_order, comment_id, action_order, location_order, target_file,
               anchor_text, operation, marked_text, clean_text, notes
        FROM export_patches
        ORDER BY patch_set_id, patch_order
        """,
    )
    supplement_intake_items = fetch_all(
        connection,
        """
        SELECT round_id, file_path, concern_summary, decision, decision_rationale
        FROM supplement_intake_items
        ORDER BY round_id, file_path
        """,
    )
    supplement_suggestion_items = fetch_all(
        connection,
        """
        SELECT comment_id, suggestion_order, analysis_order, request_summary, request_recommendation, status
        FROM supplement_suggestion_items
        ORDER BY comment_id, suggestion_order
        """,
    )
    supplement_suggestion_intake_links = fetch_all(
        connection,
        """
        SELECT comment_id, suggestion_order, round_id, file_path, link_note
        FROM supplement_suggestion_intake_links
        ORDER BY comment_id, suggestion_order, round_id, file_path
        """,
    )
    supplement_landing_links = fetch_all(
        connection,
        """
        SELECT round_id, file_path, comment_id, action_order, location_order, planned_usage_note
        FROM supplement_landing_links
        ORDER BY round_id, file_path, comment_id, action_order, location_order
        """,
    )
    comment_blockers = fetch_all(
        connection,
        """
        SELECT comment_id, blocker_order, message
        FROM comment_blockers
        ORDER BY comment_id, blocker_order
        """,
    )
    return {
        "raw_thread_links": raw_thread_links,
        "review_comment_source_documents": review_comment_source_documents,
        "raw_thread_source_spans": raw_thread_source_spans,
        "atomic_source_spans": atomic_source_spans,
        "target_locations": target_locations,
        "analysis_links": analysis_links,
        "strategy_action_locations": strategy_action_locations,
        "strategy_action_manuscript_drafts": strategy_action_manuscript_drafts,
        "comment_response_drafts": comment_response_drafts,
        "response_links": response_links,
        "style_profiles": style_profiles,
        "style_rules": style_rules,
        "action_copy_variants": action_copy_variants,
        "selected_action_copy_variants": selected_action_copy_variants,
        "response_thread_rows": response_thread_rows,
        "export_patch_sets": export_patch_sets,
        "export_patches": export_patches,
        "export_artifacts": export_artifacts,
        "supplement_suggestion_items": supplement_suggestion_items,
        "supplement_suggestion_intake_links": supplement_suggestion_intake_links,
        "supplement_intake_items": supplement_intake_items,
        "supplement_landing_links": supplement_landing_links,
        "comment_blockers": comment_blockers,
    }


def validate_database_content(
    connection: sqlite3.Connection,
    db_path: Path,
) -> tuple[Any, ...]:
    format_errors: list[dict[str, Any]] = []
    workflow_rows = fetch_all(connection, "SELECT id, current_stage, stage_gate, active_comment_id, next_action FROM workflow_state ORDER BY id")
    workflow_state = workflow_rows[0] if workflow_rows else None
    if len(workflow_rows) != 1:
        add_issue(format_errors, "workflow_state", "invalid_row_count", "workflow_state must contain exactly one row", path=db_path)
    if workflow_state is not None:
        if str(workflow_state["current_stage"]) not in ALLOWED_STAGE:
            add_issue(format_errors, "workflow_state", "invalid_enum", f"current_stage='{workflow_state['current_stage']}' is not allowed", path=db_path)
        if str(workflow_state["stage_gate"]) not in ALLOWED_STAGE_GATE:
            add_issue(format_errors, "workflow_state", "invalid_enum", f"stage_gate='{workflow_state['stage_gate']}' is not allowed", path=db_path)
        if not str(workflow_state["next_action"]).strip():
            add_issue(format_errors, "workflow_state", "missing_required_field", "next_action must be non-empty", path=db_path)

    pending = [str(row["message"]) for row in fetch_all(connection, "SELECT message FROM workflow_pending_user_confirmations ORDER BY position")]
    blockers = [str(row["message"]) for row in fetch_all(connection, "SELECT message FROM workflow_global_blockers ORDER BY position")]
    resume_rows = fetch_all(
        connection,
        """
        SELECT id, resume_status, current_objective, current_focus, why_paused, next_operator_action
        FROM resume_brief
        ORDER BY id
        """,
    )
    resume_brief = resume_rows[0] if resume_rows else None
    if len(resume_rows) != 1:
        add_issue(format_errors, "resume_brief", "invalid_row_count", "resume_brief must contain exactly one row", path=db_path)
    if resume_brief is not None:
        if str(resume_brief["resume_status"]) not in ALLOWED_RESUME_STATUS:
            add_issue(format_errors, "resume_brief", "invalid_enum", f"resume_status='{resume_brief['resume_status']}' is not allowed", path=db_path)
        for field in ("current_objective", "current_focus", "why_paused", "next_operator_action"):
            if not str(resume_brief[field]).strip():
                add_issue(format_errors, "resume_brief", "missing_required_field", f"{field} must be non-empty", path=db_path)

    resume_open_loops = [str(row["message"]) for row in fetch_all(connection, "SELECT message FROM resume_open_loops ORDER BY position")]
    resume_recent_decisions = [str(row["message"]) for row in fetch_all(connection, "SELECT message FROM resume_recent_decisions ORDER BY position")]
    resume_must_not_forget = [str(row["message"]) for row in fetch_all(connection, "SELECT message FROM resume_must_not_forget ORDER BY position")]

    support = load_supporting_maps(connection)
    review_comment_source_document_map = {
        str(row["source_document_id"]): row for row in support["review_comment_source_documents"]
    }
    raw_thread_source_span_map: dict[tuple[str, str, int], sqlite3.Row] = {}
    thread_to_source_span_keys: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
    spans_by_source_document: dict[str, list[tuple[int, int, str, int, str]]] = defaultdict(list)
    thread_span_roles: dict[str, set[str]] = defaultdict(set)
    legacy_source_documents: set[str] = set()
    for row in support["review_comment_source_documents"]:
        source_document_id = str(row["source_document_id"])
        if source_document_id.startswith("legacy-thread::"):
            legacy_source_documents.add(source_document_id)
        if str(row["source_kind"]) not in ALLOWED_SOURCE_KIND:
            add_issue(
                format_errors,
                "review_comment_source_documents",
                "invalid_enum",
                f"source_kind='{row['source_kind']}' is not allowed",
                path=db_path,
            )
        for field in ("source_label", "source_path", "original_text"):
            if not str(row[field]).strip():
                add_issue(
                    format_errors,
                    "review_comment_source_documents",
                    "missing_required_field",
                    f"{field} must be non-empty",
                    path=db_path,
                )
        if source_document_id.count(" ") > 0:
            add_issue(
                format_errors,
                "review_comment_source_documents",
                "invalid_identifier",
                f"source_document_id '{source_document_id}' must not contain spaces",
                path=db_path,
            )
    for row in support["raw_thread_source_spans"]:
        thread_id = str(row["thread_id"])
        source_document_id = str(row["source_document_id"])
        span_order = int(row["span_order"])
        span_key = (thread_id, source_document_id, span_order)
        raw_thread_source_span_map[span_key] = row
        thread_to_source_span_keys[thread_id].append(span_key)
        span_role = str(row["span_role"] or "")
        if span_role not in ALLOWED_SPAN_ROLE:
            add_issue(
                format_errors,
                "raw_thread_source_spans",
                "invalid_enum",
                (
                    f"span ({thread_id}, {source_document_id}, {span_order}) has invalid "
                    f"span_role='{span_role}'"
                ),
                path=db_path,
                thread_id=thread_id,
            )
            continue
        thread_span_roles[thread_id].add(span_role)
        start_offset = int(row["start_offset"])
        end_offset = int(row["end_offset"])
        if start_offset < 0 or end_offset <= start_offset:
            add_issue(
                format_errors,
                "raw_thread_source_spans",
                "invalid_span_offset",
                (
                    f"span ({thread_id}, {source_document_id}, {span_order}) "
                    f"has invalid offset range [{start_offset}, {end_offset})"
                ),
                path=db_path,
                thread_id=thread_id,
            )
            continue
        source_row = review_comment_source_document_map.get(source_document_id)
        if source_row is None:
            add_issue(
                format_errors,
                "raw_thread_source_spans",
                "missing_source_document",
                (
                    f"span ({thread_id}, {source_document_id}, {span_order}) references "
                    f"unknown source_document_id '{source_document_id}'"
                ),
                path=db_path,
                thread_id=thread_id,
            )
            continue
        original_text = str(source_row["original_text"])
        if end_offset > len(original_text):
            add_issue(
                format_errors,
                "raw_thread_source_spans",
                "span_out_of_bounds",
                (
                    f"span ({thread_id}, {source_document_id}, {span_order}) with "
                    f"offset [{start_offset}, {end_offset}) exceeds source length {len(original_text)}"
                ),
                path=db_path,
                thread_id=thread_id,
            )
            continue
        expected_text = original_text[start_offset:end_offset]
        if normalize_newlines(str(row["span_text"])) != normalize_newlines(expected_text):
            add_issue(
                format_errors,
                "raw_thread_source_spans",
                "span_text_mismatch",
                (
                    f"span ({thread_id}, {source_document_id}, {span_order}) text does not match "
                    "source substring at declared offsets"
                ),
                path=db_path,
                thread_id=thread_id,
            )
        spans_by_source_document[source_document_id].append((start_offset, end_offset, thread_id, span_order, span_role))

    for source_document_id, spans in spans_by_source_document.items():
        ordered_spans = sorted(spans, key=lambda item: (item[0], item[1], item[2], item[3]))
        previous: tuple[int, int, str, int, str] | None = None
        for span in ordered_spans:
            if previous is not None and span[0] < previous[1]:
                add_issue(
                    format_errors,
                    "raw_thread_source_spans",
                    "overlapping_spans",
                    (
                        "source document "
                        f"'{source_document_id}' has overlapping spans: "
                        f"({previous[2]}, order={previous[3]}, range={previous[0]}:{previous[1]}) and "
                        f"({span[2]}, order={span[3]}, range={span[0]}:{span[1]})"
                    ),
                    path=db_path,
                    thread_id=span[2],
                )
            previous = span

    raw_thread_rows = fetch_all(
        connection,
        """
        SELECT thread_id, reviewer_id, thread_order, source_type, original_text, normalized_summary
        FROM raw_review_threads
        ORDER BY reviewer_id, thread_order, thread_id
        """,
    )
    raw_thread_map = {str(row["thread_id"]): row for row in raw_thread_rows}
    for row in raw_thread_rows:
        thread_id = str(row["thread_id"])
        if not str(row["reviewer_id"]).strip():
            add_issue(format_errors, "raw_review_threads", "missing_required_field", "reviewer_id must be non-empty", path=db_path, thread_id=thread_id)
        if str(row["source_type"]) not in ALLOWED_SOURCE_TYPE:
            add_issue(format_errors, "raw_review_threads", "invalid_enum", f"source_type='{row['source_type']}' is not allowed", path=db_path, thread_id=thread_id)
        if not str(row["original_text"]).strip():
            add_issue(format_errors, "raw_review_threads", "missing_required_field", "original_text must be non-empty", path=db_path, thread_id=thread_id)
        if not str(row["normalized_summary"]).strip():
            add_issue(format_errors, "raw_review_threads", "missing_required_field", "normalized_summary must be non-empty", path=db_path, thread_id=thread_id)
        if thread_id not in thread_to_source_span_keys:
            add_issue(
                format_errors,
                "raw_thread_source_spans",
                "missing_thread_spans",
                f"raw_review_thread '{thread_id}' has no source spans in raw_thread_source_spans",
                path=db_path,
                thread_id=thread_id,
            )
        elif "primary" not in thread_span_roles.get(thread_id, set()):
            add_issue(
                format_errors,
                "raw_thread_source_spans",
                "missing_primary_span",
                f"raw_review_thread '{thread_id}' must include at least one primary span",
                path=db_path,
                thread_id=thread_id,
            )

    atomic_rows = fetch_all(
        connection,
        """
        SELECT comment_id, comment_order, canonical_summary, required_action
        FROM atomic_comments
        ORDER BY comment_order, comment_id
        """,
    )
    atomic_map = {str(row["comment_id"]): row for row in atomic_rows}
    for row in atomic_rows:
        comment_id = str(row["comment_id"])
        if not str(row["canonical_summary"]).strip():
            add_issue(format_errors, "atomic_comments", "missing_required_field", "canonical_summary must be non-empty", path=db_path, comment_id=comment_id)
        if not str(row["required_action"]).strip():
            add_issue(format_errors, "atomic_comments", "missing_required_field", "required_action must be non-empty", path=db_path, comment_id=comment_id)

    atomic_state_rows = fetch_all(
        connection,
        """
        SELECT comment_id, status, priority, evidence_gap, user_confirmation_needed, next_action
        FROM atomic_comment_state
        ORDER BY comment_id
        """,
    )
    atomic_state_map = {str(row["comment_id"]): row for row in atomic_state_rows}
    for row in atomic_state_rows:
        comment_id = str(row["comment_id"])
        if str(row["status"]) not in ALLOWED_STATUS:
            add_issue(format_errors, "atomic_comment_state", "invalid_enum", f"status='{row['status']}' is not allowed", path=db_path, comment_id=comment_id)
        if str(row["priority"]) not in ALLOWED_PRIORITY:
            add_issue(format_errors, "atomic_comment_state", "invalid_enum", f"priority='{row['priority']}' is not allowed", path=db_path, comment_id=comment_id)
        if str(row["evidence_gap"]) not in ALLOWED_EVIDENCE_GAP:
            add_issue(format_errors, "atomic_comment_state", "invalid_enum", f"evidence_gap='{row['evidence_gap']}' is not allowed", path=db_path, comment_id=comment_id)
        if str(row["user_confirmation_needed"]) not in ALLOWED_YES_NO:
            add_issue(
                format_errors,
                "atomic_comment_state",
                "invalid_enum",
                f"user_confirmation_needed='{row['user_confirmation_needed']}' is not allowed",
                path=db_path,
                comment_id=comment_id,
            )
        if not str(row["next_action"]).strip():
            add_issue(format_errors, "atomic_comment_state", "missing_required_field", "next_action must be non-empty", path=db_path, comment_id=comment_id)

    strategy_rows = fetch_all(connection, "SELECT comment_id, proposed_stance, stance_rationale FROM strategy_cards ORDER BY comment_id")
    strategy_map = {str(row["comment_id"]): row for row in strategy_rows}
    for row in strategy_rows:
        comment_id = str(row["comment_id"])
        if not str(row["proposed_stance"]).strip():
            add_issue(format_errors, "strategy_cards", "missing_required_field", "proposed_stance must be non-empty", path=db_path, comment_id=comment_id)
        if not str(row["stance_rationale"]).strip():
            add_issue(format_errors, "strategy_cards", "missing_required_field", "stance_rationale must be non-empty", path=db_path, comment_id=comment_id)

    completion_rows = fetch_all(
        connection,
        """
        SELECT comment_id, manuscript_draft_done, response_draft_done, evidence_gap_closed,
               user_strategy_confirmed, one_to_one_link_checked, export_ready
        FROM comment_completion_status
        ORDER BY comment_id
        """,
    )
    completion_map = {str(row["comment_id"]): row for row in completion_rows}
    for row in completion_rows:
        comment_id = str(row["comment_id"])
        for field in (
            "manuscript_draft_done",
            "response_draft_done",
            "evidence_gap_closed",
            "user_strategy_confirmed",
            "one_to_one_link_checked",
            "export_ready",
        ):
            value = str(row[field])
            if value not in ALLOWED_YES_NO:
                add_issue(format_errors, "comment_completion_status", "invalid_enum", f"{field}='{value}' is not allowed", path=db_path, comment_id=comment_id)
        if str(row["export_ready"]) == "yes":
            for field in ("manuscript_draft_done", "response_draft_done", "one_to_one_link_checked"):
                if str(row[field]) != "yes":
                    add_issue(
                        format_errors,
                        "comment_completion_status",
                        "invalid_gate_state",
                        f"export_ready cannot be yes when {field} is not yes",
                        path=db_path,
                        comment_id=comment_id,
                    )

    thread_to_comment_ids: dict[str, list[str]] = defaultdict(list)
    comment_to_thread_ids: dict[str, list[str]] = defaultdict(list)
    comment_to_target_locations: dict[str, list[str]] = defaultdict(list)
    comment_to_analysis_ids: dict[str, list[str]] = defaultdict(list)
    comment_to_action_ids: dict[str, list[str]] = defaultdict(list)
    action_location_orders: dict[tuple[str, int], list[int]] = defaultdict(list)
    manuscript_draft_map: dict[tuple[str, int, int], sqlite3.Row] = {}
    response_draft_map: dict[str, sqlite3.Row] = {}
    thread_to_resolution_comment_ids: dict[str, list[str]] = defaultdict(list)
    comment_blocker_map: dict[str, list[str]] = defaultdict(list)
    style_profile_map: dict[str, sqlite3.Row] = {}
    style_rule_count_by_target: dict[str, int] = defaultdict(int)
    action_variant_labels: dict[tuple[str, int, int], set[str]] = defaultdict(set)
    selected_variant_map: dict[tuple[str, int, int], str] = {}
    response_thread_row_map: dict[str, sqlite3.Row] = {}
    export_patch_set_map: dict[str, sqlite3.Row] = {}
    export_patch_count_map: dict[str, int] = {}
    export_artifact_map: dict[str, sqlite3.Row] = {}
    supplement_suggestion_map: dict[tuple[str, int], sqlite3.Row] = {}
    supplement_suggestion_count_by_comment: dict[str, int] = defaultdict(int)

    for row in support["raw_thread_links"]:
        thread_id = str(row["thread_id"])
        comment_id = str(row["comment_id"])
        thread_to_comment_ids[thread_id].append(comment_id)
        comment_to_thread_ids[comment_id].append(thread_id)

    for span_key, span_row in raw_thread_source_span_map.items():
        thread_id = str(span_row["thread_id"])
        if not thread_to_comment_ids.get(thread_id):
            add_issue(
                format_errors,
                "raw_thread_source_spans",
                "missing_thread_comment_links",
                (
                    f"span ({span_key[0]}, {span_key[1]}, {span_key[2]}) belongs to thread '{thread_id}' "
                    "but raw_thread_atomic_links has no linked comment_id"
                ),
                path=db_path,
                thread_id=thread_id,
            )

    for row in support["atomic_source_spans"]:
        comment_id = str(row["comment_id"])
        if not str(row["excerpt_text"]).strip():
            add_issue(format_errors, "atomic_comment_source_spans", "missing_required_field", "excerpt_text must be non-empty", path=db_path, comment_id=comment_id, thread_id=str(row["thread_id"]))

    for row in support["target_locations"]:
        comment_id = str(row["comment_id"])
        value = str(row["target_location"])
        comment_to_target_locations[comment_id].append(value)
        validate_target_location(format_errors, "atomic_comment_target_locations", db_path, comment_id=comment_id, value=value)
        if str(row["location_role"]) not in ALLOWED_LOCATION_ROLE:
            add_issue(format_errors, "atomic_comment_target_locations", "invalid_enum", f"location_role='{row['location_role']}' is not allowed", path=db_path, comment_id=comment_id)

    for row in support["analysis_links"]:
        comment_id = str(row["comment_id"])
        comment_to_analysis_ids[comment_id].append(str(row["analysis_order"]))
        if not str(row["manuscript_claim_or_section"]).strip():
            add_issue(format_errors, "atomic_comment_analysis_links", "missing_required_field", "manuscript_claim_or_section must be non-empty", path=db_path, comment_id=comment_id)
        if not str(row["existing_evidence"]).strip():
            add_issue(format_errors, "atomic_comment_analysis_links", "missing_required_field", "existing_evidence must be non-empty", path=db_path, comment_id=comment_id)
        if not str(row["gap_summary"]).strip():
            add_issue(format_errors, "atomic_comment_analysis_links", "missing_required_field", "gap_summary must be non-empty", path=db_path, comment_id=comment_id)

    action_rows = fetch_all(
        connection,
        """
        SELECT comment_id, action_order, manuscript_change, expected_response_letter_effect
        FROM strategy_card_actions
        ORDER BY comment_id, action_order
        """,
    )
    for row in action_rows:
        comment_id = str(row["comment_id"])
        action_key = f"{row['action_order']}"
        comment_to_action_ids[comment_id].append(action_key)
        if not str(row["manuscript_change"]).strip():
            add_issue(format_errors, "strategy_card_actions", "missing_required_field", "manuscript_change must be non-empty", path=db_path, comment_id=comment_id)
        if not str(row["expected_response_letter_effect"]).strip():
            add_issue(
                format_errors,
                "strategy_card_actions",
                "missing_required_field",
                "expected_response_letter_effect must be non-empty",
                path=db_path,
                comment_id=comment_id,
            )

    for row in support["strategy_action_locations"]:
        comment_id = str(row["comment_id"])
        action_order = int(row["action_order"])
        location_order = int(row["location_order"])
        action_location_orders[(comment_id, action_order)].append(location_order)
        validate_target_location(
            format_errors,
            "strategy_action_target_locations",
            db_path,
            comment_id=comment_id,
            value=str(row["target_location"]),
        )

    for row in support["strategy_action_manuscript_drafts"]:
        comment_id = str(row["comment_id"])
        action_order = int(row["action_order"])
        location_order = int(row["location_order"])
        manuscript_draft_map[(comment_id, action_order, location_order)] = row
        if not str(row["draft_text"]).strip():
            add_issue(
                format_errors,
                "strategy_action_manuscript_drafts",
                "missing_required_field",
                "draft_text must be non-empty",
                path=db_path,
                comment_id=comment_id,
            )
        if not str(row["rationale"]).strip():
            add_issue(
                format_errors,
                "strategy_action_manuscript_drafts",
                "missing_required_field",
                "rationale must be non-empty",
                path=db_path,
                comment_id=comment_id,
            )
        if location_order not in action_location_orders.get((comment_id, action_order), []):
            add_issue(
                format_errors,
                "strategy_action_manuscript_drafts",
                "invalid_action_location_reference",
                f"draft references ({comment_id}, action {action_order}, location {location_order}) which is missing in strategy_action_target_locations",
                path=db_path,
                comment_id=comment_id,
            )

    for row in support["comment_response_drafts"]:
        comment_id = str(row["comment_id"])
        response_draft_map[comment_id] = row
        if not str(row["draft_text"]).strip():
            add_issue(
                format_errors,
                "comment_response_drafts",
                "missing_required_field",
                "draft_text must be non-empty",
                path=db_path,
                comment_id=comment_id,
            )
        if not str(row["rationale"]).strip():
            add_issue(
                format_errors,
                "comment_response_drafts",
                "missing_required_field",
                "rationale must be non-empty",
                path=db_path,
                comment_id=comment_id,
            )

    evidence_rows = fetch_all(
        connection,
        """
        SELECT comment_id, evidence_order, required_material, available_now, gap_note
        FROM strategy_card_evidence_items
        ORDER BY comment_id, evidence_order
        """,
    )
    for row in evidence_rows:
        comment_id = str(row["comment_id"])
        if not str(row["required_material"]).strip():
            add_issue(format_errors, "strategy_card_evidence_items", "missing_required_field", "required_material must be non-empty", path=db_path, comment_id=comment_id)
        if str(row["available_now"]) not in ALLOWED_YES_NO:
            add_issue(format_errors, "strategy_card_evidence_items", "invalid_enum", f"available_now='{row['available_now']}' is not allowed", path=db_path, comment_id=comment_id)

    intake_keys: set[tuple[str, str]] = set()
    accepted_keys: set[tuple[str, str]] = set()
    for row in support["supplement_intake_items"]:
        round_id = str(row["round_id"])
        file_path = str(row["file_path"])
        key = (round_id, file_path)
        intake_keys.add(key)
        if not round_id.strip():
            add_issue(
                format_errors,
                "supplement_intake_items",
                "missing_required_field",
                "round_id must be non-empty",
                path=db_path,
            )
        if not file_path.strip():
            add_issue(
                format_errors,
                "supplement_intake_items",
                "missing_required_field",
                "file_path must be non-empty",
                path=db_path,
            )
        decision = str(row["decision"])
        if decision not in ALLOWED_SUPPLEMENT_DECISION:
            add_issue(
                format_errors,
                "supplement_intake_items",
                "invalid_enum",
                f"decision='{decision}' is not allowed",
                path=db_path,
            )
        if decision in {"accepted", "rejected"} and not str(row["decision_rationale"]).strip():
            add_issue(
                format_errors,
                "supplement_intake_items",
                "missing_required_field",
                "decision_rationale must be non-empty when decision is accepted/rejected",
                path=db_path,
            )
        if decision == "accepted":
            accepted_keys.add(key)

    landing_keys: set[tuple[str, str]] = set()
    for row in support["supplement_landing_links"]:
        round_id = str(row["round_id"])
        file_path = str(row["file_path"])
        key = (round_id, file_path)
        landing_keys.add(key)
        comment_id = str(row["comment_id"])
        action_order = int(row["action_order"])
        location_order = int(row["location_order"])
        if not str(row["planned_usage_note"]).strip():
            add_issue(
                format_errors,
                "supplement_landing_links",
                "missing_required_field",
                "planned_usage_note must be non-empty",
                path=db_path,
                comment_id=comment_id,
            )
        if key not in intake_keys:
            add_issue(
                format_errors,
                "supplement_landing_links",
                "missing_parent_intake_record",
                f"landing link ({round_id}, {file_path}) has no parent supplement_intake_items record",
                path=db_path,
                comment_id=comment_id,
            )
        if location_order not in action_location_orders.get((comment_id, action_order), []):
            add_issue(
                format_errors,
                "supplement_landing_links",
                "invalid_action_location_reference",
                (
                    f"landing link references ({comment_id}, action {action_order}, location {location_order}) "
                    "which is missing in strategy_action_target_locations"
                ),
                path=db_path,
                comment_id=comment_id,
            )

    for row in support["comment_blockers"]:
        comment_id = str(row["comment_id"])
        comment_blocker_map[comment_id].append(str(row["message"]))
        if not str(row["message"]).strip():
            add_issue(
                format_errors,
                "comment_blockers",
                "missing_required_field",
                "message must be non-empty",
                path=db_path,
                comment_id=comment_id,
            )

    for round_id, file_path in sorted(accepted_keys):
        if (round_id, file_path) not in landing_keys:
            add_issue(
                format_errors,
                "supplement_landing_links",
                "missing_landing_for_accepted_supplement",
                f"accepted supplement '{file_path}' in round '{round_id}' has no landing mapping",
                path=db_path,
            )

    for row in support["response_links"]:
        thread_id = str(row["thread_id"])
        comment_id = str(row["comment_id"])
        thread_to_resolution_comment_ids[thread_id].append(comment_id)
        if str(row["response_role"]) not in ALLOWED_RESPONSE_ROLE:
            add_issue(format_errors, "response_thread_resolution_links", "invalid_enum", f"response_role='{row['response_role']}' is not allowed", path=db_path, thread_id=thread_id, comment_id=comment_id)

    for row in support["style_profiles"]:
        profile_target = str(row["profile_target"])
        style_profile_map[profile_target] = row
        if profile_target not in ALLOWED_PROFILE_TARGET:
            add_issue(format_errors, "style_profiles", "invalid_enum", f"profile_target='{profile_target}' is not allowed", path=db_path)

    for row in support["style_rules"]:
        profile_target = str(row["profile_target"])
        style_rule_count_by_target[profile_target] += 1
        rule_type = str(row["rule_type"])
        if rule_type not in {"do", "dont", "anti_ai", "tone"}:
            add_issue(format_errors, "style_profile_rules", "invalid_enum", f"rule_type='{rule_type}' is not allowed", path=db_path)
        if not str(row["rule_text"]).strip():
            add_issue(format_errors, "style_profile_rules", "missing_required_field", "rule_text must be non-empty", path=db_path)

    for row in support["action_copy_variants"]:
        comment_id = str(row["comment_id"])
        action_order = int(row["action_order"])
        location_order = int(row["location_order"])
        variant_label = str(row["variant_label"])
        action_variant_labels[(comment_id, action_order, location_order)].add(variant_label)
        if variant_label not in ALLOWED_VARIANT_LABEL:
            add_issue(format_errors, "action_copy_variants", "invalid_enum", f"variant_label='{variant_label}' is not allowed", path=db_path, comment_id=comment_id)
        if not str(row["variant_text"]).strip():
            add_issue(format_errors, "action_copy_variants", "missing_required_field", "variant_text must be non-empty", path=db_path, comment_id=comment_id)
        if not str(row["rationale"]).strip():
            add_issue(format_errors, "action_copy_variants", "missing_required_field", "rationale must be non-empty", path=db_path, comment_id=comment_id)

    for row in support["selected_action_copy_variants"]:
        comment_id = str(row["comment_id"])
        action_order = int(row["action_order"])
        location_order = int(row["location_order"])
        variant_label = str(row["variant_label"])
        selected_variant_map[(comment_id, action_order, location_order)] = variant_label
        if variant_label not in ALLOWED_VARIANT_LABEL:
            add_issue(format_errors, "selected_action_copy_variants", "invalid_enum", f"variant_label='{variant_label}' is not allowed", path=db_path, comment_id=comment_id)

    for row in support["response_thread_rows"]:
        thread_id = str(row["thread_id"])
        response_thread_row_map[thread_id] = row
        for field in ("original_comment", "modification_scope", "key_revision_excerpt", "response_explanation", "latex_excerpt", "latex_response_text"):
            if not str(row[field]).strip():
                add_issue(format_errors, "response_thread_rows", "missing_required_field", f"{field} must be non-empty", path=db_path, thread_id=thread_id)

    for row in support["export_patch_sets"]:
        patch_set_id = str(row["patch_set_id"])
        export_patch_set_map[patch_set_id] = row
        if not str(row["source_root"]).strip():
            add_issue(format_errors, "export_patch_sets", "missing_required_field", "source_root must be non-empty", path=db_path)
        if not str(row["output_root"]).strip():
            add_issue(format_errors, "export_patch_sets", "missing_required_field", "output_root must be non-empty", path=db_path)

    for row in support["export_patches"]:
        patch_set_id = str(row["patch_set_id"])
        export_patch_count_map[patch_set_id] = export_patch_count_map.get(patch_set_id, 0) + 1
        comment_id = str(row["comment_id"])
        if not str(row["target_file"]).strip():
            add_issue(format_errors, "export_patches", "missing_required_field", "target_file must be non-empty", path=db_path, comment_id=comment_id)
        if not str(row["anchor_text"]).strip():
            add_issue(format_errors, "export_patches", "missing_required_field", "anchor_text must be non-empty", path=db_path, comment_id=comment_id)
        if not str(row["marked_text"]).strip():
            add_issue(format_errors, "export_patches", "missing_required_field", "marked_text must be non-empty", path=db_path, comment_id=comment_id)
        if not str(row["clean_text"]).strip():
            add_issue(format_errors, "export_patches", "missing_required_field", "clean_text must be non-empty", path=db_path, comment_id=comment_id)

    for row in support["export_artifacts"]:
        artifact_name = str(row["artifact_name"])
        export_artifact_map[artifact_name] = row
        if str(row["artifact_status"]) not in ALLOWED_ARTIFACT_STATUS:
            add_issue(format_errors, "export_artifacts", "invalid_enum", f"artifact_status='{row['artifact_status']}' is not allowed", path=db_path)

    for row in support["supplement_suggestion_items"]:
        comment_id = str(row["comment_id"])
        suggestion_order = int(row["suggestion_order"])
        supplement_suggestion_map[(comment_id, suggestion_order)] = row
        supplement_suggestion_count_by_comment[comment_id] += 1
        if not str(row["request_summary"]).strip():
            add_issue(
                format_errors,
                "supplement_suggestion_items",
                "missing_required_field",
                "request_summary must be non-empty",
                path=db_path,
                comment_id=comment_id,
            )
        if not str(row["request_recommendation"]).strip():
            add_issue(
                format_errors,
                "supplement_suggestion_items",
                "missing_required_field",
                "request_recommendation must be non-empty",
                path=db_path,
                comment_id=comment_id,
            )
        if str(row["status"]) not in ALLOWED_SUPPLEMENT_SUGGESTION_STATUS:
            add_issue(
                format_errors,
                "supplement_suggestion_items",
                "invalid_enum",
                f"status='{row['status']}' is not allowed",
                path=db_path,
                comment_id=comment_id,
            )

    for row in support["supplement_suggestion_intake_links"]:
        comment_id = str(row["comment_id"])
        suggestion_order = int(row["suggestion_order"])
        round_id = str(row["round_id"])
        file_path = str(row["file_path"])
        if (comment_id, suggestion_order) not in supplement_suggestion_map:
            add_issue(
                format_errors,
                "supplement_suggestion_intake_links",
                "missing_parent_suggestion",
                (
                    "supplement suggestion intake link "
                    f"({comment_id}, S{suggestion_order}, {round_id}, {file_path}) has no parent suggestion item"
                ),
                path=db_path,
                comment_id=comment_id,
            )
        if not str(row["link_note"]).strip():
            add_issue(
                format_errors,
                "supplement_suggestion_intake_links",
                "missing_required_field",
                "link_note must be non-empty",
                path=db_path,
                comment_id=comment_id,
            )

    stage3_coverage_advisories: list[str] = []
    threads_without_supporting = {
        thread_id
        for thread_id, roles in thread_span_roles.items()
        if "primary" in roles and "supporting" not in roles
    }
    for source_document_id, source_row in review_comment_source_document_map.items():
        original_text = str(source_row["original_text"])
        spans = sorted(
            spans_by_source_document.get(source_document_id, []),
            key=lambda item: (item[0], item[1], item[2], item[3]),
        )
        for index, span in enumerate(spans):
            start_offset, end_offset, thread_id, span_order, span_role = span
            if span_role != "primary" or thread_id not in threads_without_supporting:
                continue
            next_start = spans[index + 1][0] if index + 1 < len(spans) else len(original_text)
            if next_start <= end_offset:
                continue
            uncovered = original_text[end_offset:next_start].strip()
            if len(uncovered) < 120:
                continue
            if "\n" not in uncovered and not any(mark in uncovered for mark in (".", ";", "?", "!")):
                continue
            stage3_coverage_advisories.append(
                (
                    f"thread '{thread_id}' has no supporting span after primary span "
                    f"(source='{source_document_id}', span_order={span_order}). "
                    f"Adjacent uncovered text excerpt: \"{compact_excerpt(uncovered)}\""
                )
            )

    return (
        workflow_state,
        resume_brief,
        pending,
        blockers,
        resume_open_loops,
        resume_recent_decisions,
        resume_must_not_forget,
        review_comment_source_document_map,
        dict(raw_thread_source_span_map),
        dict(thread_to_source_span_keys),
        sorted(legacy_source_documents),
        raw_thread_map,
        atomic_map,
        atomic_state_map,
        strategy_map,
        completion_map,
        dict(thread_to_comment_ids),
        dict(comment_to_thread_ids),
        dict(comment_to_target_locations),
        dict(comment_to_analysis_ids),
        dict(comment_to_action_ids),
        {key: sorted(set(value)) for key, value in action_location_orders.items()},
        manuscript_draft_map,
        response_draft_map,
        dict(thread_to_resolution_comment_ids),
        dict(comment_blocker_map),
        style_profile_map,
        dict(style_rule_count_by_target),
        dict(action_variant_labels),
        selected_variant_map,
        response_thread_row_map,
        export_patch_set_map,
        export_patch_count_map,
        export_artifact_map,
        supplement_suggestion_map,
        dict(supplement_suggestion_count_by_comment),
        stage3_coverage_advisories,
        format_errors,
    )


def validate_dependencies(
    db_path: Path,
    stage_number: int,
    active_comment_id: str | None,
    review_comment_source_document_map: dict[str, sqlite3.Row],
    raw_thread_source_span_map: dict[tuple[str, str, int], sqlite3.Row],
    thread_to_source_span_keys: dict[str, list[tuple[str, str, int]]],
    legacy_source_documents: list[str],
    raw_thread_map: dict[str, sqlite3.Row],
    atomic_map: dict[str, sqlite3.Row],
    atomic_state_map: dict[str, sqlite3.Row],
    strategy_map: dict[str, sqlite3.Row],
    completion_map: dict[str, sqlite3.Row],
    thread_to_comment_ids: dict[str, list[str]],
    comment_to_thread_ids: dict[str, list[str]],
    comment_to_target_locations: dict[str, list[str]],
    comment_to_analysis_ids: dict[str, list[str]],
    action_location_orders: dict[tuple[str, int], list[int]],
    manuscript_draft_map: dict[tuple[str, int, int], sqlite3.Row],
    response_draft_map: dict[str, sqlite3.Row],
    thread_to_resolution_comment_ids: dict[str, list[str]],
    comment_to_action_ids: dict[str, list[str]],
    style_profile_map: dict[str, sqlite3.Row],
    style_rule_count_by_target: dict[str, int],
    action_variant_labels: dict[tuple[str, int, int], set[str]],
    selected_variant_map: dict[tuple[str, int, int], str],
    response_thread_row_map: dict[str, sqlite3.Row],
    export_patch_set_map: dict[str, sqlite3.Row],
    export_patch_count_map: dict[str, int],
    export_artifact_map: dict[str, sqlite3.Row],
    supplement_suggestion_count_by_comment: dict[str, int],
    stage3_coverage_metrics: dict[str, Any],
) -> list[dict[str, Any]]:
    dependency_errors: list[dict[str, Any]] = []
    raw_thread_ids = set(raw_thread_map)
    atomic_ids = set(atomic_map)

    if stage_number >= 3:
        if not review_comment_source_document_map:
            add_issue(
                dependency_errors,
                "review_comment_source_documents",
                "missing_source_documents",
                "stage_3 or later requires review_comment_source_documents",
                path=db_path,
            )
        if not raw_thread_source_span_map:
            add_issue(
                dependency_errors,
                "raw_thread_source_spans",
                "missing_source_spans",
                "stage_3 or later requires raw_thread_source_spans",
                path=db_path,
            )
        if legacy_source_documents and stage_number <= 4:
            add_issue(
                dependency_errors,
                "raw_thread_source_spans",
                "legacy_source_spans_require_stage3_rebuild",
                (
                    "legacy thread-level source documents were detected; rerun Stage 3 from the original reviewer/editor "
                    "files to rebuild source spans for full-document coverage highlighting"
                ),
                path=db_path,
            )
        for thread_id in sorted(raw_thread_ids):
            if not thread_to_comment_ids.get(thread_id):
                add_issue(
                    dependency_errors,
                    "raw_thread_atomic_links",
                    "missing_thread_links",
                    f"raw_review_thread '{thread_id}' has no linked canonical atomic comments",
                    path=db_path,
                    thread_id=thread_id,
                )
            if not thread_to_source_span_keys.get(thread_id):
                add_issue(
                    dependency_errors,
                    "raw_thread_source_spans",
                    "missing_thread_spans",
                    f"raw_review_thread '{thread_id}' has no source span in raw_thread_source_spans",
                    path=db_path,
                    thread_id=thread_id,
                )
        for comment_id in sorted(atomic_ids):
            if not comment_to_thread_ids.get(comment_id):
                add_issue(
                    dependency_errors,
                    "raw_thread_atomic_links",
                    "orphan_atomic_comment",
                    f"canonical atomic comment '{comment_id}' is not linked to any raw review thread",
                    path=db_path,
                    comment_id=comment_id,
                )
        for span_key, span_row in sorted(raw_thread_source_span_map.items()):
            thread_id = str(span_row["thread_id"])
            if thread_id not in raw_thread_ids:
                add_issue(
                    dependency_errors,
                    "raw_thread_source_spans",
                    "unknown_thread_reference",
                    (
                        f"span ({span_key[0]}, {span_key[1]}, {span_key[2]}) references "
                        f"unknown thread_id '{thread_id}'"
                    ),
                    path=db_path,
                    thread_id=thread_id,
                )
                continue
            if not thread_to_comment_ids.get(thread_id):
                add_issue(
                    dependency_errors,
                    "raw_thread_source_spans",
                    "span_thread_without_comment_links",
                    (
                        f"span ({span_key[0]}, {span_key[1]}, {span_key[2]}) belongs to thread '{thread_id}' "
                        "but raw_thread_atomic_links has no linked comment_id"
                    ),
                    path=db_path,
                    thread_id=thread_id,
                )
        global_metrics = stage3_coverage_metrics.get("global", {})
        total_chars = int(global_metrics.get("total_chars", 0))
        coverage_percent_including_duplicates = float(
            global_metrics.get("coverage_percent_including_duplicates", 0.0)
        )
        hard_threshold = float(
            stage3_coverage_metrics.get("thresholds", {}).get(
                "hard_percent",
                STAGE3_COVERAGE_HARD_THRESHOLD,
            )
        )
        if total_chars > 0 and str(stage3_coverage_metrics.get("gate_status", "")) == "hard_fail":
            add_issue(
                dependency_errors,
                "raw_thread_source_spans",
                "coverage_below_hard_threshold",
                (
                    "stage_3 global character coverage is below hard threshold: "
                    f"{coverage_percent_including_duplicates:.2f}% < {hard_threshold:.2f}% "
                    f"(covered_chars_including_duplicates={int(global_metrics.get('covered_chars_including_duplicates', 0))}, "
                    f"total_chars={total_chars})"
                ),
                path=db_path,
            )

    if stage_number >= 4:
        for comment_id in sorted(atomic_ids):
            if comment_id not in atomic_state_map:
                add_issue(
                    dependency_errors,
                    "atomic_comment_state",
                    "missing_comment_id",
                    f"atomic_comment_state is missing comment_id '{comment_id}'",
                    path=db_path,
                    comment_id=comment_id,
                )
    if stage_number >= 5:
        for comment_id, row in sorted(atomic_state_map.items()):
            if str(row["evidence_gap"]) != "yes":
                continue
            if supplement_suggestion_count_by_comment.get(comment_id, 0) == 0:
                add_issue(
                    dependency_errors,
                    "supplement_suggestion_items",
                    "missing_supplement_suggestions",
                    (
                        f"comment '{comment_id}' has evidence_gap=yes but no supplement suggestion rows; "
                        "Stage 5 must expose at least one suggestion item"
                    ),
                    path=db_path,
                    comment_id=comment_id,
                )
            if not comment_to_target_locations.get(comment_id):
                add_issue(
                    dependency_errors,
                    "atomic_comment_target_locations",
                    "missing_comment_id",
                    f"atomic_comment_target_locations is missing comment_id '{comment_id}'",
                    path=db_path,
                    comment_id=comment_id,
                )
            if not comment_to_analysis_ids.get(comment_id):
                add_issue(
                    dependency_errors,
                    "atomic_comment_analysis_links",
                    "missing_comment_id",
                    f"atomic_comment_analysis_links is missing comment_id '{comment_id}'",
                    path=db_path,
                    comment_id=comment_id,
                )

    if stage_number >= 5 and active_comment_id:
        if active_comment_id not in strategy_map:
            add_issue(
                dependency_errors,
                "strategy_cards",
                "missing_comment_id",
                f"strategy_cards is missing active comment_id '{active_comment_id}'",
                path=db_path,
                comment_id=active_comment_id,
            )
        completion_row = completion_map.get(active_comment_id)
        if completion_row is not None:
            if str(completion_row["manuscript_draft_done"]) == "yes":
                for action_order_text in comment_to_action_ids.get(active_comment_id, []):
                    action_order = int(action_order_text)
                    for location_order in action_location_orders.get((active_comment_id, action_order), []):
                        if (active_comment_id, action_order, location_order) not in manuscript_draft_map:
                            add_issue(
                                dependency_errors,
                                "strategy_action_manuscript_drafts",
                                "missing_draft_row",
                                f"{active_comment_id} action {action_order} location {location_order} has no manuscript draft row",
                                path=db_path,
                                comment_id=active_comment_id,
                            )
            if str(completion_row["response_draft_done"]) == "yes" and active_comment_id not in response_draft_map:
                add_issue(
                    dependency_errors,
                    "comment_response_drafts",
                    "missing_comment_id",
                    f"comment_response_drafts is missing comment_id '{active_comment_id}'",
                    path=db_path,
                    comment_id=active_comment_id,
                )

    if stage_number >= 6:
        for profile_target in ("manuscript", "response_letter"):
            if profile_target not in style_profile_map:
                add_issue(
                    dependency_errors,
                    "style_profiles",
                    "missing_profile_target",
                    f"style_profiles is missing profile_target '{profile_target}'",
                    path=db_path,
                )
            if style_rule_count_by_target.get(profile_target, 0) == 0:
                add_issue(
                    dependency_errors,
                    "style_profile_rules",
                    "missing_profile_rules",
                    f"style_profile_rules is missing authored rules for profile_target '{profile_target}'",
                    path=db_path,
                )
        for comment_id, action_orders in comment_to_action_ids.items():
            for action_order_text in action_orders:
                action_order = int(action_order_text)
                for location_order in action_location_orders.get((comment_id, action_order), []):
                    labels = action_variant_labels.get((comment_id, action_order, location_order), set())
                    if labels != {"v1", "v2", "v3"}:
                        add_issue(
                            dependency_errors,
                            "action_copy_variants",
                            "missing_three_variants",
                            f"{comment_id} action {action_order} location {location_order} is missing one or more manuscript final-copy variants",
                            path=db_path,
                            comment_id=comment_id,
                        )
                    if (comment_id, action_order, location_order) not in selected_variant_map:
                        add_issue(
                            dependency_errors,
                            "selected_action_copy_variants",
                            "missing_selected_variant",
                            f"{comment_id} action {action_order} location {location_order} has no selected manuscript final-copy variant",
                            path=db_path,
                            comment_id=comment_id,
                        )
        for comment_id in sorted(atomic_ids):
            if comment_id not in completion_map:
                add_issue(
                    dependency_errors,
                    "comment_completion_status",
                    "missing_comment_id",
                    f"comment_completion_status is missing comment_id '{comment_id}'",
                    path=db_path,
                    comment_id=comment_id,
                )
        for thread_id in sorted(raw_thread_ids):
            linked = thread_to_comment_ids.get(thread_id, [])
            outlined = set(thread_to_resolution_comment_ids.get(thread_id, []))
            if linked and not outlined:
                add_issue(
                    dependency_errors,
                    "response_thread_resolution_links",
                    "missing_thread_coverage",
                    f"thread '{thread_id}' has no response-thread resolution links",
                    path=db_path,
                    thread_id=thread_id,
                )
            elif linked:
                for comment_id in linked:
                    if comment_id not in outlined:
                        add_issue(
                            dependency_errors,
                            "response_thread_resolution_links",
                            "missing_comment_id",
                            f"thread '{thread_id}' is missing response coverage for canonical atomic comment '{comment_id}'",
                            path=db_path,
                            thread_id=thread_id,
                            comment_id=comment_id,
                        )
            if thread_id not in response_thread_row_map:
                add_issue(
                    dependency_errors,
                    "response_thread_rows",
                    "missing_thread_row",
                    f"thread '{thread_id}' has no final response_thread_rows entry",
                    path=db_path,
                    thread_id=thread_id,
                )
        required_patch_kinds = {"marked_manuscript", "clean_manuscript"}
        patch_set_by_kind = {str(row["artifact_kind"]): patch_set_id for patch_set_id, row in export_patch_set_map.items()}
        for artifact_kind in sorted(required_patch_kinds):
            patch_set_id = patch_set_by_kind.get(artifact_kind)
            if patch_set_id is None:
                add_issue(
                    dependency_errors,
                    "export_patch_sets",
                    "missing_patch_set",
                    f"export_patch_sets is missing artifact_kind '{artifact_kind}'",
                    path=db_path,
                )
                continue
            if export_patch_count_map.get(patch_set_id, 0) == 0:
                add_issue(
                    dependency_errors,
                    "export_patches",
                    "missing_patch_rows",
                    f"patch set '{patch_set_id}' for '{artifact_kind}' has no export_patches",
                    path=db_path,
                )
        for artifact_name in ("marked_manuscript", "clean_manuscript", "response_markdown", "response_latex"):
            if artifact_name not in export_artifact_map:
                add_issue(
                    dependency_errors,
                    "export_artifacts",
                    "missing_artifact_row",
                    f"export_artifacts is missing artifact_name '{artifact_name}'",
                    path=db_path,
                )
    return dependency_errors


def validate_consistency(
    db_path: Path,
    workflow_state: sqlite3.Row | None,
    resume_brief: sqlite3.Row | None,
    pending: list[str],
    blockers: list[str],
    resume_open_loops: list[str],
    resume_recent_decisions: list[str],
    resume_must_not_forget: list[str],
    review_comment_source_document_map: dict[str, sqlite3.Row],
    raw_thread_source_span_map: dict[tuple[str, str, int], sqlite3.Row],
    raw_thread_map: dict[str, sqlite3.Row],
    atomic_map: dict[str, sqlite3.Row],
    atomic_state_map: dict[str, sqlite3.Row],
    strategy_map: dict[str, sqlite3.Row],
    completion_map: dict[str, sqlite3.Row],
    thread_to_comment_ids: dict[str, list[str]],
    thread_to_resolution_comment_ids: dict[str, list[str]],
    comment_blocker_map: dict[str, list[str]],
    style_profile_map: dict[str, sqlite3.Row],
    style_rule_count_by_target: dict[str, int],
    action_variant_labels: dict[tuple[str, int, int], set[str]],
    selected_variant_map: dict[tuple[str, int, int], str],
    response_thread_row_map: dict[str, sqlite3.Row],
    export_patch_set_map: dict[str, sqlite3.Row],
    export_patch_count_map: dict[str, int],
    export_artifact_map: dict[str, sqlite3.Row],
    supplement_suggestion_count_by_comment: dict[str, int],
    manuscript_draft_map: dict[tuple[str, int, int], sqlite3.Row],
    response_draft_map: dict[str, sqlite3.Row],
) -> list[dict[str, Any]]:
    consistency_errors: list[dict[str, Any]] = []
    if workflow_state is None:
        return consistency_errors

    active_comment_id = str(workflow_state["active_comment_id"]) if workflow_state["active_comment_id"] is not None else None
    if resume_brief is None:
        add_issue(consistency_errors, "resume_brief", "missing_resume_brief", "workflow_state exists but resume_brief is missing", path=db_path)
    else:
        resume_status = str(resume_brief["resume_status"])
        if current_stage := str(workflow_state["current_stage"]):
            stage_number = workflow_stage_number(workflow_state)
            if stage_number >= 2 and resume_status == "bootstrap":
                add_issue(
                    consistency_errors,
                    "resume_brief",
                    "stale_bootstrap_resume",
                    f"resume_status cannot remain bootstrap once workflow has advanced to {current_stage}",
                    path=db_path,
                )
            if stage_number >= 4 and not resume_open_loops and not pending and not blockers:
                add_issue(
                    consistency_errors,
                    "resume_open_loops",
                    "missing_runtime_resume_detail",
                    "mid-to-late workflow should retain at least one open loop or an explicit blocker/confirmation trail",
                    path=db_path,
                )
            if stage_number >= 3 and not resume_must_not_forget:
                add_issue(
                    consistency_errors,
                    "resume_must_not_forget",
                    "missing_runtime_resume_detail",
                    "resume_must_not_forget should contain at least one runtime reminder after stage_3",
                    path=db_path,
                )
            if stage_number >= 2 and not resume_recent_decisions:
                add_issue(
                    consistency_errors,
                    "resume_recent_decisions",
                    "missing_runtime_resume_detail",
                    "resume_recent_decisions should contain at least one authored decision after stage_2",
                    path=db_path,
                )
    if active_comment_id and active_comment_id not in atomic_map:
        add_issue(
            consistency_errors,
            "workflow_state",
            "unknown_active_comment_id",
            f"active_comment_id '{active_comment_id}' does not exist in atomic_comments",
            path=db_path,
            comment_id=active_comment_id,
        )

    current_stage = str(workflow_state["current_stage"])
    stage_gate = str(workflow_state["stage_gate"])
    if stage_gate != "ready":
        return consistency_errors

    if current_stage == "stage_2":
        with connect_db(db_path) as connection:
            summary = fetch_one(connection, "SELECT main_entry, project_shape FROM manuscript_summary WHERE id = 1")
        if summary is not None and (not str(summary["main_entry"]).strip() or not str(summary["project_shape"]).strip()):
            add_issue(consistency_errors, "workflow_state", "stage_gate_without_authored_prerequisites", "stage_2 is ready but manuscript_summary is not fully authored", path=db_path)
    if current_stage == "stage_3":
        if not raw_thread_map:
            add_issue(consistency_errors, "workflow_state", "stage_gate_without_authored_prerequisites", "stage_3 is ready but raw_review_threads is empty", path=db_path)
        if not atomic_map:
            add_issue(consistency_errors, "workflow_state", "stage_gate_without_authored_prerequisites", "stage_3 is ready but atomic_comments is empty", path=db_path)
        if not review_comment_source_document_map:
            add_issue(
                consistency_errors,
                "workflow_state",
                "stage_gate_without_authored_prerequisites",
                "stage_3 is ready but review_comment_source_documents is empty",
                path=db_path,
            )
        if not raw_thread_source_span_map:
            add_issue(
                consistency_errors,
                "workflow_state",
                "stage_gate_without_authored_prerequisites",
                "stage_3 is ready but raw_thread_source_spans is empty",
                path=db_path,
            )
    if current_stage == "stage_4":
        if not atomic_state_map:
            add_issue(consistency_errors, "workflow_state", "stage_gate_without_authored_prerequisites", "stage_4 is ready but atomic_comment_state is empty", path=db_path)
    if current_stage == "stage_5":
        if not active_comment_id:
            add_issue(consistency_errors, "workflow_state", "missing_active_comment", "stage_5 requires active_comment_id", path=db_path)
        if active_comment_id and active_comment_id not in strategy_map and not pending and not blockers:
            add_issue(consistency_errors, "workflow_state", "stage_gate_without_authored_prerequisites", "stage_5 is ready but active comment has no strategy card", path=db_path, comment_id=active_comment_id)
        if active_comment_id:
            completion_row = completion_map.get(active_comment_id)
            if completion_row is not None and str(completion_row["user_strategy_confirmed"]) != "yes":
                add_issue(
                    consistency_errors,
                    "workflow_state",
                    "stage_gate_without_confirmed_strategy",
                    "stage_5 cannot be ready for draft authoring or advancement while active strategy is unconfirmed",
                    path=db_path,
                    comment_id=active_comment_id,
                )
            if completion_row is not None and str(completion_row["user_strategy_confirmed"]) != "yes":
                has_manuscript_drafts = any(key[0] == active_comment_id for key in manuscript_draft_map)
                has_response_draft = active_comment_id in response_draft_map
                if has_manuscript_drafts or has_response_draft:
                    add_issue(
                        consistency_errors,
                        "comment_completion_status",
                        "stale_stage5_drafts_before_confirmation",
                        "unconfirmed strategy must not retain Stage 5 drafts",
                        path=db_path,
                        comment_id=active_comment_id,
                    )
        for comment_id, row in sorted(atomic_state_map.items()):
            if str(row["evidence_gap"]) == "yes" and supplement_suggestion_count_by_comment.get(comment_id, 0) == 0:
                add_issue(
                    consistency_errors,
                    "workflow_state",
                    "stage_gate_without_supplement_suggestions",
                    f"stage_5 is missing supplement suggestions for evidence-gap comment '{comment_id}'",
                    path=db_path,
                    comment_id=comment_id,
                )
        with connect_db(db_path) as connection:
            intake_rows = fetch_all(
                connection,
                """
                SELECT round_id, file_path, decision, decision_rationale
                FROM supplement_intake_items
                ORDER BY round_id, file_path
                """,
            )
            landing_rows = fetch_all(
                connection,
                """
                SELECT round_id, file_path
                FROM supplement_landing_links
                ORDER BY round_id, file_path
                """,
            )
        if intake_rows:
            landing_keys = {(str(row["round_id"]), str(row["file_path"])) for row in landing_rows}
            for row in intake_rows:
                round_id = str(row["round_id"])
                file_path = str(row["file_path"])
                decision = str(row["decision"])
                if not decision:
                    add_issue(
                        consistency_errors,
                        "workflow_state",
                        "stage_gate_without_authored_prerequisites",
                        (
                            "stage_5 is ready but supplement intake contains pending decision "
                            f"for round '{round_id}' file '{file_path}'"
                        ),
                        path=db_path,
                    )
                if decision in {"accepted", "rejected"} and not str(row["decision_rationale"]).strip():
                    add_issue(
                        consistency_errors,
                        "workflow_state",
                        "stage_gate_without_authored_prerequisites",
                        (
                            "stage_5 is ready but supplement intake decision lacks rationale "
                            f"for round '{round_id}' file '{file_path}'"
                        ),
                        path=db_path,
                    )
                if decision == "accepted" and (round_id, file_path) not in landing_keys:
                    add_issue(
                        consistency_errors,
                        "workflow_state",
                        "stage_gate_without_authored_prerequisites",
                        (
                            "stage_5 is ready but accepted supplement has no landing mapping: "
                            f"round '{round_id}' file '{file_path}'"
                        ),
                        path=db_path,
                    )
    if current_stage == "stage_6":
        if not completion_map:
            add_issue(consistency_errors, "workflow_state", "stage_gate_without_authored_prerequisites", "stage_6 is ready but comment_completion_status is empty", path=db_path)
        if blockers:
            add_issue(consistency_errors, "workflow_state", "blocked_stage_marked_ready", "stage_6 is ready but global blockers are still present", path=db_path)
        for profile_target in ("manuscript", "response_letter"):
            profile_row = style_profile_map.get(profile_target)
            if profile_row is None or not str(profile_row["profile_summary"]).strip():
                add_issue(
                    consistency_errors,
                    "workflow_state",
                    "stage_gate_without_authored_prerequisites",
                    f"stage_6 is ready but style profile '{profile_target}' is not fully authored",
                    path=db_path,
                )
            if style_rule_count_by_target.get(profile_target, 0) == 0:
                add_issue(
                    consistency_errors,
                    "workflow_state",
                    "stage_gate_without_authored_prerequisites",
                    f"stage_6 is ready but style profile '{profile_target}' has no authored rules",
                    path=db_path,
                )
        for thread_id, linked_comment_ids in thread_to_comment_ids.items():
            outlined = set(thread_to_resolution_comment_ids.get(thread_id, []))
            if linked_comment_ids and any(comment_id not in outlined for comment_id in linked_comment_ids):
                add_issue(
                    consistency_errors,
                    "workflow_state",
                    "stage_gate_without_authored_prerequisites",
                    f"stage_6 is ready but thread '{thread_id}' is not fully covered in response_thread_resolution_links",
                    path=db_path,
                    thread_id=thread_id,
                )
            if linked_comment_ids and thread_id not in response_thread_row_map:
                add_issue(
                    consistency_errors,
                    "workflow_state",
                    "stage_gate_without_authored_prerequisites",
                    f"stage_6 is ready but thread '{thread_id}' has no final response row",
                    path=db_path,
                    thread_id=thread_id,
                )
        patch_set_by_kind = {str(row["artifact_kind"]): patch_set_id for patch_set_id, row in export_patch_set_map.items()}
        for artifact_kind in ("marked_manuscript", "clean_manuscript"):
            patch_set_id = patch_set_by_kind.get(artifact_kind)
            if patch_set_id is None:
                add_issue(
                    consistency_errors,
                    "workflow_state",
                    "stage_gate_without_export_patch_plan",
                    f"stage_6 is ready but export_patch_sets has no '{artifact_kind}' patch set",
                    path=db_path,
                )
            elif export_patch_count_map.get(patch_set_id, 0) == 0:
                add_issue(
                    consistency_errors,
                    "workflow_state",
                    "stage_gate_without_export_patch_plan",
                    f"stage_6 is ready but patch set '{patch_set_id}' has no export_patches",
                    path=db_path,
                )
        for row in export_artifact_map.values():
            if str(row["artifact_name"]) == "marked_manuscript" and str(row["artifact_status"]) == "exported":
                continue
        if export_artifact_map.get("marked_manuscript") is None:
            add_issue(consistency_errors, "workflow_state", "stage_gate_without_authored_prerequisites", "stage_6 is ready but export_artifacts lacks marked_manuscript", path=db_path)
    return consistency_errors


def classify_issue_target(issue: dict[str, Any]) -> tuple[str, str | None]:
    artifact = str(issue.get("artifact", ""))
    comment_id = issue.get("comment_id")
    if artifact in REPAIR_PRIORITY:
        return artifact, comment_id if isinstance(comment_id, str) else None
    if artifact == "database":
        return "workflow_state", None
    return "atomic_comment_state", comment_id if isinstance(comment_id, str) else None


def build_repair_sequence(
    format_errors: list[dict[str, Any]],
    dependency_errors: list[dict[str, Any]],
    consistency_errors: list[dict[str, Any]],
    localization: LocalizationBundle,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str | None], list[str]] = {}
    for issue in [*format_errors, *dependency_errors, *consistency_errors]:
        artifact, comment_id = classify_issue_target(issue)
        grouped.setdefault((artifact, comment_id), []).append(str(issue.get("detail", issue.get("issue", "validation issue"))))

    ordered = sorted(grouped.items(), key=lambda item: (REPAIR_PRIORITY.get(item[0][0], 99), item[0][1] or ""))
    repairs: list[dict[str, Any]] = []
    recipe_map = {
        "workflow_state": "recipe_stage1_set_entry_state",
        "resume_brief": "recipe_stage1_set_entry_state",
        "resume_open_loops": "recipe_stage1_set_entry_state",
        "resume_recent_decisions": "recipe_stage1_set_entry_state",
        "resume_must_not_forget": "recipe_stage1_set_entry_state",
        "manuscript_summary": "recipe_stage2_upsert_manuscript_summary",
        "raw_review_threads": "recipe_stage3_replace_threaded_atomic_model",
        "atomic_comments": "recipe_stage3_replace_threaded_atomic_model",
        "raw_thread_atomic_links": "recipe_stage3_replace_threaded_atomic_model",
        "review_comment_source_documents": "recipe_stage3_replace_threaded_atomic_model",
        "raw_thread_source_spans": "recipe_stage3_replace_threaded_atomic_model",
        "review_comment_coverage_segments": "recipe_stage3_replace_threaded_atomic_model",
        "review_comment_coverage_segment_comment_links": "recipe_stage3_replace_threaded_atomic_model",
        "atomic_comment_state": "recipe_stage4_upsert_atomic_workboard",
        "atomic_comment_target_locations": "recipe_stage4_upsert_atomic_workboard",
        "atomic_comment_analysis_links": "recipe_stage4_upsert_atomic_workboard",
        "strategy_cards": "recipe_stage5_upsert_strategy_card",
        "strategy_action_manuscript_drafts": "recipe_stage5_replace_execution_drafts",
        "comment_response_drafts": "recipe_stage5_replace_execution_drafts",
        "comment_completion_status": "recipe_stage5_upsert_completion_status",
        "comment_blockers": "recipe_stage5_replace_comment_blockers",
        "response_thread_resolution_links": "recipe_stage6_upsert_response_thread_rows",
        "style_profiles": "recipe_stage6_upsert_style_profiles",
        "style_profile_rules": "recipe_stage6_upsert_style_profiles",
        "action_copy_variants": "recipe_stage6_replace_action_copy_variants",
        "selected_action_copy_variants": "recipe_stage6_select_action_copy_variants",
        "response_thread_rows": "recipe_stage6_upsert_response_thread_rows",
        "export_patch_sets": "recipe_stage6_replace_export_patches",
        "export_patches": "recipe_stage6_replace_export_patches",
        "export_artifacts": "recipe_stage6_export_marked_manuscript",
        "supplement_suggestion_items": "recipe_stage5_replace_supplement_suggestions",
        "supplement_suggestion_intake_links": "recipe_stage5_replace_supplement_suggestions",
        "supplement_intake_items": "recipe_stage5_replace_supplement_intake_and_landing",
        "supplement_landing_links": "recipe_stage5_replace_supplement_intake_and_landing",
    }
    target_map = {
        "workflow_state": ["review-master.db"],
        "resume_brief": ["review-master.db", AGENT_RESUME_MD],
        "resume_open_loops": ["review-master.db", AGENT_RESUME_MD],
        "resume_recent_decisions": ["review-master.db", AGENT_RESUME_MD],
        "resume_must_not_forget": ["review-master.db", AGENT_RESUME_MD],
        "manuscript_summary": ["review-master.db", MANUSCRIPT_SUMMARY_MD],
        "raw_review_threads": ["review-master.db", RAW_REVIEW_THREADS_MD],
        "atomic_comments": ["review-master.db", ATOMIC_COMMENTS_MD],
        "raw_thread_atomic_links": ["review-master.db", THREAD_TO_ATOMIC_MAPPING_MD],
        "review_comment_source_documents": ["review-master.db", REVIEW_COMMENT_COVERAGE_MD],
        "raw_thread_source_spans": ["review-master.db", REVIEW_COMMENT_COVERAGE_MD],
        "review_comment_coverage_segments": ["review-master.db", REVIEW_COMMENT_COVERAGE_MD],
        "review_comment_coverage_segment_comment_links": ["review-master.db", REVIEW_COMMENT_COVERAGE_MD],
        "atomic_comment_state": ["review-master.db", ATOMIC_WORKBOARD_MD],
        "atomic_comment_target_locations": ["review-master.db", ATOMIC_WORKBOARD_MD],
        "atomic_comment_analysis_links": ["review-master.db", ATOMIC_WORKBOARD_MD],
        "strategy_cards": ["review-master.db", STRATEGY_CARD_DIR],
        "strategy_action_manuscript_drafts": ["review-master.db", STRATEGY_CARD_DIR],
        "comment_response_drafts": ["review-master.db", STRATEGY_CARD_DIR],
        "comment_completion_status": ["review-master.db", FINAL_CHECKLIST_MD],
        "comment_blockers": ["review-master.db", STRATEGY_CARD_DIR],
        "response_thread_resolution_links": ["review-master.db", RESPONSE_LETTER_OUTLINE_MD, RESPONSE_TABLE_PREVIEW_MD],
        "style_profiles": ["review-master.db", STYLE_PROFILE_MD],
        "style_profile_rules": ["review-master.db", STYLE_PROFILE_MD],
        "action_copy_variants": ["review-master.db", ACTION_COPY_VARIANTS_MD],
        "selected_action_copy_variants": ["review-master.db", ACTION_COPY_VARIANTS_MD],
        "response_thread_rows": ["review-master.db", RESPONSE_TABLE_PREVIEW_MD, RESPONSE_TABLE_PREVIEW_TEX],
        "export_patch_sets": ["review-master.db", EXPORT_PATCH_PLAN_MD],
        "export_patches": ["review-master.db", EXPORT_PATCH_PLAN_MD],
        "export_artifacts": ["review-master.db", FINAL_CHECKLIST_MD],
        "supplement_suggestion_items": ["review-master.db", SUPPLEMENT_SUGGESTION_PLAN_MD],
        "supplement_suggestion_intake_links": ["review-master.db", SUPPLEMENT_SUGGESTION_PLAN_MD],
        "supplement_intake_items": ["review-master.db", SUPPLEMENT_INTAKE_PLAN_MD],
        "supplement_landing_links": ["review-master.db", SUPPLEMENT_INTAKE_PLAN_MD],
    }
    instruction_map = {
        "workflow_state": localization.msg("gate.repair.workflow_state"),
        "resume_brief": localization.msg("gate.repair.resume_brief"),
        "resume_open_loops": localization.msg("gate.repair.resume_open_loops"),
        "resume_recent_decisions": localization.msg("gate.repair.resume_recent_decisions"),
        "resume_must_not_forget": localization.msg("gate.repair.resume_must_not_forget"),
        "manuscript_summary": localization.msg("gate.repair.manuscript_summary"),
        "raw_review_threads": localization.msg("gate.repair.raw_review_threads"),
        "atomic_comments": localization.msg("gate.repair.atomic_comments"),
        "raw_thread_atomic_links": localization.msg("gate.repair.raw_thread_atomic_links"),
        "review_comment_source_documents": localization.msg("gate.repair.review_comment_source_documents"),
        "raw_thread_source_spans": localization.msg("gate.repair.raw_thread_source_spans"),
        "review_comment_coverage_segments": localization.msg("gate.repair.review_comment_coverage_segments"),
        "review_comment_coverage_segment_comment_links": localization.msg("gate.repair.review_comment_coverage_segment_comment_links"),
        "atomic_comment_state": localization.msg("gate.repair.atomic_comment_state"),
        "atomic_comment_target_locations": localization.msg("gate.repair.atomic_comment_target_locations"),
        "atomic_comment_analysis_links": localization.msg("gate.repair.atomic_comment_analysis_links"),
        "strategy_cards": localization.msg("gate.repair.strategy_cards"),
        "strategy_action_manuscript_drafts": localization.msg("gate.repair.strategy_action_manuscript_drafts"),
        "comment_response_drafts": localization.msg("gate.repair.comment_response_drafts"),
        "comment_completion_status": localization.msg("gate.repair.comment_completion_status"),
        "comment_blockers": localization.msg("gate.repair.comment_blockers"),
        "response_thread_resolution_links": localization.msg("gate.repair.response_thread_resolution_links"),
        "style_profiles": localization.msg("gate.repair.style_profiles"),
        "style_profile_rules": localization.msg("gate.repair.style_profile_rules"),
        "action_copy_variants": localization.msg("gate.repair.action_copy_variants"),
        "selected_action_copy_variants": localization.msg("gate.repair.selected_action_copy_variants"),
        "response_thread_rows": localization.msg("gate.repair.response_thread_rows"),
        "export_patch_sets": localization.msg("gate.repair.export_patch_sets"),
        "export_patches": localization.msg("gate.repair.export_patches"),
        "export_artifacts": localization.msg("gate.repair.export_artifacts"),
        "supplement_suggestion_items": localization.msg("gate.repair.supplement_suggestion_items"),
        "supplement_suggestion_intake_links": localization.msg("gate.repair.supplement_suggestion_intake_links"),
        "supplement_intake_items": localization.msg("gate.repair.supplement_intake_items"),
        "supplement_landing_links": localization.msg("gate.repair.supplement_landing_links"),
    }
    for index, ((artifact, _comment_id), details) in enumerate(ordered, start=1):
        repairs.append(
            make_action(
                f"repair_{index:02d}",
                (
                    f"{instruction_map.get(artifact, localization.msg('gate.repair.default'))} "
                    f"{localization.msg('gate.repair.summary_suffix', details='; '.join(details))}"
                ),
                localization.msg("gate.repair.rationale"),
                target_map.get(artifact, ["review-master.db"]),
                recipe_id=recipe_map.get(artifact),
            )
        )
    return repairs


def build_current_state(
    workflow_state: sqlite3.Row | None,
    pending: list[str],
    blockers: list[str],
    has_validation_issues: bool,
    localization: LocalizationBundle,
) -> dict[str, Any]:
    if workflow_state is None:
        return {
            "current_stage": "unknown",
            "stage_gate": "blocked",
            "active_comment_id": None,
            "has_pending_user_confirmations": bool(pending),
            "has_global_blockers": bool(blockers),
            "has_validation_issues": has_validation_issues,
            "summary": localization.msg("gate.current_state.missing_workflow_summary"),
        }
    return {
        "current_stage": str(workflow_state["current_stage"]),
        "stage_gate": str(workflow_state["stage_gate"]),
        "active_comment_id": workflow_state["active_comment_id"],
        "has_pending_user_confirmations": bool(pending),
        "has_global_blockers": bool(blockers),
        "has_validation_issues": has_validation_issues,
        "summary": localization.msg(
            "current_state.summary",
            current_stage=str(workflow_state["current_stage"]),
            stage_gate=str(workflow_state["stage_gate"]),
            active_comment_id=repr(workflow_state["active_comment_id"]),
        ),
    }


def build_resume_packet(
    workflow_state: sqlite3.Row | None,
    resume_brief: sqlite3.Row | None,
    pending: list[str],
    blockers: list[str],
    resume_open_loops: list[str],
    resume_recent_decisions: list[str],
    resume_must_not_forget: list[str],
    current_state: dict[str, Any],
    recommended_next_action: dict[str, Any],
    localization: LocalizationBundle,
    runtime_language_context: dict[str, str],
) -> dict[str, Any]:
    runtime_digest = load_runtime_digest()
    base_packet = {
        "resume_status": "bootstrap",
        "is_bootstrap": True,
        "current_stage": current_state["current_stage"],
        "stage_gate": current_state["stage_gate"],
        "active_comment_id": current_state["active_comment_id"],
        "current_state_summary": current_state["summary"],
        "current_objective": localization.msg("bootstrap.resume.current_objective"),
        "current_focus": localization.msg("bootstrap.resume.current_focus"),
        "why_paused": localization.msg("bootstrap.resume.why_paused"),
        "next_operator_action": recommended_next_action["instruction"],
        "open_loops": list(resume_open_loops),
        "recent_decisions": list(resume_recent_decisions),
        "must_not_forget": list(resume_must_not_forget),
        "runtime_digest": runtime_digest,
        "language_context": runtime_language_context,
    }
    if resume_brief is not None:
        resume_status = str(resume_brief["resume_status"])
        base_packet.update(
            {
                "resume_status": resume_status,
                "is_bootstrap": resume_status == "bootstrap",
                "current_objective": str(resume_brief["current_objective"]),
                "current_focus": str(resume_brief["current_focus"]),
                "why_paused": str(resume_brief["why_paused"]),
                "next_operator_action": str(resume_brief["next_operator_action"]),
            }
        )
    if not base_packet["open_loops"]:
        if pending:
            base_packet["open_loops"] = [localization.msg("gate.allowed.request_pending_confirmation.reason") + f": {message}" for message in pending]
        elif blockers:
            base_packet["open_loops"] = [localization.msg("gate.allowed.resolve_global_blockers.reason") + f": {message}" for message in blockers]
    if workflow_state is None:
        base_packet["resume_status"] = "blocked"
        base_packet["is_bootstrap"] = False
        base_packet["why_paused"] = localization.msg("gate.blocked.missing_workflow.reason")

    resume_read_order = [
        localization.msg("resume.read_order.instruction_payload"),
        AGENT_RESUME_MD,
        localization.msg("resume.read_order.stage_view"),
        localization.msg("resume.read_order.stage_reference"),
    ]
    packet = build_default_resume_packet_for_emit(base_packet, resume_read_order, recommended_next_action["action_id"])
    return packet


def build_default_resume_packet_for_emit(
    packet: dict[str, Any],
    resume_read_order: list[str],
    next_action_anchor: str,
) -> dict[str, Any]:
    return {
        "resume_status": str(packet["resume_status"]),
        "is_bootstrap": bool(packet["is_bootstrap"]),
        "current_stage": str(packet["current_stage"]),
        "stage_gate": str(packet["stage_gate"]),
        "active_comment_id": packet["active_comment_id"],
        "current_state_summary": str(packet["current_state_summary"]),
        "current_focus": str(packet["current_focus"]),
        "current_objective": str(packet["current_objective"]),
        "why_paused": str(packet["why_paused"]),
        "next_operator_action": str(packet["next_operator_action"]),
        "open_loops": [str(item) for item in packet["open_loops"]],
        "recent_decisions": [str(item) for item in packet["recent_decisions"]],
        "must_not_forget": [str(item) for item in packet["must_not_forget"]],
        "runtime_digest": str(packet["runtime_digest"]),
        "resume_read_order": resume_read_order,
        "next_action_anchor": next_action_anchor,
        "language_context": dict(packet.get("language_context", {})),
    }


def build_blocked_actions(
    workflow_state: sqlite3.Row | None,
    pending: list[str],
    blockers: list[str],
    comment_blocker_map: dict[str, list[str]],
    completion_map: dict[str, sqlite3.Row],
    export_artifact_map: dict[str, sqlite3.Row],
    localization: LocalizationBundle,
) -> list[dict[str, Any]]:
    if workflow_state is None:
        return [
            make_action(
                "blocked_until_db_state_fixed",
                localization.msg("gate.blocked.missing_workflow.instruction"),
                localization.msg("gate.blocked.missing_workflow.reason"),
                ["review-master.db"],
                recipe_id="recipe_stage1_set_entry_state",
            )
        ]

    current_stage = str(workflow_state["current_stage"])
    active_comment_id = str(workflow_state["active_comment_id"]) if workflow_state["active_comment_id"] is not None else None
    blocked: list[dict[str, Any]] = []
    if current_stage == "stage_3" and pending:
        blocked.append(
            make_action(
                "blocked_enter_stage_4",
                localization.msg("gate.blocked.stage3_pending.instruction"),
                localization.msg("gate.blocked.stage3_pending.reason"),
                ["review-master.db", REVIEW_COMMENT_COVERAGE_MD, THREAD_TO_ATOMIC_MAPPING_MD],
                recipe_id="recipe_stage3_clear_coverage_confirmation",
            )
        )
    if current_stage == "stage_4" and pending:
        blocked.append(
            make_action(
                "blocked_enter_stage_5",
                localization.msg("gate.blocked.stage4_pending.instruction"),
                localization.msg("gate.blocked.stage4_pending.reason"),
                ["review-master.db", ATOMIC_WORKBOARD_MD],
                recipe_id="recipe_stage4_set_pending_confirmations",
            )
        )
    if current_stage == "stage_5" and active_comment_id:
        if pending:
            blocked.append(
                make_action(
                    "blocked_execute_active_comment",
                    localization.msg("gate.blocked.active_comment_pending.instruction", active_comment_id=active_comment_id),
                    localization.msg("gate.blocked.active_comment_pending.reason"),
                    ["review-master.db", f"{STRATEGY_CARD_DIR}/{active_comment_id}.md", SUPPLEMENT_SUGGESTION_PLAN_MD],
                    recipe_id=None,
                )
            )
        if blockers or comment_blocker_map.get(active_comment_id):
            blocked.append(
                make_action(
                    "blocked_complete_active_comment",
                    localization.msg("gate.blocked.active_comment_blocker.instruction", active_comment_id=active_comment_id),
                    localization.msg("gate.blocked.active_comment_blocker.reason"),
                    ["review-master.db", SUPPLEMENT_INTAKE_PLAN_MD],
                    recipe_id="recipe_stage5_set_blockers",
                )
            )
    export_not_ready = any(str(row["export_ready"]) != "yes" for row in completion_map.values()) if completion_map else True
    if current_stage != "stage_6" or export_not_ready:
        blocked.append(
            make_action(
                "blocked_final_export",
                localization.msg("gate.blocked.stage6_final_export.instruction"),
                localization.msg("gate.blocked.stage6_final_export.reason"),
                ["review-master.db", FINAL_CHECKLIST_MD, RESPONSE_TABLE_PREVIEW_MD, RESPONSE_TABLE_PREVIEW_TEX],
                recipe_id="recipe_stage6_export_clean_manuscript",
            )
        )
    marked_status = export_artifact_map.get("marked_manuscript")
    if current_stage == "stage_6" and marked_status is not None and str(marked_status["artifact_status"]) != "exported":
        blocked.append(
            make_action(
                "blocked_clean_export_before_marked_review",
                localization.msg("gate.blocked.stage6_marked_first.instruction"),
                localization.msg("gate.blocked.stage6_marked_first.reason"),
                ["review-master.db", FINAL_CHECKLIST_MD],
                recipe_id="recipe_stage6_export_marked_manuscript",
            )
        )
    return blocked


def build_stage_actions(
    workflow_state: sqlite3.Row | None,
    pending: list[str],
    blockers: list[str],
    comment_blocker_map: dict[str, list[str]],
    atomic_map: dict[str, sqlite3.Row],
    atomic_state_map: dict[str, sqlite3.Row],
    strategy_map: dict[str, sqlite3.Row],
    completion_map: dict[str, sqlite3.Row],
    comment_to_action_ids: dict[str, list[str]],
    action_location_orders: dict[tuple[str, int], list[int]],
    manuscript_draft_map: dict[tuple[str, int, int], sqlite3.Row],
    response_draft_map: dict[str, sqlite3.Row],
    style_profile_map: dict[str, sqlite3.Row],
    style_rule_count_by_target: dict[str, int],
    action_variant_labels: dict[tuple[str, int, int], set[str]],
    selected_variant_map: dict[tuple[str, int, int], str],
    response_thread_row_map: dict[str, sqlite3.Row],
    export_patch_set_map: dict[str, sqlite3.Row],
    export_patch_count_map: dict[str, int],
    export_artifact_map: dict[str, sqlite3.Row],
    stage3_coverage_advisories: list[str],
    localization: LocalizationBundle,
) -> list[dict[str, Any]]:
    if workflow_state is None:
        return [
            make_action(
                "repair_workflow_state",
                localization.msg("gate.blocked.missing_workflow.instruction"),
                localization.msg("gate.blocked.missing_workflow.reason"),
                ["review-master.db"],
                recipe_id="recipe_stage1_set_entry_state",
            )
        ]

    current_stage = str(workflow_state["current_stage"])
    active_comment_id = str(workflow_state["active_comment_id"]) if workflow_state["active_comment_id"] is not None else None
    if pending:
        if current_stage == "stage_3":
            reason = localization.msg("gate.allowed.request_stage3_coverage_confirmation.reason")
            if stage3_coverage_advisories:
                reason = (
                    f"{reason} "
                    f"{localization.msg('gate.allowed.request_stage3_coverage_confirmation.advisory', count=len(stage3_coverage_advisories))}"
                )
            return [
                make_action(
                    "request_stage3_coverage_confirmation",
                    localization.msg("gate.allowed.request_stage3_coverage_confirmation.instruction"),
                    reason,
                    ["review-master.db", REVIEW_COMMENT_COVERAGE_MD, RAW_REVIEW_THREADS_MD, THREAD_TO_ATOMIC_MAPPING_MD],
                    recipe_id="recipe_stage3_clear_coverage_confirmation",
                )
            ]
        if current_stage == "stage_4":
            return [
                make_action(
                    "request_stage4_confirmation",
                    localization.msg("gate.allowed.stage4_request_confirmation.instruction"),
                    localization.msg("gate.allowed.stage4_request_confirmation.reason"),
                    ["review-master.db", ATOMIC_WORKBOARD_MD, THREAD_TO_ATOMIC_MAPPING_MD],
                    recipe_id="recipe_stage4_set_pending_confirmations",
                )
            ]
        if current_stage == "stage_5" and active_comment_id:
            return [
                make_action(
                    "request_pending_confirmation",
                    localization.msg("gate.allowed.request_pending_confirmation.instruction"),
                    localization.msg("gate.allowed.request_pending_confirmation.reason"),
                    ["review-master.db", f"{STRATEGY_CARD_DIR}/{active_comment_id}.md", SUPPLEMENT_SUGGESTION_PLAN_MD],
                    recipe_id="recipe_stage5_confirm_strategy",
                )
            ]
        return [
            make_action(
                "request_pending_confirmation",
                localization.msg("gate.allowed.request_pending_confirmation.instruction"),
                localization.msg("gate.allowed.request_pending_confirmation.reason"),
                ["review-master.db"],
                recipe_id=None,
            )
        ]
    if blockers:
        return [
            make_action(
                "resolve_blockers",
                localization.msg("gate.allowed.resolve_global_blockers.instruction"),
                localization.msg("gate.allowed.resolve_global_blockers.reason"),
                ["review-master.db", SUPPLEMENT_INTAKE_PLAN_MD],
                recipe_id="recipe_stage5_set_blockers",
            )
        ]
    if current_stage == "stage_1":
        return [
            make_action(
                "enter_stage_2",
                localization.msg("gate.allowed.enter_stage_2.instruction"),
                localization.msg("gate.allowed.enter_stage_2.reason"),
                ["review-master.db", MANUSCRIPT_SUMMARY_MD],
                recipe_id="recipe_stage2_upsert_manuscript_summary",
            )
        ]
    if current_stage == "stage_2":
        return [
            make_action(
                "enter_stage_3",
                localization.msg("gate.allowed.enter_stage_3.instruction"),
                localization.msg("gate.allowed.enter_stage_3.reason"),
                ["review-master.db", RAW_REVIEW_THREADS_MD, ATOMIC_COMMENTS_MD, THREAD_TO_ATOMIC_MAPPING_MD],
                recipe_id="recipe_stage3_replace_threaded_atomic_model",
            )
        ]
    if current_stage == "stage_3":
        return [
            make_action(
                "enter_stage_4",
                localization.msg("gate.allowed.enter_stage_4.instruction"),
                localization.msg("gate.allowed.enter_stage_4.reason"),
                ["review-master.db", ATOMIC_WORKBOARD_MD],
                recipe_id="recipe_stage4_upsert_atomic_workboard",
            )
        ]
    if current_stage == "stage_4":
        ready_comment = next((comment_id for comment_id, row in atomic_state_map.items() if str(row["status"]) == "ready"), None)
        return [
            make_action(
                "enter_stage_5",
                localization.msg("gate.allowed.enter_stage_5.instruction", ready_comment=ready_comment or "next ready atomic comment"),
                localization.msg("gate.allowed.enter_stage_5.reason"),
                ["review-master.db", STRATEGY_CARD_DIR, SUPPLEMENT_SUGGESTION_PLAN_MD],
                recipe_id="recipe_stage5_set_active_comment",
            )
        ]
    if current_stage == "stage_5":
        if active_comment_id and active_comment_id not in strategy_map:
            return [
                make_action(
                    "author_strategy_card",
                    localization.msg("gate.allowed.author_strategy_card.instruction", active_comment_id=active_comment_id),
                    localization.msg("gate.allowed.author_strategy_card.reason"),
                    ["review-master.db", f"{STRATEGY_CARD_DIR}/{active_comment_id}.md", SUPPLEMENT_SUGGESTION_PLAN_MD],
                    recipe_id="recipe_stage5_upsert_strategy_card",
                )
            ]
        if active_comment_id:
            completion_row = completion_map.get(active_comment_id)
            strategy_confirmed = completion_row is not None and str(completion_row["user_strategy_confirmed"]) == "yes"
            has_manuscript_drafts = any(key[0] == active_comment_id for key in manuscript_draft_map)
            has_response_draft = active_comment_id in response_draft_map
            has_stage5_drafts = has_manuscript_drafts and has_response_draft
            other_comment = next(
                (
                    comment_id
                    for comment_id, row in atomic_state_map.items()
                    if comment_id != active_comment_id and str(row["status"]) != "done"
                ),
                None,
            )
            actions = []
            if not strategy_confirmed:
                actions.append(
                    make_action(
                        "request_pending_confirmation",
                        localization.msg("gate.allowed.request_pending_confirmation.instruction"),
                        localization.msg("gate.allowed.request_pending_confirmation.reason"),
                        ["review-master.db", f"{STRATEGY_CARD_DIR}/{active_comment_id}.md", SUPPLEMENT_SUGGESTION_PLAN_MD],
                        recipe_id="recipe_stage5_confirm_strategy",
                    )
                )
            elif not has_stage5_drafts:
                actions.append(
                    make_action(
                        "author_comment_drafts",
                        localization.msg("gate.allowed.author_comment_drafts.instruction", active_comment_id=active_comment_id),
                        localization.msg("gate.allowed.author_comment_drafts.reason"),
                        ["review-master.db", f"{STRATEGY_CARD_DIR}/{active_comment_id}.md", SUPPLEMENT_SUGGESTION_PLAN_MD],
                        recipe_id="recipe_stage5_replace_execution_drafts",
                    )
                )
            elif comment_blocker_map.get(active_comment_id):
                actions.append(
                    make_action(
                        "resolve_blockers",
                        localization.msg("gate.allowed.resolve_comment_blockers.instruction", active_comment_id=active_comment_id),
                        localization.msg("gate.allowed.resolve_comment_blockers.reason"),
                        ["review-master.db", f"{STRATEGY_CARD_DIR}/{active_comment_id}.md", SUPPLEMENT_SUGGESTION_PLAN_MD, SUPPLEMENT_INTAKE_PLAN_MD],
                        recipe_id="recipe_stage5_replace_comment_blockers",
                    )
                )
            else:
                actions.append(
                    make_action(
                        "advance_active_comment",
                        localization.msg("gate.allowed.advance_active_comment.instruction", active_comment_id=active_comment_id),
                        localization.msg("gate.allowed.advance_active_comment.reason"),
                        ["review-master.db", f"{STRATEGY_CARD_DIR}/{active_comment_id}.md", SUPPLEMENT_SUGGESTION_PLAN_MD, SUPPLEMENT_INTAKE_PLAN_MD],
                        recipe_id="recipe_stage5_upsert_completion_status",
                    )
                )
            if other_comment is not None:
                actions.append(
                    make_action(
                        "set_active_comment",
                        localization.msg("gate.allowed.set_active_comment.instruction", other_comment=other_comment),
                        localization.msg("gate.allowed.set_active_comment.reason"),
                        ["review-master.db", ATOMIC_WORKBOARD_MD, STRATEGY_CARD_DIR],
                        recipe_id="recipe_stage5_set_active_comment",
                    )
                )
            return actions
        next_comment = next((comment_id for comment_id, row in atomic_state_map.items() if str(row["status"]) == "ready"), None)
        return [
            make_action(
                "set_active_comment",
                localization.msg("gate.allowed.set_next_active_comment.instruction", next_comment=next_comment or "next ready atomic comment"),
                localization.msg("gate.allowed.set_next_active_comment.reason"),
                ["review-master.db"],
                recipe_id="recipe_stage5_set_active_comment",
            )
        ]
    if current_stage == "stage_6":
        missing_style = False
        for profile_target in ("manuscript", "response_letter"):
            row = style_profile_map.get(profile_target)
            if row is None or not str(row["profile_summary"]).strip() or style_rule_count_by_target.get(profile_target, 0) == 0:
                missing_style = True
        if missing_style:
            return [
                make_action(
                    "author_style_profiles",
                    localization.msg("gate.allowed.stage6_style_profile.instruction"),
                    localization.msg("gate.allowed.stage6_style_profile.reason"),
                    ["review-master.db", STYLE_PROFILE_MD],
                    recipe_id="recipe_stage6_upsert_style_profiles",
                )
            ]
        for comment_id, action_orders in comment_to_action_ids.items():
            for action_order_text in action_orders:
                action_order = int(action_order_text)
                for location_order in action_location_orders.get((comment_id, action_order), []):
                    labels = action_variant_labels.get((comment_id, action_order, location_order), set())
                    if labels != {"v1", "v2", "v3"}:
                        return [
                            make_action(
                                "generate_action_copy_variants",
                                localization.msg("gate.allowed.stage6_generate_variants.instruction"),
                                localization.msg("gate.allowed.stage6_generate_variants.reason"),
                                ["review-master.db", ACTION_COPY_VARIANTS_MD],
                                recipe_id="recipe_stage6_replace_action_copy_variants",
                            )
                        ]
        for comment_id, action_orders in comment_to_action_ids.items():
            for action_order_text in action_orders:
                action_order = int(action_order_text)
                for location_order in action_location_orders.get((comment_id, action_order), []):
                    if (comment_id, action_order, location_order) not in selected_variant_map:
                        return [
                            make_action(
                                "request_variant_selection",
                                localization.msg("gate.allowed.stage6_select_variants.instruction"),
                                localization.msg("gate.allowed.stage6_select_variants.reason"),
                                ["review-master.db", ACTION_COPY_VARIANTS_MD],
                                recipe_id="recipe_stage6_select_action_copy_variants",
                            )
                        ]
        if len(response_thread_row_map) == 0:
            return [
                make_action(
                    "assemble_response_thread_rows",
                    localization.msg("gate.allowed.stage6_build_rows.instruction"),
                    localization.msg("gate.allowed.stage6_build_rows.reason"),
                    ["review-master.db", RESPONSE_LETTER_OUTLINE_MD, RESPONSE_TABLE_PREVIEW_MD, RESPONSE_TABLE_PREVIEW_TEX],
                    recipe_id="recipe_stage6_upsert_response_thread_rows",
                )
            ]
        patch_set_by_kind = {str(row["artifact_kind"]): patch_set_id for patch_set_id, row in export_patch_set_map.items()}
        marked_patch_ready = False
        clean_patch_ready = False
        marked_patch_set_id = patch_set_by_kind.get("marked_manuscript")
        clean_patch_set_id = patch_set_by_kind.get("clean_manuscript")
        if marked_patch_set_id is not None and export_patch_count_map.get(marked_patch_set_id, 0) > 0:
            marked_patch_ready = True
        if clean_patch_set_id is not None and export_patch_count_map.get(clean_patch_set_id, 0) > 0:
            clean_patch_ready = True
        if not marked_patch_ready or not clean_patch_ready:
            return [
                make_action(
                    "prepare_export_patches",
                    localization.msg("gate.allowed.stage6_build_patch_sets.instruction"),
                    localization.msg("gate.allowed.stage6_build_patch_sets.reason"),
                    ["review-master.db", EXPORT_PATCH_PLAN_MD],
                    recipe_id="recipe_stage6_replace_export_patches",
                )
            ]
        marked_row = export_artifact_map.get("marked_manuscript")
        if marked_row is None or str(marked_row["artifact_status"]) != "exported":
            return [
                make_action(
                    "export_marked_manuscript",
                    localization.msg("gate.allowed.stage6_export_marked.instruction"),
                    localization.msg("gate.allowed.stage6_export_marked.reason"),
                    ["review-master.db", EXPORT_PATCH_PLAN_MD, FINAL_CHECKLIST_MD],
                    recipe_id="recipe_stage6_export_marked_manuscript",
                )
            ]
        clean_ready = all(
            export_artifact_map.get(name) is not None and str(export_artifact_map[name]["artifact_status"]) == "exported"
            for name in ("clean_manuscript", "response_markdown", "response_latex")
        )
        if not clean_ready:
            return [
                make_action(
                    "final_review_and_clean_export",
                    localization.msg("gate.allowed.stage6_export_clean.instruction"),
                    localization.msg("gate.allowed.stage6_export_clean.reason"),
                    ["review-master.db", EXPORT_PATCH_PLAN_MD, FINAL_CHECKLIST_MD, RESPONSE_TABLE_PREVIEW_MD, RESPONSE_TABLE_PREVIEW_TEX],
                    recipe_id="recipe_stage6_export_clean_manuscript",
                )
            ]
        return [
            make_action(
                "stage_6_completed",
                localization.msg("gate.allowed.stage6_completed.instruction"),
                localization.msg("gate.allowed.stage6_completed.reason"),
                ["review-master.db", EXPORT_PATCH_PLAN_MD, FINAL_CHECKLIST_MD, RESPONSE_TABLE_PREVIEW_MD, RESPONSE_TABLE_PREVIEW_TEX],
                recipe_id="recipe_stage6_export_clean_manuscript",
            )
        ]
    return [
        make_action(
            "inspect_state_machine",
            localization.msg("gate.allowed.unknown_state.instruction"),
            localization.msg("gate.allowed.unknown_state.reason"),
            ["review-master.db"],
            recipe_id="recipe_stage1_set_entry_state",
        )
    ]


def build_instruction_payload(
    workflow_state: sqlite3.Row | None,
    resume_brief: sqlite3.Row | None,
    pending: list[str],
    blockers: list[str],
    comment_blocker_map: dict[str, list[str]],
    resume_open_loops: list[str],
    resume_recent_decisions: list[str],
    resume_must_not_forget: list[str],
    atomic_map: dict[str, sqlite3.Row],
    atomic_state_map: dict[str, sqlite3.Row],
    strategy_map: dict[str, sqlite3.Row],
    completion_map: dict[str, sqlite3.Row],
    comment_to_action_ids: dict[str, list[str]],
    action_location_orders: dict[tuple[str, int], list[int]],
    manuscript_draft_map: dict[tuple[str, int, int], sqlite3.Row],
    response_draft_map: dict[str, sqlite3.Row],
    style_profile_map: dict[str, sqlite3.Row],
    style_rule_count_by_target: dict[str, int],
    action_variant_labels: dict[tuple[str, int, int], set[str]],
    selected_variant_map: dict[tuple[str, int, int], str],
    response_thread_row_map: dict[str, sqlite3.Row],
    export_patch_set_map: dict[str, sqlite3.Row],
    export_patch_count_map: dict[str, int],
    export_artifact_map: dict[str, sqlite3.Row],
    stage3_coverage_advisories: list[str],
    stage3_coverage_metrics: dict[str, Any],
    format_errors: list[dict[str, Any]],
    dependency_errors: list[dict[str, Any]],
    consistency_errors: list[dict[str, Any]],
    localization: LocalizationBundle,
    runtime_language_context: dict[str, str],
) -> dict[str, Any]:
    repair_sequence = build_repair_sequence(format_errors, dependency_errors, consistency_errors, localization)
    current_state = build_current_state(workflow_state, pending, blockers, bool(repair_sequence), localization)
    blocked_actions = build_blocked_actions(
        workflow_state,
        pending,
        blockers,
        comment_blocker_map,
        completion_map,
        export_artifact_map,
        localization,
    )
    if repair_sequence:
        allowed_next_actions = repair_sequence
        recommended_next_action = repair_sequence[0]
    else:
        allowed_next_actions = build_stage_actions(
            workflow_state,
            pending,
            blockers,
            comment_blocker_map,
            atomic_map,
            atomic_state_map,
            strategy_map,
            completion_map,
            comment_to_action_ids,
            action_location_orders,
            manuscript_draft_map,
            response_draft_map,
            style_profile_map,
            style_rule_count_by_target,
            action_variant_labels,
            selected_variant_map,
            response_thread_row_map,
            export_patch_set_map,
            export_patch_count_map,
            export_artifact_map,
            stage3_coverage_advisories,
            localization,
        )
        recommended_next_action = allowed_next_actions[0]
    resume_packet = build_resume_packet(
        workflow_state,
        resume_brief,
        pending,
        blockers,
        resume_open_loops,
        resume_recent_decisions,
        resume_must_not_forget,
        current_state,
        recommended_next_action,
        localization,
        runtime_language_context,
    )
    return {
        "current_state": current_state,
        "resume_packet": resume_packet,
        "allowed_next_actions": allowed_next_actions,
        "recommended_next_action": recommended_next_action,
        "repair_sequence": repair_sequence,
        "blocked_actions": blocked_actions,
        "coverage_review_advisories": stage3_coverage_advisories,
        "coverage_review_metrics": stage3_coverage_metrics,
    }


def main() -> int:
    args = parse_args()
    artifact_root = Path(args.artifact_root).expanduser()
    if not artifact_root.exists():
        return emit({"status": "error", "error": f"artifact root does not exist: {artifact_root}"}, exit_code=1)
    if not artifact_root.is_dir():
        return emit({"status": "error", "error": f"artifact root is not a directory: {artifact_root}"}, exit_code=1)

    presence, paths = build_presence_report(artifact_root)
    db_path = paths["db"]
    if not db_path.exists():
        return emit(
            {
                "status": "error",
                "error": f"database does not exist: {db_path}",
                "artifact_presence": presence,
            },
            exit_code=1,
        )

    format_errors: list[dict[str, Any]] = []
    dependency_errors: list[dict[str, Any]] = []
    consistency_errors: list[dict[str, Any]] = []
    workflow_state: sqlite3.Row | None = None
    resume_brief: sqlite3.Row | None = None
    pending: list[str] = []
    blockers: list[str] = []
    resume_open_loops: list[str] = []
    resume_recent_decisions: list[str] = []
    resume_must_not_forget: list[str] = []
    review_comment_source_document_map: dict[str, sqlite3.Row] = {}
    raw_thread_source_span_map: dict[tuple[str, str, int], sqlite3.Row] = {}
    thread_to_source_span_keys: dict[str, list[tuple[str, str, int]]] = {}
    legacy_source_documents: list[str] = []
    raw_thread_map: dict[str, sqlite3.Row] = {}
    atomic_map: dict[str, sqlite3.Row] = {}
    atomic_state_map: dict[str, sqlite3.Row] = {}
    strategy_map: dict[str, sqlite3.Row] = {}
    completion_map: dict[str, sqlite3.Row] = {}
    thread_to_comment_ids: dict[str, list[str]] = {}
    comment_to_thread_ids: dict[str, list[str]] = {}
    comment_to_target_locations: dict[str, list[str]] = {}
    comment_to_analysis_ids: dict[str, list[str]] = {}
    comment_to_action_ids: dict[str, list[str]] = {}
    action_location_orders: dict[tuple[str, int], list[int]] = {}
    manuscript_draft_map: dict[tuple[str, int, int], sqlite3.Row] = {}
    response_draft_map: dict[str, sqlite3.Row] = {}
    thread_to_resolution_comment_ids: dict[str, list[str]] = {}
    comment_blocker_map: dict[str, list[str]] = {}
    style_profile_map: dict[str, sqlite3.Row] = {}
    style_rule_count_by_target: dict[str, int] = {}
    action_variant_labels: dict[tuple[str, int, int], set[str]] = {}
    selected_variant_map: dict[tuple[str, int, int], str] = {}
    response_thread_row_map: dict[str, sqlite3.Row] = {}
    export_patch_set_map: dict[str, sqlite3.Row] = {}
    export_patch_count_map: dict[str, int] = {}
    export_artifact_map: dict[str, sqlite3.Row] = {}
    stage3_coverage_advisories: list[str] = []
    stage3_coverage_metrics: dict[str, Any] = {
        "metric_type": "character_coverage",
        "scope": "global",
        "counts_include_whitespace": True,
        "includes_duplicate_filtered": True,
        "thresholds": {
            "hard_percent": STAGE3_COVERAGE_HARD_THRESHOLD,
            "soft_percent": STAGE3_COVERAGE_SOFT_THRESHOLD,
            "unit": "percent",
        },
        "global": {
            "total_chars": 0,
            "covered_chars_including_duplicates": 0,
            "covered_chars_non_duplicate": 0,
            "coverage_percent_including_duplicates": 0.0,
            "coverage_percent_non_duplicate": 0.0,
        },
        "per_document": [],
        "gate_status": "not_applicable",
    }
    runtime_language_context = {
        "document_language": "en",
        "working_language": "en",
        "manuscript_detected_language": "",
        "review_comments_detected_language": "",
        "prompt_detected_language": "",
        "document_language_source": "",
        "working_language_source": "",
        "languages_confirmed": "no",
    }

    try:
        with connect_db(db_path) as connection:
            ensure_runtime_schema_compatibility(connection)
            validate_schema(connection, db_path, format_errors)
            runtime_language_context = fetch_runtime_language_context(connection)
            (
                workflow_state,
                resume_brief,
                pending,
                blockers,
                resume_open_loops,
                resume_recent_decisions,
                resume_must_not_forget,
                review_comment_source_document_map,
                raw_thread_source_span_map,
                thread_to_source_span_keys,
                legacy_source_documents,
                raw_thread_map,
                atomic_map,
                atomic_state_map,
                strategy_map,
                completion_map,
                thread_to_comment_ids,
                comment_to_thread_ids,
                comment_to_target_locations,
                comment_to_analysis_ids,
                comment_to_action_ids,
                action_location_orders,
                manuscript_draft_map,
                response_draft_map,
                thread_to_resolution_comment_ids,
                comment_blocker_map,
                style_profile_map,
                style_rule_count_by_target,
                action_variant_labels,
                selected_variant_map,
                response_thread_row_map,
                export_patch_set_map,
                export_patch_count_map,
                export_artifact_map,
                supplement_suggestion_map,
                supplement_suggestion_count_by_comment,
                stage3_coverage_advisories,
                content_errors,
            ) = validate_database_content(connection, db_path)
            stage3_coverage_metrics = build_stage3_character_coverage_metrics(
                connection,
                hard_threshold=STAGE3_COVERAGE_HARD_THRESHOLD,
                soft_threshold=STAGE3_COVERAGE_SOFT_THRESHOLD,
            )
            format_errors.extend(content_errors)
    except sqlite3.DatabaseError as exc:
        return emit({"status": "error", "error": f"sqlite error: {exc}"}, exit_code=1)

    localization = load_localization_bundle(
        artifact_root,
        runtime_context=runtime_language_context,
    )

    stage_num = workflow_stage_number(workflow_state)
    active_comment_id = str(workflow_state["active_comment_id"]) if workflow_state is not None and workflow_state["active_comment_id"] is not None else None
    dependency_errors.extend(
        validate_dependencies(
            db_path,
            stage_num,
            active_comment_id,
            review_comment_source_document_map,
            raw_thread_source_span_map,
            thread_to_source_span_keys,
            legacy_source_documents,
            raw_thread_map,
            atomic_map,
            atomic_state_map,
            strategy_map,
            completion_map,
            thread_to_comment_ids,
            comment_to_thread_ids,
            comment_to_target_locations,
            comment_to_analysis_ids,
            action_location_orders,
            manuscript_draft_map,
            response_draft_map,
            thread_to_resolution_comment_ids,
            comment_to_action_ids,
            style_profile_map,
            style_rule_count_by_target,
            action_variant_labels,
            selected_variant_map,
            response_thread_row_map,
            export_patch_set_map,
            export_patch_count_map,
            export_artifact_map,
            supplement_suggestion_count_by_comment,
            stage3_coverage_metrics,
        )
    )
    if (
        stage_num >= 3
        and str(stage3_coverage_metrics.get("gate_status", "")) == "soft_warn"
    ):
        global_metrics = stage3_coverage_metrics.get("global", {})
        thresholds = stage3_coverage_metrics.get("thresholds", {})
        stage3_coverage_advisories.append(
            localization.msg(
                "gate.stage3.coverage.soft_advisory",
                coverage_percent=f"{float(global_metrics.get('coverage_percent_including_duplicates', 0.0)):.2f}",
                hard_threshold=f"{float(thresholds.get('hard_percent', STAGE3_COVERAGE_HARD_THRESHOLD)):.2f}",
                soft_threshold=f"{float(thresholds.get('soft_percent', STAGE3_COVERAGE_SOFT_THRESHOLD)):.2f}",
                covered_chars=int(global_metrics.get("covered_chars_including_duplicates", 0)),
                total_chars=int(global_metrics.get("total_chars", 0)),
            )
        )
    consistency_errors.extend(
        validate_consistency(
            db_path,
            workflow_state,
            resume_brief,
            pending,
            blockers,
            resume_open_loops,
            resume_recent_decisions,
            resume_must_not_forget,
            review_comment_source_document_map,
            raw_thread_source_span_map,
            raw_thread_map,
            atomic_map,
            atomic_state_map,
            strategy_map,
            completion_map,
            thread_to_comment_ids,
            thread_to_resolution_comment_ids,
            comment_blocker_map,
            style_profile_map,
            style_rule_count_by_target,
            action_variant_labels,
            selected_variant_map,
            response_thread_row_map,
            export_patch_set_map,
            export_patch_count_map,
            export_artifact_map,
            supplement_suggestion_count_by_comment,
            manuscript_draft_map,
            response_draft_map,
        )
    )
    instruction_payload = build_instruction_payload(
        workflow_state,
        resume_brief,
        pending,
        blockers,
        comment_blocker_map,
        resume_open_loops,
        resume_recent_decisions,
        resume_must_not_forget,
        atomic_map,
        atomic_state_map,
        strategy_map,
        completion_map,
        comment_to_action_ids,
        action_location_orders,
        manuscript_draft_map,
        response_draft_map,
        style_profile_map,
        style_rule_count_by_target,
        action_variant_labels,
        selected_variant_map,
        response_thread_row_map,
        export_patch_set_map,
        export_patch_count_map,
        export_artifact_map,
        stage3_coverage_advisories,
        stage3_coverage_metrics,
        format_errors,
        dependency_errors,
        consistency_errors,
        localization,
        runtime_language_context,
    )
    resume_render_context = {
        "resume_status": instruction_payload["resume_packet"]["resume_status"],
        "is_bootstrap": "yes" if instruction_payload["resume_packet"]["is_bootstrap"] else "no",
        "current_stage": instruction_payload["resume_packet"]["current_stage"],
        "stage_gate": instruction_payload["resume_packet"]["stage_gate"],
        "active_comment_id": instruction_payload["resume_packet"]["active_comment_id"] or "None",
        "current_state_summary": instruction_payload["resume_packet"]["current_state_summary"],
        "current_objective": instruction_payload["resume_packet"]["current_objective"],
        "current_focus": instruction_payload["resume_packet"]["current_focus"],
        "why_paused": instruction_payload["resume_packet"]["why_paused"],
        "next_operator_action": instruction_payload["resume_packet"]["next_operator_action"],
        "open_loops": instruction_payload["resume_packet"]["open_loops"],
        "recent_decisions": instruction_payload["resume_packet"]["recent_decisions"],
        "must_not_forget": instruction_payload["resume_packet"]["must_not_forget"],
        "runtime_digest": instruction_payload["resume_packet"]["runtime_digest"],
        "resume_read_order": instruction_payload["resume_packet"]["resume_read_order"],
        "next_action_anchor": instruction_payload["resume_packet"]["next_action_anchor"],
        "language_context": instruction_payload["resume_packet"]["language_context"],
    }
    try:
        render_workspace(db_path, artifact_root, resume_context=resume_render_context)
    except (OSError, RuntimeError, ValueError) as exc:
        return emit({"status": "error", "error": f"render error: {exc}"}, exit_code=1)

    presence, _ = build_presence_report(artifact_root)
    issue_count = len(format_errors) + len(dependency_errors) + len(consistency_errors)
    status = "ok" if issue_count == 0 else "issues_found"
    summary = {
        "artifact_root": str(artifact_root.resolve()),
        "database_path": str(db_path.resolve()),
        "format_error_count": len(format_errors),
        "dependency_error_count": len(dependency_errors),
        "consistency_error_count": len(consistency_errors),
        "total_issue_count": issue_count,
    }
    return emit(
        {
            "status": status,
            "summary": summary,
            "artifact_presence": presence,
            "format_errors": format_errors,
            "dependency_errors": dependency_errors,
            "consistency_errors": consistency_errors,
            "instruction_payload": instruction_payload,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())

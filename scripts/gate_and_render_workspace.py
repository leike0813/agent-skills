from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

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
    ALLOWED_SOURCE_TYPE,
    ALLOWED_STAGE,
    ALLOWED_STAGE_GATE,
    ALLOWED_STATUS,
    ALLOWED_SUPPLEMENT_DECISION,
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
    RESPONSE_LETTER_OUTLINE_MD,
    SUPPLEMENT_INTAKE_PLAN_MD,
    RESPONSE_TABLE_PREVIEW_MD,
    RESPONSE_TABLE_PREVIEW_TEX,
    STYLE_PROFILE_MD,
    STRATEGY_CARD_DIR,
    TARGET_LOCATION_RE,
    THREAD_TO_ATOMIC_MAPPING_MD,
    artifact_paths,
    connect_db,
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


def load_supporting_maps(connection: sqlite3.Connection) -> dict[str, Any]:
    raw_thread_links = fetch_all(
        connection,
        "SELECT thread_id, comment_id, link_order FROM raw_thread_atomic_links ORDER BY thread_id, link_order, comment_id",
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
    supplement_landing_links = fetch_all(
        connection,
        """
        SELECT round_id, file_path, comment_id, action_order, location_order, planned_usage_note
        FROM supplement_landing_links
        ORDER BY round_id, file_path, comment_id, action_order, location_order
        """,
    )
    return {
        "raw_thread_links": raw_thread_links,
        "atomic_source_spans": atomic_source_spans,
        "target_locations": target_locations,
        "analysis_links": analysis_links,
        "strategy_action_locations": strategy_action_locations,
        "response_links": response_links,
        "style_profiles": style_profiles,
        "style_rules": style_rules,
        "action_copy_variants": action_copy_variants,
        "selected_action_copy_variants": selected_action_copy_variants,
        "response_thread_rows": response_thread_rows,
        "export_patch_sets": export_patch_sets,
        "export_patches": export_patches,
        "export_artifacts": export_artifacts,
        "supplement_intake_items": supplement_intake_items,
        "supplement_landing_links": supplement_landing_links,
    }


def validate_database_content(
    connection: sqlite3.Connection,
    db_path: Path,
) -> tuple[
    sqlite3.Row | None,
    sqlite3.Row | None,
    list[str],
    list[str],
    list[str],
    list[str],
    list[str],
    dict[str, sqlite3.Row],
    dict[str, sqlite3.Row],
    dict[str, sqlite3.Row],
    dict[str, sqlite3.Row],
    dict[str, sqlite3.Row],
    dict[str, list[str]],
    dict[str, list[str]],
    dict[str, list[str]],
    dict[str, list[str]],
    dict[str, list[str]],
    dict[tuple[str, int], list[int]],
    dict[str, list[str]],
    dict[str, sqlite3.Row],
    dict[str, int],
    dict[tuple[str, int, int], set[str]],
    dict[tuple[str, int, int], str],
    dict[str, sqlite3.Row],
    dict[str, sqlite3.Row],
    dict[str, int],
    dict[str, sqlite3.Row],
    list[dict[str, Any]],
]:
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
        SELECT comment_id, manuscript_change_done, response_section_done, evidence_gap_closed,
               user_strategy_confirmed, one_to_one_link_checked, export_ready
        FROM comment_completion_status
        ORDER BY comment_id
        """,
    )
    completion_map = {str(row["comment_id"]): row for row in completion_rows}
    for row in completion_rows:
        comment_id = str(row["comment_id"])
        for field in (
            "manuscript_change_done",
            "response_section_done",
            "evidence_gap_closed",
            "user_strategy_confirmed",
            "one_to_one_link_checked",
            "export_ready",
        ):
            value = str(row[field])
            if value not in ALLOWED_YES_NO:
                add_issue(format_errors, "comment_completion_status", "invalid_enum", f"{field}='{value}' is not allowed", path=db_path, comment_id=comment_id)
        if str(row["export_ready"]) == "yes":
            for field in ("manuscript_change_done", "response_section_done", "one_to_one_link_checked"):
                if str(row[field]) != "yes":
                    add_issue(
                        format_errors,
                        "comment_completion_status",
                        "invalid_gate_state",
                        f"export_ready cannot be yes when {field} is not yes",
                        path=db_path,
                        comment_id=comment_id,
                    )

    support = load_supporting_maps(connection)
    thread_to_comment_ids: dict[str, list[str]] = defaultdict(list)
    comment_to_thread_ids: dict[str, list[str]] = defaultdict(list)
    comment_to_target_locations: dict[str, list[str]] = defaultdict(list)
    comment_to_analysis_ids: dict[str, list[str]] = defaultdict(list)
    comment_to_action_ids: dict[str, list[str]] = defaultdict(list)
    action_location_orders: dict[tuple[str, int], list[int]] = defaultdict(list)
    thread_to_resolution_comment_ids: dict[str, list[str]] = defaultdict(list)
    style_profile_map: dict[str, sqlite3.Row] = {}
    style_rule_count_by_target: dict[str, int] = defaultdict(int)
    action_variant_labels: dict[tuple[str, int, int], set[str]] = defaultdict(set)
    selected_variant_map: dict[tuple[str, int, int], str] = {}
    response_thread_row_map: dict[str, sqlite3.Row] = {}
    export_patch_set_map: dict[str, sqlite3.Row] = {}
    export_patch_count_map: dict[str, int] = {}
    export_artifact_map: dict[str, sqlite3.Row] = {}

    for row in support["raw_thread_links"]:
        thread_id = str(row["thread_id"])
        comment_id = str(row["comment_id"])
        thread_to_comment_ids[thread_id].append(comment_id)
        comment_to_thread_ids[comment_id].append(thread_id)

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

    return (
        workflow_state,
        resume_brief,
        pending,
        blockers,
        resume_open_loops,
        resume_recent_decisions,
        resume_must_not_forget,
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
        dict(thread_to_resolution_comment_ids),
        style_profile_map,
        dict(style_rule_count_by_target),
        dict(action_variant_labels),
        selected_variant_map,
        response_thread_row_map,
        export_patch_set_map,
        export_patch_count_map,
        export_artifact_map,
        format_errors,
    )


def validate_dependencies(
    db_path: Path,
    stage_number: int,
    active_comment_id: str | None,
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
) -> list[dict[str, Any]]:
    dependency_errors: list[dict[str, Any]] = []
    raw_thread_ids = set(raw_thread_map)
    atomic_ids = set(atomic_map)

    if stage_number >= 3:
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
    raw_thread_map: dict[str, sqlite3.Row],
    atomic_map: dict[str, sqlite3.Row],
    atomic_state_map: dict[str, sqlite3.Row],
    strategy_map: dict[str, sqlite3.Row],
    completion_map: dict[str, sqlite3.Row],
    thread_to_comment_ids: dict[str, list[str]],
    thread_to_resolution_comment_ids: dict[str, list[str]],
    style_profile_map: dict[str, sqlite3.Row],
    style_rule_count_by_target: dict[str, int],
    action_variant_labels: dict[tuple[str, int, int], set[str]],
    selected_variant_map: dict[tuple[str, int, int], str],
    response_thread_row_map: dict[str, sqlite3.Row],
    export_patch_set_map: dict[str, sqlite3.Row],
    export_patch_count_map: dict[str, int],
    export_artifact_map: dict[str, sqlite3.Row],
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
    if current_stage == "stage_4":
        if not atomic_state_map:
            add_issue(consistency_errors, "workflow_state", "stage_gate_without_authored_prerequisites", "stage_4 is ready but atomic_comment_state is empty", path=db_path)
    if current_stage == "stage_5":
        if not active_comment_id:
            add_issue(consistency_errors, "workflow_state", "missing_active_comment", "stage_5 requires active_comment_id", path=db_path)
        if active_comment_id and active_comment_id not in strategy_map and not pending and not blockers:
            add_issue(consistency_errors, "workflow_state", "stage_gate_without_authored_prerequisites", "stage_5 is ready but active comment has no strategy card", path=db_path, comment_id=active_comment_id)
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
        "atomic_comment_state": "recipe_stage4_upsert_atomic_workboard",
        "atomic_comment_target_locations": "recipe_stage4_upsert_atomic_workboard",
        "atomic_comment_analysis_links": "recipe_stage4_upsert_atomic_workboard",
        "strategy_cards": "recipe_stage5_upsert_strategy_card",
        "comment_completion_status": "recipe_stage5_upsert_completion_status",
        "response_thread_resolution_links": "recipe_stage6_upsert_response_thread_rows",
        "style_profiles": "recipe_stage6_upsert_style_profiles",
        "style_profile_rules": "recipe_stage6_upsert_style_profiles",
        "action_copy_variants": "recipe_stage6_replace_action_copy_variants",
        "selected_action_copy_variants": "recipe_stage6_select_action_copy_variants",
        "response_thread_rows": "recipe_stage6_upsert_response_thread_rows",
        "export_patch_sets": "recipe_stage6_replace_export_patches",
        "export_patches": "recipe_stage6_replace_export_patches",
        "export_artifacts": "recipe_stage6_export_marked_manuscript",
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
        "atomic_comment_state": ["review-master.db", ATOMIC_WORKBOARD_MD],
        "atomic_comment_target_locations": ["review-master.db", ATOMIC_WORKBOARD_MD],
        "atomic_comment_analysis_links": ["review-master.db", ATOMIC_WORKBOARD_MD],
        "strategy_cards": ["review-master.db", STRATEGY_CARD_DIR],
        "comment_completion_status": ["review-master.db", FINAL_CHECKLIST_MD],
        "response_thread_resolution_links": ["review-master.db", RESPONSE_LETTER_OUTLINE_MD, RESPONSE_TABLE_PREVIEW_MD],
        "style_profiles": ["review-master.db", STYLE_PROFILE_MD],
        "style_profile_rules": ["review-master.db", STYLE_PROFILE_MD],
        "action_copy_variants": ["review-master.db", ACTION_COPY_VARIANTS_MD],
        "selected_action_copy_variants": ["review-master.db", ACTION_COPY_VARIANTS_MD],
        "response_thread_rows": ["review-master.db", RESPONSE_TABLE_PREVIEW_MD, RESPONSE_TABLE_PREVIEW_TEX],
        "export_patch_sets": ["review-master.db", EXPORT_PATCH_PLAN_MD],
        "export_patches": ["review-master.db", EXPORT_PATCH_PLAN_MD],
        "export_artifacts": ["review-master.db", FINAL_CHECKLIST_MD],
        "supplement_intake_items": ["review-master.db", SUPPLEMENT_INTAKE_PLAN_MD],
        "supplement_landing_links": ["review-master.db", SUPPLEMENT_INTAKE_PLAN_MD],
    }
    instruction_map = {
        "workflow_state": "先在 review-master.db 中修正 workflow_state、pending confirmations 或 blockers 相关记录，再重新运行 gate-and-render 核心脚本并重渲染视图。",
        "resume_brief": "先在 review-master.db 中修正 resume_brief 的恢复摘要，再重新运行 gate-and-render 核心脚本并重渲染 agent-resume.md。",
        "resume_open_loops": "先在 review-master.db 中修正 resume_open_loops，再重新运行 gate-and-render 核心脚本并重渲染 agent-resume.md。",
        "resume_recent_decisions": "先在 review-master.db 中修正 resume_recent_decisions，再重新运行 gate-and-render 核心脚本并重渲染 agent-resume.md。",
        "resume_must_not_forget": "先在 review-master.db 中修正 resume_must_not_forget，再重新运行 gate-and-render 核心脚本并重渲染 agent-resume.md。",
        "manuscript_summary": "先在 review-master.db 中修正 manuscript_summary、manuscript_sections 或 manuscript_claims 相关记录，再重新运行 gate-and-render 核心脚本并重渲染视图。",
        "raw_review_threads": "先在 review-master.db 中修正 raw_review_threads 相关记录，再重新运行 gate-and-render 核心脚本并重渲染视图。",
        "atomic_comments": "先在 review-master.db 中修正 canonical atomic comments 相关记录，再重新运行 gate-and-render 核心脚本并重渲染视图。",
        "raw_thread_atomic_links": "先在 review-master.db 中修正 raw_thread_atomic_links 或 atomic_comment_source_spans 相关记录，再重新运行 gate-and-render 核心脚本并重渲染视图。",
        "atomic_comment_state": "先在 review-master.db 中修正 atomic_comment_state 相关记录，再重新运行 gate-and-render 核心脚本并重渲染视图。",
        "atomic_comment_target_locations": "先在 review-master.db 中修正 atomic_comment_target_locations 相关记录，再重新运行 gate-and-render 核心脚本并重渲染视图。",
        "atomic_comment_analysis_links": "先在 review-master.db 中修正 atomic_comment_analysis_links 相关记录，再重新运行 gate-and-render 核心脚本并重渲染视图。",
        "strategy_cards": "先在 review-master.db 中修正 strategy_cards、strategy_card_actions、strategy_action_target_locations、strategy_card_evidence_items 或 strategy_card_pending_confirmations 相关记录，再重新运行 gate-and-render 核心脚本并重渲染视图。",
        "comment_completion_status": "先在 review-master.db 中修正 comment_completion_status 相关记录，再重新运行 gate-and-render 核心脚本并重渲染视图。",
        "response_thread_resolution_links": "先在 review-master.db 中修正 response_thread_resolution_links 相关记录，再重新运行 gate-and-render 核心脚本并重渲染视图。",
        "style_profiles": "先在 review-master.db 中修正 style_profiles 与 style_profile_rules，再重新运行 gate-and-render 核心脚本并重渲染视图。",
        "style_profile_rules": "先在 review-master.db 中修正 style_profiles 与 style_profile_rules，再重新运行 gate-and-render 核心脚本并重渲染视图。",
        "action_copy_variants": "先在 review-master.db 中修正 action_copy_variants，再重新运行 gate-and-render 核心脚本并重渲染视图。",
        "selected_action_copy_variants": "先在 review-master.db 中修正 selected_action_copy_variants，再重新运行 gate-and-render 核心脚本并重渲染视图。",
        "response_thread_rows": "先在 review-master.db 中修正 response_thread_rows，再重新运行 gate-and-render 核心脚本并重渲染视图。",
        "export_patch_sets": "先在 review-master.db 中修正 export_patch_sets，再重新运行 gate-and-render 核心脚本并重渲染视图。",
        "export_patches": "先在 review-master.db 中修正 export_patches，再重新运行 gate-and-render 核心脚本并重渲染视图。",
        "export_artifacts": "先在 review-master.db 中修正 export_artifacts，再重新运行 gate-and-render 核心脚本并重渲染视图。",
        "supplement_intake_items": "先在 review-master.db 中修正 supplement_intake_items，再重新运行 gate-and-render 核心脚本并重渲染补材接收与落地方案视图。",
        "supplement_landing_links": "先在 review-master.db 中修正 supplement_landing_links，再重新运行 gate-and-render 核心脚本并重渲染补材接收与落地方案视图。",
    }
    for index, ((artifact, _comment_id), details) in enumerate(ordered, start=1):
        repairs.append(
            make_action(
                f"repair_{index:02d}",
                f"{instruction_map.get(artifact, '先修复 review-master.db 中的问题，再重新运行 gate-and-render 核心脚本。')} 问题包括：{'; '.join(details)}。",
                "修复顺序采用先上游后下游；先修数据库真源，再观察重渲染视图。",
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
) -> dict[str, Any]:
    if workflow_state is None:
        return {
            "current_stage": "unknown",
            "stage_gate": "blocked",
            "active_comment_id": None,
            "has_pending_user_confirmations": bool(pending),
            "has_global_blockers": bool(blockers),
            "has_validation_issues": has_validation_issues,
            "summary": "review-master.db 中缺少合法的 workflow_state，必须先修复数据库状态表。",
        }
    return {
        "current_stage": str(workflow_state["current_stage"]),
        "stage_gate": str(workflow_state["stage_gate"]),
        "active_comment_id": workflow_state["active_comment_id"],
        "has_pending_user_confirmations": bool(pending),
        "has_global_blockers": bool(blockers),
        "has_validation_issues": has_validation_issues,
        "summary": (
            f"当前处于 {workflow_state['current_stage']}，gate={workflow_state['stage_gate']}，"
            f"active_comment_id={workflow_state['active_comment_id']!r}，"
            f"pending_user_confirmations={len(pending)}，global_blockers={len(blockers)}，"
            f"validation_issues={'yes' if has_validation_issues else 'no'}。"
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
) -> dict[str, Any]:
    runtime_digest = load_runtime_digest()
    base_packet = {
        "resume_status": "bootstrap",
        "is_bootstrap": True,
        "current_stage": current_state["current_stage"],
        "stage_gate": current_state["stage_gate"],
        "active_comment_id": current_state["active_comment_id"],
        "current_state_summary": current_state["summary"],
        "current_objective": "Bootstrap a new review-master workspace and establish the first actionable state.",
        "current_focus": "No historical execution exists yet. Confirm inputs, initialize the workspace, and prepare to enter the first authored step.",
        "why_paused": "This workspace is new. The resume system is active, but there is no prior history to recover.",
        "next_operator_action": recommended_next_action["instruction"],
        "open_loops": list(resume_open_loops),
        "recent_decisions": list(resume_recent_decisions),
        "must_not_forget": list(resume_must_not_forget),
        "runtime_digest": runtime_digest,
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
            base_packet["open_loops"] = [f"Resolve pending confirmation: {message}" for message in pending]
        elif blockers:
            base_packet["open_loops"] = [f"Resolve blocker: {message}" for message in blockers]
    if workflow_state is None:
        base_packet["resume_status"] = "blocked"
        base_packet["is_bootstrap"] = False
        base_packet["why_paused"] = "The workspace cannot resume safely because workflow_state is invalid or missing."

    resume_read_order = [
        "instruction_payload.resume_packet",
        AGENT_RESUME_MD,
        "当前阶段主视图",
        "当前阶段参考文档",
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
    }


def build_blocked_actions(
    workflow_state: sqlite3.Row | None,
    pending: list[str],
    blockers: list[str],
    completion_map: dict[str, sqlite3.Row],
    export_artifact_map: dict[str, sqlite3.Row],
) -> list[dict[str, Any]]:
    if workflow_state is None:
        return [
            make_action(
                "blocked_until_db_state_fixed",
                "禁止继续推进。先修复 review-master.db 中的 workflow_state，再重新运行 gate-and-render 核心脚本。",
                "没有合法的数据库状态表，状态机无法运行。",
                ["review-master.db"],
                recipe_id="recipe_stage1_set_entry_state",
            )
        ]

    current_stage = str(workflow_state["current_stage"])
    active_comment_id = str(workflow_state["active_comment_id"]) if workflow_state["active_comment_id"] is not None else None
    blocked: list[dict[str, Any]] = []
    if current_stage == "stage_4" and pending:
        blocked.append(
            make_action(
                "blocked_enter_stage_5",
                "禁止进入阶段五执行。先让用户确认 atomic-comment-workboard.md 中的处理顺序、合并策略和锁定约束。",
                "阶段四还有待确认事项。",
                ["review-master.db", ATOMIC_WORKBOARD_MD],
                recipe_id="recipe_stage4_set_pending_confirmations",
            )
        )
    if current_stage == "stage_5" and active_comment_id:
        if pending:
            blocked.append(
                make_action(
                    "blocked_execute_active_comment",
                    f"禁止执行 {active_comment_id} 的改稿。先关闭该条策略相关的待确认事项。",
                    "active comment 还有待确认项。",
                    ["review-master.db", f"{STRATEGY_CARD_DIR}/{active_comment_id}.md"],
                    recipe_id=None,
                )
            )
        if blockers:
            blocked.append(
                make_action(
                    "blocked_complete_active_comment",
                    f"禁止把 {active_comment_id} 标记为完成。先关闭数据库状态中的 blocker 或证据缺口，并补齐补材接收与落地映射。",
                    "当前仍有 blocker。",
                    ["review-master.db", SUPPLEMENT_INTAKE_PLAN_MD],
                    recipe_id="recipe_stage5_set_blockers",
                )
            )
    export_not_ready = any(str(row["export_ready"]) != "yes" for row in completion_map.values()) if completion_map else True
    if current_stage != "stage_6" or export_not_ready:
        blocked.append(
            make_action(
                "blocked_final_export",
                "禁止导出 clean manuscript 和最终 Response Letter。",
                "最终导出门禁尚未全部满足。",
                ["review-master.db", FINAL_CHECKLIST_MD, RESPONSE_TABLE_PREVIEW_MD, RESPONSE_TABLE_PREVIEW_TEX],
                recipe_id="recipe_stage6_export_clean_manuscript",
            )
        )
    marked_status = export_artifact_map.get("marked_manuscript")
    if current_stage == "stage_6" and marked_status is not None and str(marked_status["artifact_status"]) != "exported":
        blocked.append(
            make_action(
                "blocked_clean_export_before_marked_review",
                "禁止进入 clean manuscript 与最终 Response Letter 导出。先导出 marked manuscript，并完成该轮用户复核。",
                "Stage 6 采用双阶段导出，marked manuscript 是 clean export 的前置条件。",
                ["review-master.db", FINAL_CHECKLIST_MD],
                recipe_id="recipe_stage6_export_marked_manuscript",
            )
        )
    return blocked


def build_stage_actions(
    workflow_state: sqlite3.Row | None,
    pending: list[str],
    blockers: list[str],
    atomic_map: dict[str, sqlite3.Row],
    atomic_state_map: dict[str, sqlite3.Row],
    strategy_map: dict[str, sqlite3.Row],
    completion_map: dict[str, sqlite3.Row],
    comment_to_action_ids: dict[str, list[str]],
    action_location_orders: dict[tuple[str, int], list[int]],
    style_profile_map: dict[str, sqlite3.Row],
    style_rule_count_by_target: dict[str, int],
    action_variant_labels: dict[tuple[str, int, int], set[str]],
    selected_variant_map: dict[tuple[str, int, int], str],
    response_thread_row_map: dict[str, sqlite3.Row],
    export_patch_set_map: dict[str, sqlite3.Row],
    export_patch_count_map: dict[str, int],
    export_artifact_map: dict[str, sqlite3.Row],
) -> list[dict[str, Any]]:
    if workflow_state is None:
        return [
            make_action(
                "repair_workflow_state",
                "先在 review-master.db 中创建或修复 workflow_state 的唯一行，再重新运行 gate-and-render 核心脚本。",
                "没有合法 workflow_state 时，agent 无法安全判断阶段门禁。",
                ["review-master.db"],
                recipe_id="recipe_stage1_set_entry_state",
            )
        ]

    current_stage = str(workflow_state["current_stage"])
    active_comment_id = str(workflow_state["active_comment_id"]) if workflow_state["active_comment_id"] is not None else None
    if pending:
        if current_stage == "stage_4":
            return [
                make_action(
                    "request_stage4_confirmation",
                    "向用户展示 atomic-comment-workboard.md 和 thread-to-atomic-mapping.md，并请求确认原始意见块到 canonical atomic item 的拆分、合并、优先级与处理顺序。",
                    "阶段四还有 pending_user_confirmations。",
                    ["review-master.db", ATOMIC_WORKBOARD_MD, THREAD_TO_ATOMIC_MAPPING_MD],
                    recipe_id="recipe_stage4_set_pending_confirmations",
                )
            ]
        return [
            make_action(
                "request_pending_confirmation",
                "先处理 review-master.db 中记录的待确认事项，确认后再继续当前阶段。",
                "状态机要求先完成用户确认。",
                ["review-master.db"],
                recipe_id=None,
            )
        ]
    if blockers:
        return [
            make_action(
                "resolve_blockers",
                "先根据 review-master.db 中的 blockers 请求补材、澄清或额外输入，并在补材接收后写实 supplement intake/landing，再关闭 blocker 继续。",
                "当前存在 global_blockers。",
                ["review-master.db", SUPPLEMENT_INTAKE_PLAN_MD],
                recipe_id="recipe_stage5_set_blockers",
            )
        ]
    if current_stage == "stage_1":
        return [
            make_action(
                "enter_stage_2",
                "进入阶段二，在 review-master.db 中填充 manuscript_summary、manuscript_sections 和 manuscript_claims，然后重新运行 gate-and-render 核心脚本并重渲染视图。",
                "阶段一已就绪，下一步是建立结构摘要真源数据。",
                ["review-master.db", MANUSCRIPT_SUMMARY_MD],
                recipe_id="recipe_stage2_upsert_manuscript_summary",
            )
        ]
    if current_stage == "stage_2":
        return [
            make_action(
                "enter_stage_3",
                "进入阶段三，在 review-master.db 中先写入 raw_review_threads，再写 canonical atomic comments 及其映射关系，完成后重新运行 gate-and-render 核心脚本。",
                "阶段二已就绪，下一步是形成原始意见块与 canonical atomic item 的双层真源数据。",
                ["review-master.db", RAW_REVIEW_THREADS_MD, ATOMIC_COMMENTS_MD, THREAD_TO_ATOMIC_MAPPING_MD],
                recipe_id="recipe_stage3_replace_threaded_atomic_model",
            )
        ]
    if current_stage == "stage_3":
        return [
            make_action(
                "enter_stage_4",
                "进入阶段四，在 review-master.db 中写入 atomic_comment_state、atomic_comment_target_locations 和 atomic_comment_analysis_links，再重新运行 gate-and-render 核心脚本。",
                "阶段三已就绪，下一步是形成 atomic item 级 workboard。",
                ["review-master.db", ATOMIC_WORKBOARD_MD],
                recipe_id="recipe_stage4_upsert_atomic_workboard",
            )
        ]
    if current_stage == "stage_4":
        ready_comment = next((comment_id for comment_id, row in atomic_state_map.items() if str(row["status"]) == "ready"), None)
        return [
            make_action(
                "enter_stage_5",
                f"把 {ready_comment or '下一条 ready atomic comment'} 写入 workflow_state.active_comment_id，并在 review-master.db 中写入对应 strategy_cards 数据后再重新运行 gate-and-render 核心脚本。",
                "阶段四已确认，下一步是锁定 active comment 并准备逐条策略卡。",
                ["review-master.db", STRATEGY_CARD_DIR],
                recipe_id="recipe_stage5_set_active_comment",
            )
        ]
    if current_stage == "stage_5":
        if active_comment_id and active_comment_id not in strategy_map:
            return [
                make_action(
                    "author_strategy_card",
                    f"先为 {active_comment_id} 在 review-master.db 中补齐 strategy_cards 与 strategy_card_actions，再重新运行 gate-and-render 核心脚本。",
                    "阶段五已有 active comment，但缺少对应策略卡真源数据。",
                    ["review-master.db", f"{STRATEGY_CARD_DIR}/{active_comment_id}.md"],
                    recipe_id="recipe_stage5_upsert_strategy_card",
                )
            ]
        if active_comment_id:
            return [
                make_action(
                    "advance_active_comment",
                    f"继续围绕 {active_comment_id} 更新 review-master.db 中的策略、动作位置、证据、补材接收落地、完成状态和 workflow_state，然后重新运行 gate-and-render 核心脚本。",
                    "当前 active comment 已具备继续推进条件。",
                    ["review-master.db", f"{STRATEGY_CARD_DIR}/{active_comment_id}.md", SUPPLEMENT_INTAKE_PLAN_MD],
                    recipe_id="recipe_stage5_upsert_completion_status",
                )
            ]
        next_comment = next((comment_id for comment_id, row in atomic_state_map.items() if str(row["status"]) == "ready"), None)
        return [
            make_action(
                "set_active_comment",
                f"把 {next_comment or '下一条 ready atomic comment'} 写入 workflow_state.active_comment_id，并开始为它准备策略卡。",
                "阶段五没有 active comment，下一步应锁定一条 ready atomic comment。",
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
                    "先在 review-master.db 中完成 manuscript 与 response_letter 的全局风格画像，并写入去 AI 化规则，再重新运行 gate-and-render 核心脚本。",
                    "Stage 6A 还未完成，后续文案版本生成没有风格约束基线。",
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
                                "先在 review-master.db 中为每个修改点的每个 target location 生成 3 个 manuscript 最终落稿文本版本，再重新运行 gate-and-render 核心脚本。",
                                "Stage 6B 尚未完成；每个 action-location 都必须达到 3 个 manuscript 最终落稿文本版本。",
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
                                "向用户展示 action-copy-variants.md，请其为每个 action 的每个 target location 选定一个 manuscript 最终落稿文本；选择写入数据库后再重新运行 gate-and-render 核心脚本。",
                                "Stage 6C 之前必须先完成位置级 manuscript 最终文案选择。",
                                ["review-master.db", ACTION_COPY_VARIANTS_MD],
                                recipe_id="recipe_stage6_select_action_copy_variants",
                            )
                        ]
        if len(response_thread_row_map) == 0:
            return [
                make_action(
                    "assemble_response_thread_rows",
                    "先在 review-master.db 中建立 response_thread_resolution_links 与 response_thread_rows，把 Stage 5 已确认的策略/草案与已选中的 manuscript 文案聚合为 thread-level 4 列表格行，再重新运行 gate-and-render 核心脚本。",
                    "Stage 6C 尚未完成；最终 Response Letter 还没有 row-level 真源。",
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
                    "先在 review-master.db 中建立 export_patch_sets 与 export_patches，把每个修改位置的显式原文锚点、marked_text 和 clean_text 写实，再重新运行 gate-and-render 核心脚本。",
                    "Stage 6D/6E 的完整导出必须基于可执行的 export patch 真源，而不能依赖手工拼接完整稿件。",
                    ["review-master.db", EXPORT_PATCH_PLAN_MD],
                    recipe_id="recipe_stage6_replace_export_patches",
                )
            ]
        marked_row = export_artifact_map.get("marked_manuscript")
        if marked_row is None or str(marked_row["artifact_status"]) != "exported":
            return [
                make_action(
                    "export_marked_manuscript",
                    "先调用 export_manuscript_variants.py 基于 marked patch set 导出完整的 marked manuscript，并在 review-master.db 中记录其输出路径和状态，然后重新运行 gate-and-render 核心脚本。",
                    "Stage 6D 尚未完成；clean export 之前必须先完成完整 marked manuscript 导出与复核。",
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
                    "向用户展示完整 marked manuscript 和最终 Response Letter 预览做最终复核；若用户确认无误，再调用 export_manuscript_variants.py 基于 clean patch set 导出 clean manuscript，并写入 Markdown/LaTeX Response Letter 的最终输出路径和状态。",
                    "Stage 6E 尚未完成；最终 clean manuscript 与双格式 Response Letter 仍未全部落地。",
                    ["review-master.db", EXPORT_PATCH_PLAN_MD, FINAL_CHECKLIST_MD, RESPONSE_TABLE_PREVIEW_MD, RESPONSE_TABLE_PREVIEW_TEX],
                    recipe_id="recipe_stage6_export_clean_manuscript",
                )
            ]
        return [
            make_action(
                "stage_6_completed",
                "Stage 6 已闭环。保持导出产物不变，如需新增修改，应回到数据库真源更新后再重新运行 gate-and-render 核心脚本。",
                "所有 Stage 6 产物都已导出。",
                ["review-master.db", EXPORT_PATCH_PLAN_MD, FINAL_CHECKLIST_MD, RESPONSE_TABLE_PREVIEW_MD, RESPONSE_TABLE_PREVIEW_TEX],
                recipe_id="recipe_stage6_export_clean_manuscript",
            )
        ]
    return [
        make_action(
            "inspect_state_machine",
            "当前状态无法匹配既定状态机。先检查 review-master.db 中的 workflow_state 相关记录。",
            "状态机无法识别当前阶段。",
            ["review-master.db"],
            recipe_id="recipe_stage1_set_entry_state",
        )
    ]


def build_instruction_payload(
    workflow_state: sqlite3.Row | None,
    resume_brief: sqlite3.Row | None,
    pending: list[str],
    blockers: list[str],
    resume_open_loops: list[str],
    resume_recent_decisions: list[str],
    resume_must_not_forget: list[str],
    atomic_map: dict[str, sqlite3.Row],
    atomic_state_map: dict[str, sqlite3.Row],
    strategy_map: dict[str, sqlite3.Row],
    completion_map: dict[str, sqlite3.Row],
    comment_to_action_ids: dict[str, list[str]],
    action_location_orders: dict[tuple[str, int], list[int]],
    style_profile_map: dict[str, sqlite3.Row],
    style_rule_count_by_target: dict[str, int],
    action_variant_labels: dict[tuple[str, int, int], set[str]],
    selected_variant_map: dict[tuple[str, int, int], str],
    response_thread_row_map: dict[str, sqlite3.Row],
    export_patch_set_map: dict[str, sqlite3.Row],
    export_patch_count_map: dict[str, int],
    export_artifact_map: dict[str, sqlite3.Row],
    format_errors: list[dict[str, Any]],
    dependency_errors: list[dict[str, Any]],
    consistency_errors: list[dict[str, Any]],
) -> dict[str, Any]:
    repair_sequence = build_repair_sequence(format_errors, dependency_errors, consistency_errors)
    current_state = build_current_state(workflow_state, pending, blockers, bool(repair_sequence))
    blocked_actions = build_blocked_actions(workflow_state, pending, blockers, completion_map, export_artifact_map)
    if repair_sequence:
        allowed_next_actions = repair_sequence
        recommended_next_action = repair_sequence[0]
    else:
        allowed_next_actions = build_stage_actions(
            workflow_state,
            pending,
            blockers,
            atomic_map,
            atomic_state_map,
            strategy_map,
            completion_map,
            comment_to_action_ids,
            action_location_orders,
            style_profile_map,
            style_rule_count_by_target,
            action_variant_labels,
            selected_variant_map,
            response_thread_row_map,
            export_patch_set_map,
            export_patch_count_map,
            export_artifact_map,
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
    )
    return {
        "current_state": current_state,
        "resume_packet": resume_packet,
        "allowed_next_actions": allowed_next_actions,
        "recommended_next_action": recommended_next_action,
        "repair_sequence": repair_sequence,
        "blocked_actions": blocked_actions,
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
    thread_to_resolution_comment_ids: dict[str, list[str]] = {}
    style_profile_map: dict[str, sqlite3.Row] = {}
    style_rule_count_by_target: dict[str, int] = {}
    action_variant_labels: dict[tuple[str, int, int], set[str]] = {}
    selected_variant_map: dict[tuple[str, int, int], str] = {}
    response_thread_row_map: dict[str, sqlite3.Row] = {}
    export_patch_set_map: dict[str, sqlite3.Row] = {}
    export_patch_count_map: dict[str, int] = {}
    export_artifact_map: dict[str, sqlite3.Row] = {}

    try:
        with connect_db(db_path) as connection:
            validate_schema(connection, db_path, format_errors)
            (
                workflow_state,
                resume_brief,
                pending,
                blockers,
                resume_open_loops,
                resume_recent_decisions,
                resume_must_not_forget,
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
                thread_to_resolution_comment_ids,
                style_profile_map,
                style_rule_count_by_target,
                action_variant_labels,
                selected_variant_map,
                response_thread_row_map,
                export_patch_set_map,
                export_patch_count_map,
                export_artifact_map,
                content_errors,
            ) = validate_database_content(connection, db_path)
            format_errors.extend(content_errors)
    except sqlite3.DatabaseError as exc:
        return emit({"status": "error", "error": f"sqlite error: {exc}"}, exit_code=1)

    stage_num = workflow_stage_number(workflow_state)
    active_comment_id = str(workflow_state["active_comment_id"]) if workflow_state is not None and workflow_state["active_comment_id"] is not None else None
    dependency_errors.extend(
        validate_dependencies(
            db_path,
            stage_num,
            active_comment_id,
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
            raw_thread_map,
            atomic_map,
            atomic_state_map,
            strategy_map,
            completion_map,
            thread_to_comment_ids,
            thread_to_resolution_comment_ids,
            style_profile_map,
            style_rule_count_by_target,
            action_variant_labels,
            selected_variant_map,
            response_thread_row_map,
            export_patch_set_map,
            export_patch_count_map,
            export_artifact_map,
        )
    )
    instruction_payload = build_instruction_payload(
        workflow_state,
        resume_brief,
        pending,
        blockers,
        resume_open_loops,
        resume_recent_decisions,
        resume_must_not_forget,
        atomic_map,
        atomic_state_map,
        strategy_map,
        completion_map,
        comment_to_action_ids,
        action_location_orders,
        style_profile_map,
        style_rule_count_by_target,
        action_variant_labels,
        selected_variant_map,
        response_thread_row_map,
        export_patch_set_map,
        export_patch_count_map,
        export_artifact_map,
        format_errors,
        dependency_errors,
        consistency_errors,
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

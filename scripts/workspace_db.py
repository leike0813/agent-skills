from __future__ import annotations

import importlib
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from types import ModuleType
from typing import Any

try:
    import yaml  # type: ignore[import-untyped]
except ModuleNotFoundError:  # pragma: no cover - exercised through runtime checks
    yaml = None

try:
    jinja2: ModuleType | None = importlib.import_module("jinja2")
except ModuleNotFoundError:  # pragma: no cover - exercised through runtime checks
    jinja2 = None

from runtime_localization import (
    DOCUMENT_MESSAGES_FILENAME,
    LOCALIZATION_DIRNAME,
    SOURCE_MESSAGES_FILENAME,
    TEMPLATE_OVERRIDE_DIRNAME,
    WORKING_MESSAGES_FILENAME,
    LocalizationBundle,
    fetch_runtime_language_context,
    load_localization_bundle,
    seed_workspace_localization_overlay,
)


DB_FILENAME = "review-master.db"
AGENT_RESUME_MD = "01-agent-resume.md"
MANUSCRIPT_SUMMARY_MD = "02-manuscript-structure-summary.md"
RAW_REVIEW_THREADS_MD = "03-raw-review-thread-list.md"
ATOMIC_COMMENTS_MD = "04-atomic-review-comment-list.md"
THREAD_TO_ATOMIC_MAPPING_MD = "05-thread-to-atomic-mapping.md"
REVIEW_COMMENT_COVERAGE_MD = "06-review-comment-coverage.md"
ATOMIC_WORKBOARD_MD = "07-atomic-comment-workboard.md"
STYLE_PROFILE_MD = "08-style-profile.md"
ACTION_COPY_VARIANTS_MD = "09-action-copy-variants.md"
RESPONSE_LETTER_OUTLINE_MD = "10-response-letter-outline.md"
EXPORT_PATCH_PLAN_MD = "11-export-patch-plan.md"
RESPONSE_TABLE_PREVIEW_MD = "12-response-letter-table-preview.md"
RESPONSE_TABLE_PREVIEW_TEX = "13-response-letter-table-preview.tex"
SUPPLEMENT_SUGGESTION_PLAN_MD = "14-supplement-suggestion-plan.md"
SUPPLEMENT_INTAKE_PLAN_MD = "15-supplement-intake-plan.md"
FINAL_CHECKLIST_MD = "16-final-assembly-checklist.md"
STRATEGY_CARD_DIR = "response-strategy-cards"

LEGACY_RUNTIME_VIEW_FILENAMES = (
    "agent-resume.md",
    "manuscript-structure-summary.md",
    "raw-review-thread-list.md",
    "atomic-review-comment-list.md",
    "thread-to-atomic-mapping.md",
    "review-comment-coverage.md",
    "atomic-comment-workboard.md",
    "style-profile.md",
    "action-copy-variants.md",
    "response-letter-outline.md",
    "export-patch-plan.md",
    "response-letter-table-preview.md",
    "response-letter-table-preview.tex",
    "supplement-suggestion-plan.md",
    "supplement-intake-plan.md",
    "final-assembly-checklist.md",
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ASSET_PATH = PACKAGE_ROOT / "assets" / "schema" / "review-master-schema.yaml"
TEMPLATE_DIR = PACKAGE_ROOT / "assets" / "templates"
RUNTIME_ASSET_DIR = PACKAGE_ROOT / "assets" / "runtime"
RENDER_MANIFEST_PATH = TEMPLATE_DIR / "render-manifest.yaml"
RUNTIME_DIGEST_PATH = RUNTIME_ASSET_DIR / "skill-runtime-digest.md"

DEFAULT_ENUMS = {
    "status": {"todo", "blocked", "ready", "in_progress", "done"},
    "priority": {"high", "medium", "low"},
    "evidence_gap": {"yes", "no"},
    "project_shape": {"single_tex", "latex_project"},
    "yes_no": {"yes", "no"},
    "current_stage": {f"stage_{index}" for index in range(1, 7)},
    "stage_gate": {"blocked", "ready"},
    "source_type": {"reviewer_comment", "editor_comment"},
    "source_kind": {"review_comments_source", "editor_letter_source"},
    "coverage_status": {"covered", "uncovered"},
    "location_role": {"primary", "supporting"},
    "response_role": {"primary", "supporting", "merged_duplicate"},
    "profile_target": {"manuscript", "response_letter"},
    "style_rule_type": {"do", "dont", "anti_ai", "tone"},
    "variant_label": {"v1", "v2", "v3"},
    "artifact_name": {"marked_manuscript", "clean_manuscript", "response_markdown", "response_latex"},
    "artifact_status": {"pending", "ready", "exported"},
    "resume_status": {"bootstrap", "active", "blocked", "ready_to_resume", "completed"},
    "supplement_decision": {"", "accepted", "rejected"},
    "supplement_suggestion_status": {"provisional", "confirmed", "linked", "satisfied", "dismissed"},
}

TARGET_LOCATION_RE = re.compile(r"^[^:\n|]+::[^:\n|]+::[^:\n|]+$")

REPAIR_PRIORITY = {
    "workflow_state": 0,
    "resume_brief": 1,
    "resume_open_loops": 2,
    "resume_recent_decisions": 3,
    "resume_must_not_forget": 4,
    "manuscript_summary": 1,
    "raw_review_threads": 5,
    "atomic_comments": 6,
    "raw_thread_atomic_links": 7,
    "review_comment_source_documents": 8,
    "review_comment_coverage_segments": 9,
    "review_comment_coverage_segment_comment_links": 10,
    "atomic_comment_state": 11,
    "atomic_comment_target_locations": 12,
    "atomic_comment_analysis_links": 13,
    "strategy_cards": 14,
    "strategy_action_manuscript_drafts": 15,
    "comment_response_drafts": 16,
    "comment_completion_status": 17,
    "comment_blockers": 18,
    "response_thread_resolution_links": 19,
    "style_profiles": 20,
    "style_profile_rules": 21,
    "action_copy_variants": 22,
    "selected_action_copy_variants": 23,
    "response_thread_rows": 24,
    "export_patch_sets": 25,
    "export_patches": 26,
    "export_artifacts": 27,
    "supplement_suggestion_items": 28,
    "supplement_suggestion_intake_links": 29,
    "supplement_intake_items": 30,
    "supplement_landing_links": 31,
}


def required_runtime_dependencies() -> list[str]:
    missing: list[str] = []
    if yaml is None:
        missing.append("PyYAML")
    if jinja2 is None:
        missing.append("Jinja2")
    return missing


def ensure_asset_runtime_available() -> None:
    missing = required_runtime_dependencies()
    if missing:
        raise RuntimeError(f"missing Python dependencies: {', '.join(missing)}")


def load_yaml_document(path: Path) -> dict[str, Any]:
    ensure_asset_runtime_available()
    if not path.exists():
        raise FileNotFoundError(f"missing asset file: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"asset file must contain a YAML mapping: {path}")
    return data


def load_schema_definition() -> dict[str, Any]:
    return load_yaml_document(SCHEMA_ASSET_PATH)


def load_render_manifest() -> dict[str, Any]:
    return load_yaml_document(RENDER_MANIFEST_PATH)


def enum_values(enum_name: str) -> set[str]:
    try:
        schema = load_schema_definition()
        enums = schema.get("enums", {})
        values = enums.get(enum_name, [])
        if isinstance(values, list) and values:
            return {str(value) for value in values}
    except (OSError, RuntimeError):
        pass
    return set(DEFAULT_ENUMS[enum_name])


ALLOWED_STATUS = enum_values("status")
ALLOWED_PRIORITY = enum_values("priority")
ALLOWED_EVIDENCE_GAP = enum_values("evidence_gap")
ALLOWED_PROJECT_SHAPE = enum_values("project_shape")
ALLOWED_YES_NO = enum_values("yes_no")
ALLOWED_STAGE = enum_values("current_stage")
ALLOWED_STAGE_GATE = enum_values("stage_gate")
ALLOWED_SOURCE_TYPE = enum_values("source_type")
ALLOWED_SOURCE_KIND = enum_values("source_kind")
ALLOWED_COVERAGE_STATUS = enum_values("coverage_status")
ALLOWED_LOCATION_ROLE = enum_values("location_role")
ALLOWED_RESPONSE_ROLE = enum_values("response_role")
ALLOWED_PROFILE_TARGET = enum_values("profile_target")
ALLOWED_STYLE_RULE_TYPE = enum_values("style_rule_type")
ALLOWED_VARIANT_LABEL = enum_values("variant_label")
ALLOWED_ARTIFACT_NAME = enum_values("artifact_name")
ALLOWED_ARTIFACT_STATUS = enum_values("artifact_status")
ALLOWED_RESUME_STATUS = enum_values("resume_status")
ALLOWED_SUPPLEMENT_DECISION = enum_values("supplement_decision")
ALLOWED_SUPPLEMENT_SUGGESTION_STATUS = enum_values("supplement_suggestion_status")


def connect_db(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def required_tables() -> list[str]:
    schema = load_schema_definition()
    explicit = schema.get("required_tables", [])
    if isinstance(explicit, list) and explicit:
        return [str(table_name) for table_name in explicit]
    tables = schema.get("tables", [])
    return [str(table["name"]) for table in tables if isinstance(table, dict) and "name" in table]


def initialize_database(db_path: Path) -> None:
    schema = load_schema_definition()
    tables = schema.get("tables", [])
    bootstrap = schema.get("bootstrap", [])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect_db(db_path) as connection:
        for table in tables:
            if not isinstance(table, dict) or "sql" not in table:
                raise RuntimeError("each schema table entry must contain an 'sql' field")
            connection.execute(str(table["sql"]))
        for statement in bootstrap:
            if not isinstance(statement, dict) or "sql" not in statement:
                raise RuntimeError("each bootstrap entry must contain an 'sql' field")
            connection.execute(str(statement["sql"]))
        connection.commit()


def ensure_runtime_schema_compatibility(connection: sqlite3.Connection) -> None:
    schema = load_schema_definition()
    tables = schema.get("tables", [])
    legacy_missing_coverage_tables = any(
        not table_exists(connection, table_name)
        for table_name in (
            "review_comment_source_documents",
            "review_comment_coverage_segments",
            "review_comment_coverage_segment_comment_links",
        )
    )
    legacy_missing_supplement_tables = any(
        not table_exists(connection, table_name)
        for table_name in (
            "supplement_suggestion_items",
            "supplement_suggestion_intake_links",
        )
    )
    for table in tables:
        if not isinstance(table, dict) or "sql" not in table:
            raise RuntimeError("each schema table entry must contain an 'sql' field")
        connection.execute(str(table["sql"]))
    if legacy_missing_coverage_tables:
        backfill_legacy_review_comment_coverage(connection)
    if legacy_missing_supplement_tables:
        backfill_legacy_supplement_suggestions(connection)
    connection.commit()


def artifact_paths(artifact_root: Path) -> dict[str, Path]:
    return {
        "db": artifact_root / DB_FILENAME,
        "agent_resume_md": artifact_root / AGENT_RESUME_MD,
        "manuscript_summary_md": artifact_root / MANUSCRIPT_SUMMARY_MD,
        "raw_review_threads_md": artifact_root / RAW_REVIEW_THREADS_MD,
        "atomic_comments_md": artifact_root / ATOMIC_COMMENTS_MD,
        "thread_to_atomic_mapping_md": artifact_root / THREAD_TO_ATOMIC_MAPPING_MD,
        "review_comment_coverage_md": artifact_root / REVIEW_COMMENT_COVERAGE_MD,
        "atomic_workboard_md": artifact_root / ATOMIC_WORKBOARD_MD,
        "style_profile_md": artifact_root / STYLE_PROFILE_MD,
        "action_copy_variants_md": artifact_root / ACTION_COPY_VARIANTS_MD,
        "response_letter_outline_md": artifact_root / RESPONSE_LETTER_OUTLINE_MD,
        "export_patch_plan_md": artifact_root / EXPORT_PATCH_PLAN_MD,
        "response_table_preview_md": artifact_root / RESPONSE_TABLE_PREVIEW_MD,
        "response_table_preview_tex": artifact_root / RESPONSE_TABLE_PREVIEW_TEX,
        "supplement_suggestion_plan_md": artifact_root / SUPPLEMENT_SUGGESTION_PLAN_MD,
        "supplement_intake_plan_md": artifact_root / SUPPLEMENT_INTAKE_PLAN_MD,
        "final_checklist_md": artifact_root / FINAL_CHECKLIST_MD,
        "strategy_card_dir": artifact_root / STRATEGY_CARD_DIR,
        "localization_root": artifact_root / LOCALIZATION_DIRNAME,
        "localization_source_messages": artifact_root / LOCALIZATION_DIRNAME / SOURCE_MESSAGES_FILENAME,
        "localization_working_messages": artifact_root / LOCALIZATION_DIRNAME / WORKING_MESSAGES_FILENAME,
        "localization_document_messages": artifact_root / LOCALIZATION_DIRNAME / DOCUMENT_MESSAGES_FILENAME,
        "localization_template_override_dir": artifact_root / LOCALIZATION_DIRNAME / TEMPLATE_OVERRIDE_DIRNAME,
    }


def cleanup_legacy_runtime_views(artifact_root: Path) -> None:
    for filename in LEGACY_RUNTIME_VIEW_FILENAMES:
        path = artifact_root / filename
        if path.exists():
            path.unlink()


def fetch_all(connection: sqlite3.Connection, query: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
    return list(connection.execute(query, params).fetchall())


def fetch_one(connection: sqlite3.Connection, query: str, params: tuple[object, ...] = ()) -> sqlite3.Row | None:
    return connection.execute(query, params).fetchone()


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = fetch_one(
        connection,
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    return row is not None


def split_multiline(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def backfill_legacy_review_comment_coverage(connection: sqlite3.Connection) -> None:
    existing_row = fetch_one(
        connection,
        "SELECT 1 FROM review_comment_source_documents LIMIT 1",
    )
    if existing_row is not None:
        return
    thread_rows = fetch_all(
        connection,
        """
        SELECT thread_id, reviewer_id, thread_order, original_text
        FROM raw_review_threads
        ORDER BY reviewer_id, thread_order, thread_id
        """,
    )
    if not thread_rows:
        return
    thread_links = fetch_all(
        connection,
        """
        SELECT thread_id, comment_id, link_order
        FROM raw_thread_atomic_links
        ORDER BY thread_id, link_order, comment_id
        """,
    )
    comment_ids_by_thread: dict[str, list[str]] = defaultdict(list)
    for row in thread_links:
        comment_ids_by_thread[str(row["thread_id"])].append(str(row["comment_id"]))
    connection.execute("DELETE FROM review_comment_coverage_segment_comment_links")
    connection.execute("DELETE FROM review_comment_coverage_segments")
    connection.execute("DELETE FROM review_comment_source_documents")
    for document_order, row in enumerate(thread_rows, start=1):
        thread_id = str(row["thread_id"])
        reviewer_id = str(row["reviewer_id"])
        thread_order = int(row["thread_order"])
        original_text = str(row["original_text"])
        source_document_id = f"legacy-thread::{thread_id}"
        connection.execute(
            """
            INSERT INTO review_comment_source_documents (
                source_document_id, source_kind, document_order, source_label, source_path, original_text
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                source_document_id,
                "review_comments_source",
                document_order,
                f"{reviewer_id} / thread {thread_order}",
                f"legacy://review-comments/{thread_id}",
                original_text,
            ),
        )
        connection.execute(
            """
            INSERT INTO review_comment_coverage_segments (
                source_document_id, segment_order, coverage_status, segment_text, thread_id
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                source_document_id,
                1,
                "covered",
                original_text,
                thread_id,
            ),
        )
        for link_order, comment_id in enumerate(comment_ids_by_thread.get(thread_id, []), start=1):
            connection.execute(
                """
                INSERT INTO review_comment_coverage_segment_comment_links (
                    source_document_id, segment_order, link_order, comment_id
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    source_document_id,
                    1,
                    link_order,
                    comment_id,
                ),
            )


def backfill_legacy_supplement_suggestions(connection: sqlite3.Connection) -> None:
    existing_row = fetch_one(
        connection,
        "SELECT 1 FROM supplement_suggestion_items LIMIT 1",
    )
    if existing_row is not None:
        return
    gap_rows = fetch_all(
        connection,
        """
        SELECT acs.comment_id, acl.analysis_order, COALESCE(acl.gap_summary, '') AS gap_summary, ac.required_action
        FROM atomic_comment_state AS acs
        JOIN atomic_comments AS ac ON ac.comment_id = acs.comment_id
        LEFT JOIN atomic_comment_analysis_links AS acl ON acl.comment_id = acs.comment_id
        WHERE acs.evidence_gap = 'yes'
        ORDER BY acs.comment_id, acl.analysis_order
        """,
    )
    suggestion_count_by_comment: dict[str, int] = defaultdict(int)
    for row in gap_rows:
        comment_id = str(row["comment_id"])
        gap_summary = str(row["gap_summary"]).strip()
        if not gap_summary:
            continue
        suggestion_count_by_comment[comment_id] += 1
        suggestion_order = suggestion_count_by_comment[comment_id]
        connection.execute(
            """
            INSERT INTO supplement_suggestion_items (
                comment_id, suggestion_order, analysis_order, request_summary, request_recommendation, status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                comment_id,
                suggestion_order,
                row["analysis_order"],
                gap_summary,
                f"Collect evidence to support: {row['required_action']}",
                "provisional",
            ),
        )


def load_runtime_digest() -> str:
    if not RUNTIME_DIGEST_PATH.exists():
        raise FileNotFoundError(f"missing runtime digest asset: {RUNTIME_DIGEST_PATH}")
    return RUNTIME_DIGEST_PATH.read_text(encoding="utf-8").strip()


def fetch_resume_lists(connection: sqlite3.Connection) -> tuple[list[str], list[str], list[str]]:
    open_loops = [str(row["message"]) for row in fetch_all(connection, "SELECT message FROM resume_open_loops ORDER BY position")]
    recent_decisions = [str(row["message"]) for row in fetch_all(connection, "SELECT message FROM resume_recent_decisions ORDER BY position")]
    must_not_forget = [str(row["message"]) for row in fetch_all(connection, "SELECT message FROM resume_must_not_forget ORDER BY position")]
    return open_loops, recent_decisions, must_not_forget


def build_default_resume_packet(
    connection: sqlite3.Connection,
    localization: LocalizationBundle | None = None,
) -> dict[str, Any]:
    brief = fetch_one(
        connection,
        """
        SELECT resume_status, current_objective, current_focus, why_paused, next_operator_action
        FROM resume_brief
        WHERE id = 1
        """,
    )
    workflow_state = fetch_one(
        connection,
        """
        SELECT current_stage, stage_gate, active_comment_id, next_action
        FROM workflow_state
        WHERE id = 1
        """,
    )
    open_loops, recent_decisions, must_not_forget = fetch_resume_lists(connection)
    runtime_digest = load_runtime_digest()

    current_stage = str(workflow_state["current_stage"]) if workflow_state is not None else "unknown"
    stage_gate = str(workflow_state["stage_gate"]) if workflow_state is not None else "blocked"
    active_comment_id = str(workflow_state["active_comment_id"]) if workflow_state is not None and workflow_state["active_comment_id"] is not None else "None"
    resume_status = str(brief["resume_status"]) if brief is not None else "bootstrap"
    next_action_anchor = str(workflow_state["next_action"]) if workflow_state is not None else "repair_workflow_state"
    runtime_language_context = localization.snapshot() if localization is not None else fetch_runtime_language_context(connection)
    msg = localization.msg if localization is not None else (lambda key, *, target="working", **kwargs: key.format(**kwargs) if kwargs else key)
    return {
        "resume_status": resume_status,
        "is_bootstrap": "yes" if resume_status == "bootstrap" else "no",
        "current_stage": current_stage,
        "stage_gate": stage_gate,
        "active_comment_id": active_comment_id,
        "current_state_summary": (
            localization.msg(
                "current_state.summary",
                current_stage=current_stage,
                stage_gate=stage_gate,
                active_comment_id=active_comment_id,
            )
            if localization is not None
            else f"Current stage is {current_stage}, gate={stage_gate}, active_comment_id={active_comment_id}."
        ),
        "current_objective": str(brief["current_objective"]) if brief is not None else "",
        "current_focus": str(brief["current_focus"]) if brief is not None else "",
        "why_paused": str(brief["why_paused"]) if brief is not None else "",
        "next_operator_action": str(brief["next_operator_action"]) if brief is not None else "",
        "open_loops": open_loops,
        "recent_decisions": recent_decisions,
        "must_not_forget": must_not_forget,
        "resume_read_order": [
            msg("resume.read_order.instruction_payload"),
            msg("resume.read_order.agent_resume"),
            msg("resume.read_order.stage_view"),
            msg("resume.read_order.stage_reference"),
        ],
        "next_action_anchor": next_action_anchor,
        "runtime_digest": runtime_digest,
        "language_context": runtime_language_context,
    }


def create_template_environment(localization: LocalizationBundle) -> Any:
    ensure_asset_runtime_available()
    assert jinja2 is not None
    template_dirs = [path for path in localization.template_dirs if path.exists()]
    if not template_dirs:
        raise FileNotFoundError("missing template directories for localization-aware rendering")
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader([str(path) for path in template_dirs]),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )
    env.globals["msg"] = localization.msg
    env.globals["language_context"] = localization.snapshot()
    return env


def join_ordered(values: list[str]) -> str:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value and value not in seen:
            ordered.append(value)
            seen.add(value)
    return ", ".join(ordered)


def tex_escape(value: str) -> str:
    escaped = (
        value.replace("\\", "\\textbackslash{}")
        .replace("&", "\\&")
        .replace("%", "\\%")
        .replace("$", "\\$")
        .replace("#", "\\#")
        .replace("_", "\\_")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("~", "\\textasciitilde{}")
        .replace("^", "\\textasciicircum{}")
    )
    return escaped


def build_comment_source_index(connection: sqlite3.Connection) -> dict[str, dict[str, list[str]]]:
    rows = fetch_all(
        connection,
        """
        SELECT rtl.comment_id, rrt.reviewer_id, rrt.thread_id
        FROM raw_thread_atomic_links rtl
        JOIN raw_review_threads rrt ON rrt.thread_id = rtl.thread_id
        ORDER BY rtl.comment_id, rrt.reviewer_id, rrt.thread_order, rtl.link_order
        """,
    )
    source_index: dict[str, dict[str, list[str]]] = {}
    for row in rows:
        comment_id = str(row["comment_id"])
        entry = source_index.setdefault(comment_id, {"reviewers": [], "thread_ids": []})
        entry["reviewers"].append(str(row["reviewer_id"]))
        entry["thread_ids"].append(str(row["thread_id"]))
    return source_index


def build_comment_target_location_index(connection: sqlite3.Connection) -> dict[str, list[str]]:
    rows = fetch_all(
        connection,
        """
        SELECT comment_id, target_location
        FROM atomic_comment_target_locations
        ORDER BY comment_id, location_order
        """,
    )
    target_index: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        target_index[str(row["comment_id"])].append(str(row["target_location"]))
    return dict(target_index)


def build_comment_analysis_index(connection: sqlite3.Connection) -> dict[str, list[dict[str, str]]]:
    rows = fetch_all(
        connection,
        """
        SELECT comment_id, analysis_order, manuscript_claim_or_section, existing_evidence, gap_summary, dependency_comment_id
        FROM atomic_comment_analysis_links
        ORDER BY comment_id, analysis_order
        """,
    )
    analysis_index: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        analysis_index[str(row["comment_id"])].append(
            {
                "manuscript_claim_or_section": str(row["manuscript_claim_or_section"]),
                "existing_evidence": str(row["existing_evidence"]),
                "gap_summary": str(row["gap_summary"]),
                "dependency_comment_id": str(row["dependency_comment_id"] or ""),
            }
        )
    return dict(analysis_index)


def build_strategy_action_location_index(connection: sqlite3.Connection) -> dict[tuple[str, int], list[str]]:
    rows = fetch_all(
        connection,
        """
        SELECT comment_id, action_order, target_location
        FROM strategy_action_target_locations
        ORDER BY comment_id, action_order, location_order
        """,
    )
    index: dict[tuple[str, int], list[str]] = defaultdict(list)
    for row in rows:
        key = (str(row["comment_id"]), int(row["action_order"]))
        index[key].append(str(row["target_location"]))
    return dict(index)


def build_strategy_action_target_detail_index(connection: sqlite3.Connection) -> dict[tuple[str, int], list[dict[str, Any]]]:
    rows = fetch_all(
        connection,
        """
        SELECT comment_id, action_order, location_order, target_location
        FROM strategy_action_target_locations
        ORDER BY comment_id, action_order, location_order
        """,
    )
    index: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (str(row["comment_id"]), int(row["action_order"]))
        index[key].append(
            {
                "location_order": int(row["location_order"]),
                "target_location": str(row["target_location"]),
            }
        )
    return dict(index)


def build_manuscript_summary_context(connection: sqlite3.Connection) -> dict[str, Any]:
    summary = fetch_one(connection, "SELECT main_entry, project_shape, high_risk_areas FROM manuscript_summary WHERE id = 1")
    sections = fetch_all(
        connection,
        "SELECT section_id, section_title, purpose_in_manuscript, key_files_or_locations FROM manuscript_sections ORDER BY section_id",
    )
    claims = fetch_all(
        connection,
        "SELECT claim_id, core_claim, main_evidence, supporting_section_ids, risk_level FROM manuscript_claims ORDER BY claim_id",
    )
    return {
        "main_entry": str(summary["main_entry"] if summary else ""),
        "project_shape": str(summary["project_shape"] if summary else ""),
        "sections": [dict(row) for row in sections],
        "claims": [dict(row) for row in claims],
        "risk_areas": split_multiline(str(summary["high_risk_areas"] if summary else "")),
    }


def build_agent_resume_context(
    connection: sqlite3.Connection,
    *,
    resume_context: dict[str, Any] | None = None,
    localization: LocalizationBundle | None = None,
) -> dict[str, Any]:
    packet = dict(resume_context or build_default_resume_packet(connection, localization))
    return {
        "resume_status": str(packet.get("resume_status", "bootstrap")),
        "is_bootstrap": str(packet.get("is_bootstrap", "yes")),
        "current_stage": str(packet.get("current_stage", "unknown")),
        "stage_gate": str(packet.get("stage_gate", "blocked")),
        "active_comment_id": str(packet.get("active_comment_id", "None")),
        "current_state_summary": str(packet.get("current_state_summary", "")),
        "current_objective": str(packet.get("current_objective", "")),
        "current_focus": str(packet.get("current_focus", "")),
        "why_paused": str(packet.get("why_paused", "")),
        "next_operator_action": str(packet.get("next_operator_action", "")),
        "open_loops": [str(item) for item in packet.get("open_loops", [])],
        "recent_decisions": [str(item) for item in packet.get("recent_decisions", [])],
        "must_not_forget": [str(item) for item in packet.get("must_not_forget", [])],
        "resume_read_order": [str(item) for item in packet.get("resume_read_order", [])],
        "next_action_anchor": str(packet.get("next_action_anchor", "")),
        "runtime_digest": str(packet.get("runtime_digest", load_runtime_digest())),
        "language_context": dict(packet.get("language_context", localization.snapshot() if localization is not None else {})),
    }


def build_raw_review_threads_context(connection: sqlite3.Connection) -> dict[str, Any]:
    rows = fetch_all(
        connection,
        """
        SELECT rrt.thread_id, rrt.reviewer_id, rrt.thread_order, rrt.source_type, rrt.original_text,
               rrt.normalized_summary, rtl.link_order, rtl.comment_id
        FROM raw_review_threads rrt
        LEFT JOIN raw_thread_atomic_links rtl ON rtl.thread_id = rrt.thread_id
        ORDER BY rrt.reviewer_id, rrt.thread_order, rtl.link_order
        """,
    )
    thread_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        thread_id = str(row["thread_id"])
        thread = thread_map.setdefault(
            thread_id,
            {
                "thread_id": thread_id,
                "reviewer_id": str(row["reviewer_id"]),
                "thread_order": int(row["thread_order"]),
                "source_type": str(row["source_type"]),
                "original_text": str(row["original_text"]),
                "normalized_summary": str(row["normalized_summary"]),
                "linked_comment_ids": [],
            },
        )
        if row["comment_id"] is not None:
            thread["linked_comment_ids"].append(str(row["comment_id"]))
    for thread in thread_map.values():
        thread["linked_comment_ids"] = join_ordered(thread["linked_comment_ids"])
    ordered_rows = sorted(thread_map.values(), key=lambda item: (item["reviewer_id"], item["thread_order"], item["thread_id"]))
    return {"rows": ordered_rows}


def build_atomic_comments_context(connection: sqlite3.Connection) -> dict[str, Any]:
    source_index = build_comment_source_index(connection)
    target_index = build_comment_target_location_index(connection)
    rows = fetch_all(
        connection,
        """
        SELECT ac.comment_id, ac.comment_order, ac.canonical_summary, ac.required_action,
               acs.status, acs.priority, acs.evidence_gap
        FROM atomic_comments ac
        LEFT JOIN atomic_comment_state acs ON acs.comment_id = ac.comment_id
        ORDER BY ac.comment_order, ac.comment_id
        """,
    )
    payload_rows: list[dict[str, Any]] = []
    for row in rows:
        comment_id = str(row["comment_id"])
        source = source_index.get(comment_id, {"reviewers": [], "thread_ids": []})
        payload_rows.append(
            {
                "comment_id": comment_id,
                "source_reviewers": join_ordered(source["reviewers"]),
                "source_thread_ids": join_ordered(source["thread_ids"]),
                "status": str(row["status"] or ""),
                "priority": str(row["priority"] or ""),
                "evidence_gap": str(row["evidence_gap"] or ""),
                "canonical_summary": str(row["canonical_summary"]),
                "required_action": str(row["required_action"]),
                "target_locations": join_ordered(target_index.get(comment_id, [])),
            }
        )
    return {"rows": payload_rows}


def build_thread_to_atomic_mapping_context(connection: sqlite3.Connection) -> dict[str, Any]:
    rows = fetch_all(
        connection,
        """
        SELECT rrt.thread_id, rrt.reviewer_id, rrt.thread_order, rrt.original_text, rrt.normalized_summary,
               rtl.link_order, rtl.comment_id, ac.canonical_summary, acss.excerpt_text, acss.note
        FROM raw_review_threads rrt
        LEFT JOIN raw_thread_atomic_links rtl ON rtl.thread_id = rrt.thread_id
        LEFT JOIN atomic_comments ac ON ac.comment_id = rtl.comment_id
        LEFT JOIN atomic_comment_source_spans acss
          ON acss.thread_id = rtl.thread_id AND acss.comment_id = rtl.comment_id
        ORDER BY rrt.reviewer_id, rrt.thread_order, rtl.link_order
        """,
    )
    threads: dict[str, dict[str, Any]] = {}
    for row in rows:
        thread_id = str(row["thread_id"])
        thread = threads.setdefault(
            thread_id,
            {
                "thread_id": thread_id,
                "reviewer_id": str(row["reviewer_id"]),
                "thread_order": int(row["thread_order"]),
                "original_text": str(row["original_text"]),
                "normalized_summary": str(row["normalized_summary"]),
                "linked_items": [],
            },
        )
        if row["comment_id"] is not None:
            thread["linked_items"].append(
                {
                    "link_order": int(row["link_order"]),
                    "comment_id": str(row["comment_id"]),
                    "canonical_summary": str(row["canonical_summary"] or ""),
                    "excerpt_text": str(row["excerpt_text"] or ""),
                    "note": str(row["note"] or ""),
                }
            )
    ordered_threads = sorted(threads.values(), key=lambda item: (item["reviewer_id"], item["thread_order"], item["thread_id"]))
    return {"threads": ordered_threads}


def build_review_comment_coverage_context(connection: sqlite3.Connection) -> dict[str, Any]:
    rows = fetch_all(
        connection,
        """
        SELECT d.source_document_id, d.source_kind, d.document_order, d.source_label, d.source_path, d.original_text,
               s.segment_order, s.coverage_status, s.segment_text, s.thread_id,
               l.link_order, l.comment_id
        FROM review_comment_source_documents d
        LEFT JOIN review_comment_coverage_segments s ON s.source_document_id = d.source_document_id
        LEFT JOIN review_comment_coverage_segment_comment_links l
          ON l.source_document_id = s.source_document_id
         AND l.segment_order = s.segment_order
        ORDER BY d.document_order, d.source_document_id, s.segment_order, l.link_order
        """,
    )
    documents: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_document_id = str(row["source_document_id"])
        document = documents.setdefault(
            source_document_id,
            {
                "source_document_id": source_document_id,
                "source_kind": str(row["source_kind"]),
                "document_order": int(row["document_order"]),
                "source_label": str(row["source_label"]),
                "source_path": str(row["source_path"]),
                "original_text": str(row["original_text"]),
                "segments": [],
                "_segment_map": {},
                "_covered_threads": set(),
            },
        )
        if row["segment_order"] is None:
            continue
        segment_order = int(row["segment_order"])
        segment = document["_segment_map"].setdefault(
            segment_order,
            {
                "segment_order": segment_order,
                "coverage_status": str(row["coverage_status"]),
                "segment_text": str(row["segment_text"]),
                "thread_id": str(row["thread_id"] or ""),
                "comment_ids": [],
            },
        )
        if segment not in document["segments"]:
            document["segments"].append(segment)
        if row["comment_id"] is not None:
            segment["comment_ids"].append(str(row["comment_id"]))
        if segment["coverage_status"] == "covered" and segment["thread_id"]:
            document["_covered_threads"].add(segment["thread_id"])

    ordered_documents = sorted(documents.values(), key=lambda item: (item["document_order"], item["source_document_id"]))
    for document in ordered_documents:
        document["segments"] = sorted(document["segments"], key=lambda item: item["segment_order"])
        for segment in document["segments"]:
            segment["comment_ids"] = [comment_id for comment_id in dict.fromkeys(segment["comment_ids"]) if comment_id]
        document["covered_segments"] = sum(1 for segment in document["segments"] if segment["coverage_status"] == "covered")
        document["uncovered_segments"] = sum(1 for segment in document["segments"] if segment["coverage_status"] == "uncovered")
        document["covered_threads"] = len(document["_covered_threads"])
        document.pop("_segment_map", None)
        document.pop("_covered_threads", None)
    return {"documents": ordered_documents}


def build_atomic_workboard_context(connection: sqlite3.Connection) -> dict[str, Any]:
    source_index = build_comment_source_index(connection)
    target_index = build_comment_target_location_index(connection)
    analysis_index = build_comment_analysis_index(connection)
    rows = fetch_all(
        connection,
        """
        SELECT ac.comment_id, ac.comment_order, acs.status, acs.priority, acs.evidence_gap,
               acs.user_confirmation_needed, acs.next_action
        FROM atomic_comments ac
        LEFT JOIN atomic_comment_state acs ON acs.comment_id = ac.comment_id
        ORDER BY ac.comment_order, ac.comment_id
        """,
    )
    payload_rows: list[dict[str, Any]] = []
    for row in rows:
        comment_id = str(row["comment_id"])
        source = source_index.get(comment_id, {"reviewers": [], "thread_ids": []})
        analysis_lines = [
            f"{item['manuscript_claim_or_section']} | evidence: {item['existing_evidence']} | gap: {item['gap_summary']}"
            for item in analysis_index.get(comment_id, [])
        ]
        payload_rows.append(
            {
                "comment_id": comment_id,
                "source_reviewers": join_ordered(source["reviewers"]),
                "source_thread_ids": join_ordered(source["thread_ids"]),
                "status": str(row["status"] or ""),
                "priority": str(row["priority"] or ""),
                "evidence_gap": str(row["evidence_gap"] or ""),
                "target_locations": join_ordered(target_index.get(comment_id, [])),
                "analysis_summary": join_ordered(analysis_lines),
                "user_confirmation_needed": str(row["user_confirmation_needed"] or ""),
                "next_action": str(row["next_action"] or ""),
            }
        )
    return {"rows": payload_rows}


def build_style_profile_context(connection: sqlite3.Connection) -> dict[str, Any]:
    profile_rows = fetch_all(
        connection,
        """
        SELECT profile_target, profile_summary, anti_ai_focus
        FROM style_profiles
        ORDER BY CASE profile_target WHEN 'manuscript' THEN 1 WHEN 'response_letter' THEN 2 ELSE 99 END
        """,
    )
    rule_rows = fetch_all(
        connection,
        """
        SELECT profile_target, rule_order, rule_type, rule_text
        FROM style_profile_rules
        ORDER BY profile_target, rule_order
        """,
    )
    rules_by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rule_rows:
        rules_by_target[str(row["profile_target"])].append(
            {
                "rule_order": int(row["rule_order"]),
                "rule_type": str(row["rule_type"]),
                "rule_text": str(row["rule_text"]),
            }
        )
    profiles = [
        {
            "profile_target": str(row["profile_target"]),
            "profile_summary": str(row["profile_summary"]),
            "anti_ai_focus": str(row["anti_ai_focus"]),
            "rules": rules_by_target.get(str(row["profile_target"]), []),
        }
        for row in profile_rows
    ]
    return {"profiles": profiles}


def build_action_copy_variants_context(connection: sqlite3.Connection) -> dict[str, Any]:
    action_rows = fetch_all(
        connection,
        """
        SELECT comment_id, action_order, manuscript_change, expected_response_letter_effect
        FROM strategy_card_actions
        ORDER BY comment_id, action_order
        """,
    )
    variant_rows = fetch_all(
        connection,
        """
        SELECT comment_id, action_order, location_order, variant_label, variant_text, rationale
        FROM action_copy_variants
        ORDER BY comment_id, action_order, location_order, variant_label
        """,
    )
    selected_rows = fetch_all(
        connection,
        """
        SELECT comment_id, action_order, location_order, variant_label
        FROM selected_action_copy_variants
        ORDER BY comment_id, action_order, location_order
        """,
    )
    location_rows = fetch_all(
        connection,
        """
        SELECT comment_id, action_order, location_order, target_location
        FROM strategy_action_target_locations
        ORDER BY comment_id, action_order, location_order
        """,
    )
    selected_index = {
        (str(row["comment_id"]), int(row["action_order"]), int(row["location_order"])): str(row["variant_label"])
        for row in selected_rows
    }
    location_index: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in location_rows:
        location_key = (str(row["comment_id"]), int(row["action_order"]))
        location_index[location_key].append(
            {
                "location_order": int(row["location_order"]),
                "target_location": str(row["target_location"]),
                "manuscript_variants": [],
            }
        )
    variants_index: dict[tuple[str, int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in variant_rows:
        variant_key = (str(row["comment_id"]), int(row["action_order"]), int(row["location_order"]))
        selected_label = selected_index.get(variant_key, "")
        variants_index[variant_key].append(
            {
                "variant_label": str(row["variant_label"]),
                "selected": "yes" if str(row["variant_label"]) == selected_label else "no",
                "variant_text": str(row["variant_text"]),
                "rationale": str(row["rationale"]),
            }
        )
    items = []
    for row in action_rows:
        comment_id = str(row["comment_id"])
        action_order = int(row["action_order"])
        items.append(
            {
                "comment_id": comment_id,
                "action_order": action_order,
                "manuscript_change": str(row["manuscript_change"]),
                "expected_response_letter_effect": str(row["expected_response_letter_effect"]),
                "locations": [
                    {
                        **location,
                        "manuscript_variants": variants_index.get((comment_id, action_order, int(location["location_order"])), []),
                    }
                    for location in location_index.get((comment_id, action_order), [])
                ],
            }
        )
    return {"items": items}


def build_response_letter_outline_context(connection: sqlite3.Connection) -> dict[str, Any]:
    rows = fetch_all(
        connection,
        """
        SELECT rrt.thread_id, rrt.reviewer_id, rrt.thread_order, rrt.source_type, rrt.original_text, rrt.normalized_summary,
               rtrl.response_order, rtrl.response_role, rtrl.comment_id, ac.canonical_summary, sc.proposed_stance
        FROM raw_review_threads rrt
        LEFT JOIN response_thread_resolution_links rtrl ON rtrl.thread_id = rrt.thread_id
        LEFT JOIN atomic_comments ac ON ac.comment_id = rtrl.comment_id
        LEFT JOIN strategy_cards sc ON sc.comment_id = rtrl.comment_id
        ORDER BY rrt.reviewer_id, rrt.thread_order, rtrl.response_order
        """,
    )
    action_rows = fetch_all(
        connection,
        """
        SELECT sav.comment_id, sav.action_order, sav.location_order, satl.target_location, sav.variant_label, acv.variant_text
        FROM selected_action_copy_variants sav
        JOIN action_copy_variants acv
          ON acv.comment_id = sav.comment_id
         AND acv.action_order = sav.action_order
         AND acv.location_order = sav.location_order
         AND acv.variant_label = sav.variant_label
        JOIN strategy_action_target_locations satl
          ON satl.comment_id = sav.comment_id
         AND satl.action_order = sav.action_order
         AND satl.location_order = sav.location_order
        ORDER BY sav.comment_id, sav.action_order, sav.location_order
        """,
    )
    selected_index: dict[str, list[str]] = defaultdict(list)
    for row in action_rows:
        comment_id = str(row["comment_id"])
        selected_index[comment_id].append(
            f"L{row['location_order']} {row['target_location']} / {row['variant_label']}={row['variant_text']}"
        )
    final_row_map = {
        str(row["thread_id"]): {
            "original_comment": str(row["original_comment"]),
            "modification_scope": str(row["modification_scope"]),
            "key_revision_excerpt": str(row["key_revision_excerpt"]),
            "response_explanation": str(row["response_explanation"]),
        }
        for row in fetch_all(
            connection,
            """
            SELECT thread_id, original_comment, modification_scope, key_revision_excerpt, response_explanation
            FROM response_thread_rows
            ORDER BY thread_id
            """,
        )
    }

    reviewer_groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        reviewer_id = str(row["reviewer_id"])
        group = reviewer_groups.setdefault(
            reviewer_id,
            {
                "heading": reviewer_id,
                "threads": [],
                "_thread_map": {},
            },
        )
        thread_id = str(row["thread_id"])
        thread_map = group["_thread_map"]
        thread = thread_map.setdefault(
            thread_id,
            {
                "thread_id": thread_id,
                "thread_order": int(row["thread_order"]),
                "original_text": str(row["original_text"]),
                "normalized_summary": str(row["normalized_summary"]),
                "resolutions": [],
            },
        )
        if thread not in group["threads"]:
            group["threads"].append(thread)
        if row["comment_id"] is not None:
            comment_id = str(row["comment_id"])
            thread["resolutions"].append(
                {
                    "response_order": int(row["response_order"]),
                    "response_role": str(row["response_role"]),
                    "comment_id": comment_id,
                    "canonical_summary": str(row["canonical_summary"] or ""),
                    "selected_copy_summary": join_ordered(selected_index.get(comment_id, [])),
                }
            )
        thread["row_ready"] = "yes" if thread_id in final_row_map else "no"
        thread["final_row"] = final_row_map.get(
            thread_id,
            {
                "original_comment": "",
                "modification_scope": "",
                "key_revision_excerpt": "",
                "response_explanation": "",
            },
        )

    groups = sorted(reviewer_groups.values(), key=lambda item: item["heading"])
    for group in groups:
        group["threads"] = sorted(group["threads"], key=lambda item: (item["thread_order"], item["thread_id"]))
        group.pop("_thread_map", None)
    return {"reviewer_groups": groups}


def build_export_patch_plan_context(connection: sqlite3.Connection) -> dict[str, Any]:
    patch_set_rows = fetch_all(
        connection,
        """
        SELECT patch_set_id, artifact_kind, source_root, output_root, status
        FROM export_patch_sets
        ORDER BY patch_set_id
        """,
    )
    patch_rows = fetch_all(
        connection,
        """
        SELECT patch_set_id, patch_order, comment_id, action_order, location_order, target_file,
               operation, anchor_text, marked_text, clean_text, notes
        FROM export_patches
        ORDER BY patch_set_id, patch_order
        """,
    )
    patches_by_set: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in patch_rows:
        patches_by_set[str(row["patch_set_id"])].append(
            {
                "patch_order": int(row["patch_order"]),
                "comment_id": str(row["comment_id"]),
                "action_order": int(row["action_order"]),
                "location_order": int(row["location_order"]),
                "target_file": str(row["target_file"]),
                "operation": str(row["operation"]),
                "anchor_text": str(row["anchor_text"]).replace("\n", "\\n"),
                "marked_text": str(row["marked_text"]).replace("\n", "\\n"),
                "clean_text": str(row["clean_text"]).replace("\n", "\\n"),
                "notes": str(row["notes"]),
            }
        )
    patch_sets = [
        {
            "patch_set_id": str(row["patch_set_id"]),
            "artifact_kind": str(row["artifact_kind"]),
            "source_root": str(row["source_root"]),
            "output_root": str(row["output_root"]),
            "status": str(row["status"]),
            "patches": patches_by_set.get(str(row["patch_set_id"]), []),
        }
        for row in patch_set_rows
    ]
    return {"patch_sets": patch_sets}


def build_response_letter_table_preview_context(connection: sqlite3.Connection) -> dict[str, Any]:
    rows = fetch_all(
        connection,
        """
        SELECT rrt.reviewer_id, rrt.thread_order, rrt.thread_id,
               rtr.original_comment, rtr.modification_scope, rtr.key_revision_excerpt, rtr.response_explanation,
               rtr.latex_excerpt, rtr.latex_response_text
        FROM raw_review_threads rrt
        JOIN response_thread_rows rtr ON rtr.thread_id = rrt.thread_id
        ORDER BY rrt.reviewer_id, rrt.thread_order, rrt.thread_id
        """,
    )
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        reviewer_id = str(row["reviewer_id"])
        group = groups.setdefault(
            reviewer_id,
            {
                "heading": reviewer_id,
                "heading_tex": tex_escape(reviewer_id),
                "rows": [],
            },
        )
        group["rows"].append(
            {
                "thread_id": str(row["thread_id"]),
                "original_comment": str(row["original_comment"]),
                "modification_scope": str(row["modification_scope"]),
                "key_revision_excerpt": str(row["key_revision_excerpt"]),
                "response_explanation": str(row["response_explanation"]),
                "original_comment_tex": tex_escape(str(row["original_comment"])),
                "modification_scope_tex": tex_escape(str(row["modification_scope"])),
                "key_revision_excerpt_tex": tex_escape(str(row["latex_excerpt"] or row["key_revision_excerpt"])),
                "response_explanation_tex": tex_escape(str(row["latex_response_text"] or row["response_explanation"])),
            }
        )
    return {"reviewer_groups": [groups[key] for key in sorted(groups)]}


def build_supplement_intake_plan_context(connection: sqlite3.Connection) -> dict[str, Any]:
    intake_rows = fetch_all(
        connection,
        """
        SELECT round_id, file_path, concern_summary, decision, decision_rationale
        FROM supplement_intake_items
        ORDER BY round_id, file_path
        """,
    )
    landing_rows = fetch_all(
        connection,
        """
        SELECT round_id, file_path, comment_id, action_order, location_order, planned_usage_note
        FROM supplement_landing_links
        ORDER BY round_id, file_path, comment_id, action_order, location_order
        """,
    )
    landing_index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in landing_rows:
        key = (str(row["round_id"]), str(row["file_path"]))
        landing_index[key].append(
            {
                "comment_id": str(row["comment_id"]),
                "action_order": int(row["action_order"]),
                "location_order": int(row["location_order"]),
                "planned_usage_note": str(row["planned_usage_note"]),
            }
        )

    grouped: dict[str, dict[str, Any]] = {}
    for row in intake_rows:
        round_id = str(row["round_id"])
        file_path = str(row["file_path"])
        group = grouped.setdefault(round_id, {"round_id": round_id, "items": []})
        group["items"].append(
            {
                "file_path": file_path,
                "concern_summary": str(row["concern_summary"]),
                "decision": str(row["decision"]),
                "decision_rationale": str(row["decision_rationale"]),
                "landing_links": landing_index.get((round_id, file_path), []),
            }
        )
    return {"round_groups": [grouped[key] for key in sorted(grouped)]}


def build_supplement_suggestion_plan_context(connection: sqlite3.Connection) -> dict[str, Any]:
    workflow_state = fetch_one(connection, "SELECT active_comment_id FROM workflow_state WHERE id = 1")
    active_comment_id = str(workflow_state["active_comment_id"]) if workflow_state is not None and workflow_state["active_comment_id"] is not None else ""
    rows = fetch_all(
        connection,
        """
        SELECT ssi.comment_id, ssi.suggestion_order, ssi.analysis_order, ssi.request_summary,
               ssi.request_recommendation, ssi.status, ac.canonical_summary, ac.required_action
        FROM supplement_suggestion_items ssi
        JOIN atomic_comments ac ON ac.comment_id = ssi.comment_id
        ORDER BY CASE WHEN ssi.comment_id = ? THEN 0 ELSE 1 END,
                 ssi.comment_id, ssi.suggestion_order
        """,
        (active_comment_id,),
    )
    intake_links = fetch_all(
        connection,
        """
        SELECT comment_id, suggestion_order, round_id, file_path, link_note
        FROM supplement_suggestion_intake_links
        ORDER BY comment_id, suggestion_order, round_id, file_path
        """,
    )
    link_index: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in intake_links:
        key = (str(row["comment_id"]), int(row["suggestion_order"]))
        link_index[key].append(
            {
                "round_id": str(row["round_id"]),
                "file_path": str(row["file_path"]),
                "link_note": str(row["link_note"]),
            }
        )

    groups: list[dict[str, Any]] = []
    by_comment: dict[str, dict[str, Any]] = {}
    for row in rows:
        comment_id = str(row["comment_id"])
        if comment_id not in by_comment:
            group = {
                "comment_id": comment_id,
                "canonical_summary": str(row["canonical_summary"]),
                "required_action": str(row["required_action"]),
                "is_active": comment_id == active_comment_id,
                "items": [],
            }
            by_comment[comment_id] = group
            groups.append(group)
        by_comment[comment_id]["items"].append(
            {
                "suggestion_order": int(row["suggestion_order"]),
                "analysis_order": int(row["analysis_order"]) if row["analysis_order"] is not None else None,
                "request_summary": str(row["request_summary"]),
                "request_recommendation": str(row["request_recommendation"]),
                "status": str(row["status"]),
                "intake_links": link_index.get((comment_id, int(row["suggestion_order"])), []),
            }
        )
    active_group = next((group for group in groups if group["is_active"]), None)
    return {
        "active_comment_id": active_comment_id,
        "active_group": active_group,
        "comment_groups": groups,
    }


def build_final_checklist_context(connection: sqlite3.Connection) -> dict[str, Any]:
    source_index = build_comment_source_index(connection)
    target_index = build_comment_target_location_index(connection)
    atomic_rows = fetch_all(
        connection,
        """
        SELECT ac.comment_id, ac.comment_order, acs.status, acs.priority, acs.evidence_gap,
               ccs.manuscript_draft_done, ccs.response_draft_done, ccs.one_to_one_link_checked, ccs.export_ready
        FROM atomic_comments ac
        LEFT JOIN atomic_comment_state acs ON acs.comment_id = ac.comment_id
        LEFT JOIN comment_completion_status ccs ON ccs.comment_id = ac.comment_id
        ORDER BY ac.comment_order, ac.comment_id
        """,
    )
    atomic_payload: list[dict[str, Any]] = []
    export_ready_index: dict[str, str] = {}
    for row in atomic_rows:
        comment_id = str(row["comment_id"])
        source = source_index.get(comment_id, {"reviewers": [], "thread_ids": []})
        export_ready = str(row["export_ready"] or "")
        export_ready_index[comment_id] = export_ready
        atomic_payload.append(
            {
                "comment_id": comment_id,
                "source_reviewers": join_ordered(source["reviewers"]),
                "source_thread_ids": join_ordered(source["thread_ids"]),
                "status": str(row["status"] or ""),
                "priority": str(row["priority"] or ""),
                "evidence_gap": str(row["evidence_gap"] or ""),
                "target_locations": join_ordered(target_index.get(comment_id, [])),
                "manuscript_draft_done": str(row["manuscript_draft_done"] or ""),
                "response_draft_done": str(row["response_draft_done"] or ""),
                "one_to_one_link_checked": str(row["one_to_one_link_checked"] or ""),
                "export_ready": export_ready,
            }
        )

    thread_rows = fetch_all(
        connection,
        """
        SELECT rrt.thread_id, rrt.reviewer_id, rtl.comment_id, rtrl.comment_id AS outlined_comment_id
        FROM raw_review_threads rrt
        LEFT JOIN raw_thread_atomic_links rtl ON rtl.thread_id = rrt.thread_id
        LEFT JOIN response_thread_resolution_links rtrl ON rtrl.thread_id = rrt.thread_id
        ORDER BY rrt.reviewer_id, rrt.thread_order, rtl.link_order
        """,
    )
    thread_index: dict[str, dict[str, Any]] = {}
    for row in thread_rows:
        thread_id = str(row["thread_id"])
        item = thread_index.setdefault(
            thread_id,
            {
                "thread_id": thread_id,
                "reviewer_id": str(row["reviewer_id"]),
                "linked_comment_ids": [],
                "outlined_comment_ids": [],
            },
        )
        if row["comment_id"] is not None:
            item["linked_comment_ids"].append(str(row["comment_id"]))
        if row["outlined_comment_id"] is not None:
            item["outlined_comment_ids"].append(str(row["outlined_comment_id"]))

    thread_payload: list[dict[str, Any]] = []
    response_row_ids = {
        str(row["thread_id"])
        for row in fetch_all(connection, "SELECT thread_id FROM response_thread_rows ORDER BY thread_id")
    }
    for thread_id, item in sorted(thread_index.items()):
        linked_comment_ids = [value for value in item["linked_comment_ids"] if value]
        outlined_comment_ids = {value for value in item["outlined_comment_ids"] if value}
        response_outline_ready = "yes" if linked_comment_ids and all(comment_id in outlined_comment_ids for comment_id in linked_comment_ids) else "no"
        response_row_ready = "yes" if thread_id in response_row_ids else "no"
        linked_atomic_export_ready = (
            "yes"
            if linked_comment_ids and all(export_ready_index.get(comment_id) == "yes" for comment_id in linked_comment_ids)
            else "no"
        )
        thread_export_ready = "yes" if response_outline_ready == "yes" and response_row_ready == "yes" and linked_atomic_export_ready == "yes" else "no"
        thread_payload.append(
            {
                "thread_id": thread_id,
                "reviewer_id": item["reviewer_id"],
                "linked_comment_ids": join_ordered(linked_comment_ids),
                "response_outline_ready": response_outline_ready,
                "response_row_ready": response_row_ready,
                "linked_atomic_export_ready": linked_atomic_export_ready,
                "thread_export_ready": thread_export_ready,
            }
        )
    export_rows = [dict(row) for row in fetch_all(connection, "SELECT artifact_name, artifact_status, output_path FROM export_artifacts ORDER BY artifact_name")]
    return {"atomic_rows": atomic_payload, "thread_rows": thread_payload, "export_rows": export_rows}


def build_strategy_card_context(
    connection: sqlite3.Connection,
    comment_id: str,
    *,
    localization: LocalizationBundle | None = None,
) -> dict[str, Any]:
    source_index = build_comment_source_index(connection)
    target_index = build_comment_target_location_index(connection)
    header = fetch_one(
        connection,
        """
        SELECT ac.comment_id, ac.canonical_summary, ac.required_action,
               acs.status, acs.priority, acs.evidence_gap,
               sc.proposed_stance, sc.stance_rationale,
               ccs.manuscript_draft_done, ccs.response_draft_done, ccs.evidence_gap_closed,
               ccs.user_strategy_confirmed
        FROM atomic_comments ac
        LEFT JOIN atomic_comment_state acs ON acs.comment_id = ac.comment_id
        LEFT JOIN strategy_cards sc ON sc.comment_id = ac.comment_id
        LEFT JOIN comment_completion_status ccs ON ccs.comment_id = ac.comment_id
        WHERE ac.comment_id = ?
        """,
        (comment_id,),
    )
    if header is None:
        raise ValueError(f"unknown comment_id: {comment_id}")
    action_location_index = build_strategy_action_location_index(connection)
    action_target_detail_index = build_strategy_action_target_detail_index(connection)
    actions = fetch_all(
        connection,
        """
        SELECT action_order, manuscript_change, expected_response_letter_effect
        FROM strategy_card_actions
        WHERE comment_id = ?
        ORDER BY action_order
        """,
        (comment_id,),
    )
    evidence_rows = fetch_all(
        connection,
        """
        SELECT evidence_order, required_material, available_now, gap_note
        FROM strategy_card_evidence_items
        WHERE comment_id = ?
        ORDER BY evidence_order
        """,
        (comment_id,),
    )
    confirmations = fetch_all(
        connection,
        """
        SELECT message
        FROM strategy_card_pending_confirmations
        WHERE comment_id = ?
        ORDER BY confirmation_order
        """,
        (comment_id,),
    )
    draft_rows = fetch_all(
        connection,
        """
        SELECT comment_id, action_order, location_order, draft_text, rationale
        FROM strategy_action_manuscript_drafts
        WHERE comment_id = ?
        ORDER BY action_order, location_order
        """,
        (comment_id,),
    )
    response_draft = fetch_one(
        connection,
        """
        SELECT draft_text, rationale
        FROM comment_response_drafts
        WHERE comment_id = ?
        """,
        (comment_id,),
    )
    blocker_rows = fetch_all(
        connection,
        """
        SELECT blocker_order, message
        FROM comment_blockers
        WHERE comment_id = ?
        ORDER BY blocker_order
        """,
        (comment_id,),
    )
    source = source_index.get(comment_id, {"reviewers": [], "thread_ids": []})
    draft_index = {
        (str(row["comment_id"]), int(row["action_order"]), int(row["location_order"])): {
            "draft_text": str(row["draft_text"]),
            "rationale": str(row["rationale"]),
        }
        for row in draft_rows
    }
    action_payload = [
        {
            "action_order": int(row["action_order"]),
            "manuscript_change": str(row["manuscript_change"]),
            "target_locations": join_ordered(action_location_index.get((comment_id, int(row["action_order"])), [])),
            "expected_response_letter_effect": str(row["expected_response_letter_effect"]),
            "draft_rows": [
                {
                    "location_order": int(location["location_order"]),
                    "target_location": str(location["target_location"]),
                    "draft_text": draft_index.get((comment_id, int(row["action_order"]), int(location["location_order"])), {}).get("draft_text", ""),
                    "rationale": draft_index.get((comment_id, int(row["action_order"]), int(location["location_order"])), {}).get("rationale", ""),
                }
                for location in action_target_detail_index.get((comment_id, int(row["action_order"])), [])
            ],
        }
        for row in actions
    ]
    header_payload = dict(header)
    header_payload["source_reviewers"] = join_ordered(source["reviewers"])
    header_payload["source_thread_ids"] = join_ordered(source["thread_ids"])
    header_payload["target_locations"] = join_ordered(target_index.get(comment_id, []))
    strategy_confirmed = str(header["user_strategy_confirmed"] or "no") == "yes"
    return {
        "header": header_payload,
        "strategy_confirmed": strategy_confirmed,
        "actions": action_payload,
        "evidence_rows": [dict(row) for row in evidence_rows],
        "pending_confirmations": [str(row["message"]) for row in confirmations],
        "response_draft": {
            "draft_text": str(response_draft["draft_text"]) if response_draft is not None else "",
            "rationale": str(response_draft["rationale"]) if response_draft is not None else "",
        },
        "comment_blockers": [str(row["message"]) for row in blocker_rows],
        "drafts_present": bool(draft_rows) or response_draft is not None,
        "completion_lines": [
            {
                "label": localization.msg("view.strategy_card.check.manuscript_draft_done")
                if localization is not None
                else "Manuscript draft is present",
                "checked": str(header["manuscript_draft_done"] or "no") == "yes",
            },
            {
                "label": localization.msg("view.strategy_card.check.response_draft_done")
                if localization is not None
                else "Matching response draft is present",
                "checked": str(header["response_draft_done"] or "no") == "yes",
            },
            {
                "label": localization.msg("view.strategy_card.check.evidence_gap_closed")
                if localization is not None
                else "Evidence gap is closed",
                "checked": str(header["evidence_gap_closed"] or "no") == "yes",
            },
            {
                "label": localization.msg("view.strategy_card.check.user_strategy_confirmed")
                if localization is not None
                else "User has confirmed this strategy",
                "checked": str(header["user_strategy_confirmed"] or "no") == "yes",
            },
        ],
    }


def get_view_context(
    connection: sqlite3.Connection,
    view_name: str,
    *,
    comment_id: str | None = None,
    resume_context: dict[str, Any] | None = None,
    localization: LocalizationBundle | None = None,
) -> dict[str, Any]:
    if view_name == "agent_resume":
        context = build_agent_resume_context(connection, resume_context=resume_context, localization=localization)
    elif view_name == "manuscript_summary":
        context = build_manuscript_summary_context(connection)
    elif view_name == "raw_review_threads":
        context = build_raw_review_threads_context(connection)
    elif view_name == "atomic_comments":
        context = build_atomic_comments_context(connection)
    elif view_name == "thread_to_atomic_mapping":
        context = build_thread_to_atomic_mapping_context(connection)
    elif view_name == "review_comment_coverage":
        context = build_review_comment_coverage_context(connection)
    elif view_name == "atomic_workboard":
        context = build_atomic_workboard_context(connection)
    elif view_name == "style_profile":
        context = build_style_profile_context(connection)
    elif view_name == "action_copy_variants":
        context = build_action_copy_variants_context(connection)
    elif view_name == "response_letter_outline":
        context = build_response_letter_outline_context(connection)
    elif view_name == "export_patch_plan":
        context = build_export_patch_plan_context(connection)
    elif view_name == "response_letter_table_preview_md":
        context = build_response_letter_table_preview_context(connection)
    elif view_name == "response_letter_table_preview_tex":
        context = build_response_letter_table_preview_context(connection)
    elif view_name == "supplement_suggestion_plan":
        context = build_supplement_suggestion_plan_context(connection)
    elif view_name == "supplement_intake_plan":
        context = build_supplement_intake_plan_context(connection)
    elif view_name == "final_checklist":
        context = build_final_checklist_context(connection)
    elif view_name == "response_strategy_card":
        if comment_id is None:
            raise RuntimeError("response_strategy_card rendering requires comment_id")
        context = build_strategy_card_context(connection, comment_id, localization=localization)
    else:
        raise RuntimeError(f"unknown render view: {view_name}")
    context.setdefault("language_context", localization.snapshot() if localization is not None else fetch_runtime_language_context(connection))
    return context


def render_workspace(
    db_path: Path,
    artifact_root: Path,
    *,
    resume_context: dict[str, Any] | None = None,
) -> list[Path]:
    manifest = load_render_manifest()
    views = manifest.get("views", [])
    if not isinstance(views, list) or not views:
        raise RuntimeError("render-manifest.yaml must define a non-empty 'views' list")
    paths = artifact_paths(artifact_root)
    artifact_root.mkdir(parents=True, exist_ok=True)
    paths["strategy_card_dir"].mkdir(parents=True, exist_ok=True)
    paths["localization_root"].mkdir(parents=True, exist_ok=True)
    paths["localization_template_override_dir"].mkdir(parents=True, exist_ok=True)
    cleanup_legacy_runtime_views(artifact_root)
    rendered_paths: list[Path] = []
    with connect_db(db_path) as connection:
        ensure_runtime_schema_compatibility(connection)
        runtime_context = fetch_runtime_language_context(connection)
        seed_workspace_localization_overlay(
            artifact_root,
            working_language=runtime_context["working_language"],
            document_language=runtime_context["document_language"],
        )
        localization = load_localization_bundle(
            artifact_root,
            runtime_context=runtime_context,
        )
        env = create_template_environment(localization)
        assert jinja2 is not None
        for view in views:
            if not isinstance(view, dict):
                raise RuntimeError("each render manifest view entry must be a mapping")
            name = str(view.get("name", ""))
            template_name = str(view.get("template", ""))
            mode = str(view.get("mode", "single"))
            try:
                template = env.get_template(template_name)
            except jinja2.TemplateNotFound as exc:
                raise FileNotFoundError(f"missing template: {template_name}") from exc

            if mode == "single":
                output_name = str(view.get("output", ""))
                if not output_name:
                    raise RuntimeError(f"render view '{name}' must define 'output'")
                output_path = artifact_root / output_name
                context = get_view_context(connection, name, resume_context=resume_context, localization=localization)
                output_path.write_text(template.render(**context), encoding="utf-8")
                rendered_paths.append(output_path)
                continue

            if mode == "per_comment":
                output_dir = str(view.get("output_dir", ""))
                filename_pattern = str(view.get("filename_pattern", ""))
                if not output_dir or not filename_pattern:
                    raise RuntimeError(f"render view '{name}' must define 'output_dir' and 'filename_pattern'")
                card_dir = artifact_root / output_dir
                card_dir.mkdir(parents=True, exist_ok=True)
                comment_rows = fetch_all(connection, "SELECT comment_id FROM atomic_comments ORDER BY comment_order, comment_id")
                expected_cards = {filename_pattern.format(comment_id=str(row["comment_id"])) for row in comment_rows}
                for existing in card_dir.glob("*.md"):
                    if existing.name not in expected_cards:
                        existing.unlink()
                for row in comment_rows:
                    comment_id = str(row["comment_id"])
                    card_path = card_dir / filename_pattern.format(comment_id=comment_id)
                    context = get_view_context(
                        connection,
                        name,
                        comment_id=comment_id,
                        resume_context=resume_context,
                        localization=localization,
                    )
                    card_path.write_text(template.render(**context), encoding="utf-8")
                    rendered_paths.append(card_path)
                continue

            raise RuntimeError(f"unsupported render mode '{mode}' for view '{name}'")
    return rendered_paths

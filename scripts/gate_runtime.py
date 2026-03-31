from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from runtime_db import (  # noqa: E402
    ALLOWED_STAGES,
    connect_db,
    default_db_path,
    fetch_artifact_registry,
    fetch_runtime_inputs,
    fetch_workflow_state,
)

ASSETS_DIR = SCRIPT_DIR.parent / "assets"
CORE_INSTRUCTION_PATH = ASSETS_DIR / "core_instruction.md"


STAGE_RULES: dict[str, dict[str, Any]] = {
    "stage_0_bootstrap": {
        "required_reads": [],
        "required_writes": ["workflow_state", "runtime_inputs"],
    },
    "stage_1_normalize_source": {
        "required_reads": ["runtime_inputs.source_path", "runtime_inputs.language", "runtime_inputs.generated_at", "runtime_inputs.input_hash"],
        "required_writes": ["source_documents.normalized_source"],
    },
    "stage_2_outline_and_scopes": {
        "required_reads": ["source_documents.normalized_source"],
        "required_writes": ["outline_nodes", "section_scopes"],
    },
    "stage_3_digest": {
        "required_reads": ["source_documents.normalized_source", "outline_nodes"],
        "required_writes": ["digest_slots", "digest_section_summaries"],
    },
    "stage_4_references": {
        "required_reads": ["source_documents.normalized_source", "section_scopes.references_scope"],
        "required_writes": ["reference_entries", "reference_batches", "reference_parse_candidates", "reference_items"],
    },
    "stage_5_citation": {
        "required_reads": ["source_documents.normalized_source", "section_scopes.citation_scope"],
        "required_writes": [
            "citation_mentions",
            "citation_mention_links",
            "citation_workset_items",
            "citation_batches",
            "citation_items",
            "citation_timeline",
            "citation_summary",
            "citation_unmapped_mentions",
        ],
    },
    "stage_6_render_and_validate": {
        "required_reads": [
            "digest_slots",
            "digest_section_summaries",
            "reference_items",
            "section_scopes.citation_scope",
            "citation_workset_items",
            "citation_items",
            "citation_timeline",
            "citation_summary",
            "citation_unmapped_mentions",
        ],
        "required_writes": ["artifact_registry"],
    },
    "stage_7_completed": {
        "required_reads": ["artifact_registry"],
        "required_writes": [],
    },
}


STAGE_DOCS: dict[str, str] = {
    "stage_0_bootstrap": "references/step_01_bootstrap_and_source.md",
    "stage_1_normalize_source": "references/step_01_bootstrap_and_source.md",
    "stage_2_outline_and_scopes": "references/step_02_outline_and_scopes.md",
    "stage_3_digest": "references/step_03_digest_generation.md",
    "stage_4_references": "references/step_04_references_extraction.md",
    "stage_5_citation": "references/step_05_citation_pipeline.md",
    "stage_6_render_and_validate": "references/step_06_render_and_validate.md",
    "stage_7_completed": "references/step_06_render_and_validate.md",
}


ACTION_SQL_EXAMPLES: dict[str, list[dict[str, str]]] = {
    "bootstrap_runtime_db": [
        {
            "purpose": "inspect expected tables after initialization",
            "sql": "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name;",
            "notes": "Use after init to confirm the runtime schema exists.",
        },
        {
            "purpose": "seed source_path input",
            "sql": "INSERT INTO runtime_inputs (key, value, updated_at) VALUES ('source_path', :source_path, :updated_at) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;",
            "notes": "The first actionable input after bootstrap is the normalized source path contract.",
        },
    ],
    "normalize_source": [
        {
            "purpose": "read the input path before normalization",
            "sql": "SELECT value FROM runtime_inputs WHERE key = 'source_path';",
            "notes": "Normalization should only start after source_path is present.",
        },
        {
            "purpose": "persist normalized markdown",
            "sql": "INSERT INTO source_documents (doc_key, content, metadata_json, updated_at) VALUES ('normalized_source', :content, :metadata_json, :updated_at) ON CONFLICT(doc_key) DO UPDATE SET content = excluded.content, metadata_json = excluded.metadata_json, updated_at = excluded.updated_at;",
            "notes": "Store the normalized markdown before later stages read it.",
        },
    ],
    "persist_outline_and_scopes": [
        {
            "purpose": "confirm the normalized source is present",
            "sql": "SELECT doc_key, LENGTH(content) AS content_length FROM source_documents WHERE doc_key = 'normalized_source';",
            "notes": "Outline extraction should read only the normalized source.",
        },
        {
            "purpose": "persist an outline node",
            "sql": "INSERT INTO outline_nodes (node_id, heading_level, title, line_start, line_end, parent_node_id, position, metadata_json) VALUES (:node_id, :heading_level, :title, :line_start, :line_end, :parent_node_id, :position, :metadata_json);",
            "notes": "Repeat for each outline node in order.",
        },
        {
            "purpose": "persist a section scope",
            "sql": "INSERT INTO section_scopes (scope_key, section_title, line_start, line_end, metadata_json, updated_at) VALUES (:scope_key, :section_title, :line_start, :line_end, :metadata_json, :updated_at) ON CONFLICT(scope_key) DO UPDATE SET section_title = excluded.section_title, line_start = excluded.line_start, line_end = excluded.line_end, metadata_json = excluded.metadata_json, updated_at = excluded.updated_at;",
            "notes": "Use this for references_scope or citation_scope after outline analysis.",
        },
    ],
    "persist_digest": [
        {
            "purpose": "inspect outline before digest generation",
            "sql": "SELECT node_id, title, heading_level, line_start, line_end FROM outline_nodes ORDER BY position;",
            "notes": "Digest persistence should align with the stored outline order.",
        },
        {
            "purpose": "persist a digest slot",
            "sql": "INSERT INTO digest_slots (slot_key, content_json, updated_at) VALUES (:slot_key, :content_json, :updated_at) ON CONFLICT(slot_key) DO UPDATE SET content_json = excluded.content_json, updated_at = excluded.updated_at;",
            "notes": "Store each structured digest slot before final Markdown rendering.",
        },
        {
            "purpose": "persist section summaries",
            "sql": "INSERT INTO digest_section_summaries (position, source_heading, items_json, updated_at) VALUES (:position, :source_heading, :items_json, :updated_at) ON CONFLICT(position) DO UPDATE SET source_heading = excluded.source_heading, items_json = excluded.items_json, updated_at = excluded.updated_at;",
            "notes": "Store one summary row per source section in final order.",
        },
    ],
    "prepare_references_workset": [
        {
            "purpose": "inspect references scope before deterministic preparse",
            "sql": "SELECT scope_key, section_title, line_start, line_end FROM section_scopes WHERE scope_key = 'references_scope';",
            "notes": "Stage 4 workset preparation must only read the stored references_scope.",
        },
        {
            "purpose": "persist reference parse candidates",
            "sql": "INSERT INTO reference_parse_candidates (entry_index, candidate_index, pattern, author_text, author_candidates_json, title_candidate, container_candidate, year_candidate, confidence, metadata_json, updated_at) VALUES (:entry_index, :candidate_index, :pattern, :author_text, :author_candidates_json, :title_candidate, :container_candidate, :year_candidate, :confidence, :metadata_json, :updated_at);",
            "notes": "Keep every viable split candidate so the agent can choose a pattern instead of reparsing from raw text.",
        },
        {
            "purpose": "inspect prepared candidate counts by entry",
            "sql": "SELECT entry_index, COUNT(*) AS candidate_count FROM reference_parse_candidates GROUP BY entry_index ORDER BY entry_index;",
            "notes": "Use after preparation to confirm ambiguous entries retained multiple patterns.",
        },
    ],
    "persist_reference_entry_splits": [
        {
            "purpose": "inspect currently prepared raw reference entries before split review",
            "sql": "SELECT entry_index, raw, metadata_json FROM reference_entries ORDER BY entry_index;",
            "notes": "Use when deterministic splitting left grouped author-year entries that need boundary review.",
        },
        {
            "purpose": "inspect current grouped-entry suspicion warnings",
            "sql": "SELECT warning FROM runtime_warnings WHERE warning LIKE 'reference_entry_grouping_suspect:%' ORDER BY id;",
            "notes": "Split review is only for correcting raw entry boundaries, not for semantic field extraction.",
        },
    ],
    "persist_references": [
        {
            "purpose": "inspect prepared candidates before agent refinement",
            "sql": "SELECT entry_index, candidate_index, pattern, author_text, title_candidate, year_candidate FROM reference_parse_candidates ORDER BY entry_index, candidate_index;",
            "notes": "The agent must choose a selected_pattern that already exists in this candidate set.",
        },
        {
            "purpose": "persist refined reference items",
            "sql": "INSERT INTO reference_items (ref_index, author_json, title, year, raw, confidence, metadata_json, updated_at) VALUES (:ref_index, :author_json, :title, :year, :raw, :confidence, :metadata_json, :updated_at);",
            "notes": "ref_index is derived deterministically from entry_index after the selected_pattern is validated.",
        },
    ],
    "prepare_citation_workset": [
        {
            "purpose": "inspect citation scope before workset preparation",
            "sql": "SELECT scope_key, section_title, line_start, line_end FROM section_scopes WHERE scope_key = 'citation_scope';",
            "notes": "Use the stored citation scope when preparing the deterministic citation workset.",
        },
        {
            "purpose": "persist mapped mention links",
            "sql": "INSERT INTO citation_mention_links (mention_id, ref_index, status, resolution_method, resolution_confidence, evidence_json, updated_at) VALUES (:mention_id, :ref_index, :status, :resolution_method, :resolution_confidence, :evidence_json, :updated_at);",
            "notes": "Each mention is resolved once into a mapped or unmapped link row.",
        },
        {
            "purpose": "persist prepared citation workset items",
            "sql": "INSERT INTO citation_workset_items (ref_index, ref_number, mention_count, mentions_json, reference_snapshot_json, batch_hint, workset_metadata_json, updated_at) VALUES (:ref_index, :ref_number, :mention_count, :mentions_json, :reference_snapshot_json, :batch_hint, :workset_metadata_json, :updated_at);",
            "notes": "Semantic analysis should read these rows instead of rebuilding mention-reference joins.",
        },
        {
            "purpose": "persist extracted mentions",
            "sql": "INSERT INTO citation_mentions (mention_id, marker, style, line_start, line_end, snippet, ref_number_hint, year_hint, surname_hint, batch_index, consumed_status, metadata_json, updated_at) VALUES (:mention_id, :marker, :style, :line_start, :line_end, :snippet, :ref_number_hint, :year_hint, :surname_hint, :batch_index, :consumed_status, :metadata_json, :updated_at);",
            "notes": "One row per mention extracted from the active scope before workset aggregation.",
        },
    ],
    "persist_citation_semantics": [
        {
            "purpose": "inspect prepared workset items",
            "sql": "SELECT ref_index, ref_number, mention_count, batch_hint FROM citation_workset_items ORDER BY ref_index;",
            "notes": "Semantic analysis should operate over prepared workset items keyed by ref_index.",
        },
        {
            "purpose": "persist semantic analysis for a workset item",
            "sql": "INSERT INTO citation_items (ref_index, function, summary, confidence, metadata_json, updated_at) VALUES (:ref_index, :function, :summary, :confidence, :metadata_json, :updated_at);",
            "notes": "Each ref_index may appear only once and must already exist in citation_workset_items.",
        },
    ],
    "persist_citation_timeline": [
        {
            "purpose": "inspect semantic items before timeline synthesis",
            "sql": "SELECT ref_index, function, summary, confidence FROM citation_items ORDER BY ref_index;",
            "notes": "Timeline analysis is a separate stage-5 task that runs after item semantics exist.",
        },
        {
            "purpose": "persist the citation timeline",
            "sql": "INSERT INTO citation_timeline (id, timeline_json, updated_at) VALUES (1, :timeline_json, :updated_at) ON CONFLICT(id) DO UPDATE SET timeline_json = excluded.timeline_json, updated_at = excluded.updated_at;",
            "notes": "Store the structured early/mid/recent timeline before the global summary is written.",
        },
    ],
    "persist_citation_summary": [
        {
            "purpose": "inspect semantic items and timeline before writing the global summary",
            "sql": "SELECT (SELECT COUNT(*) FROM citation_items) AS citation_items, (SELECT COUNT(*) FROM citation_timeline) AS citation_timeline;",
            "notes": "The global summary must synthesize persisted item-level analyses together with the stored timeline.",
        },
        {
            "purpose": "persist the global citation summary",
            "sql": "INSERT INTO citation_summary (id, summary_text, basis_json, updated_at) VALUES (1, :summary_text, :basis_json, :updated_at) ON CONFLICT(id) DO UPDATE SET summary_text = excluded.summary_text, basis_json = excluded.basis_json, updated_at = excluded.updated_at;",
            "notes": "Final citation artifacts require a non-empty global summary.",
        },
    ],
    "repair_workflow_state": [
        {
            "purpose": "inspect the current workflow row",
            "sql": "SELECT * FROM workflow_state WHERE id = 1;",
            "notes": "Use before rewriting the state machine row.",
        },
        {
            "purpose": "repair the workflow state row",
            "sql": "INSERT INTO workflow_state (id, current_stage, current_substep, stage_gate, next_action, active_batch_kind, active_batch_index, status_summary, last_error_code, updated_at) VALUES (1, :current_stage, :current_substep, :stage_gate, :next_action, :active_batch_kind, :active_batch_index, :status_summary, :last_error_code, :updated_at) ON CONFLICT(id) DO UPDATE SET current_stage = excluded.current_stage, current_substep = excluded.current_substep, stage_gate = excluded.stage_gate, next_action = excluded.next_action, active_batch_kind = excluded.active_batch_kind, active_batch_index = excluded.active_batch_index, status_summary = excluded.status_summary, last_error_code = excluded.last_error_code, updated_at = excluded.updated_at;",
            "notes": "Repair to a legal stage/substep pair before resuming.",
        },
    ],
    "repair_db_state": [
        {
            "purpose": "inspect the missing prerequisite area",
            "sql": "SELECT key, value FROM runtime_inputs UNION ALL SELECT doc_key AS key, substr(content, 1, 80) AS value FROM source_documents;",
            "notes": "Adjust the query to the missing prerequisite named in status_summary.",
        },
        {
            "purpose": "repair the workflow row after fixing the missing data",
            "sql": "UPDATE workflow_state SET stage_gate = 'ready', next_action = :next_action, status_summary = :status_summary, updated_at = :updated_at WHERE id = 1;",
            "notes": "Only do this after restoring the prerequisite records.",
        },
    ],
    "render_and_validate": [
        {
            "purpose": "verify all render inputs are present",
            "sql": "SELECT (SELECT COUNT(*) FROM digest_slots) AS digest_slots, (SELECT COUNT(*) FROM digest_section_summaries) AS digest_section_summaries, (SELECT COUNT(*) FROM reference_items) AS reference_items, (SELECT COUNT(*) FROM citation_workset_items) AS citation_workset_items, (SELECT COUNT(*) FROM citation_items) AS citation_items, (SELECT COUNT(*) FROM citation_timeline) AS citation_timeline, (SELECT COUNT(*) FROM citation_summary) AS citation_summary, (SELECT COUNT(*) FROM citation_unmapped_mentions) AS citation_unmapped_mentions;",
            "notes": "Final rendering reads structured digest slots, reference items, citation workset, semantic items, timeline, summary, and unmapped mentions from the database.",
        },
        {
            "purpose": "inspect registered public artifacts",
            "sql": "SELECT artifact_key, path, is_required FROM artifact_registry ORDER BY artifact_key;",
            "notes": "Use after rendering to confirm the public contract has been registered.",
        },
    ],
}


def _default_instruction_refs(stage: str) -> list[dict[str, str]]:
    refs = [
        {
            "path": STAGE_DOCS.get(stage, "references/step_06_render_and_validate.md"),
            "section": "Current stage guidance",
        },
        {
            "path": "references/stage_runtime_interface.md",
            "section": "Stage runtime interface",
        },
    ]
    if stage == "stage_4_references":
        refs.append({"path": "references/bibliography_formats.md", "section": "Reference style cues"})
    elif stage not in {"stage_4_references"}:
        refs.append({"path": "references/sql_playbook.md", "section": "SQL patterns"})
    return refs


def _instruction_refs(stage: str, next_action: str) -> list[dict[str, str]]:
    refs = _default_instruction_refs(stage)
    if next_action in {"bootstrap_runtime_db", "normalize_source"}:
        refs[0]["section"] = "Bootstrap and source normalization"
    elif next_action == "persist_outline_and_scopes":
        refs[0]["section"] = "Outline and scope extraction"
    elif next_action == "persist_digest":
        refs[0]["section"] = "Digest generation"
    elif next_action in {"prepare_references_workset", "persist_reference_entry_splits", "persist_references"}:
        refs[0]["section"] = "References extraction"
    elif next_action in {"prepare_citation_workset", "persist_citation_semantics", "persist_citation_timeline", "persist_citation_summary"}:
        refs[0]["section"] = "Citation pipeline"
    elif next_action == "render_and_validate":
        refs[0]["section"] = "Render and validate"
    elif next_action.startswith("repair_"):
        refs = [
            {"path": STAGE_DOCS.get(stage, "references/step_06_render_and_validate.md"), "section": "Repair flow"},
            {"path": "references/failure_recovery.md", "section": "Failure recovery"},
            {"path": "references/sql_playbook.md", "section": "SQL patterns"},
            {"path": "references/stage_runtime_interface.md", "section": "Stage runtime interface"},
        ]
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for ref in refs:
        key = ref["path"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ref)
    return deduped[:3]


def _sql_examples(stage: str, next_action: str) -> list[dict[str, str]]:
    if next_action in ACTION_SQL_EXAMPLES:
        return ACTION_SQL_EXAMPLES[next_action]
    return [
        {
            "purpose": "inspect workflow state",
            "sql": "SELECT current_stage, current_substep, stage_gate, next_action, status_summary FROM workflow_state WHERE id = 1;",
            "notes": "Fallback SQL example when no action-specific mapping exists.",
        }
    ]


def _execution_note(current_stage: str, next_action: str, stage_gate: str) -> str:
    if next_action == "bootstrap_runtime_db":
        return "Initialize or resume the runtime DB first, decide the final output directory in this step, write it to DB, then rerun gate before doing anything else."
    if next_action == "normalize_source":
        return "Run source normalization now. Do not respecify source_path or language; this step must read the bootstrap state from DB."
    if next_action == "persist_outline_and_scopes":
        return "Persist the outline and both scopes in one payload. Keep scope boundaries explicit with section_title, line_start, line_end, and metadata."
    if next_action == "persist_digest":
        return "Persist structured digest_slots and section_summaries only. Do not write near-final Markdown."
    if next_action == "prepare_references_workset":
        return "Prepare the references workset from the stored references_scope first; let the script build entries, batches, and parse candidates."
    if next_action == "persist_reference_entry_splits":
        return "The prepared references still have suspect blocks. Review only those block boundaries with split/keep/merge decisions; do not extract author, title, or year in this step."
    if next_action == "persist_references":
        return "Refine references from prepared candidates only. Reuse selected_pattern and preserve prepared author boundaries."
    if next_action == "prepare_citation_workset":
        return "Prepare the citation workset from stored citation_scope and reference_items. Do not rebuild scope or reference mapping by hand."
    if next_action == "persist_citation_semantics":
        return "Persist per-ref_index citation semantics now. Summaries must explain how the source paper uses each citation, not just what the cited work is."
    if next_action == "persist_citation_timeline":
        return "Write the early/mid/recent citation timeline now. Use structured buckets and cover every citation item with a stable year exactly once."
    if next_action == "persist_citation_summary":
        return "Write the global citation summary now. Keep it narrative and based on research threads, argument shape, and key references."
    if next_action == "render_and_validate":
        return "You are at the final publish step. Run `python scripts/stage_runtime.py render_and_validate --mode render` next. Render will use the DB-stored output_dir, mirror the same stdout JSON into `./literature-digest.result.json`, and you should directly use that stdout JSON as the final assistant output."
    if next_action == "repair_workflow_state":
        return "Repair workflow_state first. Do not continue the main path until gate returns a non-repair next_action."
    if next_action == "repair_db_state":
        return "A prerequisite row is missing. Repair DB state first, then rerun gate."
    if stage_gate == "blocked":
        return "The current state is blocked. Repair the runtime state before trying to continue."
    return "Follow the current next_action exactly, then rerun gate."


def _core_instruction() -> str:
    return CORE_INSTRUCTION_PATH.read_text(encoding="utf-8").strip()


def _emit(payload: dict[str, Any], exit_code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


def _missing_prerequisites(connection, stage: str, next_action: str) -> list[str]:  # type: ignore[no-untyped-def]
    inputs = fetch_runtime_inputs(connection)
    missing: list[str] = []

    def count(table: str) -> int:
        row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return 0 if row is None else int(row["count"])

    if stage == "stage_1_normalize_source":
        if not inputs.get("source_path"):
            missing.append("runtime_inputs.source_path")
    elif stage == "stage_2_outline_and_scopes":
        row = connection.execute("SELECT 1 FROM source_documents WHERE doc_key = 'normalized_source' LIMIT 1").fetchone()
        if row is None:
            missing.append("source_documents.normalized_source")
    elif stage == "stage_3_digest":
        if count("outline_nodes") == 0:
            missing.append("outline_nodes")
    elif stage == "stage_4_references":
        row = connection.execute("SELECT 1 FROM source_documents WHERE doc_key = 'normalized_source' LIMIT 1").fetchone()
        if row is None:
            missing.append("source_documents.normalized_source")
        if connection.execute("SELECT 1 FROM section_scopes WHERE scope_key = 'references_scope' LIMIT 1").fetchone() is None:
            missing.append("section_scopes.references_scope")
        if next_action in {"persist_reference_entry_splits", "persist_references"}:
            if count("reference_entries") == 0:
                missing.append("reference_entries")
            if count("reference_parse_candidates") == 0:
                missing.append("reference_parse_candidates")
    elif stage == "stage_5_citation":
        row = connection.execute("SELECT 1 FROM source_documents WHERE doc_key = 'normalized_source' LIMIT 1").fetchone()
        if row is None:
            missing.append("source_documents.normalized_source")
        if connection.execute("SELECT 1 FROM section_scopes WHERE scope_key = 'citation_scope' LIMIT 1").fetchone() is None:
            missing.append("section_scopes.citation_scope")
        if count("reference_items") == 0:
            missing.append("reference_items")
        if next_action == "persist_citation_semantics" and count("citation_workset_items") == 0:
            missing.append("citation_workset_items")
        if next_action == "persist_citation_timeline" and count("citation_items") == 0:
            missing.append("citation_items")
        if next_action == "persist_citation_summary":
            if count("citation_items") == 0:
                missing.append("citation_items")
            if count("citation_timeline") == 0:
                missing.append("citation_timeline")
    elif stage == "stage_6_render_and_validate":
        if count("digest_slots") == 0:
            missing.append("digest_slots")
        if count("reference_items") == 0:
            missing.append("reference_items")
        if connection.execute("SELECT 1 FROM section_scopes WHERE scope_key = 'citation_scope' LIMIT 1").fetchone() is None:
            missing.append("section_scopes.citation_scope")
        if count("citation_workset_items") == 0:
            missing.append("citation_workset_items")
        if count("citation_items") == 0:
            missing.append("citation_items")
        if count("citation_timeline") == 0:
            missing.append("citation_timeline")
        if count("citation_summary") == 0:
            missing.append("citation_summary")
    elif stage == "stage_7_completed":
        artifacts = fetch_artifact_registry(connection)
        for key in ["digest_path", "references_path", "citation_analysis_path"]:
            if key not in artifacts:
                missing.append(f"artifact_registry.{key}")
    return missing


def _payload(
    *,
    current_stage: str,
    current_substep: str,
    stage_gate: str,
    next_action: str,
    status_summary: str,
    rules: dict[str, Any],
    db_path: Path,
    active_batch_kind: Any = None,
    active_batch_index: Any = None,
    last_error_code: Any = None,
) -> dict[str, Any]:
    return {
        "current_stage": current_stage,
        "current_substep": current_substep,
        "stage_gate": stage_gate,
        "next_action": next_action,
        "status_summary": status_summary,
        "required_reads": list(rules["required_reads"]),
        "required_writes": list(rules["required_writes"]),
        "instruction_refs": _instruction_refs(current_stage, next_action),
        "core_instruction": _core_instruction(),
        "execution_note": _execution_note(current_stage, next_action, stage_gate),
        "sql_examples": _sql_examples(current_stage, next_action),
        "resume_packet": {
            "db_path": str(db_path),
            "active_batch_kind": active_batch_kind,
            "active_batch_index": active_batch_index,
            "last_error_code": last_error_code,
            "why_paused": status_summary,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate runtime script for literature-digest DB-first execution.")
    parser.add_argument("--db-path", default="", help="Optional explicit runtime DB path.")
    args = parser.parse_args()

    db_path = Path(args.db_path) if args.db_path else default_db_path()
    if not db_path.exists():
        return _emit(
            _payload(
                current_stage="stage_0_bootstrap",
                current_substep="bootstrap_runtime_db",
                stage_gate="blocked",
                next_action="bootstrap_runtime_db",
                status_summary="runtime database missing",
                rules=STAGE_RULES["stage_0_bootstrap"],
                db_path=db_path,
            )
        )

    with connect_db(db_path) as connection:
        state = fetch_workflow_state(connection)
        if state is None:
            return _emit(
                _payload(
                    current_stage="stage_0_bootstrap",
                    current_substep="repair_workflow_state",
                    stage_gate="blocked",
                    next_action="repair_workflow_state",
                    status_summary="workflow_state missing",
                    rules=STAGE_RULES["stage_0_bootstrap"],
                    db_path=db_path,
                ),
                exit_code=2,
            )

        current_stage = str(state["current_stage"])
        if current_stage not in ALLOWED_STAGES:
            return _emit(
                _payload(
                    current_stage=current_stage,
                    current_substep=str(state["current_substep"]),
                    stage_gate="blocked",
                    next_action="repair_workflow_state",
                    status_summary=f"invalid stage: {current_stage}",
                    rules=STAGE_RULES["stage_0_bootstrap"],
                    db_path=db_path,
                    active_batch_kind=state["active_batch_kind"],
                    active_batch_index=state["active_batch_index"],
                    last_error_code=state["last_error_code"],
                ),
                exit_code=2,
            )

        rules = STAGE_RULES[current_stage]
        stage_gate = str(state["stage_gate"])
        next_action = str(state["next_action"])
        status_summary = str(state["status_summary"])
        missing = _missing_prerequisites(connection, current_stage, next_action)

        if missing:
            stage_gate = "blocked"
            next_action = "repair_db_state"
            status_summary = f"missing prerequisites: {', '.join(missing)}"

        return _emit(
            _payload(
                current_stage=current_stage,
                current_substep=str(state["current_substep"]),
                stage_gate=stage_gate,
                next_action=next_action,
                status_summary=status_summary,
                rules=rules,
                db_path=db_path,
                active_batch_kind=state["active_batch_kind"],
                active_batch_index=state["active_batch_index"],
                last_error_code=state["last_error_code"],
            ),
            exit_code=0 if stage_gate == "ready" else 2,
        )


if __name__ == "__main__":
    raise SystemExit(main())

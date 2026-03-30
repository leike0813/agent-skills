#!/usr/bin/env python3
"""Shared runtime helpers for the SQLite SSOT gate-driven workflow."""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from runtime_rendering import render_markdown_views, render_section_review

DB_FILENAME = "paper-condenser.db"

WORKFLOW_STAGES = {
    "bootstrap": "stage_0_bootstrap",
    "intake": "stage_1_intake_and_inventory",
    "analysis": "stage_2_manuscript_analysis",
    "targets": "stage_3_target_settings",
    "style": "stage_4_style_profile",
    "plan": "stage_5_condensation_plan",
    "drafting": "stage_6_final_drafting",
    "completed": "stage_7_completed",
}

ACTIONS = {
    "bootstrap": "bootstrap_runtime_db",
    "intake": "persist_intake_and_inventory",
    "analysis": "persist_manuscript_analysis",
    "raw_scope_segments": "persist_raw_scope_segments",
    "semantic_source_units": "persist_semantic_source_units",
    "target_settings_basics": "persist_target_settings_basics",
    "content_selection_board": "persist_content_selection_board",
    "confirm_content_selection": "confirm_content_selection",
    "finalize_target_settings": "finalize_target_settings",
    "style": "persist_style_profile",
    "plan": "persist_condensation_plan",
    "section_plan": "persist_section_rewrite_plan",
    "prepare_draft": "prepare_section_drafting",
    "draft_section": "persist_section_draft",
    "approve_section": "approve_section_draft",
    "output_target": "persist_output_target",
    "render_bundle": "render_final_output_bundle",
    "completed": "completed",
}
DEPRECATED_ACTIONS = {
    "persist_scope_segments": ACTIONS["raw_scope_segments"],
    "persist_target_settings": ACTIONS["target_settings_basics"],
}

RENDERED_VIEWS = {
    "resume": "01-agent-resume.md",
    "manuscript_profile": "02-manuscript-profile.md",
    "target_settings": "03-target-settings.md",
    "style_profile": "04-style-profile.md",
    "condensation_plan": "05-condensation-plan.md",
    "supporting_elements": "06-supporting-elements-inventory.md",
    "scope_segments": "07-scope-segments.md",
    "semantic_source_units": "08-semantic-source-units.md",
    "section_rewrite_plan": "09-section-rewrite-plan.md",
    "section_drafting_board": "10-section-drafting-board.md",
    "content_selection_board": "11-content-selection-board.md",
}

LATEX_TEMPLATE_ROOT = Path(__file__).resolve().parent.parent / "assets" / "latex-templates"
PREVIEW_CHAR_LIMIT = 500
CAPTION_PREVIEW_LIMIT = 160

FIGURE_PATTERN = re.compile(r"\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}", re.DOTALL)
TABLE_PATTERN = re.compile(r"\\begin\{table\*?\}(.*?)\\end\{table\*?\}", re.DOTALL)
CAPTION_PATTERN = re.compile(r"\\caption(?:\[[^\]]*\])?\{([^}]*)\}", re.DOTALL)
LABEL_PATTERN = re.compile(r"\\label\{([^}]*)\}")
INCLUDEGRAPHICS_PATTERN = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]*)\}")
CITE_PATTERN = re.compile(
    r"\\[A-Za-z]*cite[a-zA-Z*]*\s*(?:\[[^\]]*\]\s*){0,2}\{([^}]*)\}"
)
BIBLIOGRAPHY_PATTERN = re.compile(r"\\bibliography\{([^}]*)\}")
ADDBIBRESOURCE_PATTERN = re.compile(r"\\addbibresource(?:\[[^\]]*\])?\{([^}]*)\}")
BIBITEM_PATTERN = re.compile(r"\\bibitem(?:\[[^\]]*\])?\{([^}]*)\}")

REQUIRED_TARGET_BASICS_KEYS = (
    "target_language",
    "target_form",
    "target_journal_type",
    "latex_template_id",
    "target_body_length",
    "figure_table_preference",
    "reference_handling_preference",
)
REQUIRED_CONTENT_SELECTION_BOARD_KEYS = ("items",)
REQUIRED_CONTENT_SELECTION_CONFIRM_KEYS = ("items",)
REQUIRED_TARGET_FINALIZE_KEYS = ("user_confirmed",)

REQUIRED_ANALYSIS_KEYS = (
    "main_scope",
    "main_scope_locator",
    "aux_scopes",
    "topic",
    "main_work",
    "novelty",
    "section_outline",
    "removable_candidates",
    "open_questions",
)

REQUIRED_STYLE_KEYS = (
    "source_style",
    "problems_to_fix",
    "target_style_guidance",
    "open_questions",
)

REQUIRED_PLAN_KEYS = (
    "core_message",
    "priority_map",
    "target_outline",
    "length_allocation",
    "omit_merge_strategy",
    "figure_table_plan",
    "reference_plan",
    "approval_status",
)

REQUIRED_SECTION_PLAN_KEYS = ("sections",)
REQUIRED_SECTION_DRAFT_KEYS = ("section_id", "draft_tex", "source_refs")
REQUIRED_SECTION_APPROVAL_KEYS = ("section_id", "approved")
REQUIRED_OUTPUT_TARGET_KEYS = ("user_confirmed",)
REQUIRED_SEMANTIC_UNIT_KEYS = ("units",)


@dataclass
class RuntimeSnapshot:
    artifact_root: Path
    db_path: Path
    workflow_stage: str
    current_substep: str
    active_section_id: str
    next_action: str
    blockers: list[str]
    pending_confirmations: list[dict[str, str]]
    instruction_refs: list[str]
    rendered_views: dict[str, str]
    tables: dict[str, Any]


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def slugify_source_name(source_path: Path) -> str:
    raw = source_path.stem.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw)
    slug = slug.strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        raise ValueError(f"Cannot derive a valid document slug from: {source_path.name}")
    return slug


def detect_source_type(source_path: Path) -> str:
    suffix = source_path.suffix.lower()
    if suffix:
        return f"single_file:{suffix.lstrip('.')}"
    return "single_file:unknown"


def resolve_artifact_root(source_path: Path) -> Path:
    return Path.cwd().resolve() / ".paper-condenser-tmp" / slugify_source_name(source_path)


def resolve_db_path(artifact_root: Path) -> Path:
    return artifact_root / DB_FILENAME


def validate_source_path(source_path: Path) -> Path:
    resolved = source_path.resolve(strict=True)
    if not resolved.is_file():
        raise FileNotFoundError(f"Source path is not a file: {resolved}")
    return resolved


def validate_artifact_root(artifact_root: Path) -> Path:
    resolved = artifact_root.resolve(strict=False)
    if resolved.exists() and not resolved.is_dir():
        raise NotADirectoryError(f"Artifact root is not a directory: {resolved}")
    return resolved


def connect_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS runtime_workspace (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            document_slug TEXT NOT NULL,
            artifact_root TEXT NOT NULL,
            db_path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workflow_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            workflow_stage TEXT NOT NULL,
            current_substep TEXT NOT NULL DEFAULT '',
            active_section_id TEXT NOT NULL DEFAULT '',
            next_action TEXT NOT NULL,
            status TEXT NOT NULL,
            blockers_json TEXT NOT NULL,
            pending_confirmations_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS manuscript_source (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS manuscript_intake (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS supporting_elements_inventory (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS manuscript_analysis (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS target_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS content_selection_items (
            item_id TEXT PRIMARY KEY,
            item_order INTEGER NOT NULL,
            bucket TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            rationale TEXT NOT NULL,
            note TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS content_selection_item_units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT NOT NULL,
            unit_id TEXT NOT NULL,
            member_order INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (item_id) REFERENCES content_selection_items(item_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS style_profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS condensation_plan (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS final_outputs (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS raw_scope_segments (
            segment_id TEXT PRIMARY KEY,
            segment_order INTEGER NOT NULL,
            segment_kind TEXT NOT NULL,
            scope_role TEXT NOT NULL,
            scope_bucket_id TEXT NOT NULL,
            scope_label TEXT NOT NULL,
            heading_context TEXT NOT NULL,
            source_line_start INTEGER NOT NULL,
            source_line_end INTEGER NOT NULL,
            source_text TEXT NOT NULL,
            char_count INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS semantic_source_units (
            unit_id TEXT PRIMARY KEY,
            unit_order INTEGER NOT NULL,
            unit_title TEXT NOT NULL,
            unit_kind TEXT NOT NULL,
            summary TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS semantic_source_unit_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_id TEXT NOT NULL,
            segment_id TEXT NOT NULL,
            member_order INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (unit_id) REFERENCES semantic_source_units(unit_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS semantic_source_unit_elements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_id TEXT NOT NULL,
            element_kind TEXT NOT NULL,
            element_ref TEXT NOT NULL,
            usage_note TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (unit_id) REFERENCES semantic_source_units(unit_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS section_rewrite_plan (
            section_id TEXT PRIMARY KEY,
            section_order INTEGER NOT NULL,
            section_title TEXT NOT NULL,
            planned_count_value INTEGER NOT NULL,
            count_unit TEXT NOT NULL,
            tolerance_percent INTEGER NOT NULL,
            must_cover_json TEXT NOT NULL,
            must_avoid_json TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS section_rewrite_plan_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            usage_note TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (section_id) REFERENCES section_rewrite_plan(section_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS draft_sections (
            section_id TEXT PRIMARY KEY,
            draft_tex TEXT NOT NULL,
            actual_count_value INTEGER NOT NULL,
            count_unit TEXT NOT NULL,
            count_check_status TEXT NOT NULL,
            review_status TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (section_id) REFERENCES section_rewrite_plan(section_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS draft_section_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            usage_note TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (section_id) REFERENCES draft_sections(section_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS draft_section_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            note TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (section_id) REFERENCES section_rewrite_plan(section_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS output_targets (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            output_dir TEXT NOT NULL,
            images_dir TEXT NOT NULL,
            user_confirmed INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pending_confirmations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stage_name TEXT NOT NULL,
            item_key TEXT NOT NULL,
            prompt TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS action_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_name TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    workflow_columns = {
        str(row["name"]) for row in conn.execute("PRAGMA table_info(workflow_state)").fetchall()
    }
    if "current_substep" not in workflow_columns:
        conn.execute(
            "ALTER TABLE workflow_state ADD COLUMN current_substep TEXT NOT NULL DEFAULT ''"
        )
    if "active_section_id" not in workflow_columns:
        conn.execute(
            "ALTER TABLE workflow_state ADD COLUMN active_section_id TEXT NOT NULL DEFAULT ''"
        )
    raw_scope_columns = {
        str(row["name"]) for row in conn.execute("PRAGMA table_info(raw_scope_segments)").fetchall()
    }
    if "scope_role" not in raw_scope_columns:
        conn.execute(
            "ALTER TABLE raw_scope_segments ADD COLUMN scope_role TEXT NOT NULL DEFAULT 'main'"
        )
    if "scope_bucket_id" not in raw_scope_columns:
        conn.execute(
            "ALTER TABLE raw_scope_segments ADD COLUMN scope_bucket_id TEXT NOT NULL DEFAULT 'main'"
        )
    if "scope_label" not in raw_scope_columns:
        conn.execute(
            "ALTER TABLE raw_scope_segments ADD COLUMN scope_label TEXT NOT NULL DEFAULT 'Main Scope'"
        )
    target_settings_payload = load_payload_table(conn, "target_settings")
    migrated = False
    if "simplify_first" not in target_settings_payload:
        target_settings_payload["simplify_first"] = []
        migrated = True
    if "basics_completed" not in target_settings_payload:
        target_settings_payload["basics_completed"] = False
        migrated = True
    if "content_selection_board_ready" not in target_settings_payload:
        target_settings_payload["content_selection_board_ready"] = False
        migrated = True
    if "content_selection_confirmed" not in target_settings_payload:
        target_settings_payload["content_selection_confirmed"] = False
        migrated = True
    if migrated:
        upsert_payload_table(conn, "target_settings", target_settings_payload)
    section_plan_columns = {
        str(row["name"]) for row in conn.execute("PRAGMA table_info(section_rewrite_plan)").fetchall()
    }
    if "simplify_first_json" not in section_plan_columns:
        conn.execute(
            "ALTER TABLE section_rewrite_plan ADD COLUMN simplify_first_json TEXT NOT NULL DEFAULT '[]'"
        )
    conn.commit()


def load_payload_table(conn: sqlite3.Connection, table_name: str) -> dict[str, Any]:
    row = conn.execute(
        f"SELECT payload_json FROM {table_name} WHERE id = 1"
    ).fetchone()
    if row is None:
        return {}
    return json.loads(str(row["payload_json"]))


def upsert_payload_table(
    conn: sqlite3.Connection, table_name: str, payload: dict[str, Any]
) -> None:
    conn.execute(
        f"""
        INSERT INTO {table_name} (id, payload_json, updated_at)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            payload_json = excluded.payload_json,
            updated_at = excluded.updated_at
        """,
        (json.dumps(payload, ensure_ascii=False), now_iso()),
    )


def upsert_runtime_workspace(
    conn: sqlite3.Connection, document_slug: str, artifact_root: Path, db_path: Path
) -> None:
    timestamp = now_iso()
    conn.execute(
        """
        INSERT INTO runtime_workspace (id, document_slug, artifact_root, db_path, created_at, updated_at)
        VALUES (1, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            document_slug = excluded.document_slug,
            artifact_root = excluded.artifact_root,
            db_path = excluded.db_path,
            updated_at = excluded.updated_at
        """,
        (document_slug, str(artifact_root), str(db_path), timestamp, timestamp),
    )


def replace_pending_confirmations(
    conn: sqlite3.Connection, stage_name: str, items: list[dict[str, str]]
) -> None:
    conn.execute("DELETE FROM pending_confirmations WHERE stage_name = ?", (stage_name,))
    for item in items:
        conn.execute(
            """
            INSERT INTO pending_confirmations (stage_name, item_key, prompt, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                stage_name,
                item["item_key"],
                item["prompt"],
                "pending",
                now_iso(),
            ),
        )


def list_pending_confirmations(conn: sqlite3.Connection) -> list[dict[str, str]]:
    rows = conn.execute(
        """
        SELECT stage_name, item_key, prompt, status
        FROM pending_confirmations
        WHERE status = 'pending'
        ORDER BY id
        """
    ).fetchall()
    return [
        {
            "stage_name": str(row["stage_name"]),
            "item_key": str(row["item_key"]),
            "prompt": str(row["prompt"]),
            "status": str(row["status"]),
        }
        for row in rows
    ]


def append_action_log(
    conn: sqlite3.Connection,
    action_name: str,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO action_log (action_name, payload_json, result_json, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            action_name,
            json.dumps(payload, ensure_ascii=False),
            json.dumps(result, ensure_ascii=False),
            now_iso(),
        ),
    )


def replace_raw_scope_segments(
    conn: sqlite3.Connection, items: list[dict[str, Any]]
) -> None:
    conn.execute("DELETE FROM raw_scope_segments")
    for item in items:
        conn.execute(
            """
            INSERT INTO raw_scope_segments (
                segment_id, segment_order, segment_kind, scope_role,
                scope_bucket_id, scope_label, heading_context,
                source_line_start, source_line_end, source_text, char_count, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["segment_id"],
                item["segment_order"],
                item["segment_kind"],
                item["scope_role"],
                item["scope_bucket_id"],
                item["scope_label"],
                item["heading_context"],
                item["source_line_start"],
                item["source_line_end"],
                item["source_text"],
                item["char_count"],
                now_iso(),
            ),
        )


def load_raw_scope_segments(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT segment_id, segment_order, segment_kind, scope_role,
               scope_bucket_id, scope_label, heading_context,
               source_line_start, source_line_end, source_text, char_count
        FROM raw_scope_segments
        ORDER BY segment_order
        """
    ).fetchall()
    return [
        {
            "segment_id": str(row["segment_id"]),
            "segment_order": int(row["segment_order"]),
            "segment_kind": str(row["segment_kind"]),
            "scope_role": str(row["scope_role"]),
            "scope_bucket_id": str(row["scope_bucket_id"]),
            "scope_label": str(row["scope_label"]),
            "heading_context": str(row["heading_context"]),
            "source_line_start": int(row["source_line_start"]),
            "source_line_end": int(row["source_line_end"]),
            "source_text": str(row["source_text"]),
            "char_count": int(row["char_count"]),
        }
        for row in rows
    ]


def replace_semantic_source_units(
    conn: sqlite3.Connection, units: list[dict[str, Any]]
) -> None:
    conn.execute("DELETE FROM semantic_source_unit_members")
    conn.execute("DELETE FROM semantic_source_unit_elements")
    conn.execute("DELETE FROM semantic_source_units")
    for unit in units:
        timestamp = now_iso()
        conn.execute(
            """
            INSERT INTO semantic_source_units (
                unit_id, unit_order, unit_title, unit_kind, summary, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unit["unit_id"],
                unit["unit_order"],
                unit["unit_title"],
                unit["unit_kind"],
                unit["summary"],
                unit["status"],
                timestamp,
                timestamp,
            ),
        )
        for member_order, segment_id in enumerate(unit["member_segment_ids"], start=1):
            conn.execute(
                """
                INSERT INTO semantic_source_unit_members (
                    unit_id, segment_id, member_order, created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (unit["unit_id"], segment_id, member_order, now_iso()),
            )
        for element in unit["elements"]:
            conn.execute(
                """
                INSERT INTO semantic_source_unit_elements (
                    unit_id, element_kind, element_ref, usage_note, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    unit["unit_id"],
                    element["element_kind"],
                    element["element_ref"],
                    element["usage_note"],
                    now_iso(),
                ),
            )


def load_semantic_source_units(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT unit_id, unit_order, unit_title, unit_kind, summary, status
        FROM semantic_source_units
        ORDER BY unit_order
        """
    ).fetchall()
    units: list[dict[str, Any]] = []
    for row in rows:
        unit_id = str(row["unit_id"])
        members = conn.execute(
            """
            SELECT segment_id
            FROM semantic_source_unit_members
            WHERE unit_id = ?
            ORDER BY member_order
            """,
            (unit_id,),
        ).fetchall()
        elements = conn.execute(
            """
            SELECT element_kind, element_ref, usage_note
            FROM semantic_source_unit_elements
            WHERE unit_id = ?
            ORDER BY id
            """,
            (unit_id,),
        ).fetchall()
        units.append(
            {
                "unit_id": unit_id,
                "unit_order": int(row["unit_order"]),
                "unit_title": str(row["unit_title"]),
                "unit_kind": str(row["unit_kind"]),
                "summary": str(row["summary"]),
                "status": str(row["status"]),
                "member_segment_ids": [str(item["segment_id"]) for item in members],
                "elements": [
                    {
                        "element_kind": str(item["element_kind"]),
                        "element_ref": str(item["element_ref"]),
                        "usage_note": str(item["usage_note"]),
                    }
                    for item in elements
                ],
            }
        )
    return units


def replace_content_selection_items(
    conn: sqlite3.Connection, items: list[dict[str, Any]]
) -> None:
    conn.execute("DELETE FROM content_selection_item_units")
    conn.execute("DELETE FROM content_selection_items")
    for item in items:
        timestamp = now_iso()
        conn.execute(
            """
            INSERT INTO content_selection_items (
                item_id, item_order, bucket, title, summary, rationale, note,
                status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["item_id"],
                item["item_order"],
                item["bucket"],
                item["title"],
                item["summary"],
                item["rationale"],
                item["note"],
                item["status"],
                timestamp,
                timestamp,
            ),
        )
        for member_order, unit_id in enumerate(item["semantic_unit_ids"], start=1):
            conn.execute(
                """
                INSERT INTO content_selection_item_units (
                    item_id, unit_id, member_order, created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (item["item_id"], unit_id, member_order, now_iso()),
            )


def load_content_selection_items(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT item_id, item_order, bucket, title, summary, rationale, note, status
        FROM content_selection_items
        ORDER BY item_order, item_id
        """
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        item_id = str(row["item_id"])
        members = conn.execute(
            """
            SELECT unit_id
            FROM content_selection_item_units
            WHERE item_id = ?
            ORDER BY member_order
            """,
            (item_id,),
        ).fetchall()
        items.append(
            {
                "item_id": item_id,
                "item_order": int(row["item_order"]),
                "bucket": str(row["bucket"]),
                "title": str(row["title"]),
                "summary": str(row["summary"]),
                "rationale": str(row["rationale"]),
                "note": str(row["note"]),
                "status": str(row["status"]),
                "semantic_unit_ids": [str(item["unit_id"]) for item in members],
            }
        )
    return items


def replace_section_rewrite_plan(
    conn: sqlite3.Connection, sections: list[dict[str, Any]]
) -> None:
    conn.execute("DELETE FROM section_rewrite_plan_sources")
    conn.execute("DELETE FROM section_rewrite_plan")
    for item in sections:
        timestamp = now_iso()
        conn.execute(
            """
            INSERT INTO section_rewrite_plan (
                section_id, section_order, section_title, planned_count_value,
                count_unit, tolerance_percent, must_cover_json, simplify_first_json,
                must_avoid_json, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["section_id"],
                item["section_order"],
                item["section_title"],
                item["planned_count_value"],
                item["count_unit"],
                item["tolerance_percent"],
                json.dumps(item["must_cover"], ensure_ascii=False),
                json.dumps(item["simplify_first"], ensure_ascii=False),
                json.dumps(item["must_avoid"], ensure_ascii=False),
                item["status"],
                timestamp,
                timestamp,
            ),
        )
        for source in item["sources"]:
            conn.execute(
                """
                INSERT INTO section_rewrite_plan_sources (
                    section_id, source_kind, source_ref, usage_note, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    item["section_id"],
                    source["source_kind"],
                    source["source_ref"],
                    source["usage_note"],
                    now_iso(),
                ),
            )


def load_section_rewrite_plan(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT section_id, section_order, section_title, planned_count_value,
               count_unit, tolerance_percent, must_cover_json, simplify_first_json,
               must_avoid_json, status
        FROM section_rewrite_plan
        ORDER BY section_order
        """
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        section_id = str(row["section_id"])
        sources = conn.execute(
            """
            SELECT source_kind, source_ref, usage_note
            FROM section_rewrite_plan_sources
            WHERE section_id = ?
            ORDER BY id
            """,
            (section_id,),
        ).fetchall()
        result.append(
            {
                "section_id": section_id,
                "section_order": int(row["section_order"]),
                "section_title": str(row["section_title"]),
                "planned_count_value": int(row["planned_count_value"]),
                "count_unit": str(row["count_unit"]),
                "tolerance_percent": int(row["tolerance_percent"]),
                "must_cover": payload_list(json.loads(str(row["must_cover_json"]))),
                "simplify_first": payload_list(
                    json.loads(str(row["simplify_first_json"]))
                ),
                "must_avoid": payload_list(json.loads(str(row["must_avoid_json"]))),
                "status": str(row["status"]),
                "sources": [
                    {
                        "source_kind": str(source["source_kind"]),
                        "source_ref": str(source["source_ref"]),
                        "usage_note": str(source["usage_note"]),
                    }
                    for source in sources
                ],
            }
        )
    return result


def upsert_draft_section(
    conn: sqlite3.Connection,
    section_id: str,
    draft_tex: str,
    actual_count_value: int,
    count_unit: str,
    count_check_status: str,
    review_status: str,
) -> None:
    conn.execute(
        """
        INSERT INTO draft_sections (
            section_id, draft_tex, actual_count_value, count_unit,
            count_check_status, review_status, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(section_id) DO UPDATE SET
            draft_tex = excluded.draft_tex,
            actual_count_value = excluded.actual_count_value,
            count_unit = excluded.count_unit,
            count_check_status = excluded.count_check_status,
            review_status = excluded.review_status,
            updated_at = excluded.updated_at
        """,
        (
            section_id,
            draft_tex,
            actual_count_value,
            count_unit,
            count_check_status,
            review_status,
            now_iso(),
        ),
    )


def replace_draft_section_sources(
    conn: sqlite3.Connection, section_id: str, items: list[dict[str, str]]
) -> None:
    conn.execute("DELETE FROM draft_section_sources WHERE section_id = ?", (section_id,))
    for item in items:
        conn.execute(
            """
            INSERT INTO draft_section_sources (
                section_id, source_kind, source_ref, usage_note, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                section_id,
                item["source_kind"],
                item["source_ref"],
                item["usage_note"],
                now_iso(),
            ),
        )


def append_draft_section_event(
    conn: sqlite3.Connection, section_id: str, event_type: str, note: str
) -> None:
    conn.execute(
        """
        INSERT INTO draft_section_events (section_id, event_type, note, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (section_id, event_type, note, now_iso()),
    )


def load_draft_sections(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT section_id, draft_tex, actual_count_value, count_unit,
               count_check_status, review_status
        FROM draft_sections
        """
    ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        section_id = str(row["section_id"])
        sources = conn.execute(
            """
            SELECT source_kind, source_ref, usage_note
            FROM draft_section_sources
            WHERE section_id = ?
            ORDER BY id
            """,
            (section_id,),
        ).fetchall()
        events = conn.execute(
            """
            SELECT event_type, note, created_at
            FROM draft_section_events
            WHERE section_id = ?
            ORDER BY id
            """,
            (section_id,),
        ).fetchall()
        result[section_id] = {
            "section_id": section_id,
            "draft_tex": str(row["draft_tex"]),
            "actual_count_value": int(row["actual_count_value"]),
            "count_unit": str(row["count_unit"]),
            "count_check_status": str(row["count_check_status"]),
            "review_status": str(row["review_status"]),
            "sources": [
                {
                    "source_kind": str(source["source_kind"]),
                    "source_ref": str(source["source_ref"]),
                    "usage_note": str(source["usage_note"]),
                }
                for source in sources
            ],
            "events": [
                {
                    "event_type": str(event["event_type"]),
                    "note": str(event["note"]),
                    "created_at": str(event["created_at"]),
                }
                for event in events
            ],
        }
    return result


def upsert_output_target(
    conn: sqlite3.Connection, output_dir: Path, images_dir: Path, user_confirmed: bool
) -> None:
    conn.execute(
        """
        INSERT INTO output_targets (id, output_dir, images_dir, user_confirmed, updated_at)
        VALUES (1, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            output_dir = excluded.output_dir,
            images_dir = excluded.images_dir,
            user_confirmed = excluded.user_confirmed,
            updated_at = excluded.updated_at
        """,
        (str(output_dir), str(images_dir), 1 if user_confirmed else 0, now_iso()),
    )


def load_output_target(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        "SELECT output_dir, images_dir, user_confirmed FROM output_targets WHERE id = 1"
    ).fetchone()
    if row is None:
        return {}
    return {
        "output_dir": str(row["output_dir"]),
        "images_dir": str(row["images_dir"]),
        "user_confirmed": bool(row["user_confirmed"]),
    }


def stage_instruction_refs(workflow_stage: str) -> list[str]:
    mapping = {
        WORKFLOW_STAGES["bootstrap"]: [
            "references/stage0-playbook.md",
            "references/runtime-database-contract.md",
            "references/gate-and-stage-runtime.md",
        ],
        WORKFLOW_STAGES["intake"]: [
            "references/gate-and-stage-runtime.md",
            "references/stage1-playbook.md",
            "references/supporting-elements-playbook.md",
        ],
        WORKFLOW_STAGES["analysis"]: [
            "references/stage2-playbook.md",
        ],
        WORKFLOW_STAGES["targets"]: [
            "references/stage3-playbook.md",
        ],
        WORKFLOW_STAGES["style"]: [
            "references/stage4-playbook.md",
        ],
        WORKFLOW_STAGES["plan"]: [
            "references/stage5-playbook.md",
            "references/supporting-elements-playbook.md",
        ],
        WORKFLOW_STAGES["drafting"]: [
            "references/stage6-playbook.md",
            "references/rewrite-report-playbook.md",
            "references/supporting-elements-playbook.md",
        ],
        WORKFLOW_STAGES["completed"]: [
            "references/rewrite-report-playbook.md",
        ],
    }
    return mapping.get(workflow_stage, [])


def line_number(text: str, char_index: int) -> int:
    return text.count("\n", 0, char_index) + 1


def normalize_preview(value: str, limit: int) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + "..."


def extract_caption(block: str) -> str:
    match = CAPTION_PATTERN.search(block)
    if not match:
        return ""
    return normalize_preview(match.group(1), CAPTION_PREVIEW_LIMIT)


def extract_label(block: str) -> str:
    match = LABEL_PATTERN.search(block)
    if not match:
        return ""
    return match.group(1).strip()


def extract_graphics_paths(block: str) -> list[str]:
    return [match.group(1).strip() for match in INCLUDEGRAPHICS_PATTERN.finditer(block)]


def extract_float_inventory(
    text: str, pattern: re.Pattern[str], kind: str
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, match in enumerate(pattern.finditer(text), start=1):
        block = match.group(0)
        items.append(
            {
                "index": index,
                "kind": kind,
                "label": extract_label(block),
                "caption_preview": extract_caption(block),
                "asset_paths": extract_graphics_paths(block),
                "source_line_start": line_number(text, match.start()),
                "source_line_end": line_number(text, match.end()),
            }
        )
    return items


def extract_citations(text: str) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for index, match in enumerate(CITE_PATTERN.finditer(text), start=1):
        raw_keys = match.group(1)
        keys = [key.strip() for key in raw_keys.split(",") if key.strip()]
        citations.append(
            {
                "index": index,
                "command": match.group(0).split("{", 1)[0].strip(),
                "keys": keys,
                "source_line": line_number(text, match.start()),
            }
        )
    return citations


def extract_bibliography(text: str) -> dict[str, Any]:
    resources: list[str] = []
    for pattern in (BIBLIOGRAPHY_PATTERN, ADDBIBRESOURCE_PATTERN):
        for match in pattern.finditer(text):
            resources.extend(
                resource.strip()
                for resource in match.group(1).split(",")
                if resource.strip()
            )

    bibitems = [match.group(1).strip() for match in BIBITEM_PATTERN.finditer(text)]
    mode = "none"
    if resources:
        mode = "bibtex"
    elif "\\begin{thebibliography}" in text:
        mode = "thebibliography"
    return {
        "mode": mode,
        "resources": resources,
        "entries": bibitems,
    }


def build_supporting_elements_inventory(text: str) -> dict[str, Any]:
    return {
        "status": "complete",
        "figures": extract_float_inventory(text, FIGURE_PATTERN, "figure"),
        "tables": extract_float_inventory(text, TABLE_PATTERN, "table"),
        "citations": extract_citations(text),
        "bibliography": extract_bibliography(text),
    }


def build_intake_payload(source_path: Path, source_text: str) -> dict[str, Any]:
    preview = source_text.strip()
    if len(preview) > PREVIEW_CHAR_LIMIT:
        preview = preview[:PREVIEW_CHAR_LIMIT].rstrip() + "..."
    return {
        "content_preview": preview,
        "source_stats": {
            "char_count": len(source_text),
            "line_count": len(source_text.splitlines()),
            "file_size_bytes": source_path.stat().st_size,
        },
        "intake_status": "complete",
    }


def parse_scope_locator(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("scope_locator must be an object")
    mode = str(raw.get("mode", "")).strip()
    if mode == "full_document":
        return {"mode": mode}
    if mode == "line_range":
        line_start = int(raw.get("line_start", 0))
        line_end = int(raw.get("line_end", 0))
        if line_start <= 0 or line_end < line_start:
            raise ValueError("scope_locator line_range is invalid")
        return {"mode": mode, "line_start": line_start, "line_end": line_end}
    raise ValueError("scope_locator.mode must be 'full_document' or 'line_range'")


def normalize_aux_scopes(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("aux_scopes must be a list")
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError("each aux scope must be an object")
        aux_id = str(item.get("aux_id", "")).strip() or f"aux-{index}"
        label = str(item.get("label", "")).strip()
        purpose = str(item.get("purpose", "")).strip()
        locator = parse_scope_locator(item.get("locator"))
        if not label:
            raise ValueError(f"aux scope '{aux_id}' requires label")
        if not purpose:
            raise ValueError(f"aux scope '{aux_id}' requires purpose")
        if aux_id in seen_ids:
            raise ValueError(f"duplicate aux_id: {aux_id}")
        seen_ids.add(aux_id)
        normalized.append(
            {
                "aux_id": aux_id,
                "label": label,
                "purpose": purpose,
                "locator": locator,
            }
        )
    return normalized


HEADING_PATTERN = re.compile(r"\\(section|subsection|subsubsection)\*?\{([^}]*)\}")
DISPLAY_ENV_NAMES = ("equation", "equation*", "align", "align*", "displaymath")


def extract_env_name(line: str) -> str:
    match = re.search(r"\\begin\{([^}]*)\}", line)
    return match.group(1).strip() if match else ""


def build_scope_segments(source_text: str, scope_locator: dict[str, Any]) -> list[dict[str, Any]]:
    all_lines = source_text.splitlines()
    if scope_locator["mode"] == "full_document":
        line_start = 1
        line_end = len(all_lines)
    else:
        line_start = int(scope_locator["line_start"])
        line_end = min(int(scope_locator["line_end"]), len(all_lines))

    scoped_lines = all_lines[line_start - 1 : line_end]
    segments: list[dict[str, Any]] = []
    current_heading = ""
    paragraph_lines: list[str] = []
    paragraph_start: int | None = None
    segment_order = 1
    index = 0

    def flush_paragraph(end_index: int) -> None:
        nonlocal paragraph_lines, paragraph_start, segment_order
        if paragraph_start is None or not paragraph_lines:
            paragraph_lines = []
            paragraph_start = None
            return
        text = "\n".join(paragraph_lines).strip()
        paragraph_lines = []
        start_line = paragraph_start
        paragraph_start = None
        if not text:
            return
        segments.append(
            {
                "segment_id": f"seg-{segment_order:04d}",
                "segment_order": segment_order,
                "segment_kind": "paragraph",
                "heading_context": current_heading,
                "source_line_start": start_line,
                "source_line_end": end_index,
                "source_text": text,
                "char_count": len(text),
            }
        )
        segment_order += 1

    while index < len(scoped_lines):
        line = scoped_lines[index]
        absolute_line = line_start + index
        stripped = line.strip()
        heading_match = HEADING_PATTERN.search(stripped)
        if heading_match:
            flush_paragraph(absolute_line - 1)
            current_heading = heading_match.group(2).strip()
            index += 1
            continue
        if not stripped:
            flush_paragraph(absolute_line - 1)
            index += 1
            continue

        env_name = extract_env_name(stripped)
        if env_name.startswith("figure"):
            flush_paragraph(absolute_line - 1)
            buffer = [line]
            start_line = absolute_line
            index += 1
            while index < len(scoped_lines):
                buffer.append(scoped_lines[index])
                if "\\end{figure" in scoped_lines[index]:
                    break
                index += 1
            end_line = line_start + index
            block_text = "\n".join(buffer).strip()
            segments.append(
                {
                    "segment_id": f"seg-{segment_order:04d}",
                    "segment_order": segment_order,
                    "segment_kind": "figure",
                    "heading_context": current_heading,
                    "source_line_start": start_line,
                    "source_line_end": end_line,
                    "source_text": block_text,
                    "char_count": len(block_text),
                }
            )
            segment_order += 1
            index += 1
            continue
        if env_name.startswith("table"):
            flush_paragraph(absolute_line - 1)
            buffer = [line]
            start_line = absolute_line
            index += 1
            while index < len(scoped_lines):
                buffer.append(scoped_lines[index])
                if "\\end{table" in scoped_lines[index]:
                    break
                index += 1
            end_line = line_start + index
            block_text = "\n".join(buffer).strip()
            segments.append(
                {
                    "segment_id": f"seg-{segment_order:04d}",
                    "segment_order": segment_order,
                    "segment_kind": "table",
                    "heading_context": current_heading,
                    "source_line_start": start_line,
                    "source_line_end": end_line,
                    "source_text": block_text,
                    "char_count": len(block_text),
                }
            )
            segment_order += 1
            index += 1
            continue
        if env_name in DISPLAY_ENV_NAMES:
            flush_paragraph(absolute_line - 1)
            buffer = [line]
            start_line = absolute_line
            index += 1
            while index < len(scoped_lines):
                buffer.append(scoped_lines[index])
                if f"\\end{{{env_name}}}" in scoped_lines[index]:
                    break
                index += 1
            end_line = line_start + index
            block_text = "\n".join(buffer).strip()
            segments.append(
                {
                    "segment_id": f"seg-{segment_order:04d}",
                    "segment_order": segment_order,
                    "segment_kind": "display_block",
                    "heading_context": current_heading,
                    "source_line_start": start_line,
                    "source_line_end": end_line,
                    "source_text": block_text,
                    "char_count": len(block_text),
                }
            )
            segment_order += 1
            index += 1
            continue

        if paragraph_start is None:
            paragraph_start = absolute_line
        paragraph_lines.append(line)
        index += 1

    flush_paragraph(line_end)
    return segments


def build_scoped_raw_segments(
    source_text: str,
    main_scope_locator: dict[str, Any],
    aux_scopes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    scoped_segments: list[dict[str, Any]] = []
    scope_buckets = [
        {
            "scope_role": "main",
            "scope_bucket_id": "main",
            "scope_label": "Main Scope",
            "locator": main_scope_locator,
        }
    ]
    for item in aux_scopes:
        scope_buckets.append(
            {
                "scope_role": "aux",
                "scope_bucket_id": str(item["aux_id"]),
                "scope_label": str(item["label"]),
                "locator": cast(dict[str, Any], item["locator"]),
            }
        )

    for bucket in scope_buckets:
        bucket_segments = build_scope_segments(source_text, cast(dict[str, Any], bucket["locator"]))
        for item in bucket_segments:
            scoped_segments.append(
                {
                    **item,
                    "scope_role": str(bucket["scope_role"]),
                    "scope_bucket_id": str(bucket["scope_bucket_id"]),
                    "scope_label": str(bucket["scope_label"]),
                }
            )

    scoped_segments.sort(
        key=lambda item: (
            int(item["source_line_start"]),
            int(item["source_line_end"]),
            0 if str(item["scope_role"]) == "main" else 1,
            str(item["scope_bucket_id"]),
        )
    )
    for index, item in enumerate(scoped_segments, start=1):
        item["segment_order"] = index
        item["segment_id"] = f"seg-{index:04d}"
    return scoped_segments


def normalize_semantic_source_units(
    payload: dict[str, Any],
    raw_segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ensure_required_keys(payload, REQUIRED_SEMANTIC_UNIT_KEYS, ACTIONS["semantic_source_units"])
    units_raw = payload.get("units")
    if not isinstance(units_raw, list) or not units_raw:
        raise ValueError("persist_semantic_source_units requires a non-empty units list")
    raw_segment_ids = {item["segment_id"] for item in raw_segments}
    normalized: list[dict[str, Any]] = []
    seen_unit_ids: set[str] = set()
    for index, item in enumerate(units_raw, start=1):
        if not isinstance(item, dict):
            raise ValueError("each semantic source unit must be an object")
        unit_id = str(item.get("unit_id", "")).strip()
        unit_title = str(item.get("unit_title", "")).strip()
        unit_kind = str(item.get("unit_kind", "")).strip() or "argument_unit"
        summary = str(item.get("summary", "")).strip()
        if not unit_id or not unit_title or not summary:
            raise ValueError(
                "each semantic source unit requires unit_id, unit_title, and summary"
            )
        if unit_id in seen_unit_ids:
            raise ValueError(f"duplicate semantic source unit id: {unit_id}")
        seen_unit_ids.add(unit_id)
        member_segment_ids = payload_list(item.get("member_segment_ids", []))
        if not member_segment_ids:
            raise ValueError(
                f"semantic source unit '{unit_id}' must include member_segment_ids"
            )
        unknown_members = [
            segment_id for segment_id in member_segment_ids if segment_id not in raw_segment_ids
        ]
        if unknown_members:
            raise ValueError(
                f"semantic source unit '{unit_id}' references unknown raw segments: {', '.join(unknown_members)}"
            )
        normalized.append(
            {
                "unit_id": unit_id,
                "unit_order": int(item.get("unit_order", index)),
                "unit_title": unit_title,
                "unit_kind": unit_kind,
                "summary": summary,
                "status": str(item.get("status", "ready")).strip() or "ready",
                "member_segment_ids": member_segment_ids,
                "elements": normalize_semantic_unit_elements(item.get("elements", [])),
            }
        )
    return normalized


def normalize_content_selection_items(
    payload: dict[str, Any],
    semantic_units: list[dict[str, Any]],
    *,
    require_non_empty: bool,
) -> list[dict[str, Any]]:
    ensure_required_keys(
        payload,
        REQUIRED_CONTENT_SELECTION_BOARD_KEYS,
        ACTIONS["content_selection_board"],
    )
    items_raw = payload.get("items")
    if not isinstance(items_raw, list):
        raise ValueError("content selection items must be a list")
    if require_non_empty and not items_raw:
        raise ValueError("content selection board requires a non-empty items list")

    known_unit_ids = {item["unit_id"] for item in semantic_units}
    normalized: list[dict[str, Any]] = []
    seen_item_ids: set[str] = set()
    for index, item in enumerate(items_raw, start=1):
        if not isinstance(item, dict):
            raise ValueError("each content selection item must be an object")
        item_id = str(item.get("item_id", "")).strip()
        bucket = str(item.get("bucket", "")).strip()
        title = str(item.get("title", "")).strip()
        summary = str(item.get("summary", "")).strip()
        rationale = str(item.get("rationale", "")).strip()
        note = str(item.get("note", "")).strip()
        unit_ids = payload_list(item.get("semantic_unit_ids", []))
        if not item_id or not bucket or not title or not summary or not rationale:
            raise ValueError(
                "content selection items require item_id, bucket, title, summary, and rationale"
            )
        if bucket not in {"must_keep", "simplify_first", "must_avoid"}:
            raise ValueError(
                f"content selection item '{item_id}' has invalid bucket '{bucket}'"
            )
        if item_id in seen_item_ids:
            raise ValueError(f"duplicate content selection item id: {item_id}")
        if not unit_ids:
            raise ValueError(
                f"content selection item '{item_id}' must include semantic_unit_ids"
            )
        unknown_units = [unit_id for unit_id in unit_ids if unit_id not in known_unit_ids]
        if unknown_units:
            raise ValueError(
                f"content selection item '{item_id}' references unknown semantic units: {', '.join(unknown_units)}"
            )
        seen_item_ids.add(item_id)
        normalized.append(
            {
                "item_id": item_id,
                "item_order": int(item.get("item_order", index)),
                "bucket": bucket,
                "title": title,
                "summary": summary,
                "rationale": rationale,
                "note": note,
                "status": str(item.get("status", "suggested")).strip() or "suggested",
                "semantic_unit_ids": unit_ids,
            }
        )
    return normalized


def normalize_source_refs(
    value: Any,
    *,
    allowed_kinds: set[str],
    action_name: str,
) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError(f"{action_name} sources must be a list")
    result: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"each {action_name} source must be an object")
        source_kind = str(item.get("source_kind", "")).strip()
        source_ref = str(item.get("source_ref", "")).strip()
        if not source_kind or not source_ref:
            raise ValueError(
                f"{action_name} source must include source_kind and source_ref"
            )
        if source_kind not in allowed_kinds:
            allowed = ", ".join(sorted(allowed_kinds))
            raise ValueError(
                f"{action_name} source_kind '{source_kind}' is not allowed; expected one of: {allowed}"
            )
        result.append(
            {
                "source_kind": source_kind,
                "source_ref": source_ref,
                "usage_note": str(item.get("usage_note", "")).strip(),
            }
        )
    return result


def normalize_section_plan_sources(value: Any) -> list[dict[str, str]]:
    return normalize_source_refs(
        value,
        allowed_kinds={"semantic_unit", "figure", "table", "citation", "bibliography"},
        action_name="section plan",
    )


def normalize_section_draft_sources(value: Any) -> list[dict[str, str]]:
    return normalize_source_refs(
        value,
        allowed_kinds={"semantic_unit"},
        action_name="section draft",
    )


def normalize_semantic_unit_elements(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    normalized = normalize_source_refs(
        value,
        allowed_kinds={"figure", "table", "citation", "bibliography"},
        action_name="semantic unit element",
    )
    return [
        {
            "element_kind": item["source_kind"],
            "element_ref": item["source_ref"],
            "usage_note": item["usage_note"],
        }
        for item in normalized
    ]


def validate_semantic_unit_refs(
    items: list[dict[str, str]], semantic_units: list[dict[str, Any]], action_name: str
) -> None:
    known_unit_ids = {item["unit_id"] for item in semantic_units}
    unknown_units = [
        item["source_ref"]
        for item in items
        if item["source_kind"] == "semantic_unit" and item["source_ref"] not in known_unit_ids
    ]
    if unknown_units:
        raise ValueError(
            f"{action_name} references unknown semantic units: {', '.join(sorted(set(unknown_units)))}"
        )


def semantic_unit_uses_aux(
    source_ref: str,
    semantic_units: list[dict[str, Any]],
    raw_segments: list[dict[str, Any]],
) -> bool:
    units_by_id = {item["unit_id"]: item for item in semantic_units}
    raw_by_id = {item["segment_id"]: item for item in raw_segments}
    unit = units_by_id.get(source_ref)
    if unit is None:
        return False
    return any(
        str(raw_by_id.get(segment_id, {}).get("scope_role", "")) == "aux"
        for segment_id in unit.get("member_segment_ids", [])
    )


def strip_latex_for_counting(text: str) -> str:
    text = re.sub(r"%.*", "", text)
    text = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{([^}]*)\})?", r" \1 ", text)
    text = re.sub(r"[{}$&_^~]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def count_draft_text(draft_tex: str, count_unit: str) -> int:
    normalized = strip_latex_for_counting(draft_tex)
    if count_unit == "words":
        return len([token for token in normalized.split(" ") if token.strip()])
    return len(normalized)


def select_next_section(plan_sections: list[dict[str, Any]], drafts: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for item in plan_sections:
        draft = drafts.get(item["section_id"])
        if draft is None or draft.get("review_status") != "approved":
            return item
    return None


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def render_template_preamble(template_id: str) -> str:
    template_path = LATEX_TEMPLATE_ROOT / f"{template_id}.tex"
    content = template_path.read_text(encoding="utf-8")
    marker = "\\section{"
    if marker in content:
        return content.split(marker, 1)[0]
    bibliography_marker = "\\begin{thebibliography}"
    if bibliography_marker in content:
        return content.split(bibliography_marker, 1)[0]
    return content


def infer_copied_image_name(asset_path: str, used_names: set[str]) -> str:
    candidate = Path(asset_path).name or "image"
    stem = Path(candidate).stem
    suffix = Path(candidate).suffix
    final_name = candidate
    counter = 2
    while final_name in used_names:
        final_name = f"{stem}-{counter}{suffix}"
        counter += 1
    used_names.add(final_name)
    return final_name


def ensure_required_keys(payload: dict[str, Any], required_keys: tuple[str, ...], action: str) -> None:
    missing = [key for key in required_keys if key not in payload]
    if missing:
        raise ValueError(f"{action} payload is missing required key(s): {', '.join(missing)}")


def payload_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def format_list_block(items: list[str], empty_text: str = "- （空）") -> str:
    if not items:
        return empty_text
    return "\n".join(f"- {item}" for item in items)


def format_confirmation_block(items: list[dict[str, str]]) -> str:
    if not items:
        return "- 无待确认事项"
    return "\n".join(
        f"- [{item['stage_name']}] {item['item_key']}: {item['prompt']}"
        for item in items
    )


def build_supporting_elements_summary(payload: dict[str, Any]) -> dict[str, Any]:
    figures = payload.get("figures", [])
    tables = payload.get("tables", [])
    citations = payload.get("citations", [])
    bibliography = payload.get("bibliography", {})
    bib_mode = bibliography.get("mode", "unknown") if isinstance(bibliography, dict) else "unknown"
    return {
        "figures_count": len(figures) if isinstance(figures, list) else 0,
        "tables_count": len(tables) if isinstance(tables, list) else 0,
        "citations_count": len(citations) if isinstance(citations, list) else 0,
        "bibliography_mode": bib_mode,
    }


def expand_semantic_source_refs(
    sources: list[dict[str, str]],
    semantic_units_by_id: dict[str, dict[str, Any]],
    raw_segments_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for source in sources:
        item: dict[str, Any] = {
            "source_kind": source["source_kind"],
            "source_ref": source["source_ref"],
            "usage_note": source["usage_note"],
        }
        if source["source_kind"] == "semantic_unit":
            unit = semantic_units_by_id.get(source["source_ref"])
            if unit is not None:
                item["semantic_unit"] = {
                    "unit_title": unit["unit_title"],
                    "unit_kind": unit["unit_kind"],
                    "summary": unit["summary"],
                    "member_segment_ids": unit["member_segment_ids"],
                    "member_segments": [
                        {
                            "segment_id": segment_id,
                            "segment_kind": raw_segments_by_id.get(segment_id, {}).get(
                                "segment_kind", "unknown"
                            ),
                            "scope_role": raw_segments_by_id.get(segment_id, {}).get(
                                "scope_role", "unknown"
                            ),
                            "scope_bucket_id": raw_segments_by_id.get(segment_id, {}).get(
                                "scope_bucket_id", "unknown"
                            ),
                            "scope_label": raw_segments_by_id.get(segment_id, {}).get(
                                "scope_label", ""
                            ),
                            "source_text_preview": normalize_preview(
                                str(
                                    raw_segments_by_id.get(segment_id, {}).get(
                                        "source_text", ""
                                    )
                                ),
                                140,
                            ),
                        }
                        for segment_id in unit["member_segment_ids"]
                    ],
                }
        expanded.append(item)
    return expanded


def expand_content_selection_items(
    items: list[dict[str, Any]],
    semantic_units_by_id: dict[str, dict[str, Any]],
    raw_segments_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for item in items:
        semantic_units: list[dict[str, Any]] = []
        for unit_id in item.get("semantic_unit_ids", []):
            unit = semantic_units_by_id.get(unit_id)
            if unit is None:
                semantic_units.append({"unit_id": unit_id, "missing": True})
                continue
            semantic_units.append(
                {
                    "unit_id": unit_id,
                    "unit_title": unit["unit_title"],
                    "unit_kind": unit["unit_kind"],
                    "summary": unit["summary"],
                    "member_segments": [
                        {
                            **raw_segments_by_id.get(segment_id, {"segment_id": segment_id}),
                            "source_text_preview": normalize_preview(
                                str(
                                    raw_segments_by_id.get(segment_id, {}).get(
                                        "source_text", ""
                                    )
                                ),
                                140,
                            ),
                        }
                        for segment_id in unit["member_segment_ids"]
                    ],
                }
            )
        expanded.append({**item, "semantic_units": semantic_units})
    return expanded


def build_render_view_models(snapshot: RuntimeSnapshot) -> dict[str, dict[str, Any]]:
    source = snapshot.tables["manuscript_source"]
    intake = snapshot.tables["manuscript_intake"]
    analysis = snapshot.tables["manuscript_analysis"]
    inventory = snapshot.tables["supporting_elements_inventory"]
    settings = snapshot.tables["target_settings"]
    content_selection_items = snapshot.tables["content_selection_items"]
    style = snapshot.tables["style_profile"]
    plan = snapshot.tables["condensation_plan"]
    raw_scope_segments = snapshot.tables["raw_scope_segments"]
    semantic_source_units = snapshot.tables["semantic_source_units"]
    section_rewrite_plan = snapshot.tables["section_rewrite_plan"]
    draft_sections = snapshot.tables["draft_sections"]
    output_target = snapshot.tables["output_target"]
    raw_segments_by_id = {
        item["segment_id"]: item for item in raw_scope_segments if isinstance(item, dict)
    }
    semantic_units_by_id = {
        item["unit_id"]: item for item in semantic_source_units if isinstance(item, dict)
    }

    source_stats = intake.get("source_stats", {})
    if not isinstance(source_stats, dict):
        source_stats = {}

    body_length = settings.get("target_body_length", {})
    if not isinstance(body_length, dict):
        body_length = {}
    body_length_display = (
        f"{body_length.get('value', 0)} {body_length.get('unit', '')}".rstrip().strip()
    )

    bibliography = inventory.get("bibliography", {})
    if not isinstance(bibliography, dict):
        bibliography = {}

    return {
        "resume": {
            "runtime": {
                "artifact_root": str(snapshot.artifact_root),
                "db_path": str(snapshot.db_path),
                "workflow_stage": snapshot.workflow_stage,
                "next_action": snapshot.next_action,
            },
            "source": {
                "source_path": str(source.get("source_path", "")),
                "source_type": str(source.get("source_type", "")),
            },
            "blockers": snapshot.blockers,
            "pending_confirmations": snapshot.pending_confirmations,
            "instruction_refs": snapshot.instruction_refs,
            "rendered_views": [
                {"name": name, "path": path}
                for name, path in snapshot.rendered_views.items()
            ],
        },
        "manuscript_profile": {
            "source": {
                "source_path": str(source.get("source_path", "")),
                "source_type": str(source.get("source_type", "")),
            },
            "intake": {
                "intake_status": str(intake.get("intake_status", "pending")),
                "content_preview": str(intake.get("content_preview", "")),
                "source_stats": {
                    "char_count": source_stats.get("char_count", 0),
                    "line_count": source_stats.get("line_count", 0),
                    "file_size_bytes": source_stats.get("file_size_bytes", 0),
                },
            },
            "supporting_elements_summary": build_supporting_elements_summary(inventory),
            "analysis": {
                "status": str(analysis.get("status", "draft")),
                "main_scope": str(analysis.get("main_scope", "")),
                "main_scope_locator": analysis.get(
                    "main_scope_locator", {"mode": "unknown"}
                ),
                "aux_scopes": analysis.get("aux_scopes", [])
                if isinstance(analysis.get("aux_scopes", []), list)
                else [],
                "topic": str(analysis.get("topic", "")),
                "main_work": payload_list(analysis.get("main_work", [])),
                "novelty": payload_list(analysis.get("novelty", [])),
                "section_outline": payload_list(analysis.get("section_outline", [])),
                "removable_candidates": payload_list(
                    analysis.get("removable_candidates", [])
                ),
                "open_questions": payload_list(analysis.get("open_questions", [])),
            },
        },
        "target_settings": {
            "settings": {
                "user_confirmed": bool(settings.get("user_confirmed", False)),
                "basics_completed": bool(settings.get("basics_completed", False)),
                "content_selection_board_ready": bool(
                    settings.get("content_selection_board_ready", False)
                ),
                "content_selection_confirmed": bool(
                    settings.get("content_selection_confirmed", False)
                ),
                "target_language": str(settings.get("target_language", "")),
                "target_form": str(settings.get("target_form", "")),
                "target_journal_type": str(settings.get("target_journal_type", "")),
                "latex_template_id": str(settings.get("latex_template_id", "")),
                "target_body_length_display": body_length_display,
                "figure_table_preference": str(
                    settings.get("figure_table_preference", "")
                ),
                "reference_handling_preference": str(
                    settings.get("reference_handling_preference", "")
                ),
                "must_keep": payload_list(settings.get("must_keep", [])),
                "simplify_first": payload_list(settings.get("simplify_first", [])),
                "must_avoid": payload_list(settings.get("must_avoid", [])),
            }
        },
        "style_profile": {
            "profile": {
                "status": str(style.get("status", "draft")),
                "source_style": str(style.get("source_style", "")),
                "problems_to_fix": str(style.get("problems_to_fix", "")),
                "target_style_guidance": str(style.get("target_style_guidance", "")),
                "open_questions": payload_list(style.get("open_questions", [])),
            }
        },
        "condensation_plan": {
            "plan": {
                "approval_status": str(plan.get("approval_status", "draft")),
                "core_message": str(plan.get("core_message", "")),
                "priority_map": str(plan.get("priority_map", "")),
                "target_outline": str(plan.get("target_outline", "")),
                "length_allocation": str(plan.get("length_allocation", "")),
                "omit_merge_strategy": str(plan.get("omit_merge_strategy", "")),
                "figure_table_plan": str(plan.get("figure_table_plan", "")),
                "reference_plan": str(plan.get("reference_plan", "")),
            }
        },
        "supporting_elements": {
            "inventory": {
                "status": str(inventory.get("status", "pending")),
                "figures": inventory.get("figures", [])
                if isinstance(inventory.get("figures", []), list)
                else [],
                "tables": inventory.get("tables", [])
                if isinstance(inventory.get("tables", []), list)
                else [],
                "citations": [
                    {
                        **item,
                        "keys": payload_list(item.get("keys", [])),
                    }
                    for item in (
                        inventory.get("citations", [])
                        if isinstance(inventory.get("citations", []), list)
                        else []
                    )
                    if isinstance(item, dict)
                ],
            },
            "summary": build_supporting_elements_summary(inventory),
            "bibliography": {
                "mode": str(bibliography.get("mode", "none")),
                "resources": payload_list(bibliography.get("resources", [])),
                "entries": payload_list(bibliography.get("entries", [])),
            },
        },
        "scope_segments": {
            "main_scope_locator": analysis.get(
                "main_scope_locator", {"mode": "unknown"}
            ),
            "aux_scopes": analysis.get("aux_scopes", [])
            if isinstance(analysis.get("aux_scopes", []), list)
            else [],
            "segments": [
                {
                    **item,
                    "source_text_preview": normalize_preview(item["source_text"], 180),
                }
                for item in raw_scope_segments
            ],
        },
        "semantic_source_units": {
            "units": [
                {
                    **item,
                    "member_segments": [
                        {
                            **raw_segments_by_id.get(segment_id, {"segment_id": segment_id}),
                            "source_text_preview": normalize_preview(
                                str(
                                    raw_segments_by_id.get(segment_id, {}).get(
                                        "source_text", ""
                                    )
                                ),
                                140,
                            ),
                        }
                        for segment_id in item["member_segment_ids"]
                    ],
                }
                for item in semantic_source_units
            ],
        },
        "section_rewrite_plan": {
            "sections": [
                {
                    **item,
                    "sources_expanded": expand_semantic_source_refs(
                        item["sources"], semantic_units_by_id, raw_segments_by_id
                    ),
                }
                for item in section_rewrite_plan
            ],
        },
        "content_selection_board": {
            "runtime": {
                "current_substep": snapshot.current_substep,
                "next_action": snapshot.next_action,
            },
            "items": expand_content_selection_items(
                content_selection_items, semantic_units_by_id, raw_segments_by_id
            ),
        },
        "section_drafting_board": {
            "runtime": {
                "active_section_id": snapshot.active_section_id,
                "current_substep": snapshot.current_substep,
                "next_action": snapshot.next_action,
            },
            "sections": [
                {
                    "section_id": item["section_id"],
                    "section_order": item["section_order"],
                    "section_title": item["section_title"],
                    "planned_count_value": item["planned_count_value"],
                    "count_unit": item["count_unit"],
                    "plan_status": item["status"],
                    "review_status": draft_sections.get(item["section_id"], {}).get(
                        "review_status", "not_started"
                    ),
                    "actual_count_value": draft_sections.get(item["section_id"], {}).get(
                        "actual_count_value", 0
                    ),
                    "count_check_status": draft_sections.get(item["section_id"], {}).get(
                        "count_check_status", "pending"
                    ),
                    "semantic_source_count": len(
                        [
                            source
                            for source in item["sources"]
                            if source["source_kind"] == "semantic_unit"
                        ]
                    ),
                }
                for item in section_rewrite_plan
            ],
            "output_target": output_target,
        },
    }


def render_runtime_files(snapshot: RuntimeSnapshot) -> dict[str, str]:
    rendered_paths = {
        "resume": str(snapshot.artifact_root / RENDERED_VIEWS["resume"]),
        "manuscript_profile": str(snapshot.artifact_root / RENDERED_VIEWS["manuscript_profile"]),
        "target_settings": str(snapshot.artifact_root / RENDERED_VIEWS["target_settings"]),
        "style_profile": str(snapshot.artifact_root / RENDERED_VIEWS["style_profile"]),
        "condensation_plan": str(snapshot.artifact_root / RENDERED_VIEWS["condensation_plan"]),
        "supporting_elements": str(snapshot.artifact_root / RENDERED_VIEWS["supporting_elements"]),
        "scope_segments": str(snapshot.artifact_root / RENDERED_VIEWS["scope_segments"]),
        "semantic_source_units": str(snapshot.artifact_root / RENDERED_VIEWS["semantic_source_units"]),
        "section_rewrite_plan": str(snapshot.artifact_root / RENDERED_VIEWS["section_rewrite_plan"]),
        "section_drafting_board": str(snapshot.artifact_root / RENDERED_VIEWS["section_drafting_board"]),
        "content_selection_board": str(snapshot.artifact_root / RENDERED_VIEWS["content_selection_board"]),
    }
    final_outputs = snapshot.tables["final_outputs"]
    final_draft_tex = str(final_outputs.get("final_draft_tex", ""))
    rewrite_report_md = str(final_outputs.get("rewrite_report_md", ""))
    if final_draft_tex:
        final_draft_path = snapshot.artifact_root / "final-draft.tex"
        rendered_paths["final_draft"] = str(final_draft_path)
    if rewrite_report_md:
        rewrite_report_path = snapshot.artifact_root / "rewrite-report.md"
        rendered_paths["rewrite_report"] = str(rewrite_report_path)

    snapshot.rendered_views = rendered_paths.copy()
    view_models = build_render_view_models(snapshot)
    render_markdown_views(snapshot.artifact_root, view_models)

    draft_sections = snapshot.tables["draft_sections"]
    section_rewrite_plan = {
        item["section_id"]: item for item in snapshot.tables["section_rewrite_plan"]
    }
    raw_segments_by_id = {
        item["segment_id"]: item for item in snapshot.tables["raw_scope_segments"]
    }
    semantic_units_by_id = {
        item["unit_id"]: item for item in snapshot.tables["semantic_source_units"]
    }
    section_review_paths: dict[str, str] = {}
    for section_id, draft in draft_sections.items():
        plan_item = section_rewrite_plan.get(section_id)
        if plan_item is None:
            continue
        output_name = (
            f"section-reviews/{plan_item['section_order']:02d}-{section_id}.md"
        )
        section_review_paths[section_id] = render_section_review(
            snapshot.artifact_root,
            output_name,
            {
                "section": {
                    **plan_item,
                    **draft,
                    "sources_expanded": expand_semantic_source_refs(
                        draft["sources"], semantic_units_by_id, raw_segments_by_id
                    ),
                }
            },
        )
    if section_review_paths:
        rendered_paths["section_reviews"] = str(snapshot.artifact_root / "section-reviews")

    if final_draft_tex:
        final_draft_path.write_text(final_draft_tex, encoding="utf-8")
    if rewrite_report_md:
        rewrite_report_path.write_text(rewrite_report_md, encoding="utf-8")
    return rendered_paths


def build_snapshot(conn: sqlite3.Connection, artifact_root: Path) -> RuntimeSnapshot:
    workspace_row = conn.execute(
        "SELECT document_slug, artifact_root, db_path FROM runtime_workspace WHERE id = 1"
    ).fetchone()
    if workspace_row is None:
        raise ValueError("Runtime workspace is not bootstrapped yet")

    tables = {
        "manuscript_source": load_payload_table(conn, "manuscript_source"),
        "manuscript_intake": load_payload_table(conn, "manuscript_intake"),
        "supporting_elements_inventory": load_payload_table(conn, "supporting_elements_inventory"),
        "manuscript_analysis": load_payload_table(conn, "manuscript_analysis"),
        "target_settings": load_payload_table(conn, "target_settings"),
        "content_selection_items": load_content_selection_items(conn),
        "style_profile": load_payload_table(conn, "style_profile"),
        "condensation_plan": load_payload_table(conn, "condensation_plan"),
        "final_outputs": load_payload_table(conn, "final_outputs"),
        "raw_scope_segments": load_raw_scope_segments(conn),
        "semantic_source_units": load_semantic_source_units(conn),
        "section_rewrite_plan": load_section_rewrite_plan(conn),
        "draft_sections": load_draft_sections(conn),
        "output_target": load_output_target(conn),
    }

    blockers: list[str] = []
    pending_confirmations = list_pending_confirmations(conn)

    intake = cast(dict[str, Any], tables["manuscript_intake"])
    inventory = cast(dict[str, Any], tables["supporting_elements_inventory"])
    analysis = cast(dict[str, Any], tables["manuscript_analysis"])
    settings = cast(dict[str, Any], tables["target_settings"])
    content_selection_items = cast(list[dict[str, Any]], tables["content_selection_items"])
    style = cast(dict[str, Any], tables["style_profile"])
    plan = cast(dict[str, Any], tables["condensation_plan"])
    final_outputs = cast(dict[str, Any], tables["final_outputs"])
    raw_scope_segments = cast(list[dict[str, Any]], tables["raw_scope_segments"])
    semantic_source_units = cast(list[dict[str, Any]], tables["semantic_source_units"])
    section_rewrite_plan = cast(list[dict[str, Any]], tables["section_rewrite_plan"])
    draft_sections = cast(dict[str, dict[str, Any]], tables["draft_sections"])
    output_target = cast(dict[str, Any], tables["output_target"])
    current_substep = ""
    active_section_id = ""

    if intake.get("intake_status") != "complete" or inventory.get("status") != "complete":
        workflow_stage = WORKFLOW_STAGES["intake"]
        next_action = ACTIONS["intake"]
        current_substep = ACTIONS["intake"]
        if intake.get("intake_status") != "complete":
            blockers.append("Stage 1 intake has not completed yet.")
        if inventory.get("status") != "complete":
            blockers.append("Supporting-elements inventory has not completed yet.")
    elif analysis.get("status") != "analysis_complete" or any(
        item["stage_name"] == WORKFLOW_STAGES["analysis"] for item in pending_confirmations
    ):
        workflow_stage = WORKFLOW_STAGES["analysis"]
        next_action = ACTIONS["analysis"]
        current_substep = ACTIONS["analysis"]
        if analysis.get("status") != "analysis_complete":
            blockers.append("Manuscript analysis is incomplete.")
    elif not raw_scope_segments:
        workflow_stage = WORKFLOW_STAGES["analysis"]
        next_action = ACTIONS["raw_scope_segments"]
        current_substep = ACTIONS["raw_scope_segments"]
        blockers.append("Raw scope segments are not persisted yet.")
    elif not semantic_source_units:
        workflow_stage = WORKFLOW_STAGES["analysis"]
        next_action = ACTIONS["semantic_source_units"]
        current_substep = ACTIONS["semantic_source_units"]
        blockers.append("Semantic source units are not persisted yet.")
    elif not settings.get("basics_completed", False):
        workflow_stage = WORKFLOW_STAGES["targets"]
        next_action = ACTIONS["target_settings_basics"]
        current_substep = ACTIONS["target_settings_basics"]
        blockers.append("Target setting basics are not completed yet.")
    elif not settings.get("content_selection_board_ready", False):
        workflow_stage = WORKFLOW_STAGES["targets"]
        next_action = ACTIONS["content_selection_board"]
        current_substep = ACTIONS["content_selection_board"]
        blockers.append("Content-selection board is not generated yet.")
    elif not settings.get("content_selection_confirmed", False):
        workflow_stage = WORKFLOW_STAGES["targets"]
        next_action = ACTIONS["confirm_content_selection"]
        current_substep = ACTIONS["confirm_content_selection"]
        blockers.append("Content-selection lists are not confirmed yet.")
    elif settings.get("user_confirmed") is not True or any(
        item["stage_name"] == WORKFLOW_STAGES["targets"] for item in pending_confirmations
    ):
        workflow_stage = WORKFLOW_STAGES["targets"]
        next_action = ACTIONS["finalize_target_settings"]
        current_substep = ACTIONS["finalize_target_settings"]
        blockers.append("Target settings are not fully confirmed yet.")
    elif style.get("status") != "complete" or any(
        item["stage_name"] == WORKFLOW_STAGES["style"] for item in pending_confirmations
    ):
        workflow_stage = WORKFLOW_STAGES["style"]
        next_action = ACTIONS["style"]
        current_substep = ACTIONS["style"]
        if style.get("status") != "complete":
            blockers.append("Style profile is incomplete.")
    elif plan.get("approval_status") != "approved" or any(
        item["stage_name"] == WORKFLOW_STAGES["plan"] for item in pending_confirmations
    ):
        workflow_stage = WORKFLOW_STAGES["plan"]
        next_action = ACTIONS["plan"]
        current_substep = ACTIONS["plan"]
        if plan.get("approval_status") != "approved":
            blockers.append("Condensation plan is not approved yet.")
    elif not section_rewrite_plan:
        workflow_stage = WORKFLOW_STAGES["plan"]
        next_action = ACTIONS["section_plan"]
        current_substep = ACTIONS["section_plan"]
        blockers.append("Section rewrite plan is not persisted yet.")
    elif final_outputs.get("status") != "complete":
        workflow_stage = WORKFLOW_STAGES["drafting"]
        next_section = select_next_section(section_rewrite_plan, draft_sections)
        if next_section is not None:
            active_section_id = str(next_section["section_id"])
            draft = draft_sections.get(active_section_id)
            if draft is None:
                next_action = ACTIONS["prepare_draft"]
                current_substep = ACTIONS["prepare_draft"]
                blockers.append("No active section draft has been prepared yet.")
            elif draft.get("count_check_status") != "passed":
                next_action = ACTIONS["draft_section"]
                current_substep = ACTIONS["draft_section"]
                blockers.append("Active section draft has not passed count validation yet.")
            elif draft.get("review_status") == "rejected":
                next_action = ACTIONS["draft_section"]
                current_substep = ACTIONS["draft_section"]
                blockers.append("Active section draft was rejected and must be revised.")
            elif draft.get("review_status") != "approved":
                next_action = ACTIONS["approve_section"]
                current_substep = ACTIONS["approve_section"]
                blockers.append("Active section draft is waiting for user approval.")
            else:
                next_action = ACTIONS["prepare_draft"]
                current_substep = ACTIONS["prepare_draft"]
        elif output_target.get("user_confirmed") is not True:
            next_action = ACTIONS["output_target"]
            current_substep = ACTIONS["output_target"]
            blockers.append("Final output target is not confirmed yet.")
        else:
            next_action = ACTIONS["render_bundle"]
            current_substep = ACTIONS["render_bundle"]
            blockers.append("Final output bundle is not rendered yet.")
    else:
        workflow_stage = WORKFLOW_STAGES["completed"]
        next_action = ACTIONS["completed"]
        current_substep = ACTIONS["completed"]

    snapshot = RuntimeSnapshot(
        artifact_root=artifact_root,
        db_path=Path(str(workspace_row["db_path"])),
        workflow_stage=workflow_stage,
        current_substep=current_substep,
        active_section_id=active_section_id,
        next_action=next_action,
        blockers=blockers,
        pending_confirmations=pending_confirmations,
        instruction_refs=stage_instruction_refs(workflow_stage),
        rendered_views={},
        tables=tables,
    )
    snapshot.rendered_views = render_runtime_files(snapshot)
    conn.execute(
        """
        INSERT INTO workflow_state (id, workflow_stage, current_substep, active_section_id, next_action, status, blockers_json, pending_confirmations_json, updated_at)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            workflow_stage = excluded.workflow_stage,
            current_substep = excluded.current_substep,
            active_section_id = excluded.active_section_id,
            next_action = excluded.next_action,
            status = excluded.status,
            blockers_json = excluded.blockers_json,
            pending_confirmations_json = excluded.pending_confirmations_json,
            updated_at = excluded.updated_at
        """,
        (
            snapshot.workflow_stage,
            snapshot.current_substep,
            snapshot.active_section_id,
            snapshot.next_action,
            "blocked" if snapshot.blockers else "ready",
            json.dumps(snapshot.blockers, ensure_ascii=False),
            json.dumps(snapshot.pending_confirmations, ensure_ascii=False),
            now_iso(),
        ),
    )
    conn.commit()
    return snapshot


def snapshot_to_result(snapshot: RuntimeSnapshot) -> dict[str, Any]:
    return {
        "artifact_root": str(snapshot.artifact_root),
        "db_path": str(snapshot.db_path),
        "workflow_stage": snapshot.workflow_stage,
        "current_substep": snapshot.current_substep,
        "active_section_id": snapshot.active_section_id,
        "next_action": snapshot.next_action,
        "blockers": snapshot.blockers,
        "pending_confirmations": snapshot.pending_confirmations,
        "instruction_refs": snapshot.instruction_refs,
        "rendered_views": snapshot.rendered_views,
    }


def gate_from_source_path(source_path: Path) -> dict[str, Any]:
    resolved_source = validate_source_path(source_path)
    artifact_root = resolve_artifact_root(resolved_source)
    db_path = resolve_db_path(artifact_root)
    if not db_path.is_file():
        return {
            "artifact_root": str(artifact_root),
            "db_path": str(db_path),
            "workflow_stage": WORKFLOW_STAGES["bootstrap"],
            "next_action": ACTIONS["bootstrap"],
            "blockers": [],
            "pending_confirmations": [],
            "instruction_refs": stage_instruction_refs(WORKFLOW_STAGES["bootstrap"]),
            "rendered_views": {},
            "source_path": str(resolved_source),
        }
    conn = connect_db(db_path)
    try:
        init_schema(conn)
        snapshot = build_snapshot(conn, artifact_root)
        result = snapshot_to_result(snapshot)
        result["source_path"] = str(resolved_source)
        return result
    finally:
        conn.close()


def gate_from_artifact_root(artifact_root: Path) -> dict[str, Any]:
    resolved_root = validate_artifact_root(artifact_root)
    db_path = resolve_db_path(resolved_root)
    if not db_path.is_file():
        return {
            "artifact_root": str(resolved_root),
            "db_path": str(db_path),
            "workflow_stage": WORKFLOW_STAGES["bootstrap"],
            "next_action": ACTIONS["bootstrap"],
            "blockers": [
                "Runtime database is missing. Re-enter with --source-path to bootstrap a new workspace."
            ],
            "pending_confirmations": [],
            "instruction_refs": stage_instruction_refs(WORKFLOW_STAGES["bootstrap"]),
            "rendered_views": {},
        }
    conn = connect_db(db_path)
    try:
        init_schema(conn)
        snapshot = build_snapshot(conn, resolved_root)
        return snapshot_to_result(snapshot)
    finally:
        conn.close()


def read_payload_file(payload_file: Path) -> dict[str, Any]:
    return json.loads(payload_file.read_text(encoding="utf-8"))


def require_next_action(
    artifact_root: Path, action: str, conn: sqlite3.Connection
) -> None:
    snapshot = build_snapshot(conn, artifact_root)
    if snapshot.next_action != action:
        raise ValueError(
            f"Action '{action}' is not allowed right now; expected '{snapshot.next_action}'"
        )


def persist_bootstrap_runtime_db(
    artifact_root: Path | None, source_path: Path
) -> dict[str, Any]:
    resolved_source = validate_source_path(source_path)
    resolved_root = resolve_artifact_root(resolved_source) if artifact_root is None else validate_artifact_root(artifact_root)
    document_slug = slugify_source_name(resolved_source)
    db_path = resolve_db_path(resolved_root)
    if db_path.exists():
        raise FileExistsError(f"Runtime DB already exists: {db_path}")

    conn = connect_db(db_path)
    try:
        init_schema(conn)
        upsert_runtime_workspace(conn, document_slug, resolved_root, db_path)
        upsert_payload_table(
            conn,
            "manuscript_source",
            {
                "source_id": document_slug,
                "source_path": str(resolved_source),
                "source_type": detect_source_type(resolved_source),
            },
        )
        for table_name in (
            "manuscript_intake",
            "supporting_elements_inventory",
            "manuscript_analysis",
            "target_settings",
            "style_profile",
            "condensation_plan",
            "final_outputs",
        ):
            upsert_payload_table(conn, table_name, {})
        replace_pending_confirmations(conn, WORKFLOW_STAGES["analysis"], [])
        replace_pending_confirmations(conn, WORKFLOW_STAGES["targets"], [])
        replace_pending_confirmations(conn, WORKFLOW_STAGES["style"], [])
        replace_pending_confirmations(conn, WORKFLOW_STAGES["plan"], [])
        snapshot = build_snapshot(conn, resolved_root)
        result = snapshot_to_result(snapshot)
        append_action_log(
            conn,
            ACTIONS["bootstrap"],
            {"source_path": str(resolved_source)},
            result,
        )
        conn.commit()
        return result
    finally:
        conn.close()


def persist_intake_and_inventory(artifact_root: Path) -> dict[str, Any]:
    resolved_root = validate_artifact_root(artifact_root)
    db_path = resolve_db_path(resolved_root)
    conn = connect_db(db_path)
    try:
        init_schema(conn)
        require_next_action(resolved_root, ACTIONS["intake"], conn)
        source = load_payload_table(conn, "manuscript_source")
        source_path = validate_source_path(Path(str(source.get("source_path", ""))))
        source_text = source_path.read_text(encoding="utf-8")
        intake_payload = build_intake_payload(source_path, source_text)
        inventory_payload = build_supporting_elements_inventory(source_text)
        upsert_payload_table(conn, "manuscript_intake", intake_payload)
        upsert_payload_table(conn, "supporting_elements_inventory", inventory_payload)
        snapshot = build_snapshot(conn, resolved_root)
        result = snapshot_to_result(snapshot)
        append_action_log(conn, ACTIONS["intake"], {}, result)
        conn.commit()
        return result
    finally:
        conn.close()


def persist_manuscript_analysis(
    artifact_root: Path, payload: dict[str, Any]
) -> dict[str, Any]:
    ensure_required_keys(payload, REQUIRED_ANALYSIS_KEYS, ACTIONS["analysis"])
    resolved_root = validate_artifact_root(artifact_root)
    db_path = resolve_db_path(resolved_root)
    conn = connect_db(db_path)
    try:
        init_schema(conn)
        require_next_action(resolved_root, ACTIONS["analysis"], conn)
        stage_payload = {
            "main_scope": str(payload["main_scope"]),
            "main_scope_locator": parse_scope_locator(payload["main_scope_locator"]),
            "aux_scopes": normalize_aux_scopes(payload.get("aux_scopes", [])),
            "topic": str(payload["topic"]),
            "main_work": payload_list(payload["main_work"]),
            "novelty": payload_list(payload["novelty"]),
            "section_outline": payload_list(payload["section_outline"]),
            "removable_candidates": payload_list(payload["removable_candidates"]),
            "open_questions": payload_list(payload["open_questions"]),
            "status": "analysis_complete",
        }
        upsert_payload_table(conn, "manuscript_analysis", stage_payload)
        confirmations = normalize_pending_confirmation_items(
            payload.get("pending_confirmations", []),
            WORKFLOW_STAGES["analysis"],
        )
        replace_pending_confirmations(conn, WORKFLOW_STAGES["analysis"], confirmations)
        snapshot = build_snapshot(conn, resolved_root)
        result = snapshot_to_result(snapshot)
        append_action_log(conn, ACTIONS["analysis"], payload, result)
        conn.commit()
        return result
    finally:
        conn.close()


def persist_raw_scope_segments(artifact_root: Path) -> dict[str, Any]:
    resolved_root = validate_artifact_root(artifact_root)
    db_path = resolve_db_path(resolved_root)
    conn = connect_db(db_path)
    try:
        init_schema(conn)
        require_next_action(resolved_root, ACTIONS["raw_scope_segments"], conn)
        source = load_payload_table(conn, "manuscript_source")
        analysis = load_payload_table(conn, "manuscript_analysis")
        main_scope_locator = parse_scope_locator(analysis.get("main_scope_locator"))
        aux_scopes = normalize_aux_scopes(analysis.get("aux_scopes", []))
        source_path = validate_source_path(Path(str(source.get("source_path", ""))))
        source_text = source_path.read_text(encoding="utf-8")
        segments = build_scoped_raw_segments(source_text, main_scope_locator, aux_scopes)
        replace_raw_scope_segments(conn, segments)
        snapshot = build_snapshot(conn, resolved_root)
        result = snapshot_to_result(snapshot)
        append_action_log(
            conn,
            ACTIONS["raw_scope_segments"],
            {
                "main_scope_locator": main_scope_locator,
                "aux_scope_count": len(aux_scopes),
                "segment_count": len(segments),
            },
            result,
        )
        conn.commit()
        return result
    finally:
        conn.close()


def persist_semantic_source_units(
    artifact_root: Path, payload: dict[str, Any]
) -> dict[str, Any]:
    resolved_root = validate_artifact_root(artifact_root)
    db_path = resolve_db_path(resolved_root)
    conn = connect_db(db_path)
    try:
        init_schema(conn)
        require_next_action(resolved_root, ACTIONS["semantic_source_units"], conn)
        raw_segments = load_raw_scope_segments(conn)
        normalized_units = normalize_semantic_source_units(payload, raw_segments)
        replace_semantic_source_units(conn, normalized_units)
        snapshot = build_snapshot(conn, resolved_root)
        result = snapshot_to_result(snapshot)
        append_action_log(conn, ACTIONS["semantic_source_units"], payload, result)
        conn.commit()
        return result
    finally:
        conn.close()


def normalize_pending_confirmation_items(
    items: Any, stage_name: str
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    if not isinstance(items, list):
        return normalized
    for index, item in enumerate(items, start=1):
        if isinstance(item, str):
            normalized.append(
                {
                    "stage_name": stage_name,
                    "item_key": f"pending_{index}",
                    "prompt": item,
                }
            )
        elif isinstance(item, dict):
            prompt = str(item.get("prompt", "")).strip()
            if not prompt:
                continue
            normalized.append(
                {
                    "stage_name": stage_name,
                    "item_key": str(item.get("item_key", f"pending_{index}")),
                    "prompt": prompt,
                }
            )
    return normalized


def summarize_confirmed_content_selection(
    items: list[dict[str, Any]],
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {
        "must_keep": [],
        "simplify_first": [],
        "must_avoid": [],
    }
    for item in items:
        if item.get("status") != "confirmed":
            continue
        bucket = str(item.get("bucket", "")).strip()
        if bucket in result:
            result[bucket].append(str(item.get("title", "")).strip())
    return result


def persist_target_settings_basics(
    artifact_root: Path, payload: dict[str, Any]
) -> dict[str, Any]:
    ensure_required_keys(
        payload, REQUIRED_TARGET_BASICS_KEYS, ACTIONS["target_settings_basics"]
    )
    resolved_root = validate_artifact_root(artifact_root)
    db_path = resolve_db_path(resolved_root)
    conn = connect_db(db_path)
    try:
        init_schema(conn)
        require_next_action(resolved_root, ACTIONS["target_settings_basics"], conn)
        template_id = str(payload["latex_template_id"])
        template_path = LATEX_TEMPLATE_ROOT / f"{template_id}.tex"
        if not template_path.is_file():
            raise FileNotFoundError(f"Missing LaTeX template preset: {template_path}")
        body_length = payload["target_body_length"]
        if not isinstance(body_length, dict):
            raise ValueError("target_body_length must be an object")
        settings_payload = {
            "target_language": str(payload["target_language"]),
            "target_form": str(payload["target_form"]),
            "target_journal_type": str(payload["target_journal_type"]),
            "latex_template_id": template_id,
            "target_body_length": {
                "value": body_length.get("value", 0),
                "unit": str(body_length.get("unit", "")),
            },
            "figure_table_preference": str(payload["figure_table_preference"]),
            "reference_handling_preference": str(payload["reference_handling_preference"]),
            "must_keep": [],
            "simplify_first": [],
            "must_avoid": [],
            "basics_completed": True,
            "content_selection_board_ready": False,
            "content_selection_confirmed": False,
            "user_confirmed": False,
        }
        upsert_payload_table(conn, "target_settings", settings_payload)
        confirmations = normalize_pending_confirmation_items(
            payload.get("pending_confirmations", []),
            WORKFLOW_STAGES["targets"],
        )
        replace_pending_confirmations(conn, WORKFLOW_STAGES["targets"], confirmations)
        snapshot = build_snapshot(conn, resolved_root)
        result = snapshot_to_result(snapshot)
        append_action_log(conn, ACTIONS["target_settings_basics"], payload, result)
        conn.commit()
        return result
    finally:
        conn.close()


def persist_content_selection_board(
    artifact_root: Path, payload: dict[str, Any]
) -> dict[str, Any]:
    ensure_required_keys(
        payload,
        REQUIRED_CONTENT_SELECTION_BOARD_KEYS,
        ACTIONS["content_selection_board"],
    )
    resolved_root = validate_artifact_root(artifact_root)
    db_path = resolve_db_path(resolved_root)
    conn = connect_db(db_path)
    try:
        init_schema(conn)
        require_next_action(resolved_root, ACTIONS["content_selection_board"], conn)
        semantic_units = load_semantic_source_units(conn)
        items = normalize_content_selection_items(
            payload, semantic_units, require_non_empty=True
        )
        replace_content_selection_items(
            conn, [{**item, "status": "suggested"} for item in items]
        )
        settings = load_payload_table(conn, "target_settings")
        settings["content_selection_board_ready"] = True
        settings["content_selection_confirmed"] = False
        settings["must_keep"] = []
        settings["simplify_first"] = []
        settings["must_avoid"] = []
        settings["user_confirmed"] = False
        upsert_payload_table(conn, "target_settings", settings)
        snapshot = build_snapshot(conn, resolved_root)
        result = snapshot_to_result(snapshot)
        append_action_log(conn, ACTIONS["content_selection_board"], payload, result)
        conn.commit()
        return result
    finally:
        conn.close()


def confirm_content_selection(
    artifact_root: Path, payload: dict[str, Any]
) -> dict[str, Any]:
    ensure_required_keys(
        payload,
        REQUIRED_CONTENT_SELECTION_CONFIRM_KEYS,
        ACTIONS["confirm_content_selection"],
    )
    resolved_root = validate_artifact_root(artifact_root)
    db_path = resolve_db_path(resolved_root)
    conn = connect_db(db_path)
    try:
        init_schema(conn)
        require_next_action(resolved_root, ACTIONS["confirm_content_selection"], conn)
        semantic_units = load_semantic_source_units(conn)
        existing_items = load_content_selection_items(conn)
        confirmed_items = normalize_content_selection_items(
            payload, semantic_units, require_non_empty=False
        )
        confirmed_by_id = {item["item_id"]: item for item in confirmed_items}
        final_items: list[dict[str, Any]] = []
        seen_rejected: set[str] = set()
        for item in existing_items:
            if item["item_id"] in confirmed_by_id:
                final_items.append({**confirmed_by_id[item["item_id"]], "status": "confirmed"})
            else:
                final_items.append({**item, "status": "rejected"})
                seen_rejected.add(item["item_id"])
        for item in confirmed_items:
            if item["item_id"] not in seen_rejected and item["item_id"] not in {
                existing["item_id"] for existing in existing_items
            }:
                final_items.append({**item, "status": "confirmed"})
        final_items.sort(key=lambda item: (int(item["item_order"]), str(item["item_id"])))
        replace_content_selection_items(conn, final_items)
        settings = load_payload_table(conn, "target_settings")
        summaries = summarize_confirmed_content_selection(final_items)
        settings["must_keep"] = summaries["must_keep"]
        settings["simplify_first"] = summaries["simplify_first"]
        settings["must_avoid"] = summaries["must_avoid"]
        settings["content_selection_confirmed"] = True
        settings["user_confirmed"] = False
        upsert_payload_table(conn, "target_settings", settings)
        snapshot = build_snapshot(conn, resolved_root)
        result = snapshot_to_result(snapshot)
        append_action_log(conn, ACTIONS["confirm_content_selection"], payload, result)
        conn.commit()
        return result
    finally:
        conn.close()


def finalize_target_settings(
    artifact_root: Path, payload: dict[str, Any]
) -> dict[str, Any]:
    ensure_required_keys(
        payload, REQUIRED_TARGET_FINALIZE_KEYS, ACTIONS["finalize_target_settings"]
    )
    resolved_root = validate_artifact_root(artifact_root)
    db_path = resolve_db_path(resolved_root)
    conn = connect_db(db_path)
    try:
        init_schema(conn)
        require_next_action(resolved_root, ACTIONS["finalize_target_settings"], conn)
        if bool(payload["user_confirmed"]) is not True:
            raise ValueError("finalize_target_settings requires user_confirmed=true")
        settings = load_payload_table(conn, "target_settings")
        if not settings.get("content_selection_confirmed", False):
            raise ValueError("content selection must be confirmed before final target confirmation")
        settings["user_confirmed"] = True
        upsert_payload_table(conn, "target_settings", settings)
        confirmations = normalize_pending_confirmation_items(
            payload.get("pending_confirmations", []),
            WORKFLOW_STAGES["targets"],
        )
        replace_pending_confirmations(conn, WORKFLOW_STAGES["targets"], confirmations)
        snapshot = build_snapshot(conn, resolved_root)
        result = snapshot_to_result(snapshot)
        append_action_log(conn, ACTIONS["finalize_target_settings"], payload, result)
        conn.commit()
        return result
    finally:
        conn.close()


def persist_style_profile(
    artifact_root: Path, payload: dict[str, Any]
) -> dict[str, Any]:
    ensure_required_keys(payload, REQUIRED_STYLE_KEYS, ACTIONS["style"])
    resolved_root = validate_artifact_root(artifact_root)
    db_path = resolve_db_path(resolved_root)
    conn = connect_db(db_path)
    try:
        init_schema(conn)
        require_next_action(resolved_root, ACTIONS["style"], conn)
        style_payload = {
            "source_style": str(payload["source_style"]),
            "problems_to_fix": str(payload["problems_to_fix"]),
            "target_style_guidance": str(payload["target_style_guidance"]),
            "open_questions": payload_list(payload["open_questions"]),
            "status": "complete",
        }
        upsert_payload_table(conn, "style_profile", style_payload)
        confirmations = normalize_pending_confirmation_items(
            payload.get("pending_confirmations", []),
            WORKFLOW_STAGES["style"],
        )
        replace_pending_confirmations(conn, WORKFLOW_STAGES["style"], confirmations)
        snapshot = build_snapshot(conn, resolved_root)
        result = snapshot_to_result(snapshot)
        append_action_log(conn, ACTIONS["style"], payload, result)
        conn.commit()
        return result
    finally:
        conn.close()


def persist_condensation_plan(
    artifact_root: Path, payload: dict[str, Any]
) -> dict[str, Any]:
    ensure_required_keys(payload, REQUIRED_PLAN_KEYS, ACTIONS["plan"])
    resolved_root = validate_artifact_root(artifact_root)
    db_path = resolve_db_path(resolved_root)
    conn = connect_db(db_path)
    try:
        init_schema(conn)
        require_next_action(resolved_root, ACTIONS["plan"], conn)
        plan_payload = {
            "core_message": str(payload["core_message"]),
            "priority_map": str(payload["priority_map"]),
            "target_outline": str(payload["target_outline"]),
            "length_allocation": str(payload["length_allocation"]),
            "omit_merge_strategy": str(payload["omit_merge_strategy"]),
            "figure_table_plan": str(payload["figure_table_plan"]),
            "reference_plan": str(payload["reference_plan"]),
            "approval_status": str(payload["approval_status"]),
        }
        upsert_payload_table(conn, "condensation_plan", plan_payload)
        confirmations = normalize_pending_confirmation_items(
            payload.get("pending_confirmations", []),
            WORKFLOW_STAGES["plan"],
        )
        replace_pending_confirmations(conn, WORKFLOW_STAGES["plan"], confirmations)
        snapshot = build_snapshot(conn, resolved_root)
        result = snapshot_to_result(snapshot)
        append_action_log(conn, ACTIONS["plan"], payload, result)
        conn.commit()
        return result
    finally:
        conn.close()


def persist_section_rewrite_plan(
    artifact_root: Path, payload: dict[str, Any]
) -> dict[str, Any]:
    ensure_required_keys(payload, REQUIRED_SECTION_PLAN_KEYS, ACTIONS["section_plan"])
    resolved_root = validate_artifact_root(artifact_root)
    db_path = resolve_db_path(resolved_root)
    conn = connect_db(db_path)
    try:
        init_schema(conn)
        require_next_action(resolved_root, ACTIONS["section_plan"], conn)
        if not isinstance(payload.get("sections"), list) or not payload["sections"]:
            raise ValueError("persist_section_rewrite_plan requires a non-empty sections list")
        semantic_units = load_semantic_source_units(conn)
        raw_segments = load_raw_scope_segments(conn)
        settings = load_payload_table(conn, "target_settings")
        if not semantic_units:
            raise ValueError("semantic source units must exist before section rewrite planning")
        normalized_sections: list[dict[str, Any]] = []
        has_simplify_consumption = False
        for index, item in enumerate(payload["sections"], start=1):
            if not isinstance(item, dict):
                raise ValueError("each section rewrite plan item must be an object")
            section_id = str(item.get("section_id", "")).strip()
            section_title = str(item.get("section_title", "")).strip()
            if not section_id or not section_title:
                raise ValueError("section rewrite plan items require section_id and section_title")
            planned_count_value = int(item.get("planned_count_value", 0))
            count_unit = str(item.get("count_unit", "")).strip() or "words"
            sources = normalize_section_plan_sources(item.get("sources", []))
            validate_semantic_unit_refs(sources, semantic_units, "section rewrite plan")
            if not sources:
                raise ValueError(
                    f"section rewrite plan '{section_id}' must include at least one source binding"
                )
            for source in sources:
                if (
                    source["source_kind"] == "semantic_unit"
                    and semantic_unit_uses_aux(source["source_ref"], semantic_units, raw_segments)
                    and not source["usage_note"].strip()
                ):
                    raise ValueError(
                        f"section rewrite plan '{section_id}' must explain why aux-backed semantic unit '{source['source_ref']}' is used"
                    )
            normalized_sections.append(
                {
                    "section_id": section_id,
                    "section_order": int(item.get("section_order", index)),
                    "section_title": section_title,
                    "planned_count_value": planned_count_value,
                    "count_unit": count_unit,
                    "tolerance_percent": int(item.get("tolerance_percent", 15)),
                    "must_cover": payload_list(item.get("must_cover", [])),
                    "simplify_first": payload_list(item.get("simplify_first", [])),
                    "must_avoid": payload_list(item.get("must_avoid", [])),
                    "status": "planned",
                    "sources": sources,
                }
            )
            if payload_list(item.get("simplify_first", [])):
                has_simplify_consumption = True
        if payload_list(settings.get("simplify_first", [])) and not has_simplify_consumption:
            raise ValueError(
                "section rewrite plan must consume target_settings.simplify_first in at least one section"
            )
        replace_section_rewrite_plan(conn, normalized_sections)
        snapshot = build_snapshot(conn, resolved_root)
        result = snapshot_to_result(snapshot)
        append_action_log(conn, ACTIONS["section_plan"], payload, result)
        conn.commit()
        return result
    finally:
        conn.close()


def prepare_section_drafting(artifact_root: Path) -> dict[str, Any]:
    resolved_root = validate_artifact_root(artifact_root)
    db_path = resolve_db_path(resolved_root)
    conn = connect_db(db_path)
    try:
        init_schema(conn)
        require_next_action(resolved_root, ACTIONS["prepare_draft"], conn)
        plan_sections = load_section_rewrite_plan(conn)
        drafts = load_draft_sections(conn)
        next_section = select_next_section(plan_sections, drafts)
        if next_section is None:
            raise ValueError("No pending section is available for drafting")
        if next_section["section_id"] not in drafts:
            upsert_draft_section(
                conn,
                next_section["section_id"],
                "",
                0,
                str(next_section["count_unit"]),
                "pending",
                "draft",
            )
        append_draft_section_event(
            conn,
            next_section["section_id"],
            "prepare_section_drafting",
            f"Activated section {next_section['section_title']}",
        )
        snapshot = build_snapshot(conn, resolved_root)
        result = snapshot_to_result(snapshot)
        append_action_log(
            conn,
            ACTIONS["prepare_draft"],
            {"section_id": next_section["section_id"]},
            result,
        )
        conn.commit()
        return result
    finally:
        conn.close()


def persist_section_draft(
    artifact_root: Path, payload: dict[str, Any]
) -> dict[str, Any]:
    ensure_required_keys(payload, REQUIRED_SECTION_DRAFT_KEYS, ACTIONS["draft_section"])
    resolved_root = validate_artifact_root(artifact_root)
    db_path = resolve_db_path(resolved_root)
    conn = connect_db(db_path)
    try:
        init_schema(conn)
        require_next_action(resolved_root, ACTIONS["draft_section"], conn)
        snapshot = build_snapshot(conn, resolved_root)
        active_section_id = snapshot.active_section_id
        section_id = str(payload["section_id"]).strip()
        if section_id != active_section_id:
            raise ValueError(
                f"persist_section_draft must target active section '{active_section_id}'"
            )
        plan_sections = {
            item["section_id"]: item for item in load_section_rewrite_plan(conn)
        }
        plan_item = plan_sections.get(section_id)
        if plan_item is None:
            raise ValueError(f"Unknown section_id: {section_id}")
        draft_tex = str(payload["draft_tex"])
        if not draft_tex.strip():
            raise ValueError("draft_tex must not be empty")
        actual_count_value = count_draft_text(draft_tex, plan_item["count_unit"])
        planned_count = int(plan_item["planned_count_value"])
        tolerance_percent = int(plan_item["tolerance_percent"])
        lower_bound = int(planned_count * (100 - tolerance_percent) / 100)
        upper_bound = int(planned_count * (100 + tolerance_percent) / 100)
        count_check_status = (
            "passed" if lower_bound <= actual_count_value <= upper_bound else "failed"
        )
        review_status = "pending_review" if count_check_status == "passed" else "draft"
        provenance = normalize_section_draft_sources(payload.get("source_refs", []))
        if not provenance:
            raise ValueError("section draft source_refs must not be empty")
        validate_semantic_unit_refs(
            provenance, load_semantic_source_units(conn), "section draft"
        )
        upsert_draft_section(
            conn,
            section_id,
            draft_tex,
            actual_count_value,
            plan_item["count_unit"],
            count_check_status,
            review_status,
        )
        replace_draft_section_sources(conn, section_id, provenance)
        append_draft_section_event(
            conn,
            section_id,
            "persist_section_draft",
            f"actual={actual_count_value} {plan_item['count_unit']}, check={count_check_status}",
        )
        snapshot = build_snapshot(conn, resolved_root)
        result = snapshot_to_result(snapshot)
        append_action_log(conn, ACTIONS["draft_section"], payload, result)
        conn.commit()
        return result
    finally:
        conn.close()


def approve_section_draft(
    artifact_root: Path, payload: dict[str, Any]
) -> dict[str, Any]:
    ensure_required_keys(payload, REQUIRED_SECTION_APPROVAL_KEYS, ACTIONS["approve_section"])
    resolved_root = validate_artifact_root(artifact_root)
    db_path = resolve_db_path(resolved_root)
    conn = connect_db(db_path)
    try:
        init_schema(conn)
        require_next_action(resolved_root, ACTIONS["approve_section"], conn)
        snapshot = build_snapshot(conn, resolved_root)
        active_section_id = snapshot.active_section_id
        section_id = str(payload["section_id"]).strip()
        if section_id != active_section_id:
            raise ValueError(
                f"approve_section_draft must target active section '{active_section_id}'"
            )
        approved = bool(payload["approved"])
        draft = load_draft_sections(conn).get(section_id)
        if draft is None:
            raise ValueError("No draft exists for the active section")
        if approved and draft.get("count_check_status") != "passed":
            raise ValueError("Cannot approve a section whose count check has not passed")
        review_status = "approved" if approved else "rejected"
        upsert_draft_section(
            conn,
            section_id,
            str(draft["draft_tex"]),
            int(draft["actual_count_value"]),
            str(draft["count_unit"]),
            str(draft["count_check_status"]),
            review_status,
        )
        append_draft_section_event(
            conn,
            section_id,
            "approve_section_draft",
            str(payload.get("review_note", "approved" if approved else "rejected")),
        )
        snapshot = build_snapshot(conn, resolved_root)
        result = snapshot_to_result(snapshot)
        append_action_log(conn, ACTIONS["approve_section"], payload, result)
        conn.commit()
        return result
    finally:
        conn.close()


def persist_output_target(
    artifact_root: Path, payload: dict[str, Any]
) -> dict[str, Any]:
    ensure_required_keys(payload, REQUIRED_OUTPUT_TARGET_KEYS, ACTIONS["output_target"])
    resolved_root = validate_artifact_root(artifact_root)
    db_path = resolve_db_path(resolved_root)
    conn = connect_db(db_path)
    try:
        init_schema(conn)
        require_next_action(resolved_root, ACTIONS["output_target"], conn)
        output_dir_value = str(payload.get("output_dir", "")).strip()
        output_dir = (
            Path(output_dir_value).resolve()
            if output_dir_value
            else Path.cwd().resolve()
        )
        images_dir = output_dir / "images"
        upsert_output_target(conn, output_dir, images_dir, bool(payload["user_confirmed"]))
        snapshot = build_snapshot(conn, resolved_root)
        result = snapshot_to_result(snapshot)
        append_action_log(
            conn,
            ACTIONS["output_target"],
            {"output_dir": str(output_dir), "user_confirmed": bool(payload["user_confirmed"])},
            result,
        )
        conn.commit()
        return result
    finally:
        conn.close()


def render_final_output_bundle(artifact_root: Path) -> dict[str, Any]:
    resolved_root = validate_artifact_root(artifact_root)
    db_path = resolve_db_path(resolved_root)
    conn = connect_db(db_path)
    try:
        init_schema(conn)
        require_next_action(resolved_root, ACTIONS["render_bundle"], conn)
        settings = load_payload_table(conn, "target_settings")
        output_target = load_output_target(conn)
        template_id = str(settings.get("latex_template_id", ""))
        if not template_id:
            raise ValueError("target_settings.latex_template_id is missing")
        template_path = LATEX_TEMPLATE_ROOT / f"{template_id}.tex"
        if not template_path.is_file():
            raise FileNotFoundError(f"Missing LaTeX template preset: {template_path}")
        if output_target.get("user_confirmed") is not True:
            raise ValueError("Final output target is not confirmed")
        plan_sections = load_section_rewrite_plan(conn)
        draft_sections = load_draft_sections(conn)
        raw_segments = load_raw_scope_segments(conn)
        semantic_units = load_semantic_source_units(conn)
        raw_segments_by_id = {item["segment_id"]: item for item in raw_segments}
        semantic_units_by_id = {item["unit_id"]: item for item in semantic_units}
        approved_sections: list[dict[str, Any]] = []
        for item in plan_sections:
            draft = draft_sections.get(item["section_id"])
            if draft is None or draft.get("review_status") != "approved":
                raise ValueError("All sections must be approved before final rendering")
            approved_sections.append({**item, **draft})
        inventory = load_payload_table(conn, "supporting_elements_inventory")
        used_image_paths: list[str] = []
        for section in approved_sections:
            used_image_paths.extend(
                match.group(1).strip()
                for match in INCLUDEGRAPHICS_PATTERN.finditer(str(section["draft_tex"]))
                if match.group(1).strip()
            )
        source_assets = {
            asset_path: asset_path
            for figure in inventory.get("figures", [])
            if isinstance(figure, dict)
            for asset_path in figure.get("asset_paths", [])
        }
        output_dir = Path(str(output_target["output_dir"]))
        images_dir = ensure_directory(Path(str(output_target["images_dir"])))
        copied_names: set[str] = set()
        image_rewrites: dict[str, str] = {}
        for asset_ref in used_image_paths:
            source_asset = source_assets.get(asset_ref)
            if not source_asset:
                raise FileNotFoundError(f"Missing source image asset for final bundle: {asset_ref}")
            source_path = Path(str(source_asset))
            if not source_path.is_absolute():
                source_path = validate_source_path(
                    Path(str(load_payload_table(conn, "manuscript_source")["source_path"])).parent
                    / source_path
                )
            else:
                source_path = validate_source_path(source_path)
            target_name = infer_copied_image_name(str(source_path), copied_names)
            shutil.copy2(source_path, images_dir / target_name)
            image_rewrites[asset_ref] = f"images/{target_name}"

        section_blocks: list[str] = []
        for item in approved_sections:
            draft_tex = str(item["draft_tex"])
            for original, rewritten in image_rewrites.items():
                draft_tex = draft_tex.replace(f"{{{original}}}", f"{{{rewritten}}}")
            section_blocks.append(draft_tex.strip())
        preamble = render_template_preamble(template_id).rstrip()
        final_draft_tex = (
            preamble
            + "\n\n"
            + "\n\n".join(section_blocks)
            + "\n\n\\end{document}\n"
        )
        rewrite_report_lines = [
            "# Rewrite Report",
            "",
            "## Run Summary",
            f"- Template: `{template_id}`",
            f"- Output dir: `{output_dir}`",
            "",
            "## Final Draft Section Map",
        ]
        for item in approved_sections:
            expanded_sources = expand_semantic_source_refs(
                item["sources"], semantic_units_by_id, raw_segments_by_id
            )
            has_aux = any(
                source.get("semantic_unit")
                and any(
                    str(member.get("scope_role", "")) == "aux"
                    for member in cast(
                        list[dict[str, Any]],
                        source["semantic_unit"].get("member_segments", []),
                    )
                )
                for source in expanded_sources
            )
            rewrite_report_lines.append(
                f"- [{item['section_order']}] {item['section_title']} <- {', '.join(source['source_ref'] for source in item['sources']) or '（无）'}{' | uses aux support' if has_aux else ''}"
            )
        rewrite_report_lines.extend(["", "## Key Paragraph And Element Notes"])
        for item in approved_sections:
            expanded_sources = expand_semantic_source_refs(
                item["sources"], semantic_units_by_id, raw_segments_by_id
            )
            rewrite_report_lines.append(f"### {item['section_title']}")
            if expanded_sources:
                for source in expanded_sources:
                    rewrite_report_lines.append(
                        f"- {source['source_kind']}: `{source['source_ref']}`"
                    )
                    semantic_unit = source.get("semantic_unit")
                    if semantic_unit:
                        member_lines = []
                        for member in cast(
                            list[dict[str, Any]], semantic_unit.get("member_segments", [])
                        ):
                            member_lines.append(
                                f"`{member['segment_id']}`/{member.get('scope_role', 'unknown')}/{member.get('scope_bucket_id', 'unknown')}"
                            )
                        rewrite_report_lines.append(
                            f"  - unit: {semantic_unit.get('unit_title', '')}"
                        )
                        rewrite_report_lines.append(
                            f"  - members: {', '.join(member_lines) if member_lines else '（空）'}"
                        )
            else:
                rewrite_report_lines.append("- （空）")
        rewrite_report_lines.extend(["", "## Unresolved Risks / Follow-up", "- （空）"])
        rewrite_report_md = "\n".join(rewrite_report_lines).strip() + "\n"
        final_payload = {
            "template_id": template_id,
            "final_draft_tex": final_draft_tex,
            "rewrite_report_md": rewrite_report_md,
            "output_dir": str(output_dir),
            "images_dir": str(images_dir),
            "status": "complete",
        }
        upsert_payload_table(conn, "final_outputs", final_payload)
        ensure_directory(output_dir)
        (output_dir / "final-draft.tex").write_text(final_draft_tex, encoding="utf-8")
        (output_dir / "rewrite-report.md").write_text(rewrite_report_md, encoding="utf-8")
        snapshot = build_snapshot(conn, resolved_root)
        result = snapshot_to_result(snapshot)
        append_action_log(conn, ACTIONS["render_bundle"], {"output_dir": str(output_dir)}, result)
        conn.commit()
        return result
    finally:
        conn.close()


def perform_action(
    action: str,
    artifact_root: Path | None = None,
    source_path: Path | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    if action == ACTIONS["bootstrap"]:
        if source_path is None:
            raise ValueError("bootstrap_runtime_db requires --source-path")
        return persist_bootstrap_runtime_db(artifact_root, source_path)
    if artifact_root is None:
        raise ValueError(f"{action} requires --artifact-root")
    if action == ACTIONS["intake"]:
        return persist_intake_and_inventory(artifact_root)
    if action == ACTIONS["analysis"]:
        return persist_manuscript_analysis(artifact_root, payload)
    if action == ACTIONS["raw_scope_segments"]:
        return persist_raw_scope_segments(artifact_root)
    if action == ACTIONS["semantic_source_units"]:
        return persist_semantic_source_units(artifact_root, payload)
    if action == ACTIONS["target_settings_basics"]:
        return persist_target_settings_basics(artifact_root, payload)
    if action == ACTIONS["content_selection_board"]:
        return persist_content_selection_board(artifact_root, payload)
    if action == ACTIONS["confirm_content_selection"]:
        return confirm_content_selection(artifact_root, payload)
    if action == ACTIONS["finalize_target_settings"]:
        return finalize_target_settings(artifact_root, payload)
    if action == ACTIONS["style"]:
        return persist_style_profile(artifact_root, payload)
    if action == ACTIONS["plan"]:
        return persist_condensation_plan(artifact_root, payload)
    if action == ACTIONS["section_plan"]:
        return persist_section_rewrite_plan(artifact_root, payload)
    if action == ACTIONS["prepare_draft"]:
        return prepare_section_drafting(artifact_root)
    if action == ACTIONS["draft_section"]:
        return persist_section_draft(artifact_root, payload)
    if action == ACTIONS["approve_section"]:
        return approve_section_draft(artifact_root, payload)
    if action == ACTIONS["output_target"]:
        return persist_output_target(artifact_root, payload)
    if action == ACTIONS["render_bundle"]:
        return render_final_output_bundle(artifact_root)
    if action in DEPRECATED_ACTIONS:
        replacement = DEPRECATED_ACTIONS[action]
        raise ValueError(
            f"Action '{action}' is deprecated; use '{replacement}' instead"
        )
    raise ValueError(f"Unsupported action: {action}")

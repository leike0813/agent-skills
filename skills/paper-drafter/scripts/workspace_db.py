from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DB_FILENAME = "paper-drafter.db"

AGENT_RESUME_MD = "01-agent-resume.md"
INTAKE_DOMAIN_MD = "02-intake-and-domain.md"
MACRO_PICTURE_MD = "03-macro-picture.md"
RESEARCH_PLAN_MD = "04-research-plan.md"
OUTLINE_MD = "05-outline.md"
SECTION_WRITING_PLAN_MD = "06-section-writing-plan.md"
EVIDENCE_BOARD_MD = "07-evidence-board.md"
STYLE_PROFILE_MD = "08-style-profile.md"
DRAFTING_BOARD_MD = "09-drafting-board.md"
REFERENCE_ROUTE_BOARD_MD = "10-reference-route-board.md"
MANUSCRIPT_PREVIEW_MD = "11-manuscript-preview.md"
SECTIONS_DIR = "sections"

ALLOWED_NEXT_ACTIONS = {
    "collect_intake",
    "confirm_macro_picture",
    "confirm_research_plan",
    "confirm_outline",
    "confirm_section_writing_plan",
    "plan_evidence",
    "intake_evidence",
    "build_style_profile",
    "plan_section_outline",
    "draft_section",
    "revise_section",
    "final_consistency_check",
    "completed",
}

ALLOWED_STAGES = {
    "intake",
    "macro_picture",
    "research_plan",
    "outline",
    "section_writing_plan",
    "evidence_plan",
    "evidence_intake",
    "style_profile",
    "section_outline",
    "section_draft",
    "confirmation",
    "reference_route",
}

REQUIRED_TABLES = {
    "workflow_state",
    "runtime_context",
    "input_sources",
    "paper_domain_profile",
    "macro_picture",
    "research_plan",
    "outline_sections",
    "section_writing_plans",
    "evidence_items",
    "evidence_gaps",
    "style_samples",
    "style_profile",
    "draft_units",
    "draft_versions",
    "user_confirmations",
    "reference_routes",
    "action_log",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def db_path(artifact_root: Path) -> Path:
    return artifact_root / DB_FILENAME


def connect_db(artifact_root: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(artifact_root))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def artifact_paths(artifact_root: Path) -> dict[str, Path]:
    sections = artifact_root / SECTIONS_DIR
    return {
        "db": db_path(artifact_root),
        "agent_resume": artifact_root / AGENT_RESUME_MD,
        "intake_domain": artifact_root / INTAKE_DOMAIN_MD,
        "macro_picture": artifact_root / MACRO_PICTURE_MD,
        "research_plan": artifact_root / RESEARCH_PLAN_MD,
        "outline": artifact_root / OUTLINE_MD,
        "section_writing_plan": artifact_root / SECTION_WRITING_PLAN_MD,
        "evidence_board": artifact_root / EVIDENCE_BOARD_MD,
        "style_profile": artifact_root / STYLE_PROFILE_MD,
        "drafting_board": artifact_root / DRAFTING_BOARD_MD,
        "reference_route_board": artifact_root / REFERENCE_ROUTE_BOARD_MD,
        "manuscript_preview": artifact_root / MANUSCRIPT_PREVIEW_MD,
        "sections_dir": sections,
    }


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS workflow_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            current_stage TEXT NOT NULL,
            stage_gate TEXT NOT NULL,
            next_action TEXT NOT NULL,
            status_summary TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS runtime_context (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            artifact_root TEXT NOT NULL,
            document_language TEXT NOT NULL,
            working_language TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS input_sources (
            source_id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            label TEXT NOT NULL,
            path_or_text TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS paper_domain_profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            topic TEXT NOT NULL DEFAULT '',
            canonical_domain_name TEXT NOT NULL DEFAULT '',
            domain_label TEXT NOT NULL DEFAULT '',
            research_area TEXT NOT NULL DEFAULT '',
            target_venue TEXT NOT NULL DEFAULT '',
            constraints_json TEXT NOT NULL DEFAULT '[]',
            confirmed INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS macro_picture (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            topic TEXT NOT NULL DEFAULT '',
            research_question TEXT NOT NULL DEFAULT '',
            gap TEXT NOT NULL DEFAULT '',
            method_path TEXT NOT NULL DEFAULT '',
            contribution TEXT NOT NULL DEFAULT '',
            boundaries TEXT NOT NULL DEFAULT '',
            risks TEXT NOT NULL DEFAULT '',
            confirmed INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS research_plan (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            research_question TEXT NOT NULL DEFAULT '',
            objectives TEXT NOT NULL DEFAULT '',
            novelty TEXT NOT NULL DEFAULT '',
            method_design TEXT NOT NULL DEFAULT '',
            evidence_strategy TEXT NOT NULL DEFAULT '',
            claims_scope TEXT NOT NULL DEFAULT '',
            risks TEXT NOT NULL DEFAULT '',
            confirmed INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS outline_sections (
            section_id TEXT PRIMARY KEY,
            ordinal INTEGER NOT NULL,
            parent_id TEXT NOT NULL DEFAULT '',
            level INTEGER NOT NULL DEFAULT 1,
            title TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT '',
            expected_evidence TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'planned',
            confirmed INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS section_writing_plans (
            section_id TEXT PRIMARY KEY,
            content_logic TEXT NOT NULL DEFAULT '',
            key_claims TEXT NOT NULL DEFAULT '',
            materials TEXT NOT NULL DEFAULT '',
            expected_visuals TEXT NOT NULL DEFAULT '',
            dependencies TEXT NOT NULL DEFAULT '',
            confirmed INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(section_id) REFERENCES outline_sections(section_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS evidence_items (
            evidence_id TEXT PRIMARY KEY,
            evidence_type TEXT NOT NULL,
            label TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            source_path TEXT NOT NULL DEFAULT '',
            supports_section TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'available',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS evidence_gaps (
            gap_id TEXT PRIMARY KEY,
            section_id TEXT NOT NULL DEFAULT '',
            claim TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'medium',
            status TEXT NOT NULL DEFAULT 'open',
            required_evidence TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS style_samples (
            sample_id TEXT PRIMARY KEY,
            sample_type TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS style_profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            summary TEXT NOT NULL DEFAULT '',
            do_rules TEXT NOT NULL DEFAULT '',
            dont_rules TEXT NOT NULL DEFAULT '',
            tone_terms TEXT NOT NULL DEFAULT '',
            confirmed INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS draft_units (
            unit_id TEXT PRIMARY KEY,
            section_id TEXT NOT NULL,
            outline TEXT NOT NULL DEFAULT '',
            confirmed INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'planned',
            blockers TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            FOREIGN KEY(section_id) REFERENCES outline_sections(section_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS draft_versions (
            version_id TEXT PRIMARY KEY,
            unit_id TEXT NOT NULL,
            version_no INTEGER NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            evidence_notes TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'drafted',
            created_at TEXT NOT NULL,
            FOREIGN KEY(unit_id) REFERENCES draft_units(unit_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS user_confirmations (
            confirmation_id TEXT PRIMARY KEY,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            confirmed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reference_routes (
            route_id TEXT PRIMARY KEY,
            domain TEXT NOT NULL,
            drafting_phase TEXT NOT NULL,
            paper_section TEXT NOT NULL,
            headings_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS action_log (
            action_id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT NOT NULL,
            stage TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        """
    )
    now = utc_now()
    conn.execute(
        """
        INSERT OR IGNORE INTO workflow_state
            (id, current_stage, stage_gate, next_action, status_summary, updated_at)
        VALUES (1, 'stage_0', 'ready', 'collect_intake', 'Workspace initialized; intake is required.', ?)
        """,
        (now,),
    )
    conn.commit()


def validate_schema(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    present = {str(row["name"]) for row in rows}
    missing = sorted(REQUIRED_TABLES - present)
    return [f"missing table: {name}" for name in missing]


def fetch_one(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    return conn.execute(query, params).fetchone()


def fetch_all(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    return list(conn.execute(query, params).fetchall())


def scalar(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> Any:
    row = conn.execute(query, params).fetchone()
    if row is None:
        return None
    return row[0]


def bool_int(value: Any) -> int:
    return 1 if bool(value) else 0


def ensure_id(prefix: str, value: str | None, fallback_index: int) -> str:
    if value and str(value).strip():
        return str(value).strip()
    return f"{prefix}_{fallback_index:03d}"


def write_action_log(conn: sqlite3.Connection, stage: str, payload: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO action_log(action_type, stage, payload_json, created_at) VALUES (?, ?, ?, ?)",
        ("submit_stage_payload", stage, json_dumps(payload), utc_now()),
    )


def upsert_runtime_context(conn: sqlite3.Connection, artifact_root: Path, document_language: str, working_language: str) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO runtime_context(id, artifact_root, document_language, working_language, created_at, updated_at)
        VALUES (1, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            artifact_root = excluded.artifact_root,
            document_language = excluded.document_language,
            working_language = excluded.working_language,
            updated_at = excluded.updated_at
        """,
        (str(artifact_root), document_language, working_language, now, now),
    )


def submit_payload(conn: sqlite3.Connection, stage: str, payload: dict[str, Any]) -> None:
    if stage not in ALLOWED_STAGES:
        allowed = ", ".join(sorted(ALLOWED_STAGES))
        raise ValueError(f"invalid stage: {stage}; expected one of: {allowed}")
    handler = {
        "intake": _submit_intake,
        "macro_picture": _submit_macro_picture,
        "research_plan": _submit_research_plan,
        "outline": _submit_outline,
        "section_writing_plan": _submit_section_writing_plan,
        "evidence_plan": _submit_evidence_plan,
        "evidence_intake": _submit_evidence_intake,
        "style_profile": _submit_style_profile,
        "section_outline": _submit_section_outline,
        "section_draft": _submit_section_draft,
        "confirmation": _submit_confirmation,
        "reference_route": _submit_reference_route,
    }[stage]
    handler(conn, payload)
    write_action_log(conn, stage, payload)
    conn.commit()


def _submit_intake(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO paper_domain_profile
            (id, topic, canonical_domain_name, domain_label, research_area, target_venue, constraints_json, confirmed, updated_at)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            topic = excluded.topic,
            canonical_domain_name = excluded.canonical_domain_name,
            domain_label = excluded.domain_label,
            research_area = excluded.research_area,
            target_venue = excluded.target_venue,
            constraints_json = excluded.constraints_json,
            confirmed = excluded.confirmed,
            updated_at = excluded.updated_at
        """,
        (
            str(payload.get("topic", "")),
            str(payload.get("canonical_domain_name", "")),
            str(payload.get("domain_label", "")),
            str(payload.get("research_area", "")),
            str(payload.get("target_venue", "")),
            json_dumps(payload.get("constraints", [])),
            bool_int(payload.get("confirmed", False)),
            now,
        ),
    )
    for index, source in enumerate(payload.get("input_sources", []) or [], start=1):
        if not isinstance(source, dict):
            continue
        source_id = ensure_id("source", source.get("source_id"), index)
        conn.execute(
            """
            INSERT INTO input_sources(source_id, source_type, label, path_or_text, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                source_type = excluded.source_type,
                label = excluded.label,
                path_or_text = excluded.path_or_text,
                summary = excluded.summary
            """,
            (
                source_id,
                str(source.get("source_type", "note")),
                str(source.get("label", source_id)),
                str(source.get("path_or_text", "")),
                str(source.get("summary", "")),
                now,
            ),
        )


def _submit_macro_picture(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO macro_picture
            (id, topic, research_question, gap, method_path, contribution, boundaries, risks, confirmed, updated_at)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            topic = excluded.topic,
            research_question = excluded.research_question,
            gap = excluded.gap,
            method_path = excluded.method_path,
            contribution = excluded.contribution,
            boundaries = excluded.boundaries,
            risks = excluded.risks,
            confirmed = excluded.confirmed,
            updated_at = excluded.updated_at
        """,
        (
            str(payload.get("topic", "")),
            str(payload.get("research_question", "")),
            str(payload.get("gap", "")),
            str(payload.get("method_path", "")),
            str(payload.get("contribution", "")),
            str(payload.get("boundaries", "")),
            str(payload.get("risks", "")),
            bool_int(payload.get("confirmed", False)),
            now,
        ),
    )


def _submit_research_plan(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO research_plan
            (id, research_question, objectives, novelty, method_design, evidence_strategy, claims_scope, risks, confirmed, updated_at)
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            research_question = excluded.research_question,
            objectives = excluded.objectives,
            novelty = excluded.novelty,
            method_design = excluded.method_design,
            evidence_strategy = excluded.evidence_strategy,
            claims_scope = excluded.claims_scope,
            risks = excluded.risks,
            confirmed = excluded.confirmed,
            updated_at = excluded.updated_at
        """,
        (
            str(payload.get("research_question", "")),
            str(payload.get("objectives", "")),
            str(payload.get("novelty", "")),
            str(payload.get("method_design", "")),
            str(payload.get("evidence_strategy", "")),
            str(payload.get("claims_scope", "")),
            str(payload.get("risks", "")),
            bool_int(payload.get("confirmed", False)),
            now,
        ),
    )


def _submit_outline(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    now = utc_now()
    confirmed = bool_int(payload.get("confirmed", False))
    for index, section in enumerate(payload.get("sections", []) or [], start=1):
        if not isinstance(section, dict):
            continue
        section_id = ensure_id("section", section.get("section_id"), index)
        conn.execute(
            """
            INSERT INTO outline_sections
                (section_id, ordinal, parent_id, level, title, role, expected_evidence, status, confirmed, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(section_id) DO UPDATE SET
                ordinal = excluded.ordinal,
                parent_id = excluded.parent_id,
                level = excluded.level,
                title = excluded.title,
                role = excluded.role,
                expected_evidence = excluded.expected_evidence,
                status = excluded.status,
                confirmed = excluded.confirmed,
                updated_at = excluded.updated_at
            """,
            (
                section_id,
                int(section.get("ordinal", index)),
                str(section.get("parent_id", "")),
                int(section.get("level", 1)),
                str(section.get("title", section_id)),
                str(section.get("role", "")),
                str(section.get("expected_evidence", "")),
                str(section.get("status", "planned")),
                bool_int(section.get("confirmed", confirmed)),
                now,
            ),
        )


def _submit_section_writing_plan(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    now = utc_now()
    for index, plan in enumerate(payload.get("plans", [payload]) or [], start=1):
        if not isinstance(plan, dict):
            continue
        section_id = str(plan.get("section_id", "")).strip()
        if not section_id:
            raise ValueError("section_writing_plan payload requires section_id")
        conn.execute(
            """
            INSERT INTO section_writing_plans
                (section_id, content_logic, key_claims, materials, expected_visuals, dependencies, confirmed, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(section_id) DO UPDATE SET
                content_logic = excluded.content_logic,
                key_claims = excluded.key_claims,
                materials = excluded.materials,
                expected_visuals = excluded.expected_visuals,
                dependencies = excluded.dependencies,
                confirmed = excluded.confirmed,
                updated_at = excluded.updated_at
            """,
            (
                section_id,
                str(plan.get("content_logic", "")),
                str(plan.get("key_claims", "")),
                str(plan.get("materials", "")),
                str(plan.get("expected_visuals", "")),
                str(plan.get("dependencies", "")),
                bool_int(plan.get("confirmed", payload.get("confirmed", False))),
                now,
            ),
        )


def _submit_evidence_plan(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    now = utc_now()
    for index, gap in enumerate(payload.get("gaps", []) or [], start=1):
        if not isinstance(gap, dict):
            continue
        gap_id = ensure_id("gap", gap.get("gap_id"), index)
        conn.execute(
            """
            INSERT INTO evidence_gaps
                (gap_id, section_id, claim, description, severity, status, required_evidence, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(gap_id) DO UPDATE SET
                section_id = excluded.section_id,
                claim = excluded.claim,
                description = excluded.description,
                severity = excluded.severity,
                status = excluded.status,
                required_evidence = excluded.required_evidence,
                updated_at = excluded.updated_at
            """,
            (
                gap_id,
                str(gap.get("section_id", "")),
                str(gap.get("claim", "")),
                str(gap.get("description", "")),
                str(gap.get("severity", "medium")),
                str(gap.get("status", "open")),
                str(gap.get("required_evidence", "")),
                now,
            ),
        )
    _submit_evidence_items(conn, payload)


def _submit_evidence_intake(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    _submit_evidence_items(conn, payload)
    now = utc_now()
    for gap in payload.get("close_gaps", []) or []:
        if isinstance(gap, str):
            gap_id = gap
            status = "closed"
        elif isinstance(gap, dict):
            gap_id = str(gap.get("gap_id", ""))
            status = str(gap.get("status", "closed"))
        else:
            continue
        if gap_id:
            conn.execute("UPDATE evidence_gaps SET status = ?, updated_at = ? WHERE gap_id = ?", (status, now, gap_id))


def _submit_evidence_items(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    now = utc_now()
    for index, item in enumerate(payload.get("items", []) or [], start=1):
        if not isinstance(item, dict):
            continue
        evidence_id = ensure_id("evidence", item.get("evidence_id"), index)
        conn.execute(
            """
            INSERT INTO evidence_items
                (evidence_id, evidence_type, label, summary, source_path, supports_section, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(evidence_id) DO UPDATE SET
                evidence_type = excluded.evidence_type,
                label = excluded.label,
                summary = excluded.summary,
                source_path = excluded.source_path,
                supports_section = excluded.supports_section,
                status = excluded.status
            """,
            (
                evidence_id,
                str(item.get("evidence_type", "note")),
                str(item.get("label", evidence_id)),
                str(item.get("summary", "")),
                str(item.get("source_path", "")),
                str(item.get("supports_section", "")),
                str(item.get("status", "available")),
                now,
            ),
        )


def _submit_style_profile(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    now = utc_now()
    for index, sample in enumerate(payload.get("samples", []) or [], start=1):
        if not isinstance(sample, dict):
            continue
        sample_id = ensure_id("sample", sample.get("sample_id"), index)
        conn.execute(
            """
            INSERT INTO style_samples(sample_id, sample_type, content, notes, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(sample_id) DO UPDATE SET
                sample_type = excluded.sample_type,
                content = excluded.content,
                notes = excluded.notes
            """,
            (
                sample_id,
                str(sample.get("sample_type", "user_sample")),
                str(sample.get("content", "")),
                str(sample.get("notes", "")),
                now,
            ),
        )
    conn.execute(
        """
        INSERT INTO style_profile(id, summary, do_rules, dont_rules, tone_terms, confirmed, updated_at)
        VALUES (1, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            summary = excluded.summary,
            do_rules = excluded.do_rules,
            dont_rules = excluded.dont_rules,
            tone_terms = excluded.tone_terms,
            confirmed = excluded.confirmed,
            updated_at = excluded.updated_at
        """,
        (
            str(payload.get("summary", "")),
            _string_or_join(payload.get("do_rules", "")),
            _string_or_join(payload.get("dont_rules", "")),
            _string_or_join(payload.get("tone_terms", "")),
            bool_int(payload.get("confirmed", False)),
            now,
        ),
    )


def _submit_section_outline(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    now = utc_now()
    section_id = str(payload.get("section_id", "")).strip()
    if not section_id:
        raise ValueError("section_outline payload requires section_id")
    unit_id = str(payload.get("unit_id", section_id)).strip()
    conn.execute(
        """
        INSERT INTO draft_units(unit_id, section_id, outline, confirmed, status, blockers, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(unit_id) DO UPDATE SET
            section_id = excluded.section_id,
            outline = excluded.outline,
            confirmed = excluded.confirmed,
            status = excluded.status,
            blockers = excluded.blockers,
            updated_at = excluded.updated_at
        """,
        (
            unit_id,
            section_id,
            str(payload.get("outline", "")),
            bool_int(payload.get("confirmed", False)),
            str(payload.get("status", "planned")),
            _string_or_join(payload.get("blockers", "")),
            now,
        ),
    )


def _submit_section_draft(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    now = utc_now()
    unit_id = str(payload.get("unit_id", payload.get("section_id", ""))).strip()
    if not unit_id:
        raise ValueError("section_draft payload requires unit_id or section_id")
    version_no = int(scalar(conn, "SELECT COALESCE(MAX(version_no), 0) + 1 FROM draft_versions WHERE unit_id = ?", (unit_id,)) or 1)
    version_id = str(payload.get("version_id", f"{unit_id}_v{version_no:03d}"))
    conn.execute(
        """
        INSERT INTO draft_versions(version_id, unit_id, version_no, content, evidence_notes, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(version_id) DO UPDATE SET
            content = excluded.content,
            evidence_notes = excluded.evidence_notes,
            status = excluded.status
        """,
        (
            version_id,
            unit_id,
            version_no,
            str(payload.get("content", "")),
            str(payload.get("evidence_notes", "")),
            str(payload.get("status", "drafted")),
            now,
        ),
    )
    if "unit_status" in payload:
        conn.execute("UPDATE draft_units SET status = ?, updated_at = ? WHERE unit_id = ?", (str(payload["unit_status"]), now, unit_id))


def _submit_confirmation(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    now = utc_now()
    target_type = str(payload.get("target_type", "")).strip()
    target_id = str(payload.get("target_id", "1")).strip()
    if not target_type:
        raise ValueError("confirmation payload requires target_type")
    confirmation_id = str(payload.get("confirmation_id", f"{target_type}_{target_id}_{now}")).replace(":", "-")
    decision = str(payload.get("decision", "confirmed"))
    conn.execute(
        """
        INSERT INTO user_confirmations(confirmation_id, target_type, target_id, decision, notes, confirmed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(confirmation_id) DO UPDATE SET
            decision = excluded.decision,
            notes = excluded.notes,
            confirmed_at = excluded.confirmed_at
        """,
        (confirmation_id, target_type, target_id, decision, str(payload.get("notes", "")), now),
    )
    confirmed = 1 if decision in {"confirmed", "accepted", "approved"} else 0
    _apply_confirmation(conn, target_type, target_id, confirmed, now)


def _submit_reference_route(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    now = utc_now()
    route_id = str(payload.get("route_id", f"route_{now}")).replace(":", "-")
    conn.execute(
        """
        INSERT INTO reference_routes(route_id, domain, drafting_phase, paper_section, headings_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(route_id) DO UPDATE SET
            domain = excluded.domain,
            drafting_phase = excluded.drafting_phase,
            paper_section = excluded.paper_section,
            headings_json = excluded.headings_json
        """,
        (
            route_id,
            str(payload.get("domain", "")),
            str(payload.get("drafting_phase", "")),
            str(payload.get("paper_section", "")),
            json_dumps(payload.get("headings", [])),
            now,
        ),
    )


def _apply_confirmation(conn: sqlite3.Connection, target_type: str, target_id: str, confirmed: int, now: str) -> None:
    if target_type == "intake":
        conn.execute("UPDATE paper_domain_profile SET confirmed = ?, updated_at = ? WHERE id = 1", (confirmed, now))
    elif target_type == "macro_picture":
        conn.execute("UPDATE macro_picture SET confirmed = ?, updated_at = ? WHERE id = 1", (confirmed, now))
    elif target_type == "research_plan":
        conn.execute("UPDATE research_plan SET confirmed = ?, updated_at = ? WHERE id = 1", (confirmed, now))
    elif target_type == "outline":
        conn.execute("UPDATE outline_sections SET confirmed = ?, updated_at = ?", (confirmed, now))
    elif target_type == "outline_section":
        conn.execute("UPDATE outline_sections SET confirmed = ?, updated_at = ? WHERE section_id = ?", (confirmed, now, target_id))
    elif target_type == "section_writing_plan":
        conn.execute("UPDATE section_writing_plans SET confirmed = ?, updated_at = ? WHERE section_id = ?", (confirmed, now, target_id))
    elif target_type == "style_profile":
        conn.execute("UPDATE style_profile SET confirmed = ?, updated_at = ? WHERE id = 1", (confirmed, now))
    elif target_type == "draft_unit":
        conn.execute("UPDATE draft_units SET confirmed = ?, updated_at = ? WHERE unit_id = ?", (confirmed, now, target_id))


def _string_or_join(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value)
    return str(value)


def compute_gate(conn: sqlite3.Connection) -> dict[str, Any]:
    issues = validate_schema(conn)
    if issues:
        return _gate_payload(
            current_stage="invalid_schema",
            stage_gate="blocked",
            next_action="collect_intake",
            summary="Runtime database schema is invalid.",
            blockers=issues,
            repair_sequence=["Reinitialize the workspace or repair the missing tables before continuing."],
        )

    domain = fetch_one(conn, "SELECT * FROM paper_domain_profile WHERE id = 1")
    macro = fetch_one(conn, "SELECT * FROM macro_picture WHERE id = 1")
    plan = fetch_one(conn, "SELECT * FROM research_plan WHERE id = 1")
    outline_count = int(scalar(conn, "SELECT COUNT(*) FROM outline_sections") or 0)
    confirmed_outline_count = int(scalar(conn, "SELECT COUNT(*) FROM outline_sections WHERE confirmed = 1") or 0)
    missing_plan_sections = fetch_all(
        conn,
        """
        SELECT o.section_id, o.title
        FROM outline_sections o
        LEFT JOIN section_writing_plans p ON p.section_id = o.section_id AND p.confirmed = 1
        WHERE o.confirmed = 1 AND p.section_id IS NULL
        ORDER BY o.ordinal
        """,
    )
    evidence_plan_count = int(scalar(conn, "SELECT COUNT(*) FROM action_log WHERE stage = 'evidence_plan'") or 0)
    open_gaps = fetch_all(conn, "SELECT * FROM evidence_gaps WHERE status NOT IN ('closed', 'dismissed') ORDER BY severity DESC, gap_id")
    style = fetch_one(conn, "SELECT * FROM style_profile WHERE id = 1")
    missing_units = fetch_all(
        conn,
        """
        SELECT o.section_id, o.title
        FROM outline_sections o
        LEFT JOIN draft_units d ON d.section_id = o.section_id AND d.confirmed = 1
        WHERE o.confirmed = 1 AND d.unit_id IS NULL
        ORDER BY o.ordinal
        """,
    )
    units_without_draft = fetch_all(
        conn,
        """
        SELECT d.unit_id, d.section_id
        FROM draft_units d
        LEFT JOIN draft_versions v ON v.unit_id = d.unit_id
        WHERE d.confirmed = 1
        GROUP BY d.unit_id
        HAVING COUNT(v.version_id) = 0
        ORDER BY d.updated_at
        """,
    )
    revision_units = fetch_all(conn, "SELECT unit_id, section_id, blockers FROM draft_units WHERE status = 'revision_requested' ORDER BY updated_at")
    all_sections_drafted = outline_count > 0 and int(
        scalar(
            conn,
            """
            SELECT COUNT(DISTINCT d.section_id)
            FROM draft_units d
            JOIN draft_versions v ON v.unit_id = d.unit_id
            """,
        )
        or 0
    ) >= confirmed_outline_count
    final_confirmed = int(
        scalar(
            conn,
            "SELECT COUNT(*) FROM user_confirmations WHERE target_type = 'final_consistency' AND decision IN ('confirmed', 'accepted', 'approved')",
        )
        or 0
    )

    if domain is None or not domain["canonical_domain_name"] or not domain["confirmed"]:
        return _gate_payload("stage_1", "blocked", "collect_intake", "Collect and confirm intake/domain profile.", pending=["intake"])
    if macro is None or not macro["confirmed"]:
        return _gate_payload("stage_2", "blocked", "confirm_macro_picture", "Create or confirm the paper macro picture.", pending=["macro_picture"])
    if plan is None or not plan["confirmed"]:
        return _gate_payload("stage_3", "blocked", "confirm_research_plan", "Create or confirm the research plan.", pending=["research_plan"])
    if outline_count == 0 or confirmed_outline_count == 0:
        return _gate_payload("stage_4", "blocked", "confirm_outline", "Create and confirm the paper outline.", pending=["outline"])
    if missing_plan_sections:
        first = missing_plan_sections[0]
        return _gate_payload(
            "stage_5",
            "blocked",
            "confirm_section_writing_plan",
            f"Section writing plan required for `{first['section_id']}`.",
            pending=[f"section_writing_plan:{row['section_id']}" for row in missing_plan_sections],
        )
    if evidence_plan_count == 0:
        return _gate_payload("stage_6", "blocked", "plan_evidence", "Create the evidence plan before drafting.", pending=["evidence_plan"])
    if open_gaps:
        return _gate_payload(
            "stage_6",
            "blocked",
            "intake_evidence",
            "Open evidence gaps block drafting.",
            blockers=[f"{row['gap_id']}: {row['description']}" for row in open_gaps],
        )
    if style is None or not style["confirmed"]:
        return _gate_payload("stage_7", "blocked", "build_style_profile", "Build and confirm the user style profile.", pending=["style_profile"])
    if missing_units:
        first = missing_units[0]
        return _gate_payload(
            "stage_8",
            "blocked",
            "plan_section_outline",
            f"Confirmed section outline required for `{first['section_id']}`.",
            pending=[f"draft_unit:{row['section_id']}" for row in missing_units],
        )
    if units_without_draft:
        first = units_without_draft[0]
        return _gate_payload("stage_8", "ready", "draft_section", f"Draft confirmed unit `{first['unit_id']}`.")
    if revision_units:
        first = revision_units[0]
        return _gate_payload("stage_8", "ready", "revise_section", f"Revise unit `{first['unit_id']}`.", blockers=[str(first["blockers"])])
    if all_sections_drafted and not final_confirmed:
        return _gate_payload("stage_9", "ready", "final_consistency_check", "Run final consistency check and ask for confirmation.")
    if all_sections_drafted and final_confirmed:
        return _gate_payload("completed", "ready", "completed", "Paper drafting workspace is complete.")
    return _gate_payload("stage_8", "ready", "plan_section_outline", "Plan the next section outline.")


def _gate_payload(
    current_stage: str,
    stage_gate: str,
    next_action: str,
    summary: str,
    *,
    blockers: list[str] | None = None,
    pending: list[str] | None = None,
    repair_sequence: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "current_stage": current_stage,
        "stage_gate": stage_gate,
        "next_action": next_action,
        "status_summary": summary,
        "instruction_refs": _instruction_refs(next_action),
        "core_instruction": _core_instruction(next_action),
        "execution_note": "LLM performs semantic work; scripts validate, write SQLite state, gate, and render read-only views.",
        "next_action_payload_example": payload_example(next_action),
        "blockers": blockers or [],
        "pending_user_confirmations": pending or [],
        "repair_sequence": repair_sequence or [],
        "resume_packet": {
            "current_stage": current_stage,
            "next_action": next_action,
            "summary": summary,
            "must_not_forget": [
                "Do not continue from chat memory alone.",
                "Run gate-and-render after every formal write.",
                "Do not edit read-only Markdown views as state.",
            ],
        },
    }


def _instruction_refs(next_action: str) -> list[str]:
    mapping = {
        "collect_intake": ["paper-drafter/references/taxonomy.md"],
        "confirm_macro_picture": ["paper-drafter/references/general_framework.md"],
        "confirm_research_plan": ["paper-drafter/references/general_framework.md"],
        "confirm_outline": ["paper-drafter/references/general_framework.md"],
        "confirm_section_writing_plan": ["paper-drafter/references/general_framework.md"],
        "plan_evidence": ["paper-drafter/references/general_framework.md"],
        "intake_evidence": ["paper-drafter/references/general_framework.md"],
        "build_style_profile": ["paper-drafter/references/anti-ai_polishing_guide.md"],
        "plan_section_outline": ["paper-drafter/scripts/reference_guide.py nav"],
        "draft_section": ["paper-drafter/scripts/reference_guide.py nav"],
        "revise_section": ["paper-drafter/references/anti-ai_polishing_guide.md"],
        "final_consistency_check": ["paper-drafter/references/anti-ai_polishing_guide.md"],
    }
    return mapping.get(next_action, [])


def _core_instruction(next_action: str) -> str:
    return {
        "collect_intake": "Collect topic, domain, sources, language context, and constraints; submit `intake` payload only after confirmation.",
        "confirm_macro_picture": "Create or revise the macro picture and submit `macro_picture` after user confirmation.",
        "confirm_research_plan": "Create or revise the research plan and submit `research_plan` after user confirmation.",
        "confirm_outline": "Create a second-level outline and submit `outline` after user confirmation.",
        "confirm_section_writing_plan": "Create confirmed section writing plans for all confirmed outline sections.",
        "plan_evidence": "Create the evidence plan; record every gap that can block claims or sections.",
        "intake_evidence": "Ingest supplied evidence and close only the gaps actually satisfied.",
        "build_style_profile": "Build the style profile from user samples and rewrites; submit it after confirmation.",
        "plan_section_outline": "Prepare a section-level outline and submit `section_outline` after confirmation.",
        "draft_section": "Draft the next confirmed unit from DB state and evidence; submit `section_draft`.",
        "revise_section": "Revise the section draft according to blockers and submit a new `section_draft` version.",
        "final_consistency_check": "Check consistency across research plan, evidence, style, and drafts; record final confirmation when accepted.",
        "completed": "No further required action.",
    }.get(next_action, "Run gate-and-render and follow the returned next_action.")


def payload_example(next_action: str) -> dict[str, Any]:
    examples: dict[str, dict[str, Any]] = {
        "collect_intake": {
            "stage": "intake",
            "topic": "string",
            "canonical_domain_name": "computational-algorithm-data-driven",
            "domain_label": "计算 / 算法 / 数据驱动型论文",
            "research_area": "string",
            "target_venue": "string",
            "constraints": ["string"],
            "input_sources": [{"source_id": "source_001", "source_type": "note", "label": "string", "summary": "string"}],
            "confirmed": True,
        },
        "confirm_macro_picture": {"stage": "macro_picture", "research_question": "string", "gap": "string", "confirmed": True},
        "confirm_research_plan": {"stage": "research_plan", "objectives": "string", "novelty": "string", "confirmed": True},
        "confirm_outline": {
            "stage": "outline",
            "confirmed": True,
            "sections": [{"section_id": "introduction", "ordinal": 1, "level": 1, "title": "Introduction", "confirmed": True}],
        },
        "confirm_section_writing_plan": {
            "stage": "section_writing_plan",
            "section_id": "introduction",
            "content_logic": "string",
            "key_claims": "string",
            "confirmed": True,
        },
        "plan_evidence": {"stage": "evidence_plan", "gaps": [{"gap_id": "gap_001", "description": "string", "status": "open"}]},
        "intake_evidence": {
            "stage": "evidence_intake",
            "items": [{"evidence_id": "evidence_001", "evidence_type": "result", "label": "string"}],
            "close_gaps": [{"gap_id": "gap_001", "status": "closed"}],
        },
        "build_style_profile": {"stage": "style_profile", "summary": "string", "do_rules": ["string"], "dont_rules": ["string"], "confirmed": True},
        "plan_section_outline": {"stage": "section_outline", "section_id": "introduction", "outline": "string", "confirmed": True},
        "draft_section": {"stage": "section_draft", "unit_id": "introduction", "content": "string", "evidence_notes": "string"},
        "revise_section": {"stage": "section_draft", "unit_id": "introduction", "content": "string", "status": "revised"},
        "final_consistency_check": {"stage": "confirmation", "target_type": "final_consistency", "target_id": "1", "decision": "confirmed"},
    }
    return examples.get(next_action, {})


def update_workflow_state(conn: sqlite3.Connection, gate: dict[str, Any]) -> None:
    next_action = str(gate["next_action"])
    if next_action not in ALLOWED_NEXT_ACTIONS:
        raise ValueError(f"invalid next_action computed: {next_action}")
    conn.execute(
        """
        UPDATE workflow_state
        SET current_stage = ?, stage_gate = ?, next_action = ?, status_summary = ?, updated_at = ?
        WHERE id = 1
        """,
        (gate["current_stage"], gate["stage_gate"], next_action, gate["status_summary"], utc_now()),
    )
    conn.commit()


def render_workspace(conn: sqlite3.Connection, artifact_root: Path, gate: dict[str, Any]) -> None:
    paths = artifact_paths(artifact_root)
    artifact_root.mkdir(parents=True, exist_ok=True)
    paths["sections_dir"].mkdir(parents=True, exist_ok=True)
    _write(paths["agent_resume"], render_agent_resume(conn, gate))
    _write(paths["intake_domain"], render_intake_domain(conn))
    _write(paths["macro_picture"], render_singleton(conn, "macro_picture", "Macro Picture"))
    _write(paths["research_plan"], render_singleton(conn, "research_plan", "Research Plan"))
    _write(paths["outline"], render_outline(conn))
    _write(paths["section_writing_plan"], render_section_writing_plan(conn))
    _write(paths["evidence_board"], render_evidence_board(conn))
    _write(paths["style_profile"], render_singleton(conn, "style_profile", "Style Profile"))
    _write(paths["drafting_board"], render_drafting_board(conn))
    _write(paths["reference_route_board"], render_reference_routes(conn))
    _write(paths["manuscript_preview"], render_manuscript_preview(conn))
    render_section_views(conn, paths["sections_dir"])


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def render_agent_resume(conn: sqlite3.Connection, gate: dict[str, Any]) -> str:
    state = fetch_one(conn, "SELECT * FROM workflow_state WHERE id = 1")
    lines = [
        "# Agent Resume",
        "",
        "This is a read-only view rendered from `paper-drafter.db`.",
        "",
        "## Current Gate",
        "",
        f"- current_stage: `{gate['current_stage']}`",
        f"- stage_gate: `{gate['stage_gate']}`",
        f"- next_action: `{gate['next_action']}`",
        f"- status_summary: {gate['status_summary']}",
    ]
    if state:
        lines.append(f"- updated_at: {state['updated_at']}")
    lines.extend(["", "## Blockers"])
    lines.extend(_list_or_none(gate.get("blockers", [])))
    lines.extend(["", "## Pending Confirmations"])
    lines.extend(_list_or_none(gate.get("pending_user_confirmations", [])))
    lines.extend(["", "## Core Instruction", "", str(gate.get("core_instruction", ""))])
    return "\n".join(lines)


def render_intake_domain(conn: sqlite3.Connection) -> str:
    domain = fetch_one(conn, "SELECT * FROM paper_domain_profile WHERE id = 1")
    sources = fetch_all(conn, "SELECT * FROM input_sources ORDER BY source_id")
    lines = ["# Intake And Domain", "", "This is a read-only view rendered from `paper-drafter.db`.", ""]
    if domain is None:
        lines.append("_No intake submitted._")
    else:
        constraints = json_loads(domain["constraints_json"], [])
        lines.extend(
            [
                f"- topic: {domain['topic']}",
                f"- canonical_domain_name: `{domain['canonical_domain_name']}`",
                f"- domain_label: {domain['domain_label']}",
                f"- research_area: {domain['research_area']}",
                f"- target_venue: {domain['target_venue']}",
                f"- confirmed: {bool(domain['confirmed'])}",
                "- constraints:",
            ]
        )
        lines.extend(_list_or_none(constraints))
    lines.extend(["", "## Input Sources", ""])
    if not sources:
        lines.append("_No input sources recorded._")
    else:
        lines.append("| source_id | type | label | summary |")
        lines.append("|---|---|---|---|")
        for row in sources:
            lines.append(f"| `{row['source_id']}` | {row['source_type']} | {escape(row['label'])} | {escape(row['summary'])} |")
    return "\n".join(lines)


def render_singleton(conn: sqlite3.Connection, table: str, title: str) -> str:
    row = fetch_one(conn, f"SELECT * FROM {table} WHERE id = 1")
    lines = [f"# {title}", "", "This is a read-only view rendered from `paper-drafter.db`.", ""]
    if row is None:
        lines.append("_No record submitted._")
        return "\n".join(lines)
    for key in row.keys():
        if key == "id":
            continue
        value = row[key]
        if key == "confirmed":
            value = bool(value)
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def render_outline(conn: sqlite3.Connection) -> str:
    rows = fetch_all(conn, "SELECT * FROM outline_sections ORDER BY ordinal, section_id")
    lines = ["# Outline", "", "This is a read-only view rendered from `paper-drafter.db`.", ""]
    if not rows:
        lines.append("_No outline sections submitted._")
    else:
        lines.append("| section_id | level | title | role | confirmed |")
        lines.append("|---|---:|---|---|---|")
        for row in rows:
            lines.append(f"| `{row['section_id']}` | {row['level']} | {escape(row['title'])} | {escape(row['role'])} | {bool(row['confirmed'])} |")
    return "\n".join(lines)


def render_section_writing_plan(conn: sqlite3.Connection) -> str:
    rows = fetch_all(conn, "SELECT * FROM section_writing_plans ORDER BY section_id")
    lines = ["# Section Writing Plan", "", "This is a read-only view rendered from `paper-drafter.db`.", ""]
    if not rows:
        lines.append("_No section writing plans submitted._")
    else:
        for row in rows:
            lines.extend(
                [
                    f"## `{row['section_id']}`",
                    "",
                    f"- confirmed: {bool(row['confirmed'])}",
                    f"- content_logic: {row['content_logic']}",
                    f"- key_claims: {row['key_claims']}",
                    f"- materials: {row['materials']}",
                    f"- expected_visuals: {row['expected_visuals']}",
                    f"- dependencies: {row['dependencies']}",
                    "",
                ]
            )
    return "\n".join(lines)


def render_evidence_board(conn: sqlite3.Connection) -> str:
    gaps = fetch_all(conn, "SELECT * FROM evidence_gaps ORDER BY status, severity DESC, gap_id")
    items = fetch_all(conn, "SELECT * FROM evidence_items ORDER BY evidence_id")
    lines = ["# Evidence Board", "", "This is a read-only view rendered from `paper-drafter.db`.", "", "## Evidence Gaps", ""]
    if not gaps:
        lines.append("_No evidence gaps recorded._")
    else:
        lines.append("| gap_id | section | status | severity | description |")
        lines.append("|---|---|---|---|---|")
        for row in gaps:
            lines.append(f"| `{row['gap_id']}` | `{row['section_id']}` | {row['status']} | {row['severity']} | {escape(row['description'])} |")
    lines.extend(["", "## Evidence Items", ""])
    if not items:
        lines.append("_No evidence items recorded._")
    else:
        lines.append("| evidence_id | type | label | supports_section | status |")
        lines.append("|---|---|---|---|---|")
        for row in items:
            lines.append(f"| `{row['evidence_id']}` | {row['evidence_type']} | {escape(row['label'])} | `{row['supports_section']}` | {row['status']} |")
    return "\n".join(lines)


def render_drafting_board(conn: sqlite3.Connection) -> str:
    units = fetch_all(
        conn,
        """
        SELECT d.*, COUNT(v.version_id) AS version_count
        FROM draft_units d
        LEFT JOIN draft_versions v ON v.unit_id = d.unit_id
        GROUP BY d.unit_id
        ORDER BY d.section_id, d.unit_id
        """,
    )
    lines = ["# Drafting Board", "", "This is a read-only view rendered from `paper-drafter.db`.", ""]
    if not units:
        lines.append("_No draft units submitted._")
    else:
        lines.append("| unit_id | section_id | confirmed | status | versions | blockers |")
        lines.append("|---|---|---|---|---:|---|")
        for row in units:
            lines.append(f"| `{row['unit_id']}` | `{row['section_id']}` | {bool(row['confirmed'])} | {row['status']} | {row['version_count']} | {escape(row['blockers'])} |")
    return "\n".join(lines)


def render_reference_routes(conn: sqlite3.Connection) -> str:
    rows = fetch_all(conn, "SELECT * FROM reference_routes ORDER BY created_at DESC")
    lines = ["# Reference Route Board", "", "This is a read-only view rendered from `paper-drafter.db`.", ""]
    if not rows:
        lines.append("_No reference routes recorded._")
    else:
        for row in rows:
            lines.extend(
                [
                    f"## `{row['route_id']}`",
                    "",
                    f"- domain: `{row['domain']}`",
                    f"- drafting_phase: `{row['drafting_phase']}`",
                    f"- paper_section: `{row['paper_section']}`",
                    "- headings:",
                ]
            )
            headings = json_loads(row["headings_json"], [])
            lines.extend(_list_or_none(headings))
            lines.append("")
    return "\n".join(lines)


def render_manuscript_preview(conn: sqlite3.Connection) -> str:
    rows = fetch_all(
        conn,
        """
        SELECT o.ordinal, o.title, d.unit_id, v.content
        FROM outline_sections o
        LEFT JOIN draft_units d ON d.section_id = o.section_id
        LEFT JOIN draft_versions v ON v.unit_id = d.unit_id
            AND v.version_no = (SELECT MAX(version_no) FROM draft_versions WHERE unit_id = d.unit_id)
        WHERE o.confirmed = 1
        ORDER BY o.ordinal, d.unit_id
        """,
    )
    lines = ["# Manuscript Preview", "", "This is a read-only view rendered from `paper-drafter.db`.", ""]
    if not rows:
        lines.append("_No draftable sections available._")
    else:
        for row in rows:
            lines.extend([f"## {row['title']}", ""])
            lines.append(row["content"] or "_No draft version yet._")
            lines.append("")
    return "\n".join(lines)


def render_section_views(conn: sqlite3.Connection, sections_dir: Path) -> None:
    units = fetch_all(conn, "SELECT * FROM draft_units ORDER BY section_id, unit_id")
    for unit in units:
        safe_id = safe_filename(unit["unit_id"])
        _write(sections_dir / f"{safe_id}-outline.md", f"# {unit['unit_id']} Outline\n\nThis is a read-only view rendered from `paper-drafter.db`.\n\n{unit['outline'] or '_No outline content._'}")
        latest = fetch_one(
            conn,
            "SELECT * FROM draft_versions WHERE unit_id = ? ORDER BY version_no DESC LIMIT 1",
            (unit["unit_id"],),
        )
        content = latest["content"] if latest else "_No draft version yet._"
        _write(sections_dir / f"{safe_id}-draft.md", f"# {unit['unit_id']} Draft\n\nThis is a read-only view rendered from `paper-drafter.db`.\n\n{content}")


def safe_filename(value: str) -> str:
    keep = []
    for char in value:
        if char.isalnum() or char in {"-", "_"}:
            keep.append(char)
        else:
            keep.append("-")
    return "".join(keep).strip("-") or "section"


def escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def _list_or_none(values: list[Any]) -> list[str]:
    if not values:
        return ["- None"]
    return [f"- {value}" for value in values]

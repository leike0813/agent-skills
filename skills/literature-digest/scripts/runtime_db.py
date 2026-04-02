from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DB_FILENAME = "literature_digest.db"
TMP_DIRNAME = ".literature_digest_tmp"

REQUIRED_ARTIFACT_KEYS = {"digest_path", "references_path", "citation_analysis_path"}
OPTIONAL_ARTIFACT_KEYS = {"citation_analysis_report_path"}

DIGEST_SLOT_KEYS = (
    "tldr",
    "research_question_and_contributions",
    "method_highlights",
    "key_results",
    "limitations_and_reproducibility",
)

ALLOWED_STAGES = {
    "stage_0_bootstrap",
    "stage_1_normalize_source",
    "stage_2_outline_and_scopes",
    "stage_3_digest",
    "stage_4_references",
    "stage_5_citation",
    "stage_6_render_and_validate",
    "stage_7_completed",
}
ALLOWED_STAGE_GATES = {"blocked", "ready"}


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_db_path() -> Path:
    return Path.cwd() / TMP_DIRNAME / DB_FILENAME


def connect_db(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect_db(db_path) as connection:
        _create_schema(connection)
        _seed_runtime_run(connection)
        _seed_workflow_state(connection)
        connection.commit()


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS runtime_run (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS runtime_inputs (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS runtime_warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            warning TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS runtime_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            message TEXT NOT NULL,
            stage TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workflow_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            current_stage TEXT NOT NULL,
            current_substep TEXT NOT NULL,
            stage_gate TEXT NOT NULL,
            next_action TEXT NOT NULL,
            active_batch_kind TEXT,
            active_batch_index INTEGER,
            status_summary TEXT NOT NULL,
            last_error_code TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workflow_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            current_stage TEXT NOT NULL,
            current_substep TEXT NOT NULL,
            stage_gate TEXT NOT NULL,
            next_action TEXT NOT NULL,
            detail_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS action_receipts (
            action_name TEXT PRIMARY KEY,
            stage TEXT NOT NULL,
            status TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS source_documents (
            doc_key TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS outline_nodes (
            node_id TEXT PRIMARY KEY,
            heading_level INTEGER NOT NULL,
            title TEXT NOT NULL,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            parent_node_id TEXT,
            position INTEGER NOT NULL,
            metadata_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS section_scopes (
            scope_key TEXT PRIMARY KEY,
            section_title TEXT NOT NULL,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            metadata_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS digest_slots (
            slot_key TEXT PRIMARY KEY,
            content_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS digest_section_summaries (
            position INTEGER PRIMARY KEY,
            source_heading TEXT NOT NULL,
            items_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reference_entries (
            entry_index INTEGER PRIMARY KEY,
            raw TEXT NOT NULL,
            year INTEGER,
            metadata_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reference_batches (
            batch_kind TEXT NOT NULL,
            batch_index INTEGER NOT NULL,
            status TEXT NOT NULL,
            entry_start INTEGER NOT NULL,
            entry_end INTEGER NOT NULL,
            metadata_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (batch_kind, batch_index)
        );

        CREATE TABLE IF NOT EXISTS reference_items (
            ref_index INTEGER PRIMARY KEY,
            author_json TEXT NOT NULL,
            title TEXT NOT NULL,
            year INTEGER,
            raw TEXT NOT NULL,
            confidence REAL NOT NULL,
            metadata_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reference_parse_candidates (
            entry_index INTEGER NOT NULL,
            candidate_index INTEGER NOT NULL,
            pattern TEXT NOT NULL,
            author_text TEXT NOT NULL,
            author_candidates_json TEXT NOT NULL,
            title_candidate TEXT NOT NULL,
            container_candidate TEXT NOT NULL,
            year_candidate INTEGER,
            confidence REAL NOT NULL,
            metadata_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (entry_index, candidate_index)
        );

        CREATE TABLE IF NOT EXISTS citation_mentions (
            mention_id TEXT PRIMARY KEY,
            marker TEXT NOT NULL,
            style TEXT NOT NULL,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            snippet TEXT NOT NULL,
            ref_number_hint INTEGER,
            year_hint INTEGER,
            surname_hint TEXT,
            batch_index INTEGER,
            consumed_status TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS citation_batches (
            batch_kind TEXT NOT NULL,
            batch_index INTEGER NOT NULL,
            status TEXT NOT NULL,
            mention_start INTEGER NOT NULL,
            mention_end INTEGER NOT NULL,
            metadata_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (batch_kind, batch_index)
        );

        CREATE TABLE IF NOT EXISTS citation_mention_links (
            mention_id TEXT PRIMARY KEY,
            ref_index INTEGER,
            status TEXT NOT NULL,
            resolution_method TEXT NOT NULL,
            resolution_confidence REAL,
            evidence_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS citation_workset_items (
            ref_index INTEGER PRIMARY KEY,
            ref_number INTEGER,
            mention_count INTEGER NOT NULL,
            mentions_json TEXT NOT NULL,
            reference_snapshot_json TEXT NOT NULL,
            batch_hint INTEGER,
            workset_metadata_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS citation_items (
            ref_index INTEGER PRIMARY KEY,
            function TEXT NOT NULL,
            summary TEXT NOT NULL,
            confidence REAL NOT NULL,
            metadata_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS citation_unmapped_mentions (
            mention_id TEXT PRIMARY KEY,
            mention_json TEXT NOT NULL,
            reason TEXT NOT NULL,
            batch_index INTEGER,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS citation_summary (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            summary_text TEXT NOT NULL,
            basis_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS citation_timeline (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            timeline_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS artifact_registry (
            artifact_key TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            is_required INTEGER NOT NULL,
            media_type TEXT NOT NULL,
            source_table TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )


def _seed_runtime_run(connection: sqlite3.Connection) -> None:
    now = utc_now_iso()
    connection.execute(
        """
        INSERT INTO runtime_run (id, created_at, updated_at)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at
        """,
        (now, now),
    )


def _seed_workflow_state(connection: sqlite3.Connection) -> None:
    set_workflow_state(
        connection,
        current_stage="stage_0_bootstrap",
        current_substep="confirm_runtime_paths",
        stage_gate="ready",
        next_action="confirm_runtime_paths",
        status_summary="runtime database initialized; confirm runtime paths",
        active_batch_kind=None,
        active_batch_index=None,
        last_error_code=None,
    )


def _json_dump(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def set_runtime_input(connection: sqlite3.Connection, key: str, value: str) -> None:
    now = utc_now_iso()
    connection.execute(
        """
        INSERT INTO runtime_inputs (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key, value, now),
    )
    touch_runtime(connection)


def fetch_runtime_inputs(connection: sqlite3.Connection) -> dict[str, str]:
    rows = connection.execute("SELECT key, value FROM runtime_inputs").fetchall()
    return {str(row["key"]): str(row["value"]) for row in rows}


def add_runtime_warning(connection: sqlite3.Connection, warning: str) -> None:
    connection.execute(
        "INSERT INTO runtime_warnings (warning, created_at) VALUES (?, ?)",
        (warning, utc_now_iso()),
    )
    touch_runtime(connection)


def add_runtime_warning_once(connection: sqlite3.Connection, warning: str) -> None:
    row = connection.execute(
        "SELECT 1 FROM runtime_warnings WHERE warning = ? LIMIT 1",
        (warning,),
    ).fetchone()
    if row is None:
        add_runtime_warning(connection, warning)


def fetch_runtime_warnings(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute("SELECT warning FROM runtime_warnings ORDER BY id ASC").fetchall()
    return [str(row["warning"]) for row in rows]


def set_runtime_error(connection: sqlite3.Connection, code: str, message: str, stage: str) -> None:
    connection.execute(
        "INSERT INTO runtime_errors (code, message, stage, created_at) VALUES (?, ?, ?, ?)",
        (code, message, stage, utc_now_iso()),
    )
    set_workflow_state(
        connection,
        current_stage=stage,
        current_substep="error",
        stage_gate="blocked",
        next_action="repair_db_state",
        status_summary=message,
        last_error_code=code,
    )


def fetch_latest_error(connection: sqlite3.Connection) -> dict[str, str] | None:
    row = connection.execute(
        "SELECT code, message, stage FROM runtime_errors ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return {"code": str(row["code"]), "message": str(row["message"]), "stage": str(row["stage"])}


def set_workflow_state(
    connection: sqlite3.Connection,
    *,
    current_stage: str,
    current_substep: str,
    stage_gate: str,
    next_action: str,
    status_summary: str,
    active_batch_kind: str | None = None,
    active_batch_index: int | None = None,
    last_error_code: str | None = None,
) -> None:
    if current_stage not in ALLOWED_STAGES:
        raise ValueError(f"invalid stage: {current_stage}")
    if stage_gate not in ALLOWED_STAGE_GATES:
        raise ValueError(f"invalid stage_gate: {stage_gate}")
    now = utc_now_iso()
    connection.execute(
        """
        INSERT INTO workflow_state (
            id, current_stage, current_substep, stage_gate, next_action,
            active_batch_kind, active_batch_index, status_summary, last_error_code, updated_at
        )
        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            current_stage = excluded.current_stage,
            current_substep = excluded.current_substep,
            stage_gate = excluded.stage_gate,
            next_action = excluded.next_action,
            active_batch_kind = excluded.active_batch_kind,
            active_batch_index = excluded.active_batch_index,
            status_summary = excluded.status_summary,
            last_error_code = excluded.last_error_code,
            updated_at = excluded.updated_at
        """,
        (
            current_stage,
            current_substep,
            stage_gate,
            next_action,
            active_batch_kind,
            active_batch_index,
            status_summary,
            last_error_code,
            now,
        ),
    )
    append_workflow_event(
        connection,
        current_stage=current_stage,
        current_substep=current_substep,
        stage_gate=stage_gate,
        next_action=next_action,
        detail={
            "status_summary": status_summary,
            "active_batch_kind": active_batch_kind,
            "active_batch_index": active_batch_index,
            "last_error_code": last_error_code,
        },
    )
    touch_runtime(connection)


def append_workflow_event(
    connection: sqlite3.Connection,
    *,
    current_stage: str,
    current_substep: str,
    stage_gate: str,
    next_action: str,
    detail: dict[str, Any],
) -> None:
    connection.execute(
        """
        INSERT INTO workflow_events (
            current_stage, current_substep, stage_gate, next_action, detail_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (current_stage, current_substep, stage_gate, next_action, _json_dump(detail), utc_now_iso()),
    )


def fetch_workflow_state(connection: sqlite3.Connection) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM workflow_state WHERE id = 1").fetchone()
    if row is None:
        return None
    return dict(row)


def store_action_receipt(
    connection: sqlite3.Connection,
    *,
    action_name: str,
    stage: str,
    status: str = "succeeded",
    metadata: dict[str, Any] | None = None,
) -> None:
    now = utc_now_iso()
    connection.execute(
        """
        INSERT INTO action_receipts (action_name, stage, status, metadata_json, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(action_name) DO UPDATE SET
            stage = excluded.stage,
            status = excluded.status,
            metadata_json = excluded.metadata_json,
            updated_at = excluded.updated_at
        """,
        (action_name, stage, status, _json_dump(metadata or {}), now),
    )
    touch_runtime(connection)


def delete_action_receipts(connection: sqlite3.Connection, action_names: list[str]) -> None:
    if not action_names:
        return
    placeholders = ", ".join("?" for _ in action_names)
    connection.execute(
        f"DELETE FROM action_receipts WHERE action_name IN ({placeholders})",
        tuple(action_names),
    )
    touch_runtime(connection)


def fetch_action_receipts(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        "SELECT action_name, stage, status, metadata_json, updated_at FROM action_receipts ORDER BY action_name ASC"
    ).fetchall()
    receipts: dict[str, dict[str, Any]] = {}
    for row in rows:
        receipts[str(row["action_name"])] = {
            "action_name": str(row["action_name"]),
            "stage": str(row["stage"]),
            "status": str(row["status"]),
            "metadata": json.loads(str(row["metadata_json"])),
            "updated_at": str(row["updated_at"]),
        }
    return receipts


def has_action_receipt(connection: sqlite3.Connection, action_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM action_receipts WHERE action_name = ? LIMIT 1",
        (action_name,),
    ).fetchone()
    return row is not None


def store_source_document(
    connection: sqlite3.Connection,
    *,
    doc_key: str,
    content: str,
    metadata: dict[str, Any],
) -> None:
    now = utc_now_iso()
    connection.execute(
        """
        INSERT INTO source_documents (doc_key, content, metadata_json, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(doc_key) DO UPDATE SET
            content = excluded.content,
            metadata_json = excluded.metadata_json,
            updated_at = excluded.updated_at
        """,
        (doc_key, content, _json_dump(metadata), now),
    )
    touch_runtime(connection)


def fetch_source_document(connection: sqlite3.Connection, doc_key: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT doc_key, content, metadata_json FROM source_documents WHERE doc_key = ?",
        (doc_key,),
    ).fetchone()
    if row is None:
        return None
    return {
        "doc_key": str(row["doc_key"]),
        "content": str(row["content"]),
        "metadata": json.loads(str(row["metadata_json"])),
    }


def store_outline_nodes(connection: sqlite3.Connection, nodes: list[dict[str, Any]]) -> None:
    connection.execute("DELETE FROM outline_nodes")
    now = utc_now_iso()
    for position, node in enumerate(nodes, start=1):
        connection.execute(
            """
            INSERT INTO outline_nodes (
                node_id, heading_level, title, line_start, line_end, parent_node_id, position, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(node["node_id"]),
                int(node["heading_level"]),
                str(node["title"]),
                int(node["line_start"]),
                int(node["line_end"]),
                str(node["parent_node_id"]) if node.get("parent_node_id") is not None else None,
                position,
                _json_dump(dict(node.get("metadata", {}), updated_at=now)),
            ),
        )
    touch_runtime(connection)


def has_outline_nodes(connection: sqlite3.Connection) -> bool:
    row = connection.execute("SELECT COUNT(*) AS count FROM outline_nodes").fetchone()
    return row is not None and int(row["count"]) > 0


def store_section_scope(
    connection: sqlite3.Connection,
    *,
    scope_key: str,
    section_title: str,
    line_start: int,
    line_end: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    now = utc_now_iso()
    connection.execute(
        """
        INSERT INTO section_scopes (scope_key, section_title, line_start, line_end, metadata_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(scope_key) DO UPDATE SET
            section_title = excluded.section_title,
            line_start = excluded.line_start,
            line_end = excluded.line_end,
            metadata_json = excluded.metadata_json,
            updated_at = excluded.updated_at
        """,
        (scope_key, section_title, line_start, line_end, _json_dump(metadata or {}), now),
    )
    touch_runtime(connection)


def fetch_section_scope(connection: sqlite3.Connection, scope_key: str) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM section_scopes WHERE scope_key = ?", (scope_key,)).fetchone()
    if row is None:
        return None
    return {
        "scope_key": str(row["scope_key"]),
        "section_title": str(row["section_title"]),
        "line_start": int(row["line_start"]),
        "line_end": int(row["line_end"]),
        "metadata": json.loads(str(row["metadata_json"])),
    }


def _empty_digest_slots() -> dict[str, dict[str, Any]]:
    return {
        "tldr": {"paragraphs": []},
        "research_question_and_contributions": {"research_question": "", "contributions": []},
        "method_highlights": {"items": []},
        "key_results": {"items": []},
        "limitations_and_reproducibility": {"items": []},
    }


def store_digest_slots(connection: sqlite3.Connection, slots: dict[str, dict[str, Any]]) -> None:
    connection.execute("DELETE FROM digest_slots")
    now = utc_now_iso()
    for slot_key in DIGEST_SLOT_KEYS:
        connection.execute(
            """
            INSERT INTO digest_slots (slot_key, content_json, updated_at)
            VALUES (?, ?, ?)
            """,
            (slot_key, _json_dump(slots[slot_key]), now),
        )
    touch_runtime(connection)


def fetch_digest_slots(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    slots = _empty_digest_slots()
    rows = connection.execute("SELECT slot_key, content_json FROM digest_slots ORDER BY slot_key ASC").fetchall()
    for row in rows:
        slot_key = str(row["slot_key"])
        if slot_key in slots:
            slots[slot_key] = json.loads(str(row["content_json"]))
    return slots


def store_digest_section_summaries(connection: sqlite3.Connection, summaries: list[dict[str, Any]]) -> None:
    connection.execute("DELETE FROM digest_section_summaries")
    now = utc_now_iso()
    for index, summary in enumerate(summaries, start=1):
        position = int(summary.get("position", index))
        connection.execute(
            """
            INSERT INTO digest_section_summaries (position, source_heading, items_json, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (position, str(summary["source_heading"]), _json_dump(summary.get("items", [])), now),
        )
    touch_runtime(connection)


def fetch_digest_section_summaries(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT position, source_heading, items_json FROM digest_section_summaries ORDER BY position ASC"
    ).fetchall()
    return [
        {
            "position": int(row["position"]),
            "source_heading": str(row["source_heading"]),
            "items": json.loads(str(row["items_json"])),
        }
        for row in rows
    ]


def store_reference_entries(connection: sqlite3.Connection, entries: list[dict[str, Any]]) -> None:
    connection.execute("DELETE FROM reference_entries")
    now = utc_now_iso()
    for entry in entries:
        connection.execute(
            """
            INSERT INTO reference_entries (entry_index, raw, year, metadata_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                int(entry["entry_index"]),
                str(entry["raw"]),
                int(entry["year"]) if entry.get("year") is not None else None,
                _json_dump(entry.get("metadata", {})),
                now,
            ),
        )
    touch_runtime(connection)


def fetch_reference_entries(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT entry_index, raw, year, metadata_json FROM reference_entries ORDER BY entry_index ASC"
    ).fetchall()
    entries: list[dict[str, Any]] = []
    for row in rows:
        entry = json.loads(str(row["metadata_json"]))
        entry.update(
            {
                "entry_index": int(row["entry_index"]),
                "raw": str(row["raw"]),
                "year": int(row["year"]) if row["year"] is not None else None,
            }
        )
        entries.append(entry)
    return entries


def store_reference_batch(
    connection: sqlite3.Connection,
    *,
    batch_kind: str,
    batch_index: int,
    status: str,
    entry_start: int,
    entry_end: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    now = utc_now_iso()
    connection.execute(
        """
        INSERT INTO reference_batches (batch_kind, batch_index, status, entry_start, entry_end, metadata_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(batch_kind, batch_index) DO UPDATE SET
            status = excluded.status,
            entry_start = excluded.entry_start,
            entry_end = excluded.entry_end,
            metadata_json = excluded.metadata_json,
            updated_at = excluded.updated_at
        """,
        (batch_kind, batch_index, status, entry_start, entry_end, _json_dump(metadata or {}), now),
    )
    touch_runtime(connection)


def store_reference_parse_candidates(connection: sqlite3.Connection, candidates: list[dict[str, Any]]) -> None:
    connection.execute("DELETE FROM reference_parse_candidates")
    now = utc_now_iso()
    for candidate in candidates:
        connection.execute(
            """
            INSERT INTO reference_parse_candidates (
                entry_index, candidate_index, pattern, author_text, author_candidates_json,
                title_candidate, container_candidate, year_candidate, confidence, metadata_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(candidate["entry_index"]),
                int(candidate["candidate_index"]),
                str(candidate["pattern"]),
                str(candidate.get("author_text", "")),
                _json_dump(candidate.get("author_candidates", [])),
                str(candidate.get("title_candidate", "")),
                str(candidate.get("container_candidate", "")),
                int(candidate["year_candidate"]) if candidate.get("year_candidate") is not None else None,
                float(candidate.get("confidence", 0.0)),
                _json_dump(candidate.get("metadata", {})),
                now,
            ),
        )
    touch_runtime(connection)


def fetch_reference_parse_candidates(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT entry_index, candidate_index, pattern, author_text, author_candidates_json,
               title_candidate, container_candidate, year_candidate, confidence, metadata_json
        FROM reference_parse_candidates
        ORDER BY entry_index ASC, candidate_index ASC
        """
    ).fetchall()
    candidates: list[dict[str, Any]] = []
    for row in rows:
        metadata = json.loads(str(row["metadata_json"]))
        candidate = dict(metadata)
        candidate.update(
            {
                "entry_index": int(row["entry_index"]),
                "candidate_index": int(row["candidate_index"]),
                "pattern": str(row["pattern"]),
                "author_text": str(row["author_text"]),
                "author_candidates": json.loads(str(row["author_candidates_json"])),
                "title_candidate": str(row["title_candidate"]),
                "container_candidate": str(row["container_candidate"]),
                "year_candidate": int(row["year_candidate"]) if row["year_candidate"] is not None else None,
                "confidence": float(row["confidence"]),
                "metadata": metadata,
            }
        )
        candidates.append(candidate)
    return candidates


def store_reference_items(connection: sqlite3.Connection, items: list[dict[str, Any]]) -> None:
    connection.execute("DELETE FROM reference_items")
    now = utc_now_iso()
    for item in items:
        connection.execute(
            """
            INSERT INTO reference_items (
                ref_index, author_json, title, year, raw, confidence, metadata_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(item["ref_index"]),
                _json_dump(item.get("author", [])),
                str(item.get("title", "")),
                int(item["year"]) if item.get("year") is not None else None,
                str(item["raw"]),
                float(item["confidence"]),
                _json_dump(item.get("metadata", {})),
                now,
            ),
        )
    touch_runtime(connection)


def fetch_reference_items(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT ref_index, author_json, title, year, raw, confidence, metadata_json FROM reference_items ORDER BY ref_index ASC"
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = json.loads(str(row["metadata_json"]))
        item.update(
            {
                "ref_index": int(row["ref_index"]),
                "author": json.loads(str(row["author_json"])),
                "title": str(row["title"]),
                "year": int(row["year"]) if row["year"] is not None else None,
                "raw": str(row["raw"]),
                "confidence": float(row["confidence"]),
            }
        )
        items.append(item)
    return items


def store_citation_mentions(connection: sqlite3.Connection, mentions: list[dict[str, Any]]) -> None:
    connection.execute("DELETE FROM citation_mentions")
    now = utc_now_iso()
    for mention in mentions:
        connection.execute(
            """
            INSERT INTO citation_mentions (
                mention_id, marker, style, line_start, line_end, snippet, ref_number_hint,
                year_hint, surname_hint, batch_index, consumed_status, metadata_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(mention["mention_id"]),
                str(mention["marker"]),
                str(mention["style"]),
                int(mention["line_start"]),
                int(mention["line_end"]),
                str(mention["snippet"]),
                int(mention["ref_number_hint"]) if mention.get("ref_number_hint") is not None else None,
                int(mention["year_hint"]) if mention.get("year_hint") is not None else None,
                str(mention["surname_hint"]) if mention.get("surname_hint") is not None else None,
                int(mention["batch_index"]) if mention.get("batch_index") is not None else None,
                str(mention.get("consumed_status", "pending")),
                _json_dump({k: v for k, v in mention.items() if k not in {
                    "mention_id", "marker", "style", "line_start", "line_end", "snippet",
                    "ref_number_hint", "year_hint", "surname_hint", "batch_index", "consumed_status"
                }}),
                now,
            ),
        )
    touch_runtime(connection)


def count_citation_mentions(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT COUNT(*) AS count FROM citation_mentions").fetchone()
    return 0 if row is None else int(row["count"])


def fetch_citation_mentions(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT mention_id, marker, style, line_start, line_end, snippet, ref_number_hint,
               year_hint, surname_hint, batch_index, consumed_status, metadata_json
        FROM citation_mentions
        ORDER BY mention_id ASC
        """
    ).fetchall()
    mentions: list[dict[str, Any]] = []
    for row in rows:
        mention = json.loads(str(row["metadata_json"]))
        mention.update(
            {
                "mention_id": str(row["mention_id"]),
                "marker": str(row["marker"]),
                "style": str(row["style"]),
                "line_start": int(row["line_start"]),
                "line_end": int(row["line_end"]),
                "snippet": str(row["snippet"]),
                "ref_number_hint": int(row["ref_number_hint"]) if row["ref_number_hint"] is not None else None,
                "year_hint": int(row["year_hint"]) if row["year_hint"] is not None else None,
                "surname_hint": str(row["surname_hint"]) if row["surname_hint"] is not None else None,
                "batch_index": int(row["batch_index"]) if row["batch_index"] is not None else None,
                "consumed_status": str(row["consumed_status"]),
            }
        )
        mentions.append(mention)
    return mentions


def store_citation_batch(
    connection: sqlite3.Connection,
    *,
    batch_kind: str,
    batch_index: int,
    status: str,
    mention_start: int,
    mention_end: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    now = utc_now_iso()
    connection.execute(
        """
        INSERT INTO citation_batches (batch_kind, batch_index, status, mention_start, mention_end, metadata_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(batch_kind, batch_index) DO UPDATE SET
            status = excluded.status,
            mention_start = excluded.mention_start,
            mention_end = excluded.mention_end,
            metadata_json = excluded.metadata_json,
            updated_at = excluded.updated_at
        """,
        (batch_kind, batch_index, status, mention_start, mention_end, _json_dump(metadata or {}), now),
    )
    touch_runtime(connection)


def store_citation_mention_links(connection: sqlite3.Connection, links: list[dict[str, Any]]) -> None:
    connection.execute("DELETE FROM citation_mention_links")
    now = utc_now_iso()
    for link in links:
        connection.execute(
            """
            INSERT INTO citation_mention_links (
                mention_id, ref_index, status, resolution_method, resolution_confidence, evidence_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(link["mention_id"]),
                int(link["ref_index"]) if link.get("ref_index") is not None else None,
                str(link["status"]),
                str(link["resolution_method"]),
                float(link["resolution_confidence"]) if link.get("resolution_confidence") is not None else None,
                _json_dump(dict(link.get("evidence", {}))),
                now,
            ),
        )
    touch_runtime(connection)


def fetch_citation_mention_links(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT mention_id, ref_index, status, resolution_method, resolution_confidence, evidence_json
        FROM citation_mention_links
        ORDER BY mention_id ASC
        """
    ).fetchall()
    return [
        {
            "mention_id": str(row["mention_id"]),
            "ref_index": int(row["ref_index"]) if row["ref_index"] is not None else None,
            "status": str(row["status"]),
            "resolution_method": str(row["resolution_method"]),
            "resolution_confidence": float(row["resolution_confidence"]) if row["resolution_confidence"] is not None else None,
            "evidence": json.loads(str(row["evidence_json"])),
        }
        for row in rows
    ]


def store_citation_workset_items(connection: sqlite3.Connection, items: list[dict[str, Any]]) -> None:
    connection.execute("DELETE FROM citation_workset_items")
    now = utc_now_iso()
    for item in items:
        connection.execute(
            """
            INSERT INTO citation_workset_items (
                ref_index, ref_number, mention_count, mentions_json, reference_snapshot_json,
                batch_hint, workset_metadata_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(item["ref_index"]),
                int(item["ref_number"]) if item.get("ref_number") is not None else None,
                int(item["mention_count"]),
                _json_dump(item.get("mentions", [])),
                _json_dump(item.get("reference", {})),
                int(item["batch_hint"]) if item.get("batch_hint") is not None else None,
                _json_dump(dict(item.get("metadata", {}))),
                now,
            ),
        )
    touch_runtime(connection)


def fetch_citation_workset_items(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT ref_index, ref_number, mention_count, mentions_json, reference_snapshot_json, batch_hint, workset_metadata_json
        FROM citation_workset_items
        ORDER BY ref_index ASC
        """
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        metadata = json.loads(str(row["workset_metadata_json"]))
        metadata.update(
            {
                "ref_index": int(row["ref_index"]),
                "ref_number": int(row["ref_number"]) if row["ref_number"] is not None else None,
                "mention_count": int(row["mention_count"]),
                "mentions": json.loads(str(row["mentions_json"])),
                "reference": json.loads(str(row["reference_snapshot_json"])),
                "batch_hint": int(row["batch_hint"]) if row["batch_hint"] is not None else None,
            }
        )
        items.append(metadata)
    return items


def store_citation_items(connection: sqlite3.Connection, items: list[dict[str, Any]]) -> None:
    connection.execute("DELETE FROM citation_items")
    now = utc_now_iso()
    for item in items:
        connection.execute(
            """
            INSERT INTO citation_items (
                ref_index, function, summary, confidence, metadata_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(item["ref_index"]),
                str(item["function"]),
                str(item["summary"]),
                float(item["confidence"]),
                _json_dump({k: v for k, v in item.items() if k not in {
                    "ref_index", "function", "summary", "confidence"
                }}),
                now,
            ),
        )
    touch_runtime(connection)


def fetch_citation_items(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT ref_index, function, summary, confidence, metadata_json FROM citation_items ORDER BY ref_index ASC"
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = json.loads(str(row["metadata_json"]))
        item.update(
            {
                "ref_index": int(row["ref_index"]),
                "function": str(row["function"]),
                "summary": str(row["summary"]),
                "confidence": float(row["confidence"]),
            }
        )
        items.append(item)
    return items


def store_citation_unmapped_mentions(connection: sqlite3.Connection, mentions: list[dict[str, Any]]) -> None:
    connection.execute("DELETE FROM citation_unmapped_mentions")
    now = utc_now_iso()
    for mention in mentions:
        connection.execute(
            """
            INSERT INTO citation_unmapped_mentions (mention_id, mention_json, reason, batch_index, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                str(mention["mention_id"]),
                _json_dump(mention),
                str(mention.get("reason", "")),
                int(mention["batch_index"]) if mention.get("batch_index") is not None else None,
                now,
            ),
        )
    touch_runtime(connection)


def fetch_citation_unmapped_mentions(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT mention_json FROM citation_unmapped_mentions ORDER BY mention_id ASC"
    ).fetchall()
    return [json.loads(str(row["mention_json"])) for row in rows]


def store_citation_summary(connection: sqlite3.Connection, summary_text: str, basis: dict[str, Any] | None = None) -> None:
    now = utc_now_iso()
    connection.execute(
        """
        INSERT INTO citation_summary (id, summary_text, basis_json, updated_at)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            summary_text = excluded.summary_text,
            basis_json = excluded.basis_json,
            updated_at = excluded.updated_at
        """,
        (summary_text, _json_dump(basis or {}), now),
    )
    touch_runtime(connection)


def store_citation_timeline(connection: sqlite3.Connection, timeline: dict[str, Any]) -> None:
    now = utc_now_iso()
    connection.execute(
        """
        INSERT INTO citation_timeline (id, timeline_json, updated_at)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            timeline_json = excluded.timeline_json,
            updated_at = excluded.updated_at
        """,
        (_json_dump(timeline), now),
    )
    touch_runtime(connection)


def fetch_citation_summary(connection: sqlite3.Connection) -> dict[str, Any] | None:
    row = connection.execute("SELECT summary_text, basis_json FROM citation_summary WHERE id = 1").fetchone()
    if row is None:
        return None
    return {"summary": str(row["summary_text"]), "basis": json.loads(str(row["basis_json"]))}


def fetch_citation_timeline(connection: sqlite3.Connection) -> dict[str, Any] | None:
    row = connection.execute("SELECT timeline_json FROM citation_timeline WHERE id = 1").fetchone()
    if row is None:
        return None
    return json.loads(str(row["timeline_json"]))


def _author_year_label(reference: dict[str, Any]) -> str:
    authors = reference.get("author")
    first_author = ""
    if isinstance(authors, list) and authors:
        first_author = str(authors[0]).strip()
    year = reference.get("year")
    if first_author and year is not None:
        return f"{first_author}, {year}"
    title = str(reference.get("title", "")).strip()
    return title or "[unlabeled]"


def _citation_sort_key(item: dict[str, Any]) -> tuple[int, int, int]:
    mentions = item.get("mentions")
    if isinstance(mentions, list) and mentions:
        mention_positions: list[tuple[int, int]] = []
        for mention in mentions:
            if not isinstance(mention, dict):
                continue
            line_start = mention.get("line_start")
            line_end = mention.get("line_end")
            if isinstance(line_start, int) and isinstance(line_end, int):
                mention_positions.append((line_start, line_end))
        if mention_positions:
            mention_positions.sort()
            first = mention_positions[0]
            return first[0], first[1], int(item.get("ref_index", 0))
    return (10**9, 10**9, int(item.get("ref_index", 0)))


def _build_citation_label_map(items: list[dict[str, Any]]) -> dict[int, str]:
    label_map: dict[int, str] = {}
    ay_items = [item for item in items if item.get("ref_number") is None]
    ay_items.sort(key=_citation_sort_key)
    ay_counter = 1
    for item in items:
        ref_index = int(item["ref_index"])
        ref_number = item.get("ref_number")
        if ref_number is not None:
            label_map[ref_index] = f"[{ref_number}]"
        else:
            label_map[ref_index] = ""
    for item in ay_items:
        ref_index = int(item["ref_index"])
        label_map[ref_index] = f"[AY-{ay_counter}]"
        ay_counter += 1
    return label_map


def fetch_citation_payload(connection: sqlite3.Connection, report_md: str = "") -> dict[str, Any]:
    scope = fetch_section_scope(connection, "citation_scope") or {
        "section_title": "Introduction",
        "line_start": 0,
        "line_end": 0,
        "metadata": {},
    }
    scope_metadata = dict(scope.get("metadata", {}))
    semantics_items = {int(item["ref_index"]): item for item in fetch_citation_items(connection)}
    workset_items = fetch_citation_workset_items(connection)
    numeric_mentions = connection.execute(
        "SELECT COUNT(*) AS count FROM citation_mentions WHERE style = 'numeric'"
    ).fetchone()
    reference_numbering_anomalies = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM reference_items
        WHERE json_extract(metadata_json, '$.numbering.has_anomaly') = 1
        """
    ).fetchone()
    summary_row = fetch_citation_summary(connection)
    timeline_row = fetch_citation_timeline(connection) or {
        "early": {"summary": "", "ref_indexes": []},
        "mid": {"summary": "", "ref_indexes": []},
        "recent": {"summary": "", "ref_indexes": []},
    }

    items: list[dict[str, Any]] = []
    for workset in workset_items:
        ref_index = int(workset["ref_index"])
        semantics = semantics_items.get(ref_index)
        if semantics is None:
            continue
        item = dict(semantics)
        item.update(
            {
                "ref_index": ref_index,
                "ref_number": workset.get("ref_number"),
                "reference": dict(workset.get("reference", {})),
                "mentions": list(workset.get("mentions", [])),
            }
        )
        items.append(item)

    label_map = _build_citation_label_map(items)
    for item in items:
        reference = dict(item.get("reference", {}))
        item["citation_label"] = label_map.get(int(item["ref_index"]), "[unlabeled]")
        item["author_year_label"] = _author_year_label(reference)
        keywords = item.get("keywords")
        if not isinstance(keywords, list):
            item["keywords"] = []
        else:
            item["keywords"] = [str(keyword).strip() for keyword in keywords if str(keyword).strip()]

    covered_sections_val = scope_metadata.get("covered_sections", [scope["section_title"]])
    if isinstance(covered_sections_val, list):
        covered_sections = [str(item) for item in covered_sections_val]
    elif isinstance(covered_sections_val, str) and covered_sections_val.strip():
        covered_sections = [covered_sections_val.strip()]
    else:
        covered_sections = [str(scope["section_title"])]

    return {
        "meta": {
            "language": fetch_runtime_inputs(connection).get("language") or "zh-CN",
            "scope": {
                "section_title": scope["section_title"],
                "line_start": scope["line_start"],
                "line_end": scope["line_end"],
            },
            "scope_source": str(scope_metadata.get("scope_source", "db")),
            "scope_decision": {
                "selection_reason": str(scope_metadata.get("selection_reason", "")),
                "covered_sections": covered_sections,
                "fallback_from": scope_metadata.get("fallback_from"),
                "fallback_reason": str(scope_metadata.get("fallback_reason", "")),
            },
            "mapping_reliability": (
                "reduced"
                if int(reference_numbering_anomalies["count"]) > 0 and int(numeric_mentions["count"]) > 0
                else "normal"
            ),
        },
        "summary": "" if summary_row is None else str(summary_row["summary"]),
        "timeline": timeline_row,
        "items": items,
        "unmapped_mentions": fetch_citation_unmapped_mentions(connection),
        "report_md": report_md,
    }


def build_digest_render_context(connection: sqlite3.Connection) -> dict[str, Any]:
    inputs = fetch_runtime_inputs(connection)
    return {
        "language": inputs.get("language") or "zh-CN",
        "digest_slots": fetch_digest_slots(connection),
        "section_summaries": fetch_digest_section_summaries(connection),
    }


def build_references_render_context(connection: sqlite3.Connection) -> dict[str, Any]:
    return {"items": fetch_reference_items(connection)}


def _function_label(function_value: Any) -> str:
    normalized = str(function_value).strip().lower()
    mapping = {
        "background": "Background",
        "baseline": "Baseline",
        "contrast": "Contrast",
        "component": "Component",
        "dataset": "Dataset",
        "tooling": "Tooling",
        "historical": "Historical",
    }
    if normalized in mapping:
        return mapping[normalized]
    if not normalized:
        return "Uncategorized"
    return str(function_value).strip().replace("_", " ").title()


def build_citation_report_render_context(connection: sqlite3.Connection) -> dict[str, Any]:
    payload = fetch_citation_payload(connection, report_md="")
    summary_row = fetch_citation_summary(connection) or {"summary": "", "basis": {}}
    summary_basis = dict(summary_row.get("basis", {}))
    ordered_items: list[dict[str, Any]] = []
    grouped_lookup: dict[str, dict[str, Any]] = {}
    grouped_items: list[dict[str, Any]] = []

    for item in payload["items"]:
        reference = item["reference"]
        function_value = str(item.get("function", "")).strip()
        function_label = _function_label(function_value)
        report_item = {
            "citation_label": str(item.get("citation_label", "[unlabeled]")),
            "author_year_label": str(item.get("author_year_label", "")).strip(),
            "title": str(reference.get("title", "")).strip(),
            "keywords": list(item.get("keywords", [])),
            "summary": str(item.get("summary", "")).strip(),
            "function": function_value,
            "function_label": function_label,
            "ref_index": item.get("ref_index"),
            "ref_number": item.get("ref_number"),
        }
        ordered_items.append(report_item)
        group_key = function_value.lower() or "uncategorized"
        if group_key not in grouped_lookup:
            grouped_lookup[group_key] = {
                "function": function_value,
                "function_label": function_label,
                "items": [],
            }
            grouped_items.append(grouped_lookup[group_key])
        grouped_lookup[group_key]["items"].append(report_item)

    keyed_items = {int(item["ref_index"]): item for item in ordered_items if item.get("ref_index") is not None}
    key_references: list[dict[str, Any]] = []
    key_ref_indexes = summary_basis.get("key_ref_indexes", [])
    if isinstance(key_ref_indexes, list):
        for ref_index in key_ref_indexes:
            if not isinstance(ref_index, int):
                continue
            keyed_report_item: dict[str, Any] | None = keyed_items.get(ref_index)
            if keyed_report_item is None:
                continue
            reference_lookup = next((item for item in payload["items"] if int(item.get("ref_index", -1)) == ref_index), None)
            title = ""
            if reference_lookup is not None:
                title = str(dict(reference_lookup.get("reference", {})).get("title", "")).strip()
            key_references.append(
                {
                    "citation_label": keyed_report_item["citation_label"],
                    "author_year_label": keyed_report_item["author_year_label"],
                    "title": title,
                    "ref_index": keyed_report_item["ref_index"],
                    "ref_number": keyed_report_item["ref_number"],
                    "function_label": keyed_report_item["function_label"],
                }
            )

    unmapped_mentions: list[dict[str, Any]] = []
    for mention in payload["unmapped_mentions"]:
        unmapped_mentions.append(
            {
                "marker": str(mention.get("marker", "")),
                "reason": str(mention.get("reason", "")).strip(),
                "snippet": str(mention.get("snippet", "")).strip(),
                "line_start": mention.get("line_start"),
                "line_end": mention.get("line_end"),
            }
        )

    timeline_payload = payload.get("timeline", {})
    timeline_context: dict[str, Any] = {}
    keyed_reference_items = {int(item["ref_index"]): item for item in payload["items"] if item.get("ref_index") is not None}
    for bucket_key in ("early", "mid", "recent"):
        bucket = timeline_payload.get(bucket_key, {})
        bucket_summary = str(dict(bucket).get("summary", "")).strip()
        bucket_ref_indexes = dict(bucket).get("ref_indexes", [])
        refs: list[dict[str, Any]] = []
        if isinstance(bucket_ref_indexes, list):
            for ref_index in bucket_ref_indexes:
                if not isinstance(ref_index, int):
                    continue
                item = keyed_reference_items.get(ref_index)
                if item is None:
                    continue
                refs.append(
                    {
                        "citation_label": str(item.get("citation_label", "[unlabeled]")),
                        "author_year_label": str(item.get("author_year_label", "")).strip(),
                        "title": str(dict(item.get("reference", {})).get("title", "")).strip(),
                        "ref_index": ref_index,
                    }
                )
        timeline_context[bucket_key] = {
            "summary": bucket_summary,
            "ref_indexes": [ref for ref in bucket_ref_indexes if isinstance(ref, int)] if isinstance(bucket_ref_indexes, list) else [],
            "items": refs,
        }

    return {
        "language": payload["meta"]["language"],
        "scope": payload["meta"]["scope"],
        "summary": str(payload.get("summary", "")).strip(),
        "summary_basis": summary_basis,
        "key_references": key_references,
        "grouped_items": grouped_items,
        "ordered_items": ordered_items,
        "timeline": timeline_context,
        "unmapped_mentions": unmapped_mentions,
    }


def build_citation_render_context(connection: sqlite3.Connection, report_md: str) -> dict[str, Any]:
    return {"citation_analysis": fetch_citation_payload(connection, report_md=report_md)}


def register_artifact(
    connection: sqlite3.Connection,
    *,
    artifact_key: str,
    path: Path,
    is_required: bool,
    media_type: str,
    source_table: str,
) -> None:
    now = utc_now_iso()
    connection.execute(
        """
        INSERT INTO artifact_registry (artifact_key, path, is_required, media_type, source_table, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(artifact_key) DO UPDATE SET
            path = excluded.path,
            is_required = excluded.is_required,
            media_type = excluded.media_type,
            source_table = excluded.source_table,
            updated_at = excluded.updated_at
        """,
        (artifact_key, str(path.expanduser().resolve()), 1 if is_required else 0, media_type, source_table, now),
    )
    touch_runtime(connection)


def fetch_artifact_registry(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        "SELECT artifact_key, path, is_required, media_type, source_table, updated_at FROM artifact_registry ORDER BY artifact_key ASC"
    ).fetchall()
    return {
        str(row["artifact_key"]): {
            "path": str(row["path"]),
            "is_required": bool(row["is_required"]),
            "media_type": str(row["media_type"]),
            "source_table": str(row["source_table"]),
            "updated_at": str(row["updated_at"]),
        }
        for row in rows
    }


def build_public_output_payload(connection: sqlite3.Connection) -> dict[str, Any]:
    inputs = fetch_runtime_inputs(connection)
    artifacts = fetch_artifact_registry(connection)
    payload: dict[str, Any] = {
        "digest_path": str(Path(artifacts.get("digest_path", {}).get("path", "")).expanduser().resolve()) if artifacts.get("digest_path", {}).get("path", "") else "",
        "references_path": str(Path(artifacts.get("references_path", {}).get("path", "")).expanduser().resolve()) if artifacts.get("references_path", {}).get("path", "") else "",
        "citation_analysis_path": str(Path(artifacts.get("citation_analysis_path", {}).get("path", "")).expanduser().resolve()) if artifacts.get("citation_analysis_path", {}).get("path", "") else "",
        "provenance": {
            "generated_at": inputs.get("generated_at", ""),
            "input_hash": inputs.get("input_hash", ""),
            "model": inputs.get("model", ""),
        },
        "warnings": fetch_runtime_warnings(connection),
        "error": None,
    }
    if "citation_analysis_report_path" in artifacts:
        payload["citation_analysis_report_path"] = str(Path(artifacts["citation_analysis_report_path"]["path"]).expanduser().resolve())
    latest_error = fetch_latest_error(connection)
    if latest_error is not None:
        payload["error"] = {"code": latest_error["code"], "message": latest_error["message"]}
    return payload


def touch_runtime(connection: sqlite3.Connection) -> None:
    connection.execute("UPDATE runtime_run SET updated_at = ? WHERE id = 1", (utc_now_iso(),))

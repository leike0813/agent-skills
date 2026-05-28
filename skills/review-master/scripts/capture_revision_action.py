from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

from workspace_db import connect_db, ensure_runtime_schema_compatibility


ALLOWED_LOG_STATUS = {"draft", "completed", "cancelled"}
ALLOWED_OPERATOR_ROLE = {"agent", "user", "collaborative"}
ALLOWED_PLAN_STATUS = {"todo", "blocked", "in_progress", "completed", "dismissed"}
ALLOWED_CHANGE_TYPE = {"added", "revised", "deleted", "moved", "reframed", "format_only", "response_only"}


def emit(payload: dict[str, Any], exit_code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    return exit_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture one Agent-authored Stage 6 revision round into review-master runtime truth.")
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--payload", required=True, help="JSON object, or @path/to/payload.json, containing the Agent-authored revision log.")
    return parser.parse_args()


def load_payload(raw_payload: str) -> dict[str, Any]:
    if raw_payload.startswith("@"):
        payload_path = Path(raw_payload[1:]).expanduser()
        return json.loads(payload_path.read_text(encoding="utf-8"))
    return json.loads(raw_payload)


def list_field(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def string_value(payload: dict[str, Any], key: str, default: str = "") -> str:
    value = payload.get(key, default)
    if value is None:
        return default
    return str(value)


def validate_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    status = string_value(payload, "status", "completed")
    if status not in ALLOWED_LOG_STATUS:
        raise ValueError(f"status must be one of {sorted(ALLOWED_LOG_STATUS)}")
    operator_role = string_value(payload, "operator_role", "agent")
    if operator_role not in ALLOWED_OPERATOR_ROLE:
        raise ValueError(f"operator_role must be one of {sorted(ALLOWED_OPERATOR_ROLE)}")
    if not string_value(payload, "summary").strip():
        raise ValueError("summary is required")

    entries = list_field(payload, "entries")
    if status != "cancelled" and not entries:
        raise ValueError("completed or draft revision logs must include at least one semantic entry")
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"entries[{index}] must be an object")
        change_type = string_value(entry, "change_type")
        if change_type not in ALLOWED_CHANGE_TYPE:
            raise ValueError(f"entries[{index}].change_type must be one of {sorted(ALLOWED_CHANGE_TYPE)}")
        if not string_value(entry, "change_summary").strip():
            raise ValueError(f"entries[{index}].change_summary is required")

    for index, update in enumerate(list_field(payload, "plan_action_status_updates"), start=1):
        if not isinstance(update, dict):
            raise ValueError(f"plan_action_status_updates[{index}] must be an object")
        if not string_value(update, "plan_action_id").strip():
            raise ValueError(f"plan_action_status_updates[{index}].plan_action_id is required")
        status_value = string_value(update, "status")
        if status_value not in ALLOWED_PLAN_STATUS:
            raise ValueError(f"plan_action_status_updates[{index}].status must be one of {sorted(ALLOWED_PLAN_STATUS)}")


def insert_revision_log(connection: sqlite3.Connection, payload: dict[str, Any]) -> str:
    log_id = string_value(payload, "log_id") or f"log_{uuid.uuid4().hex[:12]}"
    created_at = string_value(payload, "created_at") or dt.datetime.now(dt.timezone.utc).isoformat()
    max_log_order = connection.execute("SELECT COALESCE(MAX(log_order), 0) FROM revision_action_logs").fetchone()[0]
    connection.execute(
        """
        INSERT INTO revision_action_logs (
            log_id, log_order, status, operator_role, summary, change_note, response_note, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            log_id,
            int(max_log_order) + 1,
            string_value(payload, "status", "completed"),
            string_value(payload, "operator_role", "agent"),
            string_value(payload, "summary"),
            string_value(payload, "change_note"),
            string_value(payload, "response_note"),
            created_at,
        ),
    )
    return log_id


def main() -> int:
    args = parse_args()
    artifact_root = Path(args.artifact_root).expanduser().resolve()
    db_path = artifact_root / "review-master.db"
    if not db_path.exists():
        return emit({"status": "error", "error": f"missing database: {db_path}"}, exit_code=1)
    try:
        payload = load_payload(args.payload)
        validate_payload(payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return emit({"status": "error", "error": str(exc)}, exit_code=1)

    try:
        with connect_db(db_path) as connection:
            ensure_runtime_schema_compatibility(connection)
            log_id = insert_revision_log(connection, payload)
            for plan_action_id in list_field(payload, "plan_action_ids"):
                connection.execute(
                    "INSERT INTO revision_action_log_plan_links (log_id, plan_action_id) VALUES (?, ?)",
                    (log_id, str(plan_action_id)),
                )
            for thread_id in list_field(payload, "thread_ids"):
                thread_id_text = str(thread_id)
                connection.execute(
                    "INSERT INTO revision_action_log_thread_links (log_id, thread_id) VALUES (?, ?)",
                    (log_id, thread_id_text),
                )
                next_link_order = connection.execute(
                    "SELECT COALESCE(MAX(link_order), 0) + 1 FROM response_thread_action_log_links WHERE thread_id = ?",
                    (thread_id_text,),
                ).fetchone()[0]
                connection.execute(
                    "INSERT OR REPLACE INTO response_thread_action_log_links (thread_id, log_id, link_order) VALUES (?, ?, ?)",
                    (thread_id_text, log_id, int(next_link_order)),
                )
            for index, entry in enumerate(list_field(payload, "entries"), start=1):
                connection.execute(
                    """
                    INSERT INTO revision_action_log_entries (
                        log_id, entry_order, target_file, target_locator, change_type,
                        change_summary, rationale, evidence_source, expected_response_use
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        log_id,
                        index,
                        string_value(entry, "target_file"),
                        string_value(entry, "target_locator"),
                        string_value(entry, "change_type"),
                        string_value(entry, "change_summary"),
                        string_value(entry, "rationale"),
                        string_value(entry, "evidence_source"),
                        string_value(entry, "expected_response_use"),
                    ),
                )
            for update in list_field(payload, "plan_action_status_updates"):
                cursor = connection.execute(
                    "UPDATE revision_plan_actions SET status = ? WHERE plan_action_id = ?",
                    (string_value(update, "status"), string_value(update, "plan_action_id")),
                )
                if cursor.rowcount == 0:
                    raise sqlite3.IntegrityError(f"unknown plan_action_id in status update: {string_value(update, 'plan_action_id')}")
            connection.execute(
                """
                INSERT INTO export_artifacts (artifact_name, artifact_status, output_path)
                VALUES ('working_manuscript', 'ready', ?)
                ON CONFLICT(artifact_name) DO UPDATE SET artifact_status = 'ready', output_path = excluded.output_path
                """,
                (string_value(payload, "working_manuscript_path", "manuscript-copies/working-manuscript"),),
            )
            connection.commit()
    except sqlite3.IntegrityError as exc:
        return emit({"status": "error", "error": f"integrity error: {exc}"}, exit_code=1)

    return emit(
        {
            "status": "ok",
            "log_id": log_id,
            "captured_entries": len(list_field(payload, "entries")),
            "linked_plan_actions": [str(value) for value in list_field(payload, "plan_action_ids")],
            "linked_threads": [str(value) for value in list_field(payload, "thread_ids")],
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())

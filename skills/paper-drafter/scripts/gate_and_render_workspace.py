#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from workspace_db import compute_gate, connect_db, db_path, render_workspace, update_workflow_state, validate_schema


def emit(payload: dict[str, object], exit_code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    return exit_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the gate-and-render core script for a DB-first paper-drafter workspace.")
    parser.add_argument("--artifact-root", required=True, help="Path to the runtime artifact workspace.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifact_root = Path(args.artifact_root).expanduser().resolve()
    if not db_path(artifact_root).exists():
        return emit(
            {
                "ok": False,
                "error": "workspace database not found; run init_artifact_workspace.py first",
                "artifact_root": str(artifact_root),
            },
            2,
        )

    conn = connect_db(artifact_root)
    try:
        schema_errors = validate_schema(conn)
        if schema_errors:
            gate = {
                "ok": False,
                "current_stage": "invalid_schema",
                "stage_gate": "blocked",
                "next_action": "collect_intake",
                "status_summary": "Runtime database schema is invalid.",
                "instruction_refs": [],
                "core_instruction": "Repair or reinitialize the SQLite workspace before continuing.",
                "execution_note": "No views were rendered because schema validation failed.",
                "next_action_payload_example": {},
                "blockers": schema_errors,
                "pending_user_confirmations": [],
                "repair_sequence": ["Restore the missing tables or re-run init on a clean artifact workspace."],
                "resume_packet": {"current_stage": "invalid_schema", "next_action": "collect_intake", "summary": "Schema repair required."},
            }
            return emit(gate, 2)
        gate = compute_gate(conn)
        update_workflow_state(conn, gate)
        render_workspace(conn, artifact_root, gate)
    except Exception as exc:
        return emit({"ok": False, "error": str(exc)}, 2)
    finally:
        conn.close()

    gate = {"ok": True, **gate}
    return emit(gate)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from workspace_db import ALLOWED_STAGES, compute_gate, connect_db, ensure_schema, render_workspace, submit_payload, update_workflow_state


def emit(payload: dict[str, object], exit_code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    return exit_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Submit one semantic stage payload into the paper-drafter SQLite runtime.")
    parser.add_argument("--artifact-root", required=True, help="Path to the runtime artifact workspace.")
    parser.add_argument("--stage", required=True, choices=sorted(ALLOWED_STAGES), help="Stage payload type.")
    parser.add_argument("--payload-file", required=True, help="UTF-8 JSON payload file.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifact_root = Path(args.artifact_root).expanduser().resolve()
    payload_path = Path(args.payload_file).expanduser().resolve()
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("payload root must be a JSON object")
    except Exception as exc:
        return emit({"ok": False, "error": f"invalid payload: {exc}"}, 2)

    conn = connect_db(artifact_root)
    try:
        ensure_schema(conn)
        submit_payload(conn, args.stage, payload)
        gate = compute_gate(conn)
        update_workflow_state(conn, gate)
        render_workspace(conn, artifact_root, gate)
    except Exception as exc:
        return emit({"ok": False, "error": str(exc)}, 2)
    finally:
        conn.close()

    return emit(
        {
            "ok": True,
            "stage": args.stage,
            "next_action": gate["next_action"],
            "stage_gate": gate["stage_gate"],
            "blockers": gate["blockers"],
            "pending_user_confirmations": gate["pending_user_confirmations"],
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from workspace_db import artifact_paths, compute_gate, connect_db, ensure_schema, render_workspace, update_workflow_state, upsert_runtime_context


def emit(payload: dict[str, object], exit_code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    return exit_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize a DB-first paper-drafter artifact workspace.")
    parser.add_argument("--artifact-root", required=True, help="Path to the runtime artifact workspace.")
    parser.add_argument("--document-language", required=True, help="Language used in the manuscript text.")
    parser.add_argument("--working-language", required=True, help="Language used for interaction and runtime views.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifact_root = Path(args.artifact_root).expanduser().resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    artifact_paths(artifact_root)["sections_dir"].mkdir(parents=True, exist_ok=True)

    conn = connect_db(artifact_root)
    try:
        ensure_schema(conn)
        upsert_runtime_context(conn, artifact_root, args.document_language, args.working_language)
        gate = compute_gate(conn)
        update_workflow_state(conn, gate)
        render_workspace(conn, artifact_root, gate)
    finally:
        conn.close()

    return emit(
        {
            "ok": True,
            "artifact_root": str(artifact_root),
            "database": str(artifact_root / "paper-drafter.db"),
            "next_action": gate["next_action"],
            "resume_view": str(artifact_root / "01-agent-resume.md"),
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())

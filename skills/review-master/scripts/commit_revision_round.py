from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def emit(payload: dict[str, Any], exit_code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    return exit_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Commit one revision round: capture audit state, then rerun gate-and-render.")
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--change-note", default="")
    parser.add_argument("--response-note", default="")
    parser.add_argument("--status", default="completed")
    parser.add_argument("--operator-role", default="collaborative")
    parser.add_argument("--plan-action-id", action="append", default=[])
    parser.add_argument("--thread-id", action="append", default=[])
    return parser.parse_args()


def run_json(script: Path, args: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, "-u", str(script), *args],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"{script.name} failed: {completed.stdout}\n{completed.stderr}")
    return json.loads(completed.stdout)


def main() -> int:
    args = parse_args()
    script_root = Path(__file__).resolve().parent
    capture_script = script_root / "capture_revision_action.py"
    gate_script = script_root / "gate_and_render_workspace.py"
    capture_args = [
        "--artifact-root",
        args.artifact_root,
        "--summary",
        args.summary,
        "--change-note",
        args.change_note,
        "--response-note",
        args.response_note,
        "--status",
        args.status,
        "--operator-role",
        args.operator_role,
    ]
    for value in args.plan_action_id:
        capture_args.extend(["--plan-action-id", value])
    for value in args.thread_id:
        capture_args.extend(["--thread-id", value])
    try:
        capture_payload = run_json(capture_script, capture_args)
        gate_payload = run_json(gate_script, ["--artifact-root", args.artifact_root])
    except RuntimeError as exc:
        return emit({"status": "error", "error": str(exc)}, exit_code=1)
    return emit(
        {
            "status": "ok",
            "capture": capture_payload,
            "gate": gate_payload,
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())

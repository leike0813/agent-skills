#!/usr/bin/env python3
"""Legacy Stage 1 intake wrapper for the DB-backed runtime."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from runtime_core import ACTIONS, perform_action


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deprecated wrapper. Use stage_runtime.py persist_intake_and_inventory."
    )
    parser.add_argument("--artifact-root", required=True, help="Artifact workspace root.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = perform_action(
            action=ACTIONS["intake"],
            artifact_root=Path(args.artifact_root),
        )
    except Exception as exc:  # pragma: no cover - CLI error path
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

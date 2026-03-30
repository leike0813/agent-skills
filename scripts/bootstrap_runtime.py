#!/usr/bin/env python3
"""Legacy bootstrap wrapper for the DB-backed runtime."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from runtime_core import ACTIONS, perform_action


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deprecated wrapper. Use stage_runtime.py bootstrap_runtime_db."
    )
    parser.add_argument("--source-path", required=True, help="Source manuscript file path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = perform_action(
            action=ACTIONS["bootstrap"],
            source_path=Path(args.source_path),
        )
    except Exception as exc:  # pragma: no cover - CLI error path
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Gate runtime entry for the SQLite SSOT workflow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from runtime_core import gate_from_artifact_root, gate_from_source_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect the paper-condenser runtime and return the only allowed next action."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--source-path", help="Source manuscript file path.")
    group.add_argument("--artifact-root", help="Existing runtime artifact root.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.source_path:
            result = gate_from_source_path(Path(args.source_path))
        else:
            result = gate_from_artifact_root(Path(args.artifact_root))
    except Exception as exc:  # pragma: no cover - CLI error path
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

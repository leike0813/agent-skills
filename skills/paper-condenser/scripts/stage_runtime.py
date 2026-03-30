#!/usr/bin/env python3
"""Stage write entry for the SQLite SSOT workflow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from runtime_core import perform_action, read_payload_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Persist a gated stage action into the paper-condenser runtime DB."
    )
    parser.add_argument("action", help="The gated runtime action to execute.")
    parser.add_argument("--artifact-root", help="Artifact root for an existing runtime.")
    parser.add_argument(
        "--source-path",
        help="Source manuscript path. Required for bootstrap_runtime_db.",
    )
    parser.add_argument(
        "--payload-file",
        help="JSON payload file for semantic stage writes.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = (
            read_payload_file(Path(args.payload_file))
            if args.payload_file
            else None
        )
        result = perform_action(
            action=args.action,
            artifact_root=Path(args.artifact_root) if args.artifact_root else None,
            source_path=Path(args.source_path) if args.source_path else None,
            payload=payload,
        )
    except Exception as exc:  # pragma: no cover - CLI error path
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

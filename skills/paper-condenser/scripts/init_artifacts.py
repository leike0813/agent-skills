#!/usr/bin/env python3
"""Deprecated legacy artifact initializer."""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "init_artifacts.py is deprecated in the Database SSOT & gate-driven runtime. "
        "Use gate_runtime.py and stage_runtime.py bootstrap_runtime_db instead.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

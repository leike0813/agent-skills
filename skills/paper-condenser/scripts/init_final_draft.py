#!/usr/bin/env python3
"""Deprecated legacy final-draft initializer."""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "init_final_draft.py is deprecated in the Database SSOT & gate-driven runtime. "
        "Use gate_runtime.py to obtain the next action, then complete section-loop drafting "
        "through prepare_section_drafting / persist_section_draft / approve_section_draft / "
        "persist_output_target / render_final_output_bundle.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Parse one Codex rollout file into a token-lean timeline for summarization.

Two modes:
  preview : locate one match and return a small snippet (writes nothing)
  full    : render the whole conversation timeline to <out>/timeline.md

Prints exactly one JSON object on stdout; diagnostics go to stderr.
"""

from __future__ import annotations

import argparse
import json
import mmap
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rollout  # noqa: E402


def _result(timeline_path: str = "", stats_path: str = "") -> dict:
    return {
        "timeline_path": timeline_path,
        "stats_path": stats_path,
        "layout": "full",
        "brief_tier": None,
        "thread_id": None,
        "turns": 0,
        "chars": 0,
        "truncated": False,
        "dropped_commentary": False,
        "omitted_turns": 0,
        "budget_exceeded": False,
        "human_messages": 0,
        "file_changes": 0,
        "commands": 0,
        "error": {},
    }


def run_preview(args: argparse.Namespace) -> dict:
    result = _result()
    path = args.rollout
    if not os.path.isfile(path):
        result["error"] = {"code": "rollout_missing", "message": "rollout file not found: %s" % path}
        return result
    patterns = rollout.query_patterns(args.query)
    best = None
    with open(path, "rb") as fh:
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            total, offsets = rollout.scan_matches(mm, patterns)
            if total == 0:
                result["error"] = {"code": "no_match", "message": "query not found in rollout"}
                return result
            for off in rollout.spread(offsets, 50):
                rec = rollout.parse_line(rollout.line_at(mm, off))
                hit = rollout.classify(rec, args.query) if rec else None
                if hit is None:
                    continue
                prio = rollout.ROLE_PRIORITY.get(hit["role"], 0)
                if best is None or prio > best[0]:
                    payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
                    best = (prio, {
                        "role": hit["role"],
                        "phase": hit["phase"],
                        "ordinal": rec.get("ordinal"),
                        "line": rollout.line_no(mm, off),
                        "turn_id": payload.get("turn_id"),
                        "timestamp": rec.get("timestamp"),
                        "snippet": rollout.snippet(hit["text"], args.query, args.preview_chars),
                    })
        finally:
            mm.close()
    if best is None:
        result["error"] = {"code": "no_match", "message": "query matched only records with no readable text"}
        return result
    result["thread_id"] = rollout.read_meta(path).get("id")
    result["preview"] = best[1]
    return result


def run_full(args: argparse.Namespace) -> dict:
    result = _result()
    path = args.rollout
    if not os.path.isfile(path):
        result["error"] = {"code": "rollout_missing", "message": "rollout file not found: %s" % path}
        return result

    opts = {
        "include_reasoning": args.include_reasoning,
        "include_command_output": args.include_command_output,
    }
    turns, stats = rollout.extract_turn_events(path, opts)
    if not turns:
        result["error"] = {"code": "empty_timeline", "message": "no renderable conversation events found"}
        return result

    budget = args.max_total_chars
    if budget is None:
        budget = (rollout.BRIEF_LIMITS if args.layout == "brief"
                  else rollout.DEFAULT_LIMITS)["max_total_chars"]
    if args.layout == "brief":
        timeline = rollout.render_brief(turns, stats, {"max_total_chars": budget})
        filename = "brief.md"
    else:
        timeline = rollout.render_timeline(turns, stats, {
            "max_total_chars": budget,
            "max_block_chars": args.max_block_chars,
            "user_chars": args.user_chars,
            "include_commentary": args.include_commentary,
        })
        filename = "timeline.md"

    out_dir = args.out or os.path.join(
        os.environ.get("TMPDIR", "/tmp"), "codex-salvage", str(stats.get("thread_id") or "unknown"))
    os.makedirs(out_dir, exist_ok=True)
    timeline_path = os.path.join(out_dir, filename)
    stats_path = os.path.join(out_dir, "stats.json")
    with open(timeline_path, "w", encoding="utf-8") as fh:
        fh.write(timeline)
    with open(stats_path, "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=2)

    result.update({
        "timeline_path": timeline_path,
        "stats_path": stats_path,
        "layout": args.layout,
        "brief_tier": stats.get("brief_tier"),
        "thread_id": stats.get("thread_id"),
        "turns": stats.get("turns", 0),
        "chars": stats.get("emitted_chars", 0),
        "truncated": bool(stats.get("truncated")),
        "dropped_commentary": bool(stats.get("dropped_commentary")),
        "omitted_turns": stats.get("omitted_turns", 0),
        "budget_exceeded": bool(stats.get("budget_exceeded")),
        "human_messages": stats.get("human_messages", 0),
        "file_changes": stats.get("files_changed", 0),
        "commands": stats.get("commands", 0),
    })
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Parse one Codex rollout file.")
    parser.add_argument("--rollout", required=True, help="path to a rollout-*.jsonl file")
    parser.add_argument("--preview", action="store_true", help="return one snippet instead of parsing")
    parser.add_argument("--query", default=None, help="required with --preview")
    parser.add_argument("--out", default=None, help="output directory for full mode")
    parser.add_argument("--layout", choices=("full", "brief"), default="full",
                        help="full: turn-by-turn timeline; brief: one compact digest")
    parser.add_argument("--preview-chars", type=int, default=600)
    parser.add_argument("--max-total-chars", type=int, default=None,
                        help="defaults to 150000 for full, 12000 for brief")
    parser.add_argument("--max-block-chars", type=int, default=rollout.DEFAULT_LIMITS["max_block_chars"])
    parser.add_argument("--user-chars", type=int, default=rollout.DEFAULT_LIMITS["user_chars"])
    parser.add_argument("--include-commentary", dest="include_commentary", action="store_true",
                        default=rollout.DEFAULT_LIMITS["include_commentary"])
    parser.add_argument("--no-commentary", dest="include_commentary", action="store_false")
    parser.add_argument("--include-reasoning", action="store_true", default=False)
    parser.add_argument("--include-command-output", action="store_true", default=False)
    args = parser.parse_args(argv)

    if args.preview:
        if not args.query:
            result = _result()
            result["error"] = {"code": "missing_query", "message": "--preview requires --query"}
        else:
            result = run_preview(args)
    else:
        result = run_full(args)

    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

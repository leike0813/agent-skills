#!/usr/bin/env python3
"""Exact-text search across local Codex rollout files.

Prints exactly one JSON object on stdout; diagnostics go to stderr.
"""

from __future__ import annotations

import argparse
import datetime
import json
import mmap
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rollout  # noqa: E402

SAMPLE_CAP = 5


def _iso(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _empty(query: str, root: str) -> dict:
    return {
        "query": query,
        "root": root,
        "scanned_files": 0,
        "elapsed_s": 0.0,
        "candidates": [],
        "truncated_candidates": 0,
        "excluded": {"subagent_files": 0, "noise_only_files": 0},
        "error": {},
    }


def build_result(args: argparse.Namespace) -> dict:
    root = rollout.sessions_root(args.root)
    result = _empty(args.query, root)
    started = time.time()

    if len(args.query) < 2:
        result["error"] = {"code": "query_too_short", "message": "query must be at least 2 characters"}
        return result
    if not os.path.isdir(root):
        result["error"] = {"code": "root_missing", "message": "sessions root not found: %s" % root}
        return result

    patterns = rollout.query_patterns(args.query)
    index = rollout.load_index(None)

    candidates = []
    excluded = result["excluded"]

    for path in rollout.iter_rollouts(root):
        result["scanned_files"] += 1
        try:
            with open(path, "rb") as fh:
                mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        except (OSError, ValueError):
            continue
        try:
            total, offsets = rollout.scan_matches(mm, patterns)
            if total == 0:
                continue
            meta = rollout.read_meta(path)
            if rollout.is_subagent(meta) and not args.include_subagents:
                excluded["subagent_files"] += 1
                continue

            roles = Counter()
            best = None
            noise = 0
            for off in rollout.spread(offsets, SAMPLE_CAP):
                rec = rollout.parse_line(rollout.line_at(mm, off))
                hit = rollout.classify(rec, args.query) if rec else None
                if hit is None:
                    hit = {"role": "noise", "phase": None, "text": "", "off": off, "rec": rec}
                else:
                    hit = dict(hit)
                    hit["off"] = off
                    hit["rec"] = rec
                roles[hit["role"]] += 1
                if hit["role"] == "noise":
                    noise += 1
                if best is None or rollout.ROLE_PRIORITY.get(hit["role"], 0) > rollout.ROLE_PRIORITY.get(best["role"], 0):
                    best = hit
            if best is None or best["role"] == "noise":
                excluded["noise_only_files"] += 1
                continue

            best_payload = (best["rec"] or {}).get("payload")
            best_payload = best_payload if isinstance(best_payload, dict) else {}
            st = os.stat(path)
            first_ts, last_ts = rollout.first_last_timestamp(path)
            line = rollout.line_no(mm, best["off"])
            candidates.append({
                "path": path,
                "thread_id": meta.get("id"),
                "session_id": meta.get("session_id"),
                "thread_name": index.get(meta.get("id")),
                "role": best["role"],
                "phase": best["phase"],
                "match_count": total,
                "match_count_by_role": dict(roles),
                "ordinal": (best["rec"] or {}).get("ordinal"),
                "line": line,
                "turn_id": best_payload.get("turn_id"),
                "timestamp": (best["rec"] or {}).get("timestamp"),
                "snippet": rollout.snippet(best["text"], args.query, args.snippet_chars),
                "cwd": meta.get("cwd"),
                "git": {"branch": (meta.get("git") or {}).get("branch"),
                        "commit_hash": (meta.get("git") or {}).get("commit_hash")},
                "cli_version": meta.get("cli_version"),
                "originator": meta.get("originator"),
                "size_bytes": st.st_size,
                "mtime": _iso(st.st_mtime),
                "start": first_ts,
                "end": last_ts,
                "human_messages": 0,
                "noise_matches": noise,
                "forked_from_id": meta.get("forked_from_id"),
            })
        finally:
            mm.close()

    if args.sort == "time":
        key = lambda c: (c["end"] or "", c["mtime"])
    elif args.sort == "size":
        key = lambda c: (c["size_bytes"], c["mtime"])
    else:
        key = lambda c: (rollout.ROLE_PRIORITY.get(c["role"], 0), c["match_count"], c["mtime"])
    candidates.sort(key=key, reverse=True)

    result["truncated_candidates"] = max(0, len(candidates) - args.limit)
    result["candidates"] = candidates[:args.limit]

    for cand in result["candidates"]:
        cand["human_messages"] = rollout.extract_turn_events(cand["path"], {})[1]["human_messages"]

    result["elapsed_s"] = round(time.time() - started, 3)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Search local Codex rollout files by exact text.")
    parser.add_argument("--query", required=True, help="exact text (a keyword or a quoted passage)")
    parser.add_argument("--root", default=None, help="sessions root; defaults to $CODEX_HOME/sessions")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--include-subagents", action="store_true")
    parser.add_argument("--snippet-chars", type=int, default=240)
    parser.add_argument("--sort", choices=("role", "time", "size"), default="role")
    args = parser.parse_args(argv)
    result = build_result(args)
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Enumerate every Codex session recorded against one workspace path.

Matches on `session_meta.cwd` equality and returns sessions ordered by
creation time, with the span of each session and of the whole set.

Prints exactly one JSON object on stdout; diagnostics go to stderr.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rollout  # noqa: E402


def _iso(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _duration_secs(start, end):
    if not start or not end:
        return None
    try:
        begin = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
        finish = datetime.datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return None
    secs = int((finish - begin).total_seconds())
    return secs if secs > 0 else None


def build_result(args: argparse.Namespace) -> dict:
    started = time.time()
    raw_target = args.target
    source = "argument" if raw_target else "cwd"
    target = os.path.normpath(os.path.abspath(os.path.expanduser(raw_target or os.getcwd())))
    root = rollout.sessions_root(args.root)

    result = {
        "target": target,
        "target_source": source,
        "root": root,
        "scanned_files": 0,
        "elapsed_s": 0.0,
        "sessions": [],
        "totals": {"sessions": 0, "bytes": 0, "duration_s": 0,
                   "span_start": None, "span_end": None},
        "excluded": {"subagent_files": 0, "other_cwd_files": 0},
        "error": {},
    }

    if not os.path.isdir(root):
        result["error"] = {"code": "root_missing", "message": "sessions root not found: %s" % root}
        return result

    index = rollout.load_index(None)
    sessions = []
    for path in rollout.iter_rollouts(root):
        result["scanned_files"] += 1
        meta = rollout.read_meta(path)
        if rollout.is_subagent(meta):
            result["excluded"]["subagent_files"] += 1
            continue
        if meta.get("cwd") != target:
            result["excluded"]["other_cwd_files"] += 1
            continue

        start = meta.get("timestamp")
        _first, end = rollout.first_last_timestamp(path)
        git = meta.get("git") or {}
        stat = os.stat(path)
        sessions.append({
            "path": path,
            "thread_id": meta.get("id"),
            "session_id": meta.get("session_id"),
            "thread_name": index.get(meta.get("id")),
            "cwd": meta.get("cwd"),
            "repo": git.get("repository_url"),
            "branch": git.get("branch"),
            "originator": meta.get("originator"),
            "cli_version": meta.get("cli_version"),
            "start": start,
            "end": end,
            "duration_s": _duration_secs(start, end),
            "duration": rollout.format_duration(start, end),
            "size_bytes": stat.st_size,
            "mtime": _iso(stat.st_mtime),
        })

    sessions.sort(key=lambda s: (s["start"] or "9999"))
    result["sessions"] = sessions
    result["totals"] = {
        "sessions": len(sessions),
        "bytes": sum(s["size_bytes"] for s in sessions),
        "duration_s": sum(s["duration_s"] for s in sessions if s["duration_s"]),
        "span_start": min((s["start"] for s in sessions if s["start"]), default=None),
        "span_end": max((s["end"] for s in sessions if s["end"]), default=None),
    }
    result["elapsed_s"] = round(time.time() - started, 3)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="List every Codex session recorded against one workspace path.")
    parser.add_argument("--target", default=None,
                        help="workspace path; defaults to the current working directory")
    parser.add_argument("--root", default=None,
                        help="sessions root; defaults to $CODEX_HOME/sessions")
    args = parser.parse_args(argv)
    sys.stdout.write(json.dumps(build_result(args), ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

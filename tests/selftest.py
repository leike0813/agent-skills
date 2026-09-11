#!/usr/bin/env python3
"""Self-check for codex-salvager scripts.

Builds synthetic rollouts covering both schema generations and asserts the
contracts the skill depends on. Stdlib only:  python3 tests/selftest.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
SEARCH = os.path.join(SCRIPTS, "search.py")
PARSE = os.path.join(SCRIPTS, "parse.py")

KEY_NEW = "SALVAGE_KEY_NEW"
KEY_OLD = "SALVAGE_KEY_OLD"
KEY_SUB = "SALVAGE_KEY_SUB"

checks = 0


def ok(condition, label):
    global checks
    assert condition, "FAILED: %s" % label
    checks += 1


def run(script, *args):
    proc = subprocess.run([sys.executable, script, *args], capture_output=True, text=True)
    assert proc.returncode == 0, "exit %s: %s" % (proc.returncode, proc.stderr[-2000:])
    return json.loads(proc.stdout)


def line(ordinal, rtype, payload, timestamp="2026-01-01T00:00:00.000Z"):
    return json.dumps({"timestamp": timestamp, "ordinal": ordinal, "type": rtype, "payload": payload},
                      ensure_ascii=False)


def write_rollout(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(rows) + "\n")


def build_fixtures(root):
    day = os.path.join(root, "2026", "01", "01")
    os.makedirs(day, exist_ok=True)

    # ---- old generation: shell_command + apply_patch, prompt precedes task_started
    old = [
        line(0, "session_meta", {
            "session_id": "11111111-1111-1111-1111-111111111111",
            "id": "11111111-1111-1111-1111-111111111111",
            "timestamp": "2026-01-01T00:00:00.000Z",
            "cwd": "/tmp/old-project", "originator": "codex_vscode", "cli_version": "0.78.0",
            "thread_source": "user", "git": {"branch": "main", "commit_hash": "abcdef1234567890"},
        }),
        line(1, "response_item", {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "# AGENTS.md instructions for /tmp/old-project\n\n<INSTRUCTIONS>\nbe nice"}]}),
        line(2, "response_item", {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "<environment_context>\n  <cwd>/tmp/old-project</cwd>\n</environment_context>"}]}),
        line(3, "response_item", {"type": "message", "role": "user", "content": [
            {"type": "input_text",
             "text": "# Context from my IDE setup:\n\n## Active file: a.tex\n\n## My request for Codex:\n"
                     "please inspect %s now" % KEY_OLD}]}),
        line(4, "event_msg", {"type": "task_started", "turn_id": "rollout-1", "started_at": 1}),
        line(5, "event_msg", {"type": "item_completed", "turn_id": "rollout-1", "item": {
            "type": "UserMessage", "id": "item-1", "content": [
                {"type": "text",
                 "text": "# Context from my IDE setup:\n\n## My request for Codex:\nplease inspect %s now" % KEY_OLD}]}}),
        line(6, "turn_context", {"cwd": "/tmp/old-project", "approval_policy": "never",
                                 "sandbox_policy": {"type": "danger-full-access"}, "model": "gpt-5.2",
                                 "effort": "medium", "summary": "auto"}),
        line(7, "response_item", {"type": "function_call", "name": "shell_command",
                                  "arguments": json.dumps({"command": "ls -la"}),
                                  "call_id": "call_a"}),
        line(8, "response_item", {"type": "function_call_output", "call_id": "call_a",
                                  "output": "boom\nExit code: 1"}),
        line(9, "response_item", {"type": "custom_tool_call", "name": "apply_patch", "call_id": "call_b",
                                  "input": "*** Begin Patch\n*** Add File: docs/a.md\n+hi\n*** End Patch"}),
        line(10, "event_msg", {"type": "item_completed", "turn_id": "rollout-1", "item": {
            "type": "AgentMessage", "id": "item-2", "content": [
                {"type": "Text", "text": "done with %s" % KEY_OLD}]}}),
        line(11, "response_item", {"type": "message", "role": "assistant",
                                   "content": [{"type": "output_text", "text": "done with %s" % KEY_OLD}]}),
        line(12, "event_msg", {"type": "task_complete", "turn_id": "rollout-1",
                               "last_agent_message": "done with %s" % KEY_OLD, "duration_ms": 12}),
        line(13, "response_item", {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "second request"}]}),
        line(14, "event_msg", {"type": "task_complete", "turn_id": "rollout-1", "duration_ms": 13}),
        line(15, "event_msg", {"type": "task_started", "turn_id": "rollout-2", "started_at": 2}),
        line(16, "response_item", {"type": "message", "role": "assistant",
                                   "content": [{"type": "output_text", "text": "second answer"}]}),
    ]

    # ---- new generation: item_completed trio + token_usage_record + compacted replay
    new = [
        line(0, "session_meta", {
            "session_id": "22222222-2222-2222-2222-222222222222",
            "id": "22222222-2222-2222-2222-222222222222",
            "timestamp": "2026-02-02T00:00:00.000Z",
            "cwd": "/tmp/new-project", "originator": "zed", "cli_version": "0.153.4",
            "thread_source": "user",
        }),
        line(1, "event_msg", {"type": "task_started", "turn_id": "t-1", "started_at": 1}),
        line(2, "response_item", {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "line one %s\nline two tail" % KEY_NEW}]}),
        line(3, "event_msg", {"type": "item_completed", "turn_id": "t-1", "item": {
            "type": "UserMessage", "id": "i-1", "content": [
                {"type": "text", "text": "line one %s\nline two tail" % KEY_NEW}]}}),
        line(4, "response_item", {"type": "message", "role": "assistant", "phase": "commentary",
                                  "content": [{"type": "output_text", "text": "thinking about %s" % KEY_NEW}]}),
        line(5, "event_msg", {"type": "item_completed", "turn_id": "t-1", "item": {
            "type": "AgentMessage", "id": "i-2", "content": [
                {"type": "Text", "text": "thinking about %s" % KEY_NEW}]}}),
        line(6, "response_item", {"type": "message", "role": "assistant", "phase": "final_answer",
                                  "content": [{"type": "output_text", "text": "final answer body"}]}),
        line(7, "event_msg", {"type": "item_completed", "turn_id": "t-1", "item": {
            "type": "Plan", "id": "i-3", "text": "## plan\ndo the thing"}}),
        line(8, "event_msg", {"type": "item_completed", "turn_id": "t-1", "item": {
            "type": "CommandExecution", "id": "e-1", "command": ["/usr/bin/zsh", "-lc", "make test"],
            "cwd": "file:///tmp/new-project", "status": "completed", "aggregated_output": "ok",
            "exit_code": 0, "duration": {"secs": 0, "nanos": 1}}}),
        line(9, "event_msg", {"type": "item_completed", "turn_id": "t-1", "item": {
            "type": "FileChange", "id": "e-2",
            "changes": {"/tmp/new-project/src/x.rs": {"type": "add", "content": "fn main() {}"}},
            "status": "completed", "stdout": "Success."}}),
        line(10, "token_usage_record", {"thread_id": "22222222-2222-2222-2222-222222222222",
                                        "turn_id": "t-1", "session_id": "22222222-2222-2222-2222-222222222222",
                                        "root_turn_id": "t-1", "response_id": "",
                                        "usage": {"total_tokens": 10}, "turn_token_usage": {"total_tokens": 10},
                                        "thread_token_usage": {"total_tokens": 99}}),
        line(11, "event_msg", {"type": "task_complete", "turn_id": "t-1",
                               "last_agent_message": "final answer body", "duration_ms": 5}),
        line(12, "compacted", {"message": "",
                               "replacement_history": [
                                   {"type": "message", "role": "user",
                                    "content": [{"type": "input_text", "text": "replayed %s" % KEY_NEW}]},
                                   {"type": "compaction", "encrypted_content": "gAAAAA"}],
                               "compaction_response_id": "c-1"}),
    ]

    # ---- subagent thread: must be excluded from search results
    sub = [
        line(0, "session_meta", {
            "session_id": "33333333-3333-3333-3333-333333333333",
            "id": "33333333-3333-3333-3333-333333333333",
            "parent_thread_id": "22222222-2222-2222-2222-222222222222",
            "timestamp": "2026-02-02T00:10:00.000Z", "cwd": "/tmp/new-project",
            "originator": "Codex Desktop", "cli_version": "0.153.4", "thread_source": "subagent",
            "source": {"subagent": {"thread_spawn": {"parent_thread_id":
                "22222222-2222-2222-2222-222222222222", "depth": 1, "agent_path": "/root/explore",
                "agent_nickname": "Pauli", "agent_role": None}}},
        }),
        line(1, "response_item", {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "explore %s" % KEY_SUB}]}),
    ]

    write_rollout(os.path.join(day, "rollout-2026-01-01T00-00-00-11111111-1111-1111-1111-111111111111.jsonl"), old)
    write_rollout(os.path.join(day, "rollout-2026-02-02T00-00-00-22222222-2222-2222-2222-222222222222.jsonl"), new)
    write_rollout(os.path.join(day, "rollout-2026-02-02T00-10-00-33333333-3333-3333-3333-333333333333.jsonl"), sub)
    return day


def main():
    tmp = tempfile.mkdtemp(prefix="codex-salvager-selftest-")
    try:
        day = build_fixtures(tmp)
        old_path = os.path.join(day, "rollout-2026-01-01T00-00-00-11111111-1111-1111-1111-111111111111.jsonl")
        new_path = os.path.join(day, "rollout-2026-02-02T00-00-00-22222222-2222-2222-2222-222222222222.jsonl")

        # 1. single candidate, user role, snippet keeps the real newline
        res = run(SEARCH, "--root", tmp, "--query", KEY_NEW)
        ok(res["error"] == {}, "search reports no error")
        ok(len(res["candidates"]) == 1, "search finds exactly one candidate")
        cand = res["candidates"][0]
        ok(cand["role"] == "user", "candidate role is user, got %r" % cand["role"])
        ok(KEY_NEW in cand["snippet"], "snippet contains the query")
        ok("\n" in cand["snippet"], "snippet preserves the newline inside the match")
        ok(cand["path"] == new_path, "candidate path is the new-generation file")

        # 2. subagent-only query is excluded and counted
        res = run(SEARCH, "--root", tmp, "--query", KEY_SUB)
        ok(res["candidates"] == [], "subagent-only query yields no candidates")
        ok(res["excluded"]["subagent_files"] == 1, "subagent file is counted as excluded")

        # 3. noise hits do not outrank the human hit; noise is still counted
        res = run(SEARCH, "--root", tmp, "--query", KEY_OLD)
        ok(len(res["candidates"]) == 1, "old file yields one candidate")
        ok(res["candidates"][0]["role"] == "user", "noise does not outrank the user hit")

        # 4. old-generation parse: injections stripped, commands and patches recovered
        out_old = os.path.join(tmp, "out_old")
        res = run(PARSE, "--rollout", old_path, "--out", out_old)
        ok(res["error"] == {}, "old parse reports no error")
        ok(res["turns"] == 2, "old parse splits two turns, got %s" % res["turns"])
        ok(res["file_changes"] >= 1, "old parse recovers apply_patch file changes")
        timeline = open(os.path.join(out_old, "timeline.md"), encoding="utf-8").read()
        ok(KEY_OLD in timeline, "timeline contains the human request")
        ok("### Turn actions" in timeline, "timeline has per-turn actions")
        ok("exit 1" in timeline, "failed command exit code is rendered")
        ok("A docs/a.md" in timeline, "apply_patch path and action are rendered")
        ok("# AGENTS.md" not in timeline, "AGENTS.md injection is stripped")
        ok("<environment_context>" not in timeline, "environment injection is stripped")
        ok("## My request for Codex:" not in timeline, "IDE wrapper is stripped")
        ok("### Assistant (reasoning)" not in timeline, "reasoning is excluded by default")
        ok("second request" in timeline, "second prompt lands in its own turn")

        # 5. new-generation parse: block kinds present, dual stream deduped, actions present
        out_new = os.path.join(tmp, "out_new")
        res = run(PARSE, "--rollout", new_path, "--out", out_new)
        ok(res["error"] == {}, "new parse reports no error")
        ok(res["turns"] == 1, "new parse yields one turn, got %s" % res["turns"])
        ok(res["commands"] == 1, "new parse counts the command")
        ok(res["file_changes"] == 1, "new parse counts the file change")
        timeline = open(os.path.join(out_new, "timeline.md"), encoding="utf-8").read()
        ok("### Assistant (commentary)" in timeline, "commentary block is rendered")
        ok("### Assistant (final)" in timeline, "final block is rendered")
        ok("### Plan" in timeline, "plan block is rendered")
        ok(timeline.count("thinking about %s" % KEY_NEW) == 1, "duplicated assistant text appears once")
        ok("replayed %s" % KEY_NEW not in timeline, "compaction replay is not treated as new content")
        ok("/tmp/new-project/src/x.rs" in timeline, "FileChange path is rendered")
        stats = json.load(open(os.path.join(out_new, "stats.json"), encoding="utf-8"))
        ok(stats["token_usage"]["total_tokens"] == 99, "thread token usage is captured")

        # 6. preview mode writes nothing
        ghost = os.path.join(tmp, "out_preview_ghost")
        res = run(PARSE, "--rollout", new_path, "--preview", "--query", KEY_NEW, "--out", ghost)
        ok(res["error"] == {}, "preview reports no error")
        ok(res["preview"]["role"] == "user", "preview picks the highest-priority role")
        ok("\n" in res["preview"]["snippet"], "preview snippet keeps the newline")
        ok(len(res["preview"]["snippet"]) <= 2 * 600 + 2, "preview snippet honours the width")
        ok(not os.path.exists(ghost), "preview writes no files")

        # 7. error contract: missing rollout, no match, short query, missing root
        res = run(PARSE, "--rollout", os.path.join(tmp, "nope.jsonl"), "--out", os.path.join(tmp, "out_x"))
        ok(res["error"]["code"] == "rollout_missing", "missing rollout reports rollout_missing")
        ok(res["timeline_path"] == "", "missing rollout returns an empty timeline path")
        res = run(PARSE, "--rollout", new_path, "--preview", "--query", "SALVAGE_KEY_ABSENT")
        ok(res["error"]["code"] == "no_match", "absent query reports no_match")
        res = run(SEARCH, "--root", tmp, "--query", "x")
        ok(res["error"]["code"] == "query_too_short", "one-char query is rejected")
        res = run(SEARCH, "--root", os.path.join(tmp, "missing"), "--query", KEY_NEW)
        ok(res["error"]["code"] == "root_missing", "absent root reports root_missing")
        ok(res["candidates"] == [], "absent root yields no candidates")

        print("OK %d assertions" % checks)
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

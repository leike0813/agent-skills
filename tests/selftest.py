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
WORKSPACE = os.path.join(SCRIPTS, "workspace.py")

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

    # ---- workspace-mode fixtures: two user threads in <tmp>/ws, one elsewhere
    ws = os.path.join(root, "ws")
    os.makedirs(ws, exist_ok=True)
    ws_a = [
        line(0, "session_meta", {
            "session_id": "44444444-4444-4444-4444-444444444444",
            "id": "44444444-4444-4444-4444-444444444444",
            "timestamp": "2026-03-01T10:00:00.000Z", "cwd": ws,
            "originator": "codex-tui", "cli_version": "0.153.4", "thread_source": "user",
        }),
        line(1, "event_msg", {"type": "task_started", "turn_id": "w-1", "started_at": 1},
             timestamp="2026-03-01T10:00:05.000Z"),
        line(2, "response_item", {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "add the workspace fixture"}]},
            timestamp="2026-03-01T10:00:06.000Z"),
        line(3, "response_item", {"type": "message", "role": "assistant", "phase": "final_answer",
                                  "content": [{"type": "output_text", "text": "fixture added"}]},
             timestamp="2026-03-01T12:00:00.000Z"),
        line(4, "event_msg", {"type": "item_completed", "turn_id": "w-1", "item": {
            "type": "CommandExecution", "id": "wc-1", "command": ["/usr/bin/zsh", "-lc", "make test"],
            "cwd": "file://" + ws, "status": "completed", "aggregated_output": "ok",
            "exit_code": 0, "duration": {"secs": 0, "nanos": 1}}},
            timestamp="2026-03-01T12:10:00.000Z"),
        line(5, "event_msg", {"type": "item_completed", "turn_id": "w-1", "item": {
            "type": "FileChange", "id": "wf-1",
            "changes": {os.path.join(ws, "src/a.rs"): {"type": "add", "content": "fn main() {}"}},
            "status": "completed", "stdout": "Success."}},
            timestamp="2026-03-01T12:30:00.000Z"),
    ]
    ws_b = [
        line(0, "session_meta", {
            "session_id": "55555555-5555-5555-5555-555555555555",
            "id": "55555555-5555-5555-5555-555555555555",
            "timestamp": "2026-03-02T08:00:00.000Z", "cwd": ws,
            "originator": "codex-tui", "cli_version": "0.153.4", "thread_source": "user",
        }),
        line(1, "event_msg", {"type": "task_started", "turn_id": "w-2", "started_at": 2},
             timestamp="2026-03-02T08:00:05.000Z"),
        line(2, "response_item", {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "run the failing command"}]},
            timestamp="2026-03-02T08:00:06.000Z"),
        line(3, "response_item", {"type": "message", "role": "assistant", "phase": "final_answer",
                                  "content": [{"type": "output_text", "text": "command failed"}]},
             timestamp="2026-03-02T08:20:00.000Z"),
        line(4, "event_msg", {"type": "item_completed", "turn_id": "w-2", "item": {
            "type": "CommandExecution", "id": "wc-2", "command": ["/usr/bin/zsh", "-lc", "make broken"],
            "cwd": "file://" + ws, "status": "completed", "aggregated_output": "boom",
            "exit_code": 1, "duration": {"secs": 0, "nanos": 1}}},
            timestamp="2026-03-02T08:45:00.000Z"),
    ]
    ws_other = [
        line(0, "session_meta", {
            "session_id": "66666666-6666-6666-6666-666666666666",
            "id": "66666666-6666-6666-6666-666666666666",
            "timestamp": "2026-03-03T09:00:00.000Z", "cwd": os.path.join(root, "elsewhere"),
            "originator": "codex-tui", "cli_version": "0.153.4", "thread_source": "user",
        }),
        line(1, "response_item", {"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": "elsewhere work"}]},
            timestamp="2026-03-03T09:30:00.000Z"),
    ]

    write_rollout(os.path.join(day, "rollout-2026-03-01T10-00-00-44444444-4444-4444-4444-444444444444.jsonl"), ws_a)
    write_rollout(os.path.join(day, "rollout-2026-03-02T08-00-00-55555555-5555-5555-5555-555555555555.jsonl"), ws_b)
    write_rollout(os.path.join(day, "rollout-2026-03-03T09-00-00-66666666-6666-6666-6666-666666666666.jsonl"), ws_other)
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

        # 8. workspace enumeration: exact cwd match, ordered by creation time
        ws = os.path.join(tmp, "ws")
        ws_a_path = os.path.join(day, "rollout-2026-03-01T10-00-00-44444444-4444-4444-4444-444444444444.jsonl")
        ws_b_path = os.path.join(day, "rollout-2026-03-02T08-00-00-55555555-5555-5555-5555-555555555555.jsonl")
        res = run(WORKSPACE, "--root", tmp, "--target", ws)
        ok(res["error"] == {}, "workspace enumeration reports no error")
        ok(res["totals"]["sessions"] == 2, "workspace finds two sessions, got %s" % res["totals"]["sessions"])
        names = [s["path"] for s in res["sessions"]]
        ok(names == [ws_a_path, ws_b_path], "workspace sessions are ordered by creation time")
        ok(res["sessions"][0]["duration"] == "2h30m", "first duration is 2h30m, got %r" % res["sessions"][0]["duration"])
        ok(res["sessions"][0]["duration_s"] == 9000, "first duration_s is 9000")
        ok(res["sessions"][1]["duration"] == "45m", "second duration is 45m, got %r" % res["sessions"][1]["duration"])
        ok(res["excluded"]["other_cwd_files"] >= 1, "other-cwd files are counted")
        ok(res["excluded"]["subagent_files"] >= 1, "subagent files are counted")
        ok(res["target_source"] == "argument", "explicit target is reported as an argument")

        # 8b. the brief header must agree with the workspace enumeration on the
        # same session's start/duration (both must use the creation time)
        out_agree = os.path.join(tmp, "out_agree")
        parsed = run(PARSE, "--rollout", ws_a_path, "--layout", "brief", "--out", out_agree)
        brief_head = open(parsed["timeline_path"], encoding="utf-8").read()
        ok("duration: 2h30m" in brief_head,
           "brief header duration matches the workspace enumeration")
        ok("span: 2026-03-01T10:00:00.000Z" in brief_head,
           "brief header start is the session creation time")

        # 9. workspace default target is the process cwd
        proc = subprocess.run([sys.executable, WORKSPACE, "--root", tmp], capture_output=True,
                              text=True, cwd=ws)
        ok(proc.returncode == 0, "workspace with default target exits 0")
        res = json.loads(proc.stdout)
        ok(res["target_source"] == "cwd", "default target is reported as cwd")
        ok(res["target"] == ws, "default target equals the working directory")

        # 10. a missing target is not an error; a missing root is
        res = run(WORKSPACE, "--root", tmp, "--target", os.path.join(tmp, "nowhere"))
        ok(res["sessions"] == [], "missing target yields no sessions")
        ok(res["error"] == {}, "missing target is not an error")
        res = run(WORKSPACE, "--root", os.path.join(tmp, "missing"), "--target", ws)
        ok(res["error"]["code"] == "root_missing", "workspace reports root_missing")
        ok(res["sessions"] == [], "root_missing yields no sessions")

        # 11. brief layout: compact digest, no turn detail
        out_brief = os.path.join(tmp, "out_brief")
        res = run(PARSE, "--rollout", ws_a_path, "--layout", "brief", "--out", out_brief)
        ok(res["error"] == {}, "brief parse reports no error")
        ok(res["layout"] == "brief", "brief parse reports layout=brief")
        ok(res["timeline_path"].endswith("brief.md"), "brief writes brief.md")
        ok(res["chars"] <= 12000, "brief honours the 12000 budget, got %s" % res["chars"])
        brief = open(res["timeline_path"], encoding="utf-8").read()
        for section in ("## User requests", "## Final answers", "## Files changed"):
            ok(section in brief, "brief contains %s" % section)
        ok("- A %s" % os.path.join(ws, "src/a.rs") in brief, "brief lists the added file")
        ok("### Assistant" not in brief, "brief has no turn-detail block headings")
        ok("### Turn actions" not in brief, "brief has no per-turn action section")
        ok("## Failed commands" not in brief, "brief omits the failed-command section when empty")
        ok(all("\n" not in l for l in brief.splitlines() if l.startswith("- [")),
           "brief request/answer lines are single-line")

        # 12. brief surfaces failed commands
        out_brief_b = os.path.join(tmp, "out_brief_b")
        res = run(PARSE, "--rollout", ws_b_path, "--layout", "brief", "--out", out_brief_b)
        brief_b = open(res["timeline_path"], encoding="utf-8").read()
        ok("## Failed commands" in brief_b, "brief shows the failed-command section")
        ok("exit 1" in brief_b, "brief shows the failing exit code")

        # 13. full layout is unchanged by default
        out_full = os.path.join(tmp, "out_full_a")
        res = run(PARSE, "--rollout", ws_a_path, "--out", out_full)
        ok(res["layout"] == "full", "default layout is full")
        ok(res["timeline_path"].endswith("timeline.md"), "full writes timeline.md")
        ok("### Turn actions" in open(res["timeline_path"], encoding="utf-8").read(),
           "full layout still renders turn actions")

        # 14. batching formula used by the workspace report
        def batches(n):
            size = min(8, max(5, -(-n // 24)))
            return size, -(-n // size)
        for n, want in ((1, (5, 1)), (5, (5, 1)), (6, (5, 2)), (22, (5, 5)),
                        (33, (5, 7)), (205, (8, 26))):
            ok(batches(n) == want, "batch formula for N=%d -> %s" % (n, want))

        print("OK %d assertions" % checks)
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

"""Shared rollout scanning/parsing layer for codex-salvager.

Only this module knows the on-disk rollout format. The CLIs (search.py,
parse.py) must not duplicate any of it.

Every claim about the format below was verified against the real corpus
(2095 files, cli 0.71.0 -> 0.153.4); see references/rollout-schema.md.
"""

from __future__ import annotations

import json
import mmap
import os
import re
from typing import Any, Dict, Iterator, List, Optional, Tuple

DEFAULT_CODEX_HOME = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")

# Higher number == more trustworthy hit. Used for candidate ranking.
ROLE_PRIORITY = {
    "noise": 0,
    "tool_output": 1,
    "tool_input": 2,
    "reasoning": 3,
    "assistant_commentary": 4,
    "plan": 5,
    "assistant_final": 6,
    "user": 7,
}

# role=user blocks starting with any of these are system injections, not human input.
INJECTED_PREFIXES = (
    "<environment_context",
    "<recommended_plugins",
    "<skill",
    "<subagent_notification",
    "<turn_aborted",
    "<user_instructions",
    "<plugins_instructions",
    "<apps_instructions",
    "<filesystem",
    "<workspace_roots",
    "<permission_profile",
    "# AGENTS.md instructions",
    "You are working inside Orca",
)

IDE_MARKER = "# Context from my IDE setup:"
IDE_REQUEST_MARKER = "## My request for Codex:"

SHELL_CALL_NAMES = {"shell_command", "exec_command", "exec", "local_shell"}
PATCH_CALL_NAMES = {"apply_patch"}

ITEM_TO_ROLE = {
    "UserMessage": "user",
    "AgentMessage": "assistant_final",
    "Plan": "plan",
    "Reasoning": "reasoning",
    "CommandExecution": "tool_output",
    "FunctionCallOutput": "tool_output",
    "McpToolCall": "tool_output",
    "FileChange": "tool_output",
    "WebSearch": "tool_input",
    "ImageView": "tool_input",
    "Extension": "tool_input",
    "SubAgentActivity": "noise",
    "CollabAgentToolCall": "noise",
    "ContextCompaction": "noise",
}

PATCH_FILE_RE = re.compile(r"^\*\*\* (Add|Update|Delete) File: (.+?)\s*$", re.M)
PATCH_MOVE_RE = re.compile(r"^\*\*\* Move to: (.+?)\s*$", re.M)
EXIT_CODE_RES = (
    re.compile(r"Process exited with code (-?\d+)"),
    re.compile(r"Exit code: (-?\d+)"),
)
PATCH_ACTION = {"Add": "A", "Update": "M", "Delete": "D"}


# --------------------------------------------------------------------------
# paths / enumeration
# --------------------------------------------------------------------------

def sessions_root(root: Optional[str] = None) -> str:
    """CODEX_HOME/sessions by default; an explicit root overrides it."""
    if root:
        return os.path.abspath(os.path.expanduser(root))
    return os.path.join(DEFAULT_CODEX_HOME, "sessions")


def iter_rollouts(root: str) -> Iterator[str]:
    """All rollout files under root, newest first."""
    found = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith(".jsonl"):
                found.append(os.path.join(dirpath, fn))
    found.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return iter(found)


def load_index(codex_home: Optional[str] = None) -> Dict[str, str]:
    """thread_id -> thread_name from <codex_home>/session_index.jsonl."""
    path = os.path.join(codex_home or DEFAULT_CODEX_HOME, "session_index.jsonl")
    index: Dict[str, str] = {}
    if not os.path.isfile(path):
        return index
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict) and rec.get("id"):
                    index[rec["id"]] = rec.get("thread_name")
    except OSError:
        return {}
    return index


# --------------------------------------------------------------------------
# record level
# --------------------------------------------------------------------------

def parse_line(ln: Any) -> Optional[Dict[str, Any]]:
    if isinstance(ln, (bytes, bytearray)):
        try:
            ln = bytes(ln).decode("utf-8", "replace")
        except Exception:
            return None
    try:
        rec = json.loads(ln)
    except Exception:
        return None
    return rec if isinstance(rec, dict) else None


def iter_records(path: str) -> Iterator[Dict[str, Any]]:
    with open(path, "rb") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            rec = parse_line(raw)
            if rec is not None:
                yield rec


def read_meta(path: str, cap: int = 5000) -> Dict[str, Any]:
    """Identity of the file itself: the session_meta with ordinal 0.

    Dual-meta files carry the parent thread's snapshot as ordinal 1; that one
    must never be used for identity.
    """
    first = None
    try:
        fh = open(path, "rb")
    except OSError:
        return {}
    with fh:
        for i, raw in enumerate(fh):
            if i >= cap:
                break
            if b'"session_meta"' not in raw:
                continue
            rec = parse_line(raw)
            if not rec or rec.get("type") != "session_meta":
                continue
            payload = rec.get("payload") or {}
            if first is None:
                first = payload
            if rec.get("ordinal") == 0:
                return payload
    return first or {}


def is_subagent(meta: Dict[str, Any]) -> bool:
    if not meta:
        return False
    if meta.get("thread_source") == "subagent":
        return True
    src = meta.get("source")
    if isinstance(src, dict) and "subagent" in src:
        return True
    return bool(meta.get("parent_thread_id"))


def meta_summary(meta: Dict[str, Any]) -> Dict[str, Any]:
    git = meta.get("git") or {}
    return {
        "thread_id": meta.get("id"),
        "session_id": meta.get("session_id"),
        "cwd": meta.get("cwd"),
        "originator": meta.get("originator"),
        "cli_version": meta.get("cli_version"),
        "git": {"branch": git.get("branch"), "commit_hash": git.get("commit_hash")},
        "forked_from_id": meta.get("forked_from_id"),
    }


# --------------------------------------------------------------------------
# query patterns
# --------------------------------------------------------------------------

def query_patterns(query: str) -> List[bytes]:
    """Raw-JSONL byte patterns for a query.

    Rollout text lives inside JSON strings, so a multi-line query is stored
    escaped; both the plain and the escaped form are searched.
    """
    raw = query.encode("utf-8")
    patterns = [raw]
    try:
        escaped = json.dumps(query, ensure_ascii=False)[1:-1].encode("utf-8")
    except Exception:
        escaped = raw
    if escaped != raw:
        patterns.append(escaped)
    seen = set()
    out = []
    for p in sorted(patterns, key=len, reverse=True):
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _str_patterns(query: str) -> List[str]:
    patterns = [query]
    try:
        escaped = json.dumps(query, ensure_ascii=False)[1:-1]
    except Exception:
        escaped = query
    if escaped != query:
        patterns.append(escaped)
    return [p for p in patterns if p]


def _contains(text: str, patterns: List[str]) -> bool:
    for p in patterns:
        if p in text:
            return True
    return False


def file_contains(path: str, needle: bytes) -> bool:
    """Fast presence check; used to detect a cli generation before parsing."""
    try:
        with open(path, "rb") as fh:
            mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
    except (OSError, ValueError):
        return False
    try:
        return mm.find(needle) >= 0
    finally:
        mm.close()


def spread(offsets: List[int], cap: int = 5) -> List[int]:
    """Up to `cap` offsets spread evenly across a sorted offset list.

    Even spreading keeps the sampled role representative instead of letting a
    cluster of tool output at the top of the file define the whole candidate.
    """
    if len(offsets) <= cap:
        return list(offsets)
    if cap <= 1:
        return offsets[:1]
    step = (len(offsets) - 1) / float(cap - 1)
    picked = []
    for i in range(cap):
        idx = int(round(i * step))
        if idx not in picked:
            picked.append(idx)
    return [offsets[i] for i in picked]


def scan_matches(mm, patterns: List[bytes], keep_cap: int = 5000) -> Tuple[int, List[int]]:
    """One pass over the file: (total match count, sorted offsets kept)."""
    total = 0
    kept = set()
    for p in patterns:
        if not p:
            continue
        pos = mm.find(p)
        while pos >= 0:
            total += 1
            if len(kept) < keep_cap:
                kept.add(pos)
            pos = mm.find(p, pos + 1)
    return total, sorted(kept)


def first_last_timestamp(path: str) -> Tuple[Optional[str], Optional[str]]:
    """First/last record timestamp, read from the head and tail only."""
    first = last = None
    try:
        with open(path, "rb") as fh:
            head = fh.readline()
            rec = parse_line(head)
            if rec and isinstance(rec.get("timestamp"), str):
                first = rec["timestamp"]
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            back = min(size, 1 << 16)
            fh.seek(size - back)
            chunk = fh.read(back)
    except OSError:
        return None, None
    for raw in reversed(chunk.split(b"\n")):
        if not raw.strip():
            continue
        rec = parse_line(raw)
        if rec and isinstance(rec.get("timestamp"), str):
            last = rec["timestamp"]
            break
    return first, last


def line_no(mm, offset: int) -> int:
    """1-based line number of a byte offset, counted in bounded chunks."""
    n = 0
    pos = 0
    step = 1 << 20
    while pos < offset:
        end = min(pos + step, offset)
        n += mm[pos:end].count(b"\n")
        pos = end
    return n + 1


def line_at(mm, offset: int) -> bytes:
    start = mm.rfind(b"\n", 0, offset) + 1
    end = mm.find(b"\n", offset)
    if end < 0:
        end = len(mm)
    return mm[start:end]


def as_text(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return value
    if value is None:
        return None
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


# --------------------------------------------------------------------------
# human input extraction
# --------------------------------------------------------------------------

def human_text(text: Any) -> Optional[str]:
    """Human request inside a role=user block, or None for injected noise."""
    if not isinstance(text, str):
        return None
    body = text
    stripped = body.lstrip()
    if stripped.startswith(IDE_MARKER):
        idx = body.find(IDE_REQUEST_MARKER)
        if idx < 0:
            return None
        body = body[idx + len(IDE_REQUEST_MARKER):]
        stripped = body.lstrip()
    for prefix in INJECTED_PREFIXES:
        if stripped.startswith(prefix):
            return None
    body = body.strip()
    return body or None


def item_texts(item: Dict[str, Any]) -> List[str]:
    out = []
    for c in item.get("content") or []:
        if isinstance(c, dict) and isinstance(c.get("text"), str):
            out.append(c["text"])
        elif isinstance(c, str):
            out.append(c)
    return out


def reasoning_texts(payload: Dict[str, Any]) -> List[str]:
    out = []
    for s in payload.get("summary") or []:
        if isinstance(s, dict) and isinstance(s.get("text"), str):
            out.append(s["text"])
    for s in payload.get("content") or []:
        if isinstance(s, dict) and isinstance(s.get("text"), str):
            out.append(s["text"])
        elif isinstance(s, str):
            out.append(s)
    return out


# --------------------------------------------------------------------------
# classify (single record, single query)
# --------------------------------------------------------------------------

def classify(rec: Dict[str, Any], query: str) -> Optional[Dict[str, Any]]:
    """Highest-priority match of `query` inside one record.

    Returns {"role", "phase", "text"} or None when the record does not match.
    """
    patterns = _str_patterns(query)
    best: Optional[Tuple[int, str, Optional[str], str]] = None

    def consider(role: str, phase: Optional[str], text: Any) -> None:
        nonlocal best
        if not isinstance(text, str) or not text:
            return
        if not _contains(text, patterns):
            return
        prio = ROLE_PRIORITY.get(role, 0)
        if best is None or prio > best[0]:
            best = (prio, role, phase, text)

    rtype = rec.get("type")
    p = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
    ptype = p.get("type")

    if rtype == "response_item":
        if ptype == "message":
            role = p.get("role")
            phase = p.get("phase")
            for c in p.get("content") or []:
                if not isinstance(c, dict):
                    continue
                text = c.get("text")
                if not isinstance(text, str):
                    continue
                if role == "user":
                    human = human_text(text)
                    consider("user", None, human)
                elif role == "assistant":
                    consider("assistant_commentary" if phase == "commentary" else "assistant_final", phase, text)
                else:
                    consider("noise", None, text)
        elif ptype == "reasoning":
            for text in reasoning_texts(p):
                consider("reasoning", None, text)
        elif ptype == "function_call":
            consider("tool_input", None, as_text(p.get("arguments")))
        elif ptype == "function_call_output":
            consider("tool_output", None, as_text(p.get("output")))
        elif ptype == "custom_tool_call":
            consider("tool_input", None, as_text(p.get("input")))
        elif ptype == "custom_tool_call_output":
            consider("tool_output", None, as_text(p.get("output")))
        elif ptype == "web_search_call":
            consider("tool_input", None, as_text(p.get("action")))
        elif ptype in ("tool_search_call", "tool_search_output"):
            consider("tool_input", None, as_text(p.get("arguments") or p.get("tools")))
        elif ptype == "agent_message":
            consider("noise", None, as_text(p.get("content")))
    elif rtype == "event_msg":
        if ptype == "item_completed":
            item = p.get("item") if isinstance(p.get("item"), dict) else {}
            itype = item.get("type")
            role = ITEM_TO_ROLE.get(itype, "noise")
            if itype == "UserMessage":
                for text in item_texts(item):
                    consider("user", None, human_text(text))
            elif itype == "AgentMessage":
                for text in item_texts(item):
                    consider("assistant_final", None, text)
            elif itype == "Plan":
                consider("plan", None, item.get("text"))
            elif itype == "CommandExecution":
                consider("tool_output", None, as_text(item.get("aggregated_output")))
                consider("tool_output", None, render_command(item.get("command")))
            elif itype == "FileChange":
                consider("tool_output", None, as_text(item.get("stdout")))
                consider("tool_output", None, as_text(item.get("changes")))
            elif itype == "McpToolCall":
                consider("tool_output", None, as_text(item.get("result")))
                consider("tool_input", None, as_text(item.get("arguments")))
            elif itype in ("WebSearch", "Extension"):
                consider("tool_input", None, as_text(item))
            elif itype == "FunctionCallOutput":
                consider("tool_output", None, as_text(item.get("output")))
        elif ptype == "task_complete":
            consider("assistant_final", "final_answer", p.get("last_agent_message"))
    elif rtype == "compacted":
        consider("noise", None, as_text(p.get("replacement_history")))
    elif rtype == "world_state":
        consider("noise", None, as_text(p.get("state")))
    elif rtype == "session_meta":
        consider("noise", None, as_text(p.get("base_instructions")))
    else:
        # turn_context / token_usage_record / inter_agent_communication_metadata
        consider("noise", None, as_text(p))

    if best is None:
        return None
    return {"role": best[1], "phase": best[2], "text": best[3]}


def snippet(text: str, query: str, width: int = 240) -> str:
    """`width` characters of context around the first match, newlines kept."""
    if not text:
        return ""
    idx = -1
    for p in _str_patterns(query):
        idx = text.find(p)
        if idx >= 0:
            matched = p
            break
    if idx < 0:
        return text[:width]
    half = max(1, width // 2)
    start = max(0, idx - half)
    end = min(len(text), idx + len(matched) + half)
    out = text[start:end]
    if start > 0:
        out = "…" + out
    if end < len(text):
        out = out + "…"
    return out


# --------------------------------------------------------------------------
# command / patch helpers
# --------------------------------------------------------------------------

def render_command(command: Any) -> Optional[str]:
    """Command as a single display string, unwrapping shell -lc wrappers."""
    if isinstance(command, str):
        return command.strip() or None
    if isinstance(command, list) and command:
        parts = [str(x) for x in command]
        if len(parts) >= 3 and parts[1] in ("-lc", "-c"):
            return parts[2].strip() or None
        return " ".join(parts).strip() or None
    return None


def command_from_payload(name: str, payload: Any) -> Optional[str]:
    """Command text from a function_call/custom_tool_call payload."""
    if not isinstance(name, str):
        return None
    data = payload
    if isinstance(data, str):
        text = data.strip()
        if text.startswith("{"):
            try:
                data = json.loads(text)
            except ValueError:
                data = None
        if not isinstance(data, dict):
            first = text.splitlines()[0] if text else ""
            return first.strip() or None
    if isinstance(data, dict):
        for key in ("command", "cmd"):
            value = data.get(key)
            text = render_command(value)
            if text:
                return text
    return None


def patch_changes_from_payload(payload: Any) -> List[Dict[str, str]]:
    """Paths + actions parsed out of an apply_patch body."""
    text = payload
    if isinstance(text, dict):
        text = text.get("input") or text.get("patch") or ""
    elif isinstance(text, str) and text.strip().startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if isinstance(data, dict):
            text = data.get("input") or data.get("patch") or text
    if not isinstance(text, str):
        return []
    out = []
    for match in PATCH_FILE_RE.finditer(text):
        out.append({"action": PATCH_ACTION.get(match.group(1), "M"), "path": match.group(2).strip()})
    for match in PATCH_MOVE_RE.finditer(text):
        out.append({"action": "M", "path": match.group(1).strip()})
    return out


def exit_code_from_output(output: Any) -> Optional[int]:
    if not isinstance(output, str):
        return None
    for rx in EXIT_CODE_RES:
        match = rx.search(output)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


# --------------------------------------------------------------------------
# turn extraction
# --------------------------------------------------------------------------

def _new_turn(turns: List[Dict[str, Any]], turn_id: Optional[str], started_at: Optional[str]) -> Dict[str, Any]:
    turn = {
        "index": len(turns) + 1,
        "turn_id": turn_id,
        "started_at": started_at,
        "duration_ms": None,
        "error": None,
        "user_blocks": [],
        "assistant_blocks": [],
        "plans": [],
        "commands": [],
        "tool_calls": [],
        "file_changes": [],
        "patch_changes": [],
        "_agent_msgs": [],
        "_seen_user": set(),
        "_seen_assistant": set(),
        "_last_agent_message": None,
        "closed": False,
    }
    turns.append(turn)
    return turn


def extract_turn_events(path: str, opts: Optional[Dict[str, Any]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Full-session timeline. Works on every cli generation in the corpus."""
    opts = dict(opts or {})
    include_reasoning = bool(opts.get("include_reasoning"))
    include_command_output = bool(opts.get("include_command_output"))

    meta = meta_summary(read_meta(path))
    stats: Dict[str, Any] = {
        "thread_id": meta.get("thread_id"),
        "session_id": meta.get("session_id"),
        "cwd": meta.get("cwd"),
        "originator": meta.get("originator"),
        "cli_version": meta.get("cli_version"),
        "git": meta.get("git") or {"branch": None, "commit_hash": None},
        "model": None,
        "effort": None,
        "start": None,
        "end": None,
        "turns": 0,
        "human_messages": 0,
        "files_changed": 0,
        "commands": 0,
        "commands_failed": 0,
        "token_usage": None,
    }

    turns: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    pending_calls: Dict[str, Dict[str, Any]] = {}
    buffered_users: List[str] = []
    saw_exec_item = False
    saw_filechange_item = False
    pairing = file_contains(path, b'"task_started"')
    current_ts: Optional[str] = None

    def has_payload(turn: Dict[str, Any]) -> bool:
        return bool(turn["user_blocks"] or turn["assistant_blocks"] or turn["plans"]
                    or turn["commands"] or turn["file_changes"] or turn["tool_calls"]
                    or turn["patch_changes"] or turn["_agent_msgs"])

    def open_turn(turn_id: Optional[str] = None, started_at: Optional[str] = None) -> Dict[str, Any]:
        nonlocal cur, buffered_users
        if cur is not None and not cur["closed"] and not has_payload(cur):
            cur["turn_id"] = turn_id if turn_id is not None else cur["turn_id"]
            cur["started_at"] = started_at if started_at is not None else cur["started_at"]
        else:
            cur = _new_turn(turns, turn_id, started_at if started_at is not None else current_ts)
        pending, buffered_users = buffered_users, []
        for text in pending:
            if text not in cur["_seen_user"]:
                cur["_seen_user"].add(text)
                cur["user_blocks"].append(text)
        return cur

    def ensure_turn() -> Dict[str, Any]:
        if cur is None or cur["closed"]:
            return open_turn()
        return cur

    def add_users(texts: List[Optional[str]]) -> None:
        nonlocal cur
        for text in texts:
            if not text:
                continue
            if cur is not None and text in cur["_seen_user"]:
                continue                      # same prompt seen again (dual stream)
            if pairing:
                if cur is not None and not cur["closed"]:
                    if not has_payload(cur):
                        cur["_seen_user"].add(text)
                        cur["user_blocks"].append(text)
                        continue
                    cur["closed"] = True      # a new prompt ends the previous turn
                # Older cli versions write the next prompt before its
                # task_started record; hold it for that turn.
                if text not in buffered_users:
                    buffered_users.append(text)
                continue
            turn = open_turn()
            turn["_seen_user"].add(text)
            turn["user_blocks"].append(text)

    def add_user(text: Optional[str]) -> None:
        add_users([text])

    def add_assistant(kind: str, text: Any) -> None:
        if not isinstance(text, str) or not text.strip():
            return
        turn = ensure_turn()
        key = text.strip()
        if key in turn["_seen_assistant"]:
            return
        turn["_seen_assistant"].add(key)
        turn["assistant_blocks"].append({"kind": kind, "text": text})

    def add_tool_call(name: Any, payload: Any, call_id: Any) -> None:
        turn = ensure_turn()
        if not isinstance(name, str):
            return
        if name in SHELL_CALL_NAMES:
            command = command_from_payload(name, payload)
            if command:
                entry = {"command": command, "exit_code": None, "output": None}
                turn["tool_calls"].append(entry)
                if isinstance(call_id, str):
                    pending_calls[call_id] = entry
        elif name in PATCH_CALL_NAMES:
            turn["patch_changes"].extend(patch_changes_from_payload(payload))

    def fill_call_output(call_id: Any, output: Any) -> None:
        if not isinstance(call_id, str):
            return
        entry = pending_calls.get(call_id)
        if entry is None:
            return
        entry["exit_code"] = exit_code_from_output(output)
        if include_command_output and isinstance(output, str):
            entry["output"] = output

    for rec in iter_records(path):
        ts = rec.get("timestamp")
        if isinstance(ts, str):
            current_ts = ts
            if stats["start"] is None:
                stats["start"] = ts
            stats["end"] = ts

        rtype = rec.get("type")
        p = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}

        if rtype == "turn_context":
            if stats["model"] is None:
                stats["model"] = p.get("model")
                stats["effort"] = p.get("effort")
            continue

        if rtype == "token_usage_record":
            usage = p.get("thread_token_usage") or p.get("usage")
            if isinstance(usage, dict):
                stats["token_usage"] = usage
            continue

        if rtype == "event_msg":
            ptype = p.get("type")
            if ptype == "task_started":
                open_turn(p.get("turn_id"), ts)
                continue
            if ptype == "turn_aborted":
                turn = cur if cur is not None else ensure_turn()
                if p.get("duration_ms") is not None:
                    turn["duration_ms"] = p.get("duration_ms")
                turn["closed"] = True
                continue
            if ptype == "task_complete":
                turn = cur if cur is not None else ensure_turn()
                if p.get("duration_ms") is not None:
                    turn["duration_ms"] = p.get("duration_ms")
                if p.get("error"):
                    turn["error"] = as_text(p.get("error"))
                last = p.get("last_agent_message")
                if isinstance(last, str) and last.strip():
                    turn["_last_agent_message"] = last
                turn["closed"] = True
                continue
            if ptype == "item_completed":
                item = p.get("item") if isinstance(p.get("item"), dict) else {}
                itype = item.get("type")
                if itype == "UserMessage":
                    for text in item_texts(item):
                        add_user(human_text(text))
                elif itype == "AgentMessage":
                    turn = ensure_turn()
                    for text in item_texts(item):
                        if text.strip():
                            turn["_agent_msgs"].append(text)
                elif itype == "Plan":
                    text = item.get("text")
                    turn = ensure_turn()
                    if isinstance(text, str) and text.strip() and text not in turn["plans"]:
                        turn["plans"].append(text)
                elif itype == "CommandExecution":
                    saw_exec_item = True
                    turn = ensure_turn()
                    exit_code = item.get("exit_code")
                    turn["commands"].append({
                        "command": render_command(item.get("command")),
                        "exit_code": exit_code if isinstance(exit_code, int) else None,
                        "output": item.get("aggregated_output") if include_command_output else None,
                    })
                elif itype == "FileChange":
                    saw_filechange_item = True
                    turn = ensure_turn()
                    changes = item.get("changes") if isinstance(item.get("changes"), dict) else {}
                    for path_key, change in changes.items():
                        ctype = (change or {}).get("type") if isinstance(change, dict) else None
                        action = {"add": "A", "update": "M", "delete": "D"}.get(ctype, "M")
                        turn["file_changes"].append({"action": action, "path": path_key})
                continue
            continue

        if rtype != "response_item":
            continue

        ptype = p.get("type")
        if ptype == "message":
            role = p.get("role")
            phase = p.get("phase")
            for c in p.get("content") or []:
                if not isinstance(c, dict):
                    continue
                text = c.get("text")
                if not isinstance(text, str):
                    continue
                if role == "user":
                    add_user(human_text(text))
                elif role == "assistant":
                    add_assistant("commentary" if phase == "commentary" else "final", text)
        elif ptype == "reasoning":
            if include_reasoning:
                for text in reasoning_texts(p):
                    add_assistant("reasoning", text)
        elif ptype == "function_call":
            add_tool_call(p.get("name"), p.get("arguments"), p.get("call_id"))
        elif ptype == "custom_tool_call":
            add_tool_call(p.get("name"), p.get("input"), p.get("call_id"))
        elif ptype in ("function_call_output", "custom_tool_call_output"):
            fill_call_output(p.get("call_id"), p.get("output"))

    # ---- per-turn post-processing -----------------------------------------
    for turn in turns:
        for text in turn["_agent_msgs"]:
            norm = text.strip()
            if norm in turn["_seen_assistant"]:
                continue
            turn["_seen_assistant"].add(norm)
            turn["assistant_blocks"].append({"kind": "final", "text": text})
        last = turn["_last_agent_message"]
        if isinstance(last, str):
            norm = last.strip()
            if norm and norm not in turn["_seen_assistant"]:
                turn["_seen_assistant"].add(norm)
                turn["assistant_blocks"].append({"kind": "final", "text": last})
        if not saw_exec_item:
            turn["commands"] = turn["tool_calls"]
        if not saw_filechange_item:
            turn["file_changes"] = turn["patch_changes"]
        seen_changes = set()
        deduped = []
        for change in turn["file_changes"]:
            key = (change.get("action"), change.get("path"))
            if key in seen_changes:
                continue
            seen_changes.add(key)
            deduped.append(change)
        turn["file_changes"] = deduped
        del turn["tool_calls"]
        del turn["patch_changes"]
        del turn["_agent_msgs"]
        del turn["_seen_user"]
        del turn["_seen_assistant"]
        del turn["_last_agent_message"]

    rendered_turns = [t for t in turns if _turn_has_content(t)]
    for i, turn in enumerate(rendered_turns, 1):
        turn["index"] = i

    stats["turns"] = len(rendered_turns)
    stats["human_messages"] = sum(len(t["user_blocks"]) for t in rendered_turns)
    stats["commands"] = sum(len(t["commands"]) for t in rendered_turns)
    stats["commands_failed"] = sum(
        1 for t in rendered_turns for c in t["commands"]
        if isinstance(c.get("exit_code"), int) and c["exit_code"] != 0
    )
    stats["files_changed"] = len({c["path"] for t in rendered_turns for c in t["file_changes"]})
    return rendered_turns, stats


def _turn_has_content(turn: Dict[str, Any]) -> bool:
    return bool(
        turn["user_blocks"] or turn["assistant_blocks"] or turn["plans"]
        or turn["commands"] or turn["file_changes"]
    )


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

BLOCK_HEADINGS = {
    "commentary": "### Assistant (commentary)",
    "final": "### Assistant (final)",
    "reasoning": "### Assistant (reasoning)",
}

DEFAULT_LIMITS = {
    "max_total_chars": 150000,
    "max_block_chars": 2000,
    "user_chars": 1200,
    "include_commentary": True,
    "include_reasoning": False,
    "include_command_output": False,
}

ACTION_CAP = 40
COMMAND_DISPLAY_CAP = 300


def _clip(text: str, cap: Optional[int]) -> Tuple[str, bool]:
    if cap is None or cap <= 0 or len(text) <= cap:
        return text, False
    return text[:cap] + "\u2026[truncated %d chars]" % (len(text) - cap), True


def _one_line(text: str, cap: int = COMMAND_DISPLAY_CAP) -> str:
    text = " ".join(text.split())
    if len(text) > cap:
        text = text[:cap] + "\u2026"
    return text


def _render_body(turns: List[Dict[str, Any]], stats: Dict[str, Any], user_cap: int,
                 block_cap: int, action_lines: int, commentary: bool,
                 keep_output: bool) -> Tuple[str, bool]:
    """One render pass. Returns (text, was_truncated)."""
    truncated = False
    lines: List[str] = []
    for turn in turns:
        lines.append("## Turn %d \u00b7 %s" % (turn["index"], turn.get("started_at") or "?"))
        lines.append("")
        for text in turn["user_blocks"]:
            clipped, was = _clip(text, user_cap)
            truncated = truncated or was
            lines.append("### User")
            lines.append(clipped)
            lines.append("")
        for block in turn["assistant_blocks"]:
            if block["kind"] == "commentary" and not commentary:
                continue
            clipped, was = _clip(block["text"], block_cap)
            truncated = truncated or was
            lines.append(BLOCK_HEADINGS.get(block["kind"], "### Assistant"))
            lines.append(clipped)
            lines.append("")
        for plan in turn["plans"]:
            clipped, was = _clip(plan, block_cap)
            truncated = truncated or was
            lines.append("### Plan")
            lines.append(clipped)
            lines.append("")
        lines.append("### Turn actions")
        actions = 0
        for cmd in turn["commands"]:
            if actions >= action_lines:
                break
            text = _one_line(cmd.get("command") or "?")
            code = cmd.get("exit_code")
            lines.append("- `$ %s` \u2192 exit %s" % (text, code if isinstance(code, int) else "?"))
            actions += 1
            if keep_output and cmd.get("output"):
                excerpt, was = _clip(cmd["output"].strip(), 400)
                truncated = truncated or was
                for out_line in excerpt.splitlines()[:8]:
                    lines.append("  %s" % out_line)
        for change in turn["file_changes"]:
            if actions >= action_lines:
                break
            lines.append("- %s %s" % (change.get("action", "M"), change.get("path", "?")))
            actions += 1
        extra = (len(turn["commands"]) + len(turn["file_changes"])) - actions
        if extra > 0:
            lines.append("- \u2026(+%d more)" % extra)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n", truncated


def _render_header(stats: Dict[str, Any], omitted: int) -> str:
    lines = ["# Codex Rollout Timeline", ""]
    lines.append("- thread_id: %s" % (stats.get("thread_id") or "?"))
    lines.append("- session_id: %s" % (stats.get("session_id") or "?"))
    lines.append("- cwd: %s" % (stats.get("cwd") or "?"))
    git = stats.get("git") or {}
    if git.get("branch") or git.get("commit_hash"):
        commit = (git.get("commit_hash") or "")[:8]
        lines.append("- git: %s @ %s" % (git.get("branch") or "?", commit or "?"))
    lines.append("- model: %s | effort: %s | cli: %s | originator: %s" % (
        stats.get("model") or "?", stats.get("effort") or "?",
        stats.get("cli_version") or "?", stats.get("originator") or "?"))
    lines.append("- span: %s \u2192 %s" % (stats.get("start") or "?", stats.get("end") or "?"))
    lines.append("- turns: %d | human messages: %d | commands: %d | failed commands: %d | file changes: %d" % (
        stats.get("turns") or 0, stats.get("human_messages") or 0, stats.get("commands") or 0,
        stats.get("commands_failed") or 0, stats.get("files_changed") or 0))
    if omitted > 0:
        lines.append("- omitted: %d middle turns for budget (first turn and the newest turns kept)" % omitted)
    lines.append("")
    return "\n".join(lines) + "\n"


def render_timeline(turns: List[Dict[str, Any]], stats: Dict[str, Any], opts: Optional[Dict[str, Any]] = None) -> str:
    """Deterministic timeline render; updates stats with budget/truncation facts.

    Tiers are tried in order and the first one that fits the budget wins; if
    none fits, middle turns are dropped so the goal (turn 1) and the newest
    turns (the conclusions) survive.
    """
    opts = dict(opts or {})
    limits = dict(DEFAULT_LIMITS)
    limits.update({k: v for k, v in opts.items() if k in DEFAULT_LIMITS})
    budget = int(limits["max_total_chars"])
    max_block = int(limits["max_block_chars"])
    user_request = int(limits["user_chars"])
    include_commentary = bool(limits["include_commentary"])

    n_turns = max(len(turns), 1)
    user_cap = min(user_request, max(120, budget // (2 * n_turns)))

    commentary_count = sum(1 for t in turns for b in t["assistant_blocks"] if b["kind"] == "commentary")
    other_blocks = sum(1 for t in turns for b in t["assistant_blocks"] if b["kind"] != "commentary")
    plan_count = sum(len(t["plans"]) for t in turns)
    plain_blocks = other_blocks + plan_count
    commentary_worth_it = commentary_count > other_blocks

    def block_count(commentary: bool) -> int:
        return plain_blocks + (commentary_count if commentary else 0)

    tiers = [(user_cap, max_block, ACTION_CAP, include_commentary)]
    if ACTION_CAP > 3:
        tiers.append((user_cap, max_block, 3, include_commentary))
    if ACTION_CAP > 1:
        tiers.append((user_cap, max_block, 1, include_commentary))
    if include_commentary and commentary_worth_it:
        tiers.append((user_cap, max_block, 1, False))
    share = max(1, budget // n_turns)
    tiers.append((max(80, share // 3), max(200, share // 2), 1, False))
    tiers.append((80, 200, 1, False))

    def assemble(subset: List[Dict[str, Any]], omitted: int, uc: int, bc: int, al: int, cm: bool) -> str:
        header = _render_header(stats, omitted)
        body, was = _render_body(subset, stats, uc, bc, al, cm, keep_output=False)
        stats["truncated"] = stats.get("truncated", False) or was
        return header + body

    stats["truncated"] = False
    text = ""
    chosen = None
    for uc, bc, al, cm in tiers:
        text = assemble(turns, 0, uc, bc, al, cm)
        if len(text) <= budget:
            chosen = (uc, bc, al, cm)
            break
    stats["dropped_commentary"] = False

    if chosen is None:
        # Nothing fits: keep turn 1 plus as many newest turns as the budget allows.
        uc, bc, al, cm = tiers[-1]
        stats["dropped_commentary"] = bool(include_commentary)
        keep = n_turns
        for _ in range(12):
            keep = max(1, min(keep, len(turns) - 1))
            subset = [turns[0]] + turns[len(turns) - keep:]
            text = assemble(subset, len(turns) - len(subset), uc, bc, al, cm)
            if len(text) <= budget:
                break
            if keep <= 1:
                break
            keep = max(1, int(keep * budget / max(len(text), 1) * 0.95))
        stats["omitted_turns"] = len(turns) - min(len(turns), 1 + keep)
    else:
        uc, bc, al, cm = chosen
        stats["dropped_commentary"] = bool(include_commentary and not cm)
        stats["omitted_turns"] = 0

    stats["emitted_chars"] = len(text)
    stats["budget_chars"] = budget
    stats["budget_exceeded"] = len(text) > budget
    stats["user_cap"] = uc
    stats["block_cap"] = bc
    stats["action_lines"] = al
    return text

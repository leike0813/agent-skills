"""事件流 → 固定 Markdown 日志。裁剪策略集中在这里。"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import replace
from typing import Any, Dict, List

from .model import Event, Session
from .yamlout import to_yaml

DEFAULT_MAX_CHARS = 2000

# 这些工具承载的是命令原文，命令不截断（只截结果）。
# 取值来自各 harness 实测的 shell 工具名（codex/claude/command-code/qwen/kimi/grok/dsh/pi/omp/codebuddy/cline）。
SHELL_TOOLS = {
    "exec_command",
    "shell",
    "bash",
    "Bash",
    "shell_command",
    "run_shell_command",
    "run_commands",
    "run_terminal_command",
    "terminal",
    "sh",
}

KIND_ORDER = ("user", "assistant", "system", "tool")

# compact 档位：消息按角色分档截断，工具只留名字与 shell 命令前 160 字。
COMPACT_LIMITS = {"system": 300, "user": 1200, "assistant": 1200}
COMPACT_MESSAGE_CHARS = 1200
COMPACT_CALL_CHARS = 160


def truncate(text: str, limit: int) -> str:
    """超限时截断并标注被省略的字符数。"""
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit] + f"\n[... truncated {len(text) - limit} chars ...]"


def fence(text: str, lang: str) -> str:
    """围栏长度自适应：内容里最长的连续反引号 +1，至少 3。"""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    marker = "`" * max(3, longest + 1)
    return f"{marker}{lang}\n{text}\n{marker}"


def _kind_label(event: Event) -> str:
    return "tool" if event.kind == "tool" else (event.role or "message")


def _heading(index: int, event: Event) -> str:
    parts = [str(index), _kind_label(event)]
    if event.kind == "tool" and event.tool:
        parts.append(event.tool)
    if event.ts:
        parts.append(event.ts)
    return "## " + " · ".join(parts)


def prepare_events(events: List[Event], max_chars: int) -> List[Event]:
    """按 default/full 规则截断：命令原文（shell 类工具）不截，其余同上限。"""
    prepared: List[Event] = []
    for event in events:
        if event.kind != "tool":
            text = truncate(event.text, max_chars) if event.role == "system" else event.text
            prepared.append(replace(event, text=text))
            continue
        call = event.call if event.tool in SHELL_TOOLS else truncate(event.call, max_chars)
        prepared.append(replace(event, call=call, result=truncate(event.result, max_chars)))
    return prepared


def prepare_compact(events: List[Event]) -> List[Event]:
    """compact 档位：消息按角色分档截断；工具只留名字与 shell 命令前 160 字，丢弃结果。"""
    prepared: List[Event] = []
    for event in events:
        if event.kind != "tool":
            limit = COMPACT_LIMITS.get(event.role, COMPACT_MESSAGE_CHARS)
            prepared.append(replace(event, text=truncate(event.text, limit)))
            continue
        call = truncate(event.call, COMPACT_CALL_CHARS) if event.tool in SHELL_TOOLS else ""
        status = "" if event.status == "completed" else event.status
        prepared.append(replace(event, call=call, result="", status=status))
    return prepared


def _block(index: int, event: Event) -> str:
    lines: List[str] = [_heading(index, event), ""]
    if event.kind == "tool":
        if event.status:
            lines += [f"- status: {event.status}", ""]
        if event.call:
            if event.tool in SHELL_TOOLS:
                lines += [fence(event.call, "bash"), ""]
            else:
                lines += [fence(event.call, "text"), ""]
        if event.result:
            lines += [fence(event.result, "text"), ""]
    else:
        lines += [event.text, ""]
    return "\n".join(lines).rstrip("\n")


def meta_lines(session: Session) -> List[str]:
    """会话头字段行（不含 events / profile 行）。"""
    lines = [f"- harness: {session.harness}"]
    if session.session_id:
        lines.append(f"- session: {session.session_id}")
    lines.append(f"- source: {session.source}")
    if session.cwd:
        lines.append(f"- cwd: {session.cwd}")
    origin = " ".join(part for part in (session.originator, session.version) if part)
    if origin:
        lines.append(f"- origin: {origin}")
    if session.history:
        lines.append(f"- history: {session.history}")
    return lines


def events_line(events: List[Event]) -> str:
    counts = Counter(_kind_label(event) for event in events)
    summary = ", ".join(f"{kind} {counts[kind]}" for kind in KIND_ORDER if counts[kind])
    return f"- events: {len(events)}" + (f" ({summary})" if summary else "")


def render_markdown(
    session: Session,
    events: List[Event],
    max_chars: int = DEFAULT_MAX_CHARS,
    profile: str = "",
) -> str:
    events = prepare_events(events, max_chars)

    title = f"# Transcript · {session.harness}"
    if session.started:
        title += f" · {session.started}"
    meta = meta_lines(session)
    if profile and profile != "default":  # default 档位的文档形状不含 profile 行
        meta.insert(1, f"- profile: {profile}")
    meta.append(events_line(events))

    blocks = ["\n".join([title, "", *meta, "", "---"])]
    for index, event in enumerate(events, start=1):
        blocks.append(_block(index, event))
    return "\n\n".join(blocks) + "\n"


def _event_mapping(event: Event) -> Dict[str, Any]:
    mapping: Dict[str, Any] = {"kind": event.kind}
    for key, value in (("role", event.role), ("tool", event.tool), ("ts", event.ts),
                       ("status", event.status), ("text", event.text),
                       ("call", event.call), ("result", event.result)):
        if value:
            mapping[key] = value
    return mapping


def render_yaml(
    session: Session,
    events: List[Event],
    max_chars: int = DEFAULT_MAX_CHARS,
    profile: str = "default",
) -> str:
    """与 render_markdown 同一份裁剪结果，序列化为 YAML。"""
    document: Dict[str, Any] = {"harness": session.harness, "profile": profile}
    for key, value in (("session", session.session_id), ("source", session.source),
                       ("cwd", session.cwd), ("started", session.started)):
        if value:
            document[key] = value
    origin = " ".join(part for part in (session.originator, session.version) if part)
    if origin:
        document["origin"] = origin
    if session.history:
        document["history"] = session.history
    document["events"] = [_event_mapping(event) for event in prepare_events(events, max_chars)]
    return to_yaml(document)

"""Codex rollout（JSONL）解析器。

一份 rollout 里同一内容可能在两条流里各出现一次：
`event_msg/item_completed`（富结构，TUI 视角）与 `response_item`（模型原始格式）。
两者只取其一：item 流含工具类条目时用 item 流，否则（旧版本）用 response_item。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..model import Event, Session
from ._support import (
    ResultBinder,
    as_text,
    head_records,
    iter_records,
    join_argv,
    message_event,
    text_blocks,
    tool_event,
)
from .base import Adapter

# item 流里出现这些类型，说明该文件的工具调用记录在 item 流中。
TOOL_ITEM_TYPES = {
    "CommandExecution",
    "McpToolCall",
    "FileChange",
    "WebSearch",
    "CollabAgentToolCall",
    "ImageView",
    "SubAgentActivity",
    "Extension",
}

KNOWN_RECORD_TYPES = {
    "session_meta",
    "response_item",
    "event_msg",
    "turn_context",
    "token_usage_record",
    "world_state",
    "compacted",
}

DETECT_LINE_LIMIT = 200

_ROLE_MAP = {
    "user": "user",
    "assistant": "assistant",
    "developer": "system",
    "system": "system",
}

_TEXT_TYPES = ("input_text", "output_text", "text")


def _output_text(output: Any) -> str:
    """工具输出：字符串原样，content 块列表取 text，其它按 JSON 文本。"""
    if isinstance(output, list):
        return text_blocks(output, _TEXT_TYPES)
    return as_text(output)


def _mcp_name(name: str) -> str:
    """`mcp__server__tool` → `mcp:server.tool`，其它名字原样返回。"""
    if not name.startswith("mcp__"):
        return name
    parts = name[len("mcp__"):].split("__")
    if len(parts) >= 2:
        return f"mcp:{parts[0]}.{parts[1]}"
    return f"mcp:{parts[0]}"


def _join_name(prefix: str, *parts: Any) -> str:
    tail = ".".join(str(part) for part in parts if part)
    return f"{prefix}{tail}" if tail else prefix.rstrip(":")


def _payload(record: Dict[str, Any]) -> Dict[str, Any]:
    payload = record.get("payload")
    return payload if isinstance(payload, dict) else {}


class CodexAdapter(Adapter):
    name = "codex"

    def detect(self, path: Path) -> bool:
        if not path.is_file():
            return False
        try:
            for record in head_records(path, DETECT_LINE_LIMIT):
                if record.get("type") in KNOWN_RECORD_TYPES and isinstance(record.get("payload"), dict):
                    return True
        except (OSError, RuntimeError):
            return False
        return False

    def parse(self, path: Path) -> Tuple[Session, List[Event]]:
        meta: Dict[str, Any] = {}
        history = "legacy"
        for record in iter_records(path):
            rtype = record.get("type")
            if rtype == "session_meta" and not meta:
                meta = _payload(record)
            elif rtype == "event_msg":
                payload = _payload(record)
                if payload.get("type") != "item_completed":
                    continue
                item = payload.get("item")
                if isinstance(item, dict) and item.get("type") in TOOL_ITEM_TYPES:
                    history = "paginated"
                    break

        session = Session(
            harness=self.name,
            source=str(path),
            session_id=str(meta.get("id") or meta.get("session_id") or ""),
            cwd=str(meta.get("cwd") or ""),
            started=str(meta.get("timestamp") or ""),
            version=str(meta.get("cli_version") or ""),
            originator=str(meta.get("originator") or ""),
            history=history,
        )
        events = self._parse_paginated(path) if history == "paginated" else self._parse_legacy(path)
        return session, events

    def _parse_paginated(self, path: Path) -> List[Event]:
        events: List[Event] = []
        for record in iter_records(path):
            ts = str(record.get("timestamp") or "")
            rtype = record.get("type")
            payload = _payload(record)
            if rtype == "event_msg" and payload.get("type") == "item_completed":
                item = payload.get("item")
                if isinstance(item, dict):
                    event = _item_event(item, ts)
                    if event is not None:
                        events.append(event)
            elif rtype == "response_item" and payload.get("type") == "message":
                # item 流已覆盖 user/assistant，这里只补 system/developer。
                if payload.get("role") in ("developer", "system"):
                    text = text_blocks(payload.get("content"), _TEXT_TYPES)
                    event = message_event("system", text, ts)
                    if event is not None:
                        events.append(event)
        return events

    def _parse_legacy(self, path: Path) -> List[Event]:
        events: List[Event] = []
        binder = ResultBinder()
        for record in iter_records(path):
            ts = str(record.get("timestamp") or "")
            rtype = record.get("type")
            payload = _payload(record)

            if rtype == "compacted":
                events.append(Event(kind="message", role="system", text="context compacted", ts=ts))
                continue
            if rtype == "event_msg":
                ptype = payload.get("type")
                if ptype == "agent_message":
                    event = message_event("assistant", as_text(payload.get("message") or payload.get("text")), ts)
                elif ptype == "user_message":
                    event = message_event("user", as_text(payload.get("message") or payload.get("text")), ts)
                else:
                    event = None
                if event is not None:
                    events.append(event)
                continue
            if rtype != "response_item":
                continue

            ptype = payload.get("type")
            call_id = payload.get("call_id")
            if ptype == "message":
                role = _ROLE_MAP.get(str(payload.get("role") or ""), "")
                if not role:
                    continue
                event = message_event(role, text_blocks(payload.get("content"), _TEXT_TYPES), ts)
                if event is not None:
                    events.append(event)
            elif ptype == "function_call":
                event = tool_event(
                    _mcp_name(str(payload.get("name") or "function")),
                    as_text(payload.get("arguments")),
                    "",
                    "",
                    ts,
                )
                if event is not None:
                    events.append(event)
                    binder.add(call_id, event)
            elif ptype == "function_call_output":
                binder.bind(call_id, _output_text(payload.get("output")))
            elif ptype == "custom_tool_call":
                event = tool_event(str(payload.get("name") or "custom_tool"), as_text(payload.get("input")), "", "", ts)
                if event is not None:
                    events.append(event)
                    binder.add(call_id, event)
            elif ptype == "custom_tool_call_output":
                binder.bind(call_id, _output_text(payload.get("output")))
            elif ptype == "local_shell_call":
                action = payload.get("action")
                command = action.get("command") if isinstance(action, dict) else None
                event = tool_event("shell", join_argv(command), "", "", ts)
                if event is not None:
                    events.append(event)
                    binder.add(call_id, event)
            elif ptype == "local_shell_call_output":
                binder.bind(call_id, _output_text(payload.get("output")))
            elif ptype == "web_search_call":
                action = payload.get("action")
                query = payload.get("query")
                if not query and isinstance(action, dict):
                    query = action.get("query")
                event = tool_event("web_search", as_text(query), "", "", ts)
                if event is not None:
                    events.append(event)
        return events


def _item_event(item: Dict[str, Any], ts: str) -> Optional[Event]:
    itype = item.get("type")
    if itype == "UserMessage":
        return message_event("user", text_blocks(item.get("content"), ("text",)), ts)
    if itype == "AgentMessage":
        return message_event("assistant", text_blocks(item.get("content"), ("Text", "text")), ts)
    if itype == "Plan":
        return message_event("assistant", as_text(item.get("text")), ts)
    if itype == "ContextCompaction":
        return message_event("system", "context compacted", ts)
    if itype == "CommandExecution":
        event = tool_event(
            "exec_command",
            join_argv(item.get("command")),
            as_text(item.get("aggregated_output")),
            str(item.get("status") or ""),
            ts,
        )
        return event
    if itype == "McpToolCall":
        result = item.get("result")
        content = result.get("content") if isinstance(result, dict) else None
        return tool_event(
            _join_name("mcp:", item.get("server"), item.get("tool")),
            as_text(item.get("arguments")),
            text_blocks(content, ("text",)),
            str(item.get("status") or ""),
            ts,
        )
    if itype == "FileChange":
        paths: List[str] = []
        diffs: List[str] = []
        changes = item.get("changes")
        if isinstance(changes, dict):
            for path, change in changes.items():
                if isinstance(change, dict):
                    ctype = str(change.get("type") or "")
                    paths.append(f"{path} ({ctype})" if ctype else str(path))
                    diff = change.get("unified_diff")
                    if diff:
                        diffs.append(str(diff))
                else:
                    paths.append(str(path))
        return tool_event("file_change", "; ".join(paths), "\n".join(diffs), "", ts)
    if itype == "WebSearch":
        action = item.get("action")
        query = item.get("query")
        if not query and isinstance(action, dict):
            query = action.get("query")
        return tool_event("web_search", as_text(query), "", "", ts)
    if itype == "CollabAgentToolCall":
        return tool_event(
            _join_name("collab:", item.get("tool")),
            as_text(item.get("prompt")),
            "",
            str(item.get("status") or ""),
            ts,
        )
    if itype == "ImageView":
        return tool_event("image_view", as_text(item.get("path")), "", "", ts)
    if itype == "SubAgentActivity":
        call = as_text(item.get("agent_path") or item.get("agent_thread_id"))
        if item.get("model"):
            call = f"{call} (model={item['model']})"
        return tool_event(_join_name("subagent:", item.get("kind")), call, "", "", ts)
    return None

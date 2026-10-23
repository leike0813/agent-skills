"""Continue CLI 会话（`~/.continue/sessions/<sessionId>.json`）。

单个 JSON 文档：`{sessionId, title, workspaceDirectory, history[]}`。
每条 history 项的 `message` 是正文，`message.toolCalls` 与 `item.toolCallStates`
是同一批工具调用的两份副本，按调用 ID 去重合并；工具结果取自状态项的 `output`。
会话文件不带时间戳，事件时间一律留空。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..model import Event, Session
from ._support import as_text, load_json_doc, message_event, text_blocks, tool_event
from .base import Adapter

# Continue 的 ToolStatus 枚举（generating/generated/calling/errored/done/canceled）。
_STATUS_MAP = {"done": "completed", "errored": "error"}


def _status(source: str) -> str:
    return _STATUS_MAP.get(source, source)


def _is_history_item(item: Any) -> bool:
    """history 项须带 message，且 message 有 role 与文本型 content。"""
    if not isinstance(item, dict):
        return False
    message = item.get("message")
    if not isinstance(message, dict):
        return False
    if not isinstance(message.get("role"), str):
        return False
    content = message.get("content")
    return isinstance(content, (str, list))


def _output_text(output: Any) -> str:
    """`toolCallStates[].output` 是 ContextItem 列表，正文在 `content` 里。"""
    if not isinstance(output, list):
        return ""
    parts: List[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, str):
            if content:
                parts.append(content)
        elif isinstance(content, list):
            text = text_blocks(content, ("text",))
            if text:
                parts.append(text)
    return "\n".join(parts)


def _call_name(call: Any) -> str:
    if not isinstance(call, dict):
        return ""
    function = call.get("function")
    if isinstance(function, dict) and isinstance(function.get("name"), str):
        return function["name"]
    return ""


def _call_arguments(call: Any) -> Any:
    if not isinstance(call, dict):
        return None
    function = call.get("function")
    return function.get("arguments") if isinstance(function, dict) else None


class ContinueCliAdapter(Adapter):
    name = "continue"

    def detect(self, path: Path) -> bool:
        document = load_json_doc(path)
        if document is None:
            return False
        if not (
            isinstance(document.get("history"), list)
            and isinstance(document.get("sessionId"), str)
            and isinstance(document.get("workspaceDirectory"), str)
        ):
            return False
        return all(_is_history_item(item) for item in document["history"])

    def parse(self, path: Path) -> Tuple[Session, List[Event]]:
        document = load_json_doc(path)
        if document is None:
            raise RuntimeError(f"cannot read JSON document: {path}")

        events: List[Event] = []
        for item in document.get("history") or []:
            if not isinstance(item, dict):
                continue
            message = item.get("message")
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            if role in ("user", "assistant", "system"):
                event = message_event(role, text_blocks(message.get("content"), ("text",)), "")
                if event is not None:
                    events.append(event)
            events.extend(self._tool_events(message.get("toolCalls"), item.get("toolCallStates")))

        session = Session(
            harness=self.name,
            source=str(path),
            session_id=str(document.get("sessionId") or ""),
            cwd=str(document.get("workspaceDirectory") or ""),
        )
        return session, events

    def _tool_events(self, tool_calls: Any, states: Any) -> List[Event]:
        """消息里的调用副本与状态项按调用 ID 合并；只出现在状态项里的调用也要输出。"""
        records: List[Dict[str, Any]] = []
        by_id: Dict[str, Dict[str, Any]] = {}

        def register(call_id: str, call: Any, state: Any) -> None:
            record = by_id.get(call_id)
            if record is None:
                record = {"call": None, "state": None}
                by_id[call_id] = record
                records.append(record)
            if call is not None and record["call"] is None:
                record["call"] = call
            if state is not None:
                record["state"] = state

        for call in tool_calls or []:
            if not isinstance(call, dict):
                continue
            call_id = str(call.get("id") or "")
            if call_id:
                register(call_id, call, None)

        for state in states or []:
            if not isinstance(state, dict):
                continue
            call_id = str(state.get("toolCallId") or "")
            if call_id:
                register(call_id, state.get("toolCall"), state)

        events: List[Event] = []
        for record in records:
            state = record["state"] or {}
            call = record["call"] or {}
            args = state.get("parsedArgs")
            if not (isinstance(args, dict) and args):
                args = _call_arguments(call)
                if args is None:
                    args = _call_arguments(state.get("toolCall"))
            name = _call_name(call) or _call_name(state.get("toolCall"))
            event = tool_event(
                name or "tool",
                as_text(args),
                _output_text(state.get("output")),
                _status(str(state.get("status") or "")),
                "",
            )
            if event is not None:
                events.append(event)
        return events

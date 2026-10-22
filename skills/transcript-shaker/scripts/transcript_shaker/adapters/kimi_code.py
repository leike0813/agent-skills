"""Kimi Code 会话（`~/.kimi-code/sessions/<wd>/session_<uuid>/agents/main/wire.jsonl`）。

wire 是 agent 内部事件总线，几十种事件里只有 `agent.message.appended` 是对话正文；
`context.append_message`、`llm.request`、`turn.*`、`file_history.*` 等都是索引或状态。
正文消息外壳是 `{message: {message: {role, content[], toolCalls[]}, meta: {source}}}`。
子代理写在 `agents/agent-*/wire.jsonl`，不自动拼接。
只有会话头与配置事件的空会话也识别，输出 0 事件。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..model import Event, Session
from ._support import (
    ResultBinder,
    as_text,
    head_records,
    iso_from_ms,
    iter_records,
    load_json_doc,
    message_event,
    text_blocks,
    tool_event,
)
from .base import Adapter

MESSAGE_EVENT = "agent.message.appended"

# 这些 type 带 `.`，是识别 kimi wire 的依据（含正文事件本身）。
WIRE_TYPES = {
    MESSAGE_EVENT,
    "context.append_message",
    "llm.request",
    "turn.prompt",
    "turn.ended",
    "agent.turn.started",
}


def _looks_like_kimi(record: Dict[str, Any]) -> bool:
    rtype = record.get("type")
    return isinstance(rtype, str) and "." in rtype and rtype in WIRE_TYPES


def _looks_like_kimi_metadata(record: Dict[str, Any]) -> bool:
    """会话头：正文前中断的会话只剩 metadata + config.update，靠它识别。"""
    return record.get("type") == "metadata" and "protocol_version" in record


class KimiCodeAdapter(Adapter):
    name = "kimi-code"

    def detect(self, path: Path) -> bool:
        try:
            records = head_records(path)
        except (OSError, RuntimeError):
            return False
        return any(
            _looks_like_kimi(record) or _looks_like_kimi_metadata(record) for record in records
        )

    def parse(self, path: Path) -> Tuple[Session, List[Event]]:
        events: List[Event] = []
        binder = ResultBinder()

        for record in iter_records(path):
            if record.get("type") != MESSAGE_EVENT:
                continue
            ts = iso_from_ms(record.get("time"))
            envelope = record.get("message")
            if not isinstance(envelope, dict):
                continue
            inner = envelope.get("message")
            if not isinstance(inner, dict):
                continue
            meta = envelope.get("meta")
            source = meta.get("source") if isinstance(meta, dict) else None
            if source == "notify":
                continue

            role = inner.get("role")
            content = inner.get("content")
            if role == "user":
                if source != "input":
                    continue
                event = message_event("user", text_blocks(content, ("text",)), ts)
                if event is not None:
                    events.append(event)
            elif role == "assistant":
                event = message_event("assistant", text_blocks(content, ("text",)), ts)
                if event is not None:
                    events.append(event)
                for call in inner.get("toolCalls") or []:
                    if not isinstance(call, dict):
                        continue
                    tool = tool_event(str(call.get("name") or "tool"), as_text(call.get("arguments")), "", "", ts)
                    if tool is not None:
                        events.append(tool)
                        binder.add(call.get("id"), tool)
            elif role == "tool":
                binder.bind(inner.get("toolCallId"), text_blocks(content, ("text",)), "completed")

        session_dir = path.parent.parent.parent
        state = load_json_doc(session_dir / "state.json") or {}
        session_id = str(state.get("id") or session_dir.name)
        if session_id.startswith("session_"):
            session_id = session_id[len("session_"):]
        created = state.get("createdAt")
        session = Session(
            harness=self.name,
            source=str(path),
            session_id=session_id,
            cwd=str(state.get("cwd") or ""),
            # 新版写 epoch 毫秒，旧版写 ISO 字符串。
            started=iso_from_ms(created) if isinstance(created, int) else str(created or ""),
        )
        return session, events

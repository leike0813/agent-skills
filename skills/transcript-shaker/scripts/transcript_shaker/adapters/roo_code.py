"""Roo Code API history（`<tasks>/<taskId>/api_conversation_history.json`）。

顶层是 Anthropic 形状的消息数组：`role` + `content` 块（text / tool_use /
tool_result），`ts` 是 epoch 毫秒。同目录 `history_item.json` 只补会话元数据；
UI 侧 `ui_messages.json` 不读取，避免同一轮正文重复。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Tuple

from ..model import Event, Session
from ._support import (
    ResultBinder,
    as_text,
    iso_from_ms,
    load_json_doc,
    load_json_value,
    message_event,
    text_blocks,
    tool_event,
)
from .base import Adapter


def _is_history(value: Any) -> bool:
    """只验证消息数组形状；空数组也是合法会话。"""
    if not isinstance(value, list):
        return False
    for item in value:
        if not isinstance(item, dict):
            return False
        role = item.get("role")
        if role is None:
            if item.get("type") != "reasoning":
                return False
            continue
        if role not in ("user", "assistant", "system"):
            return False
        if not isinstance(item.get("content"), (str, list)):
            return False
    return True


def _result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return text_blocks(content, ("text",))


class RooCodeAdapter(Adapter):
    name = "roo-code"

    def detect(self, path: Path) -> bool:
        return _is_history(load_json_value(path))

    def parse(self, path: Path) -> Tuple[Session, List[Event]]:
        history = load_json_value(path)
        if not isinstance(history, list):
            raise RuntimeError(f"cannot read JSON document: {path}")

        events: List[Event] = []
        binder = ResultBinder()
        first_ts = ""

        for item in history:
            if not isinstance(item, dict):
                continue
            ts = iso_from_ms(item.get("ts"))
            if ts and not first_ts:
                first_ts = ts
            role = item.get("role")
            if item.get("type") == "reasoning" or role not in ("user", "assistant", "system"):
                continue
            content = item.get("content")
            if isinstance(content, str):
                event = message_event(role, content, ts)
                if event is not None:
                    events.append(event)
                continue
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    event = message_event(role, as_text(block.get("text")), ts)
                    if event is not None:
                        events.append(event)
                elif btype == "tool_use":
                    event = tool_event(
                        str(block.get("name") or "tool"), as_text(block.get("input")), "", "", ts
                    )
                    if event is not None:
                        events.append(event)
                        binder.add(block.get("id"), event)
                elif btype == "tool_result":
                    status = "error" if block.get("is_error") else "completed"
                    binder.bind(block.get("tool_use_id"), _result_text(block.get("content")), status)

        item_doc = load_json_doc(path.parent / "history_item.json") or {}
        session = Session(
            harness=self.name,
            source=str(path),
            session_id=str(item_doc.get("id") or "") or path.parent.name,
            cwd=str(item_doc.get("workspace") or ""),
            started=iso_from_ms(item_doc.get("ts")) or first_ts,
        )
        return session, events

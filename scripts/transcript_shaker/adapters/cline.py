"""Cline 会话（`~/.cline/data/sessions/<id>/<id>.messages.json`）。

单个 JSON 文档：`{sessionId, updated_at, system_prompt, messages[]}`；
消息 content 块与 Claude 同构（text / thinking / tool_use / tool_result），
`ts` 是 epoch 毫秒。同目录 `<id>.json` 是运行时状态，只用来补 cwd 与真实开始时间。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..model import Event, Session
from ._support import ResultBinder, as_text, iso_from_ms, load_json_doc, message_event, text_blocks, tool_event
from .base import Adapter


def _result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: List[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        for key in ("result", "text"):
            value = block.get(key)
            if isinstance(value, str) and value:
                parts.append(value)
                break
    return "\n".join(parts)


def _state_doc(path: Path) -> Dict[str, Any]:
    """同目录 `<id>.json`：运行时状态（cwd / started_at），缺失时返回空。"""
    name = path.name
    if not name.endswith(".messages.json"):
        return {}
    return load_json_doc(path.parent / (name[: -len(".messages.json")] + ".json")) or {}


class ClineAdapter(Adapter):
    name = "cline"

    def detect(self, path: Path) -> bool:
        document = load_json_doc(path)
        if document is None:
            return False
        return (
            isinstance(document.get("messages"), list)
            and isinstance(document.get("system_prompt"), str)
            and "origin" in document
        )

    def parse(self, path: Path) -> Tuple[Session, List[Event]]:
        document = load_json_doc(path)
        if document is None:
            raise RuntimeError(f"cannot read JSON document: {path}")

        events: List[Event] = []
        binder = ResultBinder()

        prompt = document.get("system_prompt")
        if isinstance(prompt, str):
            event = message_event("system", prompt, "")
            if event is not None:
                events.append(event)

        for message in document.get("messages") or []:
            if not isinstance(message, dict):
                continue
            ts = iso_from_ms(message.get("ts"))
            content = message.get("content")
            if not isinstance(content, list):
                continue
            role = message.get("role")

            if role == "user":
                blocks = [block for block in content if isinstance(block, dict)]
                results = [block for block in blocks if block.get("type") == "tool_result"]
                if results:
                    for block in results:
                        binder.bind(block.get("tool_use_id"), _result_text(block.get("content")), "completed")
                    continue
                event = message_event("user", text_blocks(blocks, ("text",)), ts)
                if event is not None:
                    events.append(event)
            elif role == "assistant":
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "text":
                        event = message_event("assistant", as_text(block.get("text")), ts)
                        if event is not None:
                            events.append(event)
                    elif btype == "tool_use":
                        tool = tool_event(str(block.get("name") or "tool"), as_text(block.get("input")), "", "", ts)
                        if tool is not None:
                            events.append(tool)
                            binder.add(block.get("id"), tool)

        state = _state_doc(path)
        session = Session(
            harness=self.name,
            source=str(path),
            session_id=str(document.get("sessionId") or ""),
            cwd=str(state.get("cwd") or ""),
            started=str(state.get("started_at") or document.get("updated_at") or ""),
        )
        return session, events

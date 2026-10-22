"""Qwen Code 会话（`~/.qwen/projects/<slug>/chats/<uuid>.jsonl`）。

message.parts 没有 `type` 字段，只能按键区分：`text` / `functionCall` / `functionResponse`。
`type=="system"` 是提示词快照（systemPayload），不是对话内容。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..model import Event, Session
from ._support import ResultBinder, as_text, head_records, iter_records, message_event, tool_event
from .base import Adapter

DIALOG_TYPES = {"user", "assistant", "system"}


def _looks_like_qwen(record: Dict[str, Any]) -> bool:
    message = record.get("message")
    message = message if isinstance(message, dict) else {}
    if record.get("type") == "tool_result" and isinstance(message.get("parts"), list):
        return True
    return record.get("type") in DIALOG_TYPES and "provenance" in record


def _part_text(parts: Any) -> str:
    if not isinstance(parts, list):
        return ""
    # 推理 part 也带 `text`，靠 `thought` 标记区分；带它的一律不输出。
    return "\n".join(
        part["text"]
        for part in parts
        if isinstance(part, dict)
        and not part.get("thought")
        and isinstance(part.get("text"), str)
        and part["text"]
    )


class QwenCodeAdapter(Adapter):
    name = "qwen-code"

    def detect(self, path: Path) -> bool:
        try:
            return any(_looks_like_qwen(record) for record in head_records(path))
        except (OSError, RuntimeError):
            return False

    def parse(self, path: Path) -> Tuple[Session, List[Event]]:
        events: List[Event] = []
        binder = ResultBinder()
        session_id = ""
        cwd = ""
        started = ""

        for record in iter_records(path):
            ts = str(record.get("timestamp") or "")
            session_id = session_id or str(record.get("sessionId") or "")
            cwd = cwd or str(record.get("cwd") or "")
            started = started or ts

            rtype = record.get("type")
            message = record.get("message")
            message = message if isinstance(message, dict) else {}
            parts = message.get("parts")

            if rtype == "user":
                if record.get("provenance") != "real_user":
                    continue
                event = message_event("user", _part_text(parts), ts)
                if event is not None:
                    events.append(event)
            elif rtype == "assistant":
                event = message_event("assistant", _part_text(parts), ts)
                if event is not None:
                    events.append(event)
                if not isinstance(parts, list):
                    continue
                for part in parts:
                    if not isinstance(part, dict):
                        continue
                    call = part.get("functionCall")
                    if not isinstance(call, dict):
                        continue
                    tool = tool_event(str(call.get("name") or "tool"), as_text(call.get("args")), "", "", ts)
                    if tool is not None:
                        events.append(tool)
                        binder.add(call.get("id"), tool)
            elif rtype == "tool_result":
                if not isinstance(parts, list):
                    continue
                for part in parts:
                    if not isinstance(part, dict):
                        continue
                    response = part.get("functionResponse")
                    if not isinstance(response, dict):
                        continue
                    payload = response.get("response")
                    output = payload.get("output") if isinstance(payload, dict) else None
                    binder.bind(response.get("id"), as_text(output), "completed")

        session = Session(
            harness=self.name,
            source=str(path),
            session_id=session_id,
            cwd=cwd,
            started=started,
        )
        return session, events

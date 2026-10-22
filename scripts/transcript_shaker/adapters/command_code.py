"""Command Code 会话（`~/.commandcode/projects/<slug>/<uuid>.jsonl`）。

记录形如 `{type, id, timestamp, message: {role, content[], meta}}`，与 Claude 的
content 块结构一致，但会话头是一条 `type=="session"` 记录。
`~/.commandcode/sessions/hooks-audit-*.jsonl` 是审计日志，不含会话正文。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..model import Event, Session
from ._support import ResultBinder, as_text, head_records, iter_records, message_event, text_blocks, tool_event
from .base import Adapter


def _looks_like_command_code(record: Dict[str, Any]) -> bool:
    if record.get("type") != "message":
        return False
    message = record.get("message")
    # pi 系同为 type=="message"，但 message 里没有 meta。
    return isinstance(message, dict) and isinstance(message.get("meta"), dict)


def _result_text(content: Any) -> str:
    return text_blocks(content, ("text",)) if isinstance(content, list) else as_text(content)


class CommandCodeAdapter(Adapter):
    name = "command-code"

    def detect(self, path: Path) -> bool:
        try:
            return any(_looks_like_command_code(record) for record in head_records(path))
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
            rtype = record.get("type")

            if rtype == "session":
                session_id = session_id or str(record.get("id") or "")
                cwd = cwd or str(record.get("cwd") or "")
                started = started or ts
                continue
            if rtype != "message":
                continue

            message = record.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            role = message.get("role")

            if role == "user":
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type")
                    if btype == "text":
                        event = message_event("user", as_text(block.get("text")), ts)
                        if event is not None:
                            events.append(event)
                    elif btype == "tool_result":
                        binder.bind(block.get("tool_use_id"), _result_text(block.get("content")), "completed")
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
                        event = tool_event(str(block.get("name") or "tool"), as_text(block.get("input")), "", "", ts)
                        if event is not None:
                            events.append(event)
                            binder.add(block.get("id"), event)

        session = Session(
            harness=self.name,
            source=str(path),
            session_id=session_id,
            cwd=cwd,
            started=started,
        )
        return session, events

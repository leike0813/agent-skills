"""DeepSeek Harness 会话（`~/.dsh/sessions/<cwd-slug>/<uuid>/session*.jsonl.zstd`）。

zstd 帧流里是 JSONL，每条记录 `{type, seq, time, data}`。24 种事件里只有
`session`、`user/message`、`assistant/message`、`tool/call`、`tool/result` 承载正文；
`assistant/chunk`、`text-chunks`、`reasoning-chunks`、`tool-call-chunks` 是流式增量，
读它们会让同一内容出现两遍。`assistant/message` 的 `tool-call` 块与 `tool/call`
记录重复，只取后者。
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
    message_event,
    text_blocks,
    tool_event,
)
from .base import Adapter

DIALOG_TYPES = {"user/message", "assistant/message", "tool/call", "tool/result"}


def _looks_like_dsh(record: Dict[str, Any]) -> bool:
    if record.get("type") == "session":
        # 只有 dsh 的会话头用 createdAt（epoch 毫秒）；pi/omp 用 ISO timestamp。
        return isinstance(record.get("version"), int) and "createdAt" in record
    if record.get("type") not in DIALOG_TYPES:
        return False
    return "seq" in record and "time" in record and isinstance(record.get("data"), dict)


def _surface_replaced(record: Dict[str, Any]) -> bool:
    """压缩摘要会以 replace 操作把历史消息替换掉，那份内容不该再算作正文。"""
    surface = record.get("surfaceOp")
    if isinstance(surface, str):
        return surface == "replace"
    if isinstance(surface, dict):
        return surface.get("op") == "replace"
    return False


class DeepseekHarnessAdapter(Adapter):
    name = "deepseek-harness"

    def detect(self, path: Path) -> bool:
        if not path.is_file():
            return False
        try:
            return any(_looks_like_dsh(record) for record in head_records(path))
        except (OSError, RuntimeError):
            return False

    def parse(self, path: Path) -> Tuple[Session, List[Event]]:
        events: List[Event] = []
        binder = ResultBinder()
        session_id = ""
        cwd = ""
        started = ""

        for record in iter_records(path):
            rtype = record.get("type")
            data = record.get("data")
            data = data if isinstance(data, dict) else {}
            ts = iso_from_ms(record.get("time"))

            if rtype == "session":
                session_id = str(record.get("id") or "")
                cwd = str(record.get("cwd") or "")
                started = iso_from_ms(record.get("createdAt"))
            elif rtype == "user/message":
                if _surface_replaced(record):
                    continue
                event = message_event("user", text_blocks(data.get("content"), ("text",)), ts)
                if event is not None:
                    events.append(event)
            elif rtype == "assistant/message":
                message = data.get("message")
                message = message if isinstance(message, dict) else {}
                content = message.get("content")
                if not isinstance(content, list):
                    continue
                event = message_event("assistant", text_blocks(content, ("text",)), ts)
                if event is not None:
                    events.append(event)
            elif rtype == "tool/call":
                event = tool_event(
                    str(data.get("name") or "tool"),
                    as_text(data.get("arguments")),
                    "",
                    "",
                    ts,
                )
                if event is not None:
                    events.append(event)
                    binder.add(data.get("callId"), event)
            elif rtype == "tool/result":
                message = data.get("message")
                message = message if isinstance(message, dict) else {}
                source = message.get("source")
                call_id = source.get("callId") if isinstance(source, dict) else None
                result, is_error = _result_text(message.get("content"))
                binder.bind(call_id, result, "error" if is_error else "completed")

        session = Session(
            harness=self.name,
            source=str(path),
            session_id=session_id,
            cwd=cwd,
            started=started,
        )
        return session, events


def _result_text(content: Any) -> Tuple[str, bool]:
    """`tool/result` 的 message.content 是包装层，正文与 isError 在更里面。"""
    if not isinstance(content, list):
        return "", False
    texts: List[str] = []
    is_error = False
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("isError") is True:
            is_error = True
        texts.append(text_blocks(block.get("content"), ("text",)))
    return "\n".join(text for text in texts if text), is_error

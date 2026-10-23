"""Goose CLI 的 SQLite 会话；content_json 使用 camelCase 内容块。"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from ..model import Event, Session
from ._support import (
    ResultBinder, as_text, iso_from_ms, json_value, message_event,
    read_sqlite, sqlite_matches, text_blocks, tool_event,
)
from .base import Adapter

SCHEMA = {
    "sessions": ("id", "working_dir", "created_at"),
    "messages": ("id", "session_id", "role", "content_json", "created_timestamp"),
}


class GooseAdapter(Adapter):
    name = "goose"

    def detect(self, path: Path) -> bool:
        return sqlite_matches(path, SCHEMA)

    def parse(self, path: Path) -> Tuple[Session, List[Event]]:
        with read_sqlite(path) as conn:
            row = conn.execute(
                "SELECT id, working_dir, created_at FROM sessions ORDER BY created_at DESC, id DESC LIMIT 1"
            ).fetchone()
            if row is None:
                raise RuntimeError(f"no session rows in {path}")
            session_id, cwd, started = row
            rows = conn.execute(
                "SELECT role, content_json, created_timestamp FROM messages WHERE session_id = ? "
                "ORDER BY created_timestamp, id", (session_id,),
            ).fetchall()

        events: List[Event] = []
        binder = ResultBinder()
        for role, content, stamp in rows:
            blocks = json_value(content)
            if not isinstance(blocks, list):
                continue
            # Goose 的秒级时间戳也接受源码规定的毫秒表示。
            ts = ""
            if isinstance(stamp, (int, float)):
                ts = iso_from_ms(stamp if stamp > 10_000_000_000 else stamp * 1000)
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                kind = block.get("type")
                if kind == "text" and role in ("user", "assistant", "system"):
                    event = message_event(role, as_text(block.get("text")), ts)
                    if event is not None:
                        events.append(event)
                elif kind == "toolRequest":
                    call = block.get("toolCall")
                    if not isinstance(call, dict):
                        continue
                    value = call.get("value")
                    value = value if isinstance(value, dict) else {}
                    event = tool_event(
                        str(value.get("name") or "tool"), as_text(value.get("arguments")),
                        as_text(call.get("error")), "error" if call.get("status") == "error" else "pending", ts,
                    )
                    if event is not None:
                        events.append(event)
                        binder.add(block.get("id"), event)
                elif kind == "toolResponse":
                    result = block.get("toolResult")
                    if not isinstance(result, dict):
                        continue
                    value = result.get("value")
                    value = value if isinstance(value, dict) else {}
                    failed = result.get("status") == "error" or value.get("isError") is True
                    text = as_text(result.get("error")) if result.get("status") == "error" else text_blocks(value.get("content"), ("text",))
                    binder.bind(block.get("id"), text, "error" if failed else "completed")

        return Session(
            harness=self.name, source=str(path), session_id=str(session_id),
            cwd=str(cwd or ""), started=str(started or ""),
        ), events

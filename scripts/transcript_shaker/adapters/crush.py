"""Crush 项目 SQLite 会话；messages.parts 是 type/data 包装数组。"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from ..model import Event, Session
from ._support import (
    ResultBinder, as_text, iso_from_ms, json_value, message_event,
    read_sqlite, sqlite_matches, tool_event,
)
from .base import Adapter

SCHEMA = {
    "sessions": ("id", "created_at"),
    "messages": ("id", "session_id", "role", "parts", "created_at"),
}


class CrushAdapter(Adapter):
    name = "crush"

    def detect(self, path: Path) -> bool:
        return sqlite_matches(path, SCHEMA)

    def parse(self, path: Path) -> Tuple[Session, List[Event]]:
        with read_sqlite(path) as conn:
            row = conn.execute(
                "SELECT id, created_at FROM sessions ORDER BY created_at DESC, rowid DESC LIMIT 1"
            ).fetchone()
            if row is None:
                raise RuntimeError(f"no session rows in {path}")
            session_id, created = row
            rows = conn.execute(
                "SELECT role, parts, created_at FROM messages WHERE session_id = ? ORDER BY created_at, rowid",
                (session_id,),
            ).fetchall()

        events: List[Event] = []
        binder = ResultBinder()
        for role, content, stamp in rows:
            parts = json_value(content)
            if not isinstance(parts, list):
                continue
            ts = iso_from_ms(stamp * 1000) if isinstance(stamp, (int, float)) else ""
            for part in parts:
                if not isinstance(part, dict) or not isinstance(part.get("data"), dict):
                    continue
                data = part["data"]
                kind = part.get("type")
                if kind == "text" and role in ("user", "assistant", "system"):
                    event = message_event(role, as_text(data.get("text")), ts)
                elif kind == "tool_call":
                    event = tool_event(str(data.get("name") or "tool"), as_text(data.get("input")), "", "pending", ts)
                    binder.add(data.get("id"), event)
                elif kind == "tool_result":
                    binder.bind(data.get("tool_call_id"), as_text(data.get("content")), "error" if data.get("is_error") else "completed")
                    continue
                elif kind == "shell_command":
                    event = tool_event("shell", as_text(data.get("command")), as_text(data.get("output")), "error" if data.get("exit_code") else "completed", ts)
                else:
                    continue
                if event is not None:
                    events.append(event)

        return Session(
            harness=self.name, source=str(path), session_id=str(session_id),
            started=iso_from_ms(created * 1000) if isinstance(created, (int, float)) else "",
        ), events

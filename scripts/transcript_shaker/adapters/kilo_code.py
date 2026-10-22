"""Kilo Code 会话（`~/.local/share/kilo/kilo.db`，SQLite）。

一个库里有全部历史会话，`message` 与 `part` 各存 JSON 文本：`message.data.role` 决定
`part` 的 text 归属，`part.data.type == "tool"` 自带调用参数与结果。
库可能有上百个会话与数十万 part，因此只解析最新的一个会话（`ORDER BY time_created DESC`）；
其它会话请先把库拆开或另开 change 支持会话选择。
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..model import Event, Session
from ._support import as_text, iso_from_ms, message_event, tool_event
from .base import Adapter

SQLITE_MAGIC = b"SQLite format 3\x00"
REQUIRED_TABLES = {"session", "message", "part"}
ROLE_MAP = {"user": "user", "assistant": "assistant"}


def _connect(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _load(data: Any) -> Dict[str, Any]:
    if not isinstance(data, str):
        return {}
    try:
        value = json.loads(data)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


class KiloCodeAdapter(Adapter):
    name = "kilo-code"

    def detect(self, path: Path) -> bool:
        if not path.is_file():
            return False
        try:
            with path.open("rb") as handle:
                if handle.read(len(SQLITE_MAGIC)) != SQLITE_MAGIC:
                    return False
        except OSError:
            return False
        try:
            with closing(_connect(path)) as conn:
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        except sqlite3.Error:
            return False
        return REQUIRED_TABLES <= tables

    def parse(self, path: Path) -> Tuple[Session, List[Event]]:
        with closing(_connect(path)) as conn:
            session_row = conn.execute(
                "SELECT id, directory, time_created FROM session ORDER BY time_created DESC LIMIT 1"
            ).fetchone()
            if session_row is None:
                raise RuntimeError(f"no session rows in {path}")
            session_id, directory, created = session_row

            roles = {
                str(message_id): ROLE_MAP.get(str(_load(data).get("role")), "")
                for message_id, data in conn.execute(
                    "SELECT id, data FROM message WHERE session_id = ? ORDER BY time_created", (session_id,)
                )
            }
            rows = conn.execute(
                "SELECT message_id, time_created, data FROM part WHERE session_id = ? ORDER BY time_created",
                (session_id,),
            ).fetchall()

        events: List[Event] = []
        for message_id, time_created, data in rows:
            part = _load(data)
            ts = iso_from_ms(time_created)
            ptype = part.get("type")
            if ptype == "text":
                role = roles.get(str(message_id), "")
                if not role:
                    continue
                event = message_event(role, as_text(part.get("text")), ts)
                if event is not None:
                    events.append(event)
            elif ptype == "tool":
                state = part.get("state")
                state = state if isinstance(state, dict) else {}
                event = tool_event(
                    str(part.get("tool") or "tool"),
                    as_text(state.get("input")),
                    as_text(state.get("output")),
                    str(state.get("status") or ""),
                    ts,
                )
                if event is not None:
                    events.append(event)

        session = Session(
            harness=self.name,
            source=str(path),
            session_id=str(session_id),
            cwd=str(directory or ""),
            started=iso_from_ms(created),
        )
        return session, events

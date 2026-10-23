"""OpenCode 与 Kilo 的同构 SQLite 会话库。

一个库里有全部历史会话，`message` 与 `part` 各存 JSON 文本：`message.data.role` 决定
`part` 的 text 归属，`part.data.type == "tool"` 自带调用参数与结果。
库可能有上百个会话与数十万 part，因此只解析最新的一个会话（`ORDER BY time_created DESC`）；
规范文件名或显式 harness 提示决定产品身份。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from ..model import Event, Session
from ._support import as_text, iso_from_ms, json_value, message_event, read_sqlite, sqlite_matches, tool_event
from .base import Adapter

SCHEMA = {
    "session": ("id", "directory", "time_created"),
    "message": ("id", "session_id", "time_created", "data"),
    "part": ("message_id", "session_id", "time_created", "data"),
}
ROLE_MAP = {"user": "user", "assistant": "assistant"}


class OpenCodeAdapter(Adapter):
    name = "opencode"

    def detect(self, path: Path) -> bool:
        return sqlite_matches(path, SCHEMA)

    def parse(self, path: Path) -> Tuple[Session, List[Event]]:
        with read_sqlite(path) as conn:
            session_row = conn.execute(
                "SELECT id, directory, time_created FROM session ORDER BY time_created DESC LIMIT 1"
            ).fetchone()
            if session_row is None:
                raise RuntimeError(f"no session rows in {path}")
            session_id, directory, created = session_row

            roles = {
                str(message_id): ROLE_MAP.get(str(payload.get("role")), "")
                for message_id, data in conn.execute(
                    "SELECT id, data FROM message WHERE session_id = ? ORDER BY time_created", (session_id,)
                )
                if isinstance(payload := json_value(data), dict)
            }
            rows = conn.execute(
                "SELECT message_id, time_created, data FROM part WHERE session_id = ? ORDER BY time_created",
                (session_id,),
            ).fetchall()

        events: List[Event] = []
        for message_id, time_created, data in rows:
            part = json_value(data)
            if not isinstance(part, dict):
                continue
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
                    as_text(state.get("output") or state.get("error")),
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


class KiloCodeAdapter(OpenCodeAdapter):
    name = "kilo-code"

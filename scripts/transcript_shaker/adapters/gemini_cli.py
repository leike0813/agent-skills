"""Gemini CLI 会话（`~/.gemini/tmp/<key>/chats/session-*.json`）。

整个会话是一个 JSON 文档：`{sessionId, projectHash, startTime, messages[]}`。
`messages[].type` 取 `user` / `gemini` / `info` / `error`；工具调用内联在 `toolCalls[]` 里，
结果也挂在同一个 toolCall 上，不需要按 id 回填。`thoughts[]` 一律丢弃。
`projectHash` 不可逆，cwd 留空。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..model import Event, Session
from ._support import as_text, load_json_doc, message_event, text_blocks, tool_event
from .base import Adapter


def _tool_result(call: Dict[str, Any]) -> str:
    results = call.get("result")
    if not isinstance(results, list) or not results:
        return ""
    first = results[0]
    response = first.get("functionResponse") if isinstance(first, dict) else None
    payload = response.get("response") if isinstance(response, dict) else None
    if not isinstance(payload, dict):
        return as_text(first)
    if "error" in payload:
        return as_text(payload.get("error"))
    return as_text(payload.get("output"))


class GeminiCliAdapter(Adapter):
    name = "gemini-cli"

    def detect(self, path: Path) -> bool:
        document = load_json_doc(path)
        if document is None:
            return False
        return (
            "sessionId" in document
            and "projectHash" in document
            and isinstance(document.get("messages"), list)
        )

    def parse(self, path: Path) -> Tuple[Session, List[Event]]:
        document = load_json_doc(path)
        if document is None:
            raise RuntimeError(f"cannot read JSON document: {path}")

        events: List[Event] = []
        for message in document.get("messages") or []:
            if not isinstance(message, dict):
                continue
            ts = str(message.get("timestamp") or "")
            mtype = message.get("type")
            content = message.get("content")

            if mtype == "user":
                event = message_event("user", text_blocks(content), ts)
                if event is not None:
                    events.append(event)
            elif mtype == "gemini":
                event = message_event("assistant", text_blocks(content), ts)
                if event is not None:
                    events.append(event)
                for call in message.get("toolCalls") or []:
                    if not isinstance(call, dict):
                        continue
                    tool = tool_event(
                        str(call.get("name") or "tool"),
                        as_text(call.get("args")),
                        _tool_result(call),
                        str(call.get("status") or ""),
                        ts,
                    )
                    if tool is not None:
                        events.append(tool)
            elif mtype in ("info", "error"):
                event = message_event("system", text_blocks(content), ts)
                if event is not None:
                    events.append(event)

        session = Session(
            harness=self.name,
            source=str(path),
            session_id=str(document.get("sessionId") or ""),
            started=str(document.get("startTime") or ""),
        )
        return session, events

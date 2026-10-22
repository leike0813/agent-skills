"""multicoder 会话（`~/.multicoder/content/ses_*.json`）。

单个 JSON 文档：`{sessionId, agentKey, configOptions[], messages[{role, parts[]}]}`。
parts 按 `type` 区分：`text` / `reasoning` / `tool-execute` / `tool-read` / `tool-edit` /
`tool-search` / `tool-other`。文档没有逐条时间戳，`ts` 一律留空。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..model import Event, Session
from ._support import as_text, load_json_doc, message_event, tool_event
from .base import Adapter

TOOL_PART_PREFIX = "tool-"


def _part_texts(parts: List[Any]) -> str:
    return "\n".join(
        part["text"]
        for part in parts
        if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str) and part["text"]
    )


def _part_result(part: Dict[str, Any]) -> str:
    output = part.get("output")
    if not isinstance(output, list):
        return as_text(output)
    texts: List[str] = []
    for entry in output:
        content = entry.get("content") if isinstance(entry, dict) else None
        text = content.get("text") if isinstance(content, dict) else None
        if isinstance(text, str) and text:
            texts.append(text)
    return "\n".join(texts)


class MulticoderAdapter(Adapter):
    name = "multicoder"

    def detect(self, path: Path) -> bool:
        document = load_json_doc(path)
        if document is None:
            return False
        return isinstance(document.get("configOptions"), list) and "agentKey" in document

    def parse(self, path: Path) -> Tuple[Session, List[Event]]:
        document = load_json_doc(path)
        if document is None:
            raise RuntimeError(f"cannot read JSON document: {path}")

        events: List[Event] = []
        for message in document.get("messages") or []:
            if not isinstance(message, dict):
                continue
            parts = message.get("parts")
            if not isinstance(parts, list) or not parts:
                continue
            role = message.get("role")

            if role == "user":
                event = message_event("user", _part_texts(parts), "")
                if event is not None:
                    events.append(event)
            elif role == "assistant":
                event = message_event("assistant", _part_texts(parts), "")
                if event is not None:
                    events.append(event)
                for part in parts:
                    if not isinstance(part, dict):
                        continue
                    ptype = str(part.get("type") or "")
                    if not ptype.startswith(TOOL_PART_PREFIX):
                        continue
                    tool = tool_event(
                        ptype,
                        as_text(part.get("input")),
                        _part_result(part),
                        str(part.get("state") or ""),
                        "",
                    )
                    if tool is not None:
                        events.append(tool)

        session = Session(
            harness=self.name,
            source=str(path),
            session_id=str(document.get("sessionId") or ""),
            cwd=str(document.get("cwd") or ""),
            started=str(document.get("updatedAt") or ""),
        )
        return session, events

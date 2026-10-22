"""CodeBuddy 会话（`~/.codebuddy/projects/<slug>/<uuid>.jsonl`）。

与 Claude 相近，但 content 块是 `input_text`/`output_text`，工具是独立记录
（`function_call` + `function_call_result`），时间戳是 epoch 毫秒。
`reasoning` 记录自带思考过程（另有 `rawContent`），任何字段都不输出。
`summary` 是首条 user 消息的截断副本，必须丢弃，否则正文重复。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..model import Event, Session
from ._support import ResultBinder, as_text, head_records, iso_from_ms, iter_records, message_event, tool_event
from .base import Adapter

TOOL_TYPES = {"function_call", "function_call_result"}


def _looks_like_codebuddy(record: Dict[str, Any]) -> bool:
    rtype = record.get("type")
    if rtype in TOOL_TYPES:
        return True
    if rtype != "message":
        return False
    content = record.get("content")
    if not isinstance(content, list):
        return False
    return any(isinstance(block, dict) and block.get("type") == "output_text" for block in content)


def _output_text(output: Any) -> str:
    if isinstance(output, dict):
        return as_text(output.get("text"))
    return as_text(output)


class CodeBuddyAdapter(Adapter):
    name = "codebuddy"

    def detect(self, path: Path) -> bool:
        try:
            return any(_looks_like_codebuddy(record) for record in head_records(path))
        except (OSError, RuntimeError):
            return False

    def parse(self, path: Path) -> Tuple[Session, List[Event]]:
        events: List[Event] = []
        binder = ResultBinder()
        session_id = ""
        cwd = ""
        started = ""

        for record in iter_records(path):
            ts = iso_from_ms(record.get("timestamp"))
            session_id = session_id or str(record.get("sessionId") or "")
            cwd = cwd or str(record.get("cwd") or "")
            started = started or ts

            rtype = record.get("type")
            if rtype == "message":
                role = record.get("role")
                block_type = {"user": "input_text", "assistant": "output_text"}.get(str(role))
                if block_type is None:
                    continue
                event = message_event(str(role), _blocks_text(record.get("content"), block_type), ts)
                if event is not None:
                    events.append(event)
            elif rtype == "function_call":
                event = tool_event(str(record.get("name") or "tool"), as_text(record.get("arguments")), "", "", ts)
                if event is not None:
                    events.append(event)
                    binder.add(record.get("callId"), event)
            elif rtype == "function_call_result":
                binder.bind(record.get("callId"), _output_text(record.get("output")), str(record.get("status") or ""))

        session = Session(
            harness=self.name,
            source=str(path),
            session_id=session_id,
            cwd=cwd,
            started=started,
        )
        return session, events


def _blocks_text(content: Any, block_type: str) -> str:
    if not isinstance(content, list):
        return ""
    return "\n".join(
        block["text"]
        for block in content
        if isinstance(block, dict) and block.get("type") == block_type and isinstance(block.get("text"), str) and block["text"]
    )

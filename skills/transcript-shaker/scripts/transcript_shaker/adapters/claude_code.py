"""Claude Code 会话（`~/.claude/projects/<slug>/<uuid>.jsonl`）。

同一轮回复被按 `apiBlockIndex` 拆成多条 `assistant` 记录，每条只含一个 content 块，
因此逐条映射即可，不要把同 `message.id` 的文本块拼起来。
`api-request*`、`attachment`、`file-history-*` 等是请求快照与 UI 状态，不是对话。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..model import Event, Session
from ._support import ResultBinder, as_text, head_records, iter_records, message_event, text_blocks, tool_event
from .base import Adapter

NOISE_TYPES = {
    "attachment",
    "ai-title",
    "agent-name",
    "last-prompt",
    "mode",
    "permission-mode",
    "api-request",
    "api-request-blob",
    "api-request-shape",
    "cost-state",
    "file-history-snapshot",
    "file-history-delta",
    "queue-operation",
    "atis-latch",
    "continued-in",
}

DIALOG_TYPES = {"user", "assistant"}


def _looks_like_claude(record: Dict[str, Any]) -> bool:
    rtype = record.get("type")
    if rtype in NOISE_TYPES:
        return True
    if rtype in DIALOG_TYPES:
        # qwen 也有 user/assistant，但它带 provenance。
        return (
            "uuid" in record
            and "parentUuid" in record
            and "sessionId" in record
            and "provenance" not in record
        )
    return False


def _result_text(content: Any) -> str:
    return text_blocks(content, ("text",)) if isinstance(content, list) else as_text(content)


class ClaudeCodeAdapter(Adapter):
    name = "claude-code"

    def detect(self, path: Path) -> bool:
        try:
            return any(_looks_like_claude(record) for record in head_records(path))
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

            if rtype == "assistant":
                content = message.get("content")
                if not isinstance(content, list):
                    continue
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
            elif rtype == "user":
                content = message.get("content")
                if isinstance(content, str):
                    event = message_event("user", content, ts)
                    if event is not None:
                        events.append(event)
                    continue
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    status = "error" if block.get("is_error") is True else "completed"
                    binder.bind(block.get("tool_use_id"), _result_text(block.get("content")), status)
            elif rtype == "system" and isinstance(record.get("content"), str):
                event = message_event("system", record["content"], ts)
                if event is not None:
                    events.append(event)

        session = Session(
            harness=self.name,
            source=str(path),
            session_id=session_id,
            cwd=cwd,
            started=started,
        )
        return session, events

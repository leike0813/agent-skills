"""Grok CLI 会话（`~/.grok/sessions/<percent-encoded-cwd>/<uuid>/chat_history.jsonl`）。

`chat_history.jsonl` 是唯一的对话流；同目录 `updates.jsonl`、`events.jsonl` 是同一内容
的增量/事件副本，读它会让正文重复，因此完全不碰。`summary.json` 只取元数据
（`info.cwd`、`created_at`）。记录没有时间戳，`ts` 留空。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..model import Event, Session
from ._support import ResultBinder, as_text, head_records, iter_records, load_json_doc, message_event, text_blocks, tool_event
from .base import Adapter

DIALOG_TYPES = {"system", "user", "assistant", "tool_result"}


def _looks_like_grok(record: Dict[str, Any]) -> bool:
    rtype = record.get("type")
    if rtype not in DIALOG_TYPES:
        return False
    if "message" in record or "payload" in record:
        return False
    if isinstance(record.get("tool_calls"), list) or "model_id" in record:
        return True
    return rtype == "tool_result" and "tool_call_id" in record


# 会话在模型回复前中断时没有 assistant/tool 记录，只能靠这些 grok 专有键认定。
GROK_MARKERS = ("synthetic_reason", "prompt_index", "model_id", "tool_calls", "tool_call_id")


def _looks_like_grok_file(records: List[Dict[str, Any]]) -> bool:
    """整份文件都是 `{type, content…}` 对话记录，且至少一条带 grok 专有键。"""
    if not records:
        return False
    if not any(key in record for record in records for key in GROK_MARKERS):
        return False
    for record in records:
        if record.get("type") not in DIALOG_TYPES:
            return False
        if "message" in record or "payload" in record:
            return False
    return True


class GrokAdapter(Adapter):
    name = "grok"

    def detect(self, path: Path) -> bool:
        try:
            records = head_records(path)
        except (OSError, RuntimeError):
            return False
        return any(_looks_like_grok(record) for record in records) or _looks_like_grok_file(records)

    def parse(self, path: Path) -> Tuple[Session, List[Event]]:
        events: List[Event] = []
        binder = ResultBinder()

        for record in iter_records(path):
            rtype = record.get("type")
            content = record.get("content")

            if rtype == "system":
                event = message_event("system", text_blocks(content), "")
                if event is not None:
                    events.append(event)
            elif rtype == "user":
                if record.get("synthetic_reason"):
                    continue
                event = message_event("user", text_blocks(content), "")
                if event is not None:
                    events.append(event)
            elif rtype == "assistant":
                event = message_event("assistant", text_blocks(content), "")
                if event is not None:
                    events.append(event)
                for call in record.get("tool_calls") or []:
                    if not isinstance(call, dict):
                        continue
                    tool = tool_event(str(call.get("name") or "tool"), as_text(call.get("arguments")), "", "", "")
                    if tool is not None:
                        events.append(tool)
                        binder.add(call.get("id"), tool)
            elif rtype == "tool_result":
                binder.bind(record.get("tool_call_id"), as_text(content), "completed")

        summary = load_json_doc(path.parent / "summary.json") or {}
        info = summary.get("info") if isinstance(summary.get("info"), dict) else {}
        session = Session(
            harness=self.name,
            source=str(path),
            session_id=path.parent.name,
            cwd=str(info.get("cwd") or ""),
            started=str(summary.get("created_at") or ""),
        )
        return session, events

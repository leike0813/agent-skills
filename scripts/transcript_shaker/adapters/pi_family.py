"""pi 系 harness：`pi`、`omp`、`minimax-code`。

三者共用 `{role, content[], …}` 的消息模型（user / developer / assistant / toolResult），
区别只在文件位置、会话头与记录外壳：
- pi / omp：JSONL，首条 `type=="session"`，omp 另有 `type=="title"` 槽位；
- minimax：每行是 `{message_id, turn_id, message}`，没有 `type`，会话头在 `manifest.json`。
omp 的 `type=="custom"`（含 `tool_execution_start`）是工具执行轨迹的副本，
读它会让工具数翻倍，因此非 message 记录一律跳过。
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
    load_json_doc,
    message_event,
    text_blocks,
    tool_event,
)
from .base import Adapter

MINIMAX_ROLES = {"user", "assistant", "toolResult"}


def _message_events(message: Dict[str, Any], ts: str, binder: ResultBinder, events: List[Event]) -> None:
    role = message.get("role")
    content = message.get("content")

    if role in ("user", "developer"):
        event = message_event("user" if role == "user" else "system", text_blocks(content, ("text",)), ts)
        if event is not None:
            events.append(event)
        return

    if role == "assistant":
        if isinstance(content, str):
            event = message_event("assistant", content, ts)
            if event is not None:
                events.append(event)
            return
        if not isinstance(content, list):
            return
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            event = None
            if btype == "text":
                event = message_event("assistant", as_text(block.get("text")), ts)
            elif btype == "toolCall":
                event = tool_event(str(block.get("name") or "tool"), as_text(block.get("arguments")), "", "", ts)
                binder.add(block.get("id"), event)
            if event is not None:
                events.append(event)
        return

    if role == "toolResult":
        status = "error" if message.get("isError") is True else "completed"
        binder.bind(message.get("toolCallId"), text_blocks(content, ("text",)), status)


def _parse_pi_like(path: Path, harness: str) -> Tuple[Session, List[Event]]:
    events: List[Event] = []
    binder = ResultBinder()
    meta: Dict[str, Any] = {}

    for record in iter_records(path):
        rtype = record.get("type")
        if rtype == "session":
            if not meta:
                meta = record
            continue
        if rtype != "message":
            continue
        message = record.get("message")
        if isinstance(message, dict):
            _message_events(message, str(record.get("timestamp") or ""), binder, events)

    session = Session(
        harness=harness,
        source=str(path),
        session_id=str(meta.get("id") or ""),
        cwd=str(meta.get("cwd") or ""),
        started=str(meta.get("timestamp") or ""),
    )
    return session, events


class PiAdapter(Adapter):
    name = "pi"

    def detect(self, path: Path) -> bool:
        try:
            records = head_records(path, 1)
        except (OSError, RuntimeError):
            return False
        if not records:
            return False
        first = records[0]
        return first.get("type") == "session" and isinstance(first.get("version"), int) and "pad" not in first

    def parse(self, path: Path) -> Tuple[Session, List[Event]]:
        return _parse_pi_like(path, self.name)


class OmpAdapter(Adapter):
    name = "omp"

    def detect(self, path: Path) -> bool:
        try:
            records = head_records(path, 1)
        except (OSError, RuntimeError):
            return False
        if not records:
            return False
        first = records[0]
        return first.get("type") == "title" and "pad" in first

    def parse(self, path: Path) -> Tuple[Session, List[Event]]:
        return _parse_pi_like(path, self.name)


class MinimaxAdapter(Adapter):
    name = "minimax-code"

    def detect(self, path: Path) -> bool:
        def matches(record: Dict[str, Any]) -> bool:
            message = record.get("message")
            return (
                "message_id" in record
                and "turn_id" in record
                and isinstance(message, dict)
                and message.get("role") in MINIMAX_ROLES
            )

        try:
            return any(matches(record) for record in head_records(path))
        except (OSError, RuntimeError):
            return False

    def parse(self, path: Path) -> Tuple[Session, List[Event]]:
        events: List[Event] = []
        binder = ResultBinder()
        for record in iter_records(path):
            message = record.get("message")
            if isinstance(message, dict):
                _message_events(message, "", binder, events)

        manifest = load_json_doc(path.parent / "manifest.json") or {}
        session = Session(
            harness=self.name,
            source=str(path),
            session_id=str(manifest.get("sessionId") or ""),
            started=iso_from_ms(manifest.get("createdAtMs")),
        )
        return session, events

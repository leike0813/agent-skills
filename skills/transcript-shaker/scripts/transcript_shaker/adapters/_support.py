"""各 adapter 共用的读取、内容提取与事件构造工具。

transcript 的存储方式只有四类：JSONL（可能 zstd 压缩）、单个 JSON 文档、SQLite、
以及事件日志（grok / kimi / dsh 的 JSONL 子集）。这里只提供与格式无关的部分，
各 harness 的字段映射仍留在自己的 adapter 里。
"""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

from ..model import Event

# detect 只需看文件头部；读到这么多条记录就够判定，避免整文件遍历。
DETECT_RECORD_LIMIT = 60

ZSTD_SUFFIXES = (".zst", ".zstd")


def as_text(value: Any) -> str:
    """字符串原样，None 变空串，其它按 JSON 文本（保留中文）。"""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)


def text_blocks(blocks: Any, types: Optional[Sequence[str]] = None) -> str:
    """从 content 块列表取正文，用换行连接。

    `blocks` 可以是字符串（原样返回）、块列表或其它（空串）。
    `types` 给定时只取 `type` 命中的块；不给则取所有带 `text` 键的块
    （qwen/gemini 的块没有 `type` 字段，只能按键取）。
    """
    if isinstance(blocks, str):
        return blocks
    if not isinstance(blocks, list):
        return ""
    parts: List[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if types is not None and block.get("type") not in types:
            continue
        text = block.get("text")
        if isinstance(text, str) and text:
            parts.append(text)
    return "\n".join(parts)


def join_argv(command: Any) -> str:
    if isinstance(command, str):
        return command
    if isinstance(command, list):
        return " ".join(shlex.quote(str(part)) for part in command)
    return ""


def iso_from_ms(value: Any) -> str:
    """epoch 毫秒 → ISO-8601 UTC（`2026-10-21T09:27:25.484Z`）；非数字返回空串。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ""
    stamp = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    return stamp.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def message_event(role: str, text: str, ts: str) -> Optional[Event]:
    if not text.strip():
        return None
    return Event(kind="message", role=role, text=text, ts=ts)


def tool_event(tool: str, call: str, result: str, status: str, ts: str) -> Optional[Event]:
    if not call and not result and not status:
        return None
    return Event(kind="tool", tool=tool, call=call, result=result, status=status, ts=ts)


def _decompress_lines(path: Path) -> Iterator[str]:
    try:
        from compression import zstd as zstd_module  # Python 3.14+
    except ImportError:
        zstd_module = None
    if zstd_module is not None:
        with zstd_module.open(path, "rt", encoding="utf-8", errors="replace") as handle:
            yield from handle
        return

    try:
        import zstandard as zstandard_module
    except ImportError:
        zstandard_module = None
    if zstandard_module is not None:
        with zstandard_module.open(path, "rt", encoding="utf-8", errors="replace") as handle:
            yield from handle
        return

    zstd_bin = shutil.which("zstd")
    if zstd_bin is None:
        raise RuntimeError(
            f"cannot decompress {path}：需要 Python 3.14 compression.zstd、zstandard 包或 zstd 命令行"
        )
    proc = subprocess.run([zstd_bin, "-dc", str(path)], capture_output=True)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"cannot decompress {path}：zstd 命令失败（{detail}）")
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        yield line


def iter_lines(path: Path) -> Iterator[str]:
    if path.name.endswith(ZSTD_SUFFIXES):
        yield from _decompress_lines(path)
        return
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        yield from handle


def iter_records(path: Path) -> Iterator[Dict[str, Any]]:
    """逐行解析；空行、坏行与非对象行直接跳过。"""
    for line in iter_lines(path):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            yield record


def _is_binary(path: Path) -> bool:
    """SQLite 库、压缩包等二进制文件在 detect 阶段就排除，避免按行解析上 GB 的脏数据。"""
    if path.name.endswith(ZSTD_SUFFIXES):
        return False
    try:
        with path.open("rb") as handle:
            return b"\x00" in handle.read(8192)
    except OSError:
        return True


def head_records(path: Path, limit: int = DETECT_RECORD_LIMIT) -> List[Dict[str, Any]]:
    """前 `limit` 条记录（detect 用）；读到 limit 或 EOF 即停。"""
    if _is_binary(path):
        return []
    records: List[Dict[str, Any]] = []
    for record in iter_records(path):
        records.append(record)
        if len(records) >= limit:
            break
    return records


def load_json_doc(path: Path) -> Optional[Dict[str, Any]]:
    """整个文件是一个 JSON 对象的格式（gemini/cline/multicoder）；失败返回 None。"""
    if _is_binary(path):
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    return document if isinstance(document, dict) else None


class ResultBinder:
    """工具调用与结果的按 id 回填：结果记录后到时改写先产出的 tool 事件。"""

    def __init__(self) -> None:
        self._pending: Dict[str, Event] = {}

    def add(self, call_id: Any, event: Optional[Event]) -> None:
        if call_id and event is not None:
            self._pending[str(call_id)] = event

    def bind(self, call_id: Any, result: str, status: str = "") -> None:
        if not call_id:
            return
        event = self._pending.get(str(call_id))
        if event is None:
            return
        if result:
            event.result = result
        if status:
            event.status = status

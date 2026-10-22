"""跨 harness 的候选 transcript 定位：只 stat，不解析内容。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Source:
    """一个 harness 的扫描根目录与相对 glob。"""

    root: str  # "~/.claude"；以 ~ 开头
    patterns: Tuple[str, ...]
    env: str = ""  # 非空时该环境变量优先于 root（codex 的 CODEX_HOME）
    skip: Tuple[str, ...] = ()  # 文件名 glob；命中即跳过（这些文件永远不是该 harness 的正文）


# 键必须与 adapters.ADAPTERS 的 name 一致。
HARNESS_SOURCES: Dict[str, Source] = {
    "codex": Source(
        "~/.codex", ("sessions/*/*/*/rollout-*", "archived_sessions/rollout-*"), env="CODEX_HOME"
    ),
    "claude-code": Source("~/.claude", ("projects/*/*.jsonl",)),
    "qwen-code": Source("~/.qwen", ("projects/*/chats/*.jsonl",)),
    "command-code": Source("~/.commandcode", ("projects/*/*.jsonl",), skip=("*.checkpoints.jsonl",)),
    "codebuddy": Source("~/.codebuddy", ("projects/*/*.jsonl",)),
    "gemini-cli": Source("~/.gemini", ("tmp/*/chats/session-*.json",)),
    "pi": Source("~/.pi", ("agent/sessions/*/*.jsonl",)),
    "omp": Source("~/.omp", ("agent/sessions/*/*.jsonl",)),
    "minimax-code": Source("~/.minimax", ("v2/sessions/*/*/*/*/messages.jsonl",)),
    "kilo-code": Source("~/.local/share/kilo", ("kilo.db",)),
    "cline": Source("~/.cline", ("data/sessions/*/*.messages.json",)),
    "multicoder": Source("~/.multicoder", ("content/ses_*.json",)),
    "grok": Source("~/.grok", ("sessions/*/*/chat_history.jsonl",)),
    "kimi-code": Source("~/.kimi-code", ("sessions/*/session_*/agents/main/wire.jsonl",)),
    "deepseek-harness": Source("~/.dsh", ("sessions/*/*/session*.jsonl.zstd",)),
}


@dataclass(frozen=True)
class Candidate:
    harness: str
    path: Path
    mtime: datetime  # 本地时间


def _root(source: Source) -> Path:
    """在调用时解析根目录，测试可用 HOME / CODEX_HOME 注入。"""
    if source.env and os.environ.get(source.env):
        return Path(os.environ[source.env]).expanduser()
    return Path(source.root).expanduser()


def find_candidates(
    harnesses: Optional[Sequence[str]] = None,
    since: Optional[date] = None,
    match: Optional[str] = None,
) -> List[Candidate]:
    found: Dict[Path, Candidate] = {}
    for name in harnesses or list(HARNESS_SOURCES):
        source = HARNESS_SOURCES[name]
        root = _root(source)
        for pattern in source.patterns:
            for path in root.glob(pattern):
                if any(path.match(skip) for skip in source.skip):
                    continue
                if not path.is_file():
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                if stat.st_size == 0:
                    continue
                mtime = datetime.fromtimestamp(stat.st_mtime)
                if since is not None and mtime.date() < since:
                    continue
                if match and match.lower() not in str(path).lower():
                    continue
                found.setdefault(path, Candidate(harness=name, path=path, mtime=mtime))
    return sorted(found.values(), key=lambda c: (-c.mtime.timestamp(), str(c.path)))


def render_candidates(items: List[Candidate]) -> str:
    lines = [f"# candidates: {len(items)}"]
    lines += [
        f"{c.mtime.strftime('%Y-%m-%dT%H:%M:%S')}\t{c.harness}\t{c.path}" for c in items
    ]
    return "\n".join(lines) + "\n"

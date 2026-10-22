"""所有 harness adapter 共用的输出契约：会话元数据与事件。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Event:
    kind: str            # "message" | "tool"
    role: str = ""       # 仅 message："user" | "assistant" | "system"
    text: str = ""       # 仅 message：正文
    tool: str = ""       # 仅 tool：展示名，如 "exec_command" / "mcp:playwright.browser_navigate"
    call: str = ""       # 仅 tool：调用内容（命令原文 / 参数 / prompt）
    result: str = ""     # 仅 tool：结果原文
    status: str = ""     # 仅 tool：状态
    ts: str = ""         # 来源行 timestamp（ISO-8601），无则空


@dataclass
class Session:
    harness: str
    source: str          # transcript 绝对路径
    session_id: str = ""
    cwd: str = ""
    started: str = ""    # session_meta.timestamp
    version: str = ""    # codex cli_version
    originator: str = "" # codex originator
    history: str = ""    # codex 的 "paginated"/"legacy"；其它 harness 留空

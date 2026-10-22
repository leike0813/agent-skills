"""adapter 注册表：按注册顺序做内容级识别。

顺序即优先级：先登记格式更特异的 harness，通用格式（pi 系、Claude 系）放后面，
避免某个 adapter 的宽判据把别人的文件抢走。`detect_adapter` 返回第一个命中者。
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from .base import Adapter
from .claude_code import ClaudeCodeAdapter
from .cline import ClineAdapter
from .codebuddy import CodeBuddyAdapter
from .codex import CodexAdapter
from .command_code import CommandCodeAdapter
from .deepseek_harness import DeepseekHarnessAdapter
from .gemini_cli import GeminiCliAdapter
from .grok import GrokAdapter
from .kilo_code import KiloCodeAdapter
from .kimi_code import KimiCodeAdapter
from .multicoder import MulticoderAdapter
from .pi_family import MinimaxAdapter, OmpAdapter, PiAdapter
from .qwen_code import QwenCodeAdapter


class UnsupportedTranscript(Exception):
    """文件内容不属于任何已注册 harness。"""


ADAPTERS: List[Adapter] = [
    CodexAdapter(),
    KimiCodeAdapter(),
    DeepseekHarnessAdapter(),
    CodeBuddyAdapter(),
    CommandCodeAdapter(),
    OmpAdapter(),
    MinimaxAdapter(),
    PiAdapter(),
    ClaudeCodeAdapter(),
    QwenCodeAdapter(),
    GrokAdapter(),
    GeminiCliAdapter(),
    ClineAdapter(),
    MulticoderAdapter(),
    KiloCodeAdapter(),
]


def detect_adapter(path: Path) -> Adapter:
    for adapter in ADAPTERS:
        if adapter.detect(path):
            return adapter
    raise UnsupportedTranscript(f"unsupported transcript format: {path}")


def supported_harnesses() -> str:
    return "、".join(adapter.name for adapter in ADAPTERS)

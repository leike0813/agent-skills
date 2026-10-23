"""adapter 注册表：按注册顺序做内容级识别。

顺序即优先级：先登记格式更特异的 harness，通用格式（pi 系、Claude 系）放后面，
避免某个 adapter 的宽判据把别人的文件抢走。`detect_adapter` 返回第一个命中者。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ._support import load_json_doc
from .base import Adapter
from .claude_code import ClaudeCodeAdapter
from .cline import ClineAdapter
from .codebuddy import CodeBuddyAdapter
from .codex import CodexAdapter
from .command_code import CommandCodeAdapter
from .continue_cli import ContinueCliAdapter
from .crush import CrushAdapter
from .deepseek_harness import DeepseekHarnessAdapter
from .gemini_cli import GeminiCliAdapter
from .grok import GrokAdapter
from .goose import GooseAdapter
from .opencode_family import KiloCodeAdapter, OpenCodeAdapter
from .kimi_code import KimiCodeAdapter
from .multicoder import MulticoderAdapter
from .pi_family import MinimaxAdapter, OmpAdapter, PiAdapter
from .qwen_code import QwenCodeAdapter
from .roo_code import RooCodeAdapter


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
    OpenCodeAdapter(),
    GooseAdapter(),
    CrushAdapter(),
    ContinueCliAdapter(),
    RooCodeAdapter(),
]


def detect_adapter(path: Path, harness: Optional[str] = None) -> Adapter:
    candidates = [a for a in ADAPTERS if a.name == harness] if harness else ADAPTERS
    for adapter in candidates:
        if adapter.detect(path):
            if not harness and isinstance(adapter, OpenCodeAdapter):
                name = {"kilo.db": "kilo-code", "opencode.db": "opencode"}.get(path.name)
                if name is None:
                    raise UnsupportedTranscript(
                        f"ambiguous SQLite transcript: {path}; use --harness opencode or --harness kilo-code"
                    )
                return next(a for a in ADAPTERS if a.name == name)
            if not harness and adapter.name == "roo-code":
                metadata = load_json_doc(path.parent / "history_item.json")
                if path.name != "api_conversation_history.json" and not (
                    metadata and isinstance(metadata.get("id"), str) and "workspace" in metadata
                ):
                    continue
            return adapter
    hint = f" for {harness}" if harness else ""
    raise UnsupportedTranscript(f"unsupported transcript format{hint}: {path}")


def supported_harnesses() -> str:
    return "、".join(adapter.name for adapter in ADAPTERS)

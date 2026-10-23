"""harness adapter 契约。"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from ..model import Event, Session


class Adapter:
    """验证 transcript 格式，并把原文解析为统一事件流；同构产品的身份由注册表消歧。"""

    name: str = ""

    def detect(self, path: Path) -> bool:
        """依据文件内容判断是否属于本 harness。"""
        raise NotImplementedError

    def parse(self, path: Path) -> Tuple[Session, List[Event]]:
        """返回会话元数据与按文件顺序排列的事件。"""
        raise NotImplementedError

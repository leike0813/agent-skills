"""极简 YAML 序列化：只支持 dict / list / str / int，输出可直接被 yaml.safe_load 读回。"""

from __future__ import annotations

import re
from typing import Any, Dict, List

# 只有这些标识符形状才用裸标量；路径、时间戳、含空格的串一律加双引号，
# 避免被 YAML 解析成数字、时间或其它类型。
_PLAIN = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")
_RESERVED = {"true", "false", "null", "yes", "no", "on", "off", "y", "n", "~"}


def to_yaml(value: Dict[str, Any]) -> str:
    """把顶层 mapping 序列化为 YAML 文本（以换行结尾）。"""
    return "\n".join(_mapping_lines(value, 0)) + "\n"


def _mapping_lines(mapping: Dict[str, Any], indent: int) -> List[str]:
    pad = " " * indent
    lines: List[str] = []
    for key, item in mapping.items():
        if isinstance(item, dict):
            lines.append(f"{pad}{key}:")
            lines += _mapping_lines(item, indent + 2)
        elif isinstance(item, list):
            if not item:
                lines.append(f"{pad}{key}: []")
            else:
                lines.append(f"{pad}{key}:")
                lines += _sequence_lines(item, indent + 2)
        elif isinstance(item, str) and "\n" in item:
            lines += _block_scalar(f"{pad}{key}: ", item, indent)
        else:
            lines.append(f"{pad}{key}: {_scalar(item)}")
    return lines


def _sequence_lines(items: List[Any], indent: int) -> List[str]:
    pad = " " * indent
    lines: List[str] = []
    for item in items:
        if isinstance(item, dict):
            body = _mapping_lines(item, indent + 2)
            lines.append(f"{pad}- {body[0].lstrip()}")
            lines += body[1:]
        else:
            lines.append(f"{pad}- {_scalar(item)}")
    return lines


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if value is None:
        return "null"
    text = str(value)
    if _PLAIN.fullmatch(text) and text.lower() not in _RESERVED:
        return text
    return _quoted(text)


def _quoted(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
    return f'"{escaped}"'


def _block_scalar(prefix: str, text: str, indent: int) -> List[str]:
    """多行文本用字面块；首行带空格、以两个以上换行结尾或只有换行时退回双引号。"""
    body = text[:-1] if text.endswith("\n") else text
    header = "|" if text.endswith("\n") else "|-"
    if not body or text.endswith("\n\n") or body[0] in " \t":
        return [prefix + _quoted(text)]
    pad = " " * (indent + 2)
    return [prefix + header] + [pad + line if line else "" for line in body.split("\n")]

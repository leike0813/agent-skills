#!/usr/bin/env python3
"""Reversible prose extraction and sentence analysis for Paper Humanizer.

The artifact is JSON encoded with a .yaml suffix. JSON is a YAML 1.2 subset,
which keeps the runtime dependency-free while preserving exact string data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


SCHEMA_VERSION = "paper-humanizer.document/v1"
FORMAT_VALUES = ("auto", "plain", "markdown", "quarto", "latex")
KIND_VALUES = {"prose", "protected"}
EFFECT_VALUES = {"text", "zero", "one", "boundary"}
UTF8_BOM = b"\xef\xbb\xbf"
PLACEHOLDER = "¤"
RELIABILITY_WARNING = (
    "fewer than five eligible sentences; distributional interpretation is unreliable"
)

EXTENSION_FORMATS = {
    ".txt": "plain",
    ".text": "plain",
    ".md": "markdown",
    ".markdown": "markdown",
    ".mdown": "markdown",
    ".qmd": "quarto",
    ".tex": "latex",
    ".latex": "latex",
}

ABBREVIATIONS = {
    "mr.",
    "mrs.",
    "ms.",
    "dr.",
    "prof.",
    "sr.",
    "jr.",
    "vs.",
    "etc.",
    "e.g.",
    "i.e.",
    "fig.",
    "eq.",
    "al.",
    "cf.",
    "u.s.",
    "u.k.",
}

LATEX_TEXT_COMMANDS = {
    "section",
    "subsection",
    "subsubsection",
    "paragraph",
    "subparagraph",
    "title",
    "caption",
    "footnote",
    "emph",
    "textbf",
    "textit",
    "textrm",
    "textsf",
    "underline",
}

LATEX_PROTECTED_ENVIRONMENTS = {
    "verbatim",
    "Verbatim",
    "lstlisting",
    "minted",
    "equation",
    "equation*",
    "align",
    "align*",
    "alignat",
    "alignat*",
    "gather",
    "gather*",
    "multline",
    "multline*",
    "displaymath",
    "math",
    "thebibliography",
    "tikzpicture",
}

CLOSING_PUNCTUATION = "\"'”’»)]}）】》」』"


class PipelineError(Exception):
    """Expected, user-actionable pipeline failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class JsonArgumentParser(argparse.ArgumentParser):
    """Route argparse failures through the stable JSON error envelope."""

    def error(self, message: str) -> None:
        raise PipelineError("invalid_arguments", message)


@dataclass(frozen=True, order=True)
class Interval:
    start: int
    end: int
    role: str
    effect: str = "zero"


@dataclass(frozen=True)
class SentenceSpan:
    start: int
    end: int
    text: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(encoded)


def stdout_envelope(
    *,
    ok: bool,
    command: str,
    artifact: str | None,
    summary: dict[str, Any] | None,
    error: dict[str, str] | None,
) -> None:
    payload = {
        "ok": ok,
        "command": command,
        "artifact": artifact,
        "summary": summary or {},
        "error": error,
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def write_atomic(path: Path, data: bytes, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise PipelineError(
            "output_exists",
            f"destination already exists; pass --overwrite to replace it: {path}",
        )
    if not path.parent.is_dir():
        raise PipelineError("missing_output_directory", f"output directory does not exist: {path.parent}")

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary_path = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists() and not overwrite:
            raise PipelineError("output_exists", f"destination appeared during write: {path}")
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def read_utf8_source(path: Path) -> tuple[bytes, str, bool]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PipelineError("input_read_failed", f"cannot read input: {path}: {exc}") from exc
    has_bom = raw.startswith(UTF8_BOM)
    content = raw[len(UTF8_BOM) :] if has_bom else raw
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PipelineError("invalid_utf8", f"input is not valid UTF-8: {path}") from exc
    return raw, text, has_bom


def load_artifact(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PipelineError("artifact_read_failed", f"cannot read artifact: {path}: {exc}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PipelineError(
            "invalid_artifact_json",
            f"artifact must use the JSON-compatible YAML contract: {exc}",
        ) from exc
    if not isinstance(payload, dict):
        raise PipelineError("invalid_artifact", "artifact root must be an object")
    return payload


def dump_artifact(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def infer_format(path: Path, requested: str) -> str:
    if requested != "auto":
        return requested
    detected = EXTENSION_FORMATS.get(path.suffix.lower())
    if detected is None:
        raise PipelineError(
            "unknown_format",
            f"cannot infer source format from extension {path.suffix!r}; pass --format explicitly",
        )
    return detected


def overlaps(interval: Interval, existing: Iterable[Interval]) -> bool:
    return any(interval.start < item.end and item.start < interval.end for item in existing)


def add_interval(
    intervals: list[Interval],
    start: int,
    end: int,
    role: str,
    effect: str = "zero",
) -> bool:
    if start >= end:
        return False
    candidate = Interval(start, end, role, effect)
    if overlaps(candidate, intervals):
        return False
    intervals.append(candidate)
    return True


def position_is_protected(position: int, intervals: Iterable[Interval]) -> bool:
    return any(item.start <= position < item.end for item in intervals)


def line_number(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def build_segments(text: str, intervals: list[Interval], default_role: str) -> list[dict[str, Any]]:
    ordered = sorted(intervals)
    cursor = 0
    raw_segments: list[tuple[int, int, str, str, str]] = []
    for interval in ordered:
        if interval.start < cursor:
            raise PipelineError("overlapping_segments", "internal parser produced overlapping intervals")
        if cursor < interval.start:
            raw_segments.append((cursor, interval.start, "prose", default_role, "text"))
        raw_segments.append((interval.start, interval.end, "protected", interval.role, interval.effect))
        cursor = interval.end
    if cursor < len(text):
        raw_segments.append((cursor, len(text), "prose", default_role, "text"))

    segments: list[dict[str, Any]] = []
    for index, (start, end, kind, role, effect) in enumerate(raw_segments, start=1):
        value = text[start:end]
        if not value:
            continue
        segments.append(
            {
                "id": f"seg-{index:06d}",
                "kind": kind,
                "role": role,
                "locator": {
                    "line_start": line_number(text, start),
                    "line_end": line_number(text, max(start, end - 1)),
                },
                "text": value,
                "analysis_effect": effect,
                "checksum": sha256_bytes(value.encode("utf-8")) if kind == "protected" else None,
            }
        )
    return segments


def add_blank_line_intervals(text: str, intervals: list[Interval]) -> None:
    for match in re.finditer(r"(?:\r\n|\n|\r)[ \t]*(?:\r\n|\n|\r)+", text):
        add_interval(intervals, match.start(), match.end(), "paragraph_separator", "boundary")


def segment_plain(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    intervals: list[Interval] = []
    add_blank_line_intervals(text, intervals)
    return build_segments(text, intervals, "paragraph"), []


def line_offsets(text: str) -> list[tuple[int, str]]:
    output: list[tuple[int, str]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        output.append((offset, line))
        offset += len(line)
    if offset < len(text) or not output:
        output.append((offset, text[offset:]))
    return output


def add_markdown_frontmatter(text: str, intervals: list[Interval]) -> None:
    lines = line_offsets(text)
    if not lines or lines[0][1].strip("\r\n") != "---":
        return
    for offset, line in lines[1:]:
        if line.strip("\r\n") in {"---", "..."}:
            add_interval(intervals, 0, offset + len(line), "frontmatter", "boundary")
            return
    raise PipelineError("unclosed_frontmatter", "Markdown frontmatter has no closing delimiter")


def add_markdown_fences(text: str, intervals: list[Interval]) -> None:
    lines = line_offsets(text)
    active: tuple[str, int, int] | None = None
    for offset, line in lines:
        if active is not None:
            char, length, start = active
            if re.match(rf"^ {{0,3}}{re.escape(char)}{{{length},}}[ \t]*(?:\r?\n|$)", line):
                add_interval(intervals, start, offset + len(line), "code_fence", "boundary")
                active = None
            continue
        if position_is_protected(offset, intervals):
            continue
        match = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if match:
            fence = match.group(1)
            active = (fence[0], len(fence), offset)
    if active is not None:
        raise PipelineError("unclosed_code_fence", "Markdown code fence has no closing fence")


def add_delimited_pairs(
    text: str,
    intervals: list[Interval],
    opener: str,
    closer: str,
    role: str,
    effect: str,
    *,
    unclosed_is_error: bool,
) -> None:
    cursor = 0
    while cursor < len(text):
        start = text.find(opener, cursor)
        if start < 0:
            return
        if start > 0 and text[start - 1] == "\\":
            cursor = start + len(opener)
            continue
        if position_is_protected(start, intervals):
            cursor = start + len(opener)
            continue
        end = text.find(closer, start + len(opener))
        while end >= 0 and end > 0 and text[end - 1] == "\\":
            end = text.find(closer, end + len(closer))
        if end < 0:
            if unclosed_is_error:
                raise PipelineError("unclosed_delimiter", f"unclosed {role} delimiter {opener!r}")
            cursor = start + len(opener)
            continue
        add_interval(intervals, start, end + len(closer), role, effect)
        cursor = end + len(closer)


def add_markdown_inline_code(text: str, intervals: list[Interval]) -> None:
    cursor = 0
    while cursor < len(text):
        start = text.find("`", cursor)
        if start < 0:
            return
        if position_is_protected(start, intervals):
            cursor = start + 1
            continue
        length = 1
        while start + length < len(text) and text[start + length] == "`":
            length += 1
        delimiter = "`" * length
        end = text.find(delimiter, start + length)
        if end < 0:
            raise PipelineError("unclosed_inline_code", "Markdown inline code has no closing delimiter")
        add_interval(intervals, start, end + length, "inline_code", "one")
        cursor = end + length


def add_markdown_links(text: str, intervals: list[Interval]) -> None:
    for match in re.finditer(r"!\[[^\]\n]*\]\([^\)\n]*\)", text):
        add_interval(intervals, match.start(), match.end(), "image", "zero")

    pattern = re.compile(r"\[([^\]\n]+)\]\(([^\)\n]*)\)")
    for match in pattern.finditer(text):
        if overlaps(Interval(match.start(), match.end(), "link"), intervals):
            continue
        label_start, label_end = match.span(1)
        target_start, target_end = match.span(2)
        add_interval(intervals, match.start(), label_start, "link_markup", "zero")
        add_interval(intervals, label_end, target_start, "link_markup", "zero")
        add_interval(intervals, target_start, target_end, "link_target", "zero")
        add_interval(intervals, target_end, match.end(), "link_markup", "zero")


def add_quarto_fenced_divs(text: str, intervals: list[Interval]) -> None:
    stack: list[int] = []
    opening_pattern = re.compile(
        r"^ {0,3}:{3,}[ \t]+(?:\{[^{}\r\n]+\}|[.#][^\r\n]*?)(?::+)?[ \t]*$"
    )
    closing_pattern = re.compile(r"^ {0,3}:{3,}[ \t]*$")

    for offset, line in line_offsets(text):
        if position_is_protected(offset, intervals):
            continue
        stripped = line.rstrip("\r\n")
        if opening_pattern.fullmatch(stripped):
            stack.append(offset)
            add_interval(intervals, offset, offset + len(line), "quarto_fenced_div", "boundary")
        elif closing_pattern.fullmatch(stripped):
            if stack:
                stack.pop()
            add_interval(intervals, offset, offset + len(line), "quarto_fenced_div", "boundary")

    if stack:
        raise PipelineError(
            "unclosed_fenced_div",
            f"Quarto fenced div opened on line {line_number(text, stack[-1])} has no closing fence",
        )


def containing_line_is_otherwise_blank(text: str, start: int, end: int) -> bool:
    line_start = max(text.rfind("\n", 0, start), text.rfind("\r", 0, start)) + 1
    following_breaks = [
        position
        for position in (text.find("\r", end), text.find("\n", end))
        if position >= 0
    ]
    line_end = min(following_breaks) if following_breaks else len(text)
    return not text[line_start:start].strip() and not text[end:line_end].strip()


def add_quarto_shortcodes(text: str, intervals: list[Interval]) -> None:
    cursor = 0
    while cursor < len(text):
        start = text.find("{{<", cursor)
        if start < 0:
            return
        if position_is_protected(start, intervals):
            cursor = start + 3
            continue
        end = text.find(">}}", start + 3)
        if end < 0:
            raise PipelineError("unclosed_shortcode", "Quarto shortcode has no closing delimiter")
        end += 3
        effect = "boundary" if containing_line_is_otherwise_blank(text, start, end) else "one"
        add_interval(intervals, start, end, "quarto_shortcode", effect)
        cursor = end


def add_quarto_references(text: str, intervals: list[Interval]) -> None:
    pattern = re.compile(r"(?<![\w@])(?:-?@[A-Za-z0-9][A-Za-z0-9_.:/-]*)")
    for match in pattern.finditer(text):
        add_interval(intervals, match.start(), match.end(), "quarto_reference", "zero")


def add_quarto_attributes(text: str, intervals: list[Interval]) -> None:
    pattern = re.compile(
        r"\{(?=[^{}\r\n]*(?:[#.][A-Za-z0-9_-]+|[A-Za-z_:][A-Za-z0-9_.:-]*[ \t]*=))"
        r"[^{}\r\n]*\}"
    )
    for match in pattern.finditer(text):
        if match.start() > 0 and text[match.start() - 1] == "\\":
            continue
        add_interval(intervals, match.start(), match.end(), "quarto_attribute", "zero")


def segment_markdown_family(
    text: str,
    source_format: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    intervals: list[Interval] = []
    warnings: list[str] = []
    add_markdown_frontmatter(text, intervals)
    add_markdown_fences(text, intervals)
    if source_format == "quarto":
        add_quarto_fenced_divs(text, intervals)
        add_quarto_shortcodes(text, intervals)
        add_quarto_references(text, intervals)
        add_quarto_attributes(text, intervals)

    cursor = 0
    while True:
        start = text.find("<!--", cursor)
        if start < 0:
            break
        if position_is_protected(start, intervals):
            cursor = start + 4
            continue
        end = text.find("-->", start + 4)
        if end < 0:
            raise PipelineError("unclosed_html_comment", "Markdown HTML comment has no closing marker")
        add_interval(intervals, start, end + 3, "html_comment", "zero")
        cursor = end + 3

    for match in re.finditer(r"(?m)^(?: {4}|\t).*?(?:\r?\n|$)", text):
        add_interval(intervals, match.start(), match.end(), "indented_code", "boundary")

    add_markdown_inline_code(text, intervals)
    add_delimited_pairs(text, intervals, "$$", "$$", "display_math", "boundary", unclosed_is_error=True)
    add_delimited_pairs(text, intervals, "\\[", "\\]", "display_math", "boundary", unclosed_is_error=True)
    add_delimited_pairs(text, intervals, "\\(", "\\)", "inline_math", "one", unclosed_is_error=True)
    add_delimited_pairs(text, intervals, "$", "$", "inline_math", "one", unclosed_is_error=False)

    for match in re.finditer(r"\[(?:\d+(?:\s*[-,]\s*\d+)*)\]", text):
        add_interval(intervals, match.start(), match.end(), "citation", "zero")
    add_markdown_links(text, intervals)

    for match in re.finditer(r"<https?://[^>\n]+>|<mailto:[^>\n]+>", text):
        add_interval(intervals, match.start(), match.end(), "autolink", "zero")
    for match in re.finditer(r"</?[A-Za-z][^>\n]*>", text):
        add_interval(intervals, match.start(), match.end(), "html_tag", "zero")

    for offset, line in line_offsets(text):
        if position_is_protected(offset, intervals):
            continue
        stripped = line.rstrip("\r\n")
        if re.match(r"^\s{0,3}(?:[-*_]\s*){3,}$", stripped):
            add_interval(intervals, offset, offset + len(line), "thematic_break", "boundary")
            continue
        if re.match(r"^\s*\|?\s*:?-{3,}", stripped) and "|" in stripped:
            add_interval(intervals, offset, offset + len(line), "table_delimiter", "boundary")
            continue
        marker = re.match(r"^(\s{0,3}(?:#{1,6}\s+|>\s?|[-+*]\s+|\d+[.)]\s+))", line)
        if marker:
            add_interval(intervals, offset, offset + len(marker.group(1)), "block_marker", "zero")
        for pipe in re.finditer(r"\|", line):
            add_interval(intervals, offset + pipe.start(), offset + pipe.end(), "table_marker", "zero")

    for match in re.finditer(r"(?<!\\)(?:\*\*|__|~~|\*|_)", text):
        add_interval(intervals, match.start(), match.end(), "inline_markup", "zero")
    add_blank_line_intervals(text, intervals)
    return build_segments(text, intervals, f"{source_format}_prose"), warnings


def matching_group_end(text: str, start: int, opener: str, closer: str) -> int:
    if start >= len(text) or text[start] != opener:
        raise PipelineError("invalid_group", f"expected {opener!r} at offset {start}")
    depth = 0
    position = start
    while position < len(text):
        char = text[position]
        if char == "\\":
            position += 2
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return position + 1
        position += 1
    raise PipelineError("unclosed_group", f"unclosed {opener}{closer} group at offset {start}")


def add_latex_environments(text: str, intervals: list[Interval]) -> None:
    token_pattern = re.compile(r"\\(begin|end)\{([^{}]+)\}")
    stack: list[tuple[str, int]] = []
    for match in token_pattern.finditer(text):
        if position_is_protected(match.start(), intervals):
            continue
        kind, name = match.group(1), match.group(2)
        if kind == "begin":
            stack.append((name, match.start()))
            continue
        if not stack or stack[-1][0] != name:
            raise PipelineError("unbalanced_environment", f"unexpected \\end{{{name}}}")
        open_name, start = stack.pop()
        if open_name in LATEX_PROTECTED_ENVIRONMENTS:
            add_interval(intervals, start, match.end(), f"latex_environment:{open_name}", "boundary")
    if stack:
        name, _ = stack[-1]
        raise PipelineError("unclosed_environment", f"LaTeX environment has no closing \\end{{{name}}}")


def add_latex_comments(text: str, intervals: list[Interval]) -> None:
    for match in re.finditer(r"(?<!\\)%[^\r\n]*", text):
        add_interval(intervals, match.start(), match.end(), "latex_comment", "zero")


def command_token(text: str, start: int) -> tuple[str, int]:
    if start + 1 >= len(text):
        return "", start + 1
    match = re.match(r"\\([A-Za-z@]+\*?|.)", text[start:])
    if not match:
        return "", start + 1
    raw_name = match.group(1)
    return raw_name.rstrip("*"), start + len(match.group(0))


def consume_command_groups(text: str, position: int) -> int:
    cursor = position
    while True:
        whitespace_start = cursor
        while cursor < len(text) and text[cursor] in " \t":
            cursor += 1
        if cursor < len(text) and text[cursor] == "[":
            cursor = matching_group_end(text, cursor, "[", "]")
            continue
        if cursor < len(text) and text[cursor] == "{":
            cursor = matching_group_end(text, cursor, "{", "}")
            continue
        return whitespace_start if cursor > whitespace_start else cursor


def add_latex_commands(text: str, intervals: list[Interval]) -> None:
    cursor = 0
    while cursor < len(text):
        start = text.find("\\", cursor)
        if start < 0:
            return
        if position_is_protected(start, intervals):
            cursor = start + 1
            continue
        name, token_end = command_token(text, start)
        if not name:
            add_interval(intervals, start, token_end, "latex_command", "zero")
            cursor = token_end
            continue

        if name in LATEX_TEXT_COMMANDS:
            add_interval(intervals, start, token_end, f"latex_command:{name}", "zero")
            group_cursor = token_end
            while group_cursor < len(text) and text[group_cursor] in " \t":
                group_cursor += 1
            if group_cursor < len(text) and text[group_cursor] == "[":
                optional_end = matching_group_end(text, group_cursor, "[", "]")
                add_interval(intervals, token_end, optional_end, "latex_option", "zero")
                group_cursor = optional_end
                while group_cursor < len(text) and text[group_cursor] in " \t":
                    group_cursor += 1
            if group_cursor >= len(text) or text[group_cursor] != "{":
                raise PipelineError("missing_text_argument", f"\\{name} has no text argument")
            group_end = matching_group_end(text, group_cursor, "{", "}")
            add_interval(intervals, token_end, group_cursor + 1, "latex_markup", "zero")
            add_interval(intervals, group_end - 1, group_end, "latex_markup", "zero")
            cursor = group_cursor + 1
            continue

        end = consume_command_groups(text, token_end)
        if end <= token_end:
            end = token_end
        effect = "boundary" if name in {"begin", "end"} else "zero"
        add_interval(intervals, start, end, f"latex_command:{name}", effect)
        cursor = end


def validate_latex_braces(text: str, intervals: list[Interval]) -> None:
    depth = 0
    position = 0
    while position < len(text):
        if position_is_protected(position, intervals):
            position += 1
            continue
        char = text[position]
        if char == "\\":
            position += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                raise PipelineError("unbalanced_braces", "LaTeX contains an unmatched closing brace")
        position += 1
    if depth:
        raise PipelineError("unbalanced_braces", "LaTeX contains an unmatched opening brace")


def segment_latex(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    intervals: list[Interval] = []
    warnings: list[str] = []
    add_latex_comments(text, intervals)
    add_latex_environments(text, intervals)
    add_delimited_pairs(text, intervals, "$$", "$$", "display_math", "boundary", unclosed_is_error=True)
    add_delimited_pairs(text, intervals, "\\[", "\\]", "display_math", "boundary", unclosed_is_error=True)
    add_delimited_pairs(text, intervals, "\\(", "\\)", "inline_math", "one", unclosed_is_error=True)
    add_delimited_pairs(text, intervals, "$", "$", "inline_math", "one", unclosed_is_error=True)
    validate_latex_braces(text, intervals)
    add_latex_commands(text, intervals)

    for match in re.finditer(r"(?<!\\)[{}&#_^]", text):
        add_interval(intervals, match.start(), match.end(), "latex_markup", "zero")
    add_blank_line_intervals(text, intervals)
    return build_segments(text, intervals, "latex_prose"), warnings


def segment_source(text: str, source_format: str) -> tuple[list[dict[str, Any]], list[str]]:
    if source_format == "plain":
        return segment_plain(text)
    if source_format in {"markdown", "quarto"}:
        return segment_markdown_family(text, source_format)
    if source_format == "latex":
        return segment_latex(text)
    raise PipelineError("unsupported_format", f"unsupported source format: {source_format}")


def manifest_payload(document: dict[str, Any]) -> dict[str, Any]:
    source = document["source"]
    segments = document["segments"]
    return {
        "schema_version": document["schema_version"],
        "source_format": source["format"],
        "byte_order_mark": source["byte_order_mark"],
        "segments": [
            {
                "id": item["id"],
                "kind": item["kind"],
                "role": item["role"],
                "locator": item["locator"],
                "analysis_effect": item["analysis_effect"],
                "checksum": item["checksum"],
            }
            for item in segments
        ],
    }


def analysis_input(document: dict[str, Any]) -> tuple[str, list[str | None]]:
    chunks: list[str] = []
    mapping: list[str | None] = []
    for segment in document["segments"]:
        effect = segment["analysis_effect"]
        if segment["kind"] == "prose" or effect == "text":
            value = segment["text"]
        elif effect == "one":
            value = PLACEHOLDER
        elif effect == "boundary":
            value = "\n\n"
        else:
            value = ""
        chunks.append(value)
        mapping.extend([segment["id"]] * len(value))
    return "".join(chunks), mapping


def analysis_content_hash(document: dict[str, Any]) -> str:
    payload = [
        {
            "id": segment["id"],
            "kind": segment["kind"],
            "effect": segment["analysis_effect"],
            "text": segment["text"],
        }
        for segment in document["segments"]
    ]
    return canonical_hash(payload)


def period_is_exception(text: str, position: int) -> bool:
    previous = text[position - 1] if position else ""
    following = text[position + 1] if position + 1 < len(text) else ""
    if previous.isdigit() and following.isdigit():
        return True

    token_start = position
    while token_start > 0 and not text[token_start - 1].isspace():
        token_start -= 1
    token_end = position + 1
    while token_end < len(text) and not text[token_end].isspace():
        token_end += 1
    token = text[token_start:token_end].strip(CLOSING_PUNCTUATION + ",;:").lower()
    if "://" in token or token.startswith("www.") or "@" in token:
        return True
    prefix = text[token_start : position + 1].lower()
    if any(prefix.endswith(abbreviation) for abbreviation in ABBREVIATIONS):
        return True
    if re.search(r"(?:^|\s)(?:[A-Z]\.)+$", text[max(0, token_start - 1) : position + 1]):
        return True
    return False


def split_sentences(text: str) -> list[SentenceSpan]:
    spans: list[SentenceSpan] = []
    start = 0
    position = 0
    while position < len(text):
        char = text[position]
        if char not in ".?!。？！":
            position += 1
            continue
        if char == "." and period_is_exception(text, position):
            position += 1
            continue
        end = position + 1
        while end < len(text) and text[end] in CLOSING_PUNCTUATION:
            end += 1
        candidate = text[start:end]
        if candidate.strip():
            spans.append(SentenceSpan(start, end, candidate.strip()))
        start = end
        position = end
    if text[start:].strip():
        spans.append(SentenceSpan(start, len(text), text[start:].strip()))
    return spans


def count_length_units(text: str) -> tuple[int, bool, bool]:
    cleaned = re.sub(r"\[(?:\d+(?:\s*[-,]\s*\d+)*)\]", "", text)
    cleaned = re.sub(r"https?://\S+|www\.\S+", PLACEHOLDER, cleaned)
    han_count = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", cleaned))
    placeholder_count = cleaned.count(PLACEHOLDER)
    latin_tokens = re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", cleaned)
    return han_count + placeholder_count + len(latin_tokens), han_count > 0, placeholder_count > 0


def median_of_halves(values: Sequence[int]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    ordered = sorted(values)
    if len(ordered) == 1:
        value = float(ordered[0])
        return value, value
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        lower = ordered[:midpoint]
        upper = ordered[midpoint + 1 :]
    else:
        lower = ordered[:midpoint]
        upper = ordered[midpoint:]
    return float(statistics.median(lower)), float(statistics.median(upper))


def uniform_runs(sentences: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    start = 0
    while start < len(sentences):
        longest = -1
        for end in range(start + 4, len(sentences) + 1):
            lengths = [item["length"] for item in sentences[start:end]]
            median = statistics.median(lengths)
            tolerance = max(2.0, median * 0.10)
            if max(lengths) - min(lengths) <= tolerance:
                longest = end
            elif longest >= 0:
                break
        if longest >= 0:
            group = sentences[start:longest]
            segment_ids: list[str] = []
            for sentence in group:
                for segment_id in sentence["segment_ids"]:
                    if segment_id not in segment_ids:
                        segment_ids.append(segment_id)
            output.append(
                {
                    "sentence_start": group[0]["id"],
                    "sentence_end": group[-1]["id"],
                    "segment_ids": segment_ids,
                    "lengths": [item["length"] for item in group],
                }
            )
            start = longest
        else:
            start += 1
    return output


def build_analysis(document: dict[str, Any], inherited_warnings: Sequence[str]) -> dict[str, Any]:
    stream, mapping = analysis_input(document)
    spans = split_sentences(stream)
    sentences: list[dict[str, Any]] = []
    has_han = False
    has_placeholder = False
    for index, span in enumerate(spans, start=1):
        length, sentence_has_han, sentence_has_placeholder = count_length_units(span.text)
        if length == 0:
            continue
        has_han = has_han or sentence_has_han
        has_placeholder = has_placeholder or sentence_has_placeholder
        segment_ids: list[str] = []
        for segment_id in mapping[span.start : span.end]:
            if segment_id is not None and segment_id not in segment_ids:
                segment_ids.append(segment_id)
        sentences.append(
            {
                "id": f"sent-{index:06d}",
                "segment_ids": segment_ids,
                "length": length,
            }
        )

    lengths = [item["length"] for item in sentences]
    q1, q3 = median_of_halves(lengths)
    if lengths:
        mean = statistics.fmean(lengths)
        population_stddev = statistics.pstdev(lengths)
        coefficient = population_stddev / mean if mean else None
        stats = {
            "mean": round(mean, 3),
            "median": round(float(statistics.median(lengths)), 3),
            "population_stddev": round(population_stddev, 3),
            "coefficient_of_variation": round(coefficient, 3) if coefficient is not None else None,
            "q1": round(q1, 3) if q1 is not None else None,
            "q3": round(q3, 3) if q3 is not None else None,
            "minimum": min(lengths),
            "maximum": max(lengths),
        }
    else:
        stats = {
            "mean": None,
            "median": None,
            "population_stddev": None,
            "coefficient_of_variation": None,
            "q1": None,
            "q3": None,
            "minimum": None,
            "maximum": None,
        }

    warnings = list(dict.fromkeys(inherited_warnings))
    reliable = len(sentences) >= 5
    if not reliable and RELIABILITY_WARNING not in warnings:
        warnings.append(RELIABILITY_WARNING)
    return {
        "content_sha256": analysis_content_hash(document),
        "unit_label": "length_units" if has_han or has_placeholder else "words",
        "sentence_count": len(sentences),
        "reliable_distribution": reliable,
        "sentences": sentences,
        "statistics": stats,
        "uniform_runs": uniform_runs(sentences),
        "warnings": warnings,
    }


def validate_keys(value: dict[str, Any], expected: set[str], context: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise PipelineError(
            "invalid_schema",
            f"{context} keys differ from contract; missing={missing}, extra={extra}",
        )


def validate_document(document: dict[str, Any], *, require_fresh: bool) -> None:
    validate_keys(
        document,
        {"schema_version", "source", "segments", "manifest_sha256", "analysis"},
        "artifact",
    )
    if document["schema_version"] != SCHEMA_VERSION:
        raise PipelineError("unsupported_schema", f"unsupported schema_version: {document['schema_version']!r}")

    source = document["source"]
    if not isinstance(source, dict):
        raise PipelineError("invalid_schema", "source must be an object")
    validate_keys(source, {"name", "format", "sha256", "byte_order_mark"}, "source")
    if source["format"] not in FORMAT_VALUES[1:]:
        raise PipelineError("invalid_schema", f"invalid source format: {source['format']!r}")
    if not isinstance(source["name"], str) or not isinstance(source["sha256"], str):
        raise PipelineError("invalid_schema", "source name and sha256 must be strings")
    if not isinstance(source["byte_order_mark"], bool):
        raise PipelineError("invalid_schema", "source byte_order_mark must be boolean")

    segments = document["segments"]
    if not isinstance(segments, list):
        raise PipelineError("invalid_schema", "segments must be an array")
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            raise PipelineError("invalid_schema", f"segment {index} must be an object")
        validate_keys(
            segment,
            {"id", "kind", "role", "locator", "text", "analysis_effect", "checksum"},
            f"segment {index}",
        )
        expected_id = f"seg-{index:06d}"
        if segment["id"] != expected_id:
            raise PipelineError("invalid_manifest", f"expected segment id {expected_id}, got {segment['id']!r}")
        if segment["kind"] not in KIND_VALUES:
            raise PipelineError("invalid_schema", f"invalid segment kind: {segment['kind']!r}")
        if segment["analysis_effect"] not in EFFECT_VALUES:
            raise PipelineError("invalid_schema", f"invalid analysis_effect: {segment['analysis_effect']!r}")
        if segment["kind"] == "prose" and segment["analysis_effect"] != "text":
            raise PipelineError("invalid_schema", "prose segments must use analysis_effect 'text'")
        if not isinstance(segment["role"], str) or not isinstance(segment["text"], str):
            raise PipelineError("invalid_schema", "segment role and text must be strings")
        locator = segment["locator"]
        if not isinstance(locator, dict):
            raise PipelineError("invalid_schema", "segment locator must be an object")
        validate_keys(locator, {"line_start", "line_end"}, f"segment {index} locator")
        if not all(isinstance(locator[key], int) and locator[key] >= 1 for key in locator):
            raise PipelineError("invalid_schema", "locator lines must be positive integers")
        if segment["kind"] == "protected":
            expected_checksum = sha256_bytes(segment["text"].encode("utf-8"))
            if segment["checksum"] != expected_checksum:
                raise PipelineError("protected_content_changed", f"protected segment changed: {segment['id']}")
        elif segment["checksum"] is not None:
            raise PipelineError("invalid_schema", "prose segment checksum must be null")

    expected_manifest = canonical_hash(manifest_payload(document))
    if document["manifest_sha256"] != expected_manifest:
        raise PipelineError("invalid_manifest", "segment order or immutable metadata changed")

    analysis = document["analysis"]
    if not isinstance(analysis, dict):
        raise PipelineError("invalid_schema", "analysis must be an object")
    expected_analysis_keys = {
        "content_sha256",
        "unit_label",
        "sentence_count",
        "reliable_distribution",
        "sentences",
        "statistics",
        "uniform_runs",
        "warnings",
    }
    validate_keys(analysis, expected_analysis_keys, "analysis")
    if not isinstance(analysis["content_sha256"], str):
        raise PipelineError("invalid_schema", "analysis content_sha256 must be a string")
    if analysis["unit_label"] not in {"words", "length_units"}:
        raise PipelineError("invalid_schema", "analysis unit_label is invalid")
    if not isinstance(analysis["sentence_count"], int) or isinstance(
        analysis["sentence_count"], bool
    ):
        raise PipelineError("invalid_schema", "analysis sentence_count must be an integer")
    if not isinstance(analysis["reliable_distribution"], bool):
        raise PipelineError("invalid_schema", "analysis reliable_distribution must be boolean")

    sentences = analysis["sentences"]
    if not isinstance(sentences, list):
        raise PipelineError("invalid_schema", "analysis sentences must be an array")
    valid_segment_ids = {segment["id"] for segment in segments}
    for index, sentence in enumerate(sentences, start=1):
        if not isinstance(sentence, dict):
            raise PipelineError("invalid_schema", f"analysis sentence {index} must be an object")
        validate_keys(sentence, {"id", "segment_ids", "length"}, f"analysis sentence {index}")
        if not isinstance(sentence["id"], str):
            raise PipelineError("invalid_schema", "analysis sentence id must be a string")
        if not isinstance(sentence["segment_ids"], list) or not all(
            isinstance(item, str) and item in valid_segment_ids for item in sentence["segment_ids"]
        ):
            raise PipelineError("invalid_schema", "analysis sentence segment_ids are invalid")
        if (
            not isinstance(sentence["length"], int)
            or isinstance(sentence["length"], bool)
            or sentence["length"] <= 0
        ):
            raise PipelineError("invalid_schema", "analysis sentence length must be positive")
    if analysis["sentence_count"] != len(sentences):
        raise PipelineError("invalid_schema", "analysis sentence_count does not match sentences")
    if analysis["reliable_distribution"] != (len(sentences) >= 5):
        raise PipelineError("invalid_schema", "analysis reliability does not match sentence count")

    statistic_keys = {
        "mean",
        "median",
        "population_stddev",
        "coefficient_of_variation",
        "q1",
        "q3",
        "minimum",
        "maximum",
    }
    statistics_payload = analysis["statistics"]
    if not isinstance(statistics_payload, dict):
        raise PipelineError("invalid_schema", "analysis statistics must be an object")
    validate_keys(statistics_payload, statistic_keys, "analysis statistics")
    if not all(
        value is None or (isinstance(value, (int, float)) and not isinstance(value, bool))
        for value in statistics_payload.values()
    ):
        raise PipelineError("invalid_schema", "analysis statistics must be numeric or null")

    runs = analysis["uniform_runs"]
    if not isinstance(runs, list):
        raise PipelineError("invalid_schema", "analysis uniform_runs must be an array")
    for index, run in enumerate(runs, start=1):
        if not isinstance(run, dict):
            raise PipelineError("invalid_schema", f"uniform run {index} must be an object")
        validate_keys(
            run,
            {"sentence_start", "sentence_end", "segment_ids", "lengths"},
            f"uniform run {index}",
        )
        if not isinstance(run["sentence_start"], str) or not isinstance(run["sentence_end"], str):
            raise PipelineError("invalid_schema", "uniform run sentence IDs must be strings")
        if not isinstance(run["segment_ids"], list) or not all(
            isinstance(item, str) and item in valid_segment_ids for item in run["segment_ids"]
        ):
            raise PipelineError("invalid_schema", "uniform run segment_ids are invalid")
        if not isinstance(run["lengths"], list) or not all(
            isinstance(item, int) and not isinstance(item, bool) and item > 0
            for item in run["lengths"]
        ):
            raise PipelineError("invalid_schema", "uniform run lengths are invalid")

    warnings = analysis["warnings"]
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
        raise PipelineError("invalid_schema", "analysis warnings must be an array of strings")
    if require_fresh and analysis["content_sha256"] != analysis_content_hash(document):
        raise PipelineError("stale_analysis", "prose changed after analysis; run analyze before validation or render")
    if require_fresh:
        inherited_warnings = [item for item in warnings if item != RELIABILITY_WARNING]
        expected_analysis = build_analysis(document, inherited_warnings)
        if analysis != expected_analysis:
            raise PipelineError("invalid_analysis", "analysis values do not match document content")


def make_document(
    *,
    source_path: Path,
    source_format: str,
    raw_bytes: bytes,
    has_bom: bool,
    segments: list[dict[str, Any]],
    warnings: Sequence[str],
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "name": source_path.name,
            "format": source_format,
            "sha256": sha256_bytes(raw_bytes),
            "byte_order_mark": has_bom,
        },
        "segments": segments,
        "manifest_sha256": "",
        "analysis": {},
    }
    document["manifest_sha256"] = canonical_hash(manifest_payload(document))
    document["analysis"] = build_analysis(document, warnings)
    validate_document(document, require_fresh=True)
    return document


def document_summary(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": document["source"]["format"],
        "segment_count": len(document["segments"]),
        "prose_segment_count": sum(1 for item in document["segments"] if item["kind"] == "prose"),
        "protected_segment_count": sum(
            1 for item in document["segments"] if item["kind"] == "protected"
        ),
        "sentence_count": document["analysis"]["sentence_count"],
        "unit_label": document["analysis"]["unit_label"],
        "warnings": document["analysis"]["warnings"],
    }


def run_extract(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    input_path = Path(args.input)
    output_path = Path(args.output)
    source_format = infer_format(input_path, args.format)
    raw, text, has_bom = read_utf8_source(input_path)
    segments, warnings = segment_source(text, source_format)
    document = make_document(
        source_path=input_path,
        source_format=source_format,
        raw_bytes=raw,
        has_bom=has_bom,
        segments=segments,
        warnings=warnings,
    )
    write_atomic(output_path, dump_artifact(document), overwrite=args.overwrite)
    return str(output_path.resolve()), document_summary(document)


def run_analyze(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    input_path = Path(args.input)
    output_path = Path(args.output)
    document = load_artifact(input_path)
    validate_document(document, require_fresh=False)
    previous_warnings = [
        item
        for item in document.get("analysis", {}).get("warnings", [])
        if item != RELIABILITY_WARNING
    ]
    document["analysis"] = build_analysis(document, previous_warnings)
    validate_document(document, require_fresh=True)
    write_atomic(output_path, dump_artifact(document), overwrite=args.overwrite)
    return str(output_path.resolve()), document_summary(document)


def run_validate(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    input_path = Path(args.input)
    document = load_artifact(input_path)
    validate_document(document, require_fresh=True)
    return str(input_path.resolve()), document_summary(document)


def run_render(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    input_path = Path(args.input)
    output_path = Path(args.output)
    document = load_artifact(input_path)
    validate_document(document, require_fresh=True)
    text = "".join(segment["text"] for segment in document["segments"])
    rendered = text.encode("utf-8")
    if document["source"]["byte_order_mark"]:
        rendered = UTF8_BOM + rendered
    write_atomic(output_path, rendered, overwrite=args.overwrite)
    summary = document_summary(document)
    summary["rendered_sha256"] = sha256_bytes(rendered)
    return str(output_path.resolve()), summary


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description="Extract, analyze, validate, and render Paper Humanizer document artifacts.",
        epilog=(
            "Examples:\n"
            "  document_pipeline.py extract --input paper.md --format auto --output paper.yaml\n"
            "  document_pipeline.py analyze --input edited.yaml --output checked.yaml\n"
            "  document_pipeline.py validate --input checked.yaml\n"
            "  document_pipeline.py render --input checked.yaml --output paper-humanized.md"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=JsonArgumentParser)

    extract = subparsers.add_parser("extract", help="convert source text to a protected YAML artifact")
    extract.add_argument("--input", required=True, help="UTF-8 source path")
    extract.add_argument("--format", choices=FORMAT_VALUES, default="auto", help="source format")
    extract.add_argument("--output", required=True, help="new JSON-compatible YAML artifact path")
    extract.add_argument("--overwrite", action="store_true", help="replace an existing output")

    analyze = subparsers.add_parser("analyze", help="refresh analysis after prose edits")
    analyze.add_argument("--input", required=True, help="existing YAML artifact path")
    analyze.add_argument("--output", required=True, help="new analyzed YAML artifact path")
    analyze.add_argument("--overwrite", action="store_true", help="replace an existing output")

    validate = subparsers.add_parser("validate", help="validate structure and analysis freshness")
    validate.add_argument("--input", required=True, help="YAML artifact path")

    render = subparsers.add_parser("render", help="reconstruct the source format")
    render.add_argument("--input", required=True, help="fresh YAML artifact path")
    render.add_argument("--output", required=True, help="rendered source path")
    render.add_argument("--overwrite", action="store_true", help="replace an existing output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    command = ""
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        command = args.command
        runners = {
            "extract": run_extract,
            "analyze": run_analyze,
            "validate": run_validate,
            "render": run_render,
        }
        artifact, summary = runners[command](args)
        stdout_envelope(
            ok=True,
            command=command,
            artifact=artifact,
            summary=summary,
            error=None,
        )
        return 0
    except PipelineError as exc:
        sys.stderr.write(exc.message + "\n")
        stdout_envelope(
            ok=False,
            command=command,
            artifact=None,
            summary={},
            error={"code": exc.code, "message": exc.message},
        )
        return 2
    except Exception as exc:  # pragma: no cover - last-resort stable failure contract
        message = f"unexpected pipeline failure: {exc}"
        sys.stderr.write(message + "\n")
        stdout_envelope(
            ok=False,
            command=command,
            artifact=None,
            summary={},
            error={"code": "internal_error", "message": message},
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

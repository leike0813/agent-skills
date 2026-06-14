#!/usr/bin/env python3
"""
blockify.py — Block-level splitting for literature-translator.

Reads normalized Markdown (workspace/normalized.md), performs deterministic
block-level splitting by recognizing structural patterns, and outputs Markdown
with <!-- BLOCK: ... --> markers (workspace/blocked.md).

Two-pass algorithm:
  Pass 1: Detect heading strategy (proper_nesting vs flat_single_hash)
  Pass 2: State machine to build blocks

The output is compatible with sentencify.py's BLOCK_START_RE / BLOCK_END_RE.

After this script runs, the agent reviews the output and fixes any
misclassifications (Phase 4b).
"""
import argparse
import json
import re
import sys
from pathlib import Path


# Heading patterns for strategy detection
HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$')
MULTI_HASH_RE = re.compile(r'^#{2,}\s')

# Equation delimiters
EQUATION_START_RE = re.compile(r'^\s*\$\$\s*$')
EQUATION_END_RE = re.compile(r'\$\$')
EQUATION_BRACKET_START_RE = re.compile(r'^\s*\\\[\s*$')
EQUATION_BRACKET_END_RE = re.compile(r'^\s*\\\]\s*$')

# Table markers
TABLE_START_RE = re.compile(r'<table', re.IGNORECASE)
TABLE_END_RE = re.compile(r'</table>', re.IGNORECASE)

# Image markers
IMAGE_RE = re.compile(r'!\[.*?\]\(.*?\)')

# Code fence markers
CODE_FENCE_RE = re.compile(r'^```')
VERBATIM_START_RE = re.compile(r'\\begin\{verbatim\}')
VERBATIM_END_RE = re.compile(r'\\end\{verbatim\}')

# List patterns
LIST_PATTERNS = [
    re.compile(r'^[\-\*•·]\s+'),           # -, *, •, ·
    re.compile(r'^\d+[\.\)、]\s+'),         # 1., 2), 3、
    re.compile(r'^[a-zA-Z][\.\)]\s+'),      # a., b)
]

# Common unnumbered heading keywords (level 1)
L1_HEADING_KEYWORDS = {
    'abstract', 'introduction', 'background', 'related work',
    'method', 'methodology', 'approach', 'proposed method',
    'experiments', 'experimental setup', 'experimental results',
    'results', 'discussion', 'conclusion', 'conclusions',
    'references', 'bibliography', 'acknowledgements',
    'acknowledgments', 'appendix', 'supplementary material',
    '摘要', '引言', '引言/相关工作和背景', '相关工作',
    '方法', '实验', '结果', '讨论', '结论', '参考文献',
    '致谢', '附录',
}


class Block:
    """Represents a single block with markers."""
    def __init__(self, block_id: str, block_type: str, heading: str = "",
                 start_line: int = -1, end_line: int = -1):
        self.block_id = block_id
        self.block_type = block_type
        self.heading = heading
        self.start_line = start_line
        self.end_line = end_line
        self.lines: list[str] = []

    def add_line(self, line: str):
        self.lines.append(line)

    def get_content(self) -> str:
        return "".join(self.lines)

    def to_markdown(self) -> str:
        heading_attr = f" | heading: {self.heading}" if self.heading else ""
        content = self.get_content()
        # Strip trailing whitespace for clean output
        content_stripped = content.rstrip("\n")
        return (
            f"<!-- BLOCK: {self.block_id} | type: {self.block_type}{heading_attr} -->\n"
            f"{content_stripped}\n"
            f"<!-- BLOCK_END: {self.block_id} -->\n"
        )

    def __repr__(self):
        return f"Block({self.block_id}, type={self.block_type}, lines={len(self.lines)})"


class HeadingStack:
    """Tracks heading hierarchy for assigning heading context to content blocks."""

    def __init__(self):
        self.stack: list[tuple[int, str]] = []  # (level, text)

    def push(self, level: int, text: str):
        # Pop entries with level >= new level (siblings and children)
        while self.stack and self.stack[-1][0] >= level:
            self.stack.pop()
        self.stack.append((level, text))

    def current_heading(self) -> str:
        """Return the closest heading's text."""
        if self.stack:
            # Return the FULL heading path joined with >
            texts = [t for _, t in self.stack]
            return " > ".join(texts)
        return ""


def detect_heading_strategy(lines: list[str]) -> str:
    """Detect heading strategy by scanning the document.

    Returns 'proper_nesting' if any line uses ## or ###,
    'flat_single_hash' if all headings use exactly one #.
    """
    inside_code_block = False
    has_multi_hash = False
    has_single_hash = False

    for line in lines:
        stripped = line.rstrip("\n")

        # Skip lines inside fenced code blocks
        if CODE_FENCE_RE.match(stripped):
            inside_code_block = not inside_code_block
            continue
        if inside_code_block:
            continue

        # Skip lines inside verbatim environments
        if VERBATIM_START_RE.search(stripped):
            inside_code_block = True
            continue
        if VERBATIM_END_RE.search(stripped):
            inside_code_block = False
            continue

        if MULTI_HASH_RE.match(stripped):
            has_multi_hash = True
        elif re.match(r'^#\s', stripped):
            has_single_hash = True

    if has_multi_hash:
        return 'proper_nesting'
    return 'flat_single_hash'


def infer_heading_level(text: str) -> int:
    """Infer heading level from numbered section pattern (flat_single_hash mode).

    Rules:
    - If starts with a number: count dots to determine level
    - If starts with a Roman numeral (I, II, V, X): level 1
    - If lowercase keyword in L1_HEADING_KEYWORDS: level 1
    - Default: level 1 (most flat papers use L1 for everything)
    """
    text_stripped = text.strip()

    # Try numbered pattern: "1 ", "1.1 ", "1.1.1 ", "A ", "A.1 "
    numbered_match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?\s', text_stripped)
    if numbered_match:
        groups = numbered_match.groups()
        if groups[2] is not None:
            return 3
        elif groups[1] is not None:
            return 2
        else:
            return 1

    # Try appendix-style: "A ", "B ", "A.1 "
    appendix_match = re.match(r'^([A-Z])(?:\.(\d+))?\s', text_stripped)
    if appendix_match:
        return 1  # Appendix sections are L1

    # Check against known L1 keywords
    lower = text_stripped.lower().rstrip(".:")
    if lower in L1_HEADING_KEYWORDS:
        return 1

    # Try to detect if first word is a well-known L1 keyword
    first_word = lower.split()[0].rstrip(":") if lower.split() else ""
    if first_word in L1_HEADING_KEYWORDS:
        return 1

    return 1


def classify_heading(line: str) -> tuple[int, str] | None:
    """Classify a line as a heading.

    Returns (level, text) or None if not a heading.
    """
    m = HEADING_RE.match(line)
    if m:
        level = len(m.group(1))
        text = m.group(2).strip()
        return (level, text)
    return None


def is_list_line(line: str) -> bool:
    """Check if a line matches a list pattern."""
    stripped = line.lstrip()
    for pat in LIST_PATTERNS:
        if pat.match(stripped):
            return True
    return False


def is_bib_start(line: str) -> bool:
    """Check if a line starts a bibliography entry."""
    stripped = line.lstrip()
    return bool(re.match(r'^\[\d+\]', stripped)) or bool(re.match(r'^\d+\.\s+[A-Z]', stripped))


def is_table_caption(line: str) -> bool:
    """Check if a line is a table caption."""
    stripped = line.strip()
    return bool(re.match(r'(?:Table|TABLE|表格)\s+\d+[\.:\s]', stripped))


def is_figure_caption(line: str) -> bool:
    """Check if a line is a standalone figure caption reference."""
    stripped = line.strip()
    return bool(re.match(r'(?:Figure|Fig\.?|图)\s+\d+[\.:\s]', stripped))


def is_abstract_heading(text: str) -> bool:
    """Check if heading text indicates abstract section."""
    lower = text.strip().lower().rstrip(".:")
    return lower in ('abstract', '摘要')


def is_references_heading(text: str) -> bool:
    """Check if heading text indicates references section."""
    lower = text.strip().lower().rstrip(".:")
    return lower in ('references', 'bibliography', '参考文献')


def is_blank_line(line: str) -> bool:
    return line.strip() == ""


def blockify(lines: list[str], heading_strategy: str) -> list[Block]:
    """Main block splitting algorithm — state machine."""
    blocks: list[Block] = []
    heading_stack = HeadingStack()
    current_block: Block | None = None
    block_counter = 0
    state = "IDLE"  # IDLE, EQUATION, TABLE, CODE, FIGURE_CAPTION
    in_references = False
    abstract_detected = False
    file_has_title = False

    def start_block(block_type: str, line_idx: int = -1):
        nonlocal current_block, block_counter
        flush_block()
        block_counter += 1
        block_id = f"b_{block_counter:03d}"
        current_block = Block(block_id, block_type,
                              heading=heading_stack.current_heading(),
                              start_line=line_idx)

    def flush_block():
        nonlocal current_block
        if current_block and current_block.lines:
            current_block.end_line = len(lines) - 1 if current_block.start_line < 0 else current_block.start_line + len(current_block.lines)  # approximate
            blocks.append(current_block)
        current_block = None

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip("\n")

        # ── Blank line handling ──
        if is_blank_line(stripped):
            if state == "PARAGRAPH":
                flush_block()
                state = "IDLE"
            elif state == "LIST":
                # Check if next non-blank line is also a list item
                next_content = None
                for j in range(i + 1, len(lines)):
                    if not is_blank_line(lines[j]):
                        next_content = lines[j]
                        break
                if next_content and is_list_line(next_content):
                    # Continue the list — keep accumulating
                    current_block.add_line(line)
                else:
                    flush_block()
                    state = "IDLE"
            elif state == "FIGURE_CAPTION":
                # Blank line ends figure caption
                flush_block()
                state = "IDLE"
            elif state == "EQUATION":
                current_block.add_line(line)
            elif state == "TABLE":
                current_block.add_line(line)
            elif state == "CODE":
                current_block.add_line(line)
            # In IDLE: skip blank lines
            i += 1
            continue

        # ── Heading detection ──
        heading_result = classify_heading(stripped)
        if heading_result:
            level, text = heading_result
            # Adjust level for flat_single_hash strategy
            if heading_strategy == 'flat_single_hash':
                level = infer_heading_level(text)

            flush_block()
            heading_stack.push(level, text)
            state = "IDLE"

            # Track special headings
            if is_abstract_heading(text):
                abstract_detected = True
            in_references = is_references_heading(text)

            # Track if we've passed the title (first heading = title)
            if not file_has_title and block_counter == 0:
                file_has_title = True

            # Create heading block
            block_counter += 1
            block_id = f"b_{block_counter:03d}"
            heading_block = Block(block_id, "heading",
                                  heading=heading_stack.current_heading(),
                                  start_line=i)
            heading_block.add_line(line)
            heading_block.end_line = i
            blocks.append(heading_block)
            i += 1
            continue

        # ── Equation handling ──
        if state == "IDLE" and EQUATION_START_RE.match(stripped):
            start_block("equation", i)
            current_block.add_line(line)
            state = "EQUATION"
            i += 1
            continue

        if state == "EQUATION":
            current_block.add_line(line)
            if EQUATION_END_RE.search(stripped):
                # Could be closing $$ (possibly with \tag{N})
                # Check if this is the closing $$ (not the opening one)
                if not EQUATION_START_RE.match(stripped) or len(current_block.lines) > 1:
                    flush_block()
                    state = "IDLE"
            i += 1
            continue

        # ── Table handling ──
        if TABLE_START_RE.search(stripped):
            # Check if previous line was a table caption
            if (current_block and current_block.block_type == "PARAGRAPH"
                    and is_table_caption("".join(current_block.lines))):
                current_block.block_type = "table_caption"
                flush_block()
            else:
                flush_block()

            start_block("table", i)
            current_block.add_line(line)
            state = "TABLE"
            i += 1
            continue

        if state == "TABLE":
            current_block.add_line(line)
            if TABLE_END_RE.search(stripped):
                flush_block()
                state = "IDLE"
            i += 1
            continue

        # ── Code fence handling ──
        if CODE_FENCE_RE.match(stripped):
            flush_block()
            start_block("code", i)
            current_block.add_line(line)
            state = "CODE"
            i += 1
            continue

        if state == "CODE":
            current_block.add_line(line)
            if CODE_FENCE_RE.match(stripped):
                # This is the closing fence
                flush_block()
                state = "IDLE"
            i += 1
            continue

        # ── Verbatim handling ──
        if VERBATIM_START_RE.search(stripped):
            flush_block()
            start_block("code", i)
            current_block.add_line(line)
            state = "CODE"
            i += 1
            continue

        if state == "CODE" and VERBATIM_END_RE.search(stripped):
            current_block.add_line(line)
            flush_block()
            state = "IDLE"
            i += 1
            continue

        # ── Image handling (figure_caption) ──
        if IMAGE_RE.search(stripped):
            flush_block()
            start_block("figure_caption", i)
            current_block.add_line(line)
            state = "FIGURE_CAPTION"
            i += 1
            continue

        if state == "FIGURE_CAPTION":
            # If another image, close previous and start new
            if IMAGE_RE.search(stripped):
                flush_block()
                start_block("figure_caption", i)
                current_block.add_line(line)
            else:
                current_block.add_line(line)
            i += 1
            continue

        # ── Default: paragraph / list / abstract / bib_item ──
        # Close any existing content block if blank-line separated
        # (We're here because line is not blank but is content text)

        if state == "IDLE":
            # Determine what type of content block to start

            # Check for abstract (first content block)
            if not abstract_detected:
                lower_text = stripped.lower()
                if "abstract" in lower_text[:80] or "摘要" in stripped[:80]:
                    start_block("abstract", i)
                    current_block.add_line(line)
                    abstract_detected = True
                    state = "PARAGRAPH"
                    i += 1
                    continue

            # Check for bib_item (inside references section)
            if in_references and is_bib_start(stripped):
                start_block("bib_item", i)
                current_block.add_line(line)
                state = "PARAGRAPH"  # Reuse paragraph state for accumulation
                i += 1
                continue

            # Check for table caption (standalone)
            if is_table_caption(stripped):
                start_block("table_caption", i)
                current_block.add_line(line)
                state = "PARAGRAPH"
                i += 1
                continue

            # Check for standalone figure caption
            if is_figure_caption(stripped) and not IMAGE_RE.search(stripped):
                start_block("figure_caption", i)
                current_block.add_line(line)
                state = "PARAGRAPH"
                i += 1
                continue

            # Check for list
            if is_list_line(stripped):
                start_block("list", i)
                current_block.add_line(line)
                state = "LIST"
                i += 1
                continue

            # Default: paragraph
            if in_references and current_block and current_block.block_type == "bib_item":
                # Continue the bib item
                current_block.add_line(line)
            else:
                flush_block()
                start_block("paragraph", i)
                current_block.add_line(line)
                state = "PARAGRAPH"
            i += 1
            continue

        if state == "PARAGRAPH":
            # Check for list items inside paragraph context
            # (allows lists to interrupt paragraphs)
            if is_list_line(stripped):
                flush_block()
                start_block("list", i)
                current_block.add_line(line)
                state = "LIST"
                i += 1
                continue

            # Check for bib continuation
            if in_references and current_block and current_block.block_type == "bib_item":
                # Still accumulating bib item
                current_block.add_line(line)
                i += 1
                continue

            # Continue paragraph
            current_block.add_line(line)
            i += 1
            continue

        if state == "LIST":
            if is_list_line(stripped):
                current_block.add_line(line)
            else:
                # Close list, start paragraph with this line
                flush_block()
                start_block("paragraph", i)
                current_block.add_line(line)
                state = "PARAGRAPH"
            i += 1
            continue

        # Safety: shouldn't reach here
        i += 1

    # Flush any remaining block
    flush_block()

    # ── Post-processing: merge adjacent same-type blocks ──
    blocks = merge_adjacent_blocks(blocks)

    return blocks


def merge_adjacent_blocks(blocks: list[Block]) -> list[Block]:
    """Merge adjacent blocks of the same type under the same heading.

    Merges adjacent paragraph blocks that share the same heading context.
    Does NOT merge structural types (equation, code, table, heading).
    """
    if not blocks:
        return blocks

    MERGE_TYPES = {"paragraph", "list"}

    merged = [blocks[0]]

    for block in blocks[1:]:
        last = merged[-1]

        should_merge = (
            block.block_type in MERGE_TYPES
            and last.block_type == block.block_type
            and last.heading == block.heading
        )

        if should_merge:
            # Merge block into last
            last.lines.extend(block.lines)
            last.end_line = block.end_line
        else:
            merged.append(block)

    return merged


def write_blocked(blocks: list[Block], output_path: Path):
    """Write blocked.md with block markers."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure blank line between blocks for readability
    result_parts = []
    for i, block in enumerate(blocks):
        if i > 0:
            result_parts.append("\n")
        result_parts.append(block.to_markdown())

    result = "".join(result_parts)
    output_path.write_text(result, encoding="utf-8")


def compute_stats(blocks: list[Block]) -> dict:
    """Compute block statistics."""
    by_type: dict[str, int] = {}
    for block in blocks:
        by_type[block.block_type] = by_type.get(block.block_type, 0) + 1

    return {
        "total_blocks": len(blocks),
        "by_type": dict(sorted(by_type.items())),
    }


def main():
    parser = argparse.ArgumentParser(description="Block-level splitting for literature-translator")
    parser.add_argument("--input", required=True, help="Input normalized markdown file")
    parser.add_argument("--output", required=True, help="Output blocked markdown file with block markers")
    parser.add_argument("--stats", help="Optional: output block statistics JSON path")
    parser.add_argument("--verbose", action="store_true", help="Print processing info to stderr")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(json.dumps({"error": f"input file not found: {input_path}"}))
        sys.exit(1)

    text = input_path.read_text(encoding="utf-8")
    lines = text.split("\n")
    # Preserve newlines — keep trailing newline on each line
    lines_with_nl = [line + "\n" for line in lines[:-1]] + ([lines[-1]] if lines else [""])
    if not lines_with_nl[-1].endswith("\n") and lines_with_nl[-1]:
        lines_with_nl[-1] += "\n"

    if args.verbose:
        print(f"Input: {input_path.resolve()}", file=sys.stderr)
        print(f"Lines: {len(lines_with_nl)}", file=sys.stderr)

    # Pass 1: Detect heading strategy
    heading_strategy = detect_heading_strategy(lines_with_nl)
    if args.verbose:
        print(f"Heading strategy: {heading_strategy}", file=sys.stderr)

    # Pass 2: Block splitting
    blocks = blockify(lines_with_nl, heading_strategy)

    if not blocks:
        print(json.dumps({"error": "no blocks produced", "hint": "check input file content"}))
        sys.exit(1)

    # Write output
    output_path = Path(args.output)
    write_blocked(blocks, output_path)

    # Write stats if requested
    stats = compute_stats(blocks)
    if args.stats:
        stats_path = Path(args.stats)
        stats_path.parent.mkdir(parents=True, exist_ok=True)
        stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    result = {
        "status": "ok",
        "blocks": stats["total_blocks"],
        "by_type": stats["by_type"],
        "heading_strategy": heading_strategy,
        "output": str(output_path.resolve()),
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

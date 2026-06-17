#!/usr/bin/env python3
"""
build_block_sentences.py — Build v2 sentences.json from blocked.md for fast mode.

In fast mode, sentence-level splitting is skipped. Each block's entire content
becomes a single sentence entry, producing a sentences.json compatible with
partition_batches.py and downstream scripts.
"""
import argparse
import json
import re
import sys
from pathlib import Path

# Regex to parse block start markers: <!-- BLOCK: id | type: type | heading: heading -->
BLOCK_START_RE = re.compile(
    r'<!-- BLOCK: (b_\d+) \| type: (\S+) \| heading: (.*) -->'
)
BLOCK_END_RE = re.compile(r'<!-- BLOCK_END: (b_\d+) -->')


def parse_blocked_md(text: str) -> list[dict]:
    """Parse blocked.md content into a list of block dicts."""
    blocks = []
    current_block = None
    current_lines = []

    for line in text.splitlines(keepends=True):
        start_match = BLOCK_START_RE.match(line.strip())
        if start_match:
            # Finish previous block if any
            if current_block is not None:
                blocks.append(_finalize_block(current_block, current_lines))
            current_block = {
                "block_id": start_match.group(1),
                "type": start_match.group(2),
                "heading": start_match.group(3).strip(),
            }
            current_lines = []
            continue

        end_match = BLOCK_END_RE.match(line.strip())
        if end_match:
            if current_block and end_match.group(1) == current_block["block_id"]:
                blocks.append(_finalize_block(current_block, current_lines))
                current_block = None
                current_lines = []
            continue

        if current_block is not None:
            current_lines.append(line)

    return blocks


def _finalize_block(block: dict, lines: list[str]) -> dict:
    """Build a block entry from parsed header and content lines."""
    content = "".join(lines).strip()
    return {
        "block_id": block["block_id"],
        "type": block["type"],
        "heading": block["heading"],
        "content": content,
    }


def build_sentences(blocks: list[dict]) -> dict:
    """Build v2 sentences.json from block list."""
    blocks_dict = {}
    for block in blocks:
        # Each block gets one sentence: the entire block content
        blocks_dict[block["block_id"]] = {
            "type": block["type"],
            "heading": block["heading"],
            "sentences": [[1, block["content"]]],
            "sentence_count": 1,
        }

    total_sentences = len(blocks)
    return {
        "format": "v2",
        "blocks": blocks_dict,
        "stats": {
            "no_split": total_sentences,  # Every block = 1 sentence = no split
            "split": 0,
            "total_sentences": total_sentences,
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Build v2 sentences.json from blocked.md (fast mode)"
    )
    parser.add_argument("--blocked", required=True,
                        help="Path to blocked.md from blockify.py")
    parser.add_argument("--output", required=True,
                        help="Output path for sentences.json")
    args = parser.parse_args()

    blocked_path = Path(args.blocked)
    if not blocked_path.exists():
        print(json.dumps({"error": f"blocked.md not found: {blocked_path}"}))
        sys.exit(1)

    text = blocked_path.read_text(encoding="utf-8")
    blocks = parse_blocked_md(text)

    if not blocks:
        print(json.dumps({"error": "no blocks found in blocked.md"}))
        sys.exit(1)

    sentences = build_sentences(blocks)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(sentences, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    result = {
        "status": "ok",
        "blocks": len(blocks),
        "by_type": _count_by_type(blocks),
        "output": str(output_path.resolve()),
    }
    print(json.dumps(result, ensure_ascii=False))


def _count_by_type(blocks: list[dict]) -> dict[str, int]:
    """Count blocks by type for diagnostic output."""
    counts = {}
    for block in blocks:
        t = block["type"]
        counts[t] = counts.get(t, 0) + 1
    return counts


if __name__ == "__main__":
    main()

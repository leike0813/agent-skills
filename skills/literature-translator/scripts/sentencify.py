#!/usr/bin/env python3
"""
sentencify.py — Sentence-level splitting for literature-translator.

Reads a markdown file with block-level markers (inserted by the agent in Phase 4),
splits each block's text content into sentences by punctuation boundaries.

Deterministic script — does NOT perform semantic analysis.

Block types that keep entire content as a single "sentence":
- equation, code

Block types that get sentence-split:
- heading, paragraph, table (text cells), figure_caption, table_caption,
  bib_item, abstract, list
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path


BLOCK_START_RE = re.compile(
    r'<!--\s*BLOCK:\s*(\S+)\s*\|\s*type:\s*(\S+)(?:\s*\|\s*heading:\s*(.*?))?\s*-->'
)
BLOCK_END_RE = re.compile(r'<!--\s*BLOCK_END:\s*(\S+)\s*-->')

NO_SPLIT_TYPES = {"equation", "code", "bib_item", "heading"}

# Sentence boundary patterns
# Chinese/Japanese: 。！？
# English: .!?

# Pattern to NOT split on:
# - Decimal numbers "3.14"
SENTENCE_BOUNDARY_RE = re.compile(
    r'(?<!\d)'  # not after a digit (decimal numbers)
    r'(?<=[。！？.!?])'  # boundary character
    r'(?=\s|$)'  # followed by whitespace or end
)

# Comprehensive academic abbreviation patterns (case-insensitive)
# Used to detect and reverse false sentence splits at abbreviation periods
ABBREVIATION_PATTERNS = [
    # Common academic abbreviations (multi-letter)
    re.compile(r'\b(?:e\.g|i\.e|vs|viz|aka|etc|et\b|al|cf|dept|comp|sci|intell|tech|fig|est|approx|suppl|vol|no|pp|eds|rev|ref|sec|chap|par|eq|prop|lem|cor|def|resp|syn|lit|app|ex|min|max|avg|std|norm|init|eval|train|val|inf|sup|dim|param|config|relu|conv|attn|embed)\.$', re.IGNORECASE),  # noqa: E501
    # Titles and honorifics
    re.compile(r'\b(?:Dr|Mr|Ms|Mrs|Prof|St|Ave|Mt|Fr|Rev|Hon|Capt|Lt|Col|Gen|Sgt|Esq|Jr|Sr)\.$', re.IGNORECASE),  # noqa: E501
    # Single initial (J. in J. Smith)
    re.compile(r'\b[a-zA-Z]\.$'),
]


def parse_blocks(text: str) -> list[dict]:
    """Parse block markers from markdown text."""
    blocks = []
    current_block = None
    current_content = []
    block_start = -1

    lines = text.split("\n")

    for i, line in enumerate(lines):
        start_match = BLOCK_START_RE.search(line)
        if start_match:
            if current_block:
                # Previous block wasn't closed — close implicitly
                blocks.append({
                    "block_id": current_block["id"],
                    "type": current_block["type"],
                    "heading": current_block.get("heading", ""),
                    "content": "\n".join(current_content).strip(),
                    "start_line": block_start,
                    "end_line": i - 1,
                })
            current_block = {
                "id": start_match.group(1),
                "type": start_match.group(2),
                "heading": start_match.group(3) or "",
            }
            current_content = []
            block_start = i
            continue

        end_match = BLOCK_END_RE.search(line)
        if end_match and current_block:
            block_id = end_match.group(1)
            if block_id == current_block["id"]:
                blocks.append({
                    "block_id": current_block["id"],
                    "type": current_block["type"],
                    "heading": current_block.get("heading", ""),
                    "content": "\n".join(current_content).strip(),
                    "start_line": block_start,
                    "end_line": i,
                })
                current_block = None
                current_content = []
                block_start = -1
                continue

        # Collect content line (skip block marker lines themselves)
        if current_block is not None \
                and not BLOCK_START_RE.search(line) \
                and not BLOCK_END_RE.search(line):
            current_content.append(line)

    # Handle unclosed block at end
    if current_block:
        blocks.append({
            "block_id": current_block["id"],
            "type": current_block["type"],
            "heading": current_block.get("heading", ""),
            "content": "\n".join(current_content).strip(),
            "start_line": block_start,
            "end_line": len(lines) - 1,
        })

    return blocks


def split_sentences(text: str) -> list[str]:
    """Split text into sentences by punctuation boundaries.

    Handles:
    - Chinese punctuation 。！？
    - English punctuation .!?
    - Abbreviations (e.g., i.e., etc.)
    - Decimal numbers
    - Multiple punctuation marks (!!!, ??)
    - Empty text
    """
    if not text or not text.strip():
        return [""]

    # Normalize whitespace but preserve intentional line breaks
    text = re.sub(r'\n{2,}', '\n\n', text)  # Keep paragraph breaks
    text = text.strip()

    # Use regex to split at sentence boundaries
    # First, add a special marker at each split point
    # Handle Chinese punctuation first (they are unambiguous)
    parts = []

    # Strategy: split on identified boundaries
    last_end = 0
    for match in SENTENCE_BOUNDARY_RE.finditer(text):
        start, end = match.start(), match.end()
        sentence = text[last_end:end].strip()
        if sentence:
            parts.append(sentence)
        last_end = end

    remaining = text[last_end:].strip()
    if remaining:
        parts.append(remaining)

    # If no splits found, return whole text as one sentence
    if not parts:
        parts = [text.strip()] if text.strip() else [""]

    # Post-process: merge back trailing content after abbreviations
    merged = []
    i = 0
    while i < len(parts):
        part = parts[i]
        # Check if part looks like an abbreviation fragment
        if merged and is_abbreviation_fragment(merged[-1]):
            merged[-1] = merged[-1] + " " + part
        elif part and re.match(r'^[a-z0-9({\[]', part):
            # Starts with lowercase letter or digit — likely a continuation
            # (e.g., "of Comp." after "Dept.", or "5" after "Fig.")
            if merged:
                merged[-1] = merged[-1] + " " + part
            else:
                merged.append(part)
        else:
            merged.append(part)
        i += 1

    return [m.strip() for m in merged if m.strip()]


def is_abbreviation_fragment(text: str) -> bool:
    """Check if text ends with a known abbreviation pattern."""
    return any(p.search(text) for p in ABBREVIATION_PATTERNS)


def process_block(block: dict) -> dict:
    """Process a single block: split sentences or keep intact."""
    block_type = block["type"]
    content = block["content"]

    if block_type in NO_SPLIT_TYPES:
        sentences = [content] if content.strip() else [""]
    else:
        # Split into paragraphs first, then split paragraphs into sentences
        paragraphs = re.split(r'\n\s*\n', content)
        sentences = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            # Normalize single newlines to space within a paragraph
            # (preserve the semantic flow of multi-line text)
            para = para.replace('\n', ' ')
            para = re.sub(r' +', ' ', para)  # collapse multiple spaces
            para_sentences = split_sentences(para)
            sentences.extend(para_sentences)

        if not sentences:
            sentences = [""]

    # Wrap sentences with 1-based local index: [[1, "text"], [2, "text"], ...]
    indexed_sentences = [[i + 1, s] for i, s in enumerate(sentences)]

    return {
        "block_id": block["block_id"],
        "type": block_type,
        "heading": block["heading"],
        "sentences": indexed_sentences,
        "sentence_count": len(indexed_sentences),
    }


def main():
    parser = argparse.ArgumentParser(description="Split blocks into sentences")
    parser.add_argument("--input", required=True, help="Input markdown file with block markers")
    parser.add_argument("--output", required=True, help="Output JSON path")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(json.dumps({"error": f"input file not found: {input_path}"}))
        sys.exit(1)

    text = input_path.read_text(encoding="utf-8")
    blocks = parse_blocks(text)

    if not blocks:
        print(json.dumps({"error": "no blocks found in input file", "hint": "check BLOCK markers"}))
        sys.exit(1)

    result = {}
    block_count = {"no_split": 0, "split": 0, "total_sentences": 0}

    for block in blocks:
        processed = process_block(block)
        result[processed["block_id"]] = {
            "type": processed["type"],
            "heading": processed["heading"],
            "sentences": processed["sentences"],
        }
        if processed["type"] in NO_SPLIT_TYPES:
            block_count["no_split"] += 1
        else:
            block_count["split"] += 1
        block_count["total_sentences"] += len(processed["sentences"])

    output = {
        "format": "v2",
        "blocks": result,
        "stats": block_count,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {"status": "ok", "blocks": block_count, "output": str(output_path.resolve())}
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
concatenate.py — Translation concatenation for literature-translator.

Reads the original blocked.md (with block markers) and all translation
result files from the translations directory. Replaces each block's
content with the translated version while preserving the original
document structure, block markers, formulas, and code blocks.

Deterministic script — does NOT perform semantic editing or language polishing.
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

NO_TRANSLATE_TYPES = {"equation", "code", "bib_item"}


def extract_sentence_text(item) -> str:
    """Extract text from a sentence item, handling v1 (string) and v2 ([idx, text]) formats."""
    if isinstance(item, (list, tuple)):
        return str(item[1]) if len(item) > 1 else ""
    return str(item)


def load_translations(translations_dir: Path) -> dict[str, dict]:
    """Load all translated batch results from directory.

    Returns dict mapping block_id -> {sentences: [...], type: str, sentence_count: int}
    Sentence text is extracted from both v1 (string) and v2 ([idx, text]) formats.
    """
    translations = {}

    if not translations_dir.exists():
        print(json.dumps({"error": f"translations directory not found: {translations_dir}"}))
        sys.exit(1)

    for f in sorted(translations_dir.iterdir()):
        if not f.name.endswith("_translated.json") and not f.name.endswith(".json"):
            continue
        if f.name == "manifest.json":
            continue

        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(json.dumps({"error": f"cannot read {f.name}: {e}"}))
            continue

        # Handle different translation result formats
        blocks = data.get("blocks", data)
        if isinstance(blocks, dict):
            for block_id, block_data in blocks.items():
                if isinstance(block_data, dict):
                    sentences = block_data.get("sentences", [])
                    # Extract text for writing, but keep original for alignment
                    text_sentences = [extract_sentence_text(s) for s in sentences]
                    btype = block_data.get("type", "paragraph")
                    translations[block_id] = {
                        "sentences": text_sentences,
                        "type": btype,
                        "sentence_count": len(text_sentences),
                    }
                elif isinstance(block_data, list):
                    text_sentences = [extract_sentence_text(s) for s in block_data]
                    translations[block_id] = {
                        "sentences": text_sentences,
                        "type": "paragraph",
                        "sentence_count": len(text_sentences),
                    }
        elif isinstance(blocks, list):
            for entry in blocks:
                if isinstance(entry, dict):
                    bid = entry.get("block_id", "")
                    raw_sentences = entry.get("sentences", [])
                    text_sentences = [extract_sentence_text(s) for s in raw_sentences]
                    translations[bid] = {
                        "sentences": text_sentences,
                        "type": entry.get("type", "paragraph"),
                        "sentence_count": len(text_sentences),
                    }

    return translations


def concatenate(blocked_path: Path, translations: dict, output_path: Path):
    """Concatenate translations by replacing block content in original file."""
    text = blocked_path.read_text(encoding="utf-8")
    lines = text.split("\n")

    output_lines = []
    i = 0
    missing_blocks = []
    applied_count = 0

    while i < len(lines):
        line = lines[i]
        start_match = BLOCK_START_RE.search(line)

        if start_match:
            block_id = start_match.group(1)
            block_type = start_match.group(2)

            # Collect original content lines until BLOCK_END
            block_lines = [line]
            i += 1
            while i < len(lines):
                end_match = BLOCK_END_RE.search(lines[i])
                block_lines.append(lines[i])
                if end_match and end_match.group(1) == block_id:
                    break
                i += 1

            if block_id in translations:
                trans_data = translations[block_id]
                trans_sentences = trans_data.get("sentences", [])

                if block_type in NO_TRANSLATE_TYPES:
                    # Keep original content for equations and code
                    output_lines.extend(block_lines)
                else:
                    # Write block start marker
                    output_lines.append(block_lines[0])
                    # Write translated content — each sentence on its own line
                    # to preserve the original block's multi-line structure
                    if trans_sentences:
                        output_lines.extend(trans_sentences)
                    # Write block end marker (last line of original block)
                    output_lines.append(block_lines[-1])
                    applied_count += 1
            else:
                # No translation found — keep original content
                missing_blocks.append(block_id)
                output_lines.extend(block_lines)
        else:
            output_lines.append(line)

        i += 1

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(output_lines), encoding="utf-8")

    return missing_blocks, applied_count


def main():
    parser = argparse.ArgumentParser(description="Concatenate translations into final document")
    parser.add_argument("--blocked", required=True, help="Original blocked.md with block markers")
    parser.add_argument("--translations-dir", required=True, help="Directory containing translation results")
    parser.add_argument("--output", required=True, help="Output path for assembled document")
    args = parser.parse_args()

    blocked_path = Path(args.blocked)
    translations_dir = Path(args.translations_dir)
    output_path = Path(args.output)

    if not blocked_path.exists():
        print(json.dumps({"error": f"blocked file not found: {blocked_path}"}))
        sys.exit(1)

    translations = load_translations(translations_dir)

    if not translations:
        print(json.dumps({"error": "no translations loaded from directory", "path": str(translations_dir.resolve())}))
        sys.exit(1)

    missing_blocks, applied_count = concatenate(blocked_path, translations, output_path)

    if missing_blocks:
        print(json.dumps({
            "status": "incomplete",
            "applied_blocks": applied_count,
            "missing_blocks": missing_blocks,
            "output_path": str(output_path.resolve()),
            "warning": f"{len(missing_blocks)} block(s) missing translation",
        }, ensure_ascii=False))
    else:
        print(json.dumps({
            "status": "ok",
            "applied_blocks": applied_count,
            "output_path": str(output_path.resolve()),
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()

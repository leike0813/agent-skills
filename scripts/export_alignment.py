#!/usr/bin/env python3
"""
export_alignment.py — Export bilingual alignment data for literature-translator.

Reads the source sentences, restored translations, and QA report to produce
a structured alignment file (alignment.json) with sentence-level bilingual
pairs and QA status.

The alignment file serves as the foundation for downstream literature
reading skills (bilingual reading, sentence-level explanation, etc.).
"""
import argparse
import json
import re
import sys
from pathlib import Path


def natural_sort_key(block_id: str) -> list:
    """Sort block IDs naturally (b_002 < b_010 < b_100)."""
    parts = re.split(r'(\d+)', block_id)
    return [int(p) if p.isdigit() else p for p in parts]


def extract_sentence_text(item) -> str:
    """Extract text from a sentence item, handling v1 (string) and v2 ([idx, text]) formats."""
    if isinstance(item, (list, tuple)):
        return str(item[1]) if len(item) > 1 else ""
    return str(item)


def extract_sentence_index(item) -> int:
    """Extract the 1-based index from a sentence item. Returns -1 for v1 format."""
    if isinstance(item, (list, tuple)) and len(item) >= 2 and isinstance(item[0], int):
        return item[0]
    return -1


def load_sentences(path: Path) -> dict:
    """Load and validate a sentences.json file."""
    if not path.exists():
        return {"error": f"file not found: {path}"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if "blocks" not in data:
            return {"error": "invalid sentences JSON: missing 'blocks' key"}
        return data
    except json.JSONDecodeError as e:
        return {"error": f"invalid JSON: {e}"}


def load_translations(translations_dir: Path) -> dict[str, dict]:
    """Load all restored translation results.

    Returns dict mapping block_id -> {sentences: [[idx, text], ...], type: str}
    """
    translations = {}
    if not translations_dir.exists():
        return {"error": f"translations directory not found: {translations_dir}"}

    for f in sorted(translations_dir.iterdir()):
        if not f.name.endswith(".json"):
            continue
        if f.name in ("manifest.json",):
            continue

        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        blocks = data.get("blocks", data)
        if isinstance(blocks, dict):
            for block_id, block_data in blocks.items():
                if isinstance(block_data, dict):
                    translations[block_id] = {
                        "sentences": block_data.get("sentences", []),
                        "type": block_data.get("type", "unknown"),
                    }

    return translations


def load_qa_report(path: Path) -> dict | None:
    """Load QA report if available."""
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def build_status_map(qa_data: dict | None, block_id: str, sentence_index: int) -> dict:
    """Build a status entry for a sentence from QA report data."""
    default = {"status": "passed", "repair_count": 0}

    if not qa_data:
        return default

    # Check repaired items
    for item in qa_data.get("repaired_items", []):
        if item.get("b") == block_id and item.get("i") == sentence_index:
            return {"status": "repaired", "repair_count": item.get("repair_count", 1)}

    # Check risky items
    for item in qa_data.get("risky_items", []):
        if item.get("b") == block_id and item.get("i") == sentence_index:
            return {"status": "risky", "repair_count": item.get("repair_count", 0)}

    return default


def build_alignment(
    source_sentences: dict,
    restored_translations: dict[str, dict],
    qa_data: dict | None = None,
    source_language: str = "en",
    target_language: str = "zh-CN",
    doc_id: str = "D1",
    glossary_version: str = "unknown",
) -> dict:
    """Build bilingual alignment data."""
    source_blocks = source_sentences.get("blocks", {})

    alignment = {
        "format": "v1",
        "doc_id": doc_id,
        "source_language": source_language,
        "target_language": target_language,
        "metadata": {
            "glossary_version": glossary_version,
        },
        "blocks": [],
    }

    for block_id in sorted(source_blocks.keys(), key=natural_sort_key):
        src_block = source_blocks[block_id]
        tgt_data = restored_translations.get(block_id, {})

        src_type = src_block.get("type", "unknown")
        src_heading = src_block.get("heading", "")

        src_sentences_raw = src_block.get("sentences", [])
        tgt_sentences_raw = tgt_data.get("sentences", []) if tgt_data else []

        # Handle both v1 and v2 source formats
        pairs = []
        for i, src_item in enumerate(src_sentences_raw):
            src_text = extract_sentence_text(src_item)
            src_idx = extract_sentence_index(src_item)
            if src_idx < 0:
                src_idx = i + 1  # fallback to 1-based position

            # Get corresponding translation
            tgt_text = ""
            if i < len(tgt_sentences_raw):
                tgt_item = tgt_sentences_raw[i]
                tgt_text = extract_sentence_text(tgt_item)

            status_info = build_status_map(qa_data, block_id, src_idx)

            pairs.append({
                "i": src_idx,
                "src": src_text,
                "tgt": tgt_text,
                "status": status_info["status"],
                "repair_count": status_info.get("repair_count", 0),
            })

        # Build block-level markdown by concatenating all sentence texts
        source_markdown = "\n".join(
            extract_sentence_text(item)
            for item in src_sentences_raw
            if extract_sentence_text(item)
        ).strip()
        translated_markdown = "\n".join(
            extract_sentence_text(item)
            for item in tgt_sentences_raw
            if extract_sentence_text(item)
        ).strip()

        alignment["blocks"].append({
            "b": block_id,
            "type": src_type,
            "heading": src_heading,
            "source_markdown": source_markdown,
            "translated_markdown": translated_markdown,
            "pairs": pairs,
        })

    return alignment


def main():
    parser = argparse.ArgumentParser(description="Export bilingual alignment data")
    parser.add_argument("--sentences", required=True,
                        help="Path to original sentences.json from sentencify.py")
    parser.add_argument("--translations-dir", required=True,
                        help="Directory containing restored translation JSON files")
    parser.add_argument("--output", required=True,
                        help="Output path for alignment.json")
    parser.add_argument("--qa-report", default=None,
                        help="Optional path to qa_report.json for status information")
    parser.add_argument("--source-lang", default="en",
                        help="Source language code (default: en)")
    parser.add_argument("--target-lang", default="zh-CN",
                        help="Target language code (default: zh-CN)")
    parser.add_argument("--doc-id", default="D1",
                        help="Document identifier (default: D1)")
    parser.add_argument("--glossary-version", default="unknown",
                        help="Glossary version identifier")
    args = parser.parse_args()

    # Load source sentences
    sentences_data = load_sentences(Path(args.sentences))
    if "error" in sentences_data:
        print(json.dumps({"error": f"sentences: {sentences_data['error']}"}))
        sys.exit(1)

    # Load restored translations
    translations = load_translations(Path(args.translations_dir))
    if isinstance(translations, dict) and "error" in translations:
        print(json.dumps({"error": f"translations: {translations['error']}"}))
        sys.exit(1)
    if not translations:
        print(json.dumps({"error": "no translations loaded"}))
        sys.exit(1)

    # Load QA report (optional)
    qa_data = None
    if args.qa_report:
        qa_data = load_qa_report(Path(args.qa_report))

    # Build alignment
    alignment = build_alignment(
        source_sentences=sentences_data,
        restored_translations=translations,
        qa_data=qa_data,
        source_language=args.source_lang,
        target_language=args.target_lang,
        doc_id=args.doc_id,
        glossary_version=args.glossary_version,
    )

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(alignment, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Count stats
    total_pairs = sum(len(b["pairs"]) for b in alignment["blocks"])
    passed = sum(
        1 for b in alignment["blocks"] for p in b["pairs"] if p["status"] == "passed"
    )
    repaired = sum(
        1 for b in alignment["blocks"] for p in b["pairs"] if p["status"] == "repaired"
    )
    risky = sum(
        1 for b in alignment["blocks"] for p in b["pairs"] if p["status"] == "risky"
    )

    result = {
        "status": "ok",
        "total_blocks": len(alignment["blocks"]),
        "total_pairs": total_pairs,
        "passed": passed,
        "repaired": repaired,
        "risky": risky,
        "output": str(output_path.resolve()),
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

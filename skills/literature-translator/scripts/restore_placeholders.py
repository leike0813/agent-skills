#!/usr/bin/env python3
"""
restore_placeholders.py — Restore original values from placeholders.

Reads translation JSON files and the placeholder map from protect_placeholders.py,
replaces all placeholders in translated sentences with their original values,
and writes the restored translations.

This is run after translation + quality gate + review, before concatenation.
"""
import argparse
import json
import re
import sys
from pathlib import Path


PH_RE = re.compile(r'<[A-Z]+(?:_[A-Z]+)?_\d+>')


def restore_text(text: str, entries: dict[str, str]) -> str:
    """Replace all placeholders in text with their original values."""
    def replace_match(m: re.Match) -> str:
        ph = m.group(0)
        return entries.get(ph, ph)  # fallback: keep placeholder if not found
    return PH_RE.sub(replace_match, text)


def restore_sentence(item, entries: dict[str, str]):
    """Restore a single sentence (handles both v1 string and v2 [idx, text] formats)."""
    if isinstance(item, (list, tuple)):
        return [item[0], restore_text(item[1], entries)]
    else:
        return restore_text(item, entries)


def restore_translation_file(
    translation_path: Path,
    placeholder_map: dict,
    output_path: Path
):
    """Restore placeholders in a translation result file and write to output."""
    data = json.loads(translation_path.read_text(encoding="utf-8"))
    entries = placeholder_map.get("entries", {})

    restored_count = 0
    for block_id, block_data in data.get("blocks", {}).items():
        sentences = block_data.get("sentences", [])
        restored = []
        for item in sentences:
            restored.append(restore_sentence(item, entries))
        data["blocks"][block_id]["sentences"] = restored
        restored_count += len(restored)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return restored_count


def main():
    parser = argparse.ArgumentParser(description="Restore placeholders in translations")
    parser.add_argument(
        "--translations-dir", required=True,
        help="Directory containing translation batch JSON files"
    )
    parser.add_argument(
        "--placeholder-map", required=True,
        help="Path to placeholder_map.json"
    )
    parser.add_argument(
        "--output-dir", required=True,
        help="Output directory for restored translation files"
    )
    parser.add_argument(
        "--pattern", default="*_translated.json",
        help="Glob pattern for translation files (default: *_translated.json)"
    )
    args = parser.parse_args()

    map_path = Path(args.placeholder_map)
    if not map_path.exists():
        print(json.dumps({"error": f"placeholder map not found: {map_path}"}))
        sys.exit(1)

    placeholder_map = json.loads(map_path.read_text(encoding="utf-8"))
    entries = placeholder_map.get("entries", {})

    if not entries:
        print(json.dumps({"warning": "placeholder map is empty, nothing to restore",
                          "status": "ok"}))
        sys.exit(0)

    translations_dir = Path(args.translations_dir)
    if not translations_dir.exists():
        print(json.dumps({"error": f"translations dir not found: {translations_dir}"}))
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    import glob
    pattern = args.pattern
    translation_files = sorted(translations_dir.glob(pattern))

    if not translation_files:
        print(json.dumps({
            "error": f"no translation files matching '{pattern}' in {translations_dir}"
        }))
        sys.exit(1)

    results = []
    total_restored = 0
    for tf in translation_files:
        out_path = output_dir / tf.name
        count = restore_translation_file(tf, placeholder_map, out_path)
        total_restored += count
        results.append({
            "file": tf.name,
            "output": str(out_path.resolve()),
            "restored_sentences": count,
        })

    result = {
        "status": "ok",
        "total_files": len(results),
        "total_restored_sentences": total_restored,
        "files": results,
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

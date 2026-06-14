#!/usr/bin/env python3
"""
export_qa_report.py — Export structured quality report for literature-translator.

Aggregates quality gate results, review results, repair records, and risky
items into a structured QA report (qa_report.json).

This runs at the end of the pipeline after all checks, reviews, and repairs
are complete. The report provides a summary of translation quality and
identifies specific items that need human attention.
"""
import argparse
import json
import re
import sys
from pathlib import Path


def load_json(path: Path) -> dict | None:
    """Load and validate a JSON file, returning None if not found."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def load_all_gate_results(translations_dir: Path) -> list[dict]:
    """Read quality gate results from translation batch files.

    Each translated JSON may contain a 'quality_gate' field injected
    by the pipeline after running quality_gate.py.
    """
    results = []
    if not translations_dir.exists():
        return results

    for f in sorted(translations_dir.iterdir()):
        if not f.name.endswith("_translated.json"):
            continue
        data = load_json(f)
        if data and "quality_gate" in data:
            results.append(data["quality_gate"])
    return results


def aggregate_checks(gate_results: list[dict]) -> dict:
    """Aggregate quality gate check results across all batches."""
    check_names = [
        "sentence_count", "lazy_translation", "term_consistency",
        "language", "placeholder_preservation", "numeric_preservation",
        "non_translation_phrases", "length_check",
    ]

    checks_summary = {}
    for name in check_names:
        passed_batches = 0
        total_batches = 0
        for gate in gate_results:
            checks = gate.get("checks", {})
            if name in checks:
                total_batches += 1
                if checks[name].get("passed", False):
                    passed_batches += 1

        if total_batches > 0:
            if passed_batches == total_batches:
                checks_summary[name] = "passed"
            elif passed_batches == 0:
                checks_summary[name] = "failed"
            else:
                checks_summary[name] = "warning"
        else:
            checks_summary[name] = "skipped"

    return checks_summary


def build_qa_report(
    block_stats: dict,
    gate_results: list[dict],
    repaired_items: list[dict] | None = None,
    risky_items: list[dict] | None = None,
    doc_id: str = "D1",
) -> dict:
    """Build structured QA report."""
    repaired = repaired_items or []
    risky = risky_items or []

    # Calculate total units (sentences) from block stats
    total_units = block_stats.get("total_sentences",
                   block_stats.get("total_units", 0))
    total_blocks = block_stats.get("blocks",
                   block_stats.get("total_blocks", 0))

    # Count pass-through blocks (equation, code)
    passthrough = block_stats.get("no_split", 0)

    # Calculate passed units
    repaired_count = len(repaired)
    risky_count = len(risky)
    passed_units = max(0, total_units - repaired_count - risky_count)

    return {
        "format": "v1",
        "doc_id": doc_id,
        "summary": {
            "total_blocks": total_blocks,
            "translated_blocks": total_blocks - passthrough,
            "passthrough_blocks": passthrough,
            "total_units": total_units,
            "passed_units": passed_units,
            "repaired_units": repaired_count,
            "risky_units": risky_count,
        },
        "checks": aggregate_checks(gate_results),
        "repaired_items": [
            {
                "b": item.get("b", item.get("block_id", "")),
                "i": item.get("i", item.get("sentence_index", 0)),
                "error_type": item.get("type", item.get("error_type", "unknown")),
                "repair_count": item.get("repair_count", 1),
            }
            for item in repaired
        ],
        "risky_items": [
            {
                "b": item.get("b", item.get("block_id", "")),
                "i": item.get("i", item.get("sentence_index", 0)),
                "reason": item.get("reason", "exceeded max repair attempts"),
                "source": item.get("source", ""),
                "best_translation": item.get("best_translation", ""),
            }
            for item in risky
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Export QA report")
    parser.add_argument("--block-stats", required=True,
                        help="Path to block_stats.json or sentences.json for stats")
    parser.add_argument("--translations-dir", required=True,
                        help="Directory containing translated JSON files")
    parser.add_argument("--output", required=True,
                        help="Output path for qa_report.json")
    parser.add_argument("--repaired-items", default=None,
                        help="Optional JSON file with repaired items list")
    parser.add_argument("--risky-items", default=None,
                        help="Optional JSON file with risky items list")
    parser.add_argument("--doc-id", default="D1",
                        help="Document identifier (default: D1)")
    args = parser.parse_args()

    # Load block stats
    block_stats_path = Path(args.block_stats)
    block_stats = load_json(block_stats_path)
    if block_stats is None:
        print(json.dumps({"error": f"block stats file not found: {block_stats_path}"}))
        sys.exit(1)

    # Load quality gate results from translations
    gate_results = load_all_gate_results(Path(args.translations_dir))

    # Load repaired items (optional)
    repaired_items = None
    if args.repaired_items:
        repaired_path = Path(args.repaired_items)
        if repaired_path.exists():
            data = load_json(repaired_path)
            if data:
                repaired_items = data if isinstance(data, list) else data.get("items", [])

    # Load risky items (optional)
    risky_items = None
    if args.risky_items:
        risky_path = Path(args.risky_items)
        if risky_path.exists():
            data = load_json(risky_path)
            if data:
                risky_items = data if isinstance(data, list) else data.get("items", [])

    # Build report
    report = build_qa_report(
        block_stats=block_stats if block_stats else {},
        gate_results=gate_results,
        repaired_items=repaired_items,
        risky_items=risky_items,
        doc_id=args.doc_id,
    )

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    result = {
        "status": "ok",
        "summary": report["summary"],
        "checks": report["checks"],
        "output": str(output_path.resolve()),
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

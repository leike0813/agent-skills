#!/usr/bin/env python3
"""
partition_batches.py — Translation batch partitioner for literature-translator.

Reads the sentences JSON from sentencify.py, groups blocks into batches
targeting a character threshold. Keeps blocks intact (never splits a block
across batches). Aims to balance batch sizes.

Deterministic script — does NOT perform semantic analysis.
"""
import argparse
import json
import os
import sys
from pathlib import Path
import tiktoken


_ENCODER = None


def _count_tokens(text: str) -> int:
    """Count tokens using cl100k_base encoding (GPT-4/GPT-3.5 tokenizer)."""
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    return len(_ENCODER.encode(text))


def load_sentences(path: Path) -> dict:
    """Load and validate the sentences JSON."""
    if not path.exists():
        print(json.dumps({"error": f"sentences file not found: {path}"}))
        sys.exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    if "blocks" not in data:
        print(json.dumps({"error": "invalid sentences JSON: missing 'blocks' key"}))
        sys.exit(1)

    return data


def calculate_block_sizes(blocks: dict) -> list[dict]:
    """Calculate token count metrics for each block and sort by block_id."""
    block_list = []
    for block_id, block_data in blocks.items():
        sentences = block_data.get("sentences", [])
        # Handle both v1 (string[]) and v2 ([[index, text], ...]) formats
        if sentences and isinstance(sentences[0], (list, tuple)):
            total_tokens = sum(_count_tokens(s[1]) for s in sentences)
        else:
            total_tokens = sum(_count_tokens(s) for s in sentences)
        block_list.append({
            "block_id": block_id,
            "type": block_data.get("type", "unknown"),
            "sentence_count": block_data.get("sentence_count", len(sentences)),
            "total_tokens": total_tokens,
            "sentences": sentences,
        })

    # Sort by block_id for stable ordering
    block_list.sort(key=lambda b: b["block_id"])
    return block_list


def partition(block_list: list[dict], target_size: int) -> list[dict]:
    """Partition blocks into batches.

    Uses a greedy algorithm: add blocks until the batch exceeds target_size,
    then start a new batch. Single blocks larger than target_size get their own batch.
    """
    batches = []
    current_batch = []
    current_tokens = 0

    for block in block_list:
        token_count = block["total_tokens"]

        # If this block fits in the current batch, add it
        if current_tokens + token_count <= target_size or not current_batch:
            current_batch.append(block)
            current_tokens += token_count
        else:
            # Start new batch
            batches.append({
                "blocks": current_batch,
                "total_tokens": current_tokens,
            })
            current_batch = [block]
            current_tokens = token_count

    # Don't forget the last batch
    if current_batch:
        batches.append({
            "blocks": current_batch,
            "total_tokens": current_tokens,
        })

    return batches


def write_batch_files(batches: list[dict], workspace: Path):
    """Write batch payload files and manifest."""
    workspace.mkdir(parents=True, exist_ok=True)

    manifest = {
        "batch_count": len(batches),
        "target_size_tokens": target_size,
        "batches": [],
    }

    for i, batch in enumerate(batches):
        batch_id = f"batch_{i:04d}"
        block_ids = [b["block_id"] for b in batch["blocks"]]

        batch_payload = {
            "batch_id": batch_id,
            "block_ids": block_ids,
            "total_tokens": batch["total_tokens"],
            "blocks": {
                b["block_id"]: {
                    "type": b["type"],
                    "sentence_count": b["sentence_count"],
                    "sentences": b["sentences"],
                }
                for b in batch["blocks"]
            },
        }

        batch_path = workspace / f"{batch_id}.json"
        batch_path.write_text(json.dumps(batch_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        manifest["batches"].append({
            "batch_id": batch_id,
            "block_count": len(block_ids),
            "total_tokens": batch["total_tokens"],
            "block_ids": block_ids,
            "payload_path": str(batch_path.resolve()),
        })

    manifest_path = workspace / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return manifest, manifest_path


def main():
    parser = argparse.ArgumentParser(description="Partition translation sentences into batches")
    parser.add_argument("--sentences", required=True, help="Path to sentences.json from sentencify.py")
    parser.add_argument("--workspace", required=True, help="Output directory for batch files")
    parser.add_argument("--target-size", type=int, default=1500, help="Target batch size in tokens (default: 1500)")
    args = parser.parse_args()

    global target_size
    target_size = args.target_size

    if target_size < 100:
        print(json.dumps({"error": "target-size too small, minimum 100"}))
        sys.exit(1)

    sentences_path = Path(args.sentences)
    data = load_sentences(sentences_path)
    blocks = data.get("blocks", {})

    if not blocks:
        print(json.dumps({"error": "no blocks found in sentences.json"}))
        sys.exit(1)

    block_list = calculate_block_sizes(blocks)
    batches = partition(block_list, target_size)

    # Calculate stats
    batch_tokens = [b["total_tokens"] for b in batches]
    stats = {
        "batch_count": len(batches),
        "total_blocks": len(block_list),
        "total_tokens": sum(b["total_tokens"] for b in batches),
        "target_size": target_size,
        "min_batch_tokens": min(batch_tokens) if batch_tokens else 0,
        "max_batch_tokens": max(batch_tokens) if batch_tokens else 0,
        "avg_batch_tokens": sum(batch_tokens) // len(batch_tokens) if batch_tokens else 0,
    }

    workspace = Path(args.workspace)
    manifest, manifest_path = write_batch_files(batches, workspace)

    result = {
        "status": "ok",
        "stats": stats,
        "manifest_path": str(manifest_path.resolve()),
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

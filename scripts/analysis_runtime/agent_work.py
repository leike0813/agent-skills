from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BATCH_MAX_ITEMS = 10
AGENT_WORK_DIRNAME = "agent_work"


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def work_root(db_path: Path, kind: str) -> Path:
    return db_path.parent / AGENT_WORK_DIRNAME / kind


def chunked(items: list[Any], size: int = BATCH_MAX_ITEMS) -> list[list[Any]]:
    return [items[offset : offset + size] for offset in range(0, len(items), size)]


def write_manifest(
    *,
    db_path: Path,
    kind: str,
    batch_kind: str,
    package_key: str,
    packages: list[dict[str, Any]],
    package_key_field: str,
    batch_payload_builder: Any,
    subagent_policy: str,
    merge_contract: dict[str, Any],
    payload_submit_shape: dict[str, Any],
    batch_prefix: str,
    manifest_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = work_root(db_path, kind)
    root.mkdir(parents=True, exist_ok=True)
    batch_paths: list[str] = []
    coverage_keys = [str(package[package_key_field]) for package in packages]
    for batch_index, batch_packages in enumerate(chunked(packages)):
        batch_id = f"{batch_prefix}-{batch_index}"
        batch_path = root / f"{batch_id}.json"
        draft_path = root / f"{batch_id}.draft.json"
        batch_payload = batch_payload_builder(batch_id, batch_packages)
        batch_payload.update(
            {
                "batch_id": batch_id,
                "batch_key": batch_id,
                "batch_kind": batch_kind,
                "input_package_path": str(batch_path),
                "suggested_draft_output_path": str(draft_path),
                "batch_max_items": BATCH_MAX_ITEMS,
            }
        )
        write_json(batch_path, batch_payload)
        batch_paths.append(str(batch_path))
    manifest_path = root / f"{kind}_manifest.json"
    manifest = {
        "kind": kind,
        "batch_kind": batch_kind,
        "batch_max_items": BATCH_MAX_ITEMS,
        "batch_paths": batch_paths,
        "batch_count": len(batch_paths),
        "package_count": len(packages),
        "required_coverage_keys": coverage_keys,
        "merge_contract": merge_contract,
        "subagent_policy": subagent_policy,
        "payload_submit_shape": payload_submit_shape,
        "main_agent_workflow": [
            "Pass each batch JSON file path to a subagent.",
            "Subagent reads only that batch file and returns or writes the batch draft JSON.",
            "Main agent reads drafts, checks required_coverage_keys exactly once, and submits one official payload.",
        ],
    }
    if manifest_extra:
        manifest.update(manifest_extra)
    write_json(manifest_path, manifest)
    return {
        "manifest_path": str(manifest_path),
        "batch_paths": batch_paths,
        "batch_count": len(batch_paths),
        "package_count": len(packages),
        "required_coverage_keys": coverage_keys,
    }


def write_package_file(db_path: Path, kind: str, filename: str, payload: dict[str, Any]) -> str:
    path = work_root(db_path, kind) / filename
    write_json(path, payload)
    return str(path)

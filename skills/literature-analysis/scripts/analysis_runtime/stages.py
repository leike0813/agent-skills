from __future__ import annotations

from pathlib import Path
from typing import Any

from . import deterministic_core
from .algorithm_adapter import call_algorithm_handler
from .runtime import AnalysisRuntimePaths


def normalize_source(
    *,
    source_path: Path,
    db_path: Path,
    runtime_paths: AnalysisRuntimePaths,
    language: str,
    model: str,
) -> tuple[dict[str, object], int]:
    dispatch_paths = deterministic_core.DispatchPaths(
        source_md_path=(runtime_paths.tmp_dir / "source.md").resolve(),
        source_meta_path=(runtime_paths.tmp_dir / "source_meta.json").resolve(),
    )
    return deterministic_core._dispatch_source(
        source_path=source_path.resolve(),
        output_paths=dispatch_paths,
        disable_pymupdf4llm=False,
        db_path=db_path.resolve(),
        persist_db_only=False,
        language=language or "zh-CN",
        model=model or "",
    )


def persist_analysis_plan(db_path: Path, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    result, code = call_algorithm_handler("_handle_persist_outline_and_scopes", db_path, payload=payload)
    if code == 0:
        result.update({"db_path": str(db_path), "runtime_backend": "analysis_runtime.stages", "next_action": "persist_digest"})
    return result, code


def persist_digest(db_path: Path, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    result, code = call_algorithm_handler("_handle_persist_digest", db_path, payload=payload)
    if code == 0:
        result.update({"db_path": str(db_path), "runtime_backend": "analysis_runtime.stages", "next_action": "persist_references"})
    return result, code


def render_public_outputs(db_path: Path) -> tuple[dict[str, Any], int]:
    return call_algorithm_handler(
        "_handle_render_and_validate",
        db_path,
        mode="render",
        source_path="",
        preprocess_artifact="",
        in_path="",
        out_dir="",
    )

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import deterministic_core
from . import reference_api
from . import runtime_db


TMP_DIRNAME = ".literature_analysis_tmp"
RESULT_JSON_FILENAME = "literature-analysis.result.json"
RUNTIME_TEMPLATES_DIRNAME = "templates"
RUNTIME_DIGEST_TEMPLATE_FILENAME = "digest.runtime.md.j2"
RUNTIME_CITATION_TEMPLATE_FILENAME = "citation_analysis.runtime.md.j2"
RUNTIME_SCORE_TEMPLATE_FILENAME = "literature_score.runtime.json.j2"
RUNTIME_SCORING_RUBRIC_FILENAME = "scoring_rubric.runtime.json"


@dataclass(frozen=True)
class AnalysisRuntimePaths:
    working_dir: Path
    tmp_dir: Path
    db_path: Path
    result_json_path: Path
    output_dir: Path


def default_db_path(working_dir: Path) -> Path:
    return (working_dir / TMP_DIRNAME / "literature_analysis.db").resolve()


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def initialize_runtime(
    *,
    working_dir: Path,
    db_path: Path,
    output_dir: Path,
    source_path: Path,
    language: str,
    model: str,
    score_only: bool = False,
    identifier: str = "",
) -> AnalysisRuntimePaths:
    runtime_paths = AnalysisRuntimePaths(
        working_dir=working_dir.resolve(),
        tmp_dir=db_path.parent.resolve(),
        db_path=db_path.resolve(),
        result_json_path=(working_dir / RESULT_JSON_FILENAME).resolve(),
        output_dir=output_dir.resolve(),
    )
    runtime_db.initialize_database(runtime_paths.db_path)
    with runtime_db.connect_db(runtime_paths.db_path) as connection:
        for key, value in {
            "working_dir": runtime_paths.working_dir,
            "tmp_dir": runtime_paths.tmp_dir,
            "db_path": runtime_paths.db_path,
            "result_json_path": runtime_paths.result_json_path,
            "output_dir": runtime_paths.output_dir,
            "source_path": source_path.resolve(),
        }.items():
            runtime_db.set_runtime_input(connection, key, str(value))
        runtime_db.set_runtime_input(connection, "language", language or "zh-CN")
        runtime_db.set_runtime_input(connection, "score_only", "true" if score_only else "false")
        runtime_db.set_runtime_input(connection, "identifier", identifier.strip())
        normalized_identifier = reference_api.normalize_identifier(identifier)
        runtime_db.set_runtime_input(
            connection,
            "identifier_canonical",
            normalized_identifier.canonical if normalized_identifier is not None else "",
        )
        runtime_db.set_runtime_input(
            connection,
            "identifier_kind",
            normalized_identifier.kind if normalized_identifier is not None else "",
        )
        runtime_db.set_runtime_input(
            connection,
            "identifier_value",
            normalized_identifier.value if normalized_identifier is not None else "",
        )
        if identifier.strip() and normalized_identifier is None:
            runtime_db.add_runtime_warning_once(connection, "invalid_identifier: falling back to analysis-plan source identity")
        runtime_db.set_runtime_input(connection, "input_hash", deterministic_core.sha256_path(source_path.resolve()) if source_path.exists() else "")
        runtime_db.set_runtime_input(connection, "generated_at", runtime_db.utc_now_iso())
        if model:
            runtime_db.set_runtime_input(connection, "model", model)
        runtime_db.set_workflow_state(
            connection,
            current_stage="stage_1_normalize_source",
            current_substep="persist_render_templates",
            stage_gate="ready",
            next_action="persist_render_templates",
            status_summary="analysis runtime initialized",
        )
        runtime_db.store_action_receipt(
            connection,
            action_name="confirm_runtime_paths",
            stage="stage_0_bootstrap",
            metadata={
                "working_dir": str(runtime_paths.working_dir),
                "tmp_dir": str(runtime_paths.tmp_dir),
                "db_path": str(runtime_paths.db_path),
                "result_json_path": str(runtime_paths.result_json_path),
                "output_dir": str(runtime_paths.output_dir),
            },
        )
        runtime_db.store_action_receipt(connection, action_name="bootstrap_runtime_db", stage="stage_0_bootstrap")
        connection.commit()
    return runtime_paths


def persist_default_templates(*, db_path: Path, runtime_paths: AnalysisRuntimePaths, language: str) -> dict[str, str]:
    target_language = language or "zh-CN"
    digest_template = deterministic_core._repo_digest_template_path(target_language).read_text(encoding="utf-8")
    citation_template = deterministic_core._repo_citation_template_path(target_language).read_text(encoding="utf-8")
    score_template = (deterministic_core.TEMPLATES_DIR / "literature_score.json.j2").read_text(encoding="utf-8")
    scoring_rubric = (deterministic_core.ASSETS_DIR / "scoring_rubric.json").read_text(encoding="utf-8")
    templates_dir = runtime_paths.tmp_dir / RUNTIME_TEMPLATES_DIRNAME
    digest_template_path = (templates_dir / RUNTIME_DIGEST_TEMPLATE_FILENAME).resolve()
    citation_template_path = (templates_dir / RUNTIME_CITATION_TEMPLATE_FILENAME).resolve()
    score_template_path = (templates_dir / RUNTIME_SCORE_TEMPLATE_FILENAME).resolve()
    scoring_rubric_path = (templates_dir / RUNTIME_SCORING_RUBRIC_FILENAME).resolve()
    _write_text(digest_template_path, digest_template)
    _write_text(citation_template_path, citation_template)
    _write_text(score_template_path, score_template)
    _write_text(scoring_rubric_path, scoring_rubric)
    with runtime_db.connect_db(db_path) as connection:
        runtime_db.set_runtime_input(connection, "digest_template_path", str(digest_template_path))
        runtime_db.set_runtime_input(connection, "citation_analysis_template_path", str(citation_template_path))
        runtime_db.set_runtime_input(connection, "literature_score_template_path", str(score_template_path))
        runtime_db.set_runtime_input(connection, "scoring_rubric_path", str(scoring_rubric_path))
        runtime_db.set_workflow_state(
            connection,
            current_stage="stage_1_normalize_source",
            current_substep="normalize_source",
            stage_gate="ready",
            next_action="normalize_source",
            status_summary="analysis runtime templates persisted",
        )
        runtime_db.store_action_receipt(
            connection,
            action_name="persist_render_templates",
            stage="stage_1_normalize_source",
            metadata={
                "target_language": target_language,
                "digest_template_path": str(digest_template_path),
                "citation_analysis_template_path": str(citation_template_path),
                "literature_score_template_path": str(score_template_path),
                "scoring_rubric_path": str(scoring_rubric_path),
            },
        )
        connection.commit()
    return {
        "target_language": target_language,
        "digest_template_path": str(digest_template_path),
        "citation_analysis_template_path": str(citation_template_path),
        "literature_score_template_path": str(score_template_path),
        "scoring_rubric_path": str(scoring_rubric_path),
    }


def source_profile(db_path: Path) -> dict[str, object]:
    with runtime_db.connect_db(db_path) as connection:
        inputs = runtime_db.fetch_runtime_inputs(connection)
        source_doc = runtime_db.fetch_source_document(connection, "normalized_source")
        state = runtime_db.fetch_workflow_state(connection)
    metadata = dict(source_doc.get("metadata", {})) if source_doc else {}
    quality = metadata.get("quality", {})
    return {
        "source_path": inputs.get("source_path", ""),
        "language": inputs.get("language", "zh-CN"),
        "score_only": inputs.get("score_only", "false").strip().lower() == "true",
        "identifier": inputs.get("identifier_canonical", ""),
        "identifier_status": (
            "valid"
            if inputs.get("identifier_canonical")
            else ("invalid" if inputs.get("identifier") else "absent")
        ),
        "input_hash": inputs.get("input_hash", ""),
        "source_type": metadata.get("source_type", ""),
        "conversion_backend": metadata.get("conversion_backend", ""),
        "quality": quality if isinstance(quality, dict) else {},
        "normalized_source_chars": len(str(source_doc.get("content", ""))) if source_doc else 0,
        "workflow_state": state or {},
    }


def runtime_status(db_path: Path) -> dict[str, object]:
    with runtime_db.connect_db(db_path) as connection:
        state = runtime_db.fetch_workflow_state(connection)
        receipts = runtime_db.fetch_action_receipts(connection)
        error = runtime_db.fetch_latest_error(connection)
    return {
        "db_path": str(db_path),
        "workflow_state": state or {},
        "receipts": sorted(receipts),
        "error": error,
    }

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from . import runtime_db


CATALOGUE_PATH = Path(__file__).resolve().parents[2] / "assets" / "literature_profiles.json"
PROFILE_IDS = (
    "quantitative_empirical", "qualitative_empirical", "interpretive_historical", "conceptual_normative",
    "formal_theoretical", "review_synthesis", "mixed_methods", "general",
)
CLASSIFICATION_ACTION = "persist_literature_classification"
CLASSIFICATION_STAGE = "stage_1_classification"


def load_catalogue(path: Path = CATALOGUE_PATH) -> dict[str, Any]:
    catalogue = json.loads(path.read_text(encoding="utf-8"))
    if catalogue.get("schema") != "literature_profiles.v1" or set(catalogue.get("profiles", {})) != set(PROFILE_IDS):
        raise ValueError("invalid literature profile catalogue")
    return catalogue


def normalize_classification(value: object, catalogue: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"disciplines", "profile_id", "confidence", "reason"}:
        raise ValueError("literature_classification requires disciplines, profile_id, confidence and reason")
    disciplines = value["disciplines"]
    if not isinstance(disciplines, list) or any(not isinstance(item, str) or not item.strip() for item in disciplines):
        raise ValueError("disciplines must be an array of non-empty labels")
    profile_id = value["profile_id"]
    if not isinstance(profile_id, str):
        raise ValueError("unknown profile_id")
    profile_id = profile_id.strip().lower()
    if profile_id not in catalogue["profiles"]:
        raise ValueError("unknown profile_id")
    confidence = value["confidence"]
    if not isinstance(confidence, str) or confidence.strip().lower() not in ("high", "medium", "low"):
        raise ValueError("confidence must be high, medium or low")
    confidence = confidence.strip().lower()
    if not isinstance(value["reason"], str) or not value["reason"].strip():
        raise ValueError("classification reason must be non-empty")
    return {
        "disciplines": list(dict.fromkeys(item.strip() for item in disciplines)),
        "profile_id": "general" if confidence == "low" else profile_id,
        "confidence": confidence,
        "reason": value["reason"].strip(),
    }


def resolve_profile(catalogue: dict[str, Any], profile_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    profile = deepcopy(catalogue["profiles"][profile_id])
    rubric = {
        "rubric_id": profile["rubric_id"],
        "dimensions": [
            {**deepcopy(catalogue["dimensions"][item["dimension_key"]]), "weight": item["weight"]}
            for item in profile["dimensions"]
        ],
    }
    return profile, rubric


def require_classification(connection: Any) -> dict[str, Any]:
    snapshot = runtime_db.fetch_literature_classification(connection)
    source = runtime_db.fetch_source_document(connection, "normalized_source")
    if not snapshot or not source or not runtime_db.has_action_receipt(connection, CLASSIFICATION_ACTION):
        raise ValueError("classify the normalized source before continuing")
    if snapshot["source_hash"] != hashlib.sha256(source["content"].encode("utf-8")).hexdigest():
        raise ValueError("classification does not describe the current normalized source")
    return snapshot


def classification_error(message: str) -> tuple[dict[str, Any], int]:
    return {
        "next_action": CLASSIFICATION_ACTION,
        "warnings": [],
        "error": {"code": "classification_required", "message": message},
    }, 2


def check_classification(db_path: Path) -> tuple[dict[str, Any] | None, int]:
    if not db_path.exists():
        return classification_error("initialize and classify the source before continuing")
    with runtime_db.connect_db(db_path) as connection:
        try:
            require_classification(connection)
        except ValueError as exc:
            return classification_error(str(exc))
    return None, 0


def persist_classification(db_path: Path, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    runtime_db.initialize_database(db_path)
    with runtime_db.connect_db(db_path) as connection:
        source = runtime_db.fetch_source_document(connection, "normalized_source")
        if not source:
            return classification_error("normalized source is required")
        inputs = runtime_db.fetch_runtime_inputs(connection)
        try:
            catalogue = load_catalogue(Path(inputs.get("literature_profiles_path", str(CATALOGUE_PATH))))
            classification = normalize_classification(payload.get("literature_classification") if isinstance(payload, dict) else None, catalogue)
            profile, rubric = resolve_profile(catalogue, classification["profile_id"])
        except (ValueError, OSError, KeyError, TypeError) as exc:
            return {"next_action": CLASSIFICATION_ACTION, "warnings": [],
                    "error": {"code": "classification_invalid", "message": str(exc)}}, 2
        snapshot = {
            "classification": classification, "profile": profile, "rubric": rubric,
            "source_hash": hashlib.sha256(source["content"].encode("utf-8")).hexdigest(),
        }
        previous = runtime_db.fetch_literature_classification(connection)
        if previous == snapshot and runtime_db.has_action_receipt(connection, CLASSIFICATION_ACTION):
            state = runtime_db.fetch_workflow_state(connection) or {}
            next_action = str(state.get("next_action") or "persist_analysis_plan")
            if next_action == "persist_outline_and_scopes":
                next_action = "persist_analysis_plan"
        else:
            rubric_path = Path(inputs.get("tmp_dir", str(db_path.parent))) / "templates" / "scoring_rubric.runtime.json"
            try:
                rubric_path.parent.mkdir(parents=True, exist_ok=True)
                rubric_path.write_text(json.dumps(rubric, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError as exc:
                return {"next_action": CLASSIFICATION_ACTION, "warnings": [],
                        "error": {"code": "classification_persist_failed", "message": str(exc)}}, 2
            runtime_db.invalidate_classification_dependents(connection)
            runtime_db.store_literature_classification(connection, snapshot)
            runtime_db.store_action_receipt(connection, action_name=CLASSIFICATION_ACTION, stage=CLASSIFICATION_STAGE)
            runtime_db.set_runtime_input(connection, "scoring_rubric_path", str(rubric_path.resolve()))
            score_only = runtime_db.is_score_only(connection)
            next_action = "persist_literature_score" if score_only else "persist_analysis_plan"
            runtime_db.set_workflow_state(
                connection, current_stage="stage_4_scoring" if score_only else "stage_2_outline_and_scopes",
                current_substep=next_action, next_action=next_action, stage_gate="ready",
                status_summary="source classified and profile selected",
            )
        if classification["confidence"] == "low":
            runtime_db.add_runtime_warning_once(connection, "classification_low_confidence: using general profile")
        connection.commit()
        warnings = runtime_db.fetch_runtime_warnings(connection)
    return {
        "db_path": str(db_path), "literature_classification": classification,
        "digest_sections": profile["digest_sections"], "rubric_id": rubric["rubric_id"],
        "next_action": next_action, "warnings": warnings, "error": None,
    }, 0


def digest_headings(profile: dict[str, Any], language: str, translations: object = None) -> dict[str, str]:
    keys = ("tldr", "focus", "basis", "analysis", "limits", "section_summaries")
    if not language.lower().startswith(("en", "zh")):
        if not isinstance(translations, dict) or set(translations) != set(keys) or any(
            not isinstance(value, str) or not value.strip() for value in translations.values()
        ):
            raise ValueError("heading_translations must provide all six headings for this language")
        return {key: translations[key].strip() for key in keys}
    locale = "en-US" if language.lower().startswith("en") else "zh-CN"
    return {
        "tldr": "TL;DR",
        **{item["slot_key"]: item["heading"][locale] for item in profile["digest_sections"]},
        "section_summaries": "Section-by-Section Summary" if locale == "en-US" else "分章节总结",
    }

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from jsonschema import validate

from . import runtime_db


SKILL_DIR = Path(__file__).resolve().parents[2]
ASSETS_DIR = SKILL_DIR / "assets"
DEFAULT_RUBRIC_PATH = ASSETS_DIR / "scoring_rubric.json"
DEFAULT_TEMPLATE_PATH = ASSETS_DIR / "templates" / "literature_score.json.j2"
RENDER_SCHEMA_PATH = ASSETS_DIR / "render_schemas" / "literature_score.schema.json"
SCORE_FILENAME = "literature_score.json"
REVIEW_FORM_PREFIX = "scoring_review_form"
REVIEW_DRAFT_PREFIX = "scoring_review_draft"
EDITABLE_FIELDS = [
    "paper_type_choices[*].selected (select exactly one)",
    "paper_type_reason",
    "dimension_reviews[*].confidence",
    "dimension_reviews[*].summary",
    "criterion_reviews[*].applicable",
    "criterion_reviews[*].score",
    "criterion_reviews[*].reason",
    "criterion_reviews[*].evidence_quotes",
]


def _json_read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _rubric_path(inputs: dict[str, str]) -> Path:
    configured = inputs.get("scoring_rubric_path", "")
    return Path(configured).expanduser().resolve() if configured else DEFAULT_RUBRIC_PATH.resolve()


def _template_path(inputs: dict[str, str]) -> Path:
    configured = inputs.get("literature_score_template_path", "")
    return Path(configured).expanduser().resolve() if configured else DEFAULT_TEMPLATE_PATH.resolve()


def _round_score(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _round_confidence(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _round_weight(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_rubric(rubric: dict[str, Any]) -> None:
    if not isinstance(rubric.get("rubric_id"), str) or not str(rubric["rubric_id"]).strip():
        raise ValueError("scoring rubric requires a non-empty rubric_id")
    choices = rubric.get("paper_type_choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("scoring rubric requires paper_type_choices")
    paper_types: set[str] = set()
    for index, choice in enumerate(choices):
        if not isinstance(choice, dict) or set(choice) != {"paper_type", "description"}:
            raise ValueError(f"paper_type_choices[{index}] must contain paper_type and description")
        paper_type = choice.get("paper_type")
        description = choice.get("description")
        if not isinstance(paper_type, str) or not paper_type or paper_type in paper_types:
            raise ValueError(f"paper_type_choices[{index}].paper_type must be unique and non-empty")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"paper_type_choices[{index}].description must be non-empty")
        paper_types.add(paper_type)
    dimensions = rubric.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        raise ValueError("scoring rubric requires dimensions")
    dimension_keys: set[str] = set()
    criterion_keys: set[str] = set()
    total_weight = Decimal("0")
    for dimension_index, dimension in enumerate(dimensions):
        if not isinstance(dimension, dict):
            raise ValueError(f"dimensions[{dimension_index}] must be an object")
        required = {"dimension_key", "name", "weight", "prompt", "criteria"}
        if set(dimension) != required:
            raise ValueError(f"dimensions[{dimension_index}] must contain exactly {sorted(required)}")
        dimension_key = dimension.get("dimension_key")
        if not isinstance(dimension_key, str) or not dimension_key or dimension_key in dimension_keys:
            raise ValueError(f"dimensions[{dimension_index}].dimension_key must be unique and non-empty")
        dimension_keys.add(dimension_key)
        if not isinstance(dimension.get("name"), str) or not str(dimension["name"]).strip():
            raise ValueError(f"dimensions[{dimension_index}].name must be non-empty")
        if not isinstance(dimension.get("prompt"), str) or not str(dimension["prompt"]).strip():
            raise ValueError(f"dimensions[{dimension_index}].prompt must be non-empty")
        weight = dimension.get("weight")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <= 0:
            raise ValueError(f"dimensions[{dimension_index}].weight must be positive")
        total_weight += Decimal(str(weight))
        criteria = dimension.get("criteria")
        if not isinstance(criteria, list) or not criteria:
            raise ValueError(f"dimensions[{dimension_index}].criteria must be non-empty")
        for criterion_index, criterion in enumerate(criteria):
            required_criterion = {"criterion_key", "name", "max_score", "prompt"}
            if not isinstance(criterion, dict) or set(criterion) != required_criterion:
                raise ValueError(
                    f"dimensions[{dimension_index}].criteria[{criterion_index}] must contain exactly {sorted(required_criterion)}"
                )
            criterion_key = criterion.get("criterion_key")
            if not isinstance(criterion_key, str) or not criterion_key or criterion_key in criterion_keys:
                raise ValueError(
                    f"dimensions[{dimension_index}].criteria[{criterion_index}].criterion_key must be unique and non-empty"
                )
            criterion_keys.add(criterion_key)
            if not isinstance(criterion.get("name"), str) or not str(criterion["name"]).strip():
                raise ValueError(f"criterion {criterion_key}.name must be non-empty")
            if not isinstance(criterion.get("prompt"), str) or not str(criterion["prompt"]).strip():
                raise ValueError(f"criterion {criterion_key}.prompt must be non-empty")
            max_score = criterion.get("max_score")
            if isinstance(max_score, bool) or not isinstance(max_score, int) or max_score <= 0:
                raise ValueError(f"criterion {criterion_key}.max_score must be a positive integer")
    if total_weight != Decimal("1"):
        raise ValueError("scoring rubric dimension weights must sum to 1")


def _form_id(source_text: str, rubric: dict[str, Any]) -> str:
    source_hash = _sha256_text(source_text)
    rubric_hash = _sha256_text(_canonical_json(rubric))
    return f"sha256:{_sha256_text(f'{source_hash}:{rubric_hash}')}"


def _review_form(source_text: str, rubric: dict[str, Any]) -> dict[str, Any]:
    _validate_rubric(rubric)
    dimension_reviews: list[dict[str, Any]] = []
    criterion_reviews: list[dict[str, Any]] = []
    for dimension in rubric["dimensions"]:
        dimension_reviews.append(
            {
                "dimension_key": dimension["dimension_key"],
                "name": dimension["name"],
                "configured_weight": dimension["weight"],
                "prompt": dimension["prompt"],
                "confidence": None,
                "summary": "",
            }
        )
        for criterion in dimension["criteria"]:
            criterion_reviews.append(
                {
                    "criterion_key": criterion["criterion_key"],
                    "dimension_key": dimension["dimension_key"],
                    "name": criterion["name"],
                    "max_score": criterion["max_score"],
                    "prompt": criterion["prompt"],
                    "applicable": True,
                    "score": None,
                    "reason": "",
                    "evidence_quotes": [],
                }
            )
    return {
        "form_id": _form_id(source_text, rubric),
        "paper_type_choices": [
            {
                "paper_type": choice["paper_type"],
                "description": choice["description"],
                "selected": False,
            }
            for choice in rubric["paper_type_choices"]
        ],
        "paper_type_reason": "",
        "dimension_reviews": dimension_reviews,
        "criterion_reviews": criterion_reviews,
    }


def _review_paths(inputs: dict[str, str], db_path: Path, form_id: str) -> tuple[Path, Path]:
    tmp_dir = Path(inputs.get("tmp_dir", db_path.parent)).expanduser().resolve()
    agent_work_dir = (tmp_dir / "agent_work").resolve()
    digest = form_id.removeprefix("sha256:")
    return (
        (agent_work_dir / f"{REVIEW_FORM_PREFIX}.{digest}.json").resolve(),
        (agent_work_dir / f"{REVIEW_DRAFT_PREFIX}.{digest}.json").resolve(),
    )


def _submit_command(db_path: Path, draft_path: Path) -> str:
    return (
        'python scripts/run_analysis.py persist_literature_score '
        f'--db-path "{db_path}" --payload-file "{draft_path}"'
    )


def scoring_contract(connection: Any, db_path: Path) -> dict[str, Any]:
    inputs = runtime_db.fetch_runtime_inputs(connection)
    source_doc = runtime_db.fetch_source_document(connection, "normalized_source")
    if source_doc is None:
        return {
            "scoring_review_form_path": "",
            "scoring_review_draft_path": "",
            "editable_fields": EDITABLE_FIELDS,
            "submit_command": "",
        }
    rubric = _json_read(_rubric_path(inputs))
    form = _review_form(str(source_doc["content"]), rubric)
    form_path, draft_path = _review_paths(inputs, db_path, str(form["form_id"]))
    return {
        "scoring_review_form_path": str(form_path),
        "scoring_review_draft_path": str(draft_path),
        "editable_fields": EDITABLE_FIELDS,
        "submit_command": _submit_command(db_path, draft_path),
    }


def prepare_scoring_context(db_path: Path) -> tuple[dict[str, Any], int]:
    try:
        with runtime_db.connect_db(db_path) as connection:
            inputs = runtime_db.fetch_runtime_inputs(connection)
            source_doc = runtime_db.fetch_source_document(connection, "normalized_source")
            if source_doc is None:
                return {
                    "next_action": "persist_literature_score",
                    "error": {"code": "score_prerequisite_missing", "message": "normalized source is missing"},
                }, 2
            if not runtime_db.is_score_only(connection):
                receipts = runtime_db.fetch_action_receipts(connection)
                if "persist_digest" not in receipts:
                    return {
                        "next_action": "persist_literature_score",
                        "error": {"code": "score_prerequisite_missing", "message": "persist_digest must complete before scoring in full mode"},
                    }, 2
            rubric = _json_read(_rubric_path(inputs))
            form = _review_form(str(source_doc["content"]), rubric)
            form_path, draft_path = _review_paths(inputs, db_path, str(form["form_id"]))
        form_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(form, ensure_ascii=False, indent=2) + "\n"
        if form_path.exists():
            if _json_read(form_path) != form:
                raise ValueError(f"existing scoring review form does not match runtime form: {form_path}")
        else:
            form_path.write_text(serialized, encoding="utf-8")
            form_path.chmod(0o444)
        if not draft_path.exists():
            draft_path.write_text(serialized, encoding="utf-8")
        return {
            "db_path": str(db_path),
            "scoring_review_form_path": str(form_path),
            "scoring_review_draft_path": str(draft_path),
            "editable_fields": EDITABLE_FIELDS,
            "submit_command": _submit_command(db_path, draft_path),
            "next_action": "persist_literature_score",
            "error": None,
        }, 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "next_action": "persist_literature_score",
            "error": {"code": "scoring_context_failed", "message": str(exc)},
        }, 2


def _review_error(reason: str, field: str, message: str, **details: Any) -> dict[str, Any]:
    return {"reason": reason, "field": field, "message": message, **details}


def _normalize_match_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    without_punctuation = "".join(" " if unicodedata.category(char).startswith("P") else char for char in normalized)
    return re.sub(r"\s+", " ", without_punctuation).strip()


def _ngrams(value: str, size: int) -> Counter[str]:
    return Counter(value[index : index + size] for index in range(len(value) - size + 1))


def _ngram_similarity(left: str, right: str, size: int) -> float:
    left_grams = _ngrams(left, size)
    right_grams = _ngrams(right, size)
    denominator = sum(left_grams.values()) + sum(right_grams.values())
    if denominator == 0:
        return 0.0
    overlap = sum((left_grams & right_grams).values())
    return (2.0 * overlap) / denominator


def _source_windows(source_lines: list[str]) -> list[tuple[int, int, str]]:
    windows: list[tuple[int, int, str]] = []
    for start in range(len(source_lines)):
        for width in range(1, min(5, len(source_lines) - start) + 1):
            normalized = _normalize_match_text("\n".join(source_lines[start : start + width]))
            if normalized:
                windows.append((start + 1, start + width, normalized))
    return windows


def _locate_evidence_quote(quote: str, source_lines: list[str]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    normalized_quote = _normalize_match_text(quote)
    windows = _source_windows(source_lines)
    exact_matches = [
        (line_start, line_end)
        for line_start, line_end, normalized_window in windows
        if normalized_quote and normalized_quote in normalized_window
    ]
    if exact_matches:
        line_start, line_end = min(exact_matches, key=lambda item: (item[1] - item[0], item[0], item[1]))
        return {"line_start": line_start, "line_end": line_end, "quote": quote.strip()}, {
            "best_similarity": 1.0,
            "candidate_line_start": line_start,
            "candidate_line_end": line_end,
        }
    if len(normalized_quote) < 8 or not windows:
        return None, {"best_similarity": 0.0, "candidate_line_start": None, "candidate_line_end": None}
    ngram_size = 2 if len(normalized_quote) <= 11 else 3
    best_similarity = -1.0
    best_range: tuple[int, int] | None = None
    for line_start, line_end, normalized_window in windows:
        similarity = _ngram_similarity(normalized_quote, normalized_window, ngram_size)
        if similarity > best_similarity:
            best_similarity = similarity
            best_range = (line_start, line_end)
    assert best_range is not None
    match_details = {
        "best_similarity": round(best_similarity, 4),
        "candidate_line_start": best_range[0],
        "candidate_line_end": best_range[1],
    }
    if best_similarity >= 0.45:
        return {"line_start": best_range[0], "line_end": best_range[1], "quote": quote.strip()}, match_details
    return None, match_details


def _validate_derived_evidence(
    evidence: object,
    *,
    source_lines: list[str],
    context: str,
    errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(evidence, list):
        errors.append({"field": f"{context}.evidence", "message": "must be an array"})
        return []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(evidence):
        item_context = f"{context}.evidence[{index}]"
        if not isinstance(item, dict) or set(item) != {"line_start", "line_end", "quote"}:
            errors.append({"field": item_context, "message": "invalid runtime-derived evidence"})
            continue
        line_start = item.get("line_start")
        line_end = item.get("line_end")
        quote = item.get("quote")
        if (
            isinstance(line_start, bool)
            or not isinstance(line_start, int)
            or isinstance(line_end, bool)
            or not isinstance(line_end, int)
            or line_start < 1
            or line_end < line_start
            or line_end > len(source_lines)
            or not isinstance(quote, str)
            or not quote.strip()
        ):
            errors.append({"field": item_context, "message": "invalid runtime-derived evidence"})
            continue
        normalized.append({"line_start": line_start, "line_end": line_end, "quote": quote.strip()})
    return normalized


def _validate_object_fields(
    value: object,
    *,
    expected_fields: set[str],
    field: str,
    errors: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(_review_error("incomplete_answer", field, "must be an object"))
        return None
    missing = sorted(expected_fields.difference(value))
    extra = sorted(set(value).difference(expected_fields))
    for name in missing:
        errors.append(_review_error("incomplete_answer", f"{field}.{name}", "required field is missing"))
    if extra:
        errors.append(
            _review_error(
                "locked_field_changed",
                field,
                "review form contains fields not present in the generated form",
                unexpected_fields=extra,
            )
        )
    return value


def _validate_locked_fields(
    submitted: dict[str, Any],
    original: dict[str, Any],
    *,
    locked_fields: tuple[str, ...],
    field: str,
    errors: list[dict[str, Any]],
) -> None:
    for name in locked_fields:
        if name in submitted and submitted.get(name) != original.get(name):
            errors.append(
                _review_error(
                    "locked_field_changed",
                    f"{field}.{name}",
                    "runtime-owned field differs from the generated form",
                )
            )


def _review_to_score_payload(
    payload: dict[str, Any],
    *,
    original: dict[str, Any],
    source_text: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    top_fields = {"form_id", "paper_type_choices", "paper_type_reason", "dimension_reviews", "criterion_reviews"}
    submitted = _validate_object_fields(payload, expected_fields=top_fields, field="payload", errors=errors)
    if submitted is None:
        return None, errors

    choices_value = submitted.get("paper_type_choices")
    original_choices = original["paper_type_choices"]
    selected_types: list[str] = []
    if not isinstance(choices_value, list):
        errors.append(_review_error("incomplete_answer", "paper_type_choices", "must be an array"))
    elif len(choices_value) != len(original_choices):
        errors.append(
            _review_error(
                "incomplete_answer",
                "paper_type_choices",
                "must preserve every generated paper-type choice",
                expected_count=len(original_choices),
                actual_count=len(choices_value),
            )
        )
    else:
        for index, original_choice in enumerate(original_choices):
            field = f"paper_type_choices[{index}]"
            choice = _validate_object_fields(
                choices_value[index],
                expected_fields={"paper_type", "description", "selected"},
                field=field,
                errors=errors,
            )
            if choice is None:
                continue
            _validate_locked_fields(
                choice,
                original_choice,
                locked_fields=("paper_type", "description"),
                field=field,
                errors=errors,
            )
            selected = choice.get("selected")
            if not isinstance(selected, bool):
                errors.append(_review_error("invalid_selection", f"{field}.selected", "must be a boolean"))
            elif selected:
                selected_types.append(str(original_choice["paper_type"]))
    if len(selected_types) != 1:
        errors.append(
            _review_error(
                "invalid_selection",
                "paper_type_choices",
                "exactly one paper type must be selected",
                selected_count=len(selected_types),
            )
        )

    paper_type_reason = submitted.get("paper_type_reason")
    if not isinstance(paper_type_reason, str) or not paper_type_reason.strip():
        errors.append(_review_error("incomplete_answer", "paper_type_reason", "must be a non-empty string"))

    original_criteria = original["criterion_reviews"]
    criteria_value = submitted.get("criterion_reviews")
    converted_by_dimension: dict[str, list[dict[str, Any]]] = {
        str(item["dimension_key"]): [] for item in original["dimension_reviews"]
    }
    applicable_by_dimension = {key: False for key in converted_by_dimension}
    source_lines = source_text.splitlines()
    if not isinstance(criteria_value, list):
        errors.append(_review_error("incomplete_answer", "criterion_reviews", "must be an array"))
    elif len(criteria_value) != len(original_criteria):
        errors.append(
            _review_error(
                "incomplete_answer",
                "criterion_reviews",
                "must preserve every generated criterion",
                expected_count=len(original_criteria),
                actual_count=len(criteria_value),
            )
        )
    else:
        for index, original_criterion in enumerate(original_criteria):
            field = f"criterion_reviews[{index}]"
            criterion = _validate_object_fields(
                criteria_value[index],
                expected_fields={
                    "criterion_key",
                    "dimension_key",
                    "name",
                    "max_score",
                    "prompt",
                    "applicable",
                    "score",
                    "reason",
                    "evidence_quotes",
                },
                field=field,
                errors=errors,
            )
            if criterion is None:
                continue
            _validate_locked_fields(
                criterion,
                original_criterion,
                locked_fields=("criterion_key", "dimension_key", "name", "max_score", "prompt"),
                field=field,
                errors=errors,
            )
            criterion_key = str(original_criterion["criterion_key"])
            dimension_key = str(original_criterion["dimension_key"])
            applicable = criterion.get("applicable")
            if not isinstance(applicable, bool):
                errors.append(_review_error("incomplete_answer", f"{field}.applicable", "must be a boolean"))
                applicable = False
            score = criterion.get("score")
            max_score = int(original_criterion["max_score"])
            if applicable:
                applicable_by_dimension[dimension_key] = True
                if isinstance(score, bool) or not isinstance(score, int) or score < 0 or score > max_score:
                    errors.append(
                        _review_error(
                            "incomplete_answer",
                            f"{field}.score",
                            f"must be an integer between 0 and {max_score} when applicable is true",
                        )
                    )
            elif score is not None:
                errors.append(
                    _review_error(
                        "incomplete_answer",
                        f"{field}.score",
                        "must be null when applicable is false",
                    )
                )
            reason = criterion.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                errors.append(_review_error("incomplete_answer", f"{field}.reason", "must be a non-empty string"))
            evidence_quotes = criterion.get("evidence_quotes")
            located_evidence: list[dict[str, Any]] = []
            if not isinstance(evidence_quotes, list):
                errors.append(_review_error("incomplete_answer", f"{field}.evidence_quotes", "must be an array"))
            else:
                for evidence_index, quote in enumerate(evidence_quotes):
                    quote_field = f"{field}.evidence_quotes[{evidence_index}]"
                    if not isinstance(quote, str) or not quote.strip() or len(quote) > 500:
                        errors.append(
                            _review_error(
                                "incomplete_answer",
                                quote_field,
                                "must be a non-empty string of at most 500 characters",
                            )
                        )
                        continue
                    located, match_details = _locate_evidence_quote(quote, source_lines)
                    if located is None:
                        errors.append(
                            _review_error(
                                "evidence_not_found",
                                quote_field,
                                "evidence quote could not be located in the normalized source",
                                criterion_key=criterion_key,
                                evidence_index=evidence_index,
                                **match_details,
                            )
                        )
                    else:
                        located_evidence.append(located)
            converted_by_dimension[dimension_key].append(
                {
                    "criterion_key": criterion_key,
                    "status": "scored" if applicable else "not_applicable",
                    "score": score if applicable and isinstance(score, int) and not isinstance(score, bool) else None,
                    "reason": reason.strip() if isinstance(reason, str) else "",
                    "evidence": located_evidence,
                }
            )

    original_dimensions = original["dimension_reviews"]
    dimensions_value = submitted.get("dimension_reviews")
    converted_dimensions: list[dict[str, Any]] = []
    if not isinstance(dimensions_value, list):
        errors.append(_review_error("incomplete_answer", "dimension_reviews", "must be an array"))
    elif len(dimensions_value) != len(original_dimensions):
        errors.append(
            _review_error(
                "incomplete_answer",
                "dimension_reviews",
                "must preserve every generated dimension",
                expected_count=len(original_dimensions),
                actual_count=len(dimensions_value),
            )
        )
    else:
        for index, original_dimension in enumerate(original_dimensions):
            field = f"dimension_reviews[{index}]"
            dimension = _validate_object_fields(
                dimensions_value[index],
                expected_fields={"dimension_key", "name", "configured_weight", "prompt", "confidence", "summary"},
                field=field,
                errors=errors,
            )
            if dimension is None:
                continue
            _validate_locked_fields(
                dimension,
                original_dimension,
                locked_fields=("dimension_key", "name", "configured_weight", "prompt"),
                field=field,
                errors=errors,
            )
            dimension_key = str(original_dimension["dimension_key"])
            summary = dimension.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                errors.append(_review_error("incomplete_answer", f"{field}.summary", "must be a non-empty string"))
            confidence = dimension.get("confidence")
            if applicable_by_dimension[dimension_key]:
                if (
                    isinstance(confidence, bool)
                    or not isinstance(confidence, (int, float))
                    or confidence < 0
                    or confidence > 1
                ):
                    errors.append(
                        _review_error(
                            "incomplete_answer",
                            f"{field}.confidence",
                            "must be a number from 0 to 1 for an active dimension",
                        )
                    )
            elif confidence is not None:
                errors.append(
                    _review_error(
                        "incomplete_answer",
                        f"{field}.confidence",
                        "must be null when every dimension criterion is inapplicable",
                    )
                )
            converted_dimensions.append(
                {
                    "dimension_key": dimension_key,
                    "confidence": confidence,
                    "summary": summary.strip() if isinstance(summary, str) else "",
                    "criteria": converted_by_dimension[dimension_key],
                }
            )

    if errors:
        return None, errors
    return {
        "paper_type": selected_types[0],
        "paper_type_reason": paper_type_reason.strip(),
        "dimension_reviews": converted_dimensions,
    }, []


def _normalize_score_payload(
    payload: dict[str, Any],
    *,
    rubric: dict[str, Any],
    source_text: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[str]]:
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    allowed_top_level = {"paper_type", "paper_type_reason", "dimension_reviews"}
    unknown_top = sorted(set(payload).difference(allowed_top_level))
    if unknown_top:
        errors.append({"field": "payload", "message": f"unknown fields: {unknown_top}"})

    paper_type = payload.get("paper_type")
    paper_types = [str(item["paper_type"]) for item in rubric.get("paper_type_choices", [])]
    if paper_type not in paper_types:
        errors.append({"field": "paper_type", "message": f"must be one of {paper_types}"})
    paper_type_reason = payload.get("paper_type_reason")
    if not isinstance(paper_type_reason, str) or not paper_type_reason.strip():
        errors.append({"field": "paper_type_reason", "message": "must be a non-empty string"})

    reviews = payload.get("dimension_reviews")
    if not isinstance(reviews, list):
        errors.append({"field": "dimension_reviews", "message": "must be an array"})
        return None, errors, warnings
    by_key: dict[str, dict[str, Any]] = {}
    for index, review in enumerate(reviews):
        if not isinstance(review, dict):
            errors.append({"field": f"dimension_reviews[{index}]", "message": "must be an object"})
            continue
        unknown_review_fields = sorted(set(review).difference({"dimension_key", "confidence", "summary", "criteria"}))
        if unknown_review_fields:
            errors.append({"field": f"dimension_reviews[{index}]", "message": f"unknown fields: {unknown_review_fields}"})
        key = review.get("dimension_key")
        if not isinstance(key, str) or not key:
            errors.append({"field": f"dimension_reviews[{index}].dimension_key", "message": "must be a non-empty string"})
            continue
        if key in by_key:
            errors.append({"field": f"dimension_reviews[{index}].dimension_key", "message": f"duplicate dimension key: {key}"})
            continue
        by_key[key] = review

    expected_dimension_keys = [str(item["dimension_key"]) for item in rubric.get("dimensions", [])]
    unknown_dimensions = sorted(set(by_key).difference(expected_dimension_keys))
    missing_dimensions = [key for key in expected_dimension_keys if key not in by_key]
    if unknown_dimensions:
        errors.append({"field": "dimension_reviews", "message": f"unknown dimension keys: {unknown_dimensions}"})
    if missing_dimensions:
        errors.append({"field": "dimension_reviews", "message": f"missing dimension keys: {missing_dimensions}"})

    source_lines = source_text.splitlines()
    normalized_dimensions: list[dict[str, Any]] = []
    for dimension_spec in rubric.get("dimensions", []):
        dimension_key = str(dimension_spec["dimension_key"])
        review = by_key.get(dimension_key)
        if review is None:
            continue
        summary = review.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            errors.append({"field": f"dimension_reviews.{dimension_key}.summary", "message": "must be a non-empty string"})
        criteria = review.get("criteria")
        if not isinstance(criteria, list):
            errors.append({"field": f"dimension_reviews.{dimension_key}.criteria", "message": "must be an array"})
            continue
        criteria_by_key: dict[str, dict[str, Any]] = {}
        for criterion_index, criterion in enumerate(criteria):
            if not isinstance(criterion, dict):
                errors.append({"field": f"dimension_reviews.{dimension_key}.criteria[{criterion_index}]", "message": "must be an object"})
                continue
            unknown_criterion_fields = sorted(set(criterion).difference({"criterion_key", "status", "score", "reason", "evidence"}))
            if unknown_criterion_fields:
                errors.append(
                    {
                        "field": f"dimension_reviews.{dimension_key}.criteria[{criterion_index}]",
                        "message": f"unknown fields: {unknown_criterion_fields}",
                    }
                )
            criterion_key = criterion.get("criterion_key")
            if not isinstance(criterion_key, str) or not criterion_key:
                errors.append({"field": f"dimension_reviews.{dimension_key}.criteria[{criterion_index}].criterion_key", "message": "must be a non-empty string"})
                continue
            if criterion_key in criteria_by_key:
                errors.append({"field": f"dimension_reviews.{dimension_key}.criteria", "message": f"duplicate criterion key: {criterion_key}"})
                continue
            criteria_by_key[criterion_key] = criterion

        expected_criteria = [str(item["criterion_key"]) for item in dimension_spec.get("criteria", [])]
        unknown_criteria = sorted(set(criteria_by_key).difference(expected_criteria))
        missing_criteria = [key for key in expected_criteria if key not in criteria_by_key]
        if unknown_criteria:
            errors.append({"field": f"dimension_reviews.{dimension_key}.criteria", "message": f"unknown criterion keys: {unknown_criteria}"})
        if missing_criteria:
            errors.append({"field": f"dimension_reviews.{dimension_key}.criteria", "message": f"missing criterion keys: {missing_criteria}"})

        raw_score = 0
        applicable_max_score = 0
        normalized_criteria: list[dict[str, Any]] = []
        for criterion_spec in dimension_spec.get("criteria", []):
            criterion_key = str(criterion_spec["criterion_key"])
            criterion = criteria_by_key.get(criterion_key)
            if criterion is None:
                continue
            status = criterion.get("status")
            if status not in {"scored", "not_applicable"}:
                errors.append(
                    {
                        "field": f"dimension_reviews.{dimension_key}.criteria.{criterion_key}.status",
                        "message": "must be scored or not_applicable",
                    }
                )
            reason = criterion.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                errors.append({"field": f"dimension_reviews.{dimension_key}.criteria.{criterion_key}.reason", "message": "must be a non-empty string"})
            evidence = _validate_derived_evidence(
                criterion.get("evidence", []),
                source_lines=source_lines,
                context=f"dimension_reviews.{dimension_key}.criteria.{criterion_key}",
                errors=errors,
            )
            max_score = int(criterion_spec["max_score"])
            submitted_score = criterion.get("score")
            normalized_score: int | None = None
            if status == "scored":
                if isinstance(submitted_score, bool) or not isinstance(submitted_score, int):
                    errors.append({"field": f"dimension_reviews.{dimension_key}.criteria.{criterion_key}.score", "message": "must be an integer for scored criteria"})
                elif submitted_score < 0 or submitted_score > max_score:
                    errors.append({"field": f"dimension_reviews.{dimension_key}.criteria.{criterion_key}.score", "message": f"must be between 0 and {max_score}"})
                else:
                    normalized_score = submitted_score
                    raw_score += submitted_score
                    applicable_max_score += max_score
            elif status == "not_applicable" and submitted_score is not None:
                errors.append({"field": f"dimension_reviews.{dimension_key}.criteria.{criterion_key}.score", "message": "must be null or omitted for not_applicable criteria"})
            normalized_criteria.append(
                {
                    "criterion_key": criterion_key,
                    "name": str(criterion_spec["name"]),
                    "status": status,
                    "score": normalized_score,
                    "max_score": max_score,
                    "reason": reason.strip() if isinstance(reason, str) else "",
                    "evidence": evidence,
                }
            )

        submitted_confidence = review.get("confidence")
        confidence: Decimal | None = None
        if applicable_max_score > 0:
            if isinstance(submitted_confidence, bool) or not isinstance(submitted_confidence, (int, float)):
                errors.append({"field": f"dimension_reviews.{dimension_key}.confidence", "message": "must be a number from 0 to 1 for an active dimension"})
            else:
                confidence = Decimal(str(submitted_confidence))
                if confidence < 0 or confidence > 1:
                    errors.append({"field": f"dimension_reviews.{dimension_key}.confidence", "message": "must be between 0 and 1"})
        elif submitted_confidence is not None:
            errors.append({"field": f"dimension_reviews.{dimension_key}.confidence", "message": "must be null or omitted when the entire dimension is not_applicable"})

        normalized_dimensions.append(
            {
                "dimension_key": dimension_key,
                "name": str(dimension_spec["name"]),
                "configured_weight_decimal": Decimal(str(dimension_spec["weight"])),
                "raw_score": raw_score,
                "applicable_max_score": applicable_max_score,
                "confidence_decimal": confidence,
                "summary": summary.strip() if isinstance(summary, str) else "",
                "criteria": normalized_criteria,
            }
        )

    if errors:
        return None, errors, warnings

    active_dimensions = [item for item in normalized_dimensions if item["applicable_max_score"] > 0]
    if not active_dimensions:
        return None, [{"field": "dimension_reviews", "message": "at least one dimension must contain a scored criterion"}], warnings
    active_weight_total = sum((item["configured_weight_decimal"] for item in active_dimensions), Decimal("0"))
    output_dimensions: list[dict[str, Any]] = []
    overall_precise = Decimal("0")
    confidence_precise = Decimal("0")
    for item in normalized_dimensions:
        configured_weight = item["configured_weight_decimal"]
        if item["applicable_max_score"] == 0:
            effective_weight = Decimal("0")
            dimension_score_precise: Decimal | None = None
            confidence_decimal: Decimal | None = None
            warnings.append(f"literature_score_dimension_not_applicable: {item['dimension_key']}")
        else:
            effective_weight = configured_weight / active_weight_total
            dimension_score_precise = Decimal(item["raw_score"]) / Decimal(item["applicable_max_score"]) * Decimal("100")
            confidence_decimal = item["confidence_decimal"]
            assert confidence_decimal is not None
            overall_precise += dimension_score_precise * effective_weight
            confidence_precise += confidence_decimal * effective_weight
        output_dimensions.append(
            {
                "dimension_key": item["dimension_key"],
                "name": item["name"],
                "configured_weight": _round_weight(configured_weight),
                "effective_weight": _round_weight(effective_weight),
                "raw_score": item["raw_score"],
                "applicable_max_score": item["applicable_max_score"],
                "score": _round_score(dimension_score_precise) if dimension_score_precise is not None else None,
                "confidence": _round_confidence(confidence_decimal) if confidence_decimal is not None else None,
                "summary": item["summary"],
                "criteria": item["criteria"],
            }
        )

    overall_score = _round_score(overall_precise)
    overall_confidence = _round_confidence(confidence_precise)
    adjusted_score = _round_score(Decimal(str(overall_score)) * Decimal(str(overall_confidence)))
    result = {
        "schema": "literature_score.v1",
        "rubric_id": str(rubric["rubric_id"]),
        "paper_type": paper_type,
        "paper_type_reason": paper_type_reason.strip(),
        "overall_score": overall_score,
        "confidence": overall_confidence,
        "confidence_adjusted_score": adjusted_score,
        "dimensions": output_dimensions,
    }
    return result, [], warnings


def _render_score_with_connection(connection: Any) -> Path:
    inputs = runtime_db.fetch_runtime_inputs(connection)
    score = runtime_db.fetch_literature_score(connection)
    if score is None:
        raise ValueError("literature score state is missing")
    context = {"literature_score": score}
    schema = _json_read(RENDER_SCHEMA_PATH)
    validate(instance=context, schema=schema)
    template_path = _template_path(inputs)
    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        autoescape=False,
        trim_blocks=False,
        lstrip_blocks=False,
        undefined=StrictUndefined,
    )
    env.filters["to_pretty_json"] = lambda value: json.dumps(value, ensure_ascii=False, indent=2)
    rendered = env.get_template(template_path.name).render(**context)
    rendered_value = json.loads(rendered)
    validate(instance={"literature_score": rendered_value}, schema=schema)
    output_dir = Path(inputs.get("output_dir", ".")).expanduser().resolve()
    output_path = (output_dir / SCORE_FILENAME).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered.rstrip("\n") + "\n", encoding="utf-8")
    runtime_db.register_artifact(
        connection,
        artifact_key="literature_score_path",
        path=output_path,
        is_required=True,
        media_type="application/json",
        source_table="literature_score",
    )
    return output_path


def render_score_artifact(db_path: Path) -> tuple[dict[str, Any], int]:
    try:
        with runtime_db.connect_db(db_path) as connection:
            output_path = _render_score_with_connection(connection)
            connection.commit()
        return {"literature_score_path": str(output_path), "error": None}, 0
    except Exception as exc:  # noqa: BLE001
        return {"literature_score_path": "", "error": {"code": "score_render_failed", "message": str(exc)}}, 2


def render_score_only_outputs(db_path: Path) -> tuple[dict[str, Any], int]:
    try:
        with runtime_db.connect_db(db_path) as connection:
            if not runtime_db.is_score_only(connection):
                raise ValueError("score-only renderer requires score_only=true")
            source_doc = runtime_db.fetch_source_document(connection, "normalized_source")
            receipts = runtime_db.fetch_action_receipts(connection)
            if source_doc is None:
                raise ValueError("normalized source is missing")
            for receipt in ("persist_render_templates", "persist_literature_score"):
                if receipt not in receipts:
                    raise ValueError(f"required receipt missing: {receipt}")
            _render_score_with_connection(connection)
            runtime_db.resolve_runtime_errors(connection)
            runtime_db.store_action_receipt(connection, action_name="render_score_only", stage="stage_7_render_and_validate")
            runtime_db.set_workflow_state(
                connection,
                current_stage="stage_8_completed",
                current_substep="completed",
                stage_gate="ready",
                next_action="completed",
                status_summary="score-only artifact rendered and validated",
            )
            public_payload = runtime_db.build_public_output_payload(connection)
            payload = {
                "digest_path": "",
                "references_path": "",
                "citation_analysis_path": "",
                "literature_matching_metadata_path": "",
                "literature_score_path": public_payload["literature_score_path"],
                "provenance": public_payload["provenance"],
                "warnings": public_payload["warnings"],
                "error": public_payload["error"],
            }
            result_json_path = Path(runtime_db.fetch_runtime_inputs(connection)["result_json_path"]).expanduser().resolve()
            connection.commit()
        result_json_path.parent.mkdir(parents=True, exist_ok=True)
        result_json_path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
        return payload, 0
    except Exception as exc:  # noqa: BLE001
        with runtime_db.connect_db(db_path) as connection:
            inputs = runtime_db.fetch_runtime_inputs(connection)
        payload = {
            "digest_path": "",
            "references_path": "",
            "citation_analysis_path": "",
            "literature_matching_metadata_path": "",
            "literature_score_path": "",
            "provenance": {"generated_at": "", "input_hash": "", "model": ""},
            "warnings": [],
            "error": {"code": "score_render_failed", "message": str(exc)},
        }
        result_json_value = inputs.get("result_json_path", "")
        if result_json_value:
            result_json_path = Path(result_json_value).expanduser().resolve()
            result_json_path.parent.mkdir(parents=True, exist_ok=True)
            result_json_path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
        return payload, 2


def persist_literature_score(db_path: Path, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    with runtime_db.connect_db(db_path) as connection:
        inputs = runtime_db.fetch_runtime_inputs(connection)
        source_doc = runtime_db.fetch_source_document(connection, "normalized_source")
        if source_doc is None:
            return {
                "next_action": "persist_literature_score",
                "error": {"code": "score_prerequisite_missing", "message": "normalized source is missing"},
            }, 2
        if not runtime_db.is_score_only(connection):
            receipts = runtime_db.fetch_action_receipts(connection)
            if "persist_digest" not in receipts:
                return {
                    "next_action": "persist_literature_score",
                    "error": {"code": "score_prerequisite_missing", "message": "persist_digest must complete before scoring in full mode"},
                }, 2
        try:
            rubric = _json_read(_rubric_path(inputs))
            expected_form = _review_form(str(source_doc["content"]), rubric)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {
                "next_action": "persist_literature_score",
                "error": {"code": "scoring_rubric_invalid", "message": str(exc)},
            }, 2
        form_path, _ = _review_paths(inputs, db_path, str(expected_form["form_id"]))
        review_errors: list[dict[str, Any]] = []
        converted_payload: dict[str, Any] | None = None
        if payload.get("form_id") != expected_form["form_id"]:
            review_errors.append(
                _review_error(
                    "stale_form",
                    "form_id",
                    "review form does not match the current normalized source and rubric snapshot",
                    expected_form_id=expected_form["form_id"],
                    submitted_form_id=payload.get("form_id"),
                )
            )
        elif not form_path.exists():
            review_errors.append(
                _review_error(
                    "stale_form",
                    "form_id",
                    "prepared scoring review form is missing; run prepare again",
                    expected_form_id=expected_form["form_id"],
                )
            )
        else:
            try:
                original_form = _json_read(form_path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                review_errors.append(
                    _review_error(
                        "stale_form",
                        "form_id",
                        "prepared scoring review form is unreadable",
                        detail=str(exc),
                    )
                )
            else:
                if original_form != expected_form:
                    review_errors.append(
                        _review_error(
                            "locked_field_changed",
                            "scoring_review_form_path",
                            "immutable scoring review form differs from the runtime-generated form",
                        )
                    )
                else:
                    converted_payload, conversion_errors = _review_to_score_payload(
                        payload,
                        original=original_form,
                        source_text=str(source_doc["content"]),
                    )
                    review_errors.extend(conversion_errors)
        if review_errors:
            runtime_db.set_runtime_error(connection, "score_review_invalid", "scoring review form failed validation", "stage_4_scoring")
            connection.commit()
            return {
                "next_action": "persist_literature_score",
                "error": {
                    "code": "score_review_invalid",
                    "message": "scoring review form failed validation",
                    "details": review_errors,
                },
            }, 2
        assert converted_payload is not None
        score, errors, warnings = _normalize_score_payload(
            converted_payload,
            rubric=rubric,
            source_text=str(source_doc["content"]),
        )
        if errors or score is None:
            runtime_db.set_runtime_error(connection, "score_review_invalid", "scoring review form failed normalization", "stage_4_scoring")
            connection.commit()
            return {
                "next_action": "persist_literature_score",
                "error": {
                    "code": "score_review_invalid",
                    "message": "scoring review form failed normalization",
                    "details": errors,
                },
            }, 2
        runtime_db.store_literature_score(connection, score)
        runtime_db.resolve_runtime_errors(connection, stage="stage_4_scoring")
        runtime_db.resolve_runtime_warnings(connection, warning_prefix="literature_score_dimension_not_applicable:")
        for warning in warnings:
            runtime_db.add_runtime_warning_once(connection, warning)
        runtime_db.delete_action_receipts(connection, ["render_and_validate", "render_score_only"])
        try:
            output_path = _render_score_with_connection(connection)
        except Exception as exc:  # noqa: BLE001
            runtime_db.set_runtime_error(connection, "score_render_failed", str(exc), "stage_4_scoring")
            connection.commit()
            return {
                "literature_score_path": "",
                "next_action": "persist_literature_score",
                "error": {"code": "score_render_failed", "message": str(exc)},
            }, 2
        runtime_db.store_action_receipt(
            connection,
            action_name="persist_literature_score",
            stage="stage_4_scoring",
            metadata={"rubric_id": score["rubric_id"], "paper_type": score["paper_type"]},
        )
        score_only = runtime_db.is_score_only(connection)
        if not score_only:
            runtime_db.set_workflow_state(
                connection,
                current_stage="stage_5_references",
                current_substep="prepare_references_workset",
                stage_gate="ready",
                next_action="prepare_references_workset",
                status_summary="literature score persisted",
            )
        connection.commit()

    if score_only:
        return render_score_only_outputs(db_path)
    return {
        "db_path": str(db_path),
        "literature_score_path": str(output_path),
        "overall_score": score["overall_score"],
        "confidence": score["confidence"],
        "confidence_adjusted_score": score["confidence_adjusted_score"],
        "next_action": "prepare_references_workset",
        "error": None,
    }, 0


def validate_public_score(path: Path) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        validate(instance={"literature_score": payload}, schema=_json_read(RENDER_SCHEMA_PATH))
    except Exception as exc:  # noqa: BLE001
        return [f"literature_score_path unreadable or invalid: {exc}"]
    return []


def render_with_connection(connection: Any) -> Path:
    return _render_score_with_connection(connection)

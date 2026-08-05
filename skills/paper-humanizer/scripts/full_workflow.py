#!/usr/bin/env python3
"""Gate-driven state and view runtime for Paper Humanizer full mode."""

from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Sequence

import document_pipeline as documents


SCHEMA_VERSION = "paper-humanizer.full-workflow/v1"
STATE_NAME = "state.yaml"
VIEW_NAMES = {
    "review": "review-report.md",
    "plan": "revision-plan.md",
    "verification": "verification-report.md",
    "resume": "resume.md",
}
STAGES = {"review", "plan", "execute", "verify", "acceptance", "done", "cancelled", "blocked"}
ACTIONS = {
    "record_review",
    "revise_plan",
    "approve_plan",
    "record_execution",
    "record_verification",
    "accept",
    "reject",
    "cancel",
}
PLAN_DISPOSITIONS = {"include", "exclude", "pending"}
PLAN_RECOMMENDATIONS = {"include", "optional", "defer"}
LEVELS = {"high", "medium", "low"}
EXECUTION_STATUSES = {"applied", "partly_applied", "unchanged_for_safety"}
VERIFICATION_STATUSES = {"pass", "pass_with_residuals", "failed"}
CHECK_STATUSES = {"pass", "failed"}
FINDING_RESULTS = {"resolved", "partly_resolved", "unchanged_for_safety", "not_in_scope"}
ID_PATTERNS = {
    "finding": re.compile(r"^PH-\d{3,}$"),
    "plan": re.compile(r"^RP-\d{3,}$"),
    "unresolved": re.compile(r"^UR-\d{3,}$"),
}


class WorkflowError(documents.PipelineError):
    """Expected workflow failure with a stable error code."""


def fail(code: str, message: str) -> None:
    raise WorkflowError(code, message)


def require_exact_keys(value: Any, keys: set[str], context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail("invalid_payload", f"{context} must be an object")
    actual = set(value)
    if actual != keys:
        fail(
            "invalid_payload",
            f"{context} keys differ from contract; missing={sorted(keys - actual)}, extra={sorted(actual - keys)}",
        )
    return value


def require_string(value: Any, context: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        fail("invalid_payload", f"{context} must be a{' nonempty' if not allow_empty else ''} string")
    return value


def require_bool(value: Any, context: str) -> bool:
    if not isinstance(value, bool):
        fail("invalid_payload", f"{context} must be boolean")
    return value


def require_int(value: Any, context: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        fail("invalid_payload", f"{context} must be an integer >= {minimum}")
    return value


def require_string_list(value: Any, context: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        fail("invalid_payload", f"{context} must be an array of strings")
    if nonempty and not value:
        fail("invalid_payload", f"{context} must not be empty")
    return value


def require_enum(value: Any, allowed: set[str], context: str) -> str:
    if value not in allowed:
        fail("invalid_payload", f"{context} must be one of {sorted(allowed)}, got {value!r}")
    return value


def require_id(value: Any, kind: str, context: str) -> str:
    identifier = require_string(value, context)
    if not ID_PATTERNS[kind].fullmatch(identifier):
        fail("invalid_payload", f"{context} must use the {kind} ID format")
    return identifier


def require_unique(values: Sequence[str], context: str) -> None:
    if len(values) != len(set(values)):
        fail("invalid_payload", f"{context} contains duplicate values")


def load_json_object(path: Path, context: str) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        fail("input_read_failed", f"cannot read {context}: {path}: {exc}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail("invalid_payload_json", f"{context} must be JSON-compatible YAML: {exc}")
    if not isinstance(payload, dict):
        fail("invalid_payload", f"{context} root must be an object")
    return payload


def document_reference(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    document = documents.load_artifact(resolved)
    documents.validate_document(document, require_fresh=True)
    return {
        "path": str(resolved),
        "artifact_sha256": documents.sha256_bytes(resolved.read_bytes()),
        "content_sha256": document["analysis"]["content_sha256"],
        "source_sha256": document["source"]["sha256"],
        "manifest_sha256": document["manifest_sha256"],
        "format": document["source"]["format"],
    }


def validate_document_reference(reference: Any, context: str) -> dict[str, Any]:
    ref = require_exact_keys(
        reference,
        {"path", "artifact_sha256", "content_sha256", "source_sha256", "manifest_sha256", "format"},
        context,
    )
    for key in {"path", "artifact_sha256", "content_sha256", "source_sha256", "manifest_sha256", "format"}:
        require_string(ref[key], f"{context}.{key}")
    current = document_reference(Path(ref["path"]))
    if current != ref:
        fail("document_changed", f"{context} no longer matches its validated artifact: {ref['path']}")
    return ref


def validate_finding(value: Any, context: str) -> dict[str, Any]:
    finding = require_exact_keys(
        value,
        {
            "id",
            "locators",
            "excerpt",
            "pattern",
            "family",
            "evidence",
            "explanation",
            "confidence",
            "severity",
            "suggestion",
            "preserve",
            "risk",
        },
        context,
    )
    require_id(finding["id"], "finding", f"{context}.id")
    require_string_list(finding["locators"], f"{context}.locators", nonempty=True)
    for key in {"excerpt", "pattern", "family", "evidence", "explanation", "suggestion"}:
        require_string(finding[key], f"{context}.{key}", allow_empty=(key == "excerpt"))
    require_enum(finding["confidence"], LEVELS, f"{context}.confidence")
    require_enum(finding["severity"], LEVELS, f"{context}.severity")
    require_string_list(finding["preserve"], f"{context}.preserve", nonempty=True)
    require_enum(finding["risk"], LEVELS, f"{context}.risk")
    return finding


def validate_unresolved(value: Any, context: str) -> dict[str, Any]:
    item = require_exact_keys(value, {"id", "locators", "reason", "needed_context"}, context)
    require_id(item["id"], "unresolved", f"{context}.id")
    require_string_list(item["locators"], f"{context}.locators", nonempty=True)
    require_string(item["reason"], f"{context}.reason")
    require_string(item["needed_context"], f"{context}.needed_context")
    return item


def validate_plan_item(value: Any, context: str, finding_ids: set[str]) -> dict[str, Any]:
    item = require_exact_keys(
        value,
        {
            "id",
            "finding_ids",
            "locators",
            "operation",
            "expected_effect",
            "preserve",
            "risk",
            "recommendation",
            "disposition",
        },
        context,
    )
    require_id(item["id"], "plan", f"{context}.id")
    linked = require_string_list(item["finding_ids"], f"{context}.finding_ids")
    unknown = sorted(set(linked) - finding_ids)
    if unknown:
        fail("invalid_payload", f"{context}.finding_ids contains unknown findings: {unknown}")
    require_string_list(item["locators"], f"{context}.locators", nonempty=True)
    require_string(item["operation"], f"{context}.operation")
    require_string(item["expected_effect"], f"{context}.expected_effect")
    require_string_list(item["preserve"], f"{context}.preserve", nonempty=True)
    require_enum(item["risk"], LEVELS, f"{context}.risk")
    require_enum(item["recommendation"], PLAN_RECOMMENDATIONS, f"{context}.recommendation")
    require_enum(item["disposition"], PLAN_DISPOSITIONS, f"{context}.disposition")
    return item


def validate_plan_body(value: Any, finding_ids: set[str], context: str = "plan") -> dict[str, Any]:
    plan = require_exact_keys(value, {"summary", "user_constraints", "items"}, context)
    require_string(plan["summary"], f"{context}.summary")
    require_string_list(plan["user_constraints"], f"{context}.user_constraints")
    if not isinstance(plan["items"], list):
        fail("invalid_payload", f"{context}.items must be an array")
    for index, item in enumerate(plan["items"], start=1):
        validate_plan_item(item, f"{context}.items[{index}]", finding_ids)
    item_ids = [item["id"] for item in plan["items"]]
    require_unique(item_ids, f"{context}.items IDs")
    return plan


def build_plan(body: dict[str, Any], version: int) -> dict[str, Any]:
    canonical = {"summary": body["summary"], "user_constraints": body["user_constraints"], "items": body["items"]}
    return {"version": version, "hash": documents.canonical_hash(canonical), **deepcopy(canonical)}


def validate_review_payload(
    value: Any,
    analysis: dict[str, Any],
    source_format: str,
) -> dict[str, Any]:
    review = require_exact_keys(
        value,
        {"scope", "assessment", "sentence_interpretation", "findings", "unresolved", "coverage", "plan"},
        "review payload",
    )
    scope = require_exact_keys(
        review["scope"],
        {"input_form", "format", "languages", "genre", "included", "excluded", "locator_system", "limitations"},
        "review payload.scope",
    )
    for key in {"input_form", "format", "genre", "locator_system"}:
        require_string(scope[key], f"review payload.scope.{key}")
    if scope["format"] != source_format:
        fail(
            "invalid_payload",
            "review payload.scope.format must match the original document format",
        )
    for key in {"languages", "included", "excluded", "limitations"}:
        require_string_list(scope[key], f"review payload.scope.{key}")
    require_string(review["assessment"], "review payload.assessment")
    require_string(review["sentence_interpretation"], "review payload.sentence_interpretation")
    if not isinstance(review["findings"], list):
        fail("invalid_payload", "review payload.findings must be an array")
    for index, finding in enumerate(review["findings"], start=1):
        validate_finding(finding, f"review payload.findings[{index}]")
    finding_ids = [finding["id"] for finding in review["findings"]]
    require_unique(finding_ids, "review finding IDs")
    if finding_ids != sorted(finding_ids):
        fail("invalid_payload", "review findings must be sorted by stable ID")
    if not isinstance(review["unresolved"], list):
        fail("invalid_payload", "review payload.unresolved must be an array")
    for index, item in enumerate(review["unresolved"], start=1):
        validate_unresolved(item, f"review payload.unresolved[{index}]")
    unresolved_ids = [item["id"] for item in review["unresolved"]]
    require_unique(unresolved_ids, "unresolved IDs")
    coverage = require_exact_keys(
        review["coverage"],
        {
            "eligible_regions",
            "reviewed_regions",
            "clear_regions",
            "finding_regions",
            "unresolved_regions",
            "excluded_regions",
            "complete",
        },
        "review payload.coverage",
    )
    for key in coverage:
        if key == "complete":
            require_bool(coverage[key], f"review payload.coverage.{key}")
        else:
            require_int(coverage[key], f"review payload.coverage.{key}")
    if coverage["reviewed_regions"] > coverage["eligible_regions"]:
        fail("invalid_payload", "reviewed_regions cannot exceed eligible_regions")
    if coverage["complete"] and coverage["reviewed_regions"] != coverage["eligible_regions"]:
        fail("invalid_payload", "complete coverage requires all eligible regions to be reviewed")
    validate_plan_body(review["plan"], set(finding_ids), "review payload.plan")
    return {
        "scope": deepcopy(scope),
        "assessment": review["assessment"],
        "sentence_profile": {
            "analysis": deepcopy(analysis),
            "interpretation": review["sentence_interpretation"],
        },
        "findings": deepcopy(review["findings"]),
        "unresolved": deepcopy(review["unresolved"]),
        "coverage": deepcopy(coverage),
    }


def load_document_for_reference(reference: dict[str, Any]) -> dict[str, Any]:
    document = documents.load_artifact(Path(reference["path"]))
    documents.validate_document(document, require_fresh=True)
    return document


def plan_finding_ids(state: dict[str, Any]) -> set[str]:
    review = state["review"]
    return {finding["id"] for finding in review["findings"]} if review else set()


def gate_for_state(state: dict[str, Any]) -> dict[str, Any]:
    stage = state["stage"]
    if stage == "review":
        next_action = "record_review"
        allowed = ["record_review", "cancel"]
    elif stage == "plan":
        reason = state["plan_reason"]
        if reason == "initial":
            next_action = "await_plan_approval"
            allowed = ["revise_plan", "approve_plan", "cancel"]
        elif reason == "rejected":
            next_action = "revise_plan_after_rejection"
            allowed = ["revise_plan", "cancel"]
        else:
            next_action = "revise_plan_after_verification"
            allowed = ["revise_plan", "cancel"]
    elif stage == "execute":
        next_action = "execute_revision"
        allowed = ["record_execution", "cancel"]
    elif stage == "verify":
        next_action = "record_verification"
        allowed = ["record_verification", "cancel"]
    elif stage == "acceptance":
        next_action = "await_user_acceptance"
        allowed = ["accept", "reject", "cancel"]
    elif stage in {"done", "cancelled"}:
        next_action = "done"
        allowed = []
    else:
        next_action = "blocked"
        allowed = []
    return {
        "stage": stage,
        "cycle": state["cycle"],
        "state_revision": state["revision"],
        "next_action": next_action,
        "allowed_actions": allowed,
        "blockers": deepcopy(state["blockers"]),
    }


def validate_state(state: Any, *, validate_documents: bool = True) -> dict[str, Any]:
    state = require_exact_keys(
        state,
        {
            "schema_version",
            "revision",
            "stage",
            "cycle",
            "original_document",
            "current_document",
            "review",
            "plan",
            "plan_reason",
            "approval",
            "execution",
            "verification",
            "acceptance",
            "blockers",
            "history",
        },
        "workflow state",
    )
    if state["schema_version"] != SCHEMA_VERSION:
        fail("unsupported_schema", f"unsupported workflow schema: {state['schema_version']!r}")
    require_int(state["revision"], "workflow state.revision")
    require_enum(state["stage"], STAGES, "workflow state.stage")
    require_int(state["cycle"], "workflow state.cycle", minimum=1)
    for name in {"original_document", "current_document"}:
        if validate_documents:
            validate_document_reference(state[name], f"workflow state.{name}")
        else:
            require_exact_keys(
                state[name],
                {"path", "artifact_sha256", "content_sha256", "source_sha256", "manifest_sha256", "format"},
                f"workflow state.{name}",
            )
    original = state["original_document"]
    current = state["current_document"]
    for key in {"source_sha256", "manifest_sha256", "format"}:
        if current[key] != original[key]:
            fail("invalid_state", f"current document {key} differs from original anchor")

    finding_ids: set[str] = set()
    if state["review"] is not None:
        review = require_exact_keys(
            state["review"],
            {"scope", "assessment", "sentence_profile", "findings", "unresolved", "coverage"},
            "workflow state.review",
        )
        scope = require_exact_keys(
            review["scope"],
            {"input_form", "format", "languages", "genre", "included", "excluded", "locator_system", "limitations"},
            "workflow state.review.scope",
        )
        for key in {"input_form", "format", "genre", "locator_system"}:
            require_string(scope[key], f"workflow state.review.scope.{key}")
        if scope["format"] != original["format"]:
            fail("invalid_state", "workflow review scope format differs from the original document")
        for key in {"languages", "included", "excluded", "limitations"}:
            require_string_list(scope[key], f"workflow state.review.scope.{key}")
        require_string(review["assessment"], "workflow state.review.assessment")
        sentence_profile = require_exact_keys(
            review["sentence_profile"],
            {"analysis", "interpretation"},
            "workflow state.review.sentence_profile",
        )
        require_string(sentence_profile["interpretation"], "workflow state.review.sentence_profile.interpretation")
        if not isinstance(sentence_profile["analysis"], dict):
            fail("invalid_state", "workflow state review analysis must be an object")
        if validate_documents:
            original_document = load_document_for_reference(original)
            if sentence_profile["analysis"] != original_document["analysis"]:
                fail("invalid_state", "workflow state review analysis differs from the original document")
        if not isinstance(review["findings"], list):
            fail("invalid_state", "workflow state.review.findings must be an array")
        for index, finding in enumerate(review["findings"], start=1):
            validate_finding(finding, f"workflow state.review.findings[{index}]")
        finding_ids = {finding["id"] for finding in review["findings"]}
        if len(finding_ids) != len(review["findings"]):
            fail("invalid_state", "workflow state contains duplicate finding IDs")
        if [finding["id"] for finding in review["findings"]] != sorted(finding_ids):
            fail("invalid_state", "workflow state findings are not in stable ID order")
        if not isinstance(review["unresolved"], list):
            fail("invalid_state", "workflow state.review.unresolved must be an array")
        for index, item in enumerate(review["unresolved"], start=1):
            validate_unresolved(item, f"workflow state.review.unresolved[{index}]")
        require_unique([item["id"] for item in review["unresolved"]], "workflow state unresolved IDs")
        coverage = require_exact_keys(
            review["coverage"],
            {
                "eligible_regions",
                "reviewed_regions",
                "clear_regions",
                "finding_regions",
                "unresolved_regions",
                "excluded_regions",
                "complete",
            },
            "workflow state.review.coverage",
        )
        for key, value in coverage.items():
            if key == "complete":
                require_bool(value, f"workflow state.review.coverage.{key}")
            else:
                require_int(value, f"workflow state.review.coverage.{key}")
        if coverage["reviewed_regions"] > coverage["eligible_regions"]:
            fail("invalid_state", "workflow state reviewed regions exceed eligible regions")
        if coverage["complete"] and coverage["reviewed_regions"] != coverage["eligible_regions"]:
            fail("invalid_state", "complete workflow review must cover every eligible region")

    if state["plan"] is not None:
        plan = require_exact_keys(
            state["plan"],
            {"version", "hash", "summary", "user_constraints", "items"},
            "workflow state.plan",
        )
        require_int(plan["version"], "workflow state.plan.version", minimum=1)
        validate_plan_body(
            {"summary": plan["summary"], "user_constraints": plan["user_constraints"], "items": plan["items"]},
            finding_ids,
            "workflow state.plan",
        )
        expected = build_plan(
            {"summary": plan["summary"], "user_constraints": plan["user_constraints"], "items": plan["items"]},
            plan["version"],
        )["hash"]
        if plan["hash"] != expected:
            fail("invalid_state", "workflow state plan hash is invalid")
    require_enum(state["plan_reason"], {"initial", "rejected", "verification_failed"}, "workflow state.plan_reason")

    if state["approval"] is not None:
        approval = require_exact_keys(
            state["approval"],
            {"plan_version", "plan_hash", "base_content_sha256", "decision_note"},
            "workflow state.approval",
        )
        require_int(approval["plan_version"], "workflow state.approval.plan_version", minimum=1)
        for key in {"plan_hash", "base_content_sha256", "decision_note"}:
            require_string(approval[key], f"workflow state.approval.{key}", allow_empty=(key == "decision_note"))
        if state["plan"] is None or (
            approval["plan_version"] != state["plan"]["version"]
            or approval["plan_hash"] != state["plan"]["hash"]
        ):
            fail("invalid_state", "workflow state approval is stale")
        if state["stage"] in {"execute", "verify", "acceptance"} and approval[
            "base_content_sha256"
        ] != current["content_sha256"]:
            fail("invalid_state", "workflow state approval is bound to a different base document")

    if state["execution"] is not None:
        execution = require_exact_keys(
            state["execution"],
            {"cycle", "approved_plan_hash", "base_document", "candidate_document", "item_results"},
            "workflow state.execution",
        )
        require_int(execution["cycle"], "workflow state.execution.cycle", minimum=1)
        require_string(execution["approved_plan_hash"], "workflow state.execution.approved_plan_hash")
        if validate_documents:
            validate_document_reference(execution["base_document"], "workflow state.execution.base_document")
            validate_document_reference(execution["candidate_document"], "workflow state.execution.candidate_document")
        if not isinstance(execution["item_results"], list):
            fail("invalid_state", "workflow state.execution.item_results must be an array")
        result_ids: list[str] = []
        for index, result in enumerate(execution["item_results"], start=1):
            result = require_exact_keys(result, {"plan_item_id", "status", "note"}, f"execution result {index}")
            result_ids.append(require_id(result["plan_item_id"], "plan", f"execution result {index}.plan_item_id"))
            require_enum(result["status"], EXECUTION_STATUSES, f"execution result {index}.status")
            require_string(result["note"], f"execution result {index}.note", allow_empty=True)
        require_unique(result_ids, "workflow state execution result IDs")
        included_ids = {
            item["id"] for item in state["plan"]["items"] if item["disposition"] == "include"
        } if state["plan"] else set()
        if set(result_ids) != included_ids:
            fail("invalid_state", "workflow execution results do not match included plan items")
        if state["plan"] and execution["approved_plan_hash"] != state["plan"]["hash"]:
            fail("invalid_state", "workflow execution references a different plan")
        for reference_name in {"base_document", "candidate_document"}:
            for key in {"source_sha256", "manifest_sha256", "format"}:
                if execution[reference_name][key] != original[key]:
                    fail("invalid_state", f"execution {reference_name} differs from original {key}")

    if state["verification"] is not None:
        validate_verification_payload(state["verification"], finding_ids, context="workflow state.verification")
        if state["execution"] is None or state["verification"]["candidate_content_sha256"] != state[
            "execution"
        ]["candidate_document"]["content_sha256"]:
            fail("invalid_state", "workflow verification does not reference the execution candidate")
    acceptance = require_exact_keys(state["acceptance"], {"status", "feedback"}, "workflow state.acceptance")
    require_enum(acceptance["status"], {"pending", "accepted", "rejected", "cancelled"}, "acceptance status")
    if acceptance["feedback"] is not None:
        require_string(acceptance["feedback"], "acceptance feedback")
    require_string_list(state["blockers"], "workflow state.blockers")
    if not isinstance(state["history"], list):
        fail("invalid_state", "workflow state.history must be an array")
    for index, event in enumerate(state["history"], start=1):
        event = require_exact_keys(
            event,
            {"seq", "action", "stage_before", "stage_after", "cycle", "plan_version", "plan_hash"},
            f"workflow state.history[{index}]",
        )
        if event["seq"] != index:
            fail("invalid_state", "workflow history sequence is invalid")
        require_string(event["action"], f"workflow history event {index}.action")
        require_enum(event["stage_before"], STAGES, f"workflow history event {index}.stage_before")
        require_enum(event["stage_after"], STAGES, f"workflow history event {index}.stage_after")
        require_int(event["cycle"], f"workflow history event {index}.cycle", minimum=1)
        if event["plan_version"] is not None:
            require_int(event["plan_version"], f"workflow history event {index}.plan_version", minimum=1)
        if event["plan_hash"] is not None:
            require_string(event["plan_hash"], f"workflow history event {index}.plan_hash")

    if state["stage"] == "review" and any(
        value is not None for value in (state["review"], state["plan"], state["approval"], state["execution"], state["verification"])
    ):
        fail("invalid_state", "review stage cannot contain downstream state")
    if state["stage"] in {"execute", "verify", "acceptance", "done"} and state["approval"] is None:
        fail("invalid_state", f"{state['stage']} stage requires approval")
    if state["stage"] in {"verify", "acceptance", "done"} and state["execution"] is None:
        fail("invalid_state", f"{state['stage']} stage requires execution")
    if state["stage"] in {"acceptance", "done"} and state["verification"] is None:
        fail("invalid_state", f"{state['stage']} stage requires verification")
    if state["stage"] in {"execute", "verify", "acceptance"} and state["execution"] is not None:
        if state["execution"]["base_document"] != current:
            fail("invalid_state", f"{state['stage']} stage execution base differs from current document")
    if state["stage"] == "plan" and state["plan_reason"] == "verification_failed":
        if state["execution"] is None or state["verification"] is None or state["verification"]["status"] != "failed":
            fail("invalid_state", "verification-failed plan state requires a failed verification")
        if state["execution"]["base_document"] != current:
            fail("invalid_state", "failed verification must keep the pre-execution base")
    if state["stage"] == "plan" and state["plan_reason"] == "rejected":
        if state["execution"] is None or state["acceptance"]["status"] != "rejected":
            fail("invalid_state", "rejected plan state requires rejected acceptance")
        if state["execution"]["candidate_document"] != current:
            fail("invalid_state", "rejected candidate must become the current base")
    if state["stage"] == "done" and acceptance["status"] != "accepted":
        fail("invalid_state", "done stage requires accepted status")
    if state["stage"] == "done" and state["execution"]["candidate_document"] != current:
        fail("invalid_state", "accepted candidate must become the current document")
    if state["stage"] == "cancelled" and acceptance["status"] != "cancelled":
        fail("invalid_state", "cancelled stage requires cancelled status")
    return state


def validate_verification_payload(value: Any, finding_ids: set[str], *, context: str = "verification payload") -> dict[str, Any]:
    verification = require_exact_keys(
        value,
        {
            "candidate_content_sha256",
            "status",
            "summary",
            "information_check",
            "structure_check",
            "style_check",
            "finding_results",
            "new_findings",
            "residuals",
        },
        context,
    )
    require_string(verification["candidate_content_sha256"], f"{context}.candidate_content_sha256")
    overall = require_enum(verification["status"], VERIFICATION_STATUSES, f"{context}.status")
    require_string(verification["summary"], f"{context}.summary")
    check_statuses: list[str] = []
    for key in {"information_check", "structure_check", "style_check"}:
        check = require_exact_keys(verification[key], {"status", "summary"}, f"{context}.{key}")
        check_statuses.append(require_enum(check["status"], CHECK_STATUSES, f"{context}.{key}.status"))
        require_string(check["summary"], f"{context}.{key}.summary")
    if overall != "failed" and "failed" in check_statuses:
        fail("invalid_payload", f"{context}.status must be failed when a required check fails")
    if overall == "failed" and "failed" not in check_statuses:
        fail("invalid_payload", f"{context}.status failed requires at least one failed check")
    if not isinstance(verification["finding_results"], list):
        fail("invalid_payload", f"{context}.finding_results must be an array")
    result_ids: list[str] = []
    for index, result in enumerate(verification["finding_results"], start=1):
        result = require_exact_keys(result, {"finding_id", "status", "note"}, f"{context}.finding_results[{index}]")
        finding_id = require_id(result["finding_id"], "finding", f"{context}.finding_results[{index}].finding_id")
        if finding_id not in finding_ids:
            fail("invalid_payload", f"{context} references unknown finding {finding_id}")
        result_ids.append(finding_id)
        require_enum(result["status"], FINDING_RESULTS, f"{context}.finding_results[{index}].status")
        require_string(result["note"], f"{context}.finding_results[{index}].note", allow_empty=True)
    require_unique(result_ids, f"{context} finding result IDs")
    if not isinstance(verification["new_findings"], list):
        fail("invalid_payload", f"{context}.new_findings must be an array")
    for index, finding in enumerate(verification["new_findings"], start=1):
        validate_finding(finding, f"{context}.new_findings[{index}]")
    require_string_list(verification["residuals"], f"{context}.residuals")
    return verification


def append_event(state: dict[str, Any], action: str, stage_before: str) -> None:
    plan = state["plan"]
    state["history"].append(
        {
            "seq": len(state["history"]) + 1,
            "action": action,
            "stage_before": stage_before,
            "stage_after": state["stage"],
            "cycle": state["cycle"],
            "plan_version": plan["version"] if plan else None,
            "plan_hash": plan["hash"] if plan else None,
        }
    )
    state["revision"] += 1


def apply_record_review(state: dict[str, Any], payload: dict[str, Any]) -> None:
    document = load_document_for_reference(state["current_document"])
    review = validate_review_payload(
        payload,
        document["analysis"],
        document["source"]["format"],
    )
    plan = build_plan(payload["plan"], 1)
    state["review"] = review
    state["plan"] = plan
    state["stage"] = "plan"
    state["plan_reason"] = "initial"


def apply_revise_plan(state: dict[str, Any], payload: dict[str, Any]) -> None:
    body = validate_plan_body(payload, plan_finding_ids(state), "plan revision payload")
    version = state["plan"]["version"] + 1 if state["plan"] else 1
    state["plan"] = build_plan(body, version)
    state["approval"] = None
    state["execution"] = None
    state["verification"] = None
    state["acceptance"] = {"status": "pending", "feedback": None}
    state["plan_reason"] = "initial"


def apply_approve_plan(state: dict[str, Any], payload: dict[str, Any]) -> None:
    approval = require_exact_keys(payload, {"plan_version", "plan_hash", "decision_note"}, "approval payload")
    require_int(approval["plan_version"], "approval payload.plan_version", minimum=1)
    require_string(approval["plan_hash"], "approval payload.plan_hash")
    require_string(approval["decision_note"], "approval payload.decision_note", allow_empty=True)
    plan = state["plan"]
    if plan is None or approval["plan_version"] != plan["version"] or approval["plan_hash"] != plan["hash"]:
        fail("stale_plan", "approval does not match the current plan version and hash")
    pending = [item["id"] for item in plan["items"] if item["disposition"] == "pending"]
    if pending:
        fail("pending_plan_items", f"plan contains undecided items: {pending}")
    state["approval"] = {
        **deepcopy(approval),
        "base_content_sha256": state["current_document"]["content_sha256"],
    }
    state["stage"] = "execute"


def apply_record_execution(state: dict[str, Any], payload: dict[str, Any]) -> None:
    execution = require_exact_keys(
        payload,
        {"approved_plan_hash", "base_content_sha256", "candidate_document", "item_results"},
        "execution payload",
    )
    approval = state["approval"]
    if execution["approved_plan_hash"] != approval["plan_hash"]:
        fail("stale_plan", "execution does not reference the approved plan hash")
    if execution["base_content_sha256"] != approval["base_content_sha256"]:
        fail("stale_document", "execution base does not match the approved document")
    candidate = document_reference(Path(require_string(execution["candidate_document"], "execution payload.candidate_document")))
    original = state["original_document"]
    for key in {"source_sha256", "manifest_sha256", "format"}:
        if candidate[key] != original[key]:
            fail("candidate_mismatch", f"candidate {key} differs from the original document anchor")
    if not isinstance(execution["item_results"], list):
        fail("invalid_payload", "execution payload.item_results must be an array")
    included = [item["id"] for item in state["plan"]["items"] if item["disposition"] == "include"]
    result_ids: list[str] = []
    normalized_results: list[dict[str, Any]] = []
    for index, result in enumerate(execution["item_results"], start=1):
        result = require_exact_keys(result, {"plan_item_id", "status", "note"}, f"execution payload.item_results[{index}]")
        plan_item_id = require_id(result["plan_item_id"], "plan", f"execution payload.item_results[{index}].plan_item_id")
        result_ids.append(plan_item_id)
        require_enum(result["status"], EXECUTION_STATUSES, f"execution payload.item_results[{index}].status")
        require_string(result["note"], f"execution payload.item_results[{index}].note", allow_empty=True)
        normalized_results.append(deepcopy(result))
    require_unique(result_ids, "execution result plan item IDs")
    if set(result_ids) != set(included):
        fail("invalid_payload", f"execution results must cover included plan items exactly: {included}")
    state["execution"] = {
        "cycle": state["cycle"],
        "approved_plan_hash": approval["plan_hash"],
        "base_document": deepcopy(state["current_document"]),
        "candidate_document": candidate,
        "item_results": normalized_results,
    }
    state["verification"] = None
    state["stage"] = "verify"


def apply_record_verification(state: dict[str, Any], payload: dict[str, Any]) -> None:
    verification = validate_verification_payload(payload, plan_finding_ids(state))
    candidate = state["execution"]["candidate_document"]
    if verification["candidate_content_sha256"] != candidate["content_sha256"]:
        fail("stale_document", "verification does not reference the current execution candidate")
    state["verification"] = deepcopy(verification)
    if verification["status"] == "failed":
        state["stage"] = "plan"
        state["plan_reason"] = "verification_failed"
        state["approval"] = None
        state["cycle"] += 1
    else:
        state["stage"] = "acceptance"
        state["acceptance"] = {"status": "pending", "feedback": None}


def apply_accept(state: dict[str, Any], payload: dict[str, Any]) -> None:
    decision = require_exact_keys(payload, {"decision_note"}, "acceptance payload")
    require_string(decision["decision_note"], "acceptance payload.decision_note", allow_empty=True)
    if state["verification"]["status"] not in {"pass", "pass_with_residuals"}:
        fail("verification_required", "only a passing latest verification can be accepted")
    state["current_document"] = deepcopy(state["execution"]["candidate_document"])
    state["acceptance"] = {"status": "accepted", "feedback": decision["decision_note"] or None}
    state["stage"] = "done"


def apply_reject(state: dict[str, Any], payload: dict[str, Any]) -> None:
    decision = require_exact_keys(payload, {"feedback"}, "rejection payload")
    feedback = require_string(decision["feedback"], "rejection payload.feedback")
    state["current_document"] = deepcopy(state["execution"]["candidate_document"])
    state["acceptance"] = {"status": "rejected", "feedback": feedback}
    state["approval"] = None
    state["stage"] = "plan"
    state["plan_reason"] = "rejected"
    state["cycle"] += 1


def apply_cancel(state: dict[str, Any], payload: dict[str, Any]) -> None:
    decision = require_exact_keys(payload, {"reason"}, "cancel payload")
    reason = require_string(decision["reason"], "cancel payload.reason", allow_empty=True)
    state["acceptance"] = {"status": "cancelled", "feedback": reason or None}
    state["stage"] = "cancelled"


APPLIERS: dict[str, Callable[[dict[str, Any], dict[str, Any]], None]] = {
    "record_review": apply_record_review,
    "revise_plan": apply_revise_plan,
    "approve_plan": apply_approve_plan,
    "record_execution": apply_record_execution,
    "record_verification": apply_record_verification,
    "accept": apply_accept,
    "reject": apply_reject,
    "cancel": apply_cancel,
}


def markdown_quote(text: str) -> str:
    return "\n".join(f"> {line}" for line in text.splitlines()) or ">"


def render_review(state: dict[str, Any]) -> str:
    review = state["review"]
    if review is None:
        return "# Review report\n\nReview is pending.\n"
    scope = review["scope"]
    analysis = review["sentence_profile"]["analysis"]
    stats = analysis["statistics"]
    lines = [
        "# Review report",
        "",
        "## Scope and coverage",
        "",
        f"- Input: {scope['input_form']} / {scope['format']}",
        f"- Languages: {', '.join(scope['languages']) or 'unspecified'}",
        f"- Genre: {scope['genre']}",
        f"- Locator system: {scope['locator_system']}",
        f"- Included: {', '.join(scope['included']) or 'all eligible prose'}",
        f"- Excluded: {', '.join(scope['excluded']) or 'none'}",
        f"- Limitations: {', '.join(scope['limitations']) or 'none'}",
        "",
        "## Overall assessment",
        "",
        review["assessment"],
        "",
        "## Sentence-length profile",
        "",
        f"- Sentences: {analysis['sentence_count']} ({analysis['unit_label']})",
        f"- Reliable distribution: {analysis['reliable_distribution']}",
        f"- Mean / median: {stats['mean']} / {stats['median']}",
        f"- Population standard deviation / coefficient of variation: {stats['population_stddev']} / {stats['coefficient_of_variation']}",
        f"- Q1 / Q3 / minimum / maximum: {stats['q1']} / {stats['q3']} / {stats['minimum']} / {stats['maximum']}",
        f"- Uniform runs: {len(analysis['uniform_runs'])}",
        f"- Warnings: {', '.join(analysis['warnings']) or 'none'}",
        "",
        review["sentence_profile"]["interpretation"],
        "",
        "## Findings",
        "",
    ]
    if not review["findings"]:
        lines.extend(["No supported findings.", ""])
    for finding in review["findings"]:
        lines.extend(
            [
                f"### {finding['id']}: {finding['pattern']}",
                "",
                f"- Locators: {', '.join(finding['locators'])}",
                f"- Family: {finding['family']}",
                f"- Confidence / severity / risk: {finding['confidence']} / {finding['severity']} / {finding['risk']}",
                f"- Evidence: {finding['evidence']}",
                f"- Explanation: {finding['explanation']}",
                f"- Suggestion: {finding['suggestion']}",
                f"- Preserve: {', '.join(finding['preserve'])}",
                "",
                markdown_quote(finding["excerpt"]),
                "",
            ]
        )
    lines.extend(["## Unresolved items", ""])
    if not review["unresolved"]:
        lines.extend(["None.", ""])
    for item in review["unresolved"]:
        lines.extend(
            [
                f"- {item['id']} ({', '.join(item['locators'])}): {item['reason']} Needed: {item['needed_context']}",
            ]
        )
    coverage = review["coverage"]
    lines.extend(
        [
            "",
            "## Coverage closeout",
            "",
            f"Eligible/reviewed: {coverage['eligible_regions']}/{coverage['reviewed_regions']}; clear: {coverage['clear_regions']}; finding: {coverage['finding_regions']}; unresolved: {coverage['unresolved_regions']}; excluded: {coverage['excluded_regions']}; complete: {coverage['complete']}.",
            "",
        ]
    )
    return "\n".join(lines)


def render_plan(state: dict[str, Any]) -> str:
    plan = state["plan"]
    if plan is None:
        return "# Revision plan\n\nPlan is pending.\n"
    lines = [
        "# Revision plan",
        "",
        f"Version: {plan['version']}",
        f"Hash: `{plan['hash']}`",
        f"Status: {'approved' if state['approval'] else 'awaiting explicit approval'}",
        f"Reason: {state['plan_reason']}",
        "",
        plan["summary"],
        "",
        "## User constraints",
        "",
    ]
    lines.extend([f"- {item}" for item in plan["user_constraints"]] or ["- None"])
    lines.extend(["", "## Plan items", ""])
    if not plan["items"]:
        lines.extend(["No edits are proposed.", ""])
    for item in plan["items"]:
        lines.extend(
            [
                f"### {item['id']}: {item['disposition']}",
                "",
                f"- Findings: {', '.join(item['finding_ids']) or 'none'}",
                f"- Locators: {', '.join(item['locators'])}",
                f"- Operation: {item['operation']}",
                f"- Expected effect: {item['expected_effect']}",
                f"- Preserve: {', '.join(item['preserve'])}",
                f"- Risk / recommendation: {item['risk']} / {item['recommendation']}",
                "",
            ]
        )
    return "\n".join(lines)


def render_verification(state: dict[str, Any]) -> str:
    verification = state["verification"]
    if verification is None:
        return "# Verification report\n\nVerification is pending.\n"
    lines = [
        "# Verification report",
        "",
        f"Status: {verification['status']}",
        f"Candidate content hash: `{verification['candidate_content_sha256']}`",
        "",
        verification["summary"],
        "",
        "## Checks",
        "",
    ]
    for key, label in (
        ("information_check", "Bidirectional information"),
        ("structure_check", "Structure and protected content"),
        ("style_check", "Style and findings"),
    ):
        check = verification[key]
        lines.append(f"- {label}: {check['status']} — {check['summary']}")
    lines.extend(["", "## Finding results", ""])
    lines.extend(
        [f"- {item['finding_id']}: {item['status']} — {item['note']}" for item in verification["finding_results"]]
        or ["- None"]
    )
    lines.extend(["", "## New findings", ""])
    lines.extend(
        [f"- {item['id']}: {item['pattern']} at {', '.join(item['locators'])}" for item in verification["new_findings"]]
        or ["- None"]
    )
    lines.extend(["", "## Residuals", ""])
    lines.extend([f"- {item}" for item in verification["residuals"]] or ["- None"])
    lines.append("")
    return "\n".join(lines)


def render_resume(state: dict[str, Any]) -> str:
    gate = gate_for_state(state)
    lines = [
        "# Full-mode resume",
        "",
        f"- Stage: {gate['stage']}",
        f"- Cycle: {gate['cycle']}",
        f"- State revision: {gate['state_revision']}",
        f"- Next action: {gate['next_action']}",
        f"- Allowed actions: {', '.join(gate['allowed_actions']) or 'none'}",
        f"- Blockers: {', '.join(gate['blockers']) or 'none'}",
        f"- Original document: `{state['original_document']['path']}`",
        f"- Current base: `{state['current_document']['path']}`",
    ]
    if state["plan"]:
        lines.extend(
            [
                f"- Plan: v{state['plan']['version']} `{state['plan']['hash']}`",
                f"- Plan approved: {state['approval'] is not None}",
            ]
        )
    if state["execution"]:
        lines.append(f"- Latest candidate: `{state['execution']['candidate_document']['path']}`")
    if state["verification"]:
        lines.append(f"- Latest verification: {state['verification']['status']}")
    lines.extend(
        [
            "",
            "Read `state.yaml` as the authority. These Markdown files are projections only.",
            "",
        ]
    )
    return "\n".join(lines)


def rendered_views(state: dict[str, Any]) -> dict[str, bytes]:
    return {
        VIEW_NAMES["review"]: render_review(state).encode("utf-8"),
        VIEW_NAMES["plan"]: render_plan(state).encode("utf-8"),
        VIEW_NAMES["verification"]: render_verification(state).encode("utf-8"),
        VIEW_NAMES["resume"]: render_resume(state).encode("utf-8"),
    }


def state_path(workspace: Path) -> Path:
    return workspace.resolve() / STATE_NAME


def load_state(workspace: Path) -> dict[str, Any]:
    path = state_path(workspace)
    state = load_json_object(path, "workflow state")
    return validate_state(state)


def persist_state_and_views(workspace: Path, state: dict[str, Any], *, overwrite_state: bool) -> None:
    validate_state(state)
    views = rendered_views(state)
    for name, data in views.items():
        documents.write_atomic(workspace / name, data, overwrite=True)
    documents.write_atomic(state_path(workspace), documents.dump_artifact(state), overwrite=overwrite_state)


def command_summary(workspace: Path, state: dict[str, Any]) -> dict[str, Any]:
    gate = gate_for_state(state)
    gate["views"] = {key: str((workspace / name).resolve()) for key, name in VIEW_NAMES.items()}
    if state["plan"]:
        gate["plan_version"] = state["plan"]["version"]
        gate["plan_hash"] = state["plan"]["hash"]
    return gate


def run_init(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    workspace = Path(args.workspace).resolve()
    reference = document_reference(Path(args.document))
    if workspace.exists():
        if not workspace.is_dir():
            fail("invalid_workspace", f"workspace is not a directory: {workspace}")
        if any(workspace.iterdir()):
            fail("output_exists", f"workspace must be empty: {workspace}")
    else:
        try:
            workspace.mkdir()
        except OSError as exc:
            fail("workspace_create_failed", f"cannot create workspace: {workspace}: {exc}")
    state = {
        "schema_version": SCHEMA_VERSION,
        "revision": 0,
        "stage": "review",
        "cycle": 1,
        "original_document": deepcopy(reference),
        "current_document": deepcopy(reference),
        "review": None,
        "plan": None,
        "plan_reason": "initial",
        "approval": None,
        "execution": None,
        "verification": None,
        "acceptance": {"status": "pending", "feedback": None},
        "blockers": [],
        "history": [
            {
                "seq": 1,
                "action": "init",
                "stage_before": "review",
                "stage_after": "review",
                "cycle": 1,
                "plan_version": None,
                "plan_hash": None,
            }
        ],
    }
    persist_state_and_views(workspace, state, overwrite_state=False)
    return str(state_path(workspace)), command_summary(workspace, state)


def run_gate(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    workspace = Path(args.workspace).resolve()
    state = load_state(workspace)
    return str(state_path(workspace)), command_summary(workspace, state)


def run_apply(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    workspace = Path(args.workspace).resolve()
    state = load_state(workspace)
    action = args.action
    if action not in ACTIONS:
        fail("invalid_action", f"unsupported action: {action}")
    gate = gate_for_state(state)
    if action not in gate["allowed_actions"]:
        fail("invalid_transition", f"action {action!r} is not allowed in stage {state['stage']!r}")
    payload = load_json_object(Path(args.payload_file), f"{action} payload")
    updated = deepcopy(state)
    stage_before = updated["stage"]
    APPLIERS[action](updated, payload)
    append_event(updated, action, stage_before)
    validate_state(updated)
    persist_state_and_views(workspace, updated, overwrite_state=True)
    return str(state_path(workspace)), command_summary(workspace, updated)


def run_validate(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    workspace = Path(args.workspace).resolve()
    state = load_state(workspace)
    return str(state_path(workspace)), command_summary(workspace, state)


def run_render(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    workspace = Path(args.workspace).resolve()
    state = load_state(workspace)
    for name, data in rendered_views(state).items():
        documents.write_atomic(workspace / name, data, overwrite=True)
    return str(state_path(workspace)), command_summary(workspace, state)


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        fail("invalid_arguments", message)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        description="Manage the gate-driven Paper Humanizer full-mode workflow.",
        epilog=(
            "Examples:\n"
            "  full_workflow.py init --document document.yaml --workspace /tmp/paper-humanizer-run\n"
            "  full_workflow.py gate --workspace /tmp/paper-humanizer-run\n"
            "  full_workflow.py apply --workspace /tmp/paper-humanizer-run --action record_review --payload-file review.json\n"
            "  full_workflow.py validate --workspace /tmp/paper-humanizer-run\n"
            "  full_workflow.py render --workspace /tmp/paper-humanizer-run"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=JsonArgumentParser)
    init = subparsers.add_parser("init", help="initialize an empty workflow workspace")
    init.add_argument("--document", required=True, help="fresh document artifact")
    init.add_argument("--workspace", required=True, help="new or empty workflow directory")
    for command in ("gate", "validate", "render"):
        subparser = subparsers.add_parser(command, help=f"{command} the workflow")
        subparser.add_argument("--workspace", required=True, help="workflow directory")
    apply = subparsers.add_parser("apply", help="apply one gate-permitted state transition")
    apply.add_argument("--workspace", required=True, help="workflow directory")
    apply.add_argument("--action", required=True, choices=sorted(ACTIONS), help="state transition")
    apply.add_argument("--payload-file", required=True, help="JSON-compatible YAML payload")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    command = ""
    try:
        args = build_parser().parse_args(argv)
        command = args.command
        runners: dict[str, Callable[[argparse.Namespace], tuple[str, dict[str, Any]]]] = {
            "init": run_init,
            "gate": run_gate,
            "apply": run_apply,
            "validate": run_validate,
            "render": run_render,
        }
        artifact, summary = runners[command](args)
        documents.stdout_envelope(ok=True, command=command, artifact=artifact, summary=summary, error=None)
        return 0
    except documents.PipelineError as exc:
        sys.stderr.write(exc.message + "\n")
        documents.stdout_envelope(
            ok=False,
            command=command,
            artifact=None,
            summary={},
            error={"code": exc.code, "message": exc.message},
        )
        return 2
    except Exception as exc:  # pragma: no cover - last-resort stable failure contract
        message = f"unexpected workflow failure: {exc}"
        sys.stderr.write(message + "\n")
        documents.stdout_envelope(
            ok=False,
            command=command,
            artifact=None,
            summary={},
            error={"code": "internal_error", "message": message},
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

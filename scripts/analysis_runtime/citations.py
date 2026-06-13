from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .algorithm_adapter import call_algorithm_handler
from . import runtime_db


CITATION_FORBIDDEN_FIELDS = ["items", "timeline", "basis", "ref_index", "function"]
CITATION_REVIEW_FORBIDDEN_FIELDS = ["ref_index", "function", "is_key_reference", "mentions"]


def _citation_work_key(ref_index: int) -> str:
    return f"citation-work-{ref_index}"


def _ref_index_from_work_key(work_key: object) -> int | None:
    value = str(work_key or "").strip()
    if not value.startswith("citation-work-"):
        return None
    suffix = value.removeprefix("citation-work-")
    return int(suffix) if suffix.isdigit() else None


def _load_citation_workset_items(db_path: Path) -> list[dict[str, Any]]:
    with runtime_db.connect_db(db_path) as connection:
        return runtime_db.fetch_citation_workset_items(connection)


def _citation_packages(workset_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    packages: list[dict[str, Any]] = []
    for item in workset_items:
        ref_index = int(item["ref_index"])
        reference = dict(item.get("reference", {}))
        packages.append(
            {
                "citation_work_key": _citation_work_key(ref_index),
                "source_reference_number": item.get("ref_number"),
                "internal_ref_index": ref_index,
                "title": reference.get("title", ""),
                "authors": reference.get("author", []),
                "publication_year": reference.get("year"),
                "mention_count": item.get("mention_count", len(item.get("mentions", []))),
                "snippets": [
                    str(mention.get("snippet", "")).strip()
                    for mention in item.get("mentions", [])
                    if str(mention.get("snippet", "")).strip()
                ][:3],
            }
        )
    return packages


def _citation_batch_packages(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    batches: list[dict[str, Any]] = []
    for offset in range(0, len(packages), 12):
        keys = [pkg["citation_work_key"] for pkg in packages[offset : offset + 12]]
        batches.append(
            {
                "batch_id": f"citation-batch-{offset // 12}",
                "batch_key": f"citation-batch-{offset // 12}",
                "citation_work_keys": keys,
                "required_return_shape": {
                    "citation_semantic_reviews": [
                        {
                            "citation_work_key": "copy from this batch",
                            "topic": "semantic topic in the source paper",
                            "usage": "how the source uses this cited work",
                            "role_in_context": "natural-language role, not an enum",
                            "keywords": ["keyword"],
                            "summary": "citation-specific semantic summary",
                            "key_reference_reason": "optional evidence-backed reason",
                        }
                    ]
                },
                "forbidden_fields": CITATION_REVIEW_FORBIDDEN_FIELDS,
                "allowed_enum_values": {
                    "citation_work_key": keys,
                    "role_in_context": "Free-form natural language; runtime derives renderer function categories.",
                },
                "minimal_valid_example": {
                    "citation_semantic_reviews": [
                        {
                            "citation_work_key": keys[0] if keys else "citation-work-0",
                            "topic": "object detection benchmarks",
                            "usage": "Used as background for benchmark comparison.",
                            "role_in_context": "background context for evaluation setup",
                            "keywords": ["benchmark"],
                            "summary": "The citation supplies benchmark context for the source discussion.",
                            "key_reference_reason": "",
                        }
                    ]
                },
                "merge_notes": "Default to delegating this citation batch when subagents are available. Subagent drafts only this batch. Main agent is the single DB writer, keeps citation_work_key unchanged, merges citation_semantic_reviews[], then adds global timeline_summaries and summary once.",
                "subagent_prompt": (
                    "Review this citation batch. Return JSON with citation_semantic_reviews[] only. "
                    "Use citation_work_key as the key. Do not include ref_index, function, mentions, is_key_reference, or timeline buckets. "
                    "Do not submit timeline_summaries or global summary from the subagent batch. "
                    "Do not write DB, run runtime commands, submit payloads, modify citation_work_key, or generate final artifacts."
                ),
            }
        )
    return batches


def _function_from_role(role: object) -> str:
    text = str(role or "").strip().lower()
    keyword_map = [
        ("baseline", ("baseline", "comparison", "compare", "对比", "基线")),
        ("contrast", ("contrast", "different", "however", "区别", "反例")),
        ("component", ("component", "module", "loss", "architecture", "组件", "模块")),
        ("dataset", ("dataset", "benchmark", "coco", "imagenet", "数据集")),
        ("tooling", ("tool", "implementation", "library", "framework", "工具")),
        ("historical", ("history", "early", "origin", "foundation", "历史", "奠基")),
        ("background", ("background", "motivation", "context", "背景", "动机")),
    ]
    for function_value, tokens in keyword_map:
        if any(token in text for token in tokens):
            return function_value
    return "uncategorized"


def _citation_payload_errors(payload: dict[str, Any], workset_items: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]], dict[str, str], str]:
    errors: list[str] = []
    forbidden = sorted(key for key in CITATION_FORBIDDEN_FIELDS if key in payload)
    if forbidden:
        errors.append(f"forbidden top-level keys for current citation payload: {forbidden}")
    reviews = payload.get("citation_semantic_reviews")
    if not isinstance(reviews, list):
        return [*errors, "citation_semantic_reviews must be an array"], [], {}, ""
    timeline_summaries = payload.get("timeline_summaries")
    if not isinstance(timeline_summaries, dict):
        errors.append("timeline_summaries must be an object with early, middle, recent")
        timeline_summaries = {}
    normalized_summaries: dict[str, str] = {}
    for key in ("early", "middle", "recent"):
        value = timeline_summaries.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"timeline_summaries.{key} must be non-empty string")
        else:
            normalized_summaries[key] = value.strip()
    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        errors.append("summary must be non-empty string")
        summary_text = ""
    else:
        summary_text = summary.strip()

    items_by_key = {_citation_work_key(int(item["ref_index"])): item for item in workset_items}
    expected_keys = set(items_by_key)
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, review in enumerate(reviews):
        if not isinstance(review, dict):
            errors.append(f"citation_semantic_reviews[{index}] must be object")
            continue
        if any(key in review for key in CITATION_REVIEW_FORBIDDEN_FIELDS):
            errors.append(f"{review.get('citation_work_key', f'citation_semantic_reviews[{index}]')} contains forbidden internal fields")
        work_key = str(review.get("citation_work_key", "")).strip()
        if work_key in seen:
            errors.append(f"duplicate citation_work_key: {work_key}")
            continue
        seen.add(work_key)
        workset_item = items_by_key.get(work_key)
        if workset_item is None:
            errors.append(f"unknown citation_work_key: {work_key}")
            continue
        topic = review.get("topic")
        usage = review.get("usage")
        role = review.get("role_in_context")
        item_summary = review.get("summary")
        keywords = review.get("keywords")
        if not isinstance(topic, str) or not topic.strip():
            errors.append(f"{work_key}.topic must be non-empty string")
        if not isinstance(usage, str) or not usage.strip():
            errors.append(f"{work_key}.usage must be non-empty string")
        if not isinstance(role, str) or not role.strip():
            errors.append(f"{work_key}.role_in_context must be non-empty string")
        if not isinstance(item_summary, str) or not item_summary.strip():
            errors.append(f"{work_key}.summary must be non-empty string")
        if not isinstance(keywords, list) or not all(isinstance(item, str) and item.strip() for item in keywords):
            errors.append(f"{work_key}.keywords must be a string array")
        normalized.append(
            {
                "ref_index": int(workset_item["ref_index"]),
                "function": _function_from_role(role),
                "topic": topic.strip() if isinstance(topic, str) else "",
                "usage": usage.strip() if isinstance(usage, str) else "",
                "keywords": [str(item).strip() for item in keywords] if isinstance(keywords, list) else [],
                "summary": item_summary.strip() if isinstance(item_summary, str) else "",
                "is_key_reference": bool(str(review.get("key_reference_reason", "")).strip()),
                "confidence": 0.85,
                "metadata": {
                    "citation_work_key": work_key,
                    "role_in_context": role.strip() if isinstance(role, str) else "",
                    "key_reference_reason": str(review.get("key_reference_reason", "")).strip(),
                },
            }
        )
    missing = sorted(expected_keys - seen)
    if missing:
        errors.append(f"missing citation_semantic_reviews for citation_work_key values: {missing}")
    return errors, normalized, normalized_summaries, summary_text


def _derive_timeline_payload(workset_items: list[dict[str, Any]], timeline_summaries: dict[str, str]) -> dict[str, Any]:
    dated: list[tuple[int, int]] = []
    for item in workset_items:
        reference = dict(item.get("reference", {}))
        year = reference.get("year")
        if isinstance(year, int):
            dated.append((int(item["ref_index"]), year))
    dated.sort(key=lambda pair: (pair[1], pair[0]))
    buckets = {"early": [], "mid": [], "recent": []}
    total = len(dated)
    for position, (ref_index, _year) in enumerate(dated):
        if total == 0:
            break
        if position * 3 < total:
            buckets["early"].append(ref_index)
        elif position * 3 < total * 2:
            buckets["mid"].append(ref_index)
        else:
            buckets["recent"].append(ref_index)
    return {
        "timeline": {
            "early": {"summary": timeline_summaries["early"], "ref_indexes": buckets["early"]},
            "mid": {"summary": timeline_summaries["middle"], "ref_indexes": buckets["mid"]},
            "recent": {"summary": timeline_summaries["recent"], "ref_indexes": buckets["recent"]},
        }
    }


def _summary_basis_from_reviews(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    topics = list(dict.fromkeys(str(item.get("topic", "")).strip() for item in reviews if str(item.get("topic", "")).strip()))
    usages = list(dict.fromkeys(str(item.get("usage", "")).strip() for item in reviews if str(item.get("usage", "")).strip()))
    if len(topics) < 2:
        topics.extend(["citation context", "research positioning"][len(topics):])
    if len(usages) < 2:
        usages.extend(["supports the source paper's literature positioning", "connects cited work to the source argument"][len(usages):])
    key_ref_indexes = [int(item["ref_index"]) for item in reviews if item.get("is_key_reference")]
    if not key_ref_indexes and reviews:
        key_ref_indexes = [int(reviews[0]["ref_index"])]
    return {
        "research_threads": topics[:6],
        "argument_shape": usages[:6],
        "key_ref_indexes": key_ref_indexes[:5],
    }


def prepare_citation_workset(db_path: Path) -> tuple[dict[str, Any], int]:
    payload, code = call_algorithm_handler("_handle_prepare_citation_workset", db_path, payload={})
    return payload, int(code)


def enrich_citation_workset_payload(payload: dict[str, Any]) -> dict[str, Any]:
    workset_path = str(payload.get("workset_path", ""))
    review_path = str(payload.get("review_path", ""))
    if not payload.get("error"):
        workset = json.loads(Path(workset_path).read_text(encoding="utf-8")) if workset_path else {}
        packages = _citation_packages(list(workset.get("workset_items", [])))
        payload.update(
            {
                "runtime_backend": "analysis_runtime.citations",
                "allowed_payload_shape": {
                    "citation_semantic_reviews": [
                        {
                            "citation_work_key": "citation-work-0",
                            "topic": "semantic topic",
                            "usage": "how the source uses this citation",
                            "role_in_context": "natural language role",
                            "keywords": ["keyword"],
                            "summary": "citation role summary",
                            "key_reference_reason": "optional",
                        }
                    ],
                    "timeline_summaries": {
                        "early": "early trajectory",
                        "middle": "middle trajectory",
                        "recent": "recent trajectory",
                    },
                    "summary": "global citation analysis summary",
                },
                "field_guidance": {
                    "citation_work_key": "Stable key from citation_work_packages; do not submit ref_index.",
                    "source_reference_number": "Original numeric citation number shown for human orientation.",
                    "role_in_context": "Natural language role; runtime maps it to internal renderer categories.",
                    "timeline_summaries": "Narrative summaries only; runtime derives bucket membership from years.",
                    "undated_items": "References with null publication_year are valid but cannot enter runtime-derived timeline buckets.",
                },
                "citation_work_packages": packages,
                "batch_work_packages": _citation_batch_packages(packages),
                "subagent_policy": "Default to delegating citation semantic review by batch when batch_work_packages exist and subagents are available. Skip only when subagents are unavailable, the batch is trivially small, or context cannot be split; record the reason. Subagents draft only; main agent is the single DB writer and submits one final payload.",
                "subagent_prompt_template": (
                    "You are reviewing one citation batch for literature-analysis. "
                    "Use only the provided citation_work_packages. Return JSON with citation_semantic_reviews[]; "
                    "each review must include citation_work_key, topic, usage, role_in_context, keywords, summary, and optional key_reference_reason. "
                    "Do not include ref_index, function, mentions, is_key_reference, timeline buckets, or timeline ref indexes. "
                    "Subagents do not write timeline_summaries or the global summary. "
                    "Do not write DB, run runtime commands, submit payloads, modify citation_work_key, or generate final artifacts."
                ),
                "merge_contract": {
                    "single_writer": "main_agent",
                    "required_payload_keys": ["citation_semantic_reviews", "timeline_summaries", "summary"],
                    "forbidden_submit_keys": CITATION_FORBIDDEN_FIELDS,
                    "forbidden_review_keys": CITATION_REVIEW_FORBIDDEN_FIELDS,
                    "merge_notes": "Subagents return batch drafts only. Main agent is the single DB writer, keeps citation_work_key unchanged, combines reviews, and writes timeline_summaries as natural-language summaries only.",
                },
            }
        )
    return payload


def persist_citation_analysis(db_path: Path, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    workset_items = _load_citation_workset_items(db_path)
    errors, normalized_reviews, timeline_summaries, summary_text = _citation_payload_errors(payload, workset_items)
    if errors:
        return {
            "error": {
                "code": "citation_payload_invalid",
                "message": "citation payload failed validation",
                "details": errors,
            },
            "known_citation_work_keys": [_citation_work_key(int(item["ref_index"])) for item in workset_items],
        }, 2
    semantics, code = call_algorithm_handler(
        "_handle_persist_citation_semantics",
        db_path,
        payload={"items": normalized_reviews},
    )
    if code != 0:
        return semantics, code
    timeline, code = call_algorithm_handler(
        "_handle_persist_citation_timeline",
        db_path,
        payload=_derive_timeline_payload(workset_items, timeline_summaries),
    )
    if code != 0:
        return {"citation_semantics": semantics, "citation_timeline": timeline, "error": timeline.get("error")}, code
    summary, code = call_algorithm_handler(
        "_handle_persist_citation_summary",
        db_path,
        payload={"summary": summary_text, "basis": _summary_basis_from_reviews(normalized_reviews)},
    )
    if code != 0:
        return (
            {
                "citation_semantics": semantics,
                "citation_timeline": timeline,
                "citation_summary": summary,
                "error": summary.get("error"),
            },
            code,
        )
    from .stages import render_public_outputs

    final_payload, code = render_public_outputs(db_path)
    return final_payload, code

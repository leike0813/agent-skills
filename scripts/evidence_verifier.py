#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from difflib import SequenceMatcher
from html import unescape
from typing import Any

FIXED_HALLUCINATION_WARNING = "刚才的证据中可能存在虚假证据，请注意。"
VALID_SOURCE_TYPES = {"web_url", "reference_title", "paper_text"}
REQUIRED_EVIDENCE_FIELDS = {"source_type", "source", "keywords", "claim"}


@dataclass
class VerificationResult:
    status: str
    detail: dict[str, Any]


def _print_json(payload: dict[str, Any], code: int = 0) -> None:
    print(json.dumps(payload, ensure_ascii=False))
    raise SystemExit(code)


def _normalize(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()


def _strip_html(text: str) -> str:
    without_script = re.sub(r"<script.*?>.*?</script>", " ", text, flags=re.S | re.I)
    without_style = re.sub(r"<style.*?>.*?</style>", " ", without_script, flags=re.S | re.I)
    without_tags = re.sub(r"<[^>]+>", " ", without_style)
    return _normalize(unescape(without_tags))


def _keyword_hits(text: str, keywords: list[str]) -> list[str]:
    normalized_text = _normalize(text)
    hits: list[str] = []
    for keyword in keywords:
        normalized_keyword = _normalize(keyword)
        if normalized_keyword and normalized_keyword in normalized_text:
            hits.append(keyword)
    return hits


def _title_similarity(query: str, candidate: str) -> float:
    return SequenceMatcher(None, _normalize(query), _normalize(candidate)).ratio()


def _http_get(url: str, timeout_sec: int = 10) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=timeout_sec) as response:
        raw = response.read(1_000_000)
        body = raw.decode("utf-8", errors="ignore")
        return response.getcode(), body


def _verify_web_url(source: str, keywords: list[str]) -> VerificationResult:
    try:
        status_code, body = _http_get(source)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return VerificationResult(
            status="uncertain",
            detail={"reason": "url_unreachable", "error": str(exc)},
        )

    hits = _keyword_hits(_strip_html(body), keywords)
    if hits:
        return VerificationResult(
            status="pass",
            detail={
                "reason": "keyword_match",
                "status_code": status_code,
                "matched_keywords": hits,
            },
        )
    return VerificationResult(
        status="fail",
        detail={
            "reason": "reachable_but_no_keyword_match",
            "status_code": status_code,
            "matched_keywords": [],
        },
    )


def _query_crossref(title: str) -> VerificationResult:
    url = "https://api.crossref.org/works?query.title=" + urllib.parse.quote(title) + "&rows=5"
    try:
        _, body = _http_get(url)
        data = json.loads(body)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        return VerificationResult(
            status="uncertain",
            detail={"backend": "crossref", "reason": "backend_unreachable", "error": str(exc)},
        )

    best_score = 0.0
    best_title = ""
    for item in data.get("message", {}).get("items", []):
        titles = item.get("title", [])
        if not titles:
            continue
        candidate = str(titles[0])
        score = _title_similarity(title, candidate)
        if score > best_score:
            best_score = score
            best_title = candidate

    if best_score >= 0.86:
        return VerificationResult(
            status="pass",
            detail={
                "backend": "crossref",
                "reason": "title_match",
                "matched_title": best_title,
                "score": round(best_score, 4),
            },
        )
    return VerificationResult(
        status="fail",
        detail={"backend": "crossref", "reason": "no_title_match", "best_score": round(best_score, 4)},
    )


def _query_arxiv(title: str) -> VerificationResult:
    url = "https://export.arxiv.org/api/query?search_query=all:" + urllib.parse.quote(title) + "&start=0&max_results=5"
    try:
        _, body = _http_get(url)
        root = ET.fromstring(body)
    except (urllib.error.URLError, TimeoutError, ET.ParseError, ValueError) as exc:
        return VerificationResult(
            status="uncertain",
            detail={"backend": "arxiv", "reason": "backend_unreachable", "error": str(exc)},
        )

    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    best_score = 0.0
    best_title = ""
    for entry in root.findall("atom:entry", namespace):
        title_elem = entry.find("atom:title", namespace)
        if title_elem is None or not title_elem.text:
            continue
        candidate = title_elem.text.strip()
        score = _title_similarity(title, candidate)
        if score > best_score:
            best_score = score
            best_title = candidate

    if best_score >= 0.86:
        return VerificationResult(
            status="pass",
            detail={
                "backend": "arxiv",
                "reason": "title_match",
                "matched_title": best_title,
                "score": round(best_score, 4),
            },
        )
    return VerificationResult(
        status="fail",
        detail={"backend": "arxiv", "reason": "no_title_match", "best_score": round(best_score, 4)},
    )


def _query_semantic_scholar(title: str) -> VerificationResult:
    url = (
        "https://api.semanticscholar.org/graph/v1/paper/search?query="
        + urllib.parse.quote(title)
        + "&limit=5&fields=title"
    )
    try:
        _, body = _http_get(url)
        data = json.loads(body)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        return VerificationResult(
            status="uncertain",
            detail={"backend": "semantic_scholar", "reason": "backend_unreachable", "error": str(exc)},
        )

    best_score = 0.0
    best_title = ""
    for item in data.get("data", []):
        candidate = str(item.get("title", "")).strip()
        if not candidate:
            continue
        score = _title_similarity(title, candidate)
        if score > best_score:
            best_score = score
            best_title = candidate

    if best_score >= 0.86:
        return VerificationResult(
            status="pass",
            detail={
                "backend": "semantic_scholar",
                "reason": "title_match",
                "matched_title": best_title,
                "score": round(best_score, 4),
            },
        )
    return VerificationResult(
        status="fail",
        detail={
            "backend": "semantic_scholar",
            "reason": "no_title_match",
            "best_score": round(best_score, 4),
        },
    )


def _verify_reference_title(source: str) -> VerificationResult:
    backend_results = [_query_crossref(source), _query_arxiv(source), _query_semantic_scholar(source)]
    statuses = [result.status for result in backend_results]
    details = [result.detail for result in backend_results]

    if "pass" in statuses:
        matched = [detail for result, detail in zip(backend_results, details) if result.status == "pass"]
        return VerificationResult(
            status="pass",
            detail={"reason": "reference_exists", "backend_results": details, "matched_backends": matched},
        )

    if "fail" in statuses:
        return VerificationResult(
            status="fail",
            detail={"reason": "reference_not_found", "backend_results": details},
        )

    return VerificationResult(
        status="uncertain",
        detail={"reason": "all_backends_unreachable", "backend_results": details},
    )


def _validate_evidence_item(item: Any, index: int) -> tuple[bool, dict[str, Any]]:
    if not isinstance(item, dict):
        return False, {"index": index, "status": "fail", "reason": "evidence_item_not_object"}

    missing = sorted(REQUIRED_EVIDENCE_FIELDS - set(item.keys()))
    if missing:
        return False, {"index": index, "status": "fail", "reason": "missing_required_fields", "missing": missing}

    source_type = str(item["source_type"])
    if source_type not in VALID_SOURCE_TYPES:
        return False, {
            "index": index,
            "status": "fail",
            "reason": "invalid_source_type",
            "valid_source_types": sorted(VALID_SOURCE_TYPES),
        }

    # paper_text type (internal evidence) skips verification
    if source_type == "paper_text":
        return True, {
            "index": index,
            "status": "skipped",
            "reason": "internal_evidence_no_verification_needed",
            "source_type": source_type,
            "source": str(item["source"]),
            "claim": str(item["claim"]),
            "keywords": [str(k) for k in item["keywords"]],
        }

    keywords = item["keywords"]
    if not isinstance(keywords, list) or not any(str(keyword).strip() for keyword in keywords):
        return False, {"index": index, "status": "fail", "reason": "keywords_must_be_non_empty_array"}
    return True, {}


def handle_instructions() -> None:
    _print_json(
        {
            "ok": True,
            "mode": "instructions",
            "trigger_scope": "after_each_qa_answer_only",
            "required_fields": sorted(REQUIRED_EVIDENCE_FIELDS),
            "rules": {
                "execution_steps": [
                    "Call verify immediately after each QA answer is produced.",
                    "Ensure the QA answer follows the fixed response contract before verification.",
                    "Pass the evidence array exactly as used in the answer.",
                    "Echo the verifier result in the current session before continuing.",
                ],
                "response_contract": [
                    "问题理解",
                    "事实",
                    "证据",
                    "推断",
                    "不确定点",
                    "证据数组",
                    "验证结果",
                ],
                "evidence_item": {
                    "source_type": "web_url | reference_title | paper_text",
                    "source_must_be_verifiable": True,
                    "keywords_min_items": 1,
                    "claim_must_describe_supported_assertion": True,
                    "paper_text_handling": "internal evidence skipped automatically without network verification",
                },
                "invalid_input_failures": [
                    "Evidence item is not an object.",
                    "Missing source_type/source/keywords/claim.",
                    "Unsupported source_type.",
                    "Keywords is empty or contains only blank values.",
                ],
                "verification": {
                    "web_url": "fetch URL and pass when at least one keyword appears in page text",
                    "reference_title": "query Crossref/arXiv/Semantic Scholar and pass when any backend confirms the title",
                    "paper_text": "internal evidence skipped automatically without network verification",
                    "verdict_policy": {
                        "pass": "all evidence items pass (skipped items excluded)",
                        "fail": "any evidence item explicitly fails (excluding skipped)",
                        "uncertain": "no explicit fail but at least one item cannot be verified due to network or backend availability (excluding skipped)",
                    },
                },
                "post_verdict_actions": {
                    "pass": "continue the workflow and keep the same evidence discipline",
                    "fail": "identify the unsupported part, withdraw the unsupported assertion, restate the answer using only verified facts, echo the fixed warning, and constrain subsequent answers to verified facts only",
                    "uncertain": "echo uncertainty explicitly and continue with caution instead of labeling hallucination",
                },
                "fail_repair_sequence": [
                    "Name the unsupported evidence or assertion.",
                    "Withdraw the unsupported claim explicitly.",
                    "Restate the answer using only still-supported facts.",
                    "Echo the fixed hallucination warning in the current session.",
                ],
                "echo_policy": {
                    "must_echo_result_every_time": True,
                    "fail_user_message": FIXED_HALLUCINATION_WARNING,
                    "uncertain_user_message": "当前证据暂无法完成核实，请谨慎参考。",
                    "must_echo_cases": ["pass", "fail", "uncertain"],
                    "result_block_name": "验证结果",
                },
                "caution_points": [
                    "Do not skip verification after a QA answer.",
                    "Do not continue to the next turn before echoing the verifier result.",
                    "Do not treat uncertain as pass.",
                    "Do not keep the failed pre-verification conclusion unchanged after a fail verdict.",
                ],
            },
            "output_contract": {
                "verify_input": {
                    "type": "json_array",
                    "item_required_fields": sorted(REQUIRED_EVIDENCE_FIELDS),
                },
                "verify_response": {
                    "required_fields": ["verdict", "results", "must_echo", "agent_directives", "user_message"],
                    "verdict_values": ["pass", "fail", "uncertain"],
                },
            },
        }
    )


def handle_verify(evidence_json: str) -> None:
    try:
        evidence = json.loads(evidence_json)
    except json.JSONDecodeError as exc:
        _print_json(
            {"ok": False, "mode": "verify", "error": "invalid_evidence_json", "detail": str(exc)},
            code=1,
        )

    if not isinstance(evidence, list):
        _print_json({"ok": False, "mode": "verify", "error": "evidence_must_be_array"}, code=1)

    results: list[dict[str, Any]] = []
    statuses: list[str] = []
    for idx, item in enumerate(evidence):
        valid, invalid_result = _validate_evidence_item(item, idx)
        if not valid:
            result = invalid_result | {
                "source_type": item.get("source_type") if isinstance(item, dict) else None,
                "source": item.get("source") if isinstance(item, dict) else None,
                "claim": item.get("claim") if isinstance(item, dict) else None,
            }
            results.append(result)
            statuses.append("fail")
            continue

        # paper_text type already returned skipped in _validate_evidence_item
        if invalid_result.get("status") == "skipped":
            results.append(invalid_result)
            statuses.append("skipped")
            continue

        source_type = str(item["source_type"])
        source = str(item["source"])
        keywords = [str(keyword) for keyword in item["keywords"]]
        claim = str(item["claim"])

        verification = _verify_web_url(source, keywords) if source_type == "web_url" else _verify_reference_title(source)
        results.append(
            {
                "index": idx,
                "source_type": source_type,
                "source": source,
                "claim": claim,
                "keywords": keywords,
                "status": verification.status,
                **verification.detail,
            }
        )
        statuses.append(verification.status)

    # Determine verdict after excluding skipped items
    verifiable_statuses = [s for s, r in zip(statuses, results) if r.get("status") != "skipped"]

    if not verifiable_statuses:
        verdict = "pass"  # No items requiring verification, default to pass
    elif "fail" in verifiable_statuses:
        verdict = "fail"
    elif "uncertain" in verifiable_statuses:
        verdict = "uncertain"
    else:
        verdict = "pass"

    if verdict == "fail":
        agent_directives = [
            "检测到本轮证据验证未通过：你已产生幻觉风险，后续回答必须仅基于确定事实与可查证来源。",
            f"必须在当前会话中回显用户警告：{FIXED_HALLUCINATION_WARNING}",
        ]
        user_message = FIXED_HALLUCINATION_WARNING
    elif verdict == "uncertain":
        agent_directives = [
            "本轮证据验证结果不确定：必须在当前会话中明确告知用户该不确定性。",
            "不确定结果不等同于幻觉判定，但后续回答应继续收敛到可查证事实。",
        ]
        user_message = "当前证据暂无法完成核实，请谨慎参考。"
    else:
        agent_directives = ["本轮证据验证通过：继续保持可查证来源与关键词约束。"]
        user_message = "证据验证通过。"

    _print_json(
        {
            "ok": True,
            "mode": "verify",
            "verdict": verdict,
            "results": results,
            "must_echo": True,
            "agent_directives": agent_directives,
            "user_message": user_message,
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evidence verifier for literature-explainer.")
    parser.add_argument("--mode", required=True, choices=["instructions", "verify"])
    parser.add_argument("--evidence-json", help="Evidence array JSON for verify mode")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.mode == "instructions":
        handle_instructions()
        return

    if args.mode == "verify":
        if not args.evidence_json:
            _print_json({"ok": False, "mode": "verify", "error": "evidence_json_required"}, code=1)
        handle_verify(args.evidence_json)


if __name__ == "__main__":
    main()

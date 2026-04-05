#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_MEMORY_DIR = ".memory"
DEFAULT_MEMORY_FILE = ""
MEMORY_FILE_SUFFIX = ".memory.jsonl"
SCHEMA_VERSION = 3
VALID_INSTRUCTION_STAGES = {"initial_analysis", "qa", "note"}
VALID_UPDATE_STAGES = {"initial_analysis", "qa"}
VALID_SOURCE_TYPES = {"web_url", "reference_title", "paper_text"}
QA_THRESHOLD = 1200
QA_SUMMARY_MIN = 900
QA_SUMMARY_MAX = 1200

BASE_REQUIRED_FIELDS = {"stage", "paper_key", "session_key"}
STAGE_REQUIRED_FIELDS = {
    "initial_analysis": {"analysis_tldr", "analysis_outline", "section_summaries"},
    "qa": {"user_question", "agent_answer_summary", "answer_original_length", "evidence_items"},
}
NOTE_INSTRUCTION_REQUIRED_FIELDS = ["paper_key", "session_key"]


def _print_json(data: dict[str, Any], exit_code: int = 0) -> None:
    print(json.dumps(data, ensure_ascii=False))
    raise SystemExit(exit_code)


def _memory_dir_path(memory_dir: str) -> Path:
    return Path.cwd() / memory_dir


def _default_memory_file_name(paper_key: str) -> str:
    return f"{paper_key}{MEMORY_FILE_SUFFIX}"


def _resolve_memory_path(memory_dir: str, memory_file: str, paper_key: str = "") -> Path:
    if memory_file:
        return _memory_dir_path(memory_dir) / memory_file
    if not paper_key.strip():
        _print_json({"ok": False, "error": "paper_key_required_for_default_memory_path"}, exit_code=1)
    return _memory_dir_path(memory_dir) / _default_memory_file_name(paper_key)


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for idx, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                item = json.loads(text)
            except json.JSONDecodeError as exc:
                _print_json(
                    {
                        "ok": False,
                        "error": "invalid_jsonl_line",
                        "line": idx,
                        "detail": str(exc),
                    },
                    exit_code=1,
                )
            if isinstance(item, dict):
                entries.append(item)
    return entries


def _coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if value is None:
        return []
    return [str(value)]


def _coerce_section_summaries(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        _print_json({"ok": False, "error": "section_summaries_must_be_array"}, exit_code=1)

    sections: list[dict[str, Any]] = []
    for idx, item in enumerate(value):
        if isinstance(item, dict):
            title = str(item.get("title", "")).strip() or f"section-{idx + 1}"
            bullets = _coerce_str_list(item.get("bullets", []))
            if not bullets:
                _print_json(
                    {
                        "ok": False,
                        "error": "section_summary_bullets_required",
                        "index": idx,
                    },
                    exit_code=1,
                )
            sections.append({"title": title, "bullets": bullets})
            continue

        if isinstance(item, str):
            sections.append({"title": f"section-{idx + 1}", "bullets": [item]})
            continue

        _print_json(
            {
                "ok": False,
                "error": "invalid_section_summary_item",
                "index": idx,
            },
            exit_code=1,
        )
    return sections


def _coerce_keywords(value: Any, evidence_index: int) -> list[str]:
    if not isinstance(value, list) or not value:
        _print_json(
            {
                "ok": False,
                "error": "evidence_keywords_must_be_non_empty_array",
                "index": evidence_index,
            },
            exit_code=1,
        )

    keywords: list[str] = []
    for keyword_index, keyword in enumerate(value):
        text = str(keyword)
        if not text.strip():
            _print_json(
                {
                    "ok": False,
                    "error": "evidence_keyword_must_be_non_empty",
                    "index": evidence_index,
                    "keyword_index": keyword_index,
                },
                exit_code=1,
            )
        keywords.append(text)
    return keywords


def _coerce_evidence_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        _print_json({"ok": False, "error": "evidence_items_must_be_non_empty_array"}, exit_code=1)

    evidence_items: list[dict[str, Any]] = []
    for idx, item in enumerate(value):
        if not isinstance(item, dict):
            _print_json({"ok": False, "error": "invalid_evidence_item", "index": idx}, exit_code=1)

        source_type = str(item.get("source_type", ""))
        if source_type not in VALID_SOURCE_TYPES:
            _print_json(
                {
                    "ok": False,
                    "error": "invalid_evidence_source_type",
                    "index": idx,
                    "valid_source_types": sorted(VALID_SOURCE_TYPES),
                },
                exit_code=1,
            )

        source = str(item.get("source", ""))
        if not source.strip():
            _print_json({"ok": False, "error": "evidence_source_must_be_non_empty", "index": idx}, exit_code=1)

        claim = str(item.get("claim", ""))
        if not claim.strip():
            _print_json({"ok": False, "error": "evidence_claim_must_be_non_empty", "index": idx}, exit_code=1)

        evidence_items.append(
            {
                "source_type": source_type,
                "source": source,
                "keywords": _coerce_keywords(item.get("keywords"), idx),
                "claim": claim,
            }
        )
    return evidence_items


def _required_fields_for_stage(stage: str) -> list[str]:
    return sorted(BASE_REQUIRED_FIELDS | STAGE_REQUIRED_FIELDS[stage])


def _instruction_specs() -> dict[str, dict[str, Any]]:
    return {
        "initial_analysis": {
            "required_fields": _required_fields_for_stage("initial_analysis"),
            "rules": {
                "execution_steps": [
                    "Read and understand the paper before calling update.",
                    "Call instructions for initial_analysis first.",
                    "Build a complete initial-analysis payload.",
                    "Call update only after the first paper-level understanding is stable.",
                ],
                "summary_generation": {
                    "must_capture_complete_initial_understanding": True,
                    "must_not_second_compress_before_write": True,
                },
                "analysis_template": {
                    "core_blocks": [
                        "TL;DR",
                        "研究问题与贡献",
                        "方法要点",
                        "关键结果",
                        "局限与可复现性线索",
                        "分章节总结",
                    ],
                    "tldr_recommended_lines": "8-15",
                    "section_summary_mode": "dynamic_by_actual_paper_sections",
                },
                "caution_points": [
                    "Do not write a fragmentary analysis record when the paper understanding is still incomplete.",
                    "Do not reduce the initial analysis to only the paper abstract.",
                ],
                "failure_conditions": [
                    "Missing required initial-analysis fields.",
                    "Empty analysis_tldr or analysis_outline.",
                    "Invalid section_summaries structure.",
                ],
                "do_not_continue_when": [
                    "The paper cannot be read reliably.",
                    "The available paper content is too incomplete to form a stable first-pass understanding.",
                ],
            },
            "output_contract": {
                "update_payload": {
                    "stage": "initial_analysis",
                    "required_fields": _required_fields_for_stage("initial_analysis"),
                    "optional_fields": ["evidence_refs", "open_questions", "next_actions"],
                },
                "written_record": {
                    "schema_version": SCHEMA_VERSION,
                    "stage": "initial_analysis",
                    "preserves": ["analysis_tldr", "analysis_outline", "section_summaries"],
                },
            },
        },
        "qa": {
            "required_fields": _required_fields_for_stage("qa"),
            "rules": {
                "execution_steps": [
                    "Split multi-question input before answering when the user turn contains multiple sub-questions.",
                    "Answer the user question with the fixed QA response contract and complete verifier echo first.",
                    "Call instructions for qa before preparing the memory payload.",
                    "Preserve the full user question and build the answer summary according to the length policy.",
                    "Write the QA memory record only after the answer, verifier echo, and evidence set are finalized for this turn.",
                ],
                "qa_response_contract": [
                    "问题理解",
                    "事实",
                    "证据",
                    "推断",
                    "不确定点",
                    "证据数组",
                    "验证结果",
                ],
                "multi_question_handling": {
                    "split_before_answer": True,
                    "answer_in_declared_order_when_clear": True,
                    "ask_user_to_narrow_scope_when_needed": True,
                },
                "clarification_policy": {
                    "ask_one_most_critical_question_only": True,
                    "answer_confirmed_part_before_clarification_when_possible": True,
                    "no_repeated_clarification_only_turns": True,
                },
                "question_storage": "store_full_user_question",
                "answer_summary_policy": {
                    "threshold": QA_THRESHOLD,
                    "below_threshold": "raw_below_threshold",
                    "above_threshold": "summarized_900_1200",
                    "summary_target_range": [QA_SUMMARY_MIN, QA_SUMMARY_MAX],
                },
                "evidence_storage": {
                    "require_evidence_items": True,
                    "keep_source_verbatim": True,
                    "keep_original_order": True,
                },
                "write_prerequisites": {
                    "verifier_must_run": True,
                    "verifier_echo_must_be_completed": True,
                    "memory_must_capture_final_post_verification_turn": True,
                },
                "fail_repair_storage": {
                    "store_repaired_answer_only": True,
                    "do_not_store_pre_repair_summary": True,
                },
                "caution_points": [
                    "Do not compress or rewrite the user question.",
                    "Do not rewrite evidence source text before storing it.",
                    "Do not write the memory record before the QA turn is complete.",
                    "Do not store the pre-repair answer when verification has failed and a repaired answer exists.",
                ],
                "failure_conditions": [
                    "Missing qa required fields.",
                    "Answer summary length violates the configured policy.",
                    "Evidence items are missing or malformed.",
                    "QA memory write attempted before verifier echo is complete.",
                ],
                "do_not_continue_when": [
                    "The user question is still ambiguous and has not been clarified.",
                    "The evidence set for the current answer is not finalized.",
                    "The verification result has not been echoed yet.",
                ],
            },
            "output_contract": {
                "update_payload": {
                    "stage": "qa",
                    "required_fields": _required_fields_for_stage("qa"),
                    "optional_fields": ["evidence_refs", "open_questions", "next_actions"],
                },
                "written_record": {
                    "schema_version": SCHEMA_VERSION,
                    "stage": "qa",
                    "required_fields": [
                        "user_question",
                        "agent_answer_summary",
                        "answer_original_length",
                        "summary_policy",
                        "evidence_items",
                    ],
                },
            },
        },
        "note": {
            "required_fields": NOTE_INSTRUCTION_REQUIRED_FIELDS,
            "rules": {
                "execution_steps": [
                    "Only enter note generation after the user explicitly requests it.",
                    "Call instructions for note first.",
                    "Call read and use structured memory records as the only source material.",
                    "Generate the final Markdown note in the fixed section order.",
                ],
                "note_optional": True,
                "read_policy": {
                    "default_schema_filter": SCHEMA_VERSION,
                    "ignore_legacy_by_default": True,
                    "analysis_scope": "paper_global",
                    "qa_scope": "current_session_only",
                    "ignore_note_stage_records": True,
                },
                "note_generation": {
                    "consume_memory_directly": True,
                    "use_raw_answer_text": False,
                    "no_second_compression": True,
                    "allow_minor_polish_only": True,
                    "paper_summary_shape": "one_expanded_paragraph",
                    "section_order": [
                        "论文摘要",
                        "问答摘要",
                        "未解决问题",
                        "后续行动",
                    ],
                    "qa_evidence_rendering": "list_source_verbatim_per_item",
                    "qa_block_shape": [
                        "用户问题",
                        "回答要点",
                        "证据原文",
                        "未解决点/后续动作",
                    ],
                    "persist_note_to_file_only": True,
                },
                "caution_points": [
                    "Do not enter note generation without explicit user consent.",
                    "Do not use raw answer text as a fallback source.",
                    "Do not expand the paper summary into a multi-section recap.",
                    "Do not write note content back into memory records.",
                ],
                "failure_conditions": [
                    "Structured memory records are unavailable or insufficient.",
                    "The final note does not follow the fixed section order.",
                ],
                "do_not_continue_when": [
                    "The user has not explicitly asked for note generation.",
                    "The available memory records are too incomplete to produce a reliable note.",
                ],
            },
                "output_contract": {
                "read_response": {
                    "returns_raw_entries": True,
                    "filters": ["paper_key", "session_key", "limit", "include_legacy"],
                },
                "note_expectation": {
                    "must_use_memory_records_as_source": True,
                    "must_keep_qa_evidence_sources_verbatim": True,
                    "paper_summary_must_be_one_paragraph": True,
                    "final_note_memory_writeback": False,
                },
            },
        },
    }


def handle_instructions(args: argparse.Namespace) -> None:
    if args.stage not in VALID_INSTRUCTION_STAGES:
        _print_json(
            {
                "ok": False,
                "error": "invalid_stage",
                "valid_stages": sorted(VALID_INSTRUCTION_STAGES),
            },
            exit_code=1,
        )
    spec = _instruction_specs()[args.stage]
    _print_json(
        {
            "ok": True,
            "mode": "instructions",
            "stage": args.stage,
            "required_fields": spec["required_fields"],
            "rules": spec["rules"],
            "output_contract": spec["output_contract"],
        }
    )


def _validate_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        _print_json({"ok": False, "error": "payload_must_be_object"}, exit_code=1)

    stage = str(payload.get("stage", ""))
    if stage not in VALID_UPDATE_STAGES:
        _print_json(
            {
                "ok": False,
                "error": "invalid_stage",
                "valid_stages": sorted(VALID_UPDATE_STAGES),
            },
            exit_code=1,
        )

    required = set(_required_fields_for_stage(stage))
    missing = sorted(required - set(payload.keys()))
    if missing:
        _print_json(
            {
                "ok": False,
                "error": "missing_required_fields",
                "missing": missing,
            },
            exit_code=1,
        )
    return payload


def _build_stage_entry(payload: dict[str, Any]) -> dict[str, Any]:
    stage = str(payload["stage"])
    base_entry = {
        "id": str(uuid.uuid4()),
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "schema_version": SCHEMA_VERSION,
        "stage": stage,
        "paper_key": str(payload["paper_key"]),
        "session_key": str(payload["session_key"]),
    }

    if stage == "initial_analysis":
        outline = _coerce_str_list(payload["analysis_outline"])
        if not outline:
            _print_json({"ok": False, "error": "analysis_outline_must_be_non_empty_array"}, exit_code=1)
        tldr = str(payload["analysis_tldr"]).strip()
        if not tldr:
            _print_json({"ok": False, "error": "analysis_tldr_must_be_non_empty"}, exit_code=1)
        return base_entry | {
            "analysis_tldr": tldr,
            "analysis_outline": outline,
            "section_summaries": _coerce_section_summaries(payload["section_summaries"]),
            "evidence_refs": _coerce_str_list(payload.get("evidence_refs")),
            "open_questions": _coerce_str_list(payload.get("open_questions")),
            "next_actions": _coerce_str_list(payload.get("next_actions")),
        }

    if stage == "qa":
        user_question = str(payload["user_question"])
        if not user_question.strip():
            _print_json({"ok": False, "error": "user_question_must_be_non_empty"}, exit_code=1)

        answer_summary = str(payload["agent_answer_summary"])
        if not answer_summary.strip():
            _print_json({"ok": False, "error": "agent_answer_summary_must_be_non_empty"}, exit_code=1)

        try:
            answer_original_length = int(payload["answer_original_length"])
        except (TypeError, ValueError):
            _print_json({"ok": False, "error": "answer_original_length_must_be_int"}, exit_code=1)

        if answer_original_length < 0:
            _print_json({"ok": False, "error": "answer_original_length_must_be_non_negative"}, exit_code=1)

        summary_len = len(answer_summary)
        if answer_original_length <= QA_THRESHOLD:
            if summary_len > QA_THRESHOLD:
                _print_json(
                    {
                        "ok": False,
                        "error": "raw_below_threshold_summary_too_long",
                        "summary_length": summary_len,
                    },
                    exit_code=1,
                )
            summary_policy = "raw_below_threshold"
        else:
            if not (QA_SUMMARY_MIN <= summary_len <= QA_SUMMARY_MAX):
                _print_json(
                    {
                        "ok": False,
                        "error": "summarized_answer_length_out_of_range",
                        "required_range": [QA_SUMMARY_MIN, QA_SUMMARY_MAX],
                        "summary_length": summary_len,
                    },
                    exit_code=1,
                )
            summary_policy = "summarized_900_1200"

        return base_entry | {
            "user_question": user_question,
            "agent_answer_summary": answer_summary,
            "answer_original_length": answer_original_length,
            "summary_policy": summary_policy,
            "evidence_items": _coerce_evidence_items(payload["evidence_items"]),
            "evidence_refs": _coerce_str_list(payload.get("evidence_refs")),
            "open_questions": _coerce_str_list(payload.get("open_questions")),
            "next_actions": _coerce_str_list(payload.get("next_actions")),
        }

    _print_json({"ok": False, "error": "unsupported_stage_for_update", "stage": stage}, exit_code=1)
    raise RuntimeError("unreachable")


def handle_update(args: argparse.Namespace) -> None:
    try:
        payload = json.loads(args.payload_json)
    except json.JSONDecodeError as exc:
        _print_json(
            {"ok": False, "error": "invalid_payload_json", "detail": str(exc)},
            exit_code=1,
        )

    payload_obj = _validate_payload(payload)
    paper_key = str(payload_obj["paper_key"])
    memory_path = _resolve_memory_path(args.memory_dir, args.memory_file, paper_key=paper_key)
    _ensure_parent(memory_path)
    entry = _build_stage_entry(payload_obj)

    existing_entries = _read_jsonl(memory_path)
    existing_entries.append(entry)

    with memory_path.open("w", encoding="utf-8") as handle:
        for item in existing_entries:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    _print_json({"ok": True, "mode": "update", "path": str(memory_path), "entry": entry})


def handle_read(args: argparse.Namespace) -> None:
    if args.memory_file:
        memory_path = _resolve_memory_path(args.memory_dir, args.memory_file)
        entries = _read_jsonl(memory_path)
    elif args.paper_key:
        memory_path = _resolve_memory_path(args.memory_dir, "", paper_key=args.paper_key)
        entries = _read_jsonl(memory_path)
    else:
        memory_root = _memory_dir_path(args.memory_dir)
        memory_path = memory_root
        entries = []
        if memory_root.exists():
            for path in sorted(memory_root.glob(f"*{MEMORY_FILE_SUFFIX}")):
                entries.extend(_read_jsonl(path))

    if not args.include_legacy:
        entries = [entry for entry in entries if int(entry.get("schema_version", -1)) == SCHEMA_VERSION]
    if args.paper_key and args.session_key:
        entries = [
            entry
            for entry in entries
            if str(entry.get("paper_key")) == args.paper_key
            and (
                str(entry.get("stage")) in {"initial_analysis"}
                or str(entry.get("session_key")) == args.session_key
            )
        ]
    else:
        if args.paper_key:
            entries = [entry for entry in entries if str(entry.get("paper_key")) == args.paper_key]
        if args.session_key:
            entries = [entry for entry in entries if str(entry.get("session_key")) == args.session_key]

    entries = [entry for entry in entries if str(entry.get("stage")) in {"initial_analysis", "qa"}]

    if args.limit is not None and args.limit >= 0:
        entries = entries[-args.limit :] if args.limit > 0 else []

    _print_json(
        {
            "ok": True,
            "mode": "read",
            "path": str(memory_path),
            "schema_version_filter": None if args.include_legacy else SCHEMA_VERSION,
            "count": len(entries),
            "entries": entries,
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Memory engine for literature-explainer.")
    parser.add_argument("--mode", required=True, choices=["instructions", "update", "read"], help="Execution mode")
    parser.add_argument("--memory-dir", default=DEFAULT_MEMORY_DIR, help="Memory directory relative to current working directory.")
    parser.add_argument("--memory-file", default=DEFAULT_MEMORY_FILE, help="Explicit memory JSONL file name. When omitted, defaults to the active paper-specific file.")
    parser.add_argument("--stage", help="Stage for instructions mode.")
    parser.add_argument("--payload-json", help="JSON object payload for update mode.")
    parser.add_argument("--paper-key", help="Filter by paper key in read mode.")
    parser.add_argument("--session-key", help="Filter by session key in read mode.")
    parser.add_argument("--limit", type=int, help="Limit number of read results.")
    parser.add_argument("--include-legacy", action="store_true", help="Include non-v3 legacy records in read mode.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.mode == "instructions":
        if not args.stage:
            _print_json({"ok": False, "error": "stage_required_for_instructions"}, exit_code=1)
        handle_instructions(args)
        return

    if args.mode == "update":
        if not args.payload_json:
            _print_json({"ok": False, "error": "payload_json_required_for_update"}, exit_code=1)
        handle_update(args)
        return

    if args.mode == "read":
        handle_read(args)
        return

    _print_json({"ok": False, "error": "unsupported_mode"}, exit_code=1)


if __name__ == "__main__":
    main()

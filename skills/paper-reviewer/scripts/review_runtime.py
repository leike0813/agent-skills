#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
RUNS_DIRNAME = ".paper-reviewer-runs"
MANIFEST_FILENAME = "manifest.json"
MEMORY_FILENAME = "memory.jsonl"
REPORT_FILENAME = "review-report.md"

STAGES = [
    "S0_INIT",
    "S1_PROFILE_AND_SCOPE",
    "S2_DEEP_UNDERSTANDING",
    "S3_MACRO_REVIEW",
    "S4_MICRO_REVIEW",
    "S5_FORMAL_REVIEW",
    "S6_SYNTHESIS_CONFIRMATION",
    "S7_REPORT_EXPORT",
    "S8_DONE",
]

SEVERITIES = {"major", "minor", "note"}
CONFIDENCES = {"high", "medium", "low"}
FINDING_STATUSES = {"candidate", "confirmed", "dismissed"}
RECORD_TYPES = {"paper_profile", "section_map", "stage_summary", "finding", "decision", "open_question"}
DECISION_TYPES = {"domain_confirmation", "scope_confirmation", "report_export_confirmation"}
FINDING_STAGES = {"S3_MACRO_REVIEW", "S4_MICRO_REVIEW", "S5_FORMAL_REVIEW"}
QUESTION_STAGES = {
    "S1_PROFILE_AND_SCOPE",
    "S2_DEEP_UNDERSTANDING",
    "S3_MACRO_REVIEW",
    "S4_MICRO_REVIEW",
    "S5_FORMAL_REVIEW",
    "S6_SYNTHESIS_CONFIRMATION",
}

FINDING_REQUIRED_FIELDS = {
    "finding_id",
    "stage",
    "paper_section",
    "severity",
    "issue_type",
    "location",
    "claim",
    "paper_evidence",
    "impact",
    "suggested_revision",
    "confidence",
    "status",
}

STAGE_INSTRUCTIONS = {
    "S0_INIT": {
        "purpose": "初始化运行态，记录 source metadata、paper_key 和 run_id，不做审稿判断。",
        "agent_work": [
            "确认用户提供的 source_path 可访问。",
            "运行 init 创建工作区。",
            "把返回的 run_root 作为后续所有 runtime 命令输入。",
        ],
        "memory": "本阶段只写 manifest，不写审稿发现。",
    },
    "S1_PROFILE_AND_SCOPE": {
        "purpose": "建立论文画像并完成关键确认。",
        "agent_work": [
            "初读论文，提取标题、摘要、章节结构、研究对象、方法类型和证据类型。",
            "基于论文内容和 taxonomy 初判领域；必要时调用 reference_guide.py list 辅助选择 canonical domain name。",
            "向用户确认领域分类、审稿范围和是否审全篇。",
        ],
        "memory": "写入 paper_profile 或 section_map；写入 domain_confirmation 和 scope_confirmation decision。",
    },
    "S2_DEEP_UNDERSTANDING": {
        "purpose": "形成可执行理解，避免在理解不足时直接审稿。",
        "agent_work": [
            "记录研究问题、贡献主张、方法/材料/数据、关键结果、局限和章节功能。",
            "识别后续审稿需要重点检查的证据链。",
            "不要生成最终审稿报告。",
        ],
        "memory": "写入 stage_summary，必要时补充 paper_profile 或 open_question。",
    },
    "S3_MACRO_REVIEW": {
        "purpose": "审阅标题、摘要、研究问题、贡献、结构和整体证据路线。",
        "agent_work": [
            "每个检查对象先调用 reference_guide.py nav --review-stage macro，并仅在必要时用 show 披露具体 heading 原文。",
            "只记录能回到论文材料的问题。",
            "形成 major candidate findings，但不导出最终报告。",
        ],
        "memory": "写入 finding 和 stage_summary。",
    },
    "S4_MICRO_REVIEW": {
        "purpose": "按章节或指定范围审阅逻辑、方法、证据、结果解释和结论强度。",
        "agent_work": [
            "对每个章节 pass 调用 reference_guide.py nav --review-stage micro --paper-section <section>，并仅在必要时用 show 披露具体 heading 原文。",
            "定位具体段落、图表、公式或实验设置。",
            "避免把本阶段扩展为形式规范检查。",
        ],
        "memory": "写入 finding 和 stage_summary。",
    },
    "S5_FORMAL_REVIEW": {
        "purpose": "审阅语言、冗余、图表引用、参考文献、伦理/合规和可复现性线索。",
        "agent_work": [
            "调用 reference_guide.py nav --review-stage formal --paper-section <section>，并仅在必要时用 show 披露具体 heading 原文。",
            "只记录论文材料中可定位的形式或规范问题。",
            "不做联网参考文献核验，除非后续能力明确支持。",
        ],
        "memory": "写入 finding、open_question 和 stage_summary。",
    },
    "S6_SYNTHESIS_CONFIRMATION": {
        "purpose": "综合 findings，并在最终报告前获得用户确认。",
        "agent_work": [
            "汇总 major/minor/note findings、疑似问题和待补充信息。",
            "询问用户是否按当前发现生成最终报告，或是否继续补审某部分。",
        ],
        "memory": "写入 stage_summary；获得确认后写入 report_export_confirmation decision。",
    },
    "S7_REPORT_EXPORT": {
        "purpose": "从结构化记忆生成审稿报告草稿。",
        "agent_work": [
            "运行 export。",
            "只消费 confirmed findings 和保留的 candidate findings。",
            "不要回读长参考文档拼接报告。",
        ],
        "memory": "export 写入 artifacts/review-report.md 并把 manifest 推进到 S8_DONE。",
    },
    "S8_DONE": {
        "purpose": "运行结束。",
        "agent_work": [
            "报告 review-report.md 路径。",
            "不主动推进新审阅；如需补审，应开启新的运行或明确回到相应阶段。",
        ],
        "memory": "不需要新增记录。",
    },
}

RECORD_TEMPLATES: dict[str, dict[str, Any]] = {
    "paper_profile": {
        "record_type": "paper_profile",
        "title": "Paper title",
        "abstract": "Concise abstract summary; do not store the whole manuscript.",
        "sections": ["Abstract", "Introduction", "Methods", "Results", "Discussion"],
        "research_question": "What the paper tries to answer.",
        "contribution_claims": ["Claim 1", "Claim 2"],
        "method_summary": "Method, data, material, proof, or argument structure.",
        "evidence_type": "experimental results",
    },
    "section_map": {
        "record_type": "section_map",
        "sections": [
            {"section_id": "introduction", "title": "Introduction", "location": "Section 1"},
            {"section_id": "method", "title": "Methods", "location": "Section 2"},
        ],
    },
    "stage_summary": {
        "record_type": "stage_summary",
        "stage": "S3_MACRO_REVIEW",
        "summary": "What was checked and what remains uncertain.",
        "completed_checks": ["title", "abstract", "structure"],
    },
    "finding": {
        "record_type": "finding",
        "finding_id": "F-S3-001",
        "stage": "S3_MACRO_REVIEW",
        "paper_section": "abstract",
        "severity": "major",
        "issue_type": "contribution_overclaim",
        "location": "Abstract, final sentence",
        "claim": "One specific review issue.",
        "paper_evidence": "Evidence from the manuscript, not from the reference guide.",
        "impact": "Why this matters for validity, clarity, or reader judgement.",
        "suggested_revision": "Concrete revision direction.",
        "confidence": "high",
        "status": "candidate",
    },
    "decision": {
        "record_type": "decision",
        "decision_type": "scope_confirmation",
        "value": "Full manuscript review with extra attention to methods and results.",
        "rationale": "User confirmed this scope.",
    },
    "open_question": {
        "record_type": "open_question",
        "question_id": "Q-S2-001",
        "stage": "S2_DEEP_UNDERSTANDING",
        "question": "A concrete ambiguity that blocks confident review judgement.",
        "status": "open",
    },
}


class RuntimeErrorWithPayload(Exception):
    def __init__(self, message: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.payload = payload or {}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def fail(message: str, **payload: Any) -> None:
    raise RuntimeErrorWithPayload(message, payload)


def slugify(text: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-._").lower()
    return stem[:48] or "paper"


def source_hash(source_path: Path) -> str:
    return "sha256:" + hashlib.sha256(source_path.read_bytes()).hexdigest()


def paper_key_for(source_path: Path, input_hash: str) -> str:
    return f"{slugify(source_path.stem)}-{input_hash.split(':', 1)[1][:12]}"


def run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def manifest_path(run_root: Path) -> Path:
    return run_root / MANIFEST_FILENAME


def memory_path(run_root: Path) -> Path:
    return run_root / MEMORY_FILENAME


def artifacts_dir(run_root: Path) -> Path:
    return run_root / "artifacts"


def report_path(run_root: Path) -> Path:
    return artifacts_dir(run_root) / REPORT_FILENAME


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        fail(f"missing file: {path}")
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {path}: {exc}")
    if not isinstance(data, dict):
        fail(f"JSON root must be object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_manifest(run_root: Path) -> dict[str, Any]:
    data = read_json(manifest_path(run_root))
    if data.get("schema_version") != SCHEMA_VERSION:
        fail("unsupported manifest schema_version", expected=SCHEMA_VERSION, actual=data.get("schema_version"))
    return data


def save_manifest(run_root: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = utc_now()
    write_json(manifest_path(run_root), manifest)


def read_memory(run_root: Path) -> list[dict[str, Any]]:
    path = memory_path(run_root)
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            fail("invalid memory JSONL line", line=line_number, detail=str(exc))
        if isinstance(item, dict):
            entries.append(item)
    return entries


def write_memory(run_root: Path, entries: list[dict[str, Any]]) -> None:
    text = "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries)
    memory_path(run_root).write_text(text, encoding="utf-8")


def upsert_memory(run_root: Path, entry: dict[str, Any]) -> None:
    entries = read_memory(run_root)
    record_id = str(entry["record_id"])
    entries = [item for item in entries if str(item.get("record_id")) != record_id]
    entries.append(entry)
    write_memory(run_root, entries)


def require_non_empty_str(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        fail("missing or empty required string field", field=field)
    return value.strip()


def require_list(payload: dict[str, Any], field: str) -> list[Any]:
    value = payload.get(field)
    if not isinstance(value, list) or not value:
        fail("missing or empty required array field", field=field)
    return value


def require_stage(value: str) -> str:
    if value not in STAGES:
        fail("invalid stage", stage=value, valid_stages=STAGES)
    return value


def base_entry(record_type: str, record_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": record_type,
        "record_id": record_id,
        "created_at": str(payload.get("created_at") or utc_now()),
        "updated_at": utc_now(),
        "data": payload,
    }


def validate_paper_profile(payload: dict[str, Any]) -> dict[str, Any]:
    title = require_non_empty_str(payload, "title")
    require_list(payload, "sections")
    for optional in ("abstract", "research_question", "contribution_claims", "method_summary", "evidence_type"):
        if optional in payload and not isinstance(payload[optional], (str, list)):
            fail("invalid paper_profile field", field=optional)
    return base_entry("paper_profile", "paper_profile", payload | {"title": title})


def validate_section_map(payload: dict[str, Any]) -> dict[str, Any]:
    sections = require_list(payload, "sections")
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            fail("section_map sections must contain objects", index=index)
        for field in ("section_id", "title"):
            value = section.get(field)
            if not isinstance(value, str) or not value.strip():
                fail("section_map section missing required field", index=index, field=field)
    return base_entry("section_map", "section_map", payload)


def validate_stage_summary(payload: dict[str, Any]) -> dict[str, Any]:
    stage = require_stage(require_non_empty_str(payload, "stage"))
    require_non_empty_str(payload, "summary")
    if "completed_checks" in payload and not isinstance(payload["completed_checks"], list):
        fail("completed_checks must be an array")
    return base_entry("stage_summary", f"stage_summary:{stage}", payload | {"stage": stage})


def validate_finding(payload: dict[str, Any]) -> dict[str, Any]:
    missing = sorted(field for field in FINDING_REQUIRED_FIELDS if field not in payload)
    if missing:
        fail("finding missing required fields", missing=missing)
    finding_id = require_non_empty_str(payload, "finding_id")
    stage = require_stage(require_non_empty_str(payload, "stage"))
    severity = require_non_empty_str(payload, "severity")
    confidence = require_non_empty_str(payload, "confidence")
    status = require_non_empty_str(payload, "status")
    if severity not in SEVERITIES:
        fail("invalid severity", severity=severity, valid=sorted(SEVERITIES))
    if confidence not in CONFIDENCES:
        fail("invalid confidence", confidence=confidence, valid=sorted(CONFIDENCES))
    if status not in FINDING_STATUSES:
        fail("invalid finding status", status=status, valid=sorted(FINDING_STATUSES))
    for field in (
        "paper_section",
        "issue_type",
        "location",
        "claim",
        "impact",
        "suggested_revision",
    ):
        require_non_empty_str(payload, field)
    evidence = payload.get("paper_evidence")
    if isinstance(evidence, str):
        if not evidence.strip():
            fail("paper_evidence must be non-empty")
    elif isinstance(evidence, list):
        if not evidence or not all(str(item).strip() for item in evidence):
            fail("paper_evidence list must contain non-empty items")
    else:
        fail("paper_evidence must be string or array")
    return base_entry("finding", finding_id, payload | {"stage": stage, "severity": severity, "confidence": confidence, "status": status})


def validate_decision(payload: dict[str, Any]) -> dict[str, Any]:
    decision_type = require_non_empty_str(payload, "decision_type")
    if decision_type not in DECISION_TYPES:
        fail("invalid decision_type", decision_type=decision_type, valid=sorted(DECISION_TYPES))
    value = payload.get("value")
    if value in (None, ""):
        fail("decision value is required")
    decision_id = str(payload.get("decision_id") or f"decision:{decision_type}")
    return base_entry("decision", decision_id, payload | {"decision_id": decision_id})


def validate_open_question(payload: dict[str, Any]) -> dict[str, Any]:
    question_id = require_non_empty_str(payload, "question_id")
    stage = require_stage(require_non_empty_str(payload, "stage"))
    require_non_empty_str(payload, "question")
    if "status" in payload and payload["status"] not in {"open", "answered", "dismissed"}:
        fail("invalid open_question status", status=payload["status"])
    payload.setdefault("status", "open")
    return base_entry("open_question", question_id, payload | {"stage": stage})


def validate_record(payload: dict[str, Any]) -> dict[str, Any]:
    record_type = require_non_empty_str(payload, "record_type")
    if record_type not in RECORD_TYPES:
        fail("invalid record_type", record_type=record_type, valid=sorted(RECORD_TYPES))
    data = dict(payload)
    data.pop("record_type", None)
    validators = {
        "paper_profile": validate_paper_profile,
        "section_map": validate_section_map,
        "stage_summary": validate_stage_summary,
        "finding": validate_finding,
        "decision": validate_decision,
        "open_question": validate_open_question,
    }
    return validators[record_type](data)


def validate_record_allowed_for_manifest(entry: dict[str, Any], manifest: dict[str, Any]) -> None:
    data = entry.get("data", {})
    current_stage = require_stage(str(manifest.get("current_stage")))
    record_type = str(entry.get("record_type"))
    stage_value = data.get("stage")
    if isinstance(stage_value, str) and stage_value:
        stage = require_stage(stage_value)
        if STAGES.index(stage) > STAGES.index(current_stage):
            fail("cannot write record for a future stage", current_stage=current_stage, requested_stage=stage)
    if record_type == "finding":
        stage = str(data.get("stage", ""))
        if stage not in FINDING_STAGES:
            fail("finding stage must be a review stage", stage=stage, valid=sorted(FINDING_STAGES))
    elif record_type == "open_question":
        stage = str(data.get("stage", ""))
        if stage not in QUESTION_STAGES:
            fail("open_question stage is not allowed", stage=stage, valid=sorted(QUESTION_STAGES))


def next_stage(stage: str) -> str:
    index = STAGES.index(stage)
    return STAGES[min(index + 1, len(STAGES) - 1)]


def mark_stage_complete(manifest: dict[str, Any], stage: str) -> None:
    completed = list(manifest.get("completed_stages", []))
    if stage not in completed:
        completed.append(stage)
    manifest["completed_stages"] = completed
    if stage == "S1_PROFILE_AND_SCOPE" and manifest.get("pending_confirmations"):
        manifest["current_stage"] = "S1_PROFILE_AND_SCOPE"
        return
    if stage == "S6_SYNTHESIS_CONFIRMATION" and manifest.get("pending_confirmations"):
        manifest["current_stage"] = "S6_SYNTHESIS_CONFIRMATION"
        return
    if stage in STAGES and STAGES.index(stage) >= STAGES.index(str(manifest.get("current_stage"))):
        manifest["current_stage"] = next_stage(stage)
    if stage == "S5_FORMAL_REVIEW":
        pending = list(manifest.get("pending_confirmations", []))
        if "report_export_confirmation" not in pending:
            pending.append("report_export_confirmation")
        manifest["pending_confirmations"] = pending
        manifest["current_stage"] = "S6_SYNTHESIS_CONFIRMATION"


def apply_decision(manifest: dict[str, Any], payload: dict[str, Any]) -> None:
    decision_type = str(payload.get("decision_type"))
    value = payload.get("value")
    pending = list(manifest.get("pending_confirmations", []))
    if decision_type == "domain_confirmation":
        manifest["confirmed_domain"] = value
        pending = [item for item in pending if item != "domain_confirmation"]
    elif decision_type == "scope_confirmation":
        manifest["confirmed_scope"] = value
        pending = [item for item in pending if item != "scope_confirmation"]
    elif decision_type == "report_export_confirmation":
        if value is True or str(value).lower() in {"true", "yes", "confirmed", "confirm"}:
            manifest["report_export_confirmed"] = True
            pending = [item for item in pending if item != "report_export_confirmation"]
            if manifest.get("current_stage") == "S6_SYNTHESIS_CONFIRMATION":
                manifest["current_stage"] = "S7_REPORT_EXPORT"
    manifest["pending_confirmations"] = pending
    if manifest.get("current_stage") == "S1_PROFILE_AND_SCOPE" and not pending:
        completed = set(manifest.get("completed_stages", []))
        if "S1_PROFILE_AND_SCOPE" in completed:
            manifest["current_stage"] = "S2_DEEP_UNDERSTANDING"


def command_init(args: argparse.Namespace) -> dict[str, Any]:
    source_path = Path(args.source_path).expanduser().resolve()
    if not source_path.is_file():
        fail("source_path is not a file", source_path=str(source_path))
    try:
        source_text = source_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        fail("source_path must be UTF-8 text for this runtime version", source_path=str(source_path), detail=str(exc))
    input_hash = source_hash(source_path)
    paper_key = paper_key_for(source_path, input_hash)
    rid = run_id()
    root = Path.cwd() / RUNS_DIRNAME / paper_key / rid
    artifacts_dir(root).mkdir(parents=True, exist_ok=True)
    memory_path(root).write_text("", encoding="utf-8")
    now = utc_now()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "paper_key": paper_key,
        "run_id": rid,
        "source_path": str(source_path),
        "source_metadata": {
            "input_hash": input_hash,
            "bytes": source_path.stat().st_size,
            "characters": len(source_text),
            "lines": len(source_text.splitlines()),
        },
        "language": args.language or "",
        "user_goal": args.goal or "",
        "current_stage": "S1_PROFILE_AND_SCOPE",
        "confirmed_domain": "",
        "confirmed_scope": "",
        "pending_confirmations": ["domain_confirmation", "scope_confirmation"],
        "completed_stages": ["S0_INIT"],
        "created_at": now,
        "updated_at": now,
    }
    write_json(manifest_path(root), manifest)
    return {
        "ok": True,
        "mode": "init",
        "run_root": str(root),
        "manifest": manifest,
    }


def memory_stats(entries: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    findings_by_status: dict[str, int] = {}
    findings_by_severity: dict[str, int] = {}
    for entry in entries:
        record_type = str(entry.get("record_type", "unknown"))
        by_type[record_type] = by_type.get(record_type, 0) + 1
        if record_type == "finding":
            data = entry.get("data", {})
            status = str(data.get("status", "unknown"))
            severity = str(data.get("severity", "unknown"))
            findings_by_status[status] = findings_by_status.get(status, 0) + 1
            findings_by_severity[severity] = findings_by_severity.get(severity, 0) + 1
    return {
        "total_records": len(entries),
        "by_type": by_type,
        "findings_by_status": findings_by_status,
        "findings_by_severity": findings_by_severity,
    }


def has_memory_type(entries: list[dict[str, Any]], record_type: str) -> bool:
    return any(entry.get("record_type") == record_type for entry in entries)


def has_stage_summary(entries: list[dict[str, Any]], stage: str) -> bool:
    return any(
        entry.get("record_type") == "stage_summary" and entry.get("data", {}).get("stage") == stage
        for entry in entries
    )


def next_action(manifest: dict[str, Any], entries: list[dict[str, Any]]) -> str:
    pending = list(manifest.get("pending_confirmations", []))
    stage = str(manifest.get("current_stage"))
    if stage == "S1_PROFILE_AND_SCOPE" and not has_memory_type(entries, "paper_profile"):
        return "Create paper_profile and optional section_map before resolving domain/scope confirmations."
    if pending:
        return "Resolve pending confirmations before advancing: " + ", ".join(pending)
    if stage == "S2_DEEP_UNDERSTANDING" and not has_stage_summary(entries, "S2_DEEP_UNDERSTANDING"):
        return "Build deep understanding, then write a stage_summary for S2_DEEP_UNDERSTANDING."
    if stage in FINDING_STAGES and not has_stage_summary(entries, stage):
        return f"Run the {stage} review pass, write finding records as needed, then write a stage_summary."
    if stage == "S6_SYNTHESIS_CONFIRMATION" and not has_stage_summary(entries, "S6_SYNTHESIS_CONFIRMATION"):
        return "Summarize findings for user confirmation, then write a stage_summary and report_export_confirmation decision."
    if stage == "S7_REPORT_EXPORT":
        return "Run export to generate artifacts/review-report.md."
    if stage == "S8_DONE":
        return "Review run is complete."
    return f"Run instructions for {stage}, perform the agent review work, then write memory updates."


def sync_manifest_progress(manifest: dict[str, Any], entries: list[dict[str, Any]]) -> None:
    if (
        manifest.get("current_stage") == "S1_PROFILE_AND_SCOPE"
        and not manifest.get("pending_confirmations")
        and has_memory_type(entries, "paper_profile")
    ):
        completed = list(manifest.get("completed_stages", []))
        if "S1_PROFILE_AND_SCOPE" not in completed:
            completed.append("S1_PROFILE_AND_SCOPE")
        manifest["completed_stages"] = completed
        manifest["current_stage"] = "S2_DEEP_UNDERSTANDING"


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.run_root)
    manifest = load_manifest(root)
    entries = read_memory(root)
    return {
        "ok": True,
        "mode": "status",
        "run_root": str(root),
        "current_stage": manifest.get("current_stage"),
        "pending_confirmations": manifest.get("pending_confirmations", []),
        "completed_stages": manifest.get("completed_stages", []),
        "confirmed_domain": manifest.get("confirmed_domain", ""),
        "confirmed_scope": manifest.get("confirmed_scope", ""),
        "memory_stats": memory_stats(entries),
        "next_action": next_action(manifest, entries),
        "report_path": str(report_path(root)) if report_path(root).exists() else "",
    }


def command_instructions(args: argparse.Namespace) -> str:
    load_manifest(Path(args.run_root))
    stage = require_stage(args.stage)
    spec = STAGE_INSTRUCTIONS[stage]
    lines = [
        f"# {stage} instructions",
        "",
        f"## Purpose\n{spec['purpose']}",
        "",
        "## Agent responsibilities",
    ]
    lines.extend(f"- {item}" for item in spec["agent_work"])
    lines.extend(
        [
            "",
            "## Runtime and memory",
            f"- {spec['memory']}",
            "- Use `update` with a JSON payload only after the semantic judgement for the current work is stable.",
            "- Do not store long manuscript excerpts or long reference guide content.",
            "- Reference guidance output can be recorded as context, but optional reading suggestions are not evidence.",
        ]
    )
    return "\n".join(lines)


def command_update(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.run_root)
    manifest = load_manifest(root)
    payload = read_json(Path(args.payload_file))
    entry = validate_record(payload)
    validate_record_allowed_for_manifest(entry, manifest)
    upsert_memory(root, entry)
    data = entry["data"]
    if entry["record_type"] == "stage_summary":
        mark_stage_complete(manifest, str(data["stage"]))
    elif entry["record_type"] == "decision":
        apply_decision(manifest, data)
    sync_manifest_progress(manifest, read_memory(root))
    save_manifest(root, manifest)
    return {
        "ok": True,
        "mode": "update",
        "run_root": str(root),
        "record_type": entry["record_type"],
        "record_id": entry["record_id"],
        "current_stage": manifest.get("current_stage"),
        "pending_confirmations": manifest.get("pending_confirmations", []),
    }


def latest_entries_by_type(entries: list[dict[str, Any]], record_type: str) -> list[dict[str, Any]]:
    return [entry for entry in entries if entry.get("record_type") == record_type]


def command_read(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.run_root)
    manifest = load_manifest(root)
    entries = read_memory(root)
    findings = [entry["data"] for entry in latest_entries_by_type(entries, "finding")]
    open_questions = [
        entry["data"]
        for entry in latest_entries_by_type(entries, "open_question")
        if entry.get("data", {}).get("status", "open") == "open"
    ]
    return {
        "ok": True,
        "mode": "read",
        "run_root": str(root),
        "manifest": manifest,
        "memory_stats": memory_stats(entries),
        "paper_profile": [entry["data"] for entry in latest_entries_by_type(entries, "paper_profile")],
        "stage_summaries": [entry["data"] for entry in latest_entries_by_type(entries, "stage_summary")],
        "findings": findings,
        "open_questions": open_questions,
    }


def command_template(args: argparse.Namespace) -> dict[str, Any]:
    if args.record_type == "all":
        template: dict[str, Any] = RECORD_TEMPLATES
    else:
        template = RECORD_TEMPLATES[args.record_type]
    return {
        "ok": True,
        "mode": "template",
        "record_type": args.record_type,
        "valid_values": {
            "stages": STAGES,
            "record_types": sorted(RECORD_TYPES),
            "finding_stages": sorted(FINDING_STAGES),
            "severities": sorted(SEVERITIES),
            "confidences": sorted(CONFIDENCES),
            "finding_statuses": sorted(FINDING_STATUSES),
            "decision_types": sorted(DECISION_TYPES),
        },
        "template": template,
    }


def render_finding_item(finding: dict[str, Any], index: int) -> list[str]:
    evidence = finding.get("paper_evidence", "")
    if isinstance(evidence, list):
        evidence_text = "; ".join(str(item) for item in evidence)
    else:
        evidence_text = str(evidence)
    return [
        f"{index}. **{finding.get('claim')}**",
        f"   - Location: {finding.get('location')}",
        f"   - Type: {finding.get('issue_type')}",
        f"   - Evidence: {evidence_text}",
        f"   - Impact: {finding.get('impact')}",
        f"   - Suggested revision: {finding.get('suggested_revision')}",
        f"   - Confidence: {finding.get('confidence')} | Status: {finding.get('status')}",
    ]


def command_export(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.run_root)
    manifest = load_manifest(root)
    pending = list(manifest.get("pending_confirmations", []))
    if pending:
        fail("cannot export while confirmations are pending", pending_confirmations=pending)
    if manifest.get("current_stage") not in {"S7_REPORT_EXPORT", "S8_DONE"}:
        fail("cannot export before S7_REPORT_EXPORT", current_stage=manifest.get("current_stage"))
    entries = read_memory(root)
    findings = [
        entry["data"]
        for entry in latest_entries_by_type(entries, "finding")
        if entry.get("data", {}).get("status") in {"confirmed", "candidate"}
    ]
    major = [item for item in findings if item.get("severity") == "major"]
    minor = [item for item in findings if item.get("severity") == "minor"]
    notes = [item for item in findings if item.get("severity") == "note"]
    open_questions = [
        entry["data"]
        for entry in latest_entries_by_type(entries, "open_question")
        if entry.get("data", {}).get("status", "open") == "open"
    ]
    lines = [
        "# Review Report Draft",
        "",
        "## Summary",
        f"- Paper key: `{manifest.get('paper_key')}`",
        f"- Source: `{manifest.get('source_path')}`",
        f"- Confirmed domain: {manifest.get('confirmed_domain') or 'not recorded'}",
        f"- Confirmed scope: {manifest.get('confirmed_scope') or 'not recorded'}",
        "",
        "## Major Issues",
    ]
    if major:
        for index, finding in enumerate(major, start=1):
            lines.extend(render_finding_item(finding, index))
    else:
        lines.append("- No major issues recorded.")
    lines.extend(["", "## Minor Issues"])
    if minor:
        for index, finding in enumerate(minor, start=1):
            lines.extend(render_finding_item(finding, index))
    else:
        lines.append("- No minor issues recorded.")
    lines.extend(["", "## Notes"])
    if notes:
        for index, finding in enumerate(notes, start=1):
            lines.extend(render_finding_item(finding, index))
    else:
        lines.append("- No note-level findings recorded.")
    lines.extend(["", "## Open Questions"])
    if open_questions:
        for question in open_questions:
            lines.append(f"- {question.get('question')} ({question.get('stage')})")
    else:
        lines.append("- No open questions recorded.")
    lines.extend(
        [
            "",
            "## Recommendation-Style Comments",
            "- The final recommendation should be written by the agent from the structured findings above.",
            "- Do not add external facts or reference-guide claims that are not supported by manuscript evidence.",
        ]
    )
    artifacts_dir(root).mkdir(parents=True, exist_ok=True)
    report_path(root).write_text("\n".join(lines) + "\n", encoding="utf-8")
    completed = list(manifest.get("completed_stages", []))
    for stage in ("S7_REPORT_EXPORT",):
        if stage not in completed:
            completed.append(stage)
    manifest["completed_stages"] = completed
    manifest["current_stage"] = "S8_DONE"
    save_manifest(root, manifest)
    return {
        "ok": True,
        "mode": "export",
        "run_root": str(root),
        "report_path": str(report_path(root)),
        "findings_exported": len(findings),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lightweight runtime for paper-reviewer.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize a review run workspace.")
    init_parser.add_argument("--source-path", required=True)
    init_parser.add_argument("--language", default="")
    init_parser.add_argument("--goal", default="")

    status_parser = subparsers.add_parser("status", help="Show current runtime status.")
    status_parser.add_argument("--run-root", required=True)

    instructions_parser = subparsers.add_parser("instructions", help="Render stage instructions.")
    instructions_parser.add_argument("--run-root", required=True)
    instructions_parser.add_argument("--stage", required=True, choices=STAGES)

    update_parser = subparsers.add_parser("update", help="Validate and write a memory record.")
    update_parser.add_argument("--run-root", required=True)
    update_parser.add_argument("--payload-file", required=True)

    read_parser = subparsers.add_parser("read", help="Read runtime manifest and memory summary.")
    read_parser.add_argument("--run-root", required=True)

    template_parser = subparsers.add_parser("template", help="Print a minimum update payload template.")
    template_parser.add_argument("--record-type", required=True, choices=sorted(RECORD_TYPES) + ["all"])

    export_parser = subparsers.add_parser("export", help="Export a review report draft.")
    export_parser.add_argument("--run-root", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            print_json(command_init(args))
        elif args.command == "status":
            print_json(command_status(args))
        elif args.command == "instructions":
            print(command_instructions(args))
        elif args.command == "update":
            print_json(command_update(args))
        elif args.command == "read":
            print_json(command_read(args))
        elif args.command == "template":
            print_json(command_template(args))
        elif args.command == "export":
            print_json(command_export(args))
        else:
            parser.error(f"unknown command: {args.command}")
    except RuntimeErrorWithPayload as exc:
        payload = {"ok": False, "error": str(exc)}
        payload.update(exc.payload)
        print_json(payload)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

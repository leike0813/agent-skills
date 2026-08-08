from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from analysis_runtime import citations
from analysis_runtime import gate_contract
from analysis_runtime import references
from analysis_runtime import runtime
from analysis_runtime import runtime_db
from analysis_runtime import stages

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SKILL_DIR.parent


def _json_error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}, **extra}


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _payload_error(code: str, stage: str, payload_file: str, message: str, **extra: Any) -> dict[str, Any]:
    return {
        "runtime_backend": "analysis_runtime.run_analysis",
        "next_action": stage,
        "warnings": [],
        "error": {
            "code": code,
            "message": message,
            "stage": stage,
            "payload_file": payload_file,
            **extra,
        },
    }


def _read_json_payload(path_value: str, stage: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not path_value:
        return {}, None
    path = Path(path_value).expanduser()
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, _payload_error(
            "payload_json_invalid",
            stage,
            str(path),
            "payload file is not valid JSON",
            line=exc.lineno,
            column=exc.colno,
            json_error=exc.msg,
            repair_hint="Generate payload files with a JSON encoder and avoid hand-written string escaping.",
        )
    except UnicodeDecodeError as exc:
        return None, _payload_error(
            "payload_file_unreadable",
            stage,
            str(path),
            "payload file must be UTF-8 JSON",
            encoding_error=str(exc),
            repair_hint="Rewrite the payload file as UTF-8 JSON.",
        )
    except OSError as exc:
        return None, _payload_error(
            "payload_file_unreadable",
            stage,
            str(path),
            "payload file could not be read",
            io_error=str(exc),
            repair_hint="Check that --payload-file points to a readable JSON file.",
        )


def _reject_score_only(db_path: Path, requested_action: str) -> tuple[dict[str, Any] | None, int]:
    if not db_path.exists():
        return None, 0
    try:
        with runtime_db.connect_db(db_path) as connection:
            if not runtime_db.is_score_only(connection):
                return None, 0
            next_action = (
                "completed"
                if runtime_db.has_action_receipt(connection, "render_score_only")
                else "persist_literature_score"
            )
    except sqlite3.Error:
        return None, 0
    return (
        _json_error(
            "score_only_action_forbidden",
            f"{requested_action} is unavailable when score_only=true",
            db_path=str(db_path),
            next_action=next_action,
        ),
        2,
    )


def handle_init_runtime(args: argparse.Namespace) -> int:
    working_dir = Path(args.working_dir).expanduser().resolve() if args.working_dir else Path.cwd().resolve()
    db_path = Path(args.db_path).expanduser().resolve() if args.db_path else runtime.default_db_path(working_dir)
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else working_dir
    source_path = Path(args.source_path).expanduser().resolve()
    runtime_paths = runtime.initialize_runtime(
        working_dir=working_dir,
        db_path=db_path,
        output_dir=output_dir,
        source_path=source_path,
        language=args.language or "zh-CN",
        model=args.model or "",
        score_only=bool(args.score_only),
        identifier=args.identifier or "",
    )
    runtime.persist_default_templates(db_path=db_path, runtime_paths=runtime_paths, language=args.language or "zh-CN")
    normalize_payload, code = stages.normalize_source(
        source_path=source_path,
        db_path=db_path,
        runtime_paths=runtime_paths,
        language=args.language or "zh-CN",
        model=args.model or "",
    )
    if code != 0:
        _print(
            {
                "db_path": str(db_path),
                "next_action": "init_runtime",
                "runtime_backend": "analysis_runtime.stages",
                "error": normalize_payload.get("error") or {"code": "init_runtime_failed", "message": "source normalization failed"},
            }
        )
        return code

    next_action = "persist_literature_score" if args.score_only else "persist_analysis_plan"
    if args.score_only:
        with runtime_db.connect_db(db_path) as connection:
            runtime_db.set_workflow_state(
                connection,
                current_stage="stage_4_scoring",
                current_substep="persist_literature_score",
                stage_gate="ready",
                next_action="persist_literature_score",
                status_summary="normalized source ready for score-only analysis",
            )
            connection.commit()
    _print(
        {
            "db_path": str(db_path),
            "working_dir": str(working_dir),
            "output_dir": str(output_dir),
            "source_profile": runtime.source_profile(db_path),
            "runtime_backend": "analysis_runtime.stages",
            "next_action": next_action,
            "error": None,
        }
    )
    return 0


def handle_persist_analysis_plan(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path).expanduser().resolve()
    rejection, code = _reject_score_only(db_path, "persist_analysis_plan")
    if rejection is not None:
        _print(rejection)
        return code
    payload, error = _read_json_payload(args.payload_file, "persist_analysis_plan")
    if error is not None:
        _print(error)
        return 2
    assert payload is not None
    result, code = stages.persist_analysis_plan(db_path, payload)
    _print(result)
    return code


def handle_persist_digest(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path).expanduser().resolve()
    rejection, code = _reject_score_only(db_path, "persist_digest")
    if rejection is not None:
        _print(rejection)
        return code
    payload, error = _read_json_payload(args.payload_file, "persist_digest")
    if error is not None:
        _print(error)
        return 2
    assert payload is not None
    result, code = stages.persist_digest(db_path, payload)
    _print(result)
    return code


def handle_persist_literature_score(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path).expanduser().resolve()
    if not args.payload_file:
        result, code = stages.prepare_literature_score(db_path)
    else:
        payload, error = _read_json_payload(args.payload_file, "persist_literature_score")
        if error is not None:
            _print(error)
            return 2
        assert payload is not None
        result, code = stages.persist_literature_score(db_path, payload)
    _print(result)
    return code


def handle_persist_references(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path).expanduser().resolve()
    rejection, code = _reject_score_only(db_path, "persist_references")
    if rejection is not None:
        _print(rejection)
        return code
    if not args.payload_file:
        result, code = references.prepare_reference_workset(db_path)
        if code == 0:
            result["db_path"] = str(db_path)
            result.setdefault("next_action", "persist_references")
            if result.get("next_action") == "persist_references":
                result = references.enrich_reference_workset_payload(result)
        _print(result)
        return code

    payload, error = _read_json_payload(args.payload_file, "persist_references")
    if error is not None:
        _print(error)
        return 2
    assert payload is not None
    result, code = references.persist_references(db_path, payload)
    _print(result)
    return code


def handle_persist_citation_analysis(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path).expanduser().resolve()
    rejection, code = _reject_score_only(db_path, "persist_citation_analysis")
    if rejection is not None:
        _print(rejection)
        return code
    if not args.payload_file:
        result, code = citations.prepare_citation_workset(db_path)
        if code == 0:
            result.update({"db_path": str(db_path), "next_action": "persist_citation_analysis"})
            result = citations.enrich_citation_workset_payload(result)
        _print(result)
        return code

    payload, error = _read_json_payload(args.payload_file, "persist_citation_analysis")
    if error is not None:
        _print(error)
        return 2
    assert payload is not None
    final_payload, code = citations.persist_citation_analysis(db_path, payload)
    _print(final_payload)
    return code


def handle_finalize_outputs(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path).expanduser().resolve()
    payload, code = stages.render_public_outputs(db_path)
    _print(payload)
    return code


def handle_status(args: argparse.Namespace) -> int:
    _print(gate_contract.status_payload(Path(args.db_path).expanduser().resolve()))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Decision-oriented runtime wrapper for literature-analysis.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init_runtime")
    init.add_argument("--source-path", required=True)
    init.add_argument("--language", default="zh-CN")
    init.add_argument("--working-dir", default="")
    init.add_argument("--output-dir", default="")
    init.add_argument("--db-path", default="")
    init.add_argument("--model", default="")
    init.add_argument("--score-only", action="store_true")
    init.add_argument("--identifier", default="")
    init.set_defaults(handler=handle_init_runtime)

    plan = subparsers.add_parser("persist_analysis_plan")
    plan.add_argument("--db-path", required=True)
    plan.add_argument("--payload-file", required=True)
    plan.set_defaults(handler=handle_persist_analysis_plan)

    digest = subparsers.add_parser("persist_digest")
    digest.add_argument("--db-path", required=True)
    digest.add_argument("--payload-file", required=True)
    digest.set_defaults(handler=handle_persist_digest)

    score = subparsers.add_parser("persist_literature_score")
    score.add_argument("--db-path", required=True)
    score.add_argument("--payload-file", default="")
    score.set_defaults(handler=handle_persist_literature_score)

    references = subparsers.add_parser("persist_references")
    references.add_argument("--db-path", required=True)
    references.add_argument("--payload-file", default="")
    references.set_defaults(handler=handle_persist_references)

    citation = subparsers.add_parser("persist_citation_analysis")
    citation.add_argument("--db-path", required=True)
    citation.add_argument("--payload-file", default="")
    citation.set_defaults(handler=handle_persist_citation_analysis)

    finalize = subparsers.add_parser("finalize_outputs")
    finalize.add_argument("--db-path", required=True)
    finalize.set_defaults(handler=handle_finalize_outputs)

    status = subparsers.add_parser("status")
    status.add_argument("--db-path", required=True)
    status.set_defaults(handler=handle_status)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())

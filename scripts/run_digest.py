#!/usr/bin/env python3
"""
literature-digest-lite: Simplified paper digest generator.

Usage:
    # Step 1: Normalize input
    python run_digest.py --mode normalize --source-path "/abs/path/paper.md"

    # Step 2: Generate digest_slots + section_summaries (LLM call by agent)

    # Step 3: Render output
    python run_digest.py --mode render \
      --source-path "/abs/path/paper.md" \
      --language "zh-CN" \
      --payload-file /tmp/digest_payload.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from jinja2 import FileSystemLoader, Environment
except ImportError:
    print(
        json.dumps(
            {
                "digest_path": "",
                "provenance": {"generated_at": "", "input_hash": ""},
                "warnings": [],
                "error": {
                    "code": "jinja2_missing",
                    "message": "jinja2 is required: pip install jinja2",
                },
            },
            ensure_ascii=False,
        )
    )
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent.resolve()
PACKAGE_DIR = SCRIPT_DIR.parent.resolve()
TEMPLATES_DIR = PACKAGE_DIR / "assets" / "templates"
DEFAULT_LANG = "zh-CN"


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compute_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _resolve_latex_include(base_dir: Path, target: str) -> Path:
    candidates = [base_dir / target, base_dir / f"{target}.tex"]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0]


def _flatten_latex_text(
    base_dir: Path, lines: list[str], visited: set[Path] | None = None
) -> list[str]:
    if visited is None:
        visited = set()
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith(r"\input{") or stripped.startswith(r"\include{"):
            match = re.search(r"\{([^}]+)\}", stripped)
            if match:
                include_target = match.group(1)
                include_path = _resolve_latex_include(base_dir, include_target)
                if include_path not in visited and include_path.exists():
                    visited.add(include_path)
                    try:
                        nested_lines = include_path.read_text(
                            encoding="utf-8"
                        ).splitlines()
                        nested_result = _flatten_latex_text(
                            include_path.parent, nested_lines, visited
                        )
                        result.extend(nested_result)
                    except Exception:
                        result.append(f"% Failed to include: {include_path}")
        result.append(line)
        i += 1
    return result


def _render_fenced_latex_source(
    tex_content: str, bib_content: str | None = None
) -> str:
    lines = ["```tex", tex_content.rstrip(), "```"]
    if bib_content:
        lines.extend(["", "```bibtex", bib_content.rstrip(), "```"])
    return "\n".join(lines)


def _normalize_latex_source(source_path: Path) -> tuple[str, dict[str, Any]]:
    meta: dict[str, Any] = {}
    if source_path.is_dir():
        tex_files = list(source_path.glob("*.tex"))
        main_tex = None
        for candidate in ["main.tex", "paper.tex", "ms.tex", "root.tex"]:
            candidate_path = source_path / candidate
            if candidate_path.exists():
                main_tex = candidate_path
                break
        if main_tex is None and tex_files:
            main_tex = tex_files[0]
        if main_tex is None:
            raise RuntimeError(f"No .tex files found in directory: {source_path}")
        visited: set[Path] = {main_tex.resolve()}
        raw_text = main_tex.read_text(encoding="utf-8")
        lines = raw_text.splitlines()
        flattened = _flatten_latex_text(main_tex.parent, lines, visited)
        tex_content = "\n".join(flattened)
        bib_content = None
        bib_files = list(source_path.glob("*.bib"))
        if bib_files:
            bib_parts = []
            for bf in sorted(bib_files):
                try:
                    bib_parts.append(bf.read_text(encoding="utf-8"))
                except Exception:
                    pass
            if bib_parts:
                bib_content = "\n\n".join(bib_parts)
        markdown = _render_fenced_latex_source(tex_content, bib_content)
        meta.update(
            {
                "source_type": "latex_project",
                "detection_method": "latex_project_directory",
                "conversion_backend": "fenced_raw_latex",
            }
        )
    else:
        raw_text = source_path.read_text(encoding="utf-8")
        lines = raw_text.splitlines()
        bib_content = None
        tex_content = "\n".join(lines)
        markdown = _render_fenced_latex_source(tex_content, bib_content)
        meta.update(
            {
                "source_type": "latex_tex",
                "detection_method": "latex_text_markers",
                "conversion_backend": "fenced_raw_lat",
            }
        )
    return markdown, meta


def _convert_pdf_with_pymupdf4llm(source_path: Path) -> str:
    try:
        import pymupdf4llm  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(f"pymupdf4llm unavailable: {exc}") from exc
    try:
        markdown = pymupdf4llm.to_markdown(str(source_path))
        if not markdown or not markdown.strip():
            raise RuntimeError("pymupdf4llm returned empty markdown")
        return markdown
    except Exception as exc:
        raise RuntimeError(f"pymupdf4llm conversion failed: {exc}") from exc


def _detect_source_type(source_path: Path) -> tuple[str, str]:
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")
    if source_path.is_dir():
        tex_files = list(source_path.glob("*.tex"))
        if tex_files:
            return "latex_project", "latex_project_directory"
        raise RuntimeError(f"Directory contains no .tex files: {source_path}")
    suffix = source_path.suffix.lower()
    if suffix == ".tex":
        return "latex_tex", "latex_text_markers"
    try:
        header = source_path.read_bytes()[:1024]
        if header.startswith(b"%PDF-"):
            return "pdf", "pdf_signature"
    except Exception:
        pass
    try:
        text = source_path.read_text(encoding="utf-8")
        if r"\documentclass" in text or r"\begin{document}" in text:
            return "latex_tex", "latex_text_markers"
        return "markdown", "utf8_text"
    except UnicodeDecodeError:
        raise RuntimeError(
            f"Unable to read file as UTF-8 text: {source_path}"
        ) from None


def normalize_source(source_path: Path) -> tuple[str, dict[str, Any]]:
    source_type, detection_method = _detect_source_type(source_path)
    meta: dict[str, Any] = {
        "source_type": source_type,
        "detection_method": detection_method,
    }
    if source_type == "pdf":
        disable_pymupdf4llm = bool(
            os.environ.get("LITERATURE_DIGEST_DISABLE_PYMUPDF4LLM")
        )
        if disable_pymupdf4llm:
            raise RuntimeError("pymupdf4llm is disabled by environment variable")
        markdown = _convert_pdf_with_pymupdf4llm(source_path)
        meta["conversion_backend"] = "pymupdf4llm"
        return markdown, meta
    elif source_type in {"latex_tex", "latex_project"}:
        markdown, latex_meta = _normalize_latex_source(source_path)
        meta.update(latex_meta)
        return markdown, meta
    else:
        markdown = source_path.read_text(encoding="utf-8")
        meta["conversion_backend"] = "utf8_text"
        return markdown, meta


def _repo_digest_template_path(language: str) -> Path:
    if language.lower().startswith("en"):
        return (TEMPLATES_DIR / "digest.en-US.md.j2").resolve()
    return (TEMPLATES_DIR / "digest.zh-CN.md.j2").resolve()


def build_render_context(
    digest_slots: dict[str, Any], section_summaries: list[dict[str, Any]], language: str
) -> dict[str, Any]:
    return {
        "language": language,
        "digest_slots": digest_slots,
        "section_summaries": section_summaries,
    }


def render_digest(template_path: Path, context: dict[str, Any]) -> str:
    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)), autoescape=False
    )
    template = env.get_template(template_path.name)
    return template.render(**context)


def validate_digest_payload(
    payload: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(payload, dict):
        return None, "payload must be a dict"
    digest_slots = payload.get("digest_slots")
    if not isinstance(digest_slots, dict):
        return None, "digest_slots must be a dict"
    required_slots = [
        "tldr",
        "research_question_and_contributions",
        "method_highlights",
        "key_results",
        "limitations_and_reproducibility",
    ]
    for slot in required_slots:
        if slot not in digest_slots:
            return None, f"missing required slot: {slot}"
    tldr = digest_slots.get("tldr")
    if (
        not isinstance(tldr, dict)
        or "paragraphs" not in tldr
        or not isinstance(tldr["paragraphs"], list)
    ):
        return None, "digest_slots.tldr.paragraphs must be a list"
    rqc = digest_slots.get("research_question_and_contributions")
    if not isinstance(rqc, dict):
        return None, "digest_slots.research_question_and_contributions must be a dict"
    for key in ["method_highlights", "key_results", "limitations_and_reproducibility"]:
        slot = digest_slots.get(key)
        if (
            not isinstance(slot, dict)
            or "items" not in slot
            or not isinstance(slot["items"], list)
        ):
            return None, f"digest_slots.{key}.items must be a list"
    section_summaries = payload.get("section_summaries")
    if not isinstance(section_summaries, list):
        return None, "section_summaries must be a list"
    for item in section_summaries:
        if not isinstance(item, dict):
            return None, "section_summaries items must be dicts"
        if "source_heading" not in item or "items" not in item:
            return None, "section_summaries items must have source_heading and items"
    return payload, None


def mode_normalize(args: argparse.Namespace) -> int:
    warnings: list[str] = []
    try:
        source_path = Path(args.source_path).expanduser().resolve()
        normalized_text, meta = normalize_source(source_path)
        input_hash = compute_sha256(normalized_text)
        result = {
            "normalized_text": normalized_text,
            "input_hash": f"sha256:{input_hash}",
            "source_type": meta.get("source_type", ""),
            "detection_method": meta.get("detection_method", ""),
            "conversion_backend": meta.get("conversion_backend", ""),
            "warnings": warnings,
            "error": None,
        }
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        result = {
            "normalized_text": "",
            "input_hash": "",
            "warnings": warnings,
            "error": {"code": "normalize_failed", "message": str(exc)},
        }
        print(json.dumps(result, ensure_ascii=False))
        return 1


def mode_render(args: argparse.Namespace) -> int:
    warnings: list[str] = []
    try:
        source_path = Path(args.source_path).expanduser().resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")
        _, meta = normalize_source(source_path)
        input_hash = compute_sha256(source_path.read_text(encoding="utf-8"))
        language = (
            args.language.strip()
            if args.language and args.language.strip()
            else DEFAULT_LANG
        )
        if args.payload_file:
            payload_path = Path(args.payload_file).expanduser().resolve()
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
        else:
            raw = (
                sys.stdin.read()
                if sys.stdin.readable() and not sys.stdin.isatty()
                else ""
            )
            payload = json.loads(raw) if raw.strip() else {}
        validated_payload, validation_error = validate_digest_payload(payload)
        if validation_error or validated_payload is None:
            raise RuntimeError(
                f"Invalid digest payload: {validation_error or 'None payload'}"
            )
        digest_slots = validated_payload["digest_slots"]
        section_summaries = validated_payload["section_summaries"]
        if args.template_file:
            template_path = Path(args.template_file).expanduser().resolve()
        else:
            template_path = _repo_digest_template_path(language)
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")
        out_dir = source_path.parent
        context = build_render_context(digest_slots, section_summaries, language)
        digest_md = render_digest(template_path, context)
        digest_path = out_dir / "digest.md"
        digest_path.write_text(digest_md, encoding="utf-8")
        result = {
            "digest_path": str(digest_path.resolve()),
            "provenance": {
                "generated_at": utc_now_iso(),
                "input_hash": f"sha256:{input_hash}",
            },
            "warnings": warnings,
            "error": None,
        }
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        result = {
            "digest_path": "",
            "provenance": {"generated_at": "", "input_hash": ""},
            "warnings": warnings,
            "error": {"code": "render_failed", "message": str(exc)},
        }
        print(json.dumps(result, ensure_ascii=False))
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a paper digest from Markdown/PDF/LaTeX"
    )
    parser.add_argument(
        "--mode", required=True, choices=["normalize", "render"], help="Execution mode"
    )
    parser.add_argument(
        "--source-path",
        required=True,
        help="Path to the source file (Markdown/PDF/LaTeX)",
    )
    parser.add_argument(
        "--language",
        default="",
        help="Output language (BCP 47 tag, e.g., zh-CN, en-US)",
    )
    parser.add_argument(
        "--payload-file",
        default="",
        help="JSON file with digest_slots + section_summaries (render mode only)",
    )
    parser.add_argument(
        "--template-file", default="", help="Runtime template path (render mode only)"
    )
    args = parser.parse_args()
    if args.mode == "normalize":
        return mode_normalize(args)
    else:
        return mode_render(args)


if __name__ == "__main__":
    sys.exit(main())

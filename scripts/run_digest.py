#!/usr/bin/env python3
"""
literature-digest: Paper digest generator.

Usage:
    # Step 1: Normalize input
    python run_digest.py --mode normalize --source-path "/abs/path/paper.md"

    # Step 2: Generate classification + digest content (LLM call by agent)

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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

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
PROFILES_PATH = PACKAGE_DIR / "assets" / "literature_profiles.json"
DEFAULT_LANG = "zh-CN"
PROFILE_IDS = (
    "quantitative_empirical",
    "qualitative_empirical",
    "interpretive_historical",
    "conceptual_normative",
    "formal_theoretical",
    "review_synthesis",
    "mixed_methods",
    "general",
)
DIGEST_SECTION_KEYS = ("focus", "basis", "analysis", "limits")
HEADING_KEYS = ("tldr", *DIGEST_SECTION_KEYS, "section_summaries")
DEFAULT_HEADINGS = {
    "zh-CN": {"tldr": "TL;DR", "section_summaries": "分章节总结"},
    "en-US": {"tldr": "TL;DR", "section_summaries": "Section-by-Section Summary"},
}


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
        import pymupdf4llm  # type: ignore[import-untyped]
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


def _heading_language(language: str) -> str | None:
    normalized = language.strip().lower()
    if normalized.startswith("zh"):
        return "zh-CN"
    if normalized.startswith("en"):
        return "en-US"
    return None


def _nonempty_string(value: Any, field: str) -> tuple[str | None, str | None]:
    if not isinstance(value, str) or not value.strip():
        return None, f"{field} must be a non-empty string"
    return value.strip(), None


def _nonempty_string_list(
    value: Any, field: str, *, allow_empty: bool = False
) -> tuple[list[str] | None, str | None]:
    if not isinstance(value, list):
        return None, f"{field} must be a list"
    if not value and not allow_empty:
        return None, f"{field} must not be empty"
    normalized: list[str] = []
    for index, item in enumerate(value):
        text, error = _nonempty_string(item, f"{field}[{index}]")
        if error:
            return None, error
        normalized.append(text)
    return normalized, None


def _normalize_classification(
    value: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(value, dict) or set(value) != {"disciplines", "profile_id", "confidence", "reason"}:
        return None, "literature_classification must be a dict"
    disciplines, error = _nonempty_string_list(
        value.get("disciplines"),
        "literature_classification.disciplines",
        allow_empty=True,
    )
    if error:
        return None, error
    profile_id, error = _nonempty_string(
        value.get("profile_id"), "literature_classification.profile_id"
    )
    if error:
        return None, error
    profile_id = profile_id.lower()
    if profile_id not in PROFILE_IDS:
        return None, f"unknown literature profile: {profile_id}"
    confidence, error = _nonempty_string(
        value.get("confidence"), "literature_classification.confidence"
    )
    if error:
        return None, error
    confidence = confidence.lower()
    if confidence not in {"high", "medium", "low"}:
        return None, "literature_classification.confidence must be high, medium, or low"
    reason, error = _nonempty_string(
        value.get("reason"), "literature_classification.reason"
    )
    if error:
        return None, error
    return {
        "disciplines": list(dict.fromkeys(disciplines)),
        "profile_id": "general" if confidence == "low" else profile_id,
        "confidence": confidence,
        "reason": reason,
    }, None


def _load_profiles() -> dict[str, dict[str, Any]]:
    try:
        registry = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Unable to load literature profile registry: {exc}") from exc
    if registry.get("schema") != "literature_profiles.v1":
        raise RuntimeError("literature_profiles.json has an unsupported schema")
    profiles = registry.get("profiles")
    if not isinstance(profiles, dict):
        raise RuntimeError("literature_profiles.json profiles must be an object")
    for profile_id in PROFILE_IDS:
        profile = profiles.get(profile_id)
        if not isinstance(profile, dict) or profile.get("profile_id") != profile_id:
            raise RuntimeError(f"Missing or invalid literature profile: {profile_id}")
        sections = profile.get("digest_sections")
        if not isinstance(sections, list) or len(sections) != len(DIGEST_SECTION_KEYS):
            raise RuntimeError(f"Invalid digest_sections for profile: {profile_id}")
        for slot_key, section in zip(DIGEST_SECTION_KEYS, sections):
            if not isinstance(section, dict) or section.get("slot_key") != slot_key:
                raise RuntimeError(f"Invalid digest_sections for profile: {profile_id}")
            headings = section.get("heading")
            if not isinstance(headings, dict):
                raise RuntimeError(f"Invalid digest_sections for profile: {profile_id}")
            for language_key in ("zh-CN", "en-US"):
                if not isinstance(headings.get(language_key), str) or not headings[
                    language_key
                ].strip():
                    raise RuntimeError(
                        f"Invalid heading {language_key}/{slot_key} for profile: {profile_id}"
                    )
    return profiles


def build_render_context(
    digest_slots: dict[str, Any],
    section_summaries: list[dict[str, Any]],
    language: str,
    digest_sections: list[dict[str, Any]],
    tldr_heading: str,
    section_summaries_heading: str,
) -> dict[str, Any]:
    return {
        "language": language,
        "digest_slots": digest_slots,
        "section_summaries": section_summaries,
        "digest_sections": digest_sections,
        "tldr_heading": tldr_heading,
        "section_summaries_heading": section_summaries_heading,
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
    classification, error = _normalize_classification(
        payload.get("literature_classification")
    )
    if error:
        return None, error
    digest_slots = payload.get("digest_slots")
    if not isinstance(digest_slots, dict):
        return None, "digest_slots must be a dict"
    if set(digest_slots) != {"tldr", *DIGEST_SECTION_KEYS}:
        return None, "digest_slots must contain exactly tldr, focus, basis, analysis and limits"
    tldr = digest_slots.get("tldr")
    if not isinstance(tldr, dict):
        return None, "digest_slots.tldr must be a dict"
    paragraphs, error = _nonempty_string_list(
        tldr.get("paragraphs"), "digest_slots.tldr.paragraphs"
    )
    if error:
        return None, error
    normalized_slots: dict[str, Any] = {"tldr": {"paragraphs": paragraphs}}
    for key in DIGEST_SECTION_KEYS:
        slot_value = digest_slots.get(key)
        if not isinstance(slot_value, dict):
            return None, f"digest_slots.{key} must be a dict"
        items, error = _nonempty_string_list(
            slot_value.get("items"), f"digest_slots.{key}.items"
        )
        if error:
            return None, error
        normalized_slots[key] = {"items": items}
    section_summaries = payload.get("section_summaries")
    if not isinstance(section_summaries, list):
        return None, "section_summaries must be a list"
    normalized_summaries: list[dict[str, Any]] = []
    for index, section in enumerate(section_summaries):
        if not isinstance(section, dict):
            return None, f"section_summaries[{index}] must be a dict"
        source_heading, error = _nonempty_string(
            section.get("source_heading"),
            f"section_summaries[{index}].source_heading",
        )
        if error:
            return None, error
        items, error = _nonempty_string_list(
            section.get("items"), f"section_summaries[{index}].items"
        )
        if error:
            return None, error
        normalized_summaries.append(
            {"source_heading": source_heading, "items": items}
        )
    normalized_translations: dict[str, str] = {}
    translations = payload.get("heading_translations")
    if translations is not None:
        if not isinstance(translations, dict):
            return None, "heading_translations must be a dict"
        for key in HEADING_KEYS:
            if key not in translations:
                continue
            heading, error = _nonempty_string(
                translations[key], f"heading_translations.{key}"
            )
            if error:
                return None, error
            normalized_translations[key] = heading
    normalized_payload: dict[str, Any] = {
        "literature_classification": classification,
        "digest_slots": normalized_slots,
        "section_summaries": normalized_summaries,
    }
    if "heading_translations" in payload:
        normalized_payload["heading_translations"] = normalized_translations
    return normalized_payload, None


def _select_headings(
    profile: dict[str, Any], language: str, translations: dict[str, str]
) -> tuple[dict[str, str], str, str]:
    headings: dict[str, str] = {}
    heading_language = _heading_language(language)
    if heading_language:
        for section in profile["digest_sections"]:
            headings[section["slot_key"]] = section["heading"][heading_language].strip()
        defaults = DEFAULT_HEADINGS[heading_language]
        return headings, defaults["tldr"], defaults["section_summaries"]
    missing = [key for key in HEADING_KEYS if not translations.get(key)]
    if missing:
        raise RuntimeError(
            "Non zh/en languages require heading_translations for: " + ", ".join(missing)
        )
    for key in DIGEST_SECTION_KEYS:
        headings[key] = translations[key]
    return headings, translations["tldr"], translations["section_summaries"]


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
        normalized_text, _ = normalize_source(source_path)
        input_hash = compute_sha256(normalized_text)
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
        classification = validated_payload["literature_classification"]
        effective_profile_id = classification["profile_id"]
        if classification["confidence"] == "low":
            effective_profile_id = "general"
            warnings.append("classification_low_confidence")
        profile = _load_profiles()[effective_profile_id]
        section_headings, tldr_heading, section_summaries_heading = _select_headings(
            profile,
            language,
            validated_payload.get("heading_translations", {}),
        )
        digest_sections = [
            {
                "heading": section_headings[key],
                "items": digest_slots[key]["items"],
            }
            for key in DIGEST_SECTION_KEYS
        ]
        if args.template_file:
            template_path = Path(args.template_file).expanduser().resolve()
        else:
            template_path = _repo_digest_template_path(language)
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")
        out_dir = source_path.parent
        context = build_render_context(
            digest_slots,
            section_summaries,
            language,
            digest_sections,
            tldr_heading,
            section_summaries_heading,
        )
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
        help="JSON file with literature_classification and digest content",
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

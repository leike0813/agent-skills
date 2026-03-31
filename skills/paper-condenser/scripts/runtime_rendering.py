#!/usr/bin/env python3
"""Render read-only runtime views from external Jinja2 templates."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Mapping

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError

PACKAGE_TEMPLATE_ROOT = Path(__file__).resolve().parent.parent / "assets" / "render-templates"
WORKSPACE_TEMPLATE_DIRNAME = "render-templates"
DEFAULT_TEMPLATE_LANGUAGE = "en"
SUPPORTED_TEMPLATE_LANGUAGES = {"en", "zh"}

TEMPLATE_MAPPING: dict[str, tuple[str, str]] = {
    "resume": ("01-agent-resume.md.j2", "01-agent-resume.md"),
    "manuscript_profile": ("02-manuscript-profile.md.j2", "02-manuscript-profile.md"),
    "supporting_elements": (
        "03-supporting-elements-inventory.md.j2",
        "03-supporting-elements-inventory.md",
    ),
    "scope_segments": ("04-scope-segments.md.j2", "04-scope-segments.md"),
    "semantic_source_units": (
        "05-semantic-source-units.md.j2",
        "05-semantic-source-units.md",
    ),
    "target_settings": ("06-target-settings.md.j2", "06-target-settings.md"),
    "content_selection_board": (
        "07-content-selection-board.md.j2",
        "07-content-selection-board.md",
    ),
    "style_profile": ("08-style-profile.md.j2", "08-style-profile.md"),
    "condensation_plan": ("09-condensation-plan.md.j2", "09-condensation-plan.md"),
    "section_rewrite_plan": (
        "10-section-rewrite-plan.md.j2",
        "10-section-rewrite-plan.md",
    ),
    "section_drafting_board": (
        "11-section-drafting-board.md.j2",
        "11-section-drafting-board.md",
    ),
}
SECTION_REVIEW_TEMPLATE = "section-review.md.j2"
TEMPLATE_FILENAMES = {
    template_name for template_name, _ in TEMPLATE_MAPPING.values()
} | {SECTION_REVIEW_TEMPLATE}


def package_template_root_for_language(language: str) -> Path:
    candidate = PACKAGE_TEMPLATE_ROOT / language
    if candidate.is_dir():
        return candidate
    if language == DEFAULT_TEMPLATE_LANGUAGE:
        return PACKAGE_TEMPLATE_ROOT
    raise FileNotFoundError(f"Missing package template source for language '{language}'")


def workspace_template_root(artifact_root: Path) -> Path:
    return artifact_root / WORKSPACE_TEMPLATE_DIRNAME


def resolve_template_root(artifact_root: Path) -> Path:
    workspace_root = workspace_template_root(artifact_root)
    if workspace_root.is_dir():
        return workspace_root
    return package_template_root_for_language(DEFAULT_TEMPLATE_LANGUAGE)


def build_template_environment(template_root: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(template_root)),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=False,
        lstrip_blocks=False,
        keep_trailing_newline=True,
    )


def materialize_packaged_templates(artifact_root: Path, language: str) -> Path:
    source_root = package_template_root_for_language(language)
    destination_root = workspace_template_root(artifact_root)
    destination_root.mkdir(parents=True, exist_ok=True)
    for template_name in TEMPLATE_FILENAMES:
        source_path = source_root / template_name
        if not source_path.is_file():
            raise FileNotFoundError(f"Missing package template: {source_path}")
        shutil.copy2(source_path, destination_root / template_name)
    return destination_root


def write_runtime_templates(
    artifact_root: Path, templates: Mapping[str, str]
) -> Path:
    destination_root = workspace_template_root(artifact_root)
    destination_root.mkdir(parents=True, exist_ok=True)
    missing = TEMPLATE_FILENAMES.difference(templates.keys())
    if missing:
        raise ValueError(
            "Missing translated runtime templates: " + ", ".join(sorted(missing))
        )
    for template_name in TEMPLATE_FILENAMES:
        (destination_root / template_name).write_text(
            str(templates[template_name]).rstrip() + "\n",
            encoding="utf-8",
        )
    return destination_root


def render_markdown_views(
    artifact_root: Path,
    view_models: Mapping[str, Mapping[str, Any]],
) -> dict[str, str]:
    template_root = resolve_template_root(artifact_root)
    env = build_template_environment(template_root)
    rendered_paths: dict[str, str] = {}

    for view_name, (template_name, output_name) in TEMPLATE_MAPPING.items():
        template_path = template_root / template_name
        if not template_path.is_file():
            raise FileNotFoundError(f"Missing render template: {template_path}")
        if view_name not in view_models:
            raise KeyError(f"Missing render view-model: {view_name}")

        try:
            content = env.get_template(template_name).render(**view_models[view_name])
        except TemplateError as exc:
            raise RuntimeError(f"Failed to render template '{template_name}': {exc}") from exc

        output_path = artifact_root / output_name
        output_path.write_text(content.rstrip() + "\n", encoding="utf-8")
        rendered_paths[view_name] = str(output_path)

    return rendered_paths


def render_section_review(
    artifact_root: Path,
    output_name: str,
    view_model: Mapping[str, Any],
) -> str:
    template_root = resolve_template_root(artifact_root)
    env = build_template_environment(template_root)
    template_name = SECTION_REVIEW_TEMPLATE
    template_path = template_root / template_name
    if not template_path.is_file():
        raise FileNotFoundError(f"Missing render template: {template_path}")
    try:
        content = env.get_template(template_name).render(**view_model)
    except TemplateError as exc:
        raise RuntimeError(f"Failed to render template '{template_name}': {exc}") from exc
    output_path = artifact_root / output_name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return str(output_path)

#!/usr/bin/env python3
"""Render read-only runtime views from external Jinja2 templates."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError

TEMPLATE_ROOT = Path(__file__).resolve().parent.parent / "assets" / "render-templates"

TEMPLATE_MAPPING: dict[str, tuple[str, str]] = {
    "resume": ("01-agent-resume.md.j2", "01-agent-resume.md"),
    "manuscript_profile": ("02-manuscript-profile.md.j2", "02-manuscript-profile.md"),
    "target_settings": ("03-target-settings.md.j2", "03-target-settings.md"),
    "style_profile": ("04-style-profile.md.j2", "04-style-profile.md"),
    "condensation_plan": ("05-condensation-plan.md.j2", "05-condensation-plan.md"),
    "supporting_elements": (
        "06-supporting-elements-inventory.md.j2",
        "06-supporting-elements-inventory.md",
    ),
    "scope_segments": ("07-scope-segments.md.j2", "07-scope-segments.md"),
    "semantic_source_units": (
        "08-semantic-source-units.md.j2",
        "08-semantic-source-units.md",
    ),
    "section_rewrite_plan": (
        "09-section-rewrite-plan.md.j2",
        "09-section-rewrite-plan.md",
    ),
    "section_drafting_board": (
        "10-section-drafting-board.md.j2",
        "10-section-drafting-board.md",
    ),
    "content_selection_board": (
        "11-content-selection-board.md.j2",
        "11-content-selection-board.md",
    ),
}


def build_template_environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_ROOT)),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=False,
        lstrip_blocks=False,
        keep_trailing_newline=True,
    )


def render_markdown_views(
    artifact_root: Path,
    view_models: Mapping[str, Mapping[str, Any]],
) -> dict[str, str]:
    env = build_template_environment()
    rendered_paths: dict[str, str] = {}

    for view_name, (template_name, output_name) in TEMPLATE_MAPPING.items():
        template_path = TEMPLATE_ROOT / template_name
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
    env = build_template_environment()
    template_name = "section-review.md.j2"
    template_path = TEMPLATE_ROOT / template_name
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

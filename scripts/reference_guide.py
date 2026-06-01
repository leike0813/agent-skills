#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = PACKAGE_ROOT / "references" / "reference_index.json"
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    line_no: int
    line_index: int
    raw: str


class GuideError(Exception):
    def __init__(self, message: str, candidates: dict[str, list[str]] | None = None) -> None:
        super().__init__(message)
        self.candidates = candidates or {}


def _load_json_with_duplicate_check(path: Path) -> dict[str, Any]:
    duplicates: list[str] = []

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        seen: set[str] = set()
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in seen:
                duplicates.append(key)
            seen.add(key)
            result[key] = value
        return result

    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=hook)
    except FileNotFoundError as exc:
        raise GuideError(f"index file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GuideError(f"invalid JSON in index: {exc}") from exc

    if duplicates:
        unique = ", ".join(sorted(set(duplicates)))
        raise GuideError(f"duplicate JSON object keys found: {unique}")
    if not isinstance(data, dict):
        raise GuideError("index root must be a JSON object")
    return data


def _load_index() -> dict[str, Any]:
    return _load_json_with_duplicate_check(INDEX_PATH)


def _require_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise GuideError(f"index field '{key}' must be an object")
    return value


def _as_str_list(value: Any, field_name: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise GuideError(f"index field '{field_name}' must be a string array")
    if not allow_empty and not value:
        raise GuideError(f"index field '{field_name}' must not be empty")
    return [item.strip() for item in value]


def _reference_path(relative_path: str) -> Path:
    if relative_path.startswith("references/"):
        return PACKAGE_ROOT / relative_path
    return PACKAGE_ROOT / "references" / relative_path


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PACKAGE_ROOT.parent))
    except ValueError:
        return str(path)


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise GuideError(f"reference file not found: {_display_path(path)}") from exc


def _read_raw_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines(keepends=True)
    except FileNotFoundError as exc:
        raise GuideError(f"reference file not found: {_display_path(path)}") from exc


def _parse_headings(path: Path) -> list[Heading]:
    headings: list[Heading] = []
    for index, line in enumerate(_read_lines(path)):
        match = HEADING_RE.match(line)
        if match:
            headings.append(
                Heading(
                    level=len(match.group(1)),
                    text=match.group(2).strip(),
                    line_no=index + 1,
                    line_index=index,
                    raw=line,
                )
            )
    return headings


def _headings_by_text(path: Path) -> dict[str, list[Heading]]:
    by_text: dict[str, list[Heading]] = {}
    for heading in _parse_headings(path):
        by_text.setdefault(heading.text, []).append(heading)
    return by_text


def _dedupe_records(records: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for record in records:
        key = (record["ref"], record["heading"])
        if key in seen:
            continue
        seen.add(key)
        result.append(record)
    return result


def _domains(index: dict[str, Any]) -> dict[str, Any]:
    return _require_mapping(index, "domains")


def _topics(index: dict[str, Any]) -> dict[str, Any]:
    value = index.get("topics", {})
    if not isinstance(value, dict):
        raise GuideError("index field 'topics' must be an object when present")
    return value


def _candidate_block(index: dict[str, Any]) -> dict[str, list[str]]:
    stages = _require_mapping(index, "review_stages")
    sections = _require_mapping(index, "paper_sections")
    return {
        "canonical-domain-name": sorted(_domains(index)),
        "review-stage": sorted(stages),
        "paper-section": sorted(sections),
    }


def _render_candidates(candidates: dict[str, list[str]]) -> str:
    lines = ["## Candidate identifiers"]
    for label, values in candidates.items():
        joined = ", ".join(f"`{value}`" for value in values)
        lines.append(f"- {label}: {joined}")
    return "\n".join(lines)


def render_error(error: GuideError) -> str:
    lines = ["# Reference navigation error", "", str(error)]
    if error.candidates:
        lines.extend(["", _render_candidates(error.candidates)])
    return "\n".join(lines)


def _reference_meta(index: dict[str, Any], ref_id: str) -> dict[str, Any]:
    references = _require_mapping(index, "references")
    ref = references.get(ref_id)
    if not isinstance(ref, dict):
        raise GuideError(f"invalid ref: {ref_id}", {"ref": sorted(references)})
    if not isinstance(ref.get("path"), str) or not ref["path"].strip():
        raise GuideError(f"reference '{ref_id}' must define a non-empty path")
    return ref


def _reference_file(index: dict[str, Any], ref_id: str) -> Path:
    return _reference_path(str(_reference_meta(index, ref_id)["path"]))


def _domain_meta(index: dict[str, Any], domain_name: str) -> dict[str, Any]:
    domains = _domains(index)
    domain = domains.get(domain_name)
    if not isinstance(domain, dict):
        raise GuideError(f"invalid canonical domain name: {domain_name}", {"canonical-domain-name": sorted(domains)})
    if not isinstance(domain.get("ref"), str) or not str(domain["ref"]).strip():
        raise GuideError(f"domain '{domain_name}' must define a non-empty ref")
    return domain


def _domain_reference_file(index: dict[str, Any], domain_name: str) -> Path:
    return _reference_file(index, str(_domain_meta(index, domain_name)["ref"]))


def _topic_meta(index: dict[str, Any], topic_id: str) -> dict[str, Any]:
    topics = _topics(index)
    topic = topics.get(topic_id)
    if not isinstance(topic, dict):
        raise GuideError(f"invalid topic: {topic_id}", {"topic": sorted(topics)})
    if not isinstance(topic.get("ref"), str) or not str(topic["ref"]).strip():
        raise GuideError(f"topic '{topic_id}' must define a non-empty ref")
    return topic


def _topic_file(index: dict[str, Any], topic_id: str) -> Path:
    return _reference_file(index, str(_topic_meta(index, topic_id)["ref"]))


def _topic_applies(topic: dict[str, Any], stage_id: str, section_id: str) -> bool:
    stages = _as_str_list(topic.get("review_stages", []), "topic.review_stages")
    sections = _as_str_list(topic.get("paper_sections", []), "topic.paper_sections")
    return stage_id in stages and section_id in sections


def _topic_records(index: dict[str, Any], stage_id: str, section_id: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for topic_id, topic in sorted(_topics(index).items()):
        if not isinstance(topic, dict) or not _topic_applies(topic, stage_id, section_id):
            continue
        ref_id = str(topic["ref"])
        path = _reference_file(index, ref_id)
        for heading in _as_str_list(topic.get("headings", []), f"topics.{topic_id}.headings"):
            records.append(
                {
                    "topic": topic_id,
                    "label": str(topic.get("label", topic_id)),
                    "path": _display_path(path),
                    "heading": heading,
                }
            )
    return records


def _validate_route(index: dict[str, Any], domain_name: str | None, stage_id: str | None, section_id: str | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    candidates = _candidate_block(index)
    missing = [
        name
        for name, value in (
            ("canonical-domain-name", domain_name),
            ("review-stage", stage_id),
            ("paper-section", section_id),
        )
        if not value
    ]
    if missing:
        raise GuideError(f"missing required option(s): {', '.join(missing)}", candidates)

    domains = _domains(index)
    stages = _require_mapping(index, "review_stages")
    sections = _require_mapping(index, "paper_sections")
    assert domain_name is not None
    assert stage_id is not None
    assert section_id is not None

    invalid: list[str] = []
    if domain_name not in domains:
        invalid.append(f"domain={domain_name}")
    if stage_id not in stages:
        invalid.append(f"review-stage={stage_id}")
    if section_id not in sections:
        invalid.append(f"paper-section={section_id}")
    if invalid:
        raise GuideError(f"invalid route identifier(s): {', '.join(invalid)}", candidates)
    return domains[domain_name], stages[stage_id], sections[section_id]


def command_list(index: dict[str, Any]) -> str:
    domains = _domains(index)
    stages = _require_mapping(index, "review_stages")
    sections = _require_mapping(index, "paper_sections")

    lines = ["# Reference navigation identifiers", "", "## Canonical domain names"]
    for domain_name, domain in sorted(domains.items()):
        lines.append(f"- `{domain_name}`: {domain.get('label', domain_name)}")
    lines.append("")
    lines.append("## Review stages")
    for stage_id, stage in sorted(stages.items()):
        lines.append(f"- `{stage_id}`: {stage.get('label', stage_id)}")
    lines.append("")
    lines.append("## Paper sections")
    for section_id, section in sorted(sections.items()):
        lines.append(f"- `{section_id}`: {section.get('label', section_id)}")
    return "\n".join(lines)


def command_nav(index: dict[str, Any], domain_name: str | None, stage_id: str | None, section_id: str | None) -> str:
    domain, stage, section = _validate_route(index, domain_name, stage_id, section_id)
    assert domain_name is not None
    assert stage_id is not None
    assert section_id is not None

    records: list[dict[str, str]] = []

    def add(ref_id: str, heading: str, source: str, show_domain: str) -> None:
        path = _reference_file(index, ref_id)
        records.append(
            {
                "ref": ref_id,
                "path": _display_path(path),
                "heading": heading,
                "source": source,
                "show_domain": show_domain,
            }
        )

    taxonomy_ref = str(domain.get("taxonomy_ref", "taxonomy"))
    taxonomy_heading = domain.get("taxonomy_heading")
    if isinstance(taxonomy_heading, str) and taxonomy_heading.strip():
        add(taxonomy_ref, taxonomy_heading.strip(), "taxonomy", domain_name)

    general_ref = str(_require_mapping(index, "general").get("ref", "general"))
    for heading in _as_str_list(stage.get("general_headings", []), "review_stage.general_headings"):
        add(general_ref, heading, "general stage", "general")
    for heading in _as_str_list(section.get("general_headings", []), "paper_section.general_headings"):
        add(general_ref, heading, "general section", "general")

    domain_ref = str(domain.get("ref", domain_name))
    stage_headings = _require_mapping(domain, "stage_headings").get(stage_id, [])
    for heading in _as_str_list(stage_headings, "domain.stage_headings"):
        add(domain_ref, heading, "domain stage", domain_name)
    section_headings = _require_mapping(domain, "section_headings").get(section_id, [])
    for heading in _as_str_list(section_headings, "domain.section_headings"):
        add(domain_ref, heading, "domain section", domain_name)

    records = _dedupe_records(records)

    lines = [
        "# Reference navigation",
        "",
        f"- Canonical domain name: `{domain_name}`",
        f"- Domain label: {domain.get('label', domain_name)}",
        f"- Review stage: {stage.get('label', stage_id)} (`{stage_id}`)",
        f"- Paper section: {section.get('label', section_id)} (`{section_id}`)",
        "",
        "## Candidate reference headings",
    ]
    for record in records:
        if record["source"] == "taxonomy":
            show_command = f"python scripts/reference_guide.py taxonomy --domain {record['show_domain']}"
        else:
            show_command = f"python scripts/reference_guide.py show --domain {record['show_domain']} --heading \"{record['heading']}\""
        lines.extend(
            [
                f"- source: {record['source']}",
                f"  canonical_domain_name: `{record['show_domain']}`",
                f"  document: `{record['path']}`",
                f"  heading: `{record['heading']}`",
                f"  show: `{show_command}`",
            ]
        )

    topic_records = _topic_records(index, stage_id, section_id)
    if topic_records:
        lines.extend(["", "## Cross-cutting review topics"])
        for record in topic_records:
            show_command = f"python scripts/reference_guide.py topic show --topic {record['topic']} --heading \"{record['heading']}\""
            lines.extend(
                [
                    f"- topic: `{record['topic']}`",
                    f"  label: {record['label']}",
                    f"  document: `{record['path']}`",
                    f"  heading: `{record['heading']}`",
                    f"  show: `{show_command}`",
                ]
            )

    lines.extend(
        [
            "",
            "## Use rules",
            "- This command is an index navigator only; it does not summarize, rewrite, or generate review criteria.",
            "- Do not treat these headings as review findings or manuscript evidence.",
            "- Use `show` only for headings that are needed for the current blocker or review pass.",
            "- Do not open the whole `references/` directory or full long guide files by default.",
        ]
    )
    return "\n".join(lines)


def _resolve_domain_or_ref(index: dict[str, Any], domain_name: str | None, ref_id: str | None) -> tuple[str, str, Path, str]:
    if domain_name and ref_id:
        raise GuideError("use only one of --domain or --ref")
    if domain_name:
        domain = _domain_meta(index, domain_name)
        ref_id = str(domain["ref"])
        return domain_name, ref_id, _reference_file(index, ref_id), str(domain.get("label", domain_name))
    if ref_id:
        ref = _reference_meta(index, ref_id)
        return ref_id, ref_id, _reference_file(index, ref_id), str(ref.get("label", ref_id))
    raise GuideError("missing required option: --domain", {"canonical-domain-name": sorted(_domains(index))})


def command_toc(index: dict[str, Any], domain_name: str | None, ref_id: str | None = None) -> str:
    canonical_name, resolved_ref_id, path, label = _resolve_domain_or_ref(index, domain_name, ref_id)
    headings = _parse_headings(path)
    lines = [
        "# Reference table of contents",
        "",
        f"- canonical domain name: `{canonical_name}`",
        f"- label: {label}",
        f"- path: `{_display_path(path)}`",
        "",
        "## Headings",
    ]
    if ref_id and not domain_name:
        lines.insert(3, f"- compatibility ref: `{resolved_ref_id}`")
    for heading in headings:
        indent = "  " * max(heading.level - 1, 0)
        lines.append(f"{indent}- L{heading.line_no} H{heading.level} `{heading.text}`")
    return "\n".join(lines)


def command_show(index: dict[str, Any], domain_name: str | None, ref_id: str | None, exact_heading: str) -> str:
    canonical_name, resolved_ref_id, path, _label = _resolve_domain_or_ref(index, domain_name, ref_id)
    lines = _read_raw_lines(path)
    headings = _parse_headings(path)
    matches = [heading for heading in headings if heading.text == exact_heading]

    if not matches:
        nearby = [heading.text for heading in headings if exact_heading in heading.text or heading.text in exact_heading]
        fallback = nearby[:20] or [heading.text for heading in headings[:20]]
        raise GuideError(f"heading not found for canonical domain name '{canonical_name}': {exact_heading}", {"heading": fallback})
    if len(matches) > 1:
        locations = [f"L{heading.line_no} {heading.text}" for heading in matches]
        raise GuideError(f"heading is not unique for canonical domain name '{canonical_name}': {exact_heading}", {"matching-locations": locations})

    selected = matches[0]
    end_index = len(lines)
    for heading in headings:
        if heading.line_index <= selected.line_index:
            continue
        if heading.level <= selected.level:
            end_index = heading.line_index
            break
    return "".join(lines[selected.line_index:end_index])


def command_taxonomy(index: dict[str, Any], domain_name: str | None = None) -> str:
    domains = _domains(index)
    taxonomy_domains = {
        name: domain
        for name, domain in domains.items()
        if isinstance(domain, dict) and isinstance(domain.get("taxonomy_heading"), str) and domain["taxonomy_heading"].strip()
    }
    if domain_name is None:
        lines = ["# Paper taxonomy", "", "## Canonical domain names"]
        for name, domain in sorted(taxonomy_domains.items()):
            lines.append(f"- `{name}`: {domain.get('label', name)}")
        return "\n".join(lines)
    if domain_name not in taxonomy_domains:
        raise GuideError(
            f"invalid taxonomy canonical domain name: {domain_name}",
            {"canonical-domain-name": sorted(taxonomy_domains)},
        )
    domain = taxonomy_domains[domain_name]
    return command_show(index, None, str(domain.get("taxonomy_ref", "taxonomy")), str(domain["taxonomy_heading"]))


def command_topic_list(index: dict[str, Any]) -> str:
    lines = ["# Cross-cutting review topics", "", "## Topics"]
    for topic_id, topic in sorted(_topics(index).items()):
        if not isinstance(topic, dict):
            raise GuideError(f"topics.{topic_id} must be an object")
        lines.append(f"- `{topic_id}`: {topic.get('label', topic_id)}")
    return "\n".join(lines)


def command_topic_toc(index: dict[str, Any], topic_id: str) -> str:
    topic = _topic_meta(index, topic_id)
    path = _topic_file(index, topic_id)
    headings = _parse_headings(path)
    lines = [
        "# Topic table of contents",
        "",
        f"- topic: `{topic_id}`",
        f"- label: {topic.get('label', topic_id)}",
        f"- path: `{_display_path(path)}`",
        "",
        "## Headings",
    ]
    for heading in headings:
        indent = "  " * max(heading.level - 1, 0)
        lines.append(f"{indent}- L{heading.line_no} H{heading.level} `{heading.text}`")
    return "\n".join(lines)


def command_topic_show(index: dict[str, Any], topic_id: str, exact_heading: str) -> str:
    path = _topic_file(index, topic_id)
    lines = _read_raw_lines(path)
    headings = _parse_headings(path)
    matches = [heading for heading in headings if heading.text == exact_heading]

    if not matches:
        nearby = [heading.text for heading in headings if exact_heading in heading.text or heading.text in exact_heading]
        fallback = nearby[:20] or [heading.text for heading in headings[:20]]
        raise GuideError(f"heading not found for topic '{topic_id}': {exact_heading}", {"heading": fallback})
    if len(matches) > 1:
        locations = [f"L{heading.line_no} {heading.text}" for heading in matches]
        raise GuideError(f"heading is not unique for topic '{topic_id}': {exact_heading}", {"matching-locations": locations})

    selected = matches[0]
    end_index = len(lines)
    for heading in headings:
        if heading.line_index <= selected.line_index:
            continue
        if heading.level <= selected.level:
            end_index = heading.line_index
            break
    return "".join(lines[selected.line_index:end_index])


def _collect_index_headings(index: dict[str, Any]) -> dict[str, set[str]]:
    refs_to_headings: dict[str, set[str]] = {}

    def add(ref_id: str, headings: list[str]) -> None:
        refs_to_headings.setdefault(ref_id, set()).update(headings)

    general = _require_mapping(index, "general")
    add(str(general.get("ref", "general")), _as_str_list(general.get("headings", []), "general.headings"))

    for stage_id, stage in _require_mapping(index, "review_stages").items():
        add(str(general.get("ref", "general")), _as_str_list(stage.get("general_headings", []), f"review_stages.{stage_id}.general_headings"))

    for section_id, section in _require_mapping(index, "paper_sections").items():
        add(str(general.get("ref", "general")), _as_str_list(section.get("general_headings", []), f"paper_sections.{section_id}.general_headings"))

    for domain_id, domain in _domains(index).items():
        taxonomy_ref = str(domain.get("taxonomy_ref", "taxonomy"))
        taxonomy_heading = domain.get("taxonomy_heading")
        if taxonomy_heading is not None:
            if not isinstance(taxonomy_heading, str) or not taxonomy_heading.strip():
                raise GuideError(f"domains.{domain_id}.taxonomy_heading must be a non-empty string when present")
            add(taxonomy_ref, [taxonomy_heading.strip()])

        domain_ref = str(domain.get("ref", domain_id))
        for stage_id, headings in _require_mapping(domain, "stage_headings").items():
            add(domain_ref, _as_str_list(headings, f"domains.{domain_id}.stage_headings.{stage_id}"))
        for section_id, headings in _require_mapping(domain, "section_headings").items():
            add(domain_ref, _as_str_list(headings, f"domains.{domain_id}.section_headings.{section_id}"))

    for topic_id, topic in _topics(index).items():
        if not isinstance(topic, dict):
            raise GuideError(f"topics.{topic_id} must be an object")
        topic_ref = str(topic.get("ref", topic_id))
        _as_str_list(topic.get("review_stages", []), f"topics.{topic_id}.review_stages")
        _as_str_list(topic.get("paper_sections", []), f"topics.{topic_id}.paper_sections")
        add(topic_ref, _as_str_list(topic.get("headings", []), f"topics.{topic_id}.headings"))

    return refs_to_headings


def command_check(index: dict[str, Any]) -> str:
    if index.get("schema_version") != 2:
        raise GuideError("reference_index.json schema_version must be 2")

    references = _require_mapping(index, "references")
    for required in ("taxonomy", "general"):
        if required not in references:
            raise GuideError(f"references must include '{required}'")

    errors: list[str] = []
    for ref_id, ref in sorted(references.items()):
        if not isinstance(ref, dict):
            errors.append(f"references.{ref_id} must be an object")
            continue
        path_value = ref.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            errors.append(f"references.{ref_id}.path must be a non-empty string")
            continue
        path = _reference_path(path_value)
        if not path.exists():
            errors.append(f"missing file for ref '{ref_id}': {_display_path(path)}")

    indexed = _collect_index_headings(index)
    for ref_id, headings in sorted(indexed.items()):
        if ref_id not in references:
            errors.append(f"unknown ref in index mappings: {ref_id}")
            continue
        path = _reference_file(index, ref_id)
        if not path.exists():
            continue
        by_text = _headings_by_text(path)
        for heading in sorted(headings):
            matches = by_text.get(heading, [])
            if not matches:
                errors.append(f"missing heading in ref '{ref_id}': {heading}")
            elif len(matches) > 1:
                locations = ", ".join(f"L{match.line_no}" for match in matches)
                errors.append(f"duplicate indexed heading in ref '{ref_id}': {heading} ({locations})")

    if errors:
        raise GuideError("reference index check failed:\n" + "\n".join(f"- {error}" for error in errors))

    return "\n".join(
        [
            "# Reference index check",
            "",
            "OK",
            f"- index: `{_display_path(INDEX_PATH)}`",
            f"- references: {len(references)}",
            f"- indexed refs: {len(indexed)}",
            f"- indexed headings: {sum(len(headings) for headings in indexed.values())}",
        ]
    )


def command_guide_deprecated() -> str:
    return "\n".join(
        [
            "# Deprecated command",
            "",
            "`guide` no longer generates review instructions.",
            "",
            "Use these commands instead:",
            "",
            "- `list`: inspect valid identifiers.",
            "- `taxonomy`: inspect taxonomy canonical domain names.",
            "- `taxonomy --domain <canonical-domain-name>`: reveal one taxonomy section.",
            "- `topic list`: inspect cross-cutting review topics.",
            "- `topic toc --topic <topic-id>`: inspect one topic document's heading tree.",
            "- `topic show --topic <topic-id> --heading \"<exact-heading>\"`: reveal one topic section.",
            "- `nav --domain <canonical-domain-name> --review-stage <stage-id> --paper-section <section-id>`: find candidate reference headings.",
            "- `toc --domain <canonical-domain-name>`: inspect one guide document's heading tree.",
            "- `show --domain <canonical-domain-name> --heading \"<exact-heading>\"`: reveal one original Markdown section.",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Navigate paper-reviewer reference documents by canonical domain name without summarizing or rewriting them.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List canonical domain names, review stages, and paper sections.")
    subparsers.add_parser("check", help="Validate reference_index.json files, references, and headings.")

    taxonomy = subparsers.add_parser("taxonomy", help="List taxonomy entries or reveal one taxonomy section by canonical domain name.")
    taxonomy.add_argument("--domain", help="Canonical domain name for one taxonomy section.")

    topic = subparsers.add_parser("topic", help="List or reveal cross-cutting review topics.")
    topic_subparsers = topic.add_subparsers(dest="topic_command", required=True)
    topic_subparsers.add_parser("list", help="List cross-cutting review topics.")
    topic_toc = topic_subparsers.add_parser("toc", help="Return the heading table of contents for one topic document.")
    topic_toc.add_argument("--topic", required=True)
    topic_show = topic_subparsers.add_parser("show", help="Return the original Markdown under one exact topic heading.")
    topic_show.add_argument("--topic", required=True)
    topic_show.add_argument("--heading", required=True)

    guide = subparsers.add_parser("guide", help="Deprecated compatibility entry; use nav/toc/show instead.")
    guide.add_argument("--domain")
    guide.add_argument("--review-stage")
    guide.add_argument("--paper-section")

    nav = subparsers.add_parser("nav", help="Return candidate reference headings for one review route.")
    nav.add_argument("--domain", required=True, help="Canonical domain name, e.g. computational-algorithm-data-driven or general.")
    nav.add_argument("--review-stage", required=True)
    nav.add_argument("--paper-section", required=True)

    toc = subparsers.add_parser("toc", help="Return the heading table of contents for one guide document.")
    toc.add_argument("--domain", help="Canonical domain name, e.g. computational-algorithm-data-driven or general.")
    toc.add_argument("--ref", help=argparse.SUPPRESS)

    show = subparsers.add_parser("show", help="Return the original Markdown under one exact heading.")
    show.add_argument("--domain", help="Canonical domain name, e.g. computational-algorithm-data-driven or general.")
    show.add_argument("--ref", help=argparse.SUPPRESS)
    show.add_argument("--heading", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        index = _load_index()
        if args.command == "list":
            output = command_list(index)
        elif args.command == "check":
            output = command_check(index)
        elif args.command == "taxonomy":
            output = command_taxonomy(index, args.domain)
        elif args.command == "topic":
            if args.topic_command == "list":
                output = command_topic_list(index)
            elif args.topic_command == "toc":
                output = command_topic_toc(index, args.topic)
            elif args.topic_command == "show":
                output = command_topic_show(index, args.topic, args.heading)
            else:
                parser.error(f"unknown topic command: {args.topic_command}")
                return 2
        elif args.command == "guide":
            output = command_guide_deprecated()
        elif args.command == "nav":
            output = command_nav(index, args.domain, args.review_stage, args.paper_section)
        elif args.command == "toc":
            output = command_toc(index, args.domain, args.ref)
        elif args.command == "show":
            output = command_show(index, args.domain, args.ref, args.heading)
        else:
            parser.error(f"unknown command: {args.command}")
            return 2
    except GuideError as exc:
        print(render_error(exc), file=sys.stderr)
        return 2

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

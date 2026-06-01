from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-untyped]
except ModuleNotFoundError:  # pragma: no cover
    yaml = None


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_LOCALIZATION_DIR = PACKAGE_ROOT / "assets" / "localization"
PACKAGE_SOURCE_MESSAGES_PATH = PACKAGE_LOCALIZATION_DIR / "source-messages.yaml"
PACKAGE_MESSAGES_DIR = PACKAGE_LOCALIZATION_DIR / "messages"

LOCALIZATION_DIRNAME = "runtime-localization"
SOURCE_MESSAGES_FILENAME = "source-messages.yaml"
WORKING_MESSAGES_FILENAME = "working-messages.json"
DOCUMENT_MESSAGES_FILENAME = "document-messages.json"
TEMPLATE_OVERRIDE_DIRNAME = "templates"


DEFAULT_LANGUAGE_TAG = "en"
LANGUAGE_ALIASES = {
    "zh": "zh-CN",
    "zh-hans": "zh-CN",
    "zh-cn": "zh-CN",
    "zh-sg": "zh-CN",
    "zh-tw": "zh-CN",
    "zh-hant": "zh-CN",
    "en-us": "en",
    "en-gb": "en",
}


def ensure_yaml_available() -> None:
    if yaml is None:
        raise RuntimeError("missing Python dependency: PyYAML")


def load_yaml_mapping(path: Path) -> dict[str, str]:
    ensure_yaml_available()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"localization file must contain a mapping: {path}")
    return {str(key): str(value) for key, value in data.items()}


def load_json_mapping(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"localization file must contain a JSON object: {path}")
    return {str(key): str(value) for key, value in data.items()}


def dump_json(path: Path, payload: dict[str, str]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def dump_yaml(path: Path, payload: dict[str, str]) -> None:
    ensure_yaml_available()
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=True), encoding="utf-8")


def localization_paths(artifact_root: Path) -> dict[str, Path]:
    root = artifact_root / LOCALIZATION_DIRNAME
    return {
        "root": root,
        "source_messages": root / SOURCE_MESSAGES_FILENAME,
        "working_messages": root / WORKING_MESSAGES_FILENAME,
        "document_messages": root / DOCUMENT_MESSAGES_FILENAME,
        "template_override_dir": root / TEMPLATE_OVERRIDE_DIRNAME,
    }


def canonical_language_tag(tag: str) -> str:
    value = tag.strip()
    if not value:
        return DEFAULT_LANGUAGE_TAG
    lowered = value.lower()
    return LANGUAGE_ALIASES.get(lowered, value)


def resolve_packaged_catalog_path(language_tag: str) -> Path | None:
    canonical = canonical_language_tag(language_tag)
    candidates = [canonical]
    if "-" in canonical:
        candidates.append(canonical.split("-", 1)[0])
    if canonical.lower() in LANGUAGE_ALIASES:
        candidates.append(LANGUAGE_ALIASES[canonical.lower()])
    if canonical.split("-", 1)[0] == "zh":
        candidates.append("zh-CN")
    candidates.append(DEFAULT_LANGUAGE_TAG)

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        path = PACKAGE_MESSAGES_DIR / f"{candidate}.json"
        if path.exists():
            return path
    return None


def packaged_source_messages() -> dict[str, str]:
    default_catalog_path = resolve_packaged_catalog_path(DEFAULT_LANGUAGE_TAG)
    if default_catalog_path is None:
        raise RuntimeError("missing default packaged localization catalog")
    return load_json_mapping(default_catalog_path)


def packaged_messages(language_tag: str) -> dict[str, str]:
    source = packaged_source_messages()
    path = resolve_packaged_catalog_path(language_tag)
    if path is None:
        return source
    catalog = load_json_mapping(path)
    return {**source, **catalog}


def seed_workspace_localization_overlay(
    artifact_root: Path,
    *,
    working_language: str,
    document_language: str,
) -> dict[str, Path]:
    paths = localization_paths(artifact_root)
    paths["root"].mkdir(parents=True, exist_ok=True)
    paths["template_override_dir"].mkdir(parents=True, exist_ok=True)
    source = packaged_source_messages()
    dump_yaml(paths["source_messages"], source)
    dump_json(paths["working_messages"], packaged_messages(working_language))
    dump_json(paths["document_messages"], packaged_messages(document_language))
    return paths


def fetch_runtime_language_context(connection: sqlite3.Connection) -> dict[str, str]:
    defaults = {
        "document_language": DEFAULT_LANGUAGE_TAG,
        "working_language": DEFAULT_LANGUAGE_TAG,
        "manuscript_detected_language": "",
        "review_comments_detected_language": "",
        "prompt_detected_language": "",
        "document_language_source": "",
        "working_language_source": "",
        "languages_confirmed": "no",
    }
    try:
        row = connection.execute(
            """
            SELECT document_language, working_language, manuscript_detected_language,
                   review_comments_detected_language, prompt_detected_language,
                   document_language_source, working_language_source, languages_confirmed
            FROM runtime_language_context
            WHERE id = 1
            """
        ).fetchone()
    except sqlite3.OperationalError:
        return defaults
    if row is None:
        return defaults
    payload = defaults.copy()
    for key in payload:
        value = row[key]
        if value is not None and str(value).strip():
            payload[key] = str(value)
    return payload


@dataclass(frozen=True)
class LocalizationBundle:
    working_language: str
    document_language: str
    source_messages: dict[str, str]
    working_messages: dict[str, str]
    document_messages: dict[str, str]
    template_dirs: list[Path]
    runtime_context: dict[str, str]

    def msg(self, key: str, *, target: str = "working", **kwargs: Any) -> str:
        if target == "document":
            catalog = self.document_messages
        else:
            catalog = self.working_messages
        text = catalog.get(key) or self.source_messages.get(key) or key
        if kwargs:
            return text.format(**kwargs)
        return text

    def snapshot(self) -> dict[str, str]:
        return dict(self.runtime_context)


def load_localization_bundle(
    artifact_root: Path,
    *,
    runtime_context: dict[str, str] | None = None,
) -> LocalizationBundle:
    context = dict(runtime_context or {})
    working_language = context.get("working_language", DEFAULT_LANGUAGE_TAG) or DEFAULT_LANGUAGE_TAG
    document_language = context.get("document_language", DEFAULT_LANGUAGE_TAG) or DEFAULT_LANGUAGE_TAG
    source = packaged_source_messages()
    working_messages = packaged_messages(working_language)
    document_messages = packaged_messages(document_language)
    paths = localization_paths(artifact_root)
    if paths["working_messages"].exists():
        working_messages = {**working_messages, **load_json_mapping(paths["working_messages"])}
    if paths["document_messages"].exists():
        document_messages = {**document_messages, **load_json_mapping(paths["document_messages"])}
    if paths["source_messages"].exists():
        source = {**source, **load_yaml_mapping(paths["source_messages"])}
    template_dirs = [paths["template_override_dir"], PACKAGE_ROOT / "assets" / "templates"]
    return LocalizationBundle(
        working_language=working_language,
        document_language=document_language,
        source_messages=source,
        working_messages=working_messages,
        document_messages=document_messages,
        template_dirs=template_dirs,
        runtime_context={
            "document_language": document_language,
            "working_language": working_language,
            "manuscript_detected_language": context.get("manuscript_detected_language", ""),
            "review_comments_detected_language": context.get("review_comments_detected_language", ""),
            "prompt_detected_language": context.get("prompt_detected_language", ""),
            "document_language_source": context.get("document_language_source", ""),
            "working_language_source": context.get("working_language_source", ""),
            "languages_confirmed": context.get("languages_confirmed", "no"),
        },
    )

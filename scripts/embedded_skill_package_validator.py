#!/usr/bin/env python3
"""Runtime-independent validator aligned with upstream SkillPackageValidator behavior."""

from __future__ import annotations

import io
import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any, Optional, Tuple

import jsonschema  # type: ignore[import-untyped]
import yaml  # type: ignore[import-untyped]

_packaging_version: Any = None
try:
    import packaging.version as _packaging_version  # type: ignore
except ImportError:  # pragma: no cover
    _packaging_version = None


class EmbeddedSkillPackageValidator:
    """Runtime-independent validator equivalent to current install-time checks."""

    REQUIRED_FILES = (
        "SKILL.md",
        "assets/runner.json",
    )
    ALLOWED_ENGINES = ("codex", "gemini", "iflow", "opencode")
    SCHEMA_META_FILES = {
        "input": "skill_input_schema.schema.json",
        "parameter": "skill_parameter_schema.schema.json",
        "output": "skill_output_schema.schema.json",
    }
    CONTRACT_SCHEMAS: dict[str, dict[str, Any]] = {
        "skill_runner_manifest.schema.json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://skill-runner.local/schemas/skill_runner_manifest.schema.json",
            "type": "object",
            "required": ["id", "schemas", "execution_modes"],
            "properties": {
                "id": {"type": "string", "minLength": 1},
                "version": {"type": "string", "minLength": 1},
                "engines": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/engine"},
                    "minItems": 1,
                    "uniqueItems": True,
                },
                "unsupported_engines": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/engine"},
                    "minItems": 1,
                    "uniqueItems": True,
                },
                "execution_modes": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["auto", "interactive"]},
                    "minItems": 1,
                    "uniqueItems": True,
                },
                "max_attempt": {"type": "integer", "minimum": 1},
                "schemas": {
                    "type": "object",
                    "required": ["input", "parameter", "output"],
                    "properties": {
                        "input": {"type": "string", "minLength": 1},
                        "parameter": {"type": "string", "minLength": 1},
                        "output": {"type": "string", "minLength": 1},
                    },
                    "additionalProperties": True,
                },
                "artifacts": {"type": "array"},
            },
            "additionalProperties": True,
            "$defs": {
                "engine": {
                    "type": "string",
                    "enum": ["codex", "gemini", "iflow", "opencode"],
                }
            },
        },
        "skill_input_schema.schema.json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://skill-runner.local/schemas/skill_input_schema.schema.json",
            "type": "object",
            "properties": {
                "type": {"const": "object"},
                "properties": {
                    "type": "object",
                    "additionalProperties": {"$ref": "#/$defs/inputProperty"},
                },
                "required": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["type"],
            "additionalProperties": True,
            "$defs": {
                "inputProperty": {
                    "type": "object",
                    "properties": {
                        "x-input-source": {
                            "type": "string",
                            "enum": ["file", "inline"],
                        },
                        "extensions": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "additionalProperties": True,
                }
            },
        },
        "skill_parameter_schema.schema.json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://skill-runner.local/schemas/skill_parameter_schema.schema.json",
            "type": "object",
            "properties": {
                "type": {"const": "object"},
                "properties": {
                    "type": "object",
                    "additionalProperties": {"type": "object"},
                },
                "required": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["type"],
            "additionalProperties": True,
        },
        "skill_output_schema.schema.json": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://skill-runner.local/schemas/skill_output_schema.schema.json",
            "type": "object",
            "properties": {
                "type": {"const": "object"},
                "properties": {
                    "type": "object",
                    "additionalProperties": {"$ref": "#/$defs/outputProperty"},
                },
                "required": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["type"],
            "additionalProperties": True,
            "$defs": {
                "outputProperty": {
                    "type": "object",
                    "properties": {
                        "x-type": {
                            "type": "string",
                            "enum": ["artifact", "file"],
                        },
                        "x-role": {"type": "string", "minLength": 1},
                        "x-filename": {"type": "string", "minLength": 1},
                    },
                    "additionalProperties": True,
                }
            },
        },
    }

    def inspect_zip_top_level_from_bytes(self, payload: bytes) -> str:
        try:
            with zipfile.ZipFile(io.BytesIO(payload), "r") as zf:
                return self.inspect_zip_top_level(zf.namelist())
        except zipfile.BadZipFile as exc:
            raise ValueError("Invalid zip package") from exc

    def inspect_zip_top_level_from_path(self, package_path: Path) -> str:
        try:
            with zipfile.ZipFile(package_path, "r") as zf:
                return self.inspect_zip_top_level(zf.namelist())
        except zipfile.BadZipFile as exc:
            raise ValueError("Invalid zip package") from exc

    def inspect_zip_top_level(self, names: list[str]) -> str:
        top_levels = set()
        for name in names:
            clean = name.strip("/")
            if not clean:
                continue
            self._validate_zip_entry(clean)
            top = clean.split("/", 1)[0]
            if top == "__MACOSX":
                continue
            top_levels.add(top)
        if len(top_levels) != 1:
            raise ValueError("Skill package must contain exactly one top-level directory")
        return next(iter(top_levels))

    def extract_zip_safe(self, package_path: Path, target_dir: Path) -> None:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_root = target_dir.resolve()
        try:
            with zipfile.ZipFile(package_path, "r") as zf:
                for member in zf.infolist():
                    clean = member.filename.strip("/")
                    if not clean or clean.startswith("__MACOSX/"):
                        continue
                    self._validate_zip_entry(clean)
                    out_path = (target_dir / clean).resolve()
                    if not str(out_path).startswith(str(target_root)):
                        raise ValueError(f"Unsafe zip entry path: {clean}")
                    if member.is_dir():
                        out_path.mkdir(parents=True, exist_ok=True)
                        continue
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member, "r") as src, open(out_path, "wb") as dst:
                        dst.write(src.read())
        except zipfile.BadZipFile as exc:
            raise ValueError("Invalid zip package") from exc

    def validate_skill_dir(
        self,
        skill_dir: Path,
        top_level_dir: str,
        *,
        require_version: bool,
    ) -> Tuple[str, Optional[str]]:
        missing: list[str] = []
        for rel in self.REQUIRED_FILES:
            if not (skill_dir / rel).exists():
                missing.append(rel)
        if missing:
            raise ValueError(f"Skill package missing required files: {', '.join(missing)}")

        runner_path = skill_dir / "assets" / "runner.json"
        try:
            runner = json.loads(runner_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid assets/runner.json") from exc
        self._validate_runner_schema(runner)
        self._apply_engine_policy_to_manifest(runner)

        runner_id = runner.get("id")
        if not isinstance(runner_id, str) or not runner_id.strip():
            raise ValueError("runner.json must define a non-empty id")
        skill_id = runner_id.strip()

        skill_name = self._extract_skill_name(skill_dir / "SKILL.md")
        if not skill_name:
            raise ValueError("SKILL.md must define frontmatter name")
        if skill_id != top_level_dir or skill_name != skill_id:
            raise ValueError(
                "Skill identity mismatch: directory, runner.json id, and SKILL.md name must match"
            )

        schemas = runner.get("schemas")
        if not isinstance(schemas, dict):
            raise ValueError("runner.json must define schemas")
        for key in ("input", "parameter", "output"):
            schema_rel = schemas.get(key)
            if not isinstance(schema_rel, str) or not schema_rel.strip():
                raise ValueError("runner.json schemas must define input, parameter and output")
            schema_path = skill_dir / schema_rel
            if not schema_path.exists():
                missing.append(schema_rel)
                continue
            self._validate_skill_schema_file(schema_path, schema_key=key)
        if missing:
            raise ValueError(f"Skill package missing required files: {', '.join(missing)}")

        self._validate_execution_modes(runner)

        version = runner.get("version")
        if require_version:
            if not isinstance(version, str) or not version.strip():
                raise ValueError("runner.json must define a non-empty version")
            version = version.strip()
            self.parse_version(version)
        elif isinstance(version, str) and version.strip():
            version = version.strip()
            self.parse_version(version)
        else:
            version = None

        return skill_id, version

    def _validate_runner_schema(self, runner: dict[str, Any]) -> None:
        schema = self.CONTRACT_SCHEMAS["skill_runner_manifest.schema.json"]
        try:
            jsonschema.validate(instance=runner, schema=schema)
        except jsonschema.ValidationError as exc:
            raise ValueError(f"Invalid runner.json manifest: {exc.message}") from exc

    def _validate_skill_schema_file(self, schema_path: Path, *, schema_key: str) -> None:
        meta_filename = self.SCHEMA_META_FILES.get(schema_key)
        if not meta_filename:
            return
        meta_schema = self.CONTRACT_SCHEMAS[meta_filename]
        try:
            schema_payload = json.loads(schema_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid {schema_key} schema: not valid JSON") from exc
        try:
            jsonschema.validate(instance=schema_payload, schema=meta_schema)
        except jsonschema.ValidationError as exc:
            raise ValueError(f"Invalid {schema_key} schema: {exc.message}") from exc

    def _validate_execution_modes(self, runner: dict[str, Any]) -> None:
        execution_modes = runner.get("execution_modes")
        if not isinstance(execution_modes, list) or not execution_modes:
            raise ValueError("runner.json must define a non-empty execution_modes list")
        allowed = {"auto", "interactive"}
        normalized: list[str] = []
        for mode in execution_modes:
            if not isinstance(mode, str) or mode not in allowed:
                raise ValueError("runner.json execution_modes must contain only: auto, interactive")
            normalized.append(mode)
        runner["execution_modes"] = normalized

    def _apply_engine_policy_to_manifest(self, manifest: dict[str, Any]) -> None:
        if "unsupport_engine" in manifest:
            raise ValueError(
                "runner.json field 'unsupport_engine' has been renamed to 'unsupported_engines'"
            )
        declared = self._normalize_engine_list(manifest.get("engines"), "engines")
        unsupported = self._normalize_engine_list(
            manifest.get("unsupported_engines"),
            "unsupported_engines",
        )

        allowed_set = set(self.ALLOWED_ENGINES)
        unknown = sorted((set(declared) | set(unsupported)) - allowed_set)
        if unknown:
            raise ValueError(
                "runner.json engines/unsupported_engines must contain only: "
                + ", ".join(self.ALLOWED_ENGINES)
            )

        overlap = sorted(set(declared) & set(unsupported))
        if overlap:
            raise ValueError(
                "runner.json engines and unsupported_engines must not overlap: "
                + ", ".join(overlap)
            )

        declared_base = declared if declared else list(self.ALLOWED_ENGINES)
        deny_set = set(unsupported)
        effective = [engine for engine in declared_base if engine not in deny_set]
        if not effective:
            raise ValueError("runner.json effective engines must not be empty")

        manifest["engines"] = declared
        manifest["unsupported_engines"] = unsupported
        manifest["effective_engines"] = effective

    def _normalize_engine_list(self, raw: Any, field_name: str) -> list[str]:
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise ValueError(f"runner.json {field_name} must be a list when provided")
        normalized: list[str] = []
        for item in raw:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"runner.json {field_name} must contain non-empty strings")
            normalized.append(item.strip())
        return list(dict.fromkeys(normalized))

    def parse_version(self, raw: str) -> Any:
        if _packaging_version is not None:
            try:
                return _packaging_version.Version(raw)
            except _packaging_version.InvalidVersion as exc:
                raise ValueError(f"Invalid skill version: {raw}") from exc

        if not re.match(r"^\d+(\.\d+)*$", raw):
            raise ValueError(f"Invalid skill version: {raw}")
        return tuple(int(part) for part in raw.split("."))

    def ensure_version_upgrade(self, old_version: str, new_version: str) -> None:
        old_parsed = self.parse_version(old_version)
        new_parsed = self.parse_version(new_version)
        if new_parsed <= old_parsed:
            raise ValueError(
                f"Skill update requires strictly higher version: installed={old_version}, uploaded={new_version}"
            )

    def _extract_skill_name(self, skill_md_path: Path) -> Optional[str]:
        content = skill_md_path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
        if not match:
            return None
        frontmatter = yaml.safe_load(match.group(1)) or {}
        name = frontmatter.get("name")
        if not isinstance(name, str):
            return None
        return name.strip() or None

    def _validate_zip_entry(self, clean_name: str) -> None:
        if clean_name.startswith("/") or clean_name.startswith("\\"):
            raise ValueError(f"Unsafe zip entry path: {clean_name}")
        p = Path(clean_name)
        if p.is_absolute():
            raise ValueError(f"Unsafe zip entry path: {clean_name}")
        parts = p.parts
        if any(part == ".." for part in parts):
            raise ValueError(f"Unsafe zip entry path: {clean_name}")
        if len(parts) > 0 and parts[0].endswith(":"):
            raise ValueError(f"Unsafe zip entry path: {clean_name}")

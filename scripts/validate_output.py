from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DIGEST_FILENAME = "digest.md"
REFERENCES_FILENAME = "references.json"
CITATION_ANALYSIS_FILENAME = "citation_analysis.json"


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(chunk)
    return f"sha256:{sha.hexdigest()}"


def _is_utc_iso8601_z(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value))


def _as_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    if isinstance(value, str):
        return [value]
    return [str(value)]


def _as_int_or_none(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer():
            return int(value)
        return None
    if isinstance(value, str):
        s = value.strip()
        if re.fullmatch(r"(19|20)\d{2}", s):
            return int(s)
        return None
    return None


def _as_confidence(value: object, default: float = 0.1) -> float:
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        f = float(value)
        if not math.isfinite(f):
            return default
        return float(min(1.0, max(0.0, f)))
    if isinstance(value, str):
        try:
            f = float(value.strip())
            if not math.isfinite(f):
                return default
            return float(min(1.0, max(0.0, f)))
        except ValueError:
            return default
    return default


def _ensure_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_output_root(explicit_out_dir: Path | None, source_path: Path | None) -> Path:
    # Strategy (to avoid sandbox escapes in some agents):
    # 1) Use the input source_path directory (preferred, if available)
    # 2) Explicit CLI --out-dir
    # 3) Env var LITERATURE_DIGEST_OUTPUT_DIR (plugin can set)
    # 4) OS temp dir
    if source_path is not None:
        return source_path.parent
    if explicit_out_dir is not None:
        return explicit_out_dir
    env = os.environ.get("LITERATURE_DIGEST_OUTPUT_DIR")
    if env:
        return Path(env).expanduser()
    # Last resort fallback (should be avoided when source_path is available).
    return Path.cwd()


def _normalize_reference_item(item: object, *, fix: bool, warnings: list[str]) -> dict[str, Any]:
    if isinstance(item, str):
        if not fix:
            return {}
        return {"raw": item}
    if not isinstance(item, dict):
        return {}

    out: dict[str, Any] = dict(item)

    if "doi" in out and "DOI" not in out and fix:
        out["DOI"] = out.pop("doi")
        warnings.append("references: migrated field 'doi' -> 'DOI'")

    if fix:
        out.setdefault("author", [])
        out.setdefault("title", "")
        out.setdefault("year", None)
        out.setdefault("raw", "")
        out.setdefault("confidence", 0.1)

    out["author"] = _as_str_list(out.get("author"))
    out["title"] = "" if out.get("title") is None else str(out.get("title"))
    out["year"] = _as_int_or_none(out.get("year"))
    out["raw"] = "" if out.get("raw") is None else str(out.get("raw"))
    out["confidence"] = _as_confidence(out.get("confidence"), default=0.1)

    creators = out.get("creators")
    if creators is not None and not isinstance(creators, list) and fix:
        out["creators"] = []
        warnings.append("references: coerced non-list 'creators' to []")

    return out


def _normalize_citation_analysis_obj(
    obj: object,
    *,
    fix: bool,
    warnings: list[str],
    language_hint: str | None,
) -> dict[str, Any] | None:
    if isinstance(obj, str):
        s = obj.strip()
        if not s:
            return None
        if not (s.startswith("{") and s.endswith("}")):
            return None
        try:
            obj = json.loads(s)
        except Exception:  # noqa: BLE001
            return None

    if not isinstance(obj, dict):
        return None

    out: dict[str, Any] = dict(obj)

    if fix:
        meta = _ensure_dict(out.get("meta"))
        scope = _ensure_dict(meta.get("scope"))

        meta.setdefault("language", language_hint or "")
        scope.setdefault("section_title", "Introduction")
        scope.setdefault("line_start", 0)
        scope.setdefault("line_end", 0)
        meta["scope"] = scope
        out["meta"] = meta

        out.setdefault("items", [])
        out.setdefault("unmapped_mentions", [])
        out.setdefault("report_md", "")

    return out


def _validate_citation_analysis_obj(obj: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["citation_analysis must be a JSON object"]

    meta = obj.get("meta")
    if not isinstance(meta, dict):
        errors.append("citation_analysis.meta must be object")
        meta = {}

    language = meta.get("language")
    if not isinstance(language, str):
        errors.append("citation_analysis.meta.language must be string")

    scope = meta.get("scope")
    if not isinstance(scope, dict):
        errors.append("citation_analysis.meta.scope must be object")
        scope = {}

    section_title = scope.get("section_title")
    if not isinstance(section_title, str):
        errors.append("citation_analysis.meta.scope.section_title must be string")

    line_start = _as_int_or_none(scope.get("line_start"))
    line_end = _as_int_or_none(scope.get("line_end"))
    if line_start is None or line_end is None:
        errors.append("citation_analysis.meta.scope.line_start/line_end must be int")

    scope_valid = (
        line_start is not None
        and line_end is not None
        and line_start > 0
        and line_end > 0
        and line_start <= line_end
    )

    items = obj.get("items")
    if not isinstance(items, list):
        errors.append("citation_analysis.items must be array")
        items = []

    unmapped = obj.get("unmapped_mentions")
    if not isinstance(unmapped, list):
        errors.append("citation_analysis.unmapped_mentions must be array")
        unmapped = []

    report_md = obj.get("report_md")
    if not isinstance(report_md, str):
        errors.append("citation_analysis.report_md must be string")

    all_mentions: list[tuple[str, dict[str, Any]]] = []

    def validate_mentions_array(container: object, *, path: str) -> None:
        if not isinstance(container, list):
            return
        for i, mention in enumerate(container):
            if not isinstance(mention, dict):
                errors.append(f"{path}[{i}] must be object")
                continue
            all_mentions.append((f"{path}[{i}]", mention))
            ms = _as_int_or_none(mention.get("line_start"))
            me = _as_int_or_none(mention.get("line_end"))
            if ms is None or me is None:
                continue
            if scope_valid and not (line_start <= ms <= me <= line_end):  # type: ignore[operator]
                errors.append(f"{path}[{i}].line_start/line_end out of meta.scope range")

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"citation_analysis.items[{i}] must be object")
            continue
        for field_name in ["ref_index", "mentions", "function", "summary", "confidence"]:
            if field_name not in item:
                errors.append(f"citation_analysis.items[{i}] missing field: {field_name}")
        mentions = item.get("mentions")
        validate_mentions_array(mentions, path=f"citation_analysis.items[{i}].mentions")

    validate_mentions_array(unmapped, path="citation_analysis.unmapped_mentions")

    mention_ids: list[str] = []
    for path, mention in all_mentions:
        mention_id = mention.get("mention_id")
        marker = mention.get("marker")
        style = mention.get("style")
        snippet = mention.get("snippet")
        if not isinstance(mention_id, str) or not mention_id.strip():
            errors.append(f"{path}.mention_id must be non-empty string")
        else:
            mention_ids.append(mention_id)
        if not isinstance(marker, str):
            errors.append(f"{path}.marker must be string")
        if style not in ("numeric", "author-year", "unknown"):
            errors.append(f"{path}.style must be one of numeric/author-year/unknown")
        if not isinstance(snippet, str):
            errors.append(f"{path}.snippet must be string")
        if _as_int_or_none(mention.get("line_start")) is None:
            errors.append(f"{path}.line_start must be int")
        if _as_int_or_none(mention.get("line_end")) is None:
            errors.append(f"{path}.line_end must be int")

    if len(mention_ids) != len(set(mention_ids)):
        errors.append("citation_analysis mention_id must be unique across items and unmapped_mentions")

    return errors


def _extract_preprocess_expected_mentions(preprocess_artifact: Path | None) -> tuple[int | None, str | None]:
    if preprocess_artifact is None:
        return None, None
    if not preprocess_artifact.exists():
        return None, f"preprocess artifact does not exist: {preprocess_artifact}"
    try:
        obj = json.loads(preprocess_artifact.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return None, f"preprocess artifact unreadable JSON: {e}"
    if not isinstance(obj, dict):
        return None, "preprocess artifact must be a JSON object"
    stats = obj.get("stats")
    if not isinstance(stats, dict):
        return None, "preprocess artifact missing object: stats"
    expected = _as_int_or_none(stats.get("total_mentions"))
    if expected is None:
        return None, "preprocess artifact stats.total_mentions must be int"
    return expected, None


def _count_citation_mentions(citation_analysis_obj: object) -> int | None:
    if not isinstance(citation_analysis_obj, dict):
        return None
    items = citation_analysis_obj.get("items")
    unmapped = citation_analysis_obj.get("unmapped_mentions")
    if not isinstance(items, list) or not isinstance(unmapped, list):
        return None
    total = 0
    for item in items:
        if not isinstance(item, dict):
            return None
        mentions = item.get("mentions")
        if not isinstance(mentions, list):
            return None
        total += len(mentions)
    total += len(unmapped)
    return total


def _validate_references_items(items: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(items, list):
        return ["references must be a JSON array"]
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"references[{i}] must be object")
            continue
        author = item.get("author")
        if not isinstance(author, list) or any(not isinstance(a, str) for a in author):
            errors.append(f"references[{i}].author must be string[]")
        if not isinstance(item.get("title"), str):
            errors.append(f"references[{i}].title must be string")
        year = item.get("year")
        if year is not None and not isinstance(year, int):
            errors.append(f"references[{i}].year must be int|null")
        if not isinstance(item.get("raw"), str):
            errors.append(f"references[{i}].raw must be string")
        conf = item.get("confidence")
        if not isinstance(conf, (int, float)):
            errors.append(f"references[{i}].confidence must be number")
    return errors


def _materialize_outputs(
    out: dict[str, Any],
    *,
    fix: bool,
    warnings: list[str],
    output_root: Path,
) -> None:
    if not fix:
        return

    digest_content: str | None = None
    if "digest_path" not in out or not out.get("digest_path"):
        if isinstance(out.get("digest"), str):
            digest_content = out["digest"]
            warnings.append("digest: materialized to digest_path")
        elif isinstance(out.get("digest"), dict) and "md" in out["digest"]:
            digest_content = "" if out["digest"]["md"] is None else str(out["digest"]["md"])
            warnings.append("digest: migrated object {md} and materialized to digest_path")
        elif "digest.md" in out:
            digest_content = "" if out["digest.md"] is None else str(out["digest.md"])
            warnings.append("digest: migrated field 'digest.md' and materialized to digest_path")

    references_items: list[object] | None = None
    if "references_path" not in out or not out.get("references_path"):
        if isinstance(out.get("references"), list):
            references_items = out["references"]
            warnings.append("references: materialized to references_path")
        elif isinstance(out.get("references"), dict) and "items" in out["references"]:
            references_items = out["references"]["items"]
            warnings.append("references: migrated object {items} and materialized to references_path")
        elif "references.items" in out:
            references_items = out["references.items"]
            warnings.append("references: migrated field 'references.items' and materialized to references_path")

    citation_analysis_obj: dict[str, Any] | None = None
    if "citation_analysis_path" not in out or not out.get("citation_analysis_path"):
        citation_analysis_obj = _normalize_citation_analysis_obj(
            out.get("citation_analysis"),
            fix=True,
            warnings=warnings,
            language_hint=str(out.get("language")) if isinstance(out.get("language"), str) else None,
        )
        if citation_analysis_obj is None and "citation_analysis.json" in out:
            citation_analysis_obj = _normalize_citation_analysis_obj(
                out.get("citation_analysis.json"),
                fix=True,
                warnings=warnings,
                language_hint=str(out.get("language")) if isinstance(out.get("language"), str) else None,
            )
        if citation_analysis_obj is not None:
            warnings.append("citation_analysis: materialized to citation_analysis_path")

    if digest_content is None and references_items is None and citation_analysis_obj is None:
        return

    output_root.mkdir(parents=True, exist_ok=True)
    if digest_content is not None:
        digest_file = output_root / DIGEST_FILENAME
        _write_text(digest_file, digest_content)
        out["digest_path"] = str(digest_file)
        out.pop("digest", None)
        out.pop("digest.md", None)

    if references_items is not None:
        normalized_items: list[dict[str, Any]] = []
        if isinstance(references_items, list):
            for item in references_items:
                normalized_items.append(_normalize_reference_item(item, fix=True, warnings=warnings))
        refs_file = output_root / REFERENCES_FILENAME
        _write_json(refs_file, normalized_items)
        out["references_path"] = str(refs_file)
        out.pop("references", None)
        out.pop("references.items", None)

    if citation_analysis_obj is not None:
        ca_file = output_root / CITATION_ANALYSIS_FILENAME
        _write_json(ca_file, citation_analysis_obj)
        out["citation_analysis_path"] = str(ca_file)
        out.pop("citation_analysis", None)
        out.pop("citation_analysis.json", None)


def _normalize_top_level(
    obj: object,
    *,
    fix: bool,
    source_path: Path | None,
    output_root: Path,
    preprocess_artifact: Path | None = None,
) -> tuple[dict[str, Any], list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []

    if not isinstance(obj, dict):
        if not fix:
            return {}, warnings, ["output is not a JSON object"]
        obj = {}
        errors.append("output is not a JSON object; replaced with empty object")

    out: dict[str, Any] = dict(obj)

    if fix:
        out.setdefault("provenance", {"generated_at": "", "input_hash": "", "model": ""})
        out.setdefault("warnings", [])
        out.setdefault("error", None)

        _materialize_outputs(out, fix=True, warnings=warnings, output_root=output_root)

        out.setdefault("digest_path", "")
        out.setdefault("references_path", "")
        out.setdefault("citation_analysis_path", "")

        if "schema_version" in out:
            out.pop("schema_version", None)
            warnings.append("removed legacy field 'schema_version'")
        if "parent_itemKey" in out:
            out.pop("parent_itemKey", None)
            warnings.append("removed legacy field 'parent_itemKey'")
        if "md_attachment_key" in out:
            out.pop("md_attachment_key", None)
            warnings.append("removed legacy field 'md_attachment_key'")

    for required_key in [
        "digest_path",
        "references_path",
        "citation_analysis_path",
        "provenance",
        "warnings",
        "error",
    ]:
        if required_key not in out:
            errors.append(f"missing required key: {required_key}")

    if not isinstance(out.get("digest_path"), str):
        errors.append("digest_path must be string")
        if fix:
            out["digest_path"] = "" if out.get("digest_path") is None else str(out.get("digest_path"))
            warnings.append("digest_path coerced to string")

    if not isinstance(out.get("references_path"), str):
        errors.append("references_path must be string")
        if fix:
            out["references_path"] = "" if out.get("references_path") is None else str(out.get("references_path"))
            warnings.append("references_path coerced to string")

    if not isinstance(out.get("citation_analysis_path"), str):
        errors.append("citation_analysis_path must be string")
        if fix:
            out["citation_analysis_path"] = (
                "" if out.get("citation_analysis_path") is None else str(out.get("citation_analysis_path"))
            )
            warnings.append("citation_analysis_path coerced to string")

    prov = _ensure_dict(out.get("provenance"))
    if fix:
        prov.setdefault("generated_at", "")
        prov.setdefault("input_hash", "")
        prov.setdefault("model", "")
    out["provenance"] = prov

    if not _is_utc_iso8601_z(prov.get("generated_at")):
        errors.append("provenance.generated_at must be UTC ISO-8601 (YYYY-MM-DDTHH:MM:SSZ)")
        if fix:
            prov["generated_at"] = utc_now_iso()
            warnings.append("provenance.generated_at regenerated")

    input_hash = prov.get("input_hash")
    if not isinstance(input_hash, str) or (input_hash and not input_hash.startswith("sha256:")):
        errors.append("provenance.input_hash must be 'sha256:<hex>' or ''")
        if fix:
            prov["input_hash"] = ""
            warnings.append("provenance.input_hash reset to ''")

    if fix and source_path is not None and prov.get("input_hash") in ("", None):
        try:
            prov["input_hash"] = sha256_file(source_path)
            warnings.append("provenance.input_hash computed from source_path")
        except Exception as e:  # noqa: BLE001
            warnings.append(f"provenance.input_hash compute failed: {e}")

    model_val = prov.get("model")
    if model_val is None:
        errors.append("provenance.model must be string")
        if fix:
            prov["model"] = ""
            warnings.append("provenance.model set to ''")
    elif not isinstance(model_val, str):
        errors.append("provenance.model must be string")
        if fix:
            prov["model"] = str(model_val)
            warnings.append("provenance.model coerced to string")

    warnings_val = out.get("warnings")
    if not isinstance(warnings_val, list):
        errors.append("warnings must be array")
        if fix:
            out["warnings"] = _as_str_list(warnings_val)
            warnings.append("warnings coerced to array")

    error_val = out.get("error")
    if error_val is not None and not isinstance(error_val, dict):
        errors.append("error must be object or null")
        if fix:
            out["error"] = {"code": "INVALID_ERROR_FIELD", "message": "error was not object/null"}
            warnings.append("error replaced with object")

    def maybe_relocate_text_artifact(key: str, filename: str) -> None:
        if not fix or source_path is None:
            return
        current = out.get(key)
        if not isinstance(current, str) or not current:
            return
        expected = output_root / filename
        if Path(current) == expected:
            return
        src = Path(current)
        if not src.exists():
            return
        try:
            _write_text(expected, src.read_text(encoding="utf-8"))
            out[key] = str(expected)
            warnings.append(f"{key}: relocated to {expected.name} under source_path directory")
        except Exception as e:  # noqa: BLE001
            warnings.append(f"{key}: relocate failed: {e}")

    def maybe_relocate_json_artifact(key: str, filename: str) -> None:
        if not fix or source_path is None:
            return
        current = out.get(key)
        if not isinstance(current, str) or not current:
            return
        expected = output_root / filename
        if Path(current) == expected:
            return
        src = Path(current)
        if not src.exists():
            return
        try:
            data = json.loads(src.read_text(encoding="utf-8"))
            _write_json(expected, data)
            out[key] = str(expected)
            warnings.append(f"{key}: relocated to {expected.name} under source_path directory")
        except Exception as e:  # noqa: BLE001
            warnings.append(f"{key}: relocate failed: {e}")

    maybe_relocate_text_artifact("digest_path", DIGEST_FILENAME)
    maybe_relocate_json_artifact("references_path", REFERENCES_FILENAME)
    maybe_relocate_json_artifact("citation_analysis_path", CITATION_ANALYSIS_FILENAME)

    # Validate artifacts when paths are set (both check and fix mode).
    if isinstance(out.get("digest_path"), str) and out["digest_path"]:
        if not Path(out["digest_path"]).exists():
            errors.append("digest_path does not exist")

    if isinstance(out.get("references_path"), str) and out["references_path"]:
        rp = Path(out["references_path"])
        if not rp.exists():
            errors.append("references_path does not exist")
        else:
            try:
                refs_obj = json.loads(rp.read_text(encoding="utf-8"))
                if fix and isinstance(refs_obj, list):
                    normalized: list[dict[str, Any]] = []
                    for item in refs_obj:
                        normalized.append(_normalize_reference_item(item, fix=True, warnings=warnings))
                    _write_json(rp, normalized)
                    refs_obj = normalized
                errors.extend(_validate_references_items(refs_obj))
            except Exception as e:  # noqa: BLE001
                errors.append(f"references_path unreadable JSON: {e}")

    expected_mentions, expected_mentions_error = _extract_preprocess_expected_mentions(preprocess_artifact)
    if expected_mentions_error:
        errors.append(expected_mentions_error)

    if isinstance(out.get("citation_analysis_path"), str) and out["citation_analysis_path"]:
        cap = Path(out["citation_analysis_path"])
        if not cap.exists():
            errors.append("citation_analysis_path does not exist")
        else:
            try:
                ca_obj = json.loads(cap.read_text(encoding="utf-8"))
                errors.extend(_validate_citation_analysis_obj(ca_obj))
                if expected_mentions is not None:
                    consumed_mentions = _count_citation_mentions(ca_obj)
                    if consumed_mentions is None:
                        errors.append("unable to count consumed mentions from citation_analysis")
                    elif consumed_mentions != expected_mentions:
                        errors.append(
                            "citation_analysis mention coverage mismatch: "
                            f"expected {expected_mentions}, got {consumed_mentions}"
                        )
            except Exception as e:  # noqa: BLE001
                errors.append(f"citation_analysis_path unreadable JSON: {e}")

    if fix:
        out["warnings"] = _as_str_list(out.get("warnings")) + warnings

    return out, warnings, errors


def _load_input(path: Path | None) -> object:
    if path is None:
        data = sys.stdin.read()
        return json.loads(data) if data.strip() else {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate/fix literature_digest_v1 output JSON (file-based outputs).")
    parser.add_argument("--mode", choices=["check", "fix"], default="check")
    parser.add_argument("--in", dest="in_path", default=None, help="Input JSON file path (default: stdin)")
    parser.add_argument("--source-path", default=None, help="Optional original input path to compute provenance.input_hash")
    parser.add_argument("--md-path", default=None, help="Deprecated alias for --source-path")
    parser.add_argument("--out-dir", default=None, help="Directory to write digest/references files (fix mode only)")
    parser.add_argument(
        "--preprocess-artifact",
        default=None,
        help="Optional citation preprocess JSON path for mention coverage check",
    )
    args = parser.parse_args()

    in_path = Path(args.in_path) if args.in_path else None
    source_arg = args.source_path or args.md_path
    source_path = Path(source_arg) if source_arg else None
    if source_path is not None and not source_path.exists():
        source_path = None

    out_dir = Path(args.out_dir).expanduser() if args.out_dir else None
    output_root = _resolve_output_root(out_dir, source_path)
    preprocess_artifact = Path(args.preprocess_artifact).expanduser() if args.preprocess_artifact else None

    obj = _load_input(in_path)

    if args.mode == "check":
        _, _, errors = _normalize_top_level(
            obj,
            fix=False,
            source_path=None,
            output_root=output_root,
            preprocess_artifact=preprocess_artifact,
        )
        report = {"ok": len(errors) == 0, "errors": errors}
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["ok"] else 2

    fixed, _, _ = _normalize_top_level(
        obj,
        fix=True,
        source_path=source_path,
        output_root=output_root,
        preprocess_artifact=preprocess_artifact,
    )
    _, _, post_errors = _normalize_top_level(
        fixed,
        fix=False,
        source_path=None,
        output_root=output_root,
        preprocess_artifact=preprocess_artifact,
    )
    if post_errors:
        fixed.setdefault("warnings", [])
        fixed["warnings"] = _as_str_list(fixed["warnings"]) + [f"validate_output: still invalid: {e}" for e in post_errors]
        print(json.dumps(fixed, ensure_ascii=False))
        return 2

    print(json.dumps(fixed, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

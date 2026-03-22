from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any


TMP_DIRNAME = ".literature_digest_tmp"
CITATION_PARTS_DIRNAME = "citation.parts"
CITATION_MERGED_FILENAME = "citation_merged.json"


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _atomic_publish(src_path: Path, publish_path: Path) -> None:
    publish_path.parent.mkdir(parents=True, exist_ok=True)
    temp_publish = publish_path.with_suffix(publish_path.suffix + ".tmp")
    temp_publish.write_text(src_path.read_text(encoding="utf-8"), encoding="utf-8")
    os.replace(temp_publish, publish_path)


def _part_sort_key(path: Path) -> tuple[int, str]:
    match = re.search(r"part-(\d+)\.json$", path.name)
    if match is None:
        return (10**9, path.name)
    return (int(match.group(1)), path.name)


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_scope(scope_path: Path | None, preprocess_obj: dict[str, Any]) -> dict[str, Any] | None:
    if scope_path is not None:
        scope_obj = _load_json(scope_path)
        if isinstance(scope_obj, dict):
            if "scope" in scope_obj and isinstance(scope_obj["scope"], dict):
                return dict(scope_obj["scope"])
            if {"section_title", "line_start", "line_end"} <= set(scope_obj):
                return {
                    "section_title": scope_obj["section_title"],
                    "line_start": scope_obj["line_start"],
                    "line_end": scope_obj["line_end"],
                }
    meta = preprocess_obj.get("meta")
    if isinstance(meta, dict) and isinstance(meta.get("scope"), dict):
        return dict(meta["scope"])
    return None


def _load_preprocess(preprocess_path: Path) -> tuple[dict[str, Any] | None, int | None, str | None]:
    try:
        preprocess_obj = _load_json(preprocess_path)
    except Exception as exc:  # noqa: BLE001
        return None, None, f"unable to parse preprocess artifact: {exc}"

    if not isinstance(preprocess_obj, dict):
        return None, None, "preprocess artifact must be a JSON object"

    stats = preprocess_obj.get("stats")
    if not isinstance(stats, dict) or not isinstance(stats.get("total_mentions"), int):
        return None, None, "preprocess artifact missing stats.total_mentions"

    return preprocess_obj, int(stats["total_mentions"]), None


def merge_citation_parts(
    parts_dir: Path,
    preprocess_path: Path,
    merged_path: Path,
    publish_path: Path | None,
    report_md_path: Path | None,
    language: str,
    scope_path: Path | None,
) -> dict[str, Any]:
    preprocess_obj, expected_mentions, preprocess_error = _load_preprocess(preprocess_path)
    if preprocess_error is not None or preprocess_obj is None or expected_mentions is None:
        return {
            "citation_merged_path": "",
            "citation_analysis_path": "",
            "error": {"code": "citation_merge_failed", "message": preprocess_error or "invalid preprocess artifact"},
        }

    report_md = ""
    if report_md_path is not None:
        try:
            report_md = report_md_path.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            return {
                "citation_merged_path": "",
                "citation_analysis_path": "",
                "error": {"code": "citation_report_failed", "message": f"unable to read report_md: {exc}"},
            }

    part_paths = sorted(parts_dir.glob("part-*.json"), key=_part_sort_key)
    if not part_paths:
        return {
            "citation_merged_path": "",
            "citation_analysis_path": "",
            "error": {"code": "citation_merge_failed", "message": "no citation part files found"},
        }

    scope = _load_scope(scope_path, preprocess_obj)
    if scope is None:
        return {
            "citation_merged_path": "",
            "citation_analysis_path": "",
            "error": {"code": "citation_merge_failed", "message": "missing citation scope metadata"},
        }

    items: list[dict[str, Any]] = []
    unmapped_mentions: list[dict[str, Any]] = []
    mention_ids: set[str] = set()
    ref_indexes: set[int] = set()

    for part_path in part_paths:
        try:
            part_obj = _load_json(part_path)
        except Exception as exc:  # noqa: BLE001
            return {
                "citation_merged_path": "",
                "citation_analysis_path": "",
                "error": {"code": "citation_merge_failed", "message": f"unable to parse {part_path.name}: {exc}"},
            }

        if not isinstance(part_obj, dict):
            return {
                "citation_merged_path": "",
                "citation_analysis_path": "",
                "error": {"code": "citation_merge_failed", "message": f"{part_path.name} must be a JSON object"},
            }

        part_items = part_obj.get("items", [])
        part_unmapped = part_obj.get("unmapped_mentions", [])
        if not isinstance(part_items, list) or not isinstance(part_unmapped, list):
            return {
                "citation_merged_path": "",
                "citation_analysis_path": "",
                "error": {
                    "code": "citation_merge_failed",
                    "message": f"{part_path.name} must contain items[] and unmapped_mentions[]",
                },
            }

        for item in part_items:
            if not isinstance(item, dict):
                return {
                    "citation_merged_path": "",
                    "citation_analysis_path": "",
                    "error": {"code": "citation_merge_failed", "message": f"{part_path.name} contains non-object item"},
                }
            ref_index = item.get("ref_index")
            mentions = item.get("mentions")
            if not isinstance(ref_index, int):
                return {
                    "citation_merged_path": "",
                    "citation_analysis_path": "",
                    "error": {"code": "citation_merge_failed", "message": f"{part_path.name} item missing int ref_index"},
                }
            if ref_index in ref_indexes:
                return {
                    "citation_merged_path": "",
                    "citation_analysis_path": "",
                    "error": {"code": "citation_merge_failed", "message": f"duplicate ref_index detected: {ref_index}"},
                }
            if not isinstance(mentions, list):
                return {
                    "citation_merged_path": "",
                    "citation_analysis_path": "",
                    "error": {"code": "citation_merge_failed", "message": f"{part_path.name} item missing mentions[]"},
                }
            for mention in mentions:
                if not isinstance(mention, dict) or not isinstance(mention.get("mention_id"), str):
                    return {
                        "citation_merged_path": "",
                        "citation_analysis_path": "",
                        "error": {
                            "code": "citation_merge_failed",
                            "message": f"{part_path.name} contains invalid mapped mention",
                        },
                    }
                mention_id = mention["mention_id"]
                if mention_id in mention_ids:
                    return {
                        "citation_merged_path": "",
                        "citation_analysis_path": "",
                        "error": {"code": "citation_merge_failed", "message": f"duplicate mention_id detected: {mention_id}"},
                    }
                mention_ids.add(mention_id)
            ref_indexes.add(ref_index)
            items.append(item)

        for mention in part_unmapped:
            if not isinstance(mention, dict) or not isinstance(mention.get("mention_id"), str):
                return {
                    "citation_merged_path": "",
                    "citation_analysis_path": "",
                    "error": {
                        "code": "citation_merge_failed",
                        "message": f"{part_path.name} contains invalid unmapped mention",
                    },
                }
            mention_id = mention["mention_id"]
            if mention_id in mention_ids:
                return {
                    "citation_merged_path": "",
                    "citation_analysis_path": "",
                    "error": {"code": "citation_merge_failed", "message": f"duplicate mention_id detected: {mention_id}"},
                }
            mention_ids.add(mention_id)
            unmapped_mentions.append(mention)

    consumed_mentions = sum(len(item.get("mentions", [])) for item in items) + len(unmapped_mentions)
    if consumed_mentions != expected_mentions:
        return {
            "citation_merged_path": "",
            "citation_analysis_path": "",
            "error": {
                "code": "citation_merge_failed",
                "message": f"mention coverage mismatch: expected {expected_mentions}, got {consumed_mentions}",
            },
        }

    citation_payload = {
        "meta": {
            "language": language,
            "scope": scope,
        },
        "items": items,
        "unmapped_mentions": unmapped_mentions,
        "report_md": report_md,
    }
    _write_json(merged_path, citation_payload)

    published = ""
    if publish_path is not None:
        _atomic_publish(merged_path, publish_path)
        published = str(publish_path)

    return {
        "citation_merged_path": str(merged_path),
        "citation_analysis_path": published,
        "consumed_mentions": consumed_mentions,
        "error": None,
    }


def _default_tmp_dir() -> Path:
    return Path.cwd() / TMP_DIRNAME


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge staged citation artifacts for literature-digest.")
    parser.add_argument("--parts-dir", default=str(_default_tmp_dir() / CITATION_PARTS_DIRNAME))
    parser.add_argument("--preprocess-path", required=True)
    parser.add_argument("--merged-path", default=str(_default_tmp_dir() / CITATION_MERGED_FILENAME))
    parser.add_argument("--publish-path", default="")
    parser.add_argument("--report-md-path", default="")
    parser.add_argument("--scope-file", default="")
    parser.add_argument("--language", default="zh-CN")
    args = parser.parse_args()

    publish_path = Path(args.publish_path) if args.publish_path else None
    report_md_path = Path(args.report_md_path) if args.report_md_path else None
    scope_path = Path(args.scope_file) if args.scope_file else None

    result = merge_citation_parts(
        Path(args.parts_dir),
        Path(args.preprocess_path),
        Path(args.merged_path),
        publish_path,
        report_md_path,
        args.language,
        scope_path,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["error"] is None else 2


if __name__ == "__main__":
    raise SystemExit(main())

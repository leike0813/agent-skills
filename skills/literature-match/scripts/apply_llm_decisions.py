from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ApplyResult:
    updated: dict[str, Any]
    warnings: list[str]


def _index_refs_by_id(refs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for ref in refs:
        ref_id = str(ref.get("ref_id") or "").strip()
        if not ref_id:
            continue
        if ref_id in out:
            continue
        out[ref_id] = ref
    return out


def _candidate_map(ref: dict[str, Any]) -> dict[str, dict[str, Any]]:
    candidates = ref.get("candidates")
    if not isinstance(candidates, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for c in candidates:
        if not isinstance(c, dict):
            continue
        ck = str(c.get("citekey") or "").strip()
        if ck and ck not in out:
            out[ck] = c
    return out


def _recompute_stats(refs: list[dict[str, Any]]) -> dict[str, int]:
    stats = {"total": 0, "matched": 0, "needs_llm": 0, "needs_review": 0, "unmatched": 0}
    for ref in refs:
        stats["total"] += 1
        match = ref.get("match")
        if not isinstance(match, dict):
            stats["unmatched"] += 1
            continue
        status = str(match.get("status") or "unmatched")
        if status in stats:
            stats[status] += 1
        else:
            stats["unmatched"] += 1
    return stats


def apply_llm_decisions(match_result: dict[str, Any], decisions: dict[str, Any]) -> ApplyResult:
    warnings: list[str] = []

    refs = match_result.get("refs")
    if not isinstance(refs, list):
        raise ValueError("match_result.json missing required field: refs[]")

    decisions_list = decisions.get("decisions")
    if decisions_list is None:
        decisions_list = decisions.get("items") or decisions.get("refs")
    if not isinstance(decisions_list, list):
        raise ValueError("llm_decisions.json missing required field: decisions[]")

    refs_by_id = _index_refs_by_id(refs)

    for d in decisions_list:
        if not isinstance(d, dict):
            continue
        ref_id = str(d.get("ref_id") or "").strip()
        if not ref_id:
            warnings.append("Skipped decision with empty ref_id")
            continue

        ref = refs_by_id.get(ref_id)
        if ref is None:
            warnings.append(f"Decision ref_id not found in match_result.json: {ref_id}")
            continue

        chosen = d.get("citekey")
        citekey = str(chosen).strip() if chosen is not None else None
        if citekey == "" or citekey == "null":
            citekey = None

        reason = str(d.get("reason") or "").strip() or None
        confidence = d.get("confidence")
        try:
            confidence_f = float(confidence) if confidence is not None else None
        except Exception:
            confidence_f = None

        match = ref.get("match")
        if not isinstance(match, dict):
            match = {}
            ref["match"] = match

        if citekey is None:
            match.update(
                {
                    "status": "unmatched",
                    "citekey": None,
                    "itemKey": None,
                    "method": "llm",
                    "confidence": float(confidence_f if confidence_f is not None else 0.0),
                }
            )
            if reason is not None:
                match["reason"] = reason
            continue

        candidates = _candidate_map(ref)
        cand = candidates.get(citekey)
        if cand is None:
            raise ValueError(f"Decision citekey not in candidates for ref_id={ref_id}: {citekey}")

        match.update(
            {
                "status": "matched",
                "citekey": citekey,
                "itemKey": str(cand.get("itemKey") or "") or None,
                "method": "llm",
                "confidence": float(confidence_f if confidence_f is not None else match.get("confidence") or 0.0),
            }
        )
        if reason is not None:
            match["reason"] = reason

    match_result["stats"] = _recompute_stats(refs)

    meta = match_result.get("meta")
    if isinstance(meta, dict):
        meta.setdefault("warnings", [])
        if isinstance(meta.get("warnings"), list):
            meta["warnings"].extend(warnings)
        else:
            meta["warnings"] = warnings

    return ApplyResult(updated=match_result, warnings=warnings)


def load_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at top-level: {path}")
    return data


def write_json(path: str, data: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

#!/usr/bin/env python3
"""
quality_gate.py — Translation quality gate for literature-translator (v2).

Validates a completed translation batch against the original text.

Checks (v2 enhancements in bold):
1. Sentence count consistency — original and translation must have same count.
2. Lazy translation detection — token length ratio within threshold.
3. Term consistency — glossary.locked terms appear correctly in translation.
4. Language correctness — output matches target language (with allowlist).
5. **Placeholder preservation** — all input placeholders appear in output.
6. **Numeric/reference preservation** — numbers, citations, figure/table refs kept.
7. **Non-translation language detection** — summary/explanation phrases.
8. **Length check by block type** — weak warning per-block length ratios.

This script does NOT evaluate translation quality, fluency, or semantic accuracy.
Those are the LLM's responsibility in Phase 8 (main agent review).
"""
import argparse
import json
import re
import sys
from pathlib import Path
import tiktoken


_ENCODER = None


def _count_tokens(text: str) -> int:
    """Count tokens using cl100k_base encoding (GPT-4/GPT-3.5 tokenizer)."""
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    return len(_ENCODER.encode(text))


# ─── Constants ──────────────────────────────────────────────────────────────

MIN_TOKEN_RATIO = 0.3
MAX_TOKEN_RATIO = 3.0

# Placeholder regex (matches <TYPE_NNN> and <TYPE_SUBTYPE_NNN>)
PH_RE = re.compile(r'<[A-Z]+(?:_[A-Z]+)?_\d+>')

# Block types that are kept as-is (not translated). These bypass semantic
# checks (language, term consistency) since the original content is preserved.
PASSTHROUGH_TYPES = {"equation", "code", "bib_item"}

# Number-like patterns to check in translation
NUMERIC_PATTERNS = [
    (re.compile(r'\d+\.\d+'), 'decimal'),
    (re.compile(r'\d+%'), 'percentage'),
    (re.compile(r'\d+'), 'integer'),
]

# Citation patterns to check
CITATION_PATTERNS = [
    re.compile(r'\[\d+(?:\s*[,–—-]\s*\d+)*\]'),       # [1], [1, 2]
    re.compile(r'\bFig(?:ure)?\.?\s*\d+', re.IGNORECASE),  # Fig. 1
    re.compile(r'\bTable\s*\d+', re.IGNORECASE),            # Table 1
    re.compile(r'\bEq(?:uation)?\.?\s*\(?\d+\)?', re.IGNORECASE),  # Eq. (1)
    re.compile(r'\bSection\s*\d+(?:\.\d+)+', re.IGNORECASE),  # Section 3.2
]

# Non-translation language patterns (model explains instead of translating)
NON_TRANSLATION_PATTERNS = [
    re.compile(r'大意是'),
    re.compile(r'意思是'),
    re.compile(r'可以理解为'),
    re.compile(r'总结来说'),
    re.compile(r'简而言之'),
    re.compile(r'这句话说明'),
    re.compile(r'作者想表达'),
    re.compile(r'该段主要讲'),
    re.compile(r'以下是翻译'),
    re.compile(r'译文如下'),
    re.compile(r'本段（?:的|主要）?大意'),
    re.compile(r'换句话说'),
    re.compile(r'也就是说'),
    re.compile(r'这里的意思是'),
]

# Length rules by block type (weak check — warning only)
LENGTH_RULES = {
    "paragraph":   {"min_ratio": 0.25, "max_ratio": 2.50},
    "caption":     {"min_ratio": 0.35, "max_ratio": 2.80},
    "heading":     {"min_ratio": 0.10, "max_ratio": 3.00},
    "table":       {"min_ratio": 0.05, "max_ratio": 4.00},
    "table_cell":  {"min_ratio": 0.05, "max_ratio": 4.00},
    "figure_caption": {"min_ratio": 0.35, "max_ratio": 2.80},
    "table_caption":  {"min_ratio": 0.35, "max_ratio": 2.80},
    "list":        {"min_ratio": 0.10, "max_ratio": 3.00},
    "list_item":   {"min_ratio": 0.10, "max_ratio": 3.00},
    "bib_item":    {"min_ratio": 0.05, "max_ratio": 2.50},
    "abstract":    {"min_ratio": 0.25, "max_ratio": 2.50},
    "default":     {"min_ratio": 0.25, "max_ratio": 2.50},
}


# ─── Helper utilities ───────────────────────────────────────────────────────

def load_json(path: Path) -> dict:
    """Load and validate a JSON file."""
    if not path.exists():
        return {"error": f"file not found: {path}"}
    raw_text = path.read_text(encoding="utf-8")
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as e:
        # Extract context around the error position for diagnosis
        pos = e.pos
        start = max(0, pos - 30)
        end = min(len(raw_text), pos + 30)
        snippet = raw_text[start:end]
        marker = " " * (pos - start) + "^"
        return {
            "error": f"invalid JSON at line {e.lineno}, col {e.colno}, char {e.pos}: {e.msg}",
            "context": snippet,
            "pointer": marker,
            "hint": "Likely cause: unescaped double-quote (\") inside a JSON string. "
                    "Escape as \\\". For Chinese target language, prefer using 「」 or \"\" instead of straight double quotes.",
        }


def extract_sentence_text(item) -> str:
    """Extract text from a sentence item, handling v1 (string) and v2 ([idx, text]) formats."""
    if isinstance(item, (list, tuple)):
        return str(item[1]) if len(item) > 1 else ""
    return str(item)


def extract_sentence_index(item) -> int:
    """Extract the 1-based index from a sentence item. Returns -1 for v1 format."""
    if isinstance(item, (list, tuple)) and len(item) >= 2 and isinstance(item[0], int):
        return item[0]
    return -1


def load_original_sentences(batch_payload: dict) -> list[tuple[str, str, int]]:
    """Extract sentences from original batch payload.

    Returns list of (block_id, sentence_text, sentence_index).
    """
    sentences = []
    blocks = batch_payload.get("blocks", {})
    if not blocks:
        for block_id, block_data in batch_payload.items():
            if isinstance(block_data, dict) and "sentences" in block_data:
                for item in block_data["sentences"]:
                    text = extract_sentence_text(item)
                    idx = extract_sentence_index(item)
                    sentences.append((block_id, text, idx))
        return sentences

    for block_id, block_data in blocks.items():
        s_list = block_data.get("sentences", [])
        for item in s_list:
            text = extract_sentence_text(item)
            idx = extract_sentence_index(item)
            sentences.append((block_id, text, idx))

    return sentences


def load_translated_sentences(translation: dict) -> list[tuple[str, str, int]]:
    """Extract sentences from translation result.

    Returns list of (block_id, sentence_text, sentence_index).
    """
    sentences = []
    blocks = translation.get("blocks", translation)
    if isinstance(blocks, dict):
        for block_id, block_data in blocks.items():
            if isinstance(block_data, dict) and "sentences" in block_data:
                for item in block_data["sentences"]:
                    text = extract_sentence_text(item)
                    idx = extract_sentence_index(item)
                    sentences.append((block_id, text, idx))
            elif isinstance(block_data, list):
                for item in block_data:
                    text = extract_sentence_text(item)
                    idx = extract_sentence_index(item)
                    sentences.append((block_id, text, idx))
    return sentences


def get_block_types(batch_payload: dict) -> dict[str, str]:
    """Extract block_id -> type mapping from batch payload."""
    types = {}
    blocks = batch_payload.get("blocks", {})
    for block_id, block_data in blocks.items():
        if isinstance(block_data, dict):
            types[block_id] = block_data.get("type", "default")
    return types


def extract_keep_english(glossary: dict) -> list[str]:
    """Extract keep_english list from glossary (v2 format)."""
    if isinstance(glossary, dict):
        if "keep_english" in glossary:
            return glossary["keep_english"]
    return []


def extract_locked_terms(glossary: dict) -> dict[str, str]:
    """Extract locked terms from glossary.

    Handles both v1 (flat) and v2 (three-level) formats.
    """
    if isinstance(glossary, dict):
        if "locked" in glossary:
            return glossary["locked"]
        else:
            # v1 format — return as-is (flat dict)
            return glossary
    return {}


# ─── Check functions ────────────────────────────────────────────────────────

def check_sentence_count(original: list, translation: list) -> dict:
    """Check sentence count consistency between original and translation."""
    orig_count = len(original)
    trans_count = len(translation)

    passed = orig_count == trans_count
    return {
        "passed": passed,
        "original_count": orig_count,
        "translated_count": trans_count,
    }


def check_lazy_translation(original: list, translation: list) -> dict:
    """Check token length ratio to detect lazy/summary translation."""
    if not original or not translation:
        return {"passed": False, "error": "no sentences to compare"}

    total_orig = sum(_count_tokens(s[1]) for s in original)
    total_trans = sum(_count_tokens(s[1]) for s in translation)

    if total_orig == 0:
        return {"passed": True, "ratio": 1.0, "threshold": MIN_TOKEN_RATIO}

    ratio = total_trans / total_orig
    passed = MIN_TOKEN_RATIO <= ratio <= MAX_TOKEN_RATIO

    return {
        "passed": passed,
        "ratio": round(ratio, 4),
        "min_threshold": MIN_TOKEN_RATIO,
        "max_threshold": MAX_TOKEN_RATIO,
        "original_tokens": total_orig,
        "translated_tokens": total_trans,
    }


def check_term_consistency(glossary: dict, translation_text: str, original_text: str = "") -> dict:
    """Check that locked glossary terms are used consistently.

    For v2 glossary, only checks the 'locked' section.
    For v1 glossary, checks all entries.

    Only checks terms that actually appear in the original text for this batch.

    Matching strategy:
    - Do-not-translate terms (original == translation): exact case-sensitive
      match — the original word must appear as-is in the translation.
    - Terms with a defined translation (original != translation):
      * translation length >= 3 chars: substring match (case-insensitive).
        The glossary translation must appear as a contiguous substring.
      * translation length < 3 chars: exact match to avoid false positives
        on common short words.
    """
    terms = extract_locked_terms(glossary)
    if not terms:
        return {"passed": True, "violations": [], "note": "no locked terms to check"}

    violations = []
    for original, translation in terms.items():
        if not original or not translation:
            continue

        # Only check terms that appear in the original text for this batch
        if original_text and original not in original_text:
            continue

        if original.lower() == translation.lower():
            # Do-not-translate term: check original is preserved exactly
            if original not in translation_text:
                violations.append({
                    "term": original,
                    "expected": f"original '{original}' should appear in translation",
                    "found": False,
                })
        else:
            # Term with a defined translation: substring match (len >= 3)
            if len(translation) >= 3:
                if translation.lower() not in translation_text.lower():
                    violations.append({
                        "term": original,
                        "expected": f"translation '{translation}' should appear in output (substring match)",
                        "found": False,
                    })
            else:
                # Short translation (< 3 chars): exact matching only
                if translation not in translation_text:
                    violations.append({
                        "term": original,
                        "expected": f"translation '{translation}' should appear in output (exact match, short term)",
                        "found": False,
                    })

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "violation_count": len(violations),
    }


def check_language(text: str, target_lang: str) -> dict:
    """Basic language correctness check (v1).

    Checks whether the output text contains characters expected for the
    target language. This is a heuristic, not a definitive check.
    """
    if not text:
        return {"passed": False, "error": "empty translation text"}

    cjk = sum(1 for c in text if "一" <= c <= "鿿" or "㐀" <= c <= "䶿")
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    total_alpha = cjk + latin

    if total_alpha == 0:
        return {"passed": True, "note": "no alphabetic characters to check"}

    cjk_ratio = cjk / total_alpha if total_alpha > 0 else 0

    if target_lang.startswith("zh") or target_lang.startswith("ja") or target_lang.startswith("ko"):
        passed = cjk_ratio >= 0.1
        return {"passed": passed, "cjk_ratio": round(cjk_ratio, 4),
                "note": f"expected CJK characters for {target_lang}"}
    elif any(target_lang.startswith(p) for p in ("en", "fr", "de", "es")):
        passed = cjk_ratio < 0.5
        return {"passed": passed, "cjk_ratio": round(cjk_ratio, 4),
                "note": f"expected Latin script for {target_lang}"}
    else:
        return {"passed": True, "note": f"no specific language check for {target_lang}"}


def check_language_v2(text: str, target_lang: str, keep_english: list[str]) -> dict:
    """Enhanced language check (v2) with allowlist.

    Removes keep_english terms, placeholders, URLs, and model names
    before computing CJK ratio to avoid false positives.
    """
    if not text:
        return {"passed": False, "error": "empty translation text"}

    cleaned = text
    # Remove keep_english terms
    for term in keep_english:
        if term:
            cleaned = cleaned.replace(term, "")

    # Remove placeholders
    cleaned = PH_RE.sub("", cleaned)
    # Remove URLs
    cleaned = re.sub(r'https?://\S+', '', cleaned)
    # Remove common model/dataset name patterns (CamelCase)
    cleaned = re.sub(r'\b[A-Z][a-z]+[A-Z][a-zA-Z0-9-]*\b', '', cleaned)
    # Remove LaTeX commands
    cleaned = re.sub(r'\\([a-zA-Z]+)(?:\{[^}]*\})?', '', cleaned)
    # Remove bare numbers
    cleaned = re.sub(r'\b\d+(?:\.\d+)?\b', '', cleaned)

    cjk = sum(1 for c in cleaned if "一" <= c <= "鿿" or "㐀" <= c <= "䶿")
    latin = sum(1 for c in cleaned if c.isascii() and c.isalpha())
    total_alpha = cjk + latin

    if total_alpha == 0:
        return {"passed": True, "note": "no alphabetic characters after cleanup",
                "raw_cjk_ratio": None}

    cjk_ratio = cjk / total_alpha if total_alpha > 0 else 0

    if target_lang.startswith("zh") or target_lang.startswith("ja") or target_lang.startswith("ko"):
        passed = cjk_ratio >= 0.1
        return {"passed": passed, "cjk_ratio": round(cjk_ratio, 4),
                "note": f"v2 check (allowlist applied), expected CJK for {target_lang}"}
    elif any(target_lang.startswith(p) for p in ("en", "fr", "de", "es")):
        passed = cjk_ratio < 0.5
        return {"passed": passed, "cjk_ratio": round(cjk_ratio, 4),
                "note": f"v2 check (allowlist applied), expected Latin for {target_lang}"}
    else:
        return {"passed": True, "note": f"no specific language check for {target_lang}"}


def check_placeholder_preservation(
    original_sentences: list[tuple[str, str, int]],
    translated_sentences: list[tuple[str, str, int]],
) -> dict:
    """Check that all input placeholders appear in the output and no
    unexpected placeholders are introduced.

    Rules:
    1. Input placeholders must all appear in corresponding translations.
    2. Output must not contain placeholders absent from input.
    3. Placeholder strings must match exactly (case-sensitive).
    """
    # Collect input placeholders
    expected = set()
    for _, text, _ in original_sentences:
        for match in PH_RE.finditer(text):
            expected.add(match.group(0))

    if not expected:
        return {"passed": True, "note": "no placeholders in input", "expected_count": 0}

    # Collect output placeholders
    found = set()
    unexpected = set()
    for _, text, _ in translated_sentences:
        for match in PH_RE.finditer(text):
            token = match.group(0)
            if token in expected:
                found.add(token)
            else:
                unexpected.add(token)

    missing = expected - found

    return {
        "passed": len(missing) == 0 and len(unexpected) == 0,
        "expected_count": len(expected),
        "found_count": len(found),
        "missing": sorted(missing) if missing else [],
        "unexpected": sorted(unexpected) if unexpected else [],
    }


def check_numeric_preservation(
    original_sentences: list[tuple[str, str, int]],
    translated_sentences: list[tuple[str, str, int]],
) -> dict:
    """Check that numeric placeholders and citation references are preserved.

    Focuses on placeholder-protected items (<NUM_NNN>, <REF_NNN>, <FIG_NNN>,
    <TBL_NNN>, <EQ_REF_NNN>) — these are the high-confidence items that must
    survive translation.
    """
    numeric_types = {"NUM", "REF", "FIG", "TBL", "EQ_REF", "SEC", "APP"}

    # Check placeholder-level numeric references
    expected_nums = set()
    for _, text, _ in original_sentences:
        for match in PH_RE.finditer(text):
            ptype = match.group(0).split("_")[0][1:]  # Extract type from <TYPE_NNN>
            if ptype in numeric_types:
                expected_nums.add(match.group(0))

    if not expected_nums:
        return {"passed": True, "note": "no numeric placeholders to check"}

    found_nums = set()
    for _, text, _ in translated_sentences:
        for match in PH_RE.finditer(text):
            if match.group(0) in expected_nums:
                found_nums.add(match.group(0))

    missing_nums = expected_nums - found_nums

    return {
        "passed": len(missing_nums) == 0,
        "expected_count": len(expected_nums),
        "found_count": len(found_nums),
        "missing": sorted(missing_nums) if missing_nums else [],
    }


def check_non_translation_phrases(
    translated_sentences: list[tuple[str, str, int]],
) -> dict:
    """Check for explanation/summary phrases that indicate the model is
    explaining instead of translating."""
    violations = []
    for block_id, text, idx in translated_sentences:
        for pattern in NON_TRANSLATION_PATTERNS:
            m = pattern.search(text)
            if m:
                violations.append({
                    "block_id": block_id,
                    "sentence_index": idx,
                    "pattern": pattern.pattern,
                    "context": text[:80] + ("..." if len(text) > 80 else ""),
                })
                break  # One violation per sentence

    return {
        "passed": len(violations) == 0,
        "violations": violations,
    }


def check_length_by_type(
    original_sentences: list[tuple[str, str, int]],
    translated_sentences: list[tuple[str, str, int]],
    block_types: dict[str, str],
) -> dict:
    """Per-block-type length ratio check (weak check — warning only).

    Checks each sentence pair's token ratio against type-specific thresholds.
    Returns warnings but does NOT determine pass/fail (is_weak=True).
    """
    warnings = []
    for (b_orig, text_orig, idx_orig), (b_trans, text_trans, idx_trans) in zip(
        original_sentences, translated_sentences
    ):
        if b_orig != b_trans:
            continue
        block_type = block_types.get(b_orig, "default")
        rules = LENGTH_RULES.get(block_type, LENGTH_RULES["default"])
        ratio = _count_tokens(text_trans) / max(_count_tokens(text_orig), 1)
        if ratio < rules["min_ratio"] or ratio > rules["max_ratio"]:
            warnings.append({
                "block_id": b_orig,
                "sentence_index": idx_orig,
                "type": block_type,
                "ratio": round(ratio, 4),
                "threshold": rules,
            })

    return {
        "passed": len(warnings) == 0,
        "warnings": warnings,
        "warning_count": len(warnings),
        "is_weak": True,  # This check does NOT contribute to overall pass/fail
    }


# ─── Main ───────────────────────────────────────────────────────────────────

def resolve_placeholders(text: str, placeholder_entries: dict[str, str]) -> str:
    """Resolve placeholders in text using the entries map."""
    def _replace(m: re.Match) -> str:
        return placeholder_entries.get(m.group(0), m.group(0))
    return PH_RE.sub(_replace, text)


def resolve_mode() -> str:
    """Resolve mode from workspace mode.txt. Mode is fixed for the entire run."""
    for candidate in [".literature_translator_tmp/mode.txt", "workspace/mode.txt"]:
        p = Path(candidate)
        if p.exists():
            mode_value = p.read_text(encoding="utf-8").strip()
            if mode_value in ("fast", "high_quality"):
                return mode_value
    return "high_quality"  # fallback (should not happen in normal execution)


# ─── Retry state management ───────────────────────────────────────────────────

MAX_RETRIES_PER_BATCH = 2
MAX_GLOBAL_RETRIES = 10
RETRY_STATE_PATH = ".literature_translator_tmp/retry_state.json"


def _retry_state_path() -> Path | None:
    """Resolve the retry state file path."""
    for candidate in [RETRY_STATE_PATH, "workspace/retry_state.json"]:
        p = Path(candidate)
        parent = p.parent
        if parent.exists() or p.exists():
            return p
    # If neither exists, default to the tmp path (will be created on first write)
    return Path(RETRY_STATE_PATH)


def load_retry_state() -> dict:
    """Load retry state from disk."""
    p = _retry_state_path()
    if p and p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"batch_retries": {}, "global_retries": 0}


def save_retry_state(state: dict):
    """Persist retry state to disk."""
    p = _retry_state_path()
    if p:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def check_retry_limits(batch_id: str) -> dict | None:
    """Check if this batch has exceeded retry limits.

    Returns None if the batch can proceed, or a blocker dict if retrying
    should be stopped.
    """
    state = load_retry_state()
    per_batch = state.get("batch_retries", {}).get(batch_id, 0)
    global_retries = state.get("global_retries", 0)

    if per_batch >= MAX_RETRIES_PER_BATCH:
        return {
            "passed": False,
            "blocked": True,
            "reason": f"per-batch retry limit reached ({per_batch}/{MAX_RETRIES_PER_BATCH}) for {batch_id}",
            "batch_id": batch_id,
        }
    if global_retries >= MAX_GLOBAL_RETRIES:
        return {
            "passed": False,
            "blocked": True,
            "reason": f"global retry budget exhausted ({global_retries}/{MAX_GLOBAL_RETRIES})",
            "batch_id": batch_id,
        }
    return None


def record_retry(batch_id: str):
    """Increment retry counters for a failed batch."""
    state = load_retry_state()
    state.setdefault("batch_retries", {})
    state["batch_retries"][batch_id] = state["batch_retries"].get(batch_id, 0) + 1
    state["global_retries"] = state.get("global_retries", 0) + 1
    save_retry_state(state)


def main():
    parser = argparse.ArgumentParser(description="Translation quality gate (v2)")
    parser.add_argument("--original", required=True, help="Original batch payload JSON")
    parser.add_argument("--translation", required=True, help="Translated batch result JSON")
    parser.add_argument("--glossary", required=True, help="Glossary JSON")
    parser.add_argument("--target-lang", required=True, help="Target language code (e.g., zh-CN, en)")
    parser.add_argument("--placeholder-map", default=None,
                        help="Optional placeholder_map.json for resolving terms/language")
    args = parser.parse_args()

    mode = resolve_mode()

    original_path = Path(args.original)
    translation_path = Path(args.translation)
    glossary_path = Path(args.glossary)

    original_data = load_json(original_path)
    if "error" in original_data:
        result = {"passed": False, "error": f"original: {original_data['error']}"}
        if "context" in original_data:
            result["context"] = original_data["context"]
            result["pointer"] = original_data.get("pointer", "")
            result["hint"] = original_data.get("hint", "")
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    translation_data = load_json(translation_path)
    if "error" in translation_data:
        result = {"passed": False, "error": f"translation: {translation_data['error']}"}
        if "context" in translation_data:
            result["context"] = translation_data["context"]
            result["pointer"] = translation_data.get("pointer", "")
            result["hint"] = translation_data.get("hint", "")
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    glossary_data = load_json(glossary_path)
    if "error" in glossary_data:
        result = {"passed": False, "error": f"glossary: {glossary_data['error']}"}
        if "context" in glossary_data:
            result["context"] = glossary_data["context"]
            result["pointer"] = glossary_data.get("pointer", "")
            result["hint"] = glossary_data.get("hint", "")
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    batch_id = original_data.get("batch_id", translation_data.get("batch_id", "unknown"))

    # Check retry limits before running checks
    blocker = check_retry_limits(batch_id)
    if blocker:
        print(json.dumps(blocker, ensure_ascii=False))
        sys.exit(1)

    # Extract sentences
    original_sentences = load_original_sentences(original_data)
    translated_sentences = load_translated_sentences(translation_data)

    # Extract block types for length check
    block_types = get_block_types(original_data)

    # Extract keep_english for v2 language check
    keep_english = extract_keep_english(glossary_data)

    # Load placeholder map if provided (for resolving terms/language)
    placeholder_entries: dict[str, str] = {}
    if args.placeholder_map:
        ph_path = Path(args.placeholder_map)
        if ph_path.exists():
            ph_data = load_json(ph_path)
            if "error" not in ph_data:
                placeholder_entries = ph_data.get("entries", {})

    # Build the full translated text (for term/language checks)
    all_translated_text = " ".join(s[1] for s in translated_sentences)
    # Build resolved text by resolving placeholders if map provided
    if placeholder_entries:
        resolved_sentences = [
            (bid, resolve_placeholders(text, placeholder_entries), idx)
            for bid, text, idx in translated_sentences
        ]
        resolved_text = " ".join(s[1] for s in resolved_sentences)
    else:
        resolved_text = all_translated_text

    # Filter out passthrough-type blocks from semantic checks (language, term)
    # since these blocks keep original content (equations, code, bib_item).
    translated_semantic = [
        (bid, text, idx) for (bid, text, idx) in translated_sentences
        if block_types.get(bid, "default") not in PASSTHROUGH_TYPES
    ]
    resolved_semantic_text = " ".join(s[1] for s in translated_semantic) if translated_semantic else ""

    checks = {}

    # 1. Sentence count
    checks["sentence_count"] = check_sentence_count(original_sentences, translated_sentences)

    # 2. Lazy translation
    checks["lazy_translation"] = check_lazy_translation(original_sentences, translated_sentences)

    # Build resolved original text for term consistency check
    original_semantic = [
        (bid, text, idx) for (bid, text, idx) in original_sentences
        if block_types.get(bid, "default") not in PASSTHROUGH_TYPES
    ]
    if placeholder_entries:
        resolved_original_sentences = [
            (bid, resolve_placeholders(text, placeholder_entries), idx)
            for bid, text, idx in original_semantic
        ]
        resolved_original_text = " ".join(s[1] for s in resolved_original_sentences) if resolved_original_sentences else ""
    else:
        resolved_original_text = " ".join(s[1] for s in original_semantic) if original_semantic else ""

    # 3. Term consistency — only check semantic (non-passthrough) text
    if translated_semantic:
        checks["term_consistency"] = check_term_consistency(
            glossary_data,
            resolved_semantic_text,
            resolved_original_text
        )
    else:
        checks["term_consistency"] = {"passed": True, "violations": [], "note": "all blocks are passthrough type"}

    # 4. Language correctness — only check semantic (non-passthrough) text
    if translated_semantic:
        checks["language"] = check_language_v2(
            resolved_semantic_text,
            args.target_lang, keep_english
        )
    else:
        checks["language"] = {"passed": True, "note": "all blocks are passthrough type"}

    # 5. Placeholder preservation
    if mode == "fast":
        checks["placeholder_preservation"] = {
            "passed": True, "skipped": True,
            "reason": "fast mode — no placeholders",
        }
    else:
        checks["placeholder_preservation"] = check_placeholder_preservation(
            original_sentences, translated_sentences
        )

    # 6. Numeric/reference preservation
    if mode == "fast":
        checks["numeric_preservation"] = {
            "passed": True, "skipped": True,
            "reason": "fast mode — no placeholders",
        }
    else:
        checks["numeric_preservation"] = check_numeric_preservation(
            original_sentences, translated_sentences
        )

    # 7. Non-translation language detection (only for semantic blocks)
    checks["non_translation_phrases"] = check_non_translation_phrases(
        translated_semantic if translated_semantic else translated_sentences
    )

    # 8. Length by type (weak — does not affect pass/fail)
    checks["length_check"] = check_length_by_type(original_sentences, translated_sentences, block_types)

    # Overall result — only hard checks contribute to pass/fail
    hard_checks = {k: v for k, v in checks.items() if not v.get("is_weak", False)}
    all_passed = all(
        check.get("passed", False)
        for check in hard_checks.values()
    )

    # Record retry if checks failed
    if not all_passed:
        record_retry(batch_id)

    state = load_retry_state()
    result = {
        "passed": all_passed,
        "batch_id": batch_id,
        "checks": checks,
        "retry_state": {
            "batch_retries": state.get("batch_retries", {}).get(batch_id, 0),
            "global_retries": state.get("global_retries", 0),
            "max_per_batch": MAX_RETRIES_PER_BATCH,
            "max_global": MAX_GLOBAL_RETRIES,
        },
    }

    print(json.dumps(result, ensure_ascii=False))

    if not all_passed:
        sys.exit(0)  # Exit 0; caller reads stdout JSON for details


if __name__ == "__main__":
    main()

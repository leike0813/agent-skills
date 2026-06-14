#!/usr/bin/env python3
"""
protect_placeholders.py — Inline placeholder protection for literature-translator.

Reads the sentence-level JSON (.literature_translator_tmp/sentences.json) and replaces inline
elements (formulas, variables, citations, numbers, URLs, entity names) with
deterministic placeholders. Writes protected sentences and a placeholder map.

The placeholder map is used later by restore_placeholders.py to revert the
substitutions after translation, and by quality_gate.py to verify that no
placeholders were lost or corrupted.

Placeholder format: <TYPE_NNN> where TYPE is a category and NNN is a 3-digit index.

Replacement priority (MUST be applied in this order to avoid nested corruption):
  1. Inline math  $...$
  2. URLs / DOIs
  3. Citation references  [1], [1, 2]
  4. Figure / Table / Equation / Section references
  5. LaTeX variable commands  \\alpha, \\mathbf{x}
  6. Numbers (percentages, p-values, ranges, standalone)
  7. Known entity names (model names, dataset names)
"""
import argparse
import json
import re
import sys
from pathlib import Path


# ─── Regex patterns (ordered by replacement priority) ───────────────────────

# 1. Inline math $...$ — MUST be first to prevent internal content corruption
#    Handles $...$, $...$ across lines (but single-line preferred)
#    Negative lookbehind/lookahead for $$ (display math, already block-protected)
INLINE_MATH_RE = re.compile(r'(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)', re.DOTALL)

# 2a. URLs (http/https)
URL_RE = re.compile(r'https?://[^\s,;:!?)\]]+(?:[^\s,;:!?)\]])?')
# 2b. DOIs
DOI_RE = re.compile(r'\b(10\.\d{4,}/[^\s,;.:!?)\]]+)')

# 3. Citation references [1], [1, 2], [1-3], [1,2,3]
CITATION_RE = re.compile(r'\[(\d+(?:\s*[,–—-]\s*\d+)*(?:\s*[,–—-]\s*\d+)*)\]')

# 4a. Figure references: Fig. 1, Figure 2, Fig. 1a
FIGURE_REF_RE = re.compile(r'\b(Fig(?:ure)?\.?\s*)(\d+(?:\.\d+)?[a-zA-Z]?)', re.IGNORECASE)
# 4b. Table references: Table 1, Table 3.2
TABLE_REF_RE = re.compile(r'\b(Table\s*)(\d+(?:\.\d+)?[a-zA-Z]?)', re.IGNORECASE)
# 4c. Equation references: Eq. (4), Equation (4), Eq. 4
EQUATION_REF_RE = re.compile(
    r'\b(?:Eq(?:uation)?\.?)\s*(?:\((\d+(?:\.\d+)?[a-z]?)\)|(\d+(?:\.\d+)?[a-z]?))',
    re.IGNORECASE
)
# 4d. Section references: Section 3.2, Sec. 3.2
SECTION_REF_RE = re.compile(r'\b(?:Section|Sec\.)\s*(\d+(?:\.\d+)+)', re.IGNORECASE)
# 4e. Appendix references: Appendix A, Appendix A.1
APPENDIX_REF_RE = re.compile(r'\b(Appendix\s+)([A-Z]\d*(?:\.\d+)*)', re.IGNORECASE)

# 5. LaTeX variable commands: \alpha, \mathbf{x}, \theta_i
LATEX_VAR_RE = re.compile(r'\\([a-zA-Z]+)(?:\{[^}]*\})?')

# 6a. Percentages: 95%, 0.5%
PERCENT_RE = re.compile(r'(\d+(?:\.\d+)?\s*%)')
# 6b. p-values: p < 0.05, p=0.01, p > 0.001
P_VALUE_RE = re.compile(r'(p\s*[<>=]\s*\d+\.\d+)', re.IGNORECASE)
# 6c. Ranges: 5-10, 3.2–4.5, 100-200
RANGE_RE = re.compile(r'(\d+(?:\.\d+)?\s*[–—-]\s*\d+(?:\.\d+)?)')
# 6d. Scientific notation: 3e-5, 1.2e+3
SCIENTIFIC_RE = re.compile(r'(\d+\.?\d*[eE][+-]?\d+)')
# 6e. Standalone numbers (≥3 digits or decimals, not adjacent to letters)
STANDALONE_NUM_RE = re.compile(r'(?<![a-zA-Z])(\d+(?:\.\d+)?)(?![a-zA-Z])')

# 7. Known entities (model/dataset names) — passed via CLI arg, not regex


def build_entity_patterns(entities: list[str]) -> list[re.Pattern]:
    """Build case-sensitive regex patterns for known entity names.

    Sorts by length (longest first) to match multi-word entities first.
    """
    sorted_entities = sorted(entities, key=len, reverse=True)
    patterns = []
    for entity in sorted_entities:
        if not entity.strip():
            continue
        # Escape regex special chars in entity name
        escaped = re.escape(entity)
        # Use word boundaries to avoid partial matches
        patterns.append(re.compile(r'\b' + escaped + r'\b'))
    return patterns


class PlaceholderProtector:
    """Replace inline elements with placeholders and track the mapping."""

    TYPE_MATH = "MATH"
    TYPE_URL = "URL"
    TYPE_DOI = "DOI"
    TYPE_REF = "REF"
    TYPE_FIG = "FIG"
    TYPE_TBL = "TBL"
    TYPE_EQ_REF = "EQ_REF"
    TYPE_SEC = "SEC"
    TYPE_APP = "APP"
    TYPE_VAR = "VAR"
    TYPE_NUM = "NUM"
    TYPE_ENT = "ENT"

    def __init__(self, known_entities: list[str] | None = None):
        self.counters: dict[str, int] = {}     # type -> next index
        self.ph_map: dict[str, str] = {}       # placeholder -> original
        self.reverse_map: dict[str, str] = {}  # original -> placeholder
        self.entity_patterns = build_entity_patterns(known_entities or [])

    def _next_ph(self, ptype: str) -> str:
        """Generate the next placeholder for a given type."""
        idx = self.counters.get(ptype, 1)
        self.counters[ptype] = idx + 1
        return f"<{ptype}_{idx:03d}>"

    def _register(self, original: str, ptype: str) -> str:
        """Register an original string and return its placeholder.

        Deduplicates: identical originals get the same placeholder.
        """
        if original in self.reverse_map:
            return self.reverse_map[original]
        ph = self._next_ph(ptype)
        self.ph_map[ph] = original
        self.reverse_map[original] = ph
        return ph

    def protect_text(self, text: str) -> str:
        """Apply all placeholder replacements to text, in priority order."""
        # 1. Inline math
        text = INLINE_MATH_RE.sub(lambda m: self._register(m.group(0).strip(), self.TYPE_MATH), text)
        # 2a. URLs
        text = URL_RE.sub(lambda m: self._register(m.group(0), self.TYPE_URL), text)
        # 2b. DOIs
        text = DOI_RE.sub(lambda m: self._register(m.group(0), self.TYPE_DOI), text)
        # 3. Citation references
        text = CITATION_RE.sub(lambda m: self._register(m.group(0), self.TYPE_REF), text)
        # 4a. Figure references
        text = FIGURE_REF_RE.sub(
            lambda m: self._register(m.group(0).strip(), self.TYPE_FIG), text
        )
        # 4b. Table references
        text = TABLE_REF_RE.sub(
            lambda m: self._register(m.group(0).strip(), self.TYPE_TBL), text
        )
        # 4c. Equation references
        text = EQUATION_REF_RE.sub(
            lambda m: self._register(m.group(0).strip(), self.TYPE_EQ_REF), text
        )
        # 4d. Section references
        text = SECTION_REF_RE.sub(
            lambda m: self._register(m.group(0).strip(), self.TYPE_SEC), text
        )
        # 4e. Appendix references
        text = APPENDIX_REF_RE.sub(
            lambda m: self._register(m.group(0).strip(), self.TYPE_APP), text
        )
        # 5. LaTeX variable commands
        text = LATEX_VAR_RE.sub(
            lambda m: self._register(m.group(0), self.TYPE_VAR), text
        )
        # 6a. Percentages
        text = PERCENT_RE.sub(lambda m: self._register(m.group(1), self.TYPE_NUM), text)
        # 6b. p-values
        text = P_VALUE_RE.sub(lambda m: self._register(m.group(1), self.TYPE_NUM), text)
        # 6c. Ranges
        text = RANGE_RE.sub(lambda m: self._register(m.group(1), self.TYPE_NUM), text)
        # 6d. Scientific notation
        text = SCIENTIFIC_RE.sub(lambda m: self._register(m.group(1), self.TYPE_NUM), text)
        # 6e. Standalone numbers (≥1000 or decimal, to avoid ordinal-like numbers)
        text = STANDALONE_NUM_RE.sub(
            lambda m: self._register(m.group(1), self.TYPE_NUM)
            if "." in m.group(1) or int(m.group(1)) >= 1000
            else m.group(1),
            text
        )
        # 7. Known entities
        for pattern in self.entity_patterns:
            text = pattern.sub(lambda m: self._register(m.group(0), self.TYPE_ENT), text)

        return text

    def protect_sentences_json(self, data: dict) -> dict:
        """Protect all sentences in a sentences.json structure.

        Returns a new dict with protected sentences, preserving all other fields.
        """
        result = {"format": "v2", "blocks": {}, "stats": data.get("stats", {})}

        passthrough_types = {"equation", "code", "bib_item"}
        for block_id, block_data in data.get("blocks", {}).items():
            block_type = block_data.get("type", "")
            original_sentences = block_data.get("sentences", [])

            # Skip placeholder protection for passthrough block types
            # (their content is preserved verbatim, not translated)
            if block_type in passthrough_types:
                result["blocks"][block_id] = {
                    "type": block_type,
                    "heading": block_data.get("heading", ""),
                    "sentences": original_sentences,
                    "sentence_count": len(original_sentences),
                }
                continue

            protected_sentences = []

            for item in original_sentences:
                if isinstance(item, (list, tuple)):
                    # v2 format: [index, text]
                    idx, text = item[0], item[1]
                    protected_text = self.protect_text(text)
                    protected_sentences.append([idx, protected_text])
                else:
                    # v1 format: plain string
                    protected_text = self.protect_text(item)
                    protected_sentences.append(protected_text)

            result["blocks"][block_id] = {
                "type": block_data.get("type", "unknown"),
                "heading": block_data.get("heading", ""),
                "sentences": protected_sentences,
                "sentence_count": len(protected_sentences),
            }

        return result

    def get_placeholder_map(self) -> dict:
        """Export the placeholder map for serialization."""
        return {
            "version": "1",
            "entries": dict(sorted(self.ph_map.items())),
            "metadata": {
                "total_placeholders": len(self.ph_map),
                "by_type": {
                    t: sum(1 for ph in self.ph_map if ph.startswith(f"<{t}_"))
                    for t in set(
                        ph.split("_")[0][1:] for ph in self.ph_map
                    )
                },
            },
        }


def extract_known_entities(glossary: dict) -> list[str]:
    """Extract keep_english entities from the glossary for protection.

    Handles both v1 (flat) and v2 (three-level) glossary formats.
    """
    entities = []
    if isinstance(glossary, dict):
        # v2 format
        if "keep_english" in glossary:
            entities = glossary["keep_english"]
        # v1 format: flat dict — collect identity entries (original == translation)
        else:
            for orig, trans in glossary.items():
                if isinstance(trans, str) and orig.lower() == trans.lower():
                    entities.append(orig)
    return entities


def main():
    parser = argparse.ArgumentParser(
        description="Protect inline elements with placeholders"
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to sentences.json from sentencify.py"
    )
    parser.add_argument(
        "--output-dir", required=True,
        help="Output directory for protected files"
    )
    parser.add_argument(
        "--glossary", default=None,
        help="Optional path to glossary.json for entity extraction"
    )
    parser.add_argument(
        "--entities", nargs="*", default=[],
        help="Additional known entity names to protect (space-separated)"
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(json.dumps({"error": f"input file not found: {input_path}"}))
        sys.exit(1)

    data = json.loads(input_path.read_text(encoding="utf-8"))
    if "blocks" not in data:
        print(json.dumps({"error": "invalid input: missing 'blocks' key"}))
        sys.exit(1)

    # Collect known entities
    entities = list(args.entities)
    if args.glossary:
        glossary_path = Path(args.glossary)
        if glossary_path.exists():
            glossary = json.loads(glossary_path.read_text(encoding="utf-8"))
            entities.extend(extract_known_entities(glossary))

    protector = PlaceholderProtector(known_entities=entities)
    protected = protector.protect_sentences_json(data)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write protected sentences
    sentences_path = output_dir / "sentences.json"
    sentences_path.write_text(
        json.dumps(protected, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Write placeholder map
    map_path = output_dir / "placeholder_map.json"
    ph_map = protector.get_placeholder_map()
    ph_map["metadata"]["source_file"] = str(input_path.resolve())
    map_path.write_text(
        json.dumps(ph_map, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    result = {
        "status": "ok",
        "total_placeholders": ph_map["metadata"]["total_placeholders"],
        "sentences_output": str(sentences_path.resolve()),
        "map_output": str(map_path.resolve()),
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

---
name: literature-match
description: Match Markdown reference entries/参考文献 to Zotero Better BibTeX items (citekey as SSOT) and output match_result.json with candidates, itemKey, zotero_tags, and pdf_attachments. Use when you need deterministic+retrieval matching (doi/arxiv/url → TF-IDF topK → needs_llm) without modifying the input document.
compatibility: "Requires local Zotero + Better BibTeX export endpoint (127.0.0.1:23119). Python 3.11; conda env: DataProcessing. Network: localhost."
metadata:
  author: joshua
  version: "0.1.0"
---

# literature-match

## What this skill is

This skill produces a machine-consumable matching result (`match_result.json`) by aligning reference entries extracted from a Markdown document to items in a local Zotero library exported via Better BibTeX.

It is designed for controllable cost at scale:

1. **Agent extracts** reference entries from Markdown with traceability → `refs_extracted.json`.
2. Code deterministically matches using identifiers (DOI → arXiv → URL).
3. Code retrieves topK candidates via lightweight text search (TF‑IDF title similarity with minor year/author weighting).
4. **Agent adjudicates** only `needs_llm` entries, and only within the retrieved candidate set → `llm_decisions.json`.
5. Code applies decisions and produces the final `match_result.json`.

## Invariants and boundaries (must follow)

- **Global key / SSOT**: Better BibTeX `citekey` is the only stable identifier for downstream components.
- **Do not modify the input document**: no link insertion, no rewriting Markdown.
- **Do not write back to Zotero**: no tagging/collection changes as part of this skill.
- **Do not send full library to LLM**: LLM may only see one reference entry plus its topK candidates.
- **Agent steps are LLM-only**: for steps marked “Agent instructions”, do not create/execute ad-hoc scripts or new code files to perform the step; do the work in the LLM and only write the required JSON outputs to disk via the agent’s native file-writing mechanism.
- **Cross‑platform**: Zotero attachment `path` is an opaque string (do not rewrite/mmap).
- **Output JSON**: always UTF‑8 and `ensure_ascii=false`; schema must be stable (no missing required fields).

## Interfaces

### Inputs

- `doc_path`: path to the Markdown file to match.
- `doc_type` (optional): `gemini_dr | chatgpt_dr | research_card | generic_md`
- Zotero library source (choose one):
  - `zotero_endpoint` (default): `http://127.0.0.1:23119/better-bibtex/export/library?/1/library.betterbibtexjson`
  - `library_cache_path` (recommended for tests/dev): a local `library.betterbibtexjson` snapshot
- Matching parameters (recommended defaults):
  - `top_k`: 10
  - `tfidf_auto_match_threshold`: conservative; only auto-match when clearly high confidence

### Intermediate artifacts

- `refs_extracted.json`: produced by the agent (semantic extraction; tolerant schema).
- `llm_decisions.json`: produced by the agent (final adjudication for `needs_llm` only).

### Output: `match_result.json`

This skill outputs `match_result.json` (do not name it differently unless explicitly requested).

Required shape (fields may be extended, but not removed):

- `meta`: `doc_path`, `generated_at`, `zotero_endpoint`, `library_item_count`, `warnings[]`
- `refs[]`: each ref includes:
  - `ref_id`, `line_start`, `line_end`, `raw_text`
  - `parsed` (best-effort): `doi`, `url`, `arxiv`, `year`, `title_guess`, `author_guess`
  - `match`: `status`, `citekey`, `itemKey`, `method`, `confidence`
  - `candidates[]` (may be empty but must exist): each candidate includes `citekey`, `itemKey`, `score`, `title`, `year`, `authors`, `doi`, `url`, `zotero_tags`, `pdf_attachments[]`
- `stats`: counts by status

## Code execution (CLI)

The skill ships the deterministic pipeline as a CLI in `scripts/cli.py`.

Run commands from the repo root in the `DataProcessing` conda environment.

### 1) Build initial `match_result.json`

```bash
conda run --no-capture-output -n DataProcessing \
  python literature-match/scripts/cli.py match \
  --refs-extracted artifacts/<doc_stem>/refs_extracted.json \
  --library-cache examples/example_entry.library.betterbibtexjson
```

Notes:
- If `--library-cache` is omitted, the CLI will fetch from `--zotero-endpoint` (default is the local Better BibTeX endpoint).
- Output defaults to the same directory as `refs_extracted.json`.

### 2) Apply LLM decisions to finalize matches

```bash
conda run --no-capture-output -n DataProcessing \
  python literature-match/scripts/cli.py apply-decisions \
  --match-result artifacts/<doc_stem>/match_result.json \
  --llm-decisions artifacts/<doc_stem>/llm_decisions.json
```

Notes:
- Output defaults to overwriting the input `match_result.json`.
- The CLI will validate that each decision citekey is within the ref’s candidate set.

## Architecture overview

### Workflow (agent + code)

1. Agent creates `refs_extracted.json` from `doc_path` (semantic extraction, line-traceable).
2. Code reads `refs_extracted.json` + library export, produces an initial `match_result.json`:
   - deterministic matches are marked `matched`
   - ambiguous matches are marked `needs_llm` with `candidates[]`
3. Agent creates `llm_decisions.json` for `needs_llm` refs:
   - chooses a candidate `citekey` or `null`
4. Code applies `llm_decisions.json` to produce the final `match_result.json`.

### Data plane (deterministic code)

- **Reference extraction**
  - This skill treats reference extraction as an **agent instruction step** (see below).
  - Code consumes `refs_extracted.json` and focuses on stable matching + JSON output.

- **Library loading and indexing**
  - Load Better BibTeX JSON (prefer `.betterbibtexjson` format).
  - Build in-memory indices:
    - `by_doi[doi_norm] -> citekey`
    - `by_arxiv[arxiv_id] -> citekey`
    - `by_url[url_norm] -> [citekey...]`
    - `records[citekey] -> summary` (includes `itemKey`, `zotero_tags`, **all pdf_attachments**)

- **Matching**
  - Deterministic match: DOI → arXiv → URL (high confidence).
  - Retrieval: TF‑IDF over library titles for remaining refs to produce topK candidates.
  - Decide status:
    - `matched`: deterministic, or extremely clear retrieval winner
    - `needs_llm`: ambiguous but has plausible candidates
    - `needs_review` / `unmatched`: insufficient candidates or too-low confidence

### Judgment plane (LLM / human-in-the-loop)

Only for `needs_llm` refs:

- Provide the reference `raw_text` + parsed hints + `candidates[]`.
- Ask the model to output **only**:
  - a `citekey` from the provided candidates, or `null`
  - plus a brief `reason`
- Code writes the decision back into `match_result.json` (method=`llm` or `manual`), leaving candidates intact.

## Agent instructions

These steps intentionally rely on LLM semantic judgement. Do not convert them into “write a Python script and run it” automation; only the deterministic pipeline should be executed via the shipped scripts in `scripts/`.

### A) Extract references → `refs_extracted.json`

Use this when the input is a Markdown document whose References section varies by source and is hard to robustly parse with fixed rules.

**Constraints**

- Output must be **only JSON** (no Markdown fences, no commentary).
- Do not hallucinate: if uncertain, use `null`, empty lists, and add to `meta.warnings`.
- Line numbers are **1-based** and inclusive. If you cannot determine, use `-1`.
- Preserve traceability: always include `raw_text` for each extracted ref.
- Prefer writing the full JSON to disk to avoid chat/output truncation (see prompt below).
- Do not create/execute ad-hoc scripts or new code files for this step.

**Output shape (agent should follow; code will parse tolerantly)**

```json
{
  "meta": {
    "doc_path": "path/to/input.md",
    "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
    "reference_section": {"line_start": 0, "line_end": 0, "title": "References"},
    "warnings": []
  },
  "refs": [
    {
      "ref_id": "12",
      "line_start": 120,
      "line_end": 121,
      "raw_text": "…",
      "parsed": {
        "doi": null,
        "url": null,
        "arxiv": null,
        "year": null,
        "title_guess": null,
        "author_guess": null
      }
    }
  ]
}
```

**Extraction prompt (copy/paste; write-to-file to avoid truncation)**

You are given a Markdown document at `doc_path`.

Goal:
- Produce `refs_extracted.json` and **write it to disk** at:
  - `output_dir = artifacts/<doc_stem>/`
  - `output_path = artifacts/<doc_stem>/refs_extracted.json`
  - where `doc_stem` is the input filename without extension (e.g., `examples/example_entry.md` → `example_entry`).

Task:
0) Determine whether this document is a **Gemini DR** report:
   - A strong indicator is the presence of a section heading exactly like `#### **Works cited**`.
1) Read `doc_path` as UTF‑8 and split into lines using an “actual line list” method (e.g., Python `splitlines()`), then number lines **1-based**. Do not use `wc -l` for line counting.
2) Identify the true “References / 参考文献 / Works Cited / Bibliography” section. If multiple candidates exist, pick the one that actually contains citation entries.
3) Extract each reference entry as a structured ref object with `line_start/line_end/raw_text`.
   - Skip Markdown header lines (e.g., `# ...`, `## ...`, `#### **Works cited**`) as refs. Treat them as section/subsection markers only.
   - If entries wrap across multiple lines, merge them into one `raw_text` while keeping the correct `line_start/line_end`.
4) Best-effort parse `doi/url/arxiv/year/title_guess/author_guess` from each entry.
   - Do **not** infer `year` from arXiv identifiers (e.g., `arXiv:2010.04159` → do not set `year=2010`).
   - Do **not** treat “accessed …, 2025” as publication year; if no clear publication year exists, set `year=null`.
5) Write the full JSON object to `output_path` (UTF‑8; `ensure_ascii=false`; trailing newline).
6) In the chat, output only a small **confirmation JSON** (not the full refs). It must be plain JSON (no Markdown fences), for example:

`{"written_path":"artifacts/<doc_stem>/refs_extracted.json","ref_count":0,"reference_section":{"line_start":0,"line_end":0,"title":"References"},"warnings_count":0}`

Rules:
- Keep each `raw_text` close to source (do not rewrite content).
- Do not invent citekeys or Zotero data.
- If uncertain, use `null` and add a note to `meta.warnings` rather than guessing.

### B) Adjudicate `needs_llm` → `llm_decisions.json`

Use this after the code has produced an initial `match_result.json` with `needs_llm` refs.

**Constraints**

- Output must be **only JSON**.
- For each `needs_llm` ref, you may choose:
  - `citekey` that appears in that ref’s `candidates[].citekey`, or
  - `null` (if none fit).
- Do not use candidates outside topK; do not search the full Zotero library.
- Prefer writing the full JSON to disk to avoid chat/output truncation (see prompt below).
- Do not create/execute ad-hoc scripts or new code files for this step.

**Output shape**

```json
{
  "meta": {"generated_at": "YYYY-MM-DDTHH:MM:SSZ", "doc_path": "path/to/input.md"},
  "decisions": [
    {"ref_id": "12", "citekey": "some_citekey_from_candidates", "reason": "…", "confidence": 0.0}
  ]
}
```

**Adjudication prompt (copy/paste; write-to-file to avoid truncation)**

You are given `match_result.json` at `match_result_path`.

Goal:
- Produce `llm_decisions.json` and **write it to disk** at:
  - `output_dir = artifacts/<doc_stem>/`
  - `output_path = artifacts/<doc_stem>/llm_decisions.json`
  - where `doc_stem` is derived from `match_result.json.meta.doc_path` (fallback: from `match_result_path` directory name).

Task:
1) Load `match_result.json`.
2) For each entry where `match.status == "needs_llm"`:
   - Inspect its `raw_text`, parsed hints, and `candidates[]`.
   - Choose the single best `candidates[].citekey`, or `null` if none match.
   - Provide a short `reason`. If uncertain, set `citekey=null`.
3) Write the full `llm_decisions.json` object to `output_path` (UTF‑8; JSON only; trailing newline).
4) In the chat, output only a small confirmation JSON (not the full decisions). It must be plain JSON (no Markdown fences), for example:

`{"written_path":"artifacts/<doc_stem>/llm_decisions.json","decisions_count":0}`

Rules:
- `citekey` must be one of the provided `candidates[].citekey` for that ref, otherwise `null`.
- Do not add or remove refs; only decide within the candidate set.

### C) (Optional) Gemini DR Obsidian linking → `<doc>_processed.md`

If the input document is a Gemini DR report (indicator: `#### **Works cited**` exists in the Markdown), then after you have produced the **final** `match_result.json`, ask the user whether they want to generate an Obsidian-friendly processed markdown where:

- In-body numeric citations by `ref_id` are replaced with `[[citekey]]` (matched refs only).
- Each entry in “Works cited” gets an appended `[[citekey]]` (matched refs only).
- A “Reference” section (Harvard style, de-duplicated by citekey) is inserted before “Works cited”, with each entry ending with `[[citekey]]`.

If user says yes, run:

```bash
python scripts/gemini_dr_link.py --doc-path <doc_path> --match-result <match_result_path>
```

This writes `<doc_path>_processed.md` by default. Use `--output <path>` to override.

## Failure modes and required behavior

- Zotero endpoint unreachable: fail with a readable error (hint: start Zotero + Better BibTeX), and do not emit partial/invalid JSON.
- No References section found: emit `refs: []` plus a warning in `meta.warnings`.
- Library items missing fields: be tolerant (missing title/tags/attachments should not crash; output empty arrays/strings).

## References

- None (publishable skill keeps only runtime instructions and scripts)

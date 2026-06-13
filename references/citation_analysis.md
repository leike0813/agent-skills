# Citation Analysis

本文件补充 `persist_citation_analysis`。Agent 只写 citation semantic review、三段 timeline narrative 和全局 summary。Mention extraction、mapping、function 分类、timeline bucket membership、renderer labels、`report_md` 都由 runtime 从 DB workset 派生。

## Stage Shape

Prepare:

```bash
python scripts/run_analysis.py persist_citation_analysis --db-path "<db_path>"
```

Prepare 只读取：

- `section_scopes.citation_scope`
- `source_documents.normalized_source`
- persisted `reference_items`
- citation mention deterministic preprocess result

Prepare 输出：

- `citation_work_packages`
- `batch_work_packages`
- `allowed_payload_shape`
- `field_guidance`
- `subagent_prompt_template`
- `merge_contract`
- `resolved_items`
- `unresolved_mentions`
- `filtered_false_positive_mentions`
- `reference_free_mode`

Submit:

```bash
python scripts/run_analysis.py persist_citation_analysis --db-path "<db_path>" --payload-file citation.json
```

Submit payload:

```json
{
  "citation_semantic_reviews": [
    {
      "citation_work_key": "citation-work-12",
      "topic": "end-to-end object detection",
      "usage": "The source cites this work to identify direct set prediction as the closest technical lineage.",
      "role_in_context": "contrast against proposal-based detectors and motivation for transformer-style set prediction",
      "keywords": ["transformer", "object detection", "set prediction"],
      "summary": "The cited work is used as a representative end-to-end detector, helping the source position its method against transformer-based set prediction.",
      "key_reference_reason": "It anchors the source paper's comparison with direct set prediction methods."
    }
  ],
  "timeline_summaries": {
    "early": "Early citations establish background modeling ideas and evaluation foundations.",
    "middle": "Middle-period citations define mature baselines, datasets, and reusable components.",
    "recent": "Recent citations narrow the argument toward the source paper's immediate technical lineage."
  },
  "summary": "The citation scope first establishes historical and benchmark context, then contrasts mature baselines with the direct method family used to position the source paper."
}
```

## Field Guidance

- `citation_work_key`: stable key from `citation_work_packages`.
- `topic`: what the cited work represents in the selected citation scope.
- `usage`: why the source cites it and what argumentative job it performs.
- `role_in_context`: natural-language role. Runtime maps it into renderer categories.
- `keywords`: 2-5 concise phrases about method, task, dataset, or lineage.
- `summary`: item-level citation role summary; not a generic abstract of the cited paper.
- `key_reference_reason`: optional evidence for key-reference treatment.
- `timeline_summaries.early/middle/recent`: narrative summaries only. Runtime derives bucket membership from publication years.
- `summary`: global synthesis of how the source organizes and uses citations.

Do not submit mention arrays, renderer categories, internal indexes, bucket membership, or `report_md`.

Web/resource references may have no authors or publication year. That is valid input for citation review. Runtime may emit `missing_authors`, `missing_year`, or `citation_timeline_missing_year` warnings; undated items are excluded from automatic timeline buckets and do not require manual bucket membership.

## LLM And Script Responsibilities

Script/runtime owns:

- Citation mention extraction, false-positive filtering, mention-to-reference mapping, citation workset generation, renderer function/category derivation, timeline bucket membership, validation, DB persistence, and final JSON/Markdown rendering.
- JSON parsing, stable `citation_work_key` coverage checks, duplicate checks, warnings, and report rendering.

LLM/subagent owns:

- Citation semantic review for each `citation_work_key`: `topic`, `usage`, `role_in_context`, `keywords`, item `summary`, and optional `key_reference_reason`.
- Main agent owns `timeline_summaries` and global `summary` after merging batch drafts.

Do not use a temporary script, keyword classifier, or bulk rule to infer citation topics, usage, roles, key-reference reasons, timeline narratives, or global summary. Scripts may only inspect work packages, count key coverage, merge already-returned subagent drafts, serialize JSON, or call `run_analysis.py`.

## Mandatory Subagent Delegation Point

Use subagents by default when available for batchable work.

When `batch_work_packages` are present and the environment supports subagents, the main agent must delegate citation semantic review by batch unless the batch is trivially small or cannot be split without losing context. If delegation is skipped, keep the reason in execution notes.

Use the following prompt at the Citation Semantic Review Delegation Point: after `persist_citation_analysis` prepare returns `citation_work_packages` and `batch_work_packages`, and before constructing the final `citation_semantic_reviews[]` payload.

Main agent:

1. Runs prepare and reads `citation_work_packages`, `batch_work_packages`, `field_guidance`, and unresolved/filtered mention summaries.
2. Sends each batch to a subagent by default when subagents are available.
3. Merges returned `citation_semantic_reviews`.
4. Checks every `citation_work_key` appears exactly once.
5. Writes `timeline_summaries` and global `summary`.
6. Submits one final payload.

Subagent prompt template:

```text
You are reviewing one literature-analysis citation semantic batch.
Use only the provided citation_work_packages.
Return JSON with citation_semantic_reviews[] only.
Each review must include citation_work_key, topic, usage, role_in_context, keywords, summary, and optional key_reference_reason.
Do not include internal indexes, mention arrays, renderer categories, timeline buckets, timeline_summaries, global summary, or report markdown.
Do not write DB, run runtime commands, submit payloads, modify citation_work_key, or generate final artifacts.
```

Subagent batch draft:

```json
{
  "batch_key": "citation-batch-0",
  "citation_semantic_reviews": [
    {
      "citation_work_key": "citation-work-4",
      "topic": "COCO detection benchmark",
      "usage": "The source cites it to justify the evaluation dataset and metrics.",
      "role_in_context": "dataset and benchmark grounding",
      "keywords": ["COCO", "object detection", "benchmark"],
      "summary": "The cited work grounds the evaluation setting by defining the COCO benchmark used in the source paper.",
      "key_reference_reason": "The benchmark frames the experimental claims."
    }
  ],
  "uncertainties": []
}
```

The main agent is the only DB writer. It merges all subagent `citation_semantic_reviews[]`, keeps every `citation_work_key` unchanged, removes duplicates, and writes the single global `timeline_summaries` and `summary`. Subagents do not decide timeline bucket membership.

## Preprocess Rules

Mention extraction supports:

- Numeric citations: `[5]`, `[5, 36]`, `[4,15,38]`, `[40-42]`, `[40–42]`.
- Author-year citations: `(Smith, 2020)`, `Smith et al. (2020)`, `(Smith & Jones, 2020; Brown, 2019)`.
- LaTeX citations: `\cite{...}`, `\citep{...}`, `\citet{...}`, multi-key `\cite{a,b,c}`.

False-positive filtering removes or counts:

- Markdown image links
- plain URLs
- resource paths
- `.jpg` / `.png` / `.pdf` suffixes
- date-like strings

Filtered cases contribute to `citation_false_positive_filtered`.

Mapping preference:

1. LaTeX `citekey_hint` to persisted `citekey` / `bibitem_key`.
2. Numeric source reference number to persisted reference item.
3. Author-year `year + first-author surname aliases`.
4. Local snippet support.

Author-year aliases:

- `Cheng, G.` -> `cheng`
- `Waqas Zamir, S.` -> `waqas zamir` and `zamir`

Ambiguous mentions remain in `unmapped_mentions`. Do not hard-guess mappings in semantic payload.

Reference-free mode:

- Only valid after DB-backed `file_quality_low=true` and an explicit abandoned reference extraction decision.
- Reason must be `references_abandoned_file_quality_low`.
- Semantic reviews may be empty, but `timeline_summaries` and global `summary` must still validate.

## Work Packages

Each `citation_work_packages[]` item contains:

- `citation_work_key`
- `source_reference_number`
- `title`
- `authors`
- `publication_year`
- `mention_count`
- `snippets`

`source_reference_number` is displayed so humans can orient themselves against the paper's `[1]`, `[2]`, etc. It is not a submit key.

## Semantic Writing Rules

`topic`:

- Good: `COCO detection benchmark`
- Bad: `The paper cited in [4]`

`usage`:

- Good: `The source cites it to define the benchmark and standard metrics used in the experiments.`
- Bad: `It is related work.`

`role_in_context`:

- Good: `dataset and benchmark grounding`
- Good: `contrast against proposal-based detectors`
- Good: `historical background for attention mechanisms`
- Bad: `background`

Runtime derives renderer categories such as:

- `background`
- `baseline`
- `contrast`
- `component`
- `dataset`
- `tooling`
- `historical`
- `uncategorized`

These words can appear naturally in `role_in_context`, but agent should not submit a category field.

`summary`:

- Good: `The cited work is used to define the COCO benchmark and the evaluation metrics that frame the source paper's experimental claims.`
- Bad: `This paper introduces the COCO dataset and is widely used.`

`key_reference_reason`:

- Use when the cited work anchors the source argument, method lineage, benchmark, or central contrast.
- Leave absent or empty when the item is ordinary background.

## Timeline And Summary

Agent writes:

```json
{
  "timeline_summaries": {
    "early": "Early citations establish the background assumptions.",
    "middle": "Middle-period citations consolidate baselines and datasets.",
    "recent": "Recent citations define the closest technical comparisons."
  },
  "summary": "The source organizes citations from broad background through benchmarks toward its closest method family."
}
```

Runtime derives:

- dated item membership for `early`, `mid`, and `recent`
- timeline closure over all dated citation items
- key-reference index list from non-empty `key_reference_reason`
- renderer labels and `report_md`

All stable dated items are placed into exactly one bucket by runtime. The agent should not maintain a manual list.

## Validation Failures

Validation reports all common payload issues in one response:

- missing `citation_semantic_reviews`
- missing `timeline_summaries.early`
- missing `timeline_summaries.middle`
- missing `timeline_summaries.recent`
- duplicate `citation_work_key`
- unknown `citation_work_key`
- missing reviews for expected keys
- forbidden submit fields
- missing `topic`, `usage`, `role_in_context`, `keywords`, or `summary`

Example:

```json
{
  "error": {
    "code": "citation_payload_invalid",
    "details": [
      "duplicate citation_work_key: citation-work-8",
      "unknown citation_work_key: citation-work-99",
      "missing citation_semantic_reviews for citation_work_key values: ['citation-work-13']",
      "timeline_summaries.middle must be non-empty string"
    ]
  }
}
```

Forbidden submit content:

- renderer-owned categories
- internal indexes
- mention arrays
- manual timeline bucket membership
- renderer report Markdown

These are invalid because submit payload should contain semantic reviews and narrative summaries only.

## Public Render Contract

Rendered `citation_analysis.json` includes:

- `meta`
- `summary`
- `timeline`
- `items`
- `unmapped_mentions`
- `report_md`

`citation_analysis.md` must equal `citation_analysis.json.report_md`.

The agent does not write `report_md`. The renderer derives it from persisted semantic reviews, derived timeline, unmapped mentions, and templates.

## Failure And Recovery Notes

- `citation_mentions_not_found`: review `citation_scope`; do not invent semantic reviews.
- `citation_false_positive_filtered`: expected when URLs/images/dates were removed; inspect only if many real citations disappeared.
- `references_abandoned_file_quality_low`: valid only for reference-free mode after DB-backed low-quality reference decision.
- `citation_timeline_missing_year`: publication year missing for some items; runtime still closes over dated items.
- `citation_merge_failed`: repair duplicate or missing `citation_work_key` entries and resubmit.
- `illegal scope override`: do not submit scope changes in this stage.
- `statistical summary without basis`: global summary should explain the source argument, not just count citations.

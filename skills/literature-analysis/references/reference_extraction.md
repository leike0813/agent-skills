# Reference Extraction

本文件补充 `persist_references`。目标是让 agent 只做语义审核：确认条目边界、选择 parse hypothesis、修正文献核心字段，并在 core references 入库后再补充有证据的 metadata。原文文本、置信度、内部序号、parse audit、渲染字段由 runtime 从 DB workset 派生。

## Stage Shape

Prepare:

```bash
python scripts/run_analysis.py persist_references --db-path "<db_path>"
```

Prepare 只读取 DB 中的 `source_documents.normalized_source` 和 `section_scopes.references_scope`。stdout 只输出摘要、路径和小型契约；大型 work packages 写入 `.literature_analysis_tmp/agent_work/` 下的 manifest / batch JSON 文件：

- `reference_core_review_manifest_path`
- `reference_core_batch_paths`
- `reference_core_package_count`
- `reference_core_batch_count`
- `reference_core_required_coverage_keys`
- `split_review_packages_path`
- `split_review_package_count`
- `batch_max_items`
- `allowed_payload_shape`
- `field_guidance`
- `subagent_prompt_template`
- `merge_contract`
- `reference_preprocess_quality`
- `file_quality_low`
- `suspect_blocks`

Submit:

```bash
python scripts/run_analysis.py persist_references --db-path "<db_path>" --payload-file references.json
```

Core submit payload:

```json
{
  "reference_reviews": [
    {
      "reference_key": "reference-0",
      "selected_parse_pattern": "authors_colon_title_in_year",
      "authors": ["Lin, T.-Y.", "Maire, M.", "Belongie, S."],
      "title": "Microsoft COCO: common objects in context",
      "publication_year": 2014,
      "review_notes": "LNCS tail belongs to the same reference, not separate entries."
    }
  ]
}
```

Reference Metadata Evidence Review submit payload, after runtime returns `metadata_evidence_review_manifest_path` and `metadata_evidence_batch_paths`:

```json
{
  "metadata_evidence_reviews": [
    {
      "reference_key": "reference-0",
      "status": "fields_extracted",
      "metadata": {
        "conferenceName": "ECCV",
        "publicationTitle": "Lecture Notes in Computer Science",
        "volume": "8693",
        "pages": "740-755",
        "publisher": "Springer",
        "place": "Cham",
        "DOI": "10.1007/978-3-319-10602-1_48"
      },
      "evidence_note": "DOI is present in metadata_context_text."
    }
  ]
}
```

Split repair payload, before core submit when `split_review_packages` require boundary review:

```json
{
  "split_reviews": [
    {
      "block_key": "block-3",
      "action": "replace_with_corrected_reference_texts",
      "corrected_reference_texts": [
        "Lin, T.-Y., et al.: Microsoft COCO: common objects in context. In: Fleet, D., Pajdla, T., Schiele, B., Tuytelaars, T. (eds.) ECCV 2014. LNCS, vol. 8693, pp. 740-755. Springer, Cham (2014)."
      ]
    }
  ]
}
```

`reference_reviews` and `metadata_evidence_reviews` are separate submit rounds. Do not submit them together. `reference_reviews[].metadata` is forbidden because Reference Metadata Evidence Review must use the runtime-generated metadata evidence batch files. In plain terms: reference_reviews[].metadata is forbidden. `split_reviews` is used first when boundary repair is required; if it changes boundaries, runtime regenerates reference core batch files and the agent must submit `reference_reviews` with the regenerated keys afterward.

## Field Guidance

- `reference_key`: stable work key from the assigned `reference_core_batch_paths` file.
- `selected_parse_pattern`: required parse hypothesis. It must be one of the assigned batch file's `allowed_parse_patterns_by_reference_key[reference_key]`.
- `authors`: author strings in source order. Preserve initials and compound surnames.
- `title`: cited work title in the original language/script.
- `publication_year`: publication year as integer, or `null` when unsupported.
- `review_notes`: short uncertainty/evidence note for the main agent and audit trail.

Do not submit metadata, raw source text, confidence values, renderer labels, parse audit, or database IDs in `reference_reviews[]`. Runtime derives audit fields from DB-backed entries and selected candidates. Rich metadata is submitted only in the second metadata round.

Metadata review fields:

- `reference_key`: stable key from the assigned `metadata_evidence_batch_paths` file.
- `status`: one of `fields_extracted`, `existing_fields_confirmed`, `no_local_evidence`.
- `metadata`: required only for `status=fields_extracted`; omit or leave empty for `existing_fields_confirmed` and `no_local_evidence`.
- `evidence_note`: short note tying metadata to `locked_reference`, `existing_metadata`, `metadata_context_text`, or raw/source text explicitly present in the batch JSON file.

Do not modify locked core fields in metadata review. The workset exposes locked fields once in `instructions.locked_fields`; individual items show `locked_reference` only for reading.

Canonical metadata fields:

- `publicationTitle`, `conferenceName`, `archiveID`, `university`
- `volume`, `issue`, `pages`, `numPages`
- `DOI`, `url`
- `publisher`, `place`, `ISBN`, `ISSN`
- `itemType`, `date`

Common deterministic aliases are accepted only as a fallback and are normalized with warnings:

- `journal`, `journalTitle`, `journal_title` -> `publicationTitle`
- `doi` -> `DOI`
- `isbn` -> `ISBN`
- `issn` -> `ISSN`
- `arxiv`, `arXiv`, `arxivId`, `arxiv_id`, `archiveId` -> `archiveID`
- bare arXiv ids such as `2004.10934` -> `arXiv:2004.10934`

Alias normalization produces `reference_metadata_alias_normalized` warnings so the main agent can see which fallback was applied.

Unknown metadata fields do not block persistence by themselves, but they produce `reference_metadata_field_unrecognized` warnings and should be corrected by the main agent during merge.

## LLM And Script Responsibilities

Script/runtime owns:

- Reference scope reading from DB, deterministic preprocess, split suspicion detection, candidate generation, allowed parse pattern lists, quality metrics, metadata workset generation, validation, DB persistence, and final `references.json` rendering.
- JSON parsing, stable key coverage checks, duplicate checks, metadata alias normalization, and warning/audit sidecars.

LLM/subagent owns:

- Split review boundary judgment and source-preserving `corrected_reference_texts`.
- Core reference review: selecting `selected_parse_pattern`, refining authors/title/year, and writing `review_notes`.
- Reference Metadata Evidence Review: deciding `status`, local evidence-backed canonical metadata fields, and `evidence_note`.

Do not use a temporary script, regex batch processor, or bulk transformation to infer authors, titles, years, parse pattern choices, split boundaries, or metadata. Scripts may only inspect runtime packages, count key coverage, merge already-returned subagent drafts, normalize JSON syntax, or call `run_analysis.py`.

## Mandatory Subagent Delegation Points

Use subagents by default when available for batchable work.

When `reference_core_batch_paths` or `metadata_evidence_batch_paths` are present and the environment supports subagents, the main agent must delegate core reference review and Reference Metadata Evidence Review by runtime-precut batch unless the batch is trivially small or cannot be split without losing context. If delegation is skipped, keep the reason in execution notes or `review_notes`.

Use the prompt sections below at the exact task points named here.

Subagent prompt template sections are task-specific. Use the core prompt only at the Reference Core Review Delegation Point, and use the metadata prompt only at the Reference Metadata Evidence Review Delegation Point.

Runtime owns batch splitting. Do not manually split a full workset or review sidecar into subagent inputs. Each batch JSON file contains at most 10 entries, the package subset, allowed enum subset, prompt, merge notes, and `suggested_draft_output_path`.

### Reference Core Review Delegation Point

When `persist_references` prepare returns `reference_core_review_manifest_path` and `reference_core_batch_paths`, delegate each core batch by passing the batch JSON file path to a subagent. Do this before constructing the final `reference_reviews[]` payload.

Main agent:

1. Runs prepare and reads `reference_core_review_manifest_path`, `reference_core_batch_paths`, counts, `field_guidance`, and `merge_contract`.
2. Sends each core batch JSON file path to a subagent by default when subagents are available.
3. Merges returned drafts.
4. Checks every `reference_key` appears exactly once.
5. Submits one core `reference_reviews[]` payload.

Core review subagent prompt template:

```text
You are reviewing one literature-analysis reference batch.
Read the batch JSON file path provided by the main agent.
Use only reference_review_packages and allowed_parse_patterns_by_reference_key in that batch file.
Return JSON with reference_reviews[] only.
For each package, choose selected_parse_pattern from the allowed list, then provide authors, title, publication_year, and review_notes.
Do not include metadata. Reference Metadata Evidence Review happens in the next metadata_evidence_packages round.
Do not include raw text, confidence, database IDs, renderer fields, or entries outside this batch.
If file writing is available, write the draft to suggested_draft_output_path and return that path.
Do not write DB, run runtime commands, submit payloads, modify stable keys, or generate final artifacts.
```

Subagent batch draft shape:

```json
{
  "batch_key": "reference-batch-0",
  "reference_reviews": [
    {
      "reference_key": "reference-0",
      "selected_parse_pattern": "venue_marker",
      "authors": ["Carion, N.", "Massa, F.", "Synnaeve, G."],
      "title": "End-to-end object detection with transformers",
      "publication_year": 2020,
      "review_notes": "Venue marker candidate preserves title and venue."
    }
  ],
  "uncertainties": []
}
```

### Reference Metadata Evidence Review Delegation Point

When core `reference_reviews[]` submit succeeds and runtime returns `metadata_evidence_review_manifest_path` and `metadata_evidence_batch_paths`, delegate each metadata evidence batch by passing the batch JSON file path to a subagent. Do this before constructing the final `metadata_evidence_reviews[]` payload.

Main agent:

1. Reads returned metadata evidence manifest, batch paths, and instruction-level allowed/locked fields.
2. Sends each metadata evidence batch JSON file path to a subagent by default when subagents are available.
3. Merges returned drafts.
4. Checks every metadata `reference_key` appears exactly once.
5. Corrects obvious alias fields to canonical names when merging.
6. Submits one `metadata_evidence_reviews[]` payload.

Reference Metadata Evidence Review subagent prompt template:

```text
This is not a metadata discovery task.
You are reviewing one literature-analysis metadata evidence batch.
Read the batch JSON file path provided by the main agent.
Return JSON with metadata_evidence_reviews[] only.
Use reference_key as the key.
For each item, set status to fields_extracted, existing_fields_confirmed, or no_local_evidence.
Only add metadata when status is fields_extracted, and only when it appears in locked_reference, existing_metadata, metadata_context_text, or raw/source text explicitly present in this batch JSON file.
Use canonical metadata fields only: publicationTitle, conferenceName, archiveID, university, volume, issue, pages, numPages, DOI, url, publisher, place, ISBN, ISSN, itemType, date.
Do not modify authors, title, publication_year, selected_parse_pattern, raw text, confidence, ref_index, or other locked/internal fields.
external_lookup_allowed: false.
No web search. Do not use Crossref, arXiv, Google Scholar, Zotero, Semantic Scholar, DOI resolver, or any external database.
Do not infer venue from general knowledge, guess DOI from title, or guess publisher/venue from author/year.
If the information is not visible in the batch JSON file, return no_local_evidence. Do not search.
Do not write DB or final artifacts. Return only the batch draft.
If file writing is available, write the draft to suggested_draft_output_path and return that path.
Do not run runtime commands, submit payloads, or modify stable keys.
```

Metadata batch draft shape:

```json
{
  "batch_key": "metadata-batch-0",
  "metadata_evidence_reviews": [
    {
      "reference_key": "reference-0",
      "status": "fields_extracted",
      "metadata": {
        "publicationTitle": "Lecture Notes in Computer Science",
        "volume": "8693",
        "pages": "740-755"
      },
      "evidence_note": "The LNCS volume and page range are present in metadata_context_text."
    },
    {
      "reference_key": "reference-1",
      "status": "no_local_evidence",
      "evidence_note": "No container, DOI, URL, or archive id appears in metadata_context_text."
    }
  ],
  "uncertainties": []
}
```

The main agent is the only DB writer. It must merge subagent drafts, keep each `reference_key` stable, remove duplicates, cover every metadata evidence package, and prefer canonical metadata names before submitting. Runtime normalizes common aliases as a fallback, but subagent prompts should not rely on that fallback. The normalizer does not permit external discovery.

## Metadata Workset Shape

Metadata prepare output uses instruction-level guidance:

- `instructions.allowed_metadata_fields`: canonical metadata fields allowed in `metadata_evidence_reviews[].metadata`.
- `instructions.locked_fields`: core fields that metadata review must not change.
- `metadata_evidence_review_manifest_path`: manifest containing coverage keys and batch paths.
- `metadata_evidence_batch_paths`: runtime-precut subagent input files, each with at most 10 metadata evidence packages.
- `subagent_prompt_template`: ready-to-use metadata prompt.
- `merge_contract`: required coverage and forbidden fields.
- `external_lookup_allowed`: always `false`.
- `evidence_policy`: local evidence sources and forbidden external lookup actions.

Each metadata package contains item-specific context only:

- `reference_key`
- `locked_reference`
- `existing_metadata`
- `metadata_context_text`
- `batch_id`
- `status`

Do not expect each item to repeat `allowed_metadata_fields`; read those once from `instructions`.

## Evidence Policy Examples

Reference Metadata Evidence Review is not metadata discovery.

Allowed evidence:

- `locked_reference`
- `existing_metadata`
- `metadata_context_text`
- raw/source text explicitly present in the assigned batch JSON file

Forbidden actions:

- no web search
- no Crossref/arXiv/DOI resolver
- no Google Scholar, Zotero, Semantic Scholar, or external database
- no guessing DOI from title
- no guessing venue, publisher, or place from author/year

Legal: if raw text contains `arXiv:2004.10934`, return `archiveID: "arXiv:2004.10934"` and cite `metadata_context_text` in `evidence_note`.

Illegal: if no DOI appears in the batch JSON file, do not search the title online and do not return a DOI.

Legal: a web/resource reference may have no authors or year; extract only visible `url` or `itemType` evidence and leave missing core fields unchanged.

Legal: only preserve LNCS volume/pages or conference metadata when `LNCS`, `vol.`, page range, or the venue tail is visible in the batch JSON file.

## Bibliography Formats

Common block titles:

- `References`
- `REFERENCES`
- `Bibliography`
- `Works Cited`
- `参考文献`
- `引用文献`

Common styles:

- Numeric: `[1] ...`, `1. ...`, `1) ...`.
- Author-date: `Author, A. A. (2020). ...`, `Author A, Author B. 2020. ...`.
- Bibitem: `\bibitem{key} ...`; keep `bibitem_key` in metadata when present.
- BibTeX: top-level `@article{key, ...}` / `@inproceedings{key, ...}`; keep `citekey` and `entry_type` in metadata when present.
- GB/T 7714: numeric entries plus `［J］`, `［C］`, `［D］`, `［M］`, `［EB/OL］`.

GB/T 7714 and CJK rules:

- `等` / `et al.` means authors are truncated; do not invent hidden authors.
- `［J］` journal, `［C］` conference, `［D］` thesis, `［M］` book, `［EB/OL］` online carrier.
- Type markers are not reference numbers.
- `cjk_type_marker_entry` is a valid parse pattern when the type marker supports title/container boundaries.
- Fullwidth punctuation should be normalized for parsing but the title text should remain in the original language.

MinerU/noisy Markdown cues:

- Same entry may be broken across lines.
- Reference number may be isolated.
- Page headers, footers, running titles, figure captions, and HTML tables may pollute the block.
- Use Unicode-aware tokenizer and CJK/fullwidth normalization before judging CJK boundaries.

## Parse Pattern Guidance

Prepare provides allowed pattern names per `reference_key`. Common values include:

- `ieee_quote_title`
- `venue_marker`
- `cjk_type_marker_entry`
- `authors_period_title_period_venue_year`
- `authors_colon_title_in_year`
- `authors_year_paren_title_venue`
- `thesis_or_book_tail_year`
- `fallback_raw_split`

Rules:

- `selected_parse_pattern` must be copied exactly from the allowed enum for that package.
- Prefer a pattern that preserves title, author boundary, and publication year.
- Use `fallback_raw_split` only when stronger patterns are absent or incorrect.
- If all candidates are bad, still choose the least harmful allowed pattern and explain the repair in `review_notes`.

## LNCS And Split Review

LNCS-style references often look like several sentences, but remain one reference:

```text
23. Lin, T.-Y., et al.: Microsoft COCO: common objects in context. In: Fleet, D., Pajdla, T., Schiele, B., Tuytelaars, T. (eds.) ECCV 2014. LNCS, vol. 8693, pp. 740-755. Springer, Cham (2014).
```

Do not split these fragments as independent references:

- `LNCS, vol. 8693`
- `pp. 740-755`
- `Springer, Cham (2014)`
- DOI or URL continuation
- editor/proceedings continuation after `In:`

If `split_review_packages` appear, each package has:

- `block_key`
- `source_text`
- `current_fragments`
- `allowed_actions`

Allowed actions:

- `keep`: current fragments are acceptable.
- `replace_with_corrected_reference_texts`: replace fragments with complete reference texts; this is a boundary-changing action.

Split review rules:

- Split review changes only boundaries.
- Do not extract authors/title/year during split review.
- `corrected_reference_texts` must preserve source content by token coverage, not by exact character equality.
- Harmless differences are allowed: line breaks, repeated whitespace, Unicode normalization, fullwidth/halfwidth punctuation, quote style, dash style, soft hyphen, and punctuation style.
- Hard failures remain: translated text, rewritten titles, deleted DOI/URL/arXiv IDs, deleted years, deleted author/title keywords, or added unsupported content.
- If conservation fails, runtime returns `missing_tokens_sample`, `unexpected_tokens_sample`, `source_token_count`, `reviewed_token_count`, and `coverage_ratio`.
- Boundary-changing split review returns regenerated `reference_review_packages`; do not reuse stale `reference_reviews` from before the split repair.
- If token conservation passes but deterministic boundary heuristics still look suspicious, runtime records `reference_boundary_suspicion_after_review` and continues with regenerated packages.
- Web/resource references, project pages, software repositories, and URL-only resources may lack authors or publication years. Keep `publication_year=null` in core review and add `url` or `itemType` in metadata review when evidence exists.
- If a grouped-entry loses source tokens or remains structurally impossible to review, runtime may report `reference_entry_splitting_failed`.

## Core Field Rules

Authors:

- Keep author order.
- Keep compound surnames intact: `Al-Rfou, R.` is one author string.
- Keep multi-token names intact when source writes them as one author.
- Do not split initials into standalone authors.
- Do not invent omitted authors after `et al.` / `等`.

Title:

- Title must be in the original language/script.
- Do not translate, romanize, or title-case CJK titles.
- Do not use `none`, `null`, `unknown`, `untitled`, `N.A.`, DOI, URL, arXiv ID, or venue name as title. This is `placeholder_title` or `bare_identifier_or_url_title`.
- Title must not start with comma, period, semicolon, colon, or closing punctuation.

Year:

- Prefer the publication year near the end of the entry or in standard year position.
- Do not use arXiv ID prefixes as year.
- Do not use page ranges, volume numbers, or reference numbers as year.

Metadata:

- `publicationTitle`: journal/container title.
- `conferenceName`: conference/proceedings venue.
- `archiveID`: arXiv or preprint identifier.
- `university`: thesis/dissertation institution.
- `volume`, `issue`, `pages`, `numPages`.
- `DOI`, `url`.
- `publisher`, `place`.
- `ISBN`, `ISSN`.
- `itemType`, `date`.

Metadata priority:

1. `publicationTitle`, `conferenceName`, `archiveID`, `university`
2. `volume`, `issue`, `pages`, `numPages`
3. `DOI`, `url`
4. `publisher`, `place`, `ISBN`, `ISSN`

`metadata_context_text` is the evidence field for enrichment. Enrichment cannot modify locked core fields: authors, title, publication_year, source text, selected_parse_pattern.

## Quality Signals

`reference_preprocess_quality` summarizes deterministic file quality. Important signals:

| Signal | Trigger | Meaning |
|---|---:|---|
| `fallback_best_ratio` | `> 0.50` | Most entries only have fallback candidates |
| `year_ratio` | `< 0.20` | Few entries have valid years |
| `warning_density` | `> 1.0` | More than one warning per entry on average |
| `numbering_anomaly` | `true` | Numbering is non-monotonic, discontinuous, or dirty |
| `empty_title_ratio` | `> 0.30` | Many best candidates lack usable titles |

When `file_quality_low=true`, do not fabricate high-confidence rows. Use split review, conservative titles, and explicit `review_notes`. Abandoning references is valid only when the DB-backed quality snapshot allows it.

`quality_directives` may report hard and soft issues:

- `placeholder_title`
- `bare_identifier_or_url_title`
- `empty_title`
- `reference_author_refinement_invalid`
- `reference_numbering_anomaly_detected`
- `reference_parse_low_confidence`

Hard block example:

```json
{
  "error": {
    "code": "reference_payload_invalid",
    "details": [
      "reference-7.selected_parse_pattern must be one of ['venue_marker', 'fallback_raw_split']",
      "missing reference_reviews for reference_key values: ['reference-11']"
    ]
  }
}
```

Soft warning example:

```json
{
  "warnings": [
    {
      "code": "reference_numbering_anomaly_detected",
      "message": "Reference numbering is discontinuous; persisted rows remain usable."
    }
  ]
}
```

## Runtime Truth Sources

Runtime tables and sidecars used by this stage:

- `reference_entries`: deterministic entry boundaries.
- `reference_parse_candidates`: parse hypotheses.
- `reference_items`: persisted normalized references.
- `reference_metadata_evidence_workset`: local metadata evidence review aid.

Public `references.json` is rendered from `reference_items`. It contains bibliographic fields and renderer-owned `ref_index`, but not parse/debug fields. The agent never edits it directly. Parse candidate audit lives in `.literature_analysis_tmp/reference_parse_audit.json`.

## Examples

Example 1: Preprint

Source text:

```text
Joshua Ainslie, Santiago Ontanon, Chris Alberti, Philip Pham, Anirudh Ravula, and Sumit Sanghai. Etc: Encoding long and structured data in transformers. arXiv preprint arXiv:2004.08483, 2020.
```

Core review:

```json
{
  "reference_key": "reference-1",
  "selected_parse_pattern": "authors_period_title_period_venue_year",
  "authors": ["Joshua Ainslie", "Santiago Ontanon", "Chris Alberti", "Philip Pham", "Anirudh Ravula", "Sumit Sanghai"],
  "title": "Etc: Encoding long and structured data in transformers",
  "publication_year": 2020,
  "review_notes": "The arXiv preprint tail supports the year but metadata is submitted separately."
}
```

Metadata evidence review:

```json
{
  "reference_key": "reference-1",
  "status": "fields_extracted",
  "metadata": {"archiveID": "arXiv:2004.08483"},
  "evidence_note": "The archive id appears in the source text."
}
```

Example 2: Conference

Source text:

```text
[11] Gu, J., Bradbury, J., Xiong, C., Li, V.O., Socher, R.: Non-autoregressive neural machine translation. In: ICLR (2018).
```

Core review:

```json
{
  "reference_key": "reference-11",
  "selected_parse_pattern": "authors_colon_title_in_year",
  "authors": ["Gu, J.", "Bradbury, J.", "Xiong, C.", "Li, V.O.", "Socher, R."],
  "title": "Non-autoregressive neural machine translation",
  "publication_year": 2018,
  "review_notes": "The ICLR marker is retained for metadata review."
}
```

Metadata evidence review:

```json
{
  "reference_key": "reference-11",
  "status": "fields_extracted",
  "metadata": {"conferenceName": "ICLR"},
  "evidence_note": "The source text contains `In: ICLR (2018)`."
}
```

Example 3: Short conference entry

Source text:

```text
He, K., Zhang, X., Ren, S., Sun, J. Deep residual learning for image recognition. CVPR, 2016.
```

Core review:

```json
{
  "reference_key": "reference-3",
  "selected_parse_pattern": "venue_marker",
  "authors": ["He, K.", "Zhang, X.", "Ren, S.", "Sun, J."],
  "title": "Deep residual learning for image recognition",
  "publication_year": 2016,
  "review_notes": "Venue marker separates title from conference."
}
```

Metadata evidence review:

```json
{
  "reference_key": "reference-3",
  "status": "fields_extracted",
  "metadata": {"conferenceName": "CVPR"},
  "evidence_note": "The venue appears before the year."
}
```

Example 4: Journal

Source text:

```text
Smith J, Brown P. A survey of citation-aware retrieval. Journal of Information Science, 45(2): 100-115, 2019.
```

Core review:

```json
{
  "reference_key": "reference-4",
  "selected_parse_pattern": "authors_period_title_period_venue_year",
  "authors": ["Smith J", "Brown P"],
  "title": "A survey of citation-aware retrieval",
  "publication_year": 2019,
  "review_notes": "Journal, volume, issue, and pages are metadata evidence."
}
```

Metadata evidence review:

```json
{
  "reference_key": "reference-4",
  "status": "fields_extracted",
  "metadata": {"publicationTitle": "Journal of Information Science", "volume": "45", "issue": "2", "pages": "100-115"},
  "evidence_note": "The source text contains the journal title, volume, issue, and page range."
}
```

Example 5: Thesis

Source text:

```text
Wang, L. Neural methods for document understanding. PhD thesis, Tsinghua University, Beijing, 2021.
```

Core review:

```json
{
  "reference_key": "reference-5",
  "selected_parse_pattern": "thesis_or_book_tail_year",
  "authors": ["Wang, L."],
  "title": "Neural methods for document understanding",
  "publication_year": 2021,
  "review_notes": "The thesis tail supports institution and place metadata."
}
```

Metadata evidence review:

```json
{
  "reference_key": "reference-5",
  "status": "fields_extracted",
  "metadata": {"university": "Tsinghua University", "place": "Beijing"},
  "evidence_note": "The institution and place appear in the thesis tail."
}
```

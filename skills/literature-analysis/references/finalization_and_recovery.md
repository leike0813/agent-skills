# Finalization And Recovery

本文件补充 `finalize_outputs`、render validation 和错误恢复。正常路径下，`persist_citation_analysis` 提交成功后会级联渲染最终产物；`finalize_outputs` 主要用于恢复或手动重渲染。

## Finalization Contract

`finalize_outputs` reads from DB only:

- runtime paths
- runtime templates
- `digest_slots`
- `digest_section_summaries`
- `reference_items`
- `literature_matching_metadata`
- `citation_workset_items`
- `citation_items`
- `citation_timeline`
- `citation_summary`
- `citation_unmapped_mentions`
- `citation_scope`

It does not accept:

- business payload
- source path override
- language override
- output directory override
- hand-authored `report_md`
- hand-authored final JSON

Formal render truth:

- `digest.md` derives from `digest_slots + digest_section_summaries`.
- `references.json` derives from `reference_items`.
- `citation_analysis.json.summary` derives from `citation_summary`.
- `citation_analysis.json.timeline` derives from `citation_timeline`.
- `citation_analysis.json.items` derives from `citation_workset_items + citation_items`.
- `citation_analysis.json.report_md` derives from citation summary/timeline/items/unmapped/scope.
- `citation_analysis.md` must exactly equal `citation_analysis.json.report_md`.
- `literature_matching_metadata.json` derives from DB `literature_matching_metadata`.
- `representative_image` is optional stdout metadata from digest stage; it is not a public artifact.

## Published Artifacts

Required fixed filenames:

- `digest.md`
- `references.json`
- `citation_analysis.json`
- `literature_matching_metadata.json`

Optional/additive:

- `citation_analysis.md`
- `representative_image` field in stdout

All paths in stdout must be absolute.

Success stdout must include:

- `digest_path`
- `references_path`
- `citation_analysis_path`
- `literature_matching_metadata_path`
- `provenance.generated_at`
- `provenance.input_hash`
- `provenance.model`
- `warnings`
- `error`

Optional stdout keys:

- `citation_analysis_report_path`
- `representative_image`

Failure stdout remains schema-compatible: path fields are empty strings where unavailable, and `error` is `{code, message}`.

## Result Mirror And Artifact Registry

Runtime writes a result mirror JSON to `result_json_path`. The file content should match stdout JSON. If they diverge, rerun `finalize_outputs`; do not hand-edit the mirror.

Artifact registry should record at least:

- `digest_path` from `digest_slots`
- `references_path` from `reference_items`
- `citation_analysis_path` from `citation_summary`
- `literature_matching_metadata_path` from `literature_matching_metadata`

If renderer generated non-empty `report_md`, also record:

- `citation_analysis_report_path` from `citation_summary`

Warning aggregation may include:

- `scope_fallback_used`
- `reference_numbering_anomaly_detected`
- `reference_parse_low_confidence`
- `citation_false_positive_filtered`
- `no_mentions_found_in_review_scope`
- `digest_undercoverage`

## Safe-To-Regenerate Files

These files may be deleted and regenerated when DB state is complete:

- source sidecars such as `source.md` / `source_meta.json`
- reference workset/review sidecars
- citation workset/review sidecars
- final public artifacts: `digest.md`, `references.json`, `citation_analysis.json`, `citation_analysis.md`, `literature_matching_metadata.json`
- result mirror JSON at `result_json_path`

Do not confuse sidecars with process truth. DB is the source of truth.

## Recovery Principles

- Do not hand-edit SQLite tables.
- 不要手改 SQLite 表、最终 JSON 或 result mirror 来伪造成功。
- Do not hand-edit `workflow_state`, `artifact_registry`, `citation_scope`, or rendered artifacts to fake success.
- Prefer correcting the failed semantic payload and resubmitting the same agent-facing command.
- Workset/review sidecar JSON files may be regenerated; they are not process truth.
- Final public artifacts may be deleted and re-rendered if DB state is complete.

## Recovery Checklist

`init_runtime`

- Missing source file: fix `source_path` and restart run.
- Unsupported source: inspect file encoding/signature.
- PDF conversion warning: continue only if normalized source has enough text quality.
- Missing runtime path: rerun initialization rather than patching DB.

`persist_analysis_plan`

- Scope out of range: re-read normalized source line numbers.
- Missing `metadata`: provide `{}`.
- Matching metadata schema invalid: use `literature_matching_metadata.v1`.
- Citation scope too narrow: include child subsections or adjacent review sections.
- References scope unreliable: revise line range; do not invent bibliography lines.

`persist_digest`

- Missing slot: submit all five fixed digest slots.
- Invalid slot shape: use `digest_slots`, not final Markdown sections.
- Undercoverage: add section summaries for all major non-reference sections.
- Representative image invalid: use evidence-grounded fields or `{"status":"none"}`.

`persist_references`

- `selected_parse_pattern` not allowed: use `allowed_parse_patterns_by_reference_key` from the current prepare output.
- `requires_split_review=true`: resolve `suspect_blocks` first.
- `file_quality_low=true`: choose continue or abandon based on DB-backed quality.
- Author over-split: preserve initials and use conservative author array when needed.
- Placeholder title: recover original title in original language/script or omit unrecoverable hard row.
- Missing obvious metadata: add `metadata_reviews` using `reference_key` and evidence from `metadata_context_text`.

`persist_citation_analysis`

- Empty review-like workset: reassess `citation_scope`.
- Unknown `citation_work_key`: use only keys from `citation_work_packages`.
- Duplicate `citation_work_key`: merge semantic evidence into one final review.
- Timeline summary missing: provide `timeline_summaries.early`, `timeline_summaries.middle`, and `timeline_summaries.recent`; runtime owns bucket membership.
- Summary too thin: explain how the source organizes citations across background, baselines, components, datasets, tools, contrasts, or history.
- Illegal `report_md`: remove it; renderer owns report text.

`finalize_outputs`

- Missing digest state: rerun `persist_digest`.
- Missing references state: rerun `persist_references` or confirm reference-free mode.
- Missing citation state: rerun `persist_citation_analysis`.
- Missing matching metadata: rerun `persist_analysis_plan`.
- Report mismatch: rerun finalization from DB.
- Result mirror mismatch: rerun finalization; do not hand-edit the mirror.

## Common Failure Codes

Representative codes and meanings:

- `normalize_source_failed`: source could not be read or normalized.
- `analysis_plan_invalid`: outline/scope/metadata payload is malformed.
- `persist_digest_failed`: digest slot or section summary payload is invalid.
- `references_merge_failed`: references did not pass split, quality, or merge validation.
- `reference_entry_splitting_failed`: suspect block review did not produce stable entries.
- `citation_mentions_not_found`: citation scope had no stable mentions after filtering.
- `citation_workset_empty`: no usable citation workset was produced.
- `citation_merge_failed`: coverage, duplicate, or mapping validation failed.
- `citation_report_failed`: renderer could not derive a valid `report_md`.
- `render_validation_failed`: final artifact or stdout schema validation failed.

## Final Validation Checklist

Before considering the run successful:

- stdout is exactly one JSON object.
- All public artifact paths are absolute.
- Fixed filenames are used.
- `citation_analysis.md` equals `citation_analysis.json.report_md`.
- `literature_matching_metadata.json.schema` is `literature_matching_metadata.v1`.
- `references.json` is a JSON array with required fields.
- `citation_analysis.json` has `meta`, `summary`, `timeline`, `items`, `unmapped_mentions`, and `report_md`.
- result mirror at `result_json_path` matches stdout.
- warnings are non-fatal and auditable.
- `error` is `null` on success and structured on failure.

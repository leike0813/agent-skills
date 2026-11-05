# Finalization And Recovery

本文件补充 `finalize_outputs`、render validation 和错误恢复。正常路径下，`persist_citation_analysis` 提交成功后级联渲染最终产物；`finalize_outputs` 用于恢复或手动重渲染。

## LLM And Script Responsibilities

Script/runtime owns:

- Reading DB truth、rendering public artifacts、validating schemas、writing result mirror、aggregating warnings 和 returning final stdout JSON。
- 从 persisted classification、profile、rubric 与模板重建公开产物。

LLM/agent owns:

- 根据结构化错误选择恢复路径。
- 修正并重交失败的语义 payload。
- 不加修饰地报告最终 runtime stdout JSON。

不要用临时脚本手写最终 `literature_score.json`、`digest.md`、`references.json`、`citation_analysis.json`、`citation_analysis.md`、`literature_matching_metadata.json` 或 result mirror。脚本只可重跑 `finalize_outputs`、检查文件或比较 renderer 输出。

## Finalization Contract

`finalize_outputs` 只从 DB 读取：

- runtime paths 与 runtime templates
- `literature_classification`（effective classification、profile、resolved rubric、source hash）
- `digest_slots` 与 `digest_section_summaries`
- `literature_score`
- `reference_items`
- `literature_matching_metadata`
- `citation_workset_items`、`citation_items`、`citation_timeline`、`citation_summary`、`citation_unmapped_mentions`、`citation_scope`

It does not accept:

- business payload
- source path / language / output directory override
- hand-authored `report_md`
- hand-authored final JSON

Formal render truth:

- `digest.md` derives from persisted profile headings、`digest_slots` 与 `digest_section_summaries`。
- digest section 标题与顺序来自 effective profile；非 zh/en 语言使用已持久化的 `digest_heading_translations`。
- `references.json` derives from `reference_items`。
- `citation_analysis.json.summary` derives from `citation_summary`。
- `citation_analysis.json.timeline` derives from `citation_timeline`。
- `citation_analysis.json.items` derives from `citation_workset_items + citation_items`。
- `citation_analysis.json.report_md` derives from citation summary/timeline/items/unmapped/scope。
- `citation_analysis.md` must exactly equal `citation_analysis.json.report_md`。
- `literature_matching_metadata.json` derives from DB `literature_matching_metadata`。
- `literature_score.json` derives from DB `literature_score` 与 persisted rubric snapshot，使用 `literature_score.v2`。
- `representative_image` 是可选 stdout metadata，不是公开产物。

Full mode 需要 classification、profile、plan、digest、score、references 与 citation 状态。score-only 只需要 normalized source、classification、profile、runtime assets、score state 与 scoring receipt；digest、references、citation、outline 与 scope 均不要求。

## Published Artifacts

Required fixed filenames:

- `digest.md`
- `references.json`
- `citation_analysis.json`
- `literature_matching_metadata.json`
- `literature_score.json`

Optional/additive:

- `citation_analysis.md`
- `representative_image` field in stdout

All paths in stdout must be absolute。

Success stdout must include:

- `digest_path`
- `references_path`
- `citation_analysis_path`
- `literature_matching_metadata_path`
- `literature_score_path`
- `provenance.generated_at`
- `provenance.input_hash`
- `provenance.model`
- `warnings`
- `error`

Optional stdout keys:

- `citation_analysis_report_path`
- `representative_image`

Failure stdout remains schema-compatible: unavailable path fields are empty strings, and `error` carries `code` and `message`。score-only 成功时除 `literature_score_path` 外全部公开产物路径为空字符串，`citation_analysis_report_path` 不出现。

## Result Mirror And Artifact Registry

Runtime writes a result mirror JSON to `result_json_path`。Content should match stdout JSON；divergence 时重跑 `finalize_outputs`，不要手改 mirror。

Artifact registry records at least:

- `digest_path` from `digest_slots`
- `references_path` from `reference_items`
- `citation_analysis_path` from `citation_summary`
- `literature_matching_metadata_path` from `literature_matching_metadata`
- `literature_score_path` from `literature_score`

If renderer generated non-empty `report_md`, also record `citation_analysis_report_path`。

Warning aggregation may include:

- `classification_low_confidence`
- `scope_fallback_used`
- `reference_numbering_anomaly_detected`
- `reference_parse_low_confidence`
- `citation_false_positive_filtered`
- `no_mentions_found_in_review_scope`
- `digest_undercoverage`
- dimension 级 N/A 权重重分配 warning

## Safe-To-Regenerate Files

DB state 完整时，可删除并重新生成：

- source sidecars such as `source.md` / `source_meta.json`
- reference workset/review sidecars
- citation workset/review sidecars
- final public artifacts: `literature_score.json`、`digest.md`、`references.json`、`citation_analysis.json`、`citation_analysis.md`、`literature_matching_metadata.json`
- result mirror JSON at `result_json_path`

Do not confuse sidecars with process truth。DB is the source of truth。

## Recovery Principles

- 不要手改 SQLite 表、最终 JSON 或 result mirror 来伪造成功。
- Do not hand-edit `workflow_state`、`artifact_registry`、`literature_classification` 或 rendered artifacts。
- 不要手工修补 classification snapshot、rubric snapshot 或 locked review form。
- Prefer correcting the failed semantic payload and resubmitting the same agent-facing command。
- Workset/review sidecar JSON files may be regenerated；they are not process truth。
- 恢复时先运行 `status --db-path "<db_path>"`，按 `next_action` 继续。

## Recovery Checklist

`init_runtime`

- Missing source file：fix `source_path` and restart run。
- Unsupported source：inspect file encoding/signature。
- PDF conversion warning：continue only if normalized source has enough text quality。
- Missing runtime path：rerun initialization rather than patching DB。
- 重新初始化会让旧 classification 与下游结果失效；重新分类后再继续。

`persist_literature_classification`

- `classification_required`：classification 缺失、source 已重新归一化或 snapshot 与当前 source 不一致；重新提交 classification。
- `classification_invalid`：补齐 `disciplines`、`profile_id`、`confidence`、`reason`，并使用合法 enum。
- 低置信：确认 effective profile 为 `general`，保留 reason 与 warning；不要改写质量分。
- 重复提交同一分类是幂等操作；只有分类或 profile 定义变化才失效下游结果。

`persist_analysis_plan`

- Scope out of range：re-read normalized source line numbers。
- Missing `metadata`：provide `{}`。
- Matching metadata schema invalid：use `literature_matching_metadata.v1`。
- Citation scope too narrow：include child subsections or adjacent review sections。
- References scope unreliable：revise line range；do not invent bibliography lines。

`persist_digest`

- Missing slot：submit all five slots（`tldr.paragraphs` 与 `focus/basis/analysis/limits.items`）。
- Invalid slot shape：use `digest_slots`，not final Markdown sections。
- Missing heading translations：non zh/en language needs all six heading keys。
- Undercoverage：add section summaries for all major non-reference sections。
- Representative image invalid：use evidence-grounded fields or `{"status":"none"}`。

`persist_literature_score`

- `stale_form`：rerun prepare and continue from the new `scoring_review_draft_path`。
- `locked_field_changed`：restore runtime-owned values from `scoring_review_form_path`，including locked classification 与 rubric。
- `incomplete_answer`：fill the reported semantic field and satisfy applicability、score、reason、summary 或 confidence constraints。
- `evidence_not_found`：use the reported candidate range to copy a clearer normalized-source quote。
- Incorrect applicability：set `applicable=false` only when the criterion has no evaluation object；missing reporting remains applicable and receives a source-grounded score。
- 分类或 rubric 变化后旧 form 必然 stale，必须重新 prepare。

`persist_references`

- `selected_parse_pattern` not allowed：use `allowed_parse_patterns_by_reference_key` from the current prepare output。
- `requires_split_review=true`：resolve `suspect_blocks` first。
- `file_quality_low=true`：choose continue or abandon based on DB-backed quality。
- Author over-split：preserve initials and use conservative author array when needed。
- Placeholder title：recover original title in original language/script or omit unrecoverable hard row。
- Missing obvious metadata：add metadata reviews using `reference_key` and evidence from the metadata batch context。

`persist_citation_analysis`

- Empty review-like workset：reassess `citation_scope`。
- Unknown `citation_work_key`：use only keys from `citation_work_packages`。
- Duplicate `citation_work_key`：merge semantic evidence into one final review。
- Timeline summary missing：provide `timeline_summaries.early`、`middle` 和 `recent`；runtime owns bucket membership。
- Summary too thin：explain how the source organizes citations across background、baselines、components、datasets、tools、contrasts 或 history。
- Illegal `report_md`：remove it；renderer owns report text。

`finalize_outputs`

- Missing classification：rerun `persist_literature_classification`。
- Missing digest state：rerun `persist_digest`。
- Missing literature score state：rerun `persist_literature_score`。
- Missing references state：rerun `persist_references` or confirm reference-free mode。
- Missing citation state：rerun `persist_citation_analysis`。
- Missing matching metadata：rerun `persist_analysis_plan`。
- Report mismatch：rerun finalization from DB。
- Result mirror mismatch：rerun finalization；do not hand-edit the mirror。

## Common Failure Codes

Representative codes and meanings:

- `normalize_source_failed`：source could not be read or normalized。
- `classification_required`：classification is missing or no longer matches the current source。
- `classification_invalid`：classification structure、profile id 或 confidence 不合法。
- `analysis_plan_invalid`：outline/scope/metadata payload is malformed。
- `digest_stage_failed`：digest slot、section summary 或 heading translation payload is invalid。
- `score_review_invalid`：the scoring review form is stale、structurally changed、incomplete 或 contains an unlocatable evidence quote。
- `score_payload_invalid`：no applicable criterion exists for the selected rubric。
- `score_render_failed`：the DB-backed score artifact could not be rendered or validated。
- `references_merge_failed`：references did not pass split、quality 或 merge validation。
- `reference_entry_splitting_failed`：suspect block review did not produce stable entries。
- `citation_mentions_not_found`：citation scope had no stable mentions after filtering。
- `citation_workset_empty`：no usable citation workset was produced。
- `citation_merge_failed`：coverage、duplicate 或 mapping validation failed。
- `citation_report_failed`：renderer could not derive a valid `report_md`。
- `render_validation_failed`：final artifact or stdout schema validation failed。

## Final Validation Checklist

Before considering the run successful:

- stdout is exactly one JSON object。
- All public artifact paths are absolute。
- Fixed filenames are used。
- `citation_analysis.md` equals `citation_analysis.json.report_md`。
- `literature_matching_metadata.json.schema` is `literature_matching_metadata.v1`。
- `literature_score.json.schema` is `literature_score.v2`，含 `literature_classification`、`rubric_id`、三个 aggregate 值，以及与 selected rubric 一致的动态 dimensions。
- `references.json` is a JSON array with required fields。
- `citation_analysis.json` has `meta`、`summary`、`timeline`、`items`、`unmapped_mentions` 和 `report_md`。
- result mirror at `result_json_path` matches stdout。
- warnings are non-fatal and auditable。
- `error` is empty on success and structured on failure。

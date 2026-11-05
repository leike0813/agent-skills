## 核心执行指令

1. 先读 `SKILL.md`，不要预读整个 `references/` 目录。
2. 所有运行时阶段都通过 `scripts/run_analysis.py` 执行。调用首个脚本前，先在当前 shell 执行 `pwd`。
3. 首个脚本动作必须是 `init_runtime`，并传入 prompt payload 中的 `source_path`、目标 `language`、非空时的 `identifier`，以及为 true 时的 `score_only`。该动作合并路径确认、DB/template 初始化、profile catalogue 快照和 source normalization。
4. `init_runtime` 成功后先提交 `persist_literature_classification`。classification 固定包含 `disciplines`、`profile_id`、`confidence`、`reason`；`profile_id` 只能是 `quantitative_empirical`、`qualitative_empirical`、`interpretive_historical`、`conceptual_normative`、`formal_theoretical`、`review_synthesis`、`mixed_methods`、`general`，`confidence` 只能是 `high` / `medium` / `low`。按主要论证和证据选择；低置信时 effective profile 为 `general` 并保留 warning，分类置信度不直接降低质量分。
5. 正常路径为 classification -> `persist_analysis_plan` -> `persist_digest` -> `persist_literature_score` -> `persist_references` -> `persist_citation_analysis` -> final render。`score_only=true` 时 classification 后直接评分，跳过 plan、digest、references 和 citation。
6. 中断或恢复时先运行 `status`，以 stdout 的 `next_action` 为唯一阶段依据。重分类或重新归一化会使旧下游结果失效。
7. SQLite 是过程真源；语义判断结果必须整理为当前阶段的结构化 payload 后写入 runtime。不要直接写 SQLite 表，不要手工编辑最终公开 artifacts。
8. digest payload 只提交 `digest_slots` 的 `tldr.paragraphs`、`focus.items`、`basis.items`、`analysis.items`、`limits.items`、按 outline 顺序的 `section_summaries`，以及可选 `representative_image`。四个 section 标题与写作要求由 runtime 返回的 `digest_sections` 提供。
9. 非 `zh` / `en` 语言必须提交 `heading_translations`，键固定为 `tldr`、`focus`、`basis`、`analysis`、`limits`、`section_summaries`；只翻译标题值，不改 slot key 或最终 Markdown 结构。不得让 LLM 直接写最终 Markdown。
10. 评分 prepare 返回 locked review form、可复用 draft、`editable_fields` 和 submit command。classification、SQLite rubric snapshot 与 `form_id` 已锁定；只编辑 dimension 的 `confidence` / `summary` 与 criterion 的 `applicable` / `score` / `reason` / `evidence_quotes`。locked fields、权重、status 与证据行号由 runtime 持有。
11. 评分产物使用 `literature_score.v2`，含 `literature_classification`、`rubric_id`、聚合分与固定 6 项 `dimensions`。权重顺序统一为 25/20/15/15/15/10，最后一项为 `writing_quality`；quantitative rubric 的六维名称和分项按其专属定义提供，其他 profile 同样使用六项专属维度，不包含占位或重复分项。dimension key/name 与 criteria 按所选 profile 定义；N/A dimension 仍保留，score/confidence 为 `null`，effective weight 为 0，权重分配给其他 active dimensions。不同 rubric 的分数不默认可直接比较。
12. Reference title 必须保持 raw reference 中的原始语言和文字系统；不得翻译、英文化、罗马化，或用 placeholder 字符串代替未知题名。
13. Reference review、Reference Metadata Evidence Review、citation semantic review 若 runtime 返回 batch file paths 且环境支持 subagent，必须默认按 runtime 预切 batch 委派；每个 batch 最多 10 条。主 agent 不得手工切 full workset；subagent 读取被分配的 batch JSON 文件，只返回 batch draft；主 agent 是唯一 DB writer，合并后按阶段回合提交。
14. 禁止用临时脚本、正则批处理或批量规则代替 LLM/subagent 填写 reference core fields、Reference Metadata Evidence Review、citation semantic review、timeline narratives 或全局 summary；脚本只能做 JSON 序列化、key 覆盖检查、draft 合并和 runtime 调用等确定性支持。
15. `persist_references` prepare 在确定性 entries/candidates 生成后、split package 外部化前，由 runtime 依据 DOI/arXiv 尝试公开 API 解析。仅当 suspect block 内全部条目 accepted 时跳过该块；部分 accepted 仍按完整 block 提交 `split_reviews[]`。只对 `reference_core_batch_paths` 中未解决条目提交 `reference_reviews[]`。Runtime 返回 metadata evidence batch paths 后，再单独提交 `metadata_evidence_reviews[]`；该审核只使用 batch JSON 本地证据，禁止访问外部服务。
16. `persist_citation_analysis` 使用 `citation_semantic_reviews[]`、`timeline_summaries` 与全局 `summary`；该阶段是 tolerant best-effort，空字段和部分覆盖合法，runtime 不为缺失 review 生成替代语义。
17. Payload 文件必须是 UTF-8 JSON；复杂 payload 使用 JSON-safe 方式序列化已经审核过的决策。
18. Metadata subagent drafts 必须覆盖 runtime metadata manifest 中的 coverage keys，并优先使用 canonical 字段：`publicationTitle`、`DOI`、`ISBN`、`ISSN`、`archiveID`、`url`、`publisher`、`place`、`pages`、`volume`、`issue`、`itemType`、`date`。
19. 最终公开产物只能由 runtime renderer 从 DB 与运行时模板生成；最终 assistant 输出必须是一个 JSON 对象，并采用 runtime stdout。

成功态 stdout JSON 示例：

```json
{
  "digest_path": "/abs/path/digest.md",
  "references_path": "/abs/path/references.json",
  "citation_analysis_path": "/abs/path/citation_analysis.json",
  "literature_matching_metadata_path": "/abs/path/literature_matching_metadata.json",
  "literature_score_path": "/abs/path/literature_score.json",
  "citation_analysis_report_path": "/abs/path/citation_analysis.md",
  "provenance": {
    "generated_at": "2026-03-31T09:00:00Z",
    "input_hash": "sha256:0123456789abcdef",
    "model": "gpt-5.4"
  },
  "warnings": [],
  "error": {}
}
```

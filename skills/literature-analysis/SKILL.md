---
name: literature-analysis
description: Generate a source-grounded paper score, digest, structured references, citation analysis, matching metadata, and citation report from a source literature file. Use when you need full literature analysis and assessment with digest, references, citation semantics.
compatibility: Requires local filesystem read access to source_path; public network access is optional and reference extraction continues locally when unavailable.
---

# literature-analysis

本 skill 以 SQLite runtime 为过程真源，先识别研究范式，再生成 digest、评分、references、citation analysis、matching metadata 和 citation report。

## 目标

从一个本地文献来源生成可审计、可恢复且适合机器消费的完整论文分析。agent 负责分类与语义判断；runtime 负责输入标准化、状态迁移、profile/rubric 快照、API reference resolution、校验和公开产物渲染。

## 非目标

- 不搜索或替换来源论文；`source_path` 始终是论文内容真源，`identifier` 只用于精确获取来源论文的公开 bibliography。
- 不以 provider 返回的数量、顺序或条目替换本地 reference 边界；API 记录只解析本地已准备的 entries。
- 不在 Reference Metadata Evidence Review 中访问网络或外部数据库；该回合只审核 runtime batch 中的本地证据。
- 不由 agent 手工拼装公开 artifacts、最终 stdout JSON 或 SQLite 状态。

## 后台自动化约束

本 skill 运行于后台自动化场景：运行过程中不得询问用户做决策。任何分支或不确定性都应采用本文件定义的默认行为、脚本校验和已持久化状态继续推进。

stdout 只能输出一个 JSON 对象，不得夹杂解释文本、日志或多段输出。读取输入失败、归一化失败、校验失败或渲染失败时，也必须返回 schema-compatible JSON，并在 `error` 中写入结构化失败信息。

## 核心执行指令

1. 先读本 `SKILL.md`，不要一开始读取整个 `references/` 目录。
2. 只从 prompt payload 读取 `source_path`、`language`、可选 `score_only` 与可选 `identifier`。`score_only` 未提供时为 `false`；`identifier` 只用于精确查询公开引文 API。
3. 调用任何脚本前，先在当前 shell 执行 `pwd` 取得工作目录。所有动作都通过 `scripts/run_analysis.py` 执行。
4. SQLite 是过程真源。语义结果必须通过阶段 payload 写入 runtime DB，不能手写 SQLite 表伪造完成。
5. `init_runtime` 合并路径确认、DB/template 初始化、profile catalogue 快照和 source normalization，是唯一没有 agent 语义 payload 的阶段。
6. 正常路径固定为：classification -> `persist_analysis_plan` -> `persist_digest` -> `persist_literature_score` -> references -> citation -> finalize。`score_only=true` 时，classification 成功后直接评分。
7. 每次中断、恢复或不确定下一步时先运行 `status`；以 stdout 的 `next_action` 为唯一阶段依据。
8. Reference title 必须保持 raw reference 中的原始语言和文字系统；不得翻译、英文化、罗马化，或用 `none` / `null` / `unknown` / `untitled` / `N.A.` 等 placeholder 代替未知题名。
9. 当环境支持 subagent 且 runtime 返回可分批的 batch file paths 时，reference review、metadata review、citation semantic review 默认按 runtime 预切 batch 委派；只有主 agent 可以合并并提交正式 payload。
10. 最终公开产物只能由 runtime 从 DB 和运行时模板渲染生成。agent 不直接写 `literature_score.json`、`digest.md`、`references.json`、`citation_analysis.json`、`citation_analysis.md` 或 `literature_matching_metadata.json`。
11. 最终 assistant 输出直接采用 runtime 返回的 stdout JSON。

Runtime path is owned by `literature-analysis/scripts/analysis_runtime` and `literature-analysis/assets`.

## Subagent Delegation Contract

Reference core review、Reference Metadata Evidence Review、citation semantic review 是本 skill 的默认可委派工作。只要当前环境支持 subagent、runtime/JIT 返回 batch file paths，且 batch 不是小到无需拆分或上下文不可拆，主 agent 就必须按 runtime 预切 batch 委派。跳过委派时，在执行 notes、`review_notes` 或 payload 合并说明中保留原因。

主 agent 职责：

- 读取 runtime/JIT 返回的 manifest path、batch file paths、field guidance、batch prompts 和 merge contract。
- 按 runtime 预切的 batch JSON 文件路径委派 subagent，收集 batch draft。
- 合并 drafts，保持 stable keys 不变，去重，校验覆盖集合，再提交一次正式 payload。
- 作为唯一 DB writer 执行 `scripts/run_analysis.py`；subagent 不写 DB、不提交 payload、不生成 final artifacts。
- 不从全量 workset 或 review sidecar 手工切 batch；runtime batch files 是唯一委派输入边界。

Subagent 职责：

- 只处理分配给自己的 batch，只返回 batch draft JSON。
- 不写 DB，不运行 runtime command，不提交 payload，不生成 final artifacts。
- 不改 `reference_key` / `citation_work_key` 等 stable keys。
- 不填 `raw`、`confidence`、`ref_index`、mentions、timeline bucket、`report_md` 等内部审计或 renderer 字段。
- 不修改 locked fields；Reference Metadata Evidence Review 只能基于 batch JSON 中的本地证据返回 canonical metadata 字段和 evidence note。

Citation timeline bucket membership、全局 `summary`、最终 report 和 artifact 渲染由 runtime 或主 agent 负责。

Runtime batch files are written under `.literature_analysis_tmp/agent_work/`. Each batch contains at most 10 items, the package subset, allowed enum subset, prompt, return shape, forbidden fields, merge notes, and `suggested_draft_output_path`.

Mandatory delegation points:

- Reference Core Review：`persist_references` prepare 返回 `reference_core_review_manifest_path` 与 `reference_core_batch_paths` 后，把每个 batch JSON 文件路径交给 subagent。
- Reference Metadata Evidence Review：core `reference_reviews[]` 提交成功并返回 `metadata_evidence_review_manifest_path` 与 `metadata_evidence_batch_paths` 后，把每个 metadata evidence batch JSON 文件路径交给 subagent。
- Citation Semantic Review：`persist_citation_analysis` prepare 返回 `citation_semantic_review_manifest_path` 与 `citation_batch_paths` 后，把每个 citation batch JSON 文件路径交给 subagent。

Allowed reasons to skip a delegation point are limited to: no subagent capability in the environment, a trivially small batch where delegation adds no value, or a batch that cannot be split without losing necessary context. Do not skip because a temporary script seems faster.

## 输入输出硬契约

输入只读取 prompt payload：

- `source_path`：唯一内容来源。
- `language`：输出语言。显式给出时直接使用；否则先从 prompt 主要语言推断，仍无法稳定判断时回退 `zh-CN`。
- `score_only`：可选 boolean，默认 `false`。
- `identifier`：可选 DOI/arXiv；格式非法时 runtime 写 warning，并使用 plan 中有原文证据的 `source_identity`。

`source_path` 支持 Markdown、纯文本、PDF、单文件 `.tex`、LaTeX 工程目录和无扩展名 UTF-8 文本文件。格式按内容优先探测，后续阶段只消费 DB 中的 normalized source。

`score_only=true` 时只执行 initialization/normalization、classification 和 scoring，不要求 analysis plan、digest、references 或 citation analysis。

成功态 stdout JSON 必须包含：

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

成功态 stdout JSON 可包含 `citation_analysis_report_path` 和 `representative_image`。固定公开产物为 `digest.md`、`references.json`、`citation_analysis.json`、`citation_analysis.md`、`literature_matching_metadata.json`、`literature_score.json`，不生成额外分类文件。

输出规则：

- 公开产物路径必须是绝对路径。
- `references.json` 是 canonical `source_reference_artifact.v1`：顶层仅 `{schema, references}`；每条 reference 含 `sourceReferenceId`、`extraction`（`null` 或 `{raw, confidence}`）、`bibliography`（必填 `title`、`authors`、`year`，rich 字段按 schema 白名单）与 `matching`（仅含确有证据的 `DOI`、`url`、`ISBN`、`ISSN`、`citekey`）。同一 artifact 内 `sourceReferenceId` 唯一；它是 runtime 持久化的 opaque identity，内部 `ref_index` 与 workset 字段不公开。
- `citation_analysis.json` 是 canonical `citation_analysis_artifact.v1`：顶层仅 `{schema, meta, summary, timeline, items, unresolved}`；`items[].sourceReferenceId` 与 `timeline.*.sourceReferenceIds` 必须属于 References ID 集合；`items[].mentions` 与 `unresolved` 不重复 `mention_id`，其并集等于 SQLite 中已过滤误报后的 mention 集合。未映射 mention 与缺 semantic review 的已映射 mention 都进入 `unresolved`，后者 `reason` 为 `semantic_review_missing`。
- `citation_analysis.md` 是从 Citation DB 内容独立派生的报告，不嵌入 `citation_analysis.json`。
- 最终 stdout 同步镜像写入 runtime DB 固化的 result JSON path。
- full mode 成功时公开产物路径均非空；score-only 成功时只有 `literature_score_path` 非空，其他公开产物路径为空字符串，`citation_analysis_report_path` 不出现。
- 失败时仍返回 schema-compatible JSON；不可用路径为空字符串，`error` 含结构化 `code` 与 `message`。

## SQLite SSOT

`init_runtime` 固化 `working_dir`、`tmp_dir`、`db_path`、`result_json_path`、`output_dir`、输入、source hash、normalized source、渲染模板和 package 内 `literature_profiles.json` 快照路径。

`literature_classification` 是单行状态，保存 classification、有效 profile、resolved rubric 与 source-hash 快照。digest 与 scoring 都读取这份 SQLite snapshot；`scoring_rubric_path` 是 runtime 写出的审计镜像。

- 同一 classification 与同一 profile 定义重复提交是幂等操作，不删除已完成的下游状态。
- 重分类会失效旧 plan、digest、score、references、citation、artifact registry 和下游 receipts，并按 `score_only` 回到 plan 或 scoring。
- 重新初始化/re-normalize 会使旧 classification 和全部依赖结果失效。
- 后续阶段只读取 DB 已固化的 runtime inputs、normalized source、classification/profile/rubric、outline、scope、reference/citation workset 和模板路径。
- payload 文件必须是 UTF-8 JSON，并通过 `--payload-file` 传入。JSON 语法无效时 runtime 返回 `payload_json_invalid`，不猜测修复。
- `persist_digest` 不重传 `source_path`；`persist_references` 不重传 `references_scope`；`persist_citation_analysis` 不重传 `citation_scope`；`finalize_outputs` 不接受业务 payload 或路径覆盖。

## Runtime 调用方式

- 从 skill 目录执行：`python scripts/run_analysis.py ...`
- 从 repo 根目录执行：`python literature-analysis/scripts/run_analysis.py ...`
- 首个脚本调用前先执行 `pwd`，让默认 `working_dir` 反映调用时的真实目录。
- `run_analysis.py` 基于自身路径自举 `analysis_runtime` 导入。

## LLM 与脚本职责边界

LLM/agent 负责：

- 按主要论证和证据结构完成 `literature_classification`。
- 大纲、`references_scope` / `citation_scope` 和 `literature_matching_metadata` 决策。
- digest 五个中性槽位、`section_summaries`、非 zh/en 标题翻译和 representative image 文本判断。
- 在 runtime review draft 中填写 dimension 与 criterion 的语义答案、applicability、evidence quotes、confidence 和理由。
- reference candidate、core fields、split review、Reference Metadata Evidence Review 和 citation semantic review。
- citation `timeline_summaries` 与全局 `summary`。

Script/runtime 负责：

- 输入探测、source normalization、UTF-8/PDF/LaTeX 处理、input hash 和 SQLite 状态迁移。
- profile catalogue 加载、classification 结构校验、有效 profile 选择和 rubric resolution。
- reference deterministic preprocess、API resolution、candidate/workset 生成和质量校验。
- citation mention extraction、mapping 和 workset 生成。
- digest、classification、scope、review form 和 citation payload 校验。
- 生成锁定 scoring form、校验 form identity、定位 evidence quotes、派生证据行号与 criterion status。
- rubric snapshot、N/A 归一化、权重重分配、dimension/overall/confidence/adjusted score 计算。
- 从 DB 读取 profile headings 与内容，渲染最终产物，校验 stdout。

绝对禁止：

- 用临时脚本或批量规则代替 LLM/subagent 完成分类、摘要、大纲、scope、representative image、reference refinement、metadata evidence review、split review 或 citation semantics。
- 用脚本自动填充 `reference_reviews[]`、`metadata_evidence_reviews[]` 或 `citation_semantic_reviews[]` 的语义字段。
- 绕过 `run_analysis.py` 手工写 DB，或手工编辑最终公开 JSON 后冒充 renderer 输出。

## 文献分类

classification 必须在 normalized source 上完成，先看主要主张依赖的证据与论证方式，再用学科标签描述领域。学科不能替代研究范式判断。

payload 固定为：

```json
{
  "literature_classification": {
    "disciplines": ["社会学", "公共政策"],
    "profile_id": "mixed_methods",
    "confidence": "high",
    "reason": "核心主张同时依赖调查数据的量化比较与访谈材料的质性解释，并在同一论证中整合两类证据。"
  }
}
```

字段约束：

- `disciplines`：短标签字符串数组，可以为空；不得用空字符串占位。
- `profile_id`：只能取表中八个值。
- `confidence`：只能是 `high`、`medium`、`low`。
- `reason`：非空字符串，说明证据和论证结构。

| `profile_id` | 选择依据 |
| --- | --- |
| `quantitative_empirical` | 实验、观测、测量、统计推断或定量模型检验构成主要经验证据。 |
| `qualitative_empirical` | 访谈、观察、田野、案例或文本资料通过系统的质性分析形成解释。 |
| `interpretive_historical` | 以史料、档案、文本及历史语境进行阐释，重点在意义与形成过程。 |
| `conceptual_normative` | 概念辨析、规范判断或价值论证构成核心，需说明权利、义务、正当性或应然安排。 |
| `formal_theoretical` | 形式模型、定义、定理、证明或推导构成主要论证。 |
| `review_synthesis` | 以系统或叙述性综述、比较和综合既有研究为主。 |
| `mixed_methods` | 定量与质性证据在同一个核心论证中实质整合；并列汇报两类材料不因此成为该类。 |
| `general` | 没有专门 profile 明显占主导，或证据不足以稳定选择专门类型。 |

`confidence=low` 时 effective profile 固定为 `general`，runtime 添加 `classification_low_confidence` warning。低置信分类只选择通用 digest 与 rubric，不直接降低论文质量分。classification confidence 与 scoring confidence 相互独立。

提交命令：

```bash
python scripts/run_analysis.py persist_literature_classification \
  --db-path "<db_path>" \
  --payload-file classification.json
```

成功返回 effective `literature_classification`、四个 `digest_sections`、`rubric_id` 和 `next_action`。normal mode 进入 `persist_analysis_plan`，score-only 进入 `persist_literature_score`。未知 profile、缺字段或无效 enum 返回 `classification_invalid`，不得继续。

## 参数词表

- `source_path`：唯一内容来源路径，文件或 LaTeX 工程目录。
- `language`：输出语言，控制 digest、citation report 和非 zh/en 标题翻译要求。
- `score_only`：source normalization 与 classification 后直接评分。
- `identifier`：可选 DOI/arXiv，只触发精确公开 API 查询。
- `literature_classification`：`disciplines`、`profile_id`、`confidence`、`reason`。
- `working_dir` / `tmp_dir` / `db_path` / `result_json_path` / `output_dir`：由 `init_runtime` 固化。
- `normalized_source`：脚本标准化后写入 DB 的唯一分析文本。
- `outline_nodes`：含 `node_id`、`heading_level`、`title`、`line_start`、`line_end`、`parent_node_id`、`metadata` 的章节骨架。
- `references_scope` / `citation_scope`：含 `section_title`、`line_start`、`line_end`、`metadata` 的章节范围。
- `literature_matching_metadata`：固定 `literature_matching_metadata.v1`，含 `key_terms`、`methods`、`problems`、`datasets`、`exclude_terms`。
- `digest_slots`：`tldr.paragraphs` 与 `focus/basis/analysis/limits.items`；不是最终 Markdown。
- `section_summaries`：按大纲顺序组织的章节摘要。
- `digest_sections`：runtime 按有效 profile 返回的四个 section 标题与写作提示。
- `heading_translations`：非 zh/en 语言的六个标题翻译，键固定为 `tldr`、`focus`、`basis`、`analysis`、`limits`、`section_summaries`。
- `representative_image`：只能基于 figure label、caption、图片引用、章节和页码文本线索判断。
- `literature_score`：当前 `literature_score.v2` 评分产物，含 classification、rubric 与 selected profile 定义下的固定 6 个 dimensions。
- `reference_key` / `citation_work_key`：runtime batch 中的稳定工作键。
- `selected_parse_pattern`：必须来自对应 reference batch 的 allowed values。
- `metadata_evidence_reviews`：只从 batch 本地证据提取 canonical metadata。
- `citation_semantic_reviews`：`topic`、`usage`、`role_in_context`、`keywords`、条目 `summary`、可选 `key_reference_reason`。
- `timeline_summaries`：`early` / `middle` / `recent` 三段叙述；bucket membership 由 runtime 派生。

## 参考索引

启动时只读本文件。进入对应阶段或遇到对应错误时再读取：

- [source_and_plan.md](references/source_and_plan.md)：`init_runtime`、classification、`persist_analysis_plan`、source normalization、scope 决策。
- [digest_generation.md](references/digest_generation.md)：`persist_digest`、中性槽位、profile headings、section summary、representative image。
- [paper_scoring.md](references/paper_scoring.md)：`persist_literature_score` review form、profile rubric、applicability、evidence、confidence。
- [reference_extraction.md](references/reference_extraction.md)：`persist_references`、split review、quality gate、Reference Metadata Evidence Review、bibliography formats。
- [citation_analysis.md](references/citation_analysis.md)：`persist_citation_analysis`、mention mapping、semantics、timeline、summary。
- [finalization_and_recovery.md](references/finalization_and_recovery.md)：`finalize_outputs`、render validation、classification/profile 失效和错误恢复。

## 最小执行主路径

### 1. `init_runtime`

新 run 的第一步，必须在任何语义 payload 前执行。

```bash
pwd
python scripts/run_analysis.py init_runtime \
  --source-path "/abs/path/paper.md" \
  --language "zh-CN" \
  [--working-dir "/abs/path/run-root"] \
  [--output-dir "/abs/path/artifacts"] \
  [--db-path "/abs/path/.literature_analysis_tmp/literature_analysis.db"] \
  [--model "gpt-5.4"] \
  [--identifier "10.1109/CVPR.2016.90"] \
  [--score-only]
```

该动作确认并固化 paths、初始化 SQLite、持久化 templates 与 `literature_profiles.json` 快照、写入 provenance、normalize source。成功返回 `db_path`、`source_profile` 和 `next_action=persist_literature_classification`。文件不可读、编码失败或 source 无法标准化时，不提交语义 payload。

### 2. `persist_literature_classification`

读取 normal source 与 `status` 返回的 `profile_choices`，按上方固定 payload 分类。

成功返回 effective classification、`digest_sections`、`rubric_id` 和下一动作。相同 classification 与 profile 定义重复提交保持现有下游状态；改变分类会失效依赖结果。

### 3. `persist_analysis_plan`

仅 normal mode。classification 成功后，在 normalized source 上完成结构化 plan：

```bash
python scripts/run_analysis.py persist_analysis_plan \
  --db-path "<db_path>" \
  --payload-file plan.json
```

必须 payload：

- `outline_nodes`：按原文顺序的对象数组。每项必须含 stable `node_id`、整数 `heading_level`、原文 `title`、1-based inclusive `line_start` / `line_end`、可为 `null` 的 `parent_node_id` 与显式 `metadata` 对象。
- `references_scope`：对象，含非空 `section_title`、normalized source 内的 1-based `line_start` / `line_end` 与显式 `metadata`。
- `citation_scope`：对象，字段同上，覆盖综述/背景论证，可跨多个章节；`metadata.selection_reason` 说明选择依据。
- `source_identity`：显式 `null`，或对象 `{identifier, evidence_quote, line_start, line_end}`。非空 identifier 必须是有效 DOI/arXiv；证据行必须在 normalized source 内、位于 `references_scope` 外，且 `evidence_quote` 出现在该行范围并包含该 identifier。
- `literature_matching_metadata`：固定 `literature_matching_metadata.v1` schema，含 `key_terms`、`methods`、`problems`、`datasets`、`exclude_terms`，不得省略。

成功返回 stored scope、matching metadata 和 `next_action=persist_digest`。结构、行号、schema 错误修正后重交。

### 4. `persist_digest`

classification 后的 normal mode，读取 DB 中 normalized source、outline、selected profile 与 runtime 返回的 `digest_sections[*].prompt`。

```bash
python scripts/run_analysis.py persist_digest \
  --db-path "<db_path>" \
  --payload-file digest.json
```

最小 payload：

```json
{
  "digest_slots": {
    "tldr": {"paragraphs": ["全文问题、依据、结论与边界的综合摘要。"]},
    "focus": {"items": ["研究问题、核心主张或贡献。"]},
    "basis": {"items": ["材料、方法、数据、文本或来源基础。"]},
    "analysis": {"items": ["主要分析路径、证据、结果或形式推导。"]},
    "limits": {"items": ["适用范围、不确定性、反例或复现条件。"]}
  },
  "section_summaries": [
    {"source_heading": "Introduction", "items": ["本节的问题与主张。"]}
  ]
}
```

- 五个 slot 必须齐全且非空；slot key 与顺序固定，标题和语义由 selected profile 决定。
- `section_summaries` 按 outline 顺序覆盖主要非 reference 章节；长章节按实际论题拆分。
- `representative_image` 可选；`status` 只能是 `selected` 或 `none`。人文或理论文献没有实验、代码或数据集是材料特征，不构成 digest 缺陷。
- `status=selected` 时必须含 `source_kind`（`markdown_image_ref` 或 `pdf_figure_caption`）、`label`、`caption_quote`、`selection_reason` 与 `confidence`（`high` / `medium` / `low`）。`markdown_image_ref` 另需非空 `markdown_src_hint`；`pdf_figure_caption` 不使用该字段。`section_hint` 与正整数的 `page_hint` 可选。
- `language` 以 `zh` 或 `en` 开头时，标题由 profile 与 runtime 选择。其他语言必须提交 `heading_translations` 的六个非空值，键不变。
- 不提交最终 Markdown；renderer 使用 DB 内容和持久化 profile headings 渲染。
- 成功返回 `next_action=persist_literature_score`。

### 5. `persist_literature_score`

normal mode 在 digest 后评分；score-only 在 classification 后直接评分。

Prepare：

```bash
python scripts/run_analysis.py persist_literature_score --db-path "<db_path>"
```

读取 `scoring_review_form_path`、`scoring_review_draft_path`、`editable_fields` 和 `submit_command`。本次 profile、classification、rubric 与 source snapshot 已锁定；`form_id` 由 source、classification 和 resolved rubric 派生。

只编辑：

- `dimension_reviews[*].confidence`、`summary`
- `criterion_reviews[*].applicable`、`score`、`reason`、`evidence_quotes`

classification、rubric key/name/prompt/weight/max/order 沿用 prepare 的 locked values；聚合分数、status、effective weight 与证据行号由 runtime 派生。

Submit：

```bash
python scripts/run_analysis.py persist_literature_score \
  --db-path "<db_path>" \
  --payload-file "<scoring_review_draft_path>"
```

公开产物使用 `literature_score.v2`，包含 `literature_classification`、`rubric_id`、`overall_score`、`confidence`、`confidence_adjusted_score` 与固定 6 项 `dimensions`。权重顺序统一为 25/20/15/15/15/10，最后一项为 `writing_quality`。quantitative rubric 的六维名称和分项按其专属定义提供；其他 profile 同样使用六项专属维度，不包含占位或重复分项。每个位置的 dimension key/name 与 criteria 按所选 profile 定义，不能仅凭数组位置跨 profile 对齐。N/A dimension 仍保留，score 与 confidence 为 `null`，effective weight 为 0，configured weight 按比例分配给其他 active dimensions。不同 rubric 的分数不默认可直接比较。

### 6. `persist_references`

评分成功后执行 prepare：

```bash
python scripts/run_analysis.py persist_references --db-path "<db_path>"
```

读取 API resolution 结果、`reference_core_batch_paths`、metadata packages、split packages 和 field guidance。只有 unresolved entries 需要 core review；metadata review 只使用各自 batch 的本地证据。

提交入口：

```bash
python scripts/run_analysis.py persist_references \
  --db-path "<db_path>" \
  --payload-file references.json
```

- core payload 使用 `reference_reviews[]`，每项保持 `reference_key`，`selected_parse_pattern` 取自允许集合，并填写 `authors`、`title`、`publication_year` 与可选 `review_notes`。
- core review 不提交 `metadata`、`raw`、`confidence`、`ref_index` 等 runtime 字段。
- 边界不稳定时先按 `split_review_packages` 提交 `split_reviews[]`；修正文本必须保留原始 tokens、语言与标识符。
- core 成功后使用 `metadata_evidence_reviews[]`，status 只能是 `fields_extracted`、`existing_fields_confirmed`、`no_local_evidence`，只填写本地可见的 canonical metadata。
- author 边界保持完整，title 使用原文文字系统，不得 placeholder、翻译或补造。
- 成功后按 `next_action` 进入 citation prepare。Reference 细节读取 [reference_extraction.md](references/reference_extraction.md)。

### 7. `persist_citation_analysis`

Prepare：

```bash
python scripts/run_analysis.py persist_citation_analysis --db-path "<db_path>"
```

读取 `citation_batch_paths`、`citation_work_packages`、scope、allowed payload shape 与 merge contract。只消费 runtime 已 mapping 的 workset，不重新做 mention-reference join。

Submit：

```bash
python scripts/run_analysis.py persist_citation_analysis \
  --db-path "<db_path>" \
  --payload-file citation.json
```

payload 可含 `citation_semantic_reviews[]`、`timeline_summaries` 和全局 `summary`。阶段采用 tolerant best-effort：未提交的 known key 不生成占位语义，缺段或空 summary 合法；unknown keys、forbidden internal fields 和非法 JSON 仍失败。

- `citation_semantic_reviews[*]` 保持 `citation_work_key`，填写 `topic`、`usage`、`role_in_context`、2-5 个 `keywords`、条目 `summary` 与可选 `key_reference_reason`。
- `timeline_summaries` 含 `early` / `middle` / `recent` 叙述；不填写 bucket membership。
- 不提交 `report_md`、mentions、timeline ref indexes 或最终渲染字段。
- `citation_package_count=0` 时提交空 citation payload 完成阶段。
- 成功提交后 runtime 级联 final render。细节读取 [citation_analysis.md](references/citation_analysis.md)。

### 8. `finalize_outputs`

用于恢复或手动重渲染，只在 DB 状态完整或需要重新生成公开产物时执行。正常 citation 提交已自动完成这一步。

```bash
python scripts/run_analysis.py status --db-path "<db_path>"
python scripts/run_analysis.py finalize_outputs --db-path "<db_path>"
```

`status` 根据 workflow 状态、classification 与 prerequisites 返回当前 `next_action`。finalize 不接受业务 payload、source/language/output override 或手写 `report_md`。成功后 stdout 来自 DB-backed renderer，artifact registry 与 result mirror 同步更新。

## 阶段性最低输出约束

- classification 只提交规定的四字段对象；低置信分类使用 effective `general` 并保留原因。
- plan 必须一次提交 outline、两个 scope、source identity 和 matching metadata。
- digest 只提交结构化 slot、section summaries 与可选 representative image；最终标题和 Markdown 由 renderer 生成。
- scoring 只编辑 draft 的 semantic fields；locked classification/rubric 或 stale form 会被拒绝。
- references 不得编造 `references_scope` 外的条目；metadata review 不得联网或修改 locked core fields。
- citation 不重做 mention-reference join，不直写 `report_md`，不填 timeline bucket membership。
- 恢复时先读 `status.next_action`；不要跳过 classification 或手工写 SQLite。

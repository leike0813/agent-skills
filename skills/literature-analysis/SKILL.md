---
name: literature-analysis
description: Generate a source-grounded paper score, digest, structured references, citation analysis, matching metadata, and citation report from a source literature file. Use when you need full literature analysis and assessment with digest, references, citation semantics.
compatibility: Requires local filesystem read access to source_path; public network access is optional and reference extraction continues locally when unavailable.
---

# literature-analysis

本 skill 以 SQLite runtime 为过程真源，按 7 个 agent-facing 阶段生成 literature score、digest、references、citation analysis、matching metadata 和 citation report。

## 目标

从一个本地文献来源生成可审计、可恢复且适合机器消费的完整论文分析。语义判断由 agent 完成；确定性预处理、状态迁移、API reference resolution、校验和公开产物渲染由 runtime 完成。

## 非目标

- 不搜索或替换来源论文；`source_path` 始终是论文内容真源，`identifier` 只用于精确获取来源论文的公开 bibliography。
- 不以 provider 返回的数量、顺序或条目替换本地 reference 边界；API 记录只解析本地已准备的 entries。
- 不在 Reference Metadata Evidence Review 中访问网络或外部数据库；该回合只审核 runtime batch 中的本地证据。
- 不由 agent 手工拼装公开 artifacts、最终 stdout JSON 或 SQLite 状态。

## 后台自动化约束

本 skill 运行于后台自动化场景：运行过程中不得询问用户做决策。任何分支或不确定性都应采用本文件定义的默认行为、脚本校验和恢复路径继续推进。

stdout 只能输出一个 JSON 对象，不得夹杂解释文本、日志或多段输出。读取输入失败、归一化失败、校验失败或渲染失败时，也必须返回 schema-compatible JSON，并在 `error` 中写入结构化失败信息。

## 核心执行指令

1. 先读本 `SKILL.md`，不要一开始读取整个 `references/` 目录。
2. 只从 prompt payload 读取 `source_path`、`language`、可选 `score_only` 与可选 `identifier`；`source_path` 是唯一内容来源，`score_only` 未提供时为 `false`，`identifier` 只用于精确查询公开引文 API。
3. 所有阶段都通过 `scripts/run_analysis.py` 执行。
4. SQLite 是过程真源；语义结果必须通过阶段 payload 写入 runtime DB，不能手写 SQLite 表伪造完成。
5. `init_runtime` 是唯一允许纯运行时设置的阶段；后续阶段都必须包含 agent 的语义决策或语义审核。
6. 正常路径在 `persist_digest` 后执行 `persist_literature_score`，再进入 `persist_references`；reference 预处理仍不依赖 digest 或 scoring payload，可独立 prepare。
7. Reference title 必须保持 raw reference 中的原始语言和文字系统；不得翻译、英文化、罗马化，或用 `none` / `null` / `unknown` / `untitled` / `N.A.` 等 placeholder 代替未知题名。
8. 当环境支持 subagent 且 runtime 返回可分批的 batch file paths 时，reference review、metadata review、citation semantic review 必须默认按 runtime 预切 batch 委派；只有主智能体可以合并并提交一次正式 payload。
9. 最终公开产物只能由 runtime 从 DB 和运行时模板渲染生成；agent 不直接写最终 `literature_score.json`、`digest.md`、`references.json`、`citation_analysis.json`、`citation_analysis.md`。
10. 最终 assistant 输出必须直接采用 runtime 返回的 stdout JSON，且满足下方 stdout schema。

Runtime path is owned by `literature-analysis/scripts/analysis_runtime` and `literature-analysis/assets`.

## Subagent Delegation Contract

Reference core review、Reference Metadata Evidence Review、citation semantic review 是本 skill 的默认可委派工作。只要当前环境支持 subagent、runtime/JIT 返回 batch file paths，且 batch 不是小到无需拆分或上下文不可拆，主 agent 必须默认按 runtime 预切 batch 委派。跳过委派时，主 agent 应在执行 notes、`review_notes` 或 payload 合并说明中保留原因。

主 agent 职责：

- 读取 runtime/JIT 返回的 manifest path、batch file paths、field guidance、batch prompts 和 merge contract。
- 按 runtime 预切的 batch JSON 文件路径委派 subagent，收集 batch draft。
- 合并 drafts，保持 stable keys 不变，去重，校验覆盖集合，再提交一次正式 payload。
- 作为唯一 DB writer 执行 `scripts/run_analysis.py`，不得让 subagent 写 DB、提交 payload 或生成最终 artifacts。
- 不得从全量 workset 或 review sidecar 手工切 batch；runtime batch files 是唯一委派输入边界。

Subagent 职责：

- 只处理分配给自己的 batch，只返回 batch draft JSON。
- 不写 DB，不运行 runtime command，不提交 payload，不生成 final artifacts。
- 不改 `reference_key` / `citation_work_key` 等 stable keys。
- 不填 `raw`、`confidence`、`ref_index`、mentions、timeline bucket、`report_md` 等内部审计或 renderer 字段。
- 不修改 locked fields；Reference Metadata Evidence Review 只能基于 batch JSON 中的本地证据返回 canonical metadata 字段和 evidence note。

Subagent 禁止处理全局闭包：citation timeline bucket membership、全局 `summary`、最终 report 和 artifact 渲染始终由 runtime 或主 agent 负责。

Runtime batch files are written under `.literature_analysis_tmp/agent_work/`. Each batch has at most 10 items and contains the package subset, allowed enum subset, prompt, return shape, forbidden fields, merge notes, and `suggested_draft_output_path`.

Mandatory delegation points:

- Reference Core Review Delegation Point：`persist_references` prepare 返回 `reference_core_review_manifest_path` 与 `reference_core_batch_paths` 后，主 agent 必须把每个 batch JSON 文件路径交给 subagent；subagent 读取该文件并使用其中的 prompt 和 package 子集完成 draft。
- Reference Metadata Evidence Review Delegation Point：core `reference_reviews[]` submit 成功并返回 `metadata_evidence_review_manifest_path` 与 `metadata_evidence_batch_paths` 后，主 agent 必须把每个 metadata evidence batch JSON 文件路径交给 subagent；subagent 只处理该文件内 keys。
- Citation Semantic Review Delegation Point：`persist_citation_analysis` prepare 返回 `citation_semantic_review_manifest_path` 与 `citation_batch_paths` 后，主 agent 必须把每个 citation batch JSON 文件路径交给 subagent；subagent 读取该文件并返回 `citation_semantic_reviews[]` draft。

Allowed reasons to skip a delegation point are limited to: no subagent capability in the environment, a trivially small batch where delegation adds no value, or a batch that cannot be split without losing necessary context. Do not skip because a temporary script seems faster.

## 输入输出硬契约

- 输入只读取 prompt payload：
  - `source_path`
  - `language`
  - `score_only`（可选 boolean，默认 `false`）
  - `identifier`（可选 string，默认空；支持 DOI 与 arXiv）
- `source_path` 支持：
  - Markdown / 纯文本
  - PDF
  - 单文件 `.tex`
  - LaTeX 工程目录
  - 无扩展名 UTF-8 文本文件
- `language` 若用户显式指定则直接使用；否则先从 prompt 主要语言推断，仅在无法稳定判断时回退 `zh-CN`。
- `score_only=true` 时只执行初始化/归一化与评分，跳过 analysis plan、digest、references 和 citation analysis。
- `identifier` 非空且合法时优先作为来源论文标识；格式非法时 runtime 写 warning，并使用 analysis plan 中有原文证据的 `source_identity`。两者都不可用时，reference 阶段直接执行本地审核流程。

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

成功态 stdout JSON 可选包含：

- `citation_analysis_report_path`
- `representative_image`

固定公开产物文件名：

- `digest.md`
- `references.json`
- `citation_analysis.json`
- `citation_analysis.md`
- `literature_matching_metadata.json`
- `literature_score.json`

输出路径规则：

- stdout JSON 中公开产物路径必须是绝对路径。
- `citation_analysis.md` 内容必须与 `citation_analysis.json.report_md` 完全一致。
- 最终结果 JSON 同步镜像写入 runtime DB 固化的 result JSON path。
- 失败时仍返回 schema-compatible JSON；路径字段为空字符串，`error` 填入 `{code, message}`。

成功态 stdout 示例：

```json
{
  "digest_path": "/abs/path/digest.md",
  "references_path": "/abs/path/references.json",
  "citation_analysis_path": "/abs/path/citation_analysis.json",
  "literature_matching_metadata_path": "/abs/path/literature_matching_metadata.json",
  "literature_score_path": "/abs/path/literature_score.json",
  "citation_analysis_report_path": "/abs/path/citation_analysis.md",
  "representative_image": {
    "status": "selected",
    "source_kind": "markdown_image_ref",
    "label": "Figure 2",
    "caption_quote": "Overview of the proposed pipeline",
    "section_hint": "Methods",
    "markdown_src_hint": "figures/overview.png",
    "selection_reason": "该图概括论文核心方法流程。",
    "confidence": "medium"
  },
  "provenance": {
    "generated_at": "2026-03-31T09:00:00Z",
    "input_hash": "sha256:0123456789abcdef",
    "model": "gpt-5.4"
  },
  "warnings": [],
  "error": {}
}
```

失败态 stdout 示例：

```json
{
  "digest_path": "",
  "references_path": "",
  "citation_analysis_path": "",
  "literature_matching_metadata_path": "",
  "literature_score_path": "",
  "provenance": {
    "generated_at": "",
    "input_hash": "",
    "model": ""
  },
  "warnings": [],
  "error": {
    "code": "normalize_source_failed",
    "message": "source_path not found: /abs/path/missing.pdf"
  }
}
```

## SQLite SSOT

- 新 run 的 `working_dir`、`tmp_dir`、`db_path`、`result_json_path`、`output_dir` 在 `init_runtime` 中固化。
- 后续阶段只读取 DB 中已经固化的 runtime inputs、normalized source、outline、scope、reference/citation workset 和模板路径。
- 不保留中间 JSON/Markdown 文件作为过程真源；workset/review JSON 只是人工审阅副产物。
- 一旦某项决策已经写入 DB，后续 payload 不应重新指定它。例如：
  - `persist_digest` 不重传 `source_path`
  - `persist_references` 不重传 `references_scope`
  - `persist_citation_analysis` 不重传 `citation_scope`
  - `finalize_outputs` 不接受业务 payload 或输出目录覆盖
- 结构化 payload 默认通过 `--payload-file` 传入，避免超长内联 JSON 命令。
- Payload 文件必须是 UTF-8 JSON。不要在 shell heredoc 中手写复杂转义；可以用编辑器、JSON encoder 或脚本把已经完成的 LLM/subagent 决策序列化为 JSON 文件。若 JSON 语法无效，runtime 返回 `payload_json_invalid`，不会猜测修复未转义引号。

## Runtime 调用方式

- 正式 skill 指令只假设有可用 `python`。
- 从 skill 目录执行时使用 `python scripts/run_analysis.py ...`。
- 从 skill 父目录或工作区执行时使用 `python literature-analysis/scripts/run_analysis.py ...`。
- 需要 module 形式时，可使用 `PYTHONPATH=literature-analysis/scripts python -m run_analysis ...`。
- `run_analysis.py` 会基于自身路径自举 `analysis_runtime` 导入；不要在 skill 指令中依赖本机专属虚拟环境路径。

## LLM 与脚本职责边界

必须由 agent/LLM 完成：

- 大纲和 `references_scope` / `citation_scope` 决策
- `literature_matching_metadata`
- 在 runtime review draft 中选择论文类型，完成 criterion 评分、applicability、原文 evidence quotes、dimension confidence 与评分理由
- digest 槽位内容与分章节总结
- representative image 的文本证据判断
- reference candidate 选择、核心字段 refinement、Reference Metadata Evidence Review
- split review 的边界判断与 source-preserving corrected reference texts
- citation semantic review，包括 `topic`、`usage`、`role_in_context`、`keywords`、item `summary` 和 `key_reference_reason`
- `timeline_summaries` 和全局 citation `summary`

必须由脚本完成：

- 输入协议探测与标准化
- PDF/Markdown/LaTeX 归一化
- SQLite 写入与状态推进
- reference deterministic preprocess、candidate/workset 生成、质量校验
- citation mention extraction、mention mapping、workset 生成
- payload schema 校验
- 生成并锁定 scoring review form、校验 form identity、定位 evidence quotes、派生证据行号和 criterion status
- rubric snapshot、N/A 归一化、权重重分配、dimension/overall/confidence/adjusted score 计算
- JSON 语法解析、字段别名规范化、stable key 覆盖检查、重复 key 检查
- 基于 DB 与模板渲染最终产物
- stdout JSON 合法性检查

绝对禁止：

- 用临时脚本、正则批处理或批量规则代替 LLM/subagent 做摘要、大纲、scope 决策、representative image 判断、reference candidate 选择、authors/title/year refinement、Reference Metadata Evidence Review、split review 边界判断、citation semantic review、timeline narratives 或全局 summary。
- 用临时脚本从 workset 自动填充 `reference_reviews[]`、`metadata_evidence_reviews[]` 或 `citation_semantic_reviews[]` 的语义字段。
- 允许的脚本用途仅限：调用 `run_analysis.py`、读取/格式化 runtime 返回的 work packages、检查 JSON 语法、统计 stable key 覆盖、合并已经由 LLM/subagent 产出的 batch drafts、把已经审核过的决策序列化为 payload 文件。
- 绕过 `run_analysis.py` 手工写 DB。
- 手工编辑最终公开 JSON 再假装它来自 renderer。

## 参数词表（literature-analysis）

- `source_path`：唯一内容来源路径；输入文件或 LaTeX 工程目录。
- `language`：输出语言；控制 digest 与 citation report 语言。
- `score_only`：为 `true` 时只执行源归一化和 `persist_literature_score`，其余公开产物路径留空。
- `identifier`：可选 DOI/arXiv 来源标识；只触发精确公开 API 查询，不触发标题搜索。
- `source_identity`：analysis plan 中必填但可为 `null` 的来源标识证据对象；非空时含 `identifier`、`evidence_quote`、`line_start`、`line_end`。
- `working_dir`：本次运行根目录；由 `init_runtime` 固化。
- `tmp_dir`：本次运行临时副产物目录；保存 normalized source、workset exports、runtime templates 等。
- `db_path`：SQLite runtime DB 路径；所有过程数据以它为真源。
- `result_json_path`：最终 stdout JSON 的镜像文件路径。
- `output_dir`：最终公开产物输出目录。
- `normalized_source`：脚本归一化后写入 DB 的唯一分析文本。
- `outline_nodes`：按原文顺序组织的章节骨架，含 `node_id`、`heading_level`、`title`、`line_start`、`line_end`、`parent_node_id`、`metadata`。
- `references_scope`：references 抽取允许覆盖的章节范围，含 `section_title`、`line_start`、`line_end`、`metadata`。
- `citation_scope`：citation workset 抽取允许覆盖的综述/背景范围，含 `section_title`、`line_start`、`line_end`、`metadata.selection_reason`。
- `literature_matching_metadata`：下游候选召回 sidecar；固定 schema 为 `literature_matching_metadata.v1`，含 `key_terms`、`methods`、`problems`、`datasets`、`exclude_terms`。
- `representative_image`：可选代表图选择结果，只能基于文本中的图片引用、figure label、caption、章节和页码线索判断。
- `digest_slots`：最终 digest 的结构化槽位，不是最终 Markdown。
- `section_summaries`：按大纲顺序组织的章节级摘要列表。
- `literature_score`：DB 中的结构化论文评分状态；包含论文类型、六维逐项结果、质量总分、confidence 与 confidence-adjusted score。
- `reference_key`：reference review 的稳定工作键，例如 `reference-10`。
- `selected_parse_pattern`：agent 必填的 reference parse hypothesis；必须来自 JIT 输出的 `allowed_parse_patterns`。
- `split_review_packages`：reference 边界不稳定时提供的复核工作包。
- `suspect_blocks`：reference preprocess 标出的疑似过切、合并或噪声块；由 prepare 输出供 split review 判断。
- `batch file paths`：runtime 预切 subagent 输入文件路径；每个 batch 最多 10 条，主 agent 不手工切 batch。
- `requires_split_review`：reference deterministic preprocess 判断仍需条目边界复核。
- `file_quality_low`：reference 文件级质量低信号；只有 DB 中 deterministic preprocess 写入时才有效。
- `reference_preprocess_quality`：reference preprocess 的质量指标快照；agent 不得在 payload 中伪造。
- `metadata_evidence_reviews`：reference metadata 的本地证据审核结果，只从 batch JSON 可见证据中抽取 allowed metadata。
- `mention_id`：citation mention 唯一 ID。
- `citation_work_key`：citation semantic review 的稳定工作键，例如 `citation-work-12`。
- `source_reference_number`：原文数字引用编号，仅供人工定位。
- `role_in_context`：自然语言描述该引用在原文中的功能；runtime 会映射为内部渲染分类。
- `topic`：被引工作在当前 `citation_scope` 中代表的主题、路线或对象。
- `usage`：原文为什么引用该工作，用它完成什么论证。
- `keywords`：2-5 个短词组，概括任务、方法、对象或路线。
- `key_reference_reason`：若该文献是关键引用，说明原因；runtime 据此派生关键文献标记。
- `summary`：在 citation item 中是条目级作用总结；在 citation payload 顶层是全局引文组织总结。
- `timeline_summaries`：`early` / `middle` / `recent` 三段自然语言时间线总结；runtime 派生 bucket membership，缺失或空字符串合法。

## 参考索引

启动时只读本文件。只有在进入对应阶段或遇到对应错误时，才读取下列 references：

- [source_and_plan.md](references/source_and_plan.md)：`init_runtime`、`persist_analysis_plan`、source normalization、scope 决策。
- [digest_generation.md](references/digest_generation.md)：`persist_digest`、digest slot、section summary、representative image。
- [paper_scoring.md](references/paper_scoring.md)：`persist_literature_score` review form、语义评分、evidence quotes、applicability、confidence 与错误恢复。
- [reference_extraction.md](references/reference_extraction.md)：`persist_references`、split review、quality gate、Reference Metadata Evidence Review、bibliography formats。
- [citation_analysis.md](references/citation_analysis.md)：`persist_citation_analysis`、mention mapping、semantics、timeline、summary。
- [finalization_and_recovery.md](references/finalization_and_recovery.md)：`finalize_outputs`、render validation、错误恢复。

正常执行只读取本 skill 的阶段指南和 runtime 返回的 JIT 指令。

## 最小执行主路径

### 1. `init_runtime`

- 何时执行：
  - 新 run 的第一步。
  - 必须在任何语义 payload 提交前执行。
- 调用命令：
```bash
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
- 读取真源：
  - prompt payload 的 `source_path`、`language`、可选 `identifier`
  - shell 当前工作目录（若未显式传 `--working-dir`）
- 脚本职责：
  - 固化 runtime paths
  - 初始化 SQLite
  - 写入 source/language/provenance
  - 持久化 runtime templates
  - 规范化 Markdown/PDF/LaTeX source
  - 写入 `normalized_source`
- 必须参数：
  - `--source-path`
  - `--language`（若 prompt 未显式给出，由 agent 推断后传入）
- 可选参数：
  - `--identifier`：只在 prompt payload 的 `identifier` 非空时传入。
- 最小合法示例：
```bash
python scripts/run_analysis.py init_runtime --source-path "/tmp/paper.md" --language "zh-CN"
```
- 成功后应该看到：
  - stdout JSON 包含 `db_path`
  - `source_profile.source_type`
  - `source_profile.normalized_source_chars > 0`
  - `next_action = "persist_analysis_plan"`
  - `score_only=true` 时 `next_action = "persist_literature_score"`
- 关键失败分支：
  - 文件不存在：返回 `error.code=FILE_NOT_FOUND` 或 `normalize_source_failed`
  - PDF 转换失败：返回 schema-compatible error；不要继续提交语义 payload
  - 非 zh/en 语言模板需要后续专门模板策略时，参考 `source_and_plan.md`

### 2. `persist_analysis_plan`

- 何时执行：
  - `init_runtime` 成功后。
  - agent 已阅读 normalized source 并完成大纲、scope、matching metadata 决策后。
- 调用命令：
```bash
python scripts/run_analysis.py persist_analysis_plan --db-path "<db_path>" --payload-file plan.json
```
- 读取真源：
  - DB 中的 `normalized_source`
  - `source_profile`
- 必须 payload：
  - `outline_nodes`
  - `references_scope`
  - `citation_scope`
  - `source_identity`（无法从原文稳定识别 DOI/arXiv 时显式写 `null`）
  - `literature_matching_metadata`
- 可选 payload：
  - `representative_image_plan`（若先在 plan 阶段记录候选线索；最终选择仍在 digest payload）
- 字段含义：
  - `outline_nodes[*].node_id`：同一 payload 内唯一。
  - `outline_nodes[*].heading_level`：标题层级。
  - `outline_nodes[*].line_start/line_end`：1-based 行号范围。
  - `references_scope`：唯一合法 bibliography extraction 边界。
  - `citation_scope`：唯一合法 citation workset 边界；应覆盖文献综述职责范围。
  - `source_identity`：来源论文的 DOI/arXiv 及其 normalized source 行号证据；证据不得落在 `references_scope` 内。
  - `literature_matching_metadata.key_terms/methods/problems/datasets/exclude_terms`：用于下游候选召回，不是正文阅读真源。
- 最小合法示例：
```json
{
  "outline_nodes": [
    {
      "node_id": "n1",
      "heading_level": 1,
      "title": "Introduction",
      "line_start": 1,
      "line_end": 48,
      "parent_node_id": null,
      "metadata": {}
    }
  ],
  "references_scope": {
    "section_title": "References",
    "line_start": 201,
    "line_end": 260,
    "metadata": {}
  },
  "citation_scope": {
    "section_title": "Introduction + Related Work",
    "line_start": 1,
    "line_end": 80,
    "metadata": {
      "selection_reason": "综述职责集中在引言与相关工作",
      "covered_sections": ["Introduction", "Related Work"]
    }
  },
  "source_identity": null,
  "literature_matching_metadata": {
    "schema": "literature_matching_metadata.v1",
    "key_terms": ["citation-aware literature review"],
    "methods": ["dense retrieval"],
    "problems": ["evidence synthesis"],
    "datasets": [],
    "exclude_terms": ["clinical trial matching"]
  }
}
```
- 成功后应该看到：
  - `stored_outline_nodes`
  - `references_scope`
  - `citation_scope`
  - `next_action = "persist_digest"`
- 关键失败分支：
  - scope 越界：重新读取 normalized source 行号后修正。
  - matching metadata schema 错误：固定为 `literature_matching_metadata.v1`。

### 3. `persist_digest`

- 何时执行：
  - `persist_analysis_plan` 成功后。
  - agent 已生成 digest slots、section summaries，并完成 representative image 文本证据判断后。
- 调用命令：
```bash
python scripts/run_analysis.py persist_digest --db-path "<db_path>" --payload-file digest.json
```
- 读取真源：
  - `normalized_source`
  - `outline_nodes`
  - `language`
- 必须 payload：
  - `digest_slots`
  - `section_summaries`
- 可选 payload：
  - `representative_image`
- 字段含义：
  - digest 篇幅依据 normalized source 的实质篇幅与信息密度弹性调整；长且内容密集的来源应展开更多独立要点与章节总结，篇幅长但内容稀疏时不要机械扩写。
  - `digest_generation.md` 中的数量区间是常见输出的写作提示，不是 payload 上限；有充分原文依据时可以超过，也不要为了达到区间而重复或补写内容。
  - `digest_slots.tldr.paragraphs`：全局摘要，覆盖问题、方法、结果、局限与复现线索。
  - `research_question_and_contributions.research_question`：研究问题一句话。
  - `research_question_and_contributions.contributions`：有原文依据的核心贡献。
  - `method_highlights.items`：具体且彼此有区分的方法要点。
  - `key_results.items`：关键定量或定性结果。
  - `limitations_and_reproducibility.items`：局限和可复现性线索。
  - `section_summaries[*].source_heading`：原文章节标题。
  - `section_summaries[*].items`：章节要点，按大纲顺序。
- representative image 硬规则：
  - 必须主动寻找文本证据中的图候选。
  - 有 pipeline、architecture、method overview、核心结果图时优先选择。
  - 不能读取或导出图片本体；只基于 caption、figure label、Markdown/HTML/LaTeX 路径、PDF caption/page hint。
  - 没有可靠文本证据才返回 `{"status":"none"}`。
- 最小合法示例：
```json
{
  "digest_slots": {
    "tldr": {"paragraphs": ["本文提出……", "实验显示……"]},
    "research_question_and_contributions": {
      "research_question": "如何在保持效果的同时降低推理成本？",
      "contributions": ["提出新架构", "给出训练策略"]
    },
    "method_highlights": {"items": ["使用分层模块", "引入蒸馏损失"]},
    "key_results": {"items": ["在数据集 A 上提升 2%", "推理延迟下降 15%"]},
    "limitations_and_reproducibility": {"items": ["未开源训练代码"]}
  },
  "section_summaries": [
    {"source_heading": "Introduction", "items": ["定义研究背景", "说明核心挑战"]}
  ],
  "representative_image": {"status": "none"}
}
```
- 成功后应该看到：
  - `stored_digest_slots`
  - `stored_section_summaries`
  - `next_action = "persist_literature_score"`
- 关键失败分支：
  - 缺少固定 slot：补齐结构化槽位。
  - section summary 覆盖不足：按 outline 补充。
  - representative image 字段不合法：参考 `digest_generation.md`。

### 4. `persist_literature_score`

- 何时执行：
  - 正常路径在 `persist_digest` 成功后执行。
  - `score_only=true` 时在 `init_runtime` 成功后直接执行。
- prepare 命令：
```bash
python scripts/run_analysis.py persist_literature_score --db-path "<db_path>"
```
- prepare 后必须读取：
  - `scoring_review_form_path`
  - `scoring_review_draft_path`
  - `editable_fields`
  - `submit_command`
- agent 必须：
  - 只编辑 `scoring_review_draft_path` 中 `editable_fields` 列出的语义字段。
  - 在 `paper_type_choices[*].selected` 中选择一个且仅一个选项并填写理由。
  - 为每个 criterion 填写 `applicable`、`score`、`reason` 和 `evidence_quotes`；为每个 dimension 填写 `summary`，并为 active dimension 填写 `confidence`。
  - 只使用归一化原文证据；不依据外部声誉、引用量、venue 或联网信息评分。
- agent 不得提交：
  - 手写或修改 `form_id`、paper-type 值、key、名称、prompt、criterion 满分、权重或数组顺序。
  - evidence 行号、criterion status、dimension totals、dimension score、`overall_score`、`confidence_adjusted_score`。
- submit 命令：
```bash
python scripts/run_analysis.py persist_literature_score \
  --db-path "<db_path>" \
  --payload-file "<scoring_review_draft_path>"
```
- runtime 固定执行：
  - 从本次 rubric snapshot 生成并锁定完整 review form；同一 `form_id` 重复 prepare 不覆盖 draft。
  - 校验 locked fields 和完整答案，根据唯一选中的 choice 派生 paper type，根据 `applicable` 派生 criterion status。
  - 在 normalized source 中定位 `evidence_quotes`，生成公开产物的证据行号。
  - 按 rubric snapshot 计算维度分、有效权重和聚合值。
  - `overall_score`、`confidence`、`confidence_adjusted_score = overall_score × confidence`
- N/A 硬规则：
  - `applicable=false` 仅表示 criterion 对论文类型确实无评价对象；此时 score 必须为 null 并提供理由。
  - 未报告、证据弱或 agent 不确定仍使用 `applicable=true` 并按原文评分。
  - 部分 criterion 不适用时，runtime 在维度内按 applicable maximum points 归一化；整个维度不适用时将其权重按比例分配给 active dimensions 并写 warning。
- 成功后应该看到：
  - 正常路径：`literature_score_path` 与 `next_action = "prepare_references_workset"`。
  - score-only：stdout 即最终 JSON；`literature_score_path` 为绝对路径，其余公开产物路径为空字符串。
- 详细语义、证据定位、confidence 校准、draft 填写和恢复方法见 `paper_scoring.md`。

### 5. `persist_references`

- 何时执行：
  - `persist_literature_score` 成功后。
  - 本阶段先由 runtime 在本地 prepare 后自动尝试公开 API；只有未解决条目才进入 core submit 与 metadata submit，仍使用同一个公开 CLI 阶段。
- prepare 命令：
```bash
python scripts/run_analysis.py persist_references --db-path "<db_path>"
```
- prepare 读取真源：
  - `normalized_source`
  - `references_scope`
  - `runtime_inputs.identifier` 或 `source_identity`
- prepare 输出：
  - `workset_path`
  - `review_path`
  - `reference_core_review_manifest_path`
  - `reference_core_batch_paths`
  - `reference_core_package_count`
  - `reference_core_batch_count`
  - `split_review_packages_path`
  - `split_review_package_count`
  - `batch_max_items`
  - `allowed_payload_shape`
  - `field_guidance`
  - `subagent_prompt_template`
  - `merge_contract`
  - `reference_api` 与 `reference_api_audit_path`
- API 解析规则：
  - 本地 prepare 的条目边界、顺序、`raw` 与 stable key 始终为真源。
  - Runtime 在生成确定性 entries/candidates 后、外部化 split review package 前执行 API resolution；suspect block 通过 `entry_indexes` 关联本地条目。
  - 仅当一个 suspect block 的全部条目均已 accepted 时跳过该块；部分 accepted 时仍输出完整 `source_text`、fragments、`accepted_reference_keys` 与 `unresolved_reference_keys`，由 agent 整块复核。
  - DOI 先查 Crossref；仍有未解决条目时查 Semantic Scholar。arXiv 直接查 Semantic Scholar。
  - API 只自动接受完整且唯一匹配的 title/authors/year；Semantic Scholar 中含规范化 arXiv ID 的非精确 title candidate 使用 `0.95` 阈值，其他非精确 title candidate 使用 `0.90`，mutual-best margin 均为 `0.05`。精确 DOI/arXiv 匹配不使用 title 阈值。
  - Split review 改变边界时，runtime 清除旧 resolution，保留同一来源标识的 provider cache，并对新 entry indexes 重新匹配。
  - Provider 额外、乱序、模糊或不完整记录只进入内部审计。
  - API 或网络不可用时写 warning，未解决条目继续进入本地 core review。
  - `reference_core_required_coverage_keys` 只包含未解决条目；若全部解决，prepare 返回 `next_action="persist_citation_analysis"`，不生成 core/metadata batch。
- core submit 命令：
```bash
python scripts/run_analysis.py persist_references --db-path "<db_path>" --payload-file references.json
```
- 存在 `reference_core_batch_paths` 时，core submit 必须 payload：
  - `reference_reviews`
- split repair payload：
  - `split_reviews`
- metadata submit 命令：
```bash
python scripts/run_analysis.py persist_references --db-path "<db_path>" --payload-file reference_metadata.json
```
- 存在 `metadata_evidence_batch_paths` 时，metadata evidence submit 必须 payload：
  - `metadata_evidence_reviews`
- `reference_reviews[*]` 字段含义：
  - `reference_key`：来自 `reference_core_batch_paths[*]` 文件内 `reference_review_packages[*].reference_key` 的稳定工作键。
  - `selected_parse_pattern`：必填 parse hypothesis；只能取同一 batch 文件内 `allowed_parse_patterns_by_reference_key` 中列出的值。
  - `authors`：作者字符串数组，按原文顺序保留边界和缩写。
  - `title`：原始语言/文字系统标题，不得 placeholder。
  - `publication_year`：整数年份；无可靠证据时填 `null`。
  - `review_notes`：可选，说明低置信或人工判断依据。
- `reference_reviews[*]` 禁止字段：
  - 不得提交 `metadata`、`raw`、`confidence`、`ref_index` 或任何 DB/renderer 审计字段。
  - 富元数据必须等 runtime 返回 `metadata_evidence_review_manifest_path` / `metadata_evidence_batch_paths` 后，通过 `metadata_evidence_reviews[]` 单独提交。
- `metadata_evidence_reviews[*]` 字段含义：
  - `reference_key`：来自 `metadata_evidence_batch_paths[*]` 文件内的 `metadata_evidence_packages[*].reference_key`。
  - `status`：必填，只能是 `fields_extracted`、`existing_fields_confirmed`、`no_local_evidence`。
  - `metadata`：仅当 `status="fields_extracted"` 时填写；只能填写 batch JSON 本地证据支持的 canonical metadata 字段。
  - `evidence_note`：说明 metadata 证据来自 batch JSON 的 `locked_reference`、`existing_metadata` 或 `metadata_context_text`。
- Metadata canonical 字段：
  - 首选 `publicationTitle`、`DOI`、`ISBN`、`ISSN`、`archiveID`、`url`、`publisher`、`place`、`pages`、`volume`、`issue`、`itemType`、`date`、`conferenceName`、`university`。
  - Runtime 会把确定性别名如 `journal`、`journalTitle`、`journal_title`、`doi`、`isbn`、`issn`、`arxivId`、裸 arXiv id 规范化为 canonical 字段并写 warning。
  - 未知 metadata 字段不作为阻断错误，但会产生 `reference_metadata_field_unrecognized` warning；主 agent 应在合并 subagent drafts 时优先修正为 canonical 字段。
- `split_reviews[*]` 字段含义：
  - `block_key`：来自 `split_review_packages_path` 文件内 `split_review_packages[*].block_key`。
  - `accepted_reference_keys` / `unresolved_reference_keys`：runtime 提供的只读提示；即使部分条目已 accepted，也必须根据完整 block 证据判断边界。
  - `action`：来自该 package 的 `allowed_actions`。
  - `corrected_reference_texts`：当需要修正条目边界时，给出修正后的完整 reference 文本数组；可修复换行、空白、Unicode/全角半角、引号、破折号和标点样式差异，但不得翻译、改写、删 DOI/URL/arXiv ID、删作者/标题关键词，或补不存在的内容。
- Subagent hard rules：
  - 当环境支持 subagent 且存在 `reference_core_batch_paths` / `metadata_evidence_batch_paths` 时，core reference review 和 Reference Metadata Evidence Review 必须默认按 runtime 预切 batch 文件分批委派。
  - 只有环境不支持、batch 极小，或上下文不可拆时才由主 agent 自行完成；跳过原因写入执行 notes 或 `review_notes`。
  - subagent 只读取被分配的 batch JSON 文件，只返回 batch draft；不得写 DB、不得改 key、不得补 `raw`/`confidence`/`ref_index` 等内部审计字段。
  - 如果 subagent 可写文件，优先写到 batch JSON 中的 `suggested_draft_output_path` 并返回路径；否则直接返回 batch draft JSON。
  - 主 agent 先合并 core reference drafts 并提交 `reference_reviews[]`；成功后读取 `metadata_evidence_batch_paths`，再合并 metadata evidence drafts 并提交 `metadata_evidence_reviews[]`。
  - 主 agent 是唯一 DB 写入者。
- Reference core review subagent prompt (short)：
```text
You are reviewing one literature-analysis reference core batch.
Read the provided batch JSON file path first.
Use only reference_review_packages and allowed_parse_patterns_by_reference_key in that batch file.
Return JSON with reference_reviews[] only.
For each package, keep reference_key unchanged, choose selected_parse_pattern from that package's allowed list, and provide authors, title, publication_year, and optional review_notes.
Do not include metadata, raw text, confidence, ref_index, database fields, renderer fields, or entries outside this batch.
If file writing is available, write the draft to suggested_draft_output_path and return that path.
Do not write DB, run runtime commands, submit payloads, or generate final artifacts.
```
- Reference Metadata Evidence Review subagent prompt (short)：
```text
This is not a metadata discovery task.
You are reviewing one literature-analysis reference metadata evidence batch.
Read the provided batch JSON file path first.
Use only metadata_evidence_packages, allowed_metadata_fields, locked_fields, and evidence_policy in that batch file.
external_lookup_allowed is false: do not use web search, Crossref, arXiv, Google Scholar, Zotero, Semantic Scholar, DOI resolvers, or any external database.
Return JSON with metadata_evidence_reviews[] only.
For each package, keep reference_key unchanged and set status to fields_extracted, existing_fields_confirmed, or no_local_evidence.
Only include metadata for status=fields_extracted, only use canonical metadata fields, and include evidence_note naming the batch JSON field that supports each value.
If the information is not visible in locked_reference, existing_metadata, or metadata_context_text, use no_local_evidence. Do not search.
Do not modify locked fields, stable keys, selected_parse_pattern, raw text, confidence, ref_index, or other internal fields.
If file writing is available, write the draft to suggested_draft_output_path and return that path.
Do not write DB, run runtime commands, submit payloads, or generate final artifacts.
```
- Reference hard rules：
  - 不提交 runtime 审计字段；原文文本、置信度、内部序号由 runtime 从 workset 和候选生成。
  - public `references.json` 不包含 parse candidate/debug data；调试只看 `.literature_analysis_tmp/reference_parse_audit.json` 与 workset sidecar。
  - 不得将 `Al-Rfou, R.` 拆成 `["Al-Rfou", "R."]`。
  - 不得让 title 以前导逗号、句点、分号、冒号开头。
  - `placeholder_title`、`bare_identifier_or_url_title`、空 title 等质量问题必须修复或说明不可恢复。
  - `cjk_type_marker_entry`、全角标点、`［J］` / `［C］` / `［D］` / `［EB/OL］` 等线索必须按原文语言处理。
- core submit 最小合法示例：
```json
{
  "reference_reviews": [
    {
      "reference_key": "reference-10",
      "selected_parse_pattern": "authors_colon_title_in_year",
      "authors": ["Gu, J.", "Bradbury, J.", "Xiong, C.", "Li, V.O.", "Socher, R."],
      "title": "Non-autoregressive neural machine translation",
      "publication_year": 2018,
      "review_notes": "The selected pattern preserves the author boundary and title."
    }
  ]
}
```
- metadata submit 最小合法示例：
```json
{
  "metadata_evidence_reviews": [
    {
      "reference_key": "reference-10",
      "status": "fields_extracted",
      "metadata": {
        "conferenceName": "ICLR",
        "pages": "12-20"
      },
      "evidence_note": "Venue and pages are visible in metadata_context_text."
    }
  ]
}
```
- core submit 成功后应该看到：
  - `stored_reference_items`
  - `metadata_evidence_packages`
  - `instructions.allowed_metadata_fields`
  - `instructions.locked_fields`
  - `next_action = "persist_references"`
- metadata submit 成功后应该看到：
  - `metadata_evidence_review`
  - `next_action = "persist_citation_analysis"`
- 关键失败分支：
  - `requires_split_review=true`：先提交 `split_reviews[]` 修正 suspect blocks；若边界改变，runtime 会返回 regenerated reference review packages，随后再提交 `reference_reviews[]`。
  - split review token coverage 失败：按 `missing_tokens_sample`、`unexpected_tokens_sample`、`coverage_ratio` 修正文本，不要臆造或翻译。
  - split review 后 heuristic 仍疑似边界不稳定：runtime 会写 `reference_boundary_suspicion_after_review` warning 并继续，不要求额外 accept 步骤。
  - `file_quality_low=true`：只能基于 DB 中 deterministic quality snapshot 做 continue/abandon 决策。
  - invalid pattern：按错误详情中列出的 `allowed_parse_patterns_by_reference_key` 修正所有问题后重交。
  - missing/duplicate/unknown `reference_key`：一次性修正覆盖集合后重交。
  - core payload 含 `metadata`：改为先提交 core fields，等待 `metadata_evidence_packages` 后再提交 `metadata_evidence_reviews[]`。
  - metadata submit 覆盖不完整：按错误详情一次性补齐 missing/duplicate/unknown `reference_key`。

### 6. `persist_citation_analysis`

- 何时执行：
  - `persist_references` 成功后。
  - 本阶段分为 prepare 与 submit 两次命令。
- prepare 命令：
```bash
python scripts/run_analysis.py persist_citation_analysis --db-path "<db_path>"
```
- prepare 读取真源：
  - `normalized_source`
  - `citation_scope`
  - `reference_items`
  - citation mention deterministic preprocess
- prepare 输出：
  - `workset_path`
  - `review_path`
  - `scope`
  - `citation_semantic_review_manifest_path`
  - `citation_batch_paths`
  - `citation_package_count`
  - `citation_batch_count`
  - `batch_max_items`
  - `allowed_payload_shape`
  - `field_guidance`
  - `unresolved_mentions`
  - `filtered_false_positive_mentions`
  - `reference_free_mode`
  - `subagent_prompt_template`
  - `merge_contract`
- submit 命令：
```bash
python scripts/run_analysis.py persist_citation_analysis --db-path "<db_path>" --payload-file citation.json
```
- 推荐 payload：
  - `citation_semantic_reviews`
  - `timeline_summaries`
  - `summary`
- 本阶段是 tolerant best-effort 持久化：payload 字段可以缺失或为空；runtime 只保存 agent 已提交且 key 可识别的 citation items，不为未提交 key 制造占位语义。
- `citation_semantic_reviews[*]` 字段含义：
  - `citation_work_key`：来自 `citation_batch_paths[*]` 文件内 `citation_work_packages[*].citation_work_key` 的稳定工作键。
  - `topic`：该文献在当前 `citation_scope` 中代表的主题、路线或对象。
  - `usage`：原文为什么引用它，用它完成什么论证。
  - `role_in_context`：自然语言描述引用功能；runtime 会派生渲染分类。
  - `keywords`：2-5 个短词组。
  - `summary`：该引用在当前 scope 中的具体作用，不写泛化文献简介。
  - `key_reference_reason`：可选；非空时 runtime 将其视为关键引用依据。
- `timeline_summaries` 字段含义：
  - 可包含 `early`、`middle`、`recent` 三段自然语言总结；缺段或空字符串合法。
  - agent 不填写 bucket membership；runtime 根据年份派生闭包分桶。
- `summary` 字段含义：
  - 全局 citation analysis 总结，概括原文如何组织和使用这些引用；空字符串合法。
- Subagent hard rules：
  - 当环境支持 subagent 且存在 `citation_batch_paths` 时，citation semantic review 必须默认按 runtime 预切 batch 文件委派。
  - 只有环境不支持、batch 极小，或上下文不可拆时才由主 agent 自行完成；跳过原因写入执行 notes。
  - subagent 只读取被分配的 citation batch JSON 文件，只返回 `citation_semantic_reviews[]` draft；主 agent 合并后提交一次正式 payload。
  - 如果 subagent 可写文件，优先写到 batch JSON 中的 `suggested_draft_output_path` 并返回路径；否则直接返回 batch draft JSON。
  - 主 agent 单独撰写或整合 `timeline_summaries` 与全局 `summary`。
- Citation semantic review subagent prompt (short)：
```text
You are reviewing one literature-analysis citation semantic batch.
Read the provided batch JSON file path first.
Use only citation_work_packages in that batch file.
Return JSON with citation_semantic_reviews[] only.
For each package, keep citation_work_key unchanged and provide topic, usage, role_in_context, keywords, summary, and optional key_reference_reason.
Do not include ref_index, source mention arrays, function, is_key_reference, timeline buckets, timeline_summaries, global summary, report_md, or final artifacts.
If file writing is available, write the draft to suggested_draft_output_path and return that path.
Do not write DB, run runtime commands, or submit payloads.
```
- Citation hard rules：
  - 语义阶段只消费 citation batch files 中的 `citation_work_packages`，不得重新全文盲扫或重做 mention-reference join。
  - `source_reference_number` 只用于人工定位，不作为 submit 主键。
  - LaTeX `\cite{...}`、`\citep{...}`、`\citet{...}` 多 key 映射由 preprocess 完成。
  - BibTeX/alpha 风格 bracket labels（如 `[RNSS18]`、`[DGV+18]`、`[YDY+19]`、`[Fou]`）由 runtime 从正文和 references 自动映射；agent 不在 semantic payload 中填写 label 字段。
  - 图片链接、URL、资源路径、日期型字符串等假阳性应由 preprocess 过滤并计入 `citation_false_positive_filtered`。
  - 模糊 mention 进入 `unmapped_mentions`，不得硬猜。
  - Web/resource 型 reference 可以缺 authors/year；这会产生 warning 但不阻断。`publication_year=null` 的引用不会进入 runtime 自动时间线分桶，可能产生 `citation_timeline_missing_year` warning。
- 完整 payload 示例：
```json
{
  "citation_semantic_reviews": [
    {
      "citation_work_key": "citation-work-12",
      "topic": "早期注意力机制",
      "usage": "原文用它交代 transformer 之前的注意力思想来源。",
      "role_in_context": "historical background for pre-transformer attention",
      "keywords": ["attention", "pre-transformer", "historical lineage"],
      "summary": "该工作被用来追溯 transformer 之前的注意力思想来源，帮助原文把自身方法放回更早的技术谱系中。",
      "key_reference_reason": "它定义了引言中回溯技术谱系的早期起点。"
    }
  ],
  "timeline_summaries": {
    "early": "早期工作奠定基础建模思想。",
    "middle": "中期工作推动成熟检测路线。",
    "recent": "近期工作直接收束到本文方法脉络。"
  },
  "summary": "本节先用早期注意力与序列建模工作铺出技术背景，再引出本文路线。"
}
```
- 成功后应该看到：
  - runtime 自动渲染最终公开产物。
  - stdout 即最终 JSON。
- 宽松持久化规则：
  - `citation_semantic_reviews` 缺失、为空或只覆盖部分 `citation_work_key` 时合法；未提交 key 不生成 item。
  - `topic` / `usage` / `role_in_context` / `keywords` / `summary` 缺失或为空时合法；runtime 保存空字符串或空数组，不生成替代语义。
  - duplicate `citation_work_key` 不阻断；runtime 合并为一条，字符串字段取第一个非空值，`keywords` 合并去重。
  - unknown `citation_work_key`、forbidden internal fields、非法 JSON 仍然失败。
  - scope 存在但无稳定 mapped workset 时，prepare 会返回 `citation_package_count=0`；仍提交空 payload，让 runtime 持久化空 citation semantics、timeline、summary 并渲染空 citation artifact。

### 7. `finalize_outputs`

- 何时执行：
  - 仅用于恢复或手动重渲染。
  - 正常情况下 `persist_citation_analysis` submit 成功后已自动完成最终渲染。
- 调用命令：
```bash
python scripts/run_analysis.py finalize_outputs --db-path "<db_path>"
```
- 读取真源：
  - DB 中所有已持久化结构化数据
  - runtime templates
  - `output_dir`
  - `result_json_path`
- 必须 payload：
  - 无
- 成功后应该看到：
  - stdout 最终 JSON
  - `artifact_registry` 登记公开产物
  - result JSON mirror 与 stdout 内容一致
- 关键失败分支：
  - 缺 `digest_slots` / `section_summaries`：回到 `persist_digest`。
  - 缺 `literature_score`：回到 `persist_literature_score`。
  - 缺 `reference_items`：回到 `persist_references` 或确认 reference-free mode。
  - 缺 `citation_timeline` / `citation_summary`：回到 `persist_citation_analysis`。
  - `citation_analysis_report_path` 内容与 `citation_analysis.json.report_md` 不一致：不要手改产物，重新 finalize。

## 阶段性最低输出约束

- digest 阶段不得提交近最终 Markdown，只能提交结构化槽位。
- scoring 阶段只编辑 runtime review draft 的 `editable_fields`；不得改 locked fields 或手写权重、聚合值、status 与证据行号。
- references 阶段不得凭空编造未出现在 `references_scope` 的条目。
- Reference Metadata Evidence Review 不得修改 locked core fields，不得联网发现缺失 metadata。
- citation 语义阶段不得重做 mention-reference join。
- citation 阶段不得直接写 `report_md`。
- `citation_analysis.summary` 可以为空字符串；空 summary 代表本阶段未获得稳定全局综合。
- `persist_citation_analysis.citation_semantic_reviews[*]` 可以缺少 `topic`、`usage`、`role_in_context`、`keywords`、`summary`；runtime 不补造语义。
- prepare 已完成但 `citation_package_count=0` 时，必须提交空 citation payload 完成本阶段；不得跳过 citation 阶段、直接 finalize，或手工拼装最终 stdout JSON。
- `timeline_summaries` 可以缺少 `early`、`middle`、`recent`；runtime 仍写三段 timeline bucket，summary 可为空。
- agent 不填写 citation bucket membership；runtime 根据 dated citation items 派生时间线闭包。
- numeric 和 bracket-alpha 型渲染标签保留原文标签；author-year 型渲染标签由 renderer 合成 `[AY-k]`，不得与原始 numeric `[n]` 混用。

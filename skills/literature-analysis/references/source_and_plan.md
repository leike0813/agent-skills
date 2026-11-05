# Source, Classification, And Analysis Plan

本文件补充 `init_runtime`、`persist_literature_classification` 与 `persist_analysis_plan`。runtime 先固化路径、模板和 normalized source，再由 agent 分类并提交结构化 plan。

## 输入协议

Prompt payload 只读取：

- `source_path`：唯一内容来源；可以是 Markdown、纯文本、PDF、单文件 `.tex`、LaTeX 工程目录、无扩展名文本文件。
- `language`：digest 与 citation report 的目标语言。用户显式指定时直接使用；否则从 prompt 主要语言推断；无法稳定判断时回退 `zh-CN`。
- `score_only`：可选 boolean，默认 `false`。为 `true` 时完成 source normalization 与 classification 后直接评分，不生成 analysis plan、digest、references 或 citation analysis。
- `identifier`：可选 DOI 或 arXiv 来源标识，只用于 reference 阶段的精确公开 API 查询；不做标题搜索。

`source_path` 约束：

- 不得用用户声称的扩展名覆盖内容判断。
- 后续阶段不得重新读取任意 source 文件；只能读 DB 中的 `source_documents.normalized_source`。
- `source.md`、`source_meta.json`、workset exports 都是审计副产物，不是过程真源。

## LLM And Script Responsibilities

Script/runtime owns:

- Source type detection、PDF/Markdown/LaTeX normalization、`.bib` append、UTF-8 decoding、input hash、runtime paths、DB bootstrap 和 source profile。
- `literature_profiles.json` 加载、classification 结构校验、有效 profile 选择、rubric resolution 和 SQLite snapshot。
- Line numbering over `source_documents.normalized_source`。
- Classification 与 plan payload schema 校验。

LLM/agent owns:

- 阅读 normalized source，完成 `literature_classification`。
- Reading the normalized source and deciding `outline_nodes`、`references_scope`、`citation_scope`、`source_identity` 和 `literature_matching_metadata`。
- Grounding a non-null `source_identity` in a normalized-source line range outside `references_scope`；无法可靠定位 DOI/arXiv 时写 `null`。
- Explaining fallback scope choices in `metadata.selection_reason`。
- Keeping parent/child section coverage coherent。

Do not use a temporary script to classify by keywords or infer outline、references scope、citation scope、matching metadata from headings alone。Scripts may count lines or serialize the final payload after the agent has made the semantic decisions。

## Init Runtime Contract

`init_runtime` 合并 runtime path confirmation、DB bootstrap、template/profile persistence 与 source normalization，是唯一没有 agent 语义 payload 的阶段。

先在当前 shell 执行 `pwd`，再从 skill 目录执行：

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

repo 根目录使用 `python literature-analysis/scripts/run_analysis.py`。若 `working-dir` 省略，使用调用时的 shell 当前目录；若 `output-dir` 省略，使用 `working_dir`。

成功时固化：

- `working_dir`
- `tmp_dir`
- `db_path`
- `result_json_path`
- `output_dir`
- `source_path`
- `language`
- `score_only`
- `identifier`
- `generated_at`
- `input_hash`
- `digest_template_path`
- `citation_analysis_template_path`
- `literature_score_template_path`
- `literature_profiles_path`

successful init returns `next_action=persist_literature_classification`。init 不预选 profile 或 rubric；classification 将 resolved rubric 写入 SQLite snapshot，`scoring_rubric_path` 仅作为审计镜像。

After `init_runtime`，later stages may depend only on runtime inputs、normalized source 和已持久化 semantic state。不得传入新的 `source_path`、`language`、`score_only`、`identifier`、output directory、template path 或 normalized source override。

## Source Normalization Contract

Content-first detection rules:

- PDF signature `%PDF-` 优先于扩展名。
- 目录且可识别主入口 `.tex` 时按 LaTeX 工程目录处理。
- 文件内容命中 `\documentclass`、`\begin{document}` 或扩展名为 `.tex` 时按单文件 LaTeX 处理。
- 其它可读 UTF-8 文件按 Markdown / plain text 处理。
- 文件既不可读、也不是可识别 PDF/LaTeX/UTF-8 文本时，返回 schema-compatible error。

Normalization behavior:

- Markdown / UTF-8 plain text：直接标准化后写入 DB。
- PDF：优先使用可用 PDF-to-Markdown 转换；失败时降级文本抽取；仍不足以形成 normalized source 时失败。
- 单文件 `.tex`：原文包入 fenced code block，语言标记为 `tex`。
- LaTeX 工程目录：检测主入口，展平 `\input` / `\include`，整体包入 fenced code block，语言标记为 `tex`。
- LaTeX bibliography：若检测到 `\bibliography{...}` 或 `\addbibresource{...}`，把 `.bib` 原文追加为 fenced code block，语言标记为 `bibtex`，并标明其为 raw bib source。
- 无扩展名文件：若为 UTF-8 文本，按 Markdown/plain text 处理。

## Literature Classification

先读 normalized source，再提交固定对象：

```bash
python scripts/run_analysis.py persist_literature_classification \
  --db-path "<db_path>" \
  --payload-file classification.json
```

```json
{
  "literature_classification": {
    "disciplines": ["社会学", "公共政策"],
    "profile_id": "qualitative_empirical",
    "confidence": "high",
    "reason": "核心材料为访谈记录，作者通过系统性编码和跨案例比较形成解释。"
  }
}
```

字段必须是：

- `disciplines`：短标签字符串数组，可以为空；脚本去重并去除首尾空白，不接受空标签。
- `profile_id`：固定 enum。
- `confidence`：`high`、`medium` 或 `low`。
- `reason`：非空字符串，说明主要论证与证据，不只复述学科名称。

Profile enum:

| `profile_id` | 判断依据 |
| --- | --- |
| `quantitative_empirical` | 实验、观测、测量、统计推断或定量模型检验构成主要经验证据。 |
| `qualitative_empirical` | 访谈、观察、田野、案例或文本资料经系统质性分析形成解释。 |
| `interpretive_historical` | 史料、档案、文本与历史语境阐释是核心，重点在材料的意义和形成过程。 |
| `conceptual_normative` | 概念辨析、规范判断或价值论证构成核心，须说明权利、义务、正当性或应然安排。 |
| `formal_theoretical` | 形式模型、定义、定理、证明或推导承担主要论证。 |
| `review_synthesis` | 以系统或叙述性综述、比较、综合既有研究为主。 |
| `mixed_methods` | 定量与质性证据在同一核心论证中实质整合；并列汇报不自动归入此类。 |
| `general` | 没有专属 profile 明显占优，或证据不足以稳定选择。 |

classification 依据主要研究范式和证据结构选择，学科标签只描述领域。`confidence=low` 时 effective `profile_id` 固定为 `general`，runtime 添加 `classification_low_confidence` warning；该回退不直接降低质量分。

成功结果包含 effective classification、所选 profile 的四个 `digest_sections`、`rubric_id` 和 `next_action`。normal mode 进入 `persist_analysis_plan`，score-only 进入 `persist_literature_score`。

SQLite 表 `literature_classification` 单行保存 classification、profile、resolved rubric 与 normalized-source hash。相同分类和相同 profile 定义重复提交是幂等操作；重分类会失效 plan、digest、score、references、citation、artifact registry 与下游 receipts，并按运行模式回到 plan 或 scoring。重新初始化/re-normalize 也会让旧 classification 和依赖结果失效。

遇到恢复场景先运行 `status --db-path "<db_path>"`；`next_action` 是当前动作的唯一依据。

## Analysis Plan Payload

仅 normal mode。classification 成功后，`persist_analysis_plan` 写入 agent 的语义骨架：

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
      "selection_reason": "综述职责覆盖引言与相关工作",
      "covered_sections": ["Introduction", "Related Work"]
    }
  },
  "source_identity": {
    "identifier": "10.1109/CVPR.2016.90",
    "evidence_quote": "DOI: 10.1109/CVPR.2016.90",
    "line_start": 3,
    "line_end": 3
  },
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

`outline_nodes[*]` fields:

- `node_id`：stable unique ID in this payload。
- `heading_level`：integer heading level。
- `title`：source heading text。
- `line_start` / `line_end`：1-based line range in `normalized_source`。
- `parent_node_id`：parent ID or `null`。
- `metadata`：object，至少 `{}`。

Hard constraints:

- `outline_nodes` 不接受只有标题字符串的简写。
- `references_scope` / `citation_scope` 不接受章节名列表或纯语义描述。
- `parent_node_id` 必须显式出现；一级标题写 `null`。
- `metadata` 必须显式出现；没有补充信息时传 `{}`。
- `source_identity` 必须显式出现；只能是 `null` 或含 `identifier`、`evidence_quote`、`line_start`、`line_end` 的对象。
- 非空 `source_identity.identifier` 必须是有效 DOI/arXiv；证据行必须在 `normalized_source` 范围内、位于 `references_scope` 之外，且 `evidence_quote` 同时出现在该行范围并包含该标识符。
- `literature_matching_metadata` 必须显式出现；不得省略或留到 finalization 临时补写。

成功返回 stored outline、两个 scope、source identity、matching metadata 和 `next_action=persist_digest`。

## Scope Decision Rules

`references_scope`:

- Prefer the final valid references/bibliography block。
- Titles may be `References`、`REFERENCES`、`Bibliography`、`Works Cited`、`参考文献` 或 `引用文献`。
- Multiple candidates: choose the last reasonable block near document end。
- Include continuation lines until the actual reference list ends。
- If no reliable bibliography block exists，在 reference 阶段保留可审计的 empty/low-confidence state；不要发明 scope。

`citation_scope`:

- Should cover the review/background argument, not arbitrary experimental citations。
- It is one definition object, but may cover multiple sections such as `Introduction + Related Work`。
- If review discourse spans Introduction and Related Work, include both。
- parent-section selection includes all child subsections until the next same-or-higher heading。
- If a selected parent section has child subsections but the scope only covers the first paragraph, the scope is invalid。
- If headings are unreliable, use line ranges and explain fallback in `metadata.selection_reason`。
- If no reliable review-like scope exists, fail early with a structured error rather than letting citation preprocessing guess。

Invalid payload examples:

```json
{"outline_nodes": ["Introduction", "Related Work"]}
```

```json
{
  "references_scope": "References",
  "citation_scope": ["Introduction", "Related Work"]
}
```

## Literature Matching Metadata

This sidecar supports downstream candidate discovery；it is not reading evidence and does not replace digest artifacts。

Fields:

- `schema`：fixed `literature_matching_metadata.v1`。
- `key_terms`：up to 12 short topic/method/task terms。
- `methods`：up to 8 model、algorithm、mechanism 或 technical route names。
- `problems`：up to 8 task、challenge 或 objective phrases。
- `datasets`：up to 8 datasets、benchmarks、corpora 或 resources；缺失时 `[]`。
- `exclude_terms`：up to 6 terms that would retrieve unrelated domains；缺失时 `[]`。

Writing rules:

- Use short phrases, not full sentences。
- Strings may contain Chinese、English、hyphenated terms、abbreviations 和 formal dataset names。
- Do not copy long abstracts or source paragraphs。
- Do not add `bm25_text`。
- Avoid empty strings；scripts may trim and drop them。
- Do not include citation keys or full reference strings。

## Representative Image Planning

The final `representative_image` 在 `persist_digest` 提交；plan-stage reading only notes candidate figure evidence：

- Markdown image syntax：`![caption](path)`
- HTML images：`<img src="...">`
- LaTeX image commands：`\includegraphics{...}`
- PDF figure captions and page hints

Keep only text evidence。Do not extract、inspect 或 validate image binaries。

## Failure Semantics And Recovery

`init_runtime` failures:

- Missing source file：return schema-compatible JSON with empty output paths and structured `error`。
- Permission or encoding failure：do not continue to semantic stages。
- Unsupported source：fail unless PDF/LaTeX/UTF-8 detection can recover enough text。
- PDF conversion warnings：continue only if `normalized_source` has enough text for classification and planning。

`persist_literature_classification` failures:

- `classification_invalid`：补齐四个字段、使用合法 profile/confidence enum，或把 reason 写成基于 source 的说明。
- `classification_required`：先运行 `init_runtime`，或对 normalized source 完成并提交 classification。
- 重分类后旧 draft 或下游状态不再可用：读取 `status.next_action`，从当前 authority 重新生成。

`persist_analysis_plan` failures:

- Scope out of range：re-read `normalized_source` line numbers and resubmit plan。
- Missing `metadata`：provide `{}`。
- Invalid `literature_matching_metadata` schema：use `literature_matching_metadata.v1`。
- Citation scope too narrow：expand to cover child sections or adjacent review sections。
- References scope guessed without evidence：re-evaluate bibliography candidates；prefer an explicit low-confidence downstream reference state over invented lines。

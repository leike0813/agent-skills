---
name: literature-digest
description: Generate a paper digest (Markdown), structured references (JSON), and citation analysis artifacts from a source file using a SQLite-gated runtime.
compatibility: Requires local filesystem read access to source_path; no network required.
---

# literature-digest

本 skill 运行于后台自动化场景：不得向用户提问做决策。stdout 只能输出一个 JSON 对象。

## 核心执行指令

这部分是 gate 返回的 `core_instruction` 的完整等价内容。它只保留跨阶段都必须反复遵守的规则。

1. 先读 `SKILL.md`，不要预读整个 `references/` 目录。
2. 首次进入和每次正式写库后，都必须重新运行 `scripts/gate_runtime.py`。
3. 只能执行 gate 返回的 `next_action`。
4. 同时遵守 gate 返回的 `instruction_refs`、`core_instruction` 和 `execution_note`。
5. 所有语义判断结果都必须先整理为结构化 payload，再通过 `scripts/stage_runtime.py <next_action>` 写入 SQLite。
6. 一旦某项决策已经在前序阶段写入 DB，后续阶段只能从 DB 读取，不能重新指定。
7. 不要直接写 SQLite 表来伪造阶段完成；阶段推进必须由对应脚本动作成功写库。
8. 最终公开产物只能由 `render_and_validate --mode render` 从 DB 渲染生成。
9. **最终 assistant 输出必须是一个 JSON 对象，并且必须满足 stdout schema。**

成功态 stdout JSON 示例：

```json
{
  "digest_path": "/abs/path/digest.md",
  "references_path": "/abs/path/references.json",
  "citation_analysis_path": "/abs/path/citation_analysis.json",
  "citation_analysis_report_path": "/abs/path/citation_analysis.md",
  "provenance": {
    "generated_at": "2026-03-31T09:00:00Z",
    "input_hash": "sha256:0123456789abcdef",
    "model": "gpt-5.4"
  },
  "warnings": [],
  "error": null
}
```

失败态 stdout JSON 示例：

```json
{
  "digest_path": "",
  "references_path": "",
  "citation_analysis_path": "",
  "provenance": {
    "generated_at": "",
    "input_hash": "",
    "model": ""
  },
  "warnings": [],
  "error": {
    "code": "normalize_source_failed",
    "message": "read source failed: [Errno 2] No such file or directory"
  }
}
```

## 输入输出硬契约

- 输入只读取 prompt payload 中的 `source_path` 与 `language`
- `source_path` 是唯一内容来源；输入可为 Markdown、PDF 或无扩展名文件
- stdout 必须包含：
  - `digest_path`
  - `references_path`
  - `citation_analysis_path`
  - `provenance.generated_at`
  - `provenance.input_hash`
  - `provenance.model`
  - `warnings`
  - `error`
- stdout 可选包含：
  - `citation_analysis_report_path`
- 最终公开产物固定为：
  - `digest.md`
  - `references.json`
  - `citation_analysis.json`
  - `citation_analysis.md`
- `citation_analysis.json` 必须包含：
  - `meta`
  - `summary`
  - `items`
  - `unmapped_mentions`
  - `report_md`
- `citation_analysis.md` 内容必须与 `citation_analysis.json.report_md` 完全一致
- gate 每一步都会返回固定的 `core_instruction`；它是本节核心规则的精简镜像，不是另一套独立契约

## SQLite SSOT

- 运行时数据库固定为 `<cwd>/.literature_digest_tmp/literature_digest.db`
- 所有过程数据先写 SQLite
- 不保留中间 JSON/MD 文件作为过程真源
- 最终产物只能从 SQLite 中读取并渲染
- 结构化 payload 默认优先通过 `--payload-file` 传入；尤其在 Windows 下，避免拼接超长内联 JSON 命令

## 状态机与 Gate 纪律

状态机阶段固定为：
- `stage_0_bootstrap`
- `stage_1_normalize_source`
- `stage_2_outline_and_scopes`
- `stage_3_digest`
- `stage_4_references`
- `stage_5_citation`
- `stage_6_render_and_validate`
- `stage_7_completed`

执行纪律：
- 首次进入必须先运行 `scripts/gate_runtime.py`
- 每次正式写库后都必须重新运行 `scripts/gate_runtime.py`
- 只能执行 gate 返回的 `next_action`
- 若 gate 返回 blocker 或 repair 路径，必须先修复 DB 状态再继续
- 正常主路径下，gate 输出中的 `instruction_refs`、`core_instruction`、`execution_note` 和 `command_example` 是当前动作的显式参考，不得跳过
- 只有当 gate 进入 repair 路径时，才额外参考 `sql_examples`

## LLM 与脚本职责边界

必须由 LLM 完成：
- digest 槽位内容生成
- 大纲与 scope 决策
- references 语义字段补全
- citation semantics 与 summary

必须由脚本完成：
- 输入协议探测与标准化
- SQLite 写入与状态推进
- schema 校验
- 基于结构化 DB 内容渲染最终成品
- 输出 JSON 合法性检查

绝对禁止：
- 用临时脚本替代 LLM 做摘要、大纲、语义分类
- 绕过 gate 凭记忆推进阶段

## 参数词表（全项目统一）

以下词条是运行时参数与 payload 字段的统一定义。`references/` 下的附录文档、接口说明和 SQL 说明都必须沿用这些定义；首次出现时只补当前阶段约束，不重写基础含义。

- `source_path`
  - 中文名：源文件路径
  - 定义：用户传入的唯一内容来源文件路径。
  - 适用动作：`bootstrap_runtime_db`
- `language`
  - 中文名：输出语言
  - 定义：控制 digest 与 citation 分析语言；缺省回退 `zh-CN`。
  - 适用动作：`bootstrap_runtime_db`
- `output_dir`
  - 中文名：产物输出目录
  - 定义：step 1 确定并写入 DB 的最终公开产物目录；stage 6 只读取它，不再临时覆盖。
  - 适用动作：`bootstrap_runtime_db`
- `outline_nodes`
  - 中文名：大纲节点
  - 定义：按原文顺序组织的章节骨架，用来支撑后续 digest 与 scope 决策。
  - 适用动作：`persist_outline_and_scopes`
- `references_scope`
  - 中文名：参考文献范围
  - 定义：references 抽取允许覆盖的章节范围定义。
  - 适用动作：`persist_outline_and_scopes`
- `citation_scope`
  - 中文名：引文分析范围
  - 定义：citation workset 抽取允许覆盖的章节范围定义。
  - 适用动作：`persist_outline_and_scopes`
- `digest_slots`
  - 中文名：digest 槽位
  - 定义：最终 digest 的结构化内容槽位集合，而不是最终 Markdown。
  - 适用动作：`persist_digest`
- `section_summaries`
  - 中文名：分章节总结
  - 定义：按大纲顺序组织的章节级摘要列表。
  - 适用动作：`persist_digest`
- `entries`
  - 中文名：原始参考文献条目
  - 定义：从 references 范围切分出的原始条目列表。
  - 适用动作：`prepare_references_workset`
- `batches`
  - 中文名：批次定义
  - 定义：脚本或 LLM 用来描述分批处理边界与成员的列表。
  - 适用动作：`prepare_references_workset`
- `items`
  - 中文名：结构化条目列表
  - 定义：当前动作真正写入的核心对象数组；具体字段随动作不同而变化。
  - 适用动作：`persist_references`、`persist_citation_semantics`
- `selected_pattern`
  - 中文名：选定候选 pattern
  - 定义：agent 在 references 预解析候选中选中的切分模式标识。
  - 适用动作：`persist_references`
- `requires_split_review`
  - 中文名：需要条目切分复核
  - 定义：`prepare_references_workset` 判断当前 references workset 仍存在 grouped-entry 风险时返回的布尔标记。
  - 适用动作：`prepare_references_workset`
- `suspect_blocks`
  - 中文名：可疑分块列表
  - 定义：脚本判断边界仍不稳定、需要后续复核的 source block 列表及其原因说明。
  - 适用动作：`prepare_references_workset`
- `mention_id`
  - 中文名：引文标记 ID
  - 定义：一条 citation mention 的唯一标识。
  - 适用动作：`prepare_citation_workset`
- `ref_index`
  - 中文名：参考文献索引
  - 定义：引用 `reference_items` 中某条结构化文献记录的稳定编号。
  - 适用动作：`prepare_citation_workset`、`persist_citation_semantics`
- `function`
  - 中文名：引文功能类别
  - 定义：对某条 workset item 的语义归类，允许值由脚本枚举校验。
  - 适用动作：`persist_citation_semantics`
- `topic`
  - 中文名：引文主题
  - 定义：该被引工作在当前综述范围内代表的主题、路线或研究对象。
  - 适用动作：`persist_citation_semantics`
- `usage`
  - 中文名：引用用途
  - 定义：原文在当前 scope 中为什么引用这篇文献、借它完成什么论证。
  - 适用动作：`persist_citation_semantics`
- `keywords`
  - 中文名：引文关键词
  - 定义：概括该被引工作在当前综述范围中代表的主题词、方法词或任务词的短词组列表。
  - 适用动作：`persist_citation_semantics`
- `is_key_reference`
  - 中文名：关键文献标记
  - 定义：标记该 workset item 是否属于当前综述范围内必须点出的关键文献。
  - 适用动作：`persist_citation_semantics`
- `summary`
  - 中文名：总结文本
  - 定义：上下文相关的自然语言总结；在 `persist_citation_semantics` 中指条目级摘要，在 `persist_citation_summary` 中指全局总结。
  - 适用动作：`persist_citation_semantics`、`persist_citation_summary`
- `confidence`
  - 中文名：置信度
  - 定义：对条目级语义判断可信度的 0~1 评分。
  - 适用动作：`persist_citation_semantics`
- `basis`
  - 中文名：总结依据
  - 定义：描述全局 summary 依据的结构化补充信息，至少包括研究脉络、论述动作和关键文献索引。
  - 适用动作：`persist_citation_summary`
- `timeline`
  - 中文名：时间线分析
  - 定义：把当前综述范围内的已分析引文划分为 `early` / `mid` / `recent` 三段并分别给出时间段总结。
  - 适用动作：`persist_citation_timeline`
- `instruction_refs`
  - 中文名：附录阅读指引
  - 定义：gate 指定的当前阶段应按需阅读的文档路径与节标题列表。
  - 适用动作：`gate_runtime.py` 输出，所有阶段遵守
- `execution_note`
  - 中文名：执行提示
  - 定义：gate 为当前 `next_action` 返回的一条短提示，概括这一动作最关键的即时执行约束。
  - 适用动作：`gate_runtime.py` 输出，所有阶段遵守
- `core_instruction`
  - 中文名：核心执行指令
  - 定义：gate 每一步都返回的固定精简主指令，用来反复提醒跨阶段都必须遵守的规则。
  - 适用动作：`gate_runtime.py` 输出，所有阶段遵守
- `next_action`
  - 中文名：下一动作
  - 定义：gate 当前唯一允许执行的阶段动作名。
  - 适用动作：`gate_runtime.py` 输出，所有阶段遵守

## 最小执行主路径

启动时只读本文件。不要一开始读取整个 `references/` 目录；只有在 gate 返回 `instruction_refs` 后，才按当前阶段按需读取对应附录文档。并且每一步都要同时遵守 gate 返回的 `core_instruction` 与 `execution_note`。不得在开始阶段一次性读取全部 step 文档。

### 1. `bootstrap_runtime_db`

- 何时执行：
  - 首次进入 skill，或 gate 明确返回 `next_action=bootstrap_runtime_db`
- 调用命令：
```bash
python scripts/stage_runtime.py bootstrap_runtime_db \
  --source-path "/abs/path/paper.md" \
  --language "zh-CN" \
  --output-dir "/abs/path/artifacts"
```
- 必须提供的参数 / payload：
  - CLI 参数：`--source-path`
  - CLI 参数：`--language`（可省略，脚本会回退默认值）
  - CLI 参数：`--output-dir`（可省略；缺省时脚本把当前工作目录写入 DB）
- 各 payload 字段含义：
  - `source_path`：唯一内容来源文件路径
  - `language`：后续 digest 与 citation 分析语言
  - `output_dir`：最终 `digest.md`、`references.json`、`citation_analysis.json`、`citation_analysis.md` 的输出目录
- 最小合法示例：
```bash
python scripts/stage_runtime.py bootstrap_runtime_db --source-path "/tmp/paper.md" --language "zh-CN"
```
- 完成后应该看到的 gate 结果：
  - 再运行一次 `python scripts/gate_runtime.py`
  - `next_action` 应推进为 `normalize_source`

### 2. `normalize_source`

- 何时执行：
  - `bootstrap_runtime_db` 成功后，且 gate 返回 `normalize_source`
- 调用命令：
```bash
python scripts/stage_runtime.py normalize_source [--out-md "/abs/path/source.md"] [--out-meta "/abs/path/source_meta.json"]
```
- 必须提供的参数 / payload：
  - 无业务 payload；本步只读前序已写入的 `source_path` 与 `language`
- 各参数含义：
  - `--out-md`：可选物化标准化文本
  - `--out-meta`：可选物化标准化元数据
- 最小合法示例：
```bash
python scripts/stage_runtime.py normalize_source
```
- 完成后应该看到的 gate 结果：
  - 再运行 gate 后，`next_action` 应推进为 `persist_outline_and_scopes`

### 3. `persist_outline_and_scopes`

- 何时执行：
  - `normalize_source` 成功后，且 gate 返回 `persist_outline_and_scopes`
- 调用命令：
```bash
python scripts/stage_runtime.py persist_outline_and_scopes --payload-file /tmp/outline_scope.json
```
- 必须提供的参数 / payload：
  - `outline_nodes`
  - `references_scope`
  - `citation_scope`
- 各 payload 字段含义：
  - `outline_nodes[*].node_id`：节点唯一 ID；同一 payload 内不得重复
  - `outline_nodes[*].heading_level`：标题层级；一级标题通常为 `1`
  - `outline_nodes[*].title`：章节标题文本
  - `outline_nodes[*].line_start` / `line_end`：该节点覆盖的原文 1-based 行号范围
  - `outline_nodes[*].parent_node_id`：父节点 ID；一级标题必须显式写 `null`
  - `references_scope.section_title`：references 抽取范围的人类可读标题
  - `references_scope.line_start` / `line_end`：references 唯一合法抽取边界
  - `references_scope.metadata`：附加范围说明；至少传 `{}`，不要省略
  - `citation_scope.section_title`：citation workset 唯一合法抽取范围的标题
  - `citation_scope.line_start` / `line_end`：citation 唯一合法抽取边界
  - `citation_scope.metadata`：范围决策说明；至少包含 `selection_reason`，可附 `covered_sections`
- 最小合法示例：
```json
{
  "outline_nodes": [
    {
      "node_id": "n1",
      "heading_level": 1,
      "title": "Introduction",
      "line_start": 1,
      "line_end": 20,
      "parent_node_id": null,
      "metadata": {}
    },
    {
      "node_id": "n2",
      "heading_level": 1,
      "title": "Related Work",
      "line_start": 21,
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
    "line_end": 48,
    "metadata": {
      "selection_reason": "综述职责集中在引言与相关工作",
      "covered_sections": ["Introduction", "Related Work"]
    }
  }
}
```
- 完成后应该看到的 gate 结果：
  - `next_action` 应推进为 `persist_digest`

### 4. `persist_digest`

- 何时执行：
  - `persist_outline_and_scopes` 成功后，且 gate 返回 `persist_digest`
- 调用命令：
```bash
python scripts/stage_runtime.py persist_digest --payload-file /tmp/digest_payload.json
```
- 必须提供的参数 / payload：
  - `digest_slots`
  - `section_summaries`
- 各 payload 字段含义：
  - `digest_slots.tldr.paragraphs`：全局摘要段落数组
  - `digest_slots.research_question_and_contributions.research_question`：研究问题一句话说明
  - `digest_slots.research_question_and_contributions.contributions`：核心贡献列表
  - `digest_slots.method_highlights.items`：方法要点列表
  - `digest_slots.key_results.items`：关键结果列表
  - `digest_slots.limitations_and_reproducibility.items`：局限与可复现性线索列表
  - `section_summaries[*].source_heading`：对应原文章节标题
  - `section_summaries[*].items`：该章节的要点列表
- 最小合法示例：
```json
{
  "digest_slots": {
    "tldr": {"paragraphs": ["本文提出……", "实验显示……"]},
    "research_question_and_contributions": {
      "research_question": "如何在保持效果的同时降低推理成本？",
      "contributions": ["提出新架构", "给出新的训练策略"]
    },
    "method_highlights": {"items": ["使用分层模块", "引入蒸馏损失"]},
    "key_results": {"items": ["在数据集A上提升2%", "推理延迟下降15%"]},
    "limitations_and_reproducibility": {"items": ["未开源训练代码"]}
  },
  "section_summaries": [
    {"source_heading": "Introduction", "items": ["定义研究背景", "说明核心挑战"]}
  ]
}
```
- 完成后应该看到的 gate 结果：
  - `next_action` 应推进为 `prepare_references_workset`

### 5. `prepare_references_workset`

- 何时执行：
  - `persist_digest` 成功后，且 gate 返回 `prepare_references_workset`
- 调用命令：
```bash
python scripts/stage_runtime.py prepare_references_workset --out /tmp/references_workset.json
```
- 必须提供的参数 / payload：
  - 无业务 payload；本步只读标准化文本与 `references_scope`
- 各输出字段含义：
  - 本步默认按行切分；若单行里明显存在第二条文献起点，脚本会在该行内部继续 split；若像跨行续写，只会标记为 suspect block，不会自动合并
  - `workset_path`：完整 references workset 导出路径；每个条目带 `patterns[]`
  - `review_path`：轻量审阅视图路径；包含 block 级审阅信息与条目级候选摘要
  - `stored_reference_entries`：本次切分出的 raw 条目数量
  - `stored_reference_candidates`：本次生成的 candidate 总数
  - `entry_style`：本次 references 著录风格，可能为 `numeric` / `author-year` / `mixed`
  - `split_mode`：当前 deterministic splitting 策略；本项目固定为 `line-first`
  - `requires_split_review`：是否需要先执行条目边界复核
  - `suspect_blocks`：脚本认为边界仍不稳定、需要局部复核的 block 列表
  - `warnings`：编号异常、pattern 歧义、title 边界可疑等 warning
- 最小合法示例：
```bash
python scripts/stage_runtime.py prepare_references_workset --out /tmp/references_workset.json
```
- 完成后应该看到的 gate 结果：
  - 若 `requires_split_review=false`：`next_action` 应推进为 `persist_references`
  - 若 `requires_split_review=true`：`next_action` 应推进为 `persist_reference_entry_splits`

### 6. `persist_reference_entry_splits`

- 何时执行：
  - 只有当 `prepare_references_workset` 返回 `requires_split_review=true`，且 gate 返回 `persist_reference_entry_splits`
- 调用命令：
```bash
python scripts/stage_runtime.py persist_reference_entry_splits --payload-file /tmp/reference_entry_splits.json
```
- 必须提供的参数 / payload：
  - `blocks`
- 各 payload 字段含义：
  - `blocks[*].block_index`：当前需要复核的 suspect block 编号；只能来自 gate 返回的 `suspect_blocks`
  - `blocks[*].resolution`：当前 block 的边界决策，只允许 `split` / `keep` / `merge`
  - `blocks[*].entries`：复核后的 raw entry 列表；只能调整边界，不得改写文本内容
- 最小合法示例：
```json
{
  "blocks": [
    {
      "block_index": 11,
      "resolution": "split",
      "entries": [
        "Li, C.; Xu, C.; Cui, Z.; Wang, D.; Zhang, T.; and Yang, J. 2020. Feature-Attentioned Object Detection in Remote Sensing Imagery. In 2020 IEEE International Conference on Image Processing (ICIP), 3886–3890.",
        "Li, F.; Zhang, H.; Xu, H.; Liu, S.; Zhang, L.; Ni, L. M.; and Shum, H.-Y. 2023a. Mask dino: Towards a unified transformer-based framework for object detection and segmentation. In Proceedings of the IEEE/CVF conference on computer vision and pattern recognition, 3041–3050."
      ]
    }
  ]
}
```
- 完成后应该看到的 gate 结果：
  - `next_action` 应推进为 `persist_references`

### 7. `persist_references`

- 何时执行：
  - `prepare_references_workset` 成功且不需要 split review，或 `persist_reference_entry_splits` 成功后，且 gate 返回 `persist_references`
- 调用命令：
```bash
python scripts/stage_runtime.py persist_references --payload-file /tmp/references_payload.json
```
- 必须提供的参数 / payload：
  - `items`
- 各 payload 字段含义：
  - `items[*].entry_index`：要 refine 的原始条目编号
  - `items[*].selected_pattern`：从 workset 候选中显式选中的 `pattern`
  - `items[*].author`：refine 后的完整作者数组；若 `pattern_candidate.author_candidates` 已给出稳定作者边界，就必须直接复用该边界，不得再次把 `Al-Rfou, R.` 之类作者拆成 `["Al-Rfou", "R."]`
  - `items[*].title`：refine 后的标题；不得以前导逗号、句点、分号或冒号开头
  - `items[*].year`：优先取条目末尾出版年份；不要误取 arXiv 编号前缀
  - `items[*].raw`：对应原始 references 条目文本
  - `items[*].confidence`：对该条最终结构化结果的置信度
- 最小合法示例：
```json
{
  "items": [
    {
      "entry_index": 10,
      "selected_pattern": "authors_colon_title_in_year",
      "author": ["Gu, J.", "Bradbury, J.", "Xiong, C.", "Li, V.O.", "Socher, R."],
      "title": "Non-autoregressive neural machine translation",
      "year": 2018,
      "raw": "[11] Gu, J., Bradbury, J., Xiong, C., Li, V.O., Socher, R.: Non-autoregressive neural machine translation. In: ICLR (2018)",
      "confidence": 0.9
    }
  ]
}
```
- 作者边界合法/非法对照：
  - 合法：`["Al-Rfou, R.", "Choe, D.", "Constant, N.", "Guo, M.", "Jones, L."]`
  - 非法：`["Al-Rfou", "R.", "Choe", "D.", "Constant", "N.", "Guo", "M.", "Jones", "L."]`
- 完成后应该看到的 gate 结果：
  - `next_action` 应推进为 `prepare_citation_workset`
### 8. `prepare_citation_workset`

- 何时执行：
  - `persist_references` 成功后，且 gate 返回 `prepare_citation_workset`
- 调用命令：
```bash
python scripts/stage_runtime.py prepare_citation_workset [--out /tmp/workset.json]
```
- 必须提供的参数 / payload：
  - 无业务 payload；本步只读前序已写入的 `citation_scope`、标准化文本和 `reference_items`
- 各输出字段含义：
  - `scope`：本次实际使用的 citation 范围
  - `scope_source`：范围来源
  - `scope_decision`：范围选择与 fallback 说明
  - `resolved_items`：已成功聚合的 workset 数量
  - `unresolved_mentions`：无法稳定映射的 mention 数量
  - `filtered_false_positive_mentions`：被去噪规则过滤掉的图片链接、URL、资源路径或日期型假阳性数量
  - `review_path`：轻量审阅视图路径，只保留 `ref_index/title/mention_count/snippets`
- 最小合法示例：
```bash
python scripts/stage_runtime.py prepare_citation_workset --out /tmp/workset.json
```
- 完成后应该看到的 gate 结果：
  - `next_action` 应推进为 `persist_citation_semantics`

### 9. `persist_citation_semantics`

- 何时执行：
  - `prepare_citation_workset` 成功后，且 gate 返回 `persist_citation_semantics`
- 调用命令：
```bash
python scripts/stage_runtime.py persist_citation_semantics --payload-file /tmp/citation_semantics.json
```
- 必须提供的参数 / payload：
  - `items`
- 各 payload 字段含义：
  - `items[*].ref_index`：对应哪条 citation workset item
  - `items[*].function`：条目级语义类别
  - `items[*].topic`：这篇文献在当前综述范围里代表的主题、路线或对象
  - `items[*].usage`：原文为什么在这里引用它，用它支撑什么论证
  - `items[*].keywords`：2-5 个短词组，提炼该文献在当前综述范围中的任务、方法、对象或路线；不能把标题整句原样抄进来
  - `items[*].summary`：该参考文献在当前 scope 中的具体作用总结，必须先写“本文如何使用它”，不能只写泛化功能标签
  - `items[*].is_key_reference`：这篇文献是否属于当前范围里必须点出的关键文献
  - `items[*].confidence`：本条语义判断的置信度
- 最小合法示例：
```json
{
  "items": [
    {
      "ref_index": 12,
      "function": "historical",
      "topic": "早期注意力机制",
      "usage": "原文用它交代 transformer 之前的注意力思想来源，作为技术谱系起点。",
      "keywords": ["attention", "pre-transformer", "historical lineage"],
      "summary": "该工作被用来追溯 transformer 之前的注意力思想来源，帮助原文把自身方法放回更早的技术谱系中。",
      "is_key_reference": true,
      "confidence": 0.86
    }
  ]
}
```
- 完成后应该看到的 gate 结果：
  - `next_action` 应推进为 `persist_citation_timeline`

### 10. `persist_citation_timeline`

- 何时执行：
  - `persist_citation_semantics` 成功后，且 gate 返回 `persist_citation_timeline`
- 调用命令：
```bash
python scripts/stage_runtime.py persist_citation_timeline --payload-file /tmp/citation_timeline.json
```
- 必须提供的参数 / payload：
  - `timeline`
- 各 payload 字段含义：
  - `timeline.early` / `timeline.mid` / `timeline.recent`：时间线的三个固定时间段
  - `timeline.*.summary`：该时间段在当前综述范围内的研究脉络总结
  - `timeline.*.ref_indexes`：落入该时间段的 `ref_index` 列表
- 最小合法示例：
```json
{
  "timeline": {
    "early": {
      "summary": "早期工作主要奠定了基础建模思想与任务定义。",
      "ref_indexes": [2, 8]
    },
    "mid": {
      "summary": "中期工作把这些思想推向更成熟的检测与匹配路线。",
      "ref_indexes": [15, 24]
    },
    "recent": {
      "summary": "近期工作则更直接地收束到本文所处的方法脉络。",
      "ref_indexes": [38]
    }
  }
}
```
- 完成后应该看到的 gate 结果：
  - `next_action` 应推进为 `persist_citation_summary`

### 11. `persist_citation_summary`

- 何时执行：
  - `persist_citation_timeline` 成功后，且 gate 返回 `persist_citation_summary`
- 调用命令：
```bash
python scripts/stage_runtime.py persist_citation_summary --payload-file /tmp/citation_summary.json
```
- 必须提供的参数 / payload：
  - `summary`
  - `basis`
- 各 payload 字段含义：
  - `summary`：对当前 citation scope 内整体引文组织方式的全局自然语言总结；必须围绕原文如何使用这些文献来组织研究脉络，而不是做功能占比统计
  - `basis.research_threads`：本段综述串起的 2-4 条研究脉络
  - `basis.argument_shape`：原文组织这些文献的 2-4 个叙述动作，例如先铺背景、再对比主流范式、最后引出本文路线
  - `basis.key_ref_indexes`：当前范围内最关键的 1-5 个 `ref_index`；renderer 会据此生成“关键文献”小节
- 最小合法示例：
```json
{
  "summary": "本节先用早期注意力与序列建模工作铺出技术背景，再把直接集合预测与基于后处理的检测路线并置比较，最后借几篇关键 transformer 与匹配式检测文献把本文的方法路线明确出来。",
  "basis": {
    "research_threads": [
      "从早期 attention / seq2seq 到 transformer 的建模脉络",
      "从依赖 NMS 的检测器到直接集合预测路线的演进"
    ],
    "argument_shape": [
      "先铺技术背景",
      "再比较主流检测范式",
      "最后引出本文路线"
    ],
    "key_ref_indexes": [2, 15, 38]
  }
}
```
- 完成后应该看到的 gate 结果：
  - `next_action` 应推进为 `render_and_validate`

### 12. `render_and_validate --mode render`

- 何时执行：
  - `persist_citation_summary` 成功后，且 gate 返回 `render_and_validate`
- 调用命令：
```bash
python scripts/stage_runtime.py render_and_validate --mode render
```
- 必须提供的参数 / payload：
  - 无；正式发布路径不接受外部业务 payload
- 各输出字段含义：
  - `digest_path`：最终 digest 文件路径
  - `references_path`：最终 references 文件路径
  - `citation_analysis_path`：最终 citation analysis JSON 路径
  - `citation_analysis_report_path`：可选 Markdown 报告路径
  - `literature-digest.result.json`：render 脚本把最终 stdout JSON 同步镜像到当前工作目录的固定结果文件
- 最小合法示例：
```bash
python scripts/stage_runtime.py render_and_validate --mode render
```
- 成功态 stdout JSON 示例：
```json
{
  "digest_path": "/abs/path/digest.md",
  "references_path": "/abs/path/references.json",
  "citation_analysis_path": "/abs/path/citation_analysis.json",
  "citation_analysis_report_path": "/abs/path/citation_analysis.md",
  "provenance": {
    "generated_at": "2026-03-31T09:00:00Z",
    "input_hash": "sha256:0123456789abcdef",
    "model": "gpt-5.4"
  },
  "warnings": [],
  "error": null
}
```
- 同步写出的固定结果文件：
  - 当前工作目录下固定写出 `./literature-digest.result.json`
  - 文件内容与上面的 stdout JSON 完全一致
- 失败态 stdout JSON 示例：
```json
{
  "digest_path": "",
  "references_path": "",
  "citation_analysis_path": "",
  "provenance": {
    "generated_at": "",
    "input_hash": "",
    "model": ""
  },
  "warnings": [],
  "error": {
    "code": "citation_report_failed",
    "message": "render mode failed before validation: runtime_inputs.source_path missing"
  }
}
```
- 输出路径规则：
  - render 只读取 DB 中的 `output_dir`
  - 若库中缺失 `output_dir`，脚本回退到当前工作目录
  - render 阶段不再接受目录覆盖参数
- 完成后应该看到的 gate 结果：
  - `current_stage` 进入 `stage_7_completed`
  - `artifact_registry` 中的公开产物路径都已登记

阶段性最低输出约束：

- digest 阶段不得提交近最终 Markdown，只能提交结构化槽位
- citation 语义阶段不得重做 mention-reference join，只能消费 DB 中已有 `citation_workset_items`
- stage 5 的 `prepare_citation_workset -> persist_citation_semantics -> persist_citation_timeline -> persist_citation_summary` 必须通过对应脚本动作逐步完成，不能手工写 SQLite 代替
- citation 阶段不得直接写 `report_md`
- `citation_analysis.summary` 是必填全局字段
- `persist_citation_semantics.items[*]` 必须包含 `topic`、`usage`、`keywords`、`is_key_reference`
- `persist_citation_timeline.timeline` 必须包含 `early`、`mid`、`recent`
- `persist_citation_timeline.timeline.*.ref_indexes` 与 `persist_citation_summary.basis.key_ref_indexes` 都必须引用已持久化到 `citation_items` 的 `ref_index`
- author-year 型映射按 `year + first-author surname aliases` 匹配，而不是简单取作者字符串首 token
- 对 author-year 型引用，renderer 会按首次出现顺序合成 `[AY-k]`，避免与原始 numeric `[n]` 冲突

## 按需读取附录

执行当前阶段动作时，只按 gate 返回的 `instruction_refs` 读取以下运行时文档。它们是增强质量的附录，不是启动必读材料：

- [gate_runtime_interface.md](references/gate_runtime_interface.md)
  - `gate_runtime.py` 的 CLI、stdout payload、`next_action`、`instruction_refs`、`command_example`、`sql_examples` 与 exit code
- [stage_runtime_interface.md](references/stage_runtime_interface.md)
  - `stage_runtime.py` 的 subcommand、参数、payload 输入方式、字段说明、合法/非法示例、stdout 形状与副作用
- [step_01_bootstrap_and_source.md](references/step_01_bootstrap_and_source.md)
  - 输入读取、协议探测、标准化、副产物与 `bootstrap_runtime_db` / `normalize_source` 的细则
- [step_02_outline_and_scopes.md](references/step_02_outline_and_scopes.md)
  - 结构化骨架、references/citation scope 决策与 payload 约束
- [step_03_digest_generation.md](references/step_03_digest_generation.md)
  - digest 细则、中英文固定标题要求、`digest_slots + section_summaries` 的写库契约
- [step_04_references_extraction.md](references/step_04_references_extraction.md)
  - references 抽取细则、抽取原则、5 个完整示例与编号异常处理
- [step_05_citation_pipeline.md](references/step_05_citation_pipeline.md)
  - citation analysis 细则、workset-first 流水线、支持体例、边界情况、payload 约束与 summary 规则
- [step_06_render_and_validate.md](references/step_06_render_and_validate.md)
  - 主发布路径、辅助校验路径、输出结构与最终渲染约束
- [sql_playbook.md](references/sql_playbook.md)
  - gate SQL 示例背景、常见修复查询与 repair 路径
- [failure_recovery.md](references/failure_recovery.md)
  - DB 旧状态、gate 卡住、可删除重跑文件与禁止手改项
- [bibliography_formats.md](references/bibliography_formats.md)
  - 参考文献体例识别与切分启发

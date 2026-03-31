# Stage Runtime Interface

本文件是 `scripts/stage_runtime.py` 的接口手册。基础参数名称与字段语义统一按 `SKILL.md` 的“参数词表（全项目统一）”理解；这里只补脚本调用、payload 结构和错误边界。

## 角色

`stage_runtime.py` 是唯一阶段动作入口。它负责：

- 输入协议探测与标准化
- SQLite 持久化
- citation workset 准备
- 最终渲染与输出校验

它不负责决定下一步执行什么；下一动作只能由 `scripts/gate_runtime.py` 返回。

## 总调用形式

```bash
python scripts/stage_runtime.py <subcommand> [args...]
```

通用规则：

- stdout 只输出一个 JSON 对象
- exit code `0` 表示成功
- exit code `2` 表示当前动作失败，需要重新跑 gate 或进入 repair
- 结构化 payload 优先通过 `--payload-file FILE` 传入；未提供时脚本才从 stdin 读取 JSON
- 大 payload 默认通过 `--payload-file` 传入；尤其在 Windows 下，避免拼接超长内联 JSON 命令

## 主路径与辅助工具的边界

### 主路径 subcommand

- `bootstrap_runtime_db`
- `normalize_source`
- `persist_outline_and_scopes`
- `persist_digest`
- `prepare_references_workset`
- `persist_reference_entry_splits`
- `persist_references`
- `prepare_citation_workset`
- `persist_citation_semantics`
- `persist_citation_timeline`
- `persist_citation_summary`
- `render_and_validate --mode render`

主路径强约束：

- 一旦某项信息已由前序阶段写入 DB，后续主路径 subcommand 不得再通过 CLI / JSON 重传或覆盖
- 例如：
  - `normalize_source` 只能读 `source_path`
  - `prepare_references_workset` 只能读前序已确定的 `references_scope`
  - `prepare_citation_workset` 只能读前序已确定的 `citation_scope`
  - `render_and_validate --mode render` 只能读 DB 内容，不能显式指定 `source_path`；正式输出目录来自 DB 中的 `output_dir`

### 辅助工具 subcommand

- `export_citation_workset`
- `render_and_validate --mode fix`
- `render_and_validate --mode check`

这些工具不属于 gate 主路径，不应出现在 gate 的 `next_action` 中。

## `bootstrap_runtime_db`

### 命令

```bash
python scripts/stage_runtime.py bootstrap_runtime_db \
  [--db-path PATH] \
  --source-path PATH \
  [--language LANG] \
  [--output-dir DIR] \
  [--input-hash HASH] \
  [--generated-at ISO8601] \
  [--model MODEL]
```

### 参数

- `--source-path`
  - 必填。唯一内容来源文件路径。
- `--language`
  - 可选。输出语言；缺省时脚本应回退默认值。
- `--input-hash`
  - 可选。若不提供，由脚本自行计算。
- `--output-dir`
  - 可选。正式公开产物目录；若不提供，脚本把当前工作目录写入 DB。
- `--generated-at`
  - 可选。若不提供，由脚本生成 UTC 时间。
- `--model`
  - 可选。写入 provenance。

### 最小合法示例

```bash
python scripts/stage_runtime.py bootstrap_runtime_db \
  --source-path "/abs/path/paper.md" \
  --language "zh-CN" \
  --output-dir "/abs/path/artifacts"
```

### 典型非法示例

```bash
python scripts/stage_runtime.py bootstrap_runtime_db
```

原因：缺少 `--source-path`。

### 成功输出

```json
{
  "db_path": "/abs/path/.literature_digest_tmp/literature_digest.db",
  "output_dir": "/abs/path/artifacts",
  "error": null
}
```

### 常见失败原因

- `source_path` 不存在或不可读
- 传入非法 `language`，但脚本未做回退

## `normalize_source`

### 命令

```bash
python scripts/stage_runtime.py normalize_source \
  [--db-path PATH] \
  [--out-md PATH] \
  [--out-meta PATH] \
  [--persist-db-only]
```

### 输入方式

- 不接受业务 payload
- 只读取 bootstrap 已写入的 `source_path` 与 `language`
- 本步只接受 `--out-md`、`--out-meta`、`--persist-db-only` 这三个可选 CLI 参数

### 参数含义

- `--out-md`
  - 可选。把标准化文本物化到指定路径。
- `--out-meta`
  - 可选。把标准化元数据物化到指定路径。
- `--persist-db-only`
  - 可选。只写 DB，不物化副产物。

### 最小合法示例

```bash
python scripts/stage_runtime.py normalize_source
```

### 典型非法示例

```bash
python scripts/stage_runtime.py normalize_source --source-path "/tmp/paper.md"
```

原因：主路径不允许在本步重新传 `source_path`。

### 成功输出

```json
{
  "normalized_source_length": 12345,
  "warnings": [],
  "error": null
}
```

### 常见失败原因

- DB 中缺少 bootstrap 产生的输入上下文
- 源文件既不是可解析 PDF，也不是可读 UTF-8 文本

## `persist_outline_and_scopes`

### 命令

```bash
python scripts/stage_runtime.py persist_outline_and_scopes \
  [--db-path PATH] \
  [--payload-file FILE]
```

### 支持的输入方式

- `--payload-file FILE`
- stdin JSON

### Payload 顶层结构

```json
{
  "outline_nodes": [],
  "references_scope": {},
  "citation_scope": {}
}
```

### 字段说明

- `outline_nodes`
  - 必填。章节骨架数组。
  - 每项唯一推荐最小字段：
    - `node_id`
    - `heading_level`
    - `title`
    - `line_start`
    - `line_end`
    - `parent_node_id`
- `references_scope`
  - 必填。references 抽取范围定义，供 `prepare_references_workset` 直接使用。
  - 唯一合法形状：
    - `section_title`
    - `line_start`
    - `line_end`
    - `metadata`
- `citation_scope`
  - 必填。citation workset 抽取范围定义，供 `prepare_citation_workset` 直接使用。
  - 唯一合法形状：
    - `section_title`
    - `line_start`
    - `line_end`
    - `metadata`

### 最小合法示例

```json
{
  "outline_nodes": [
    {
      "node_id": "n1",
      "heading_level": 1,
      "title": "Introduction",
      "line_start": 1,
      "line_end": 20,
      "parent_node_id": null
    },
    {
      "node_id": "n2",
      "heading_level": 1,
      "title": "Related Work",
      "line_start": 21,
      "line_end": 48,
      "parent_node_id": null
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
      "selection_reason": "综述职责集中在前两章",
      "covered_sections": ["Introduction", "Related Work"]
    }
  }
}
```

### 典型非法示例

```json
{
  "outline_nodes": ["Introduction", "Related Work"],
  "references_scope": {"section_title": "References", "line_start": 10, "line_end": 20, "metadata": {}},
  "citation_scope": {"section_title": "Introduction", "line_start": 1, "line_end": 9, "metadata": {}}
}
```

原因：`outline_nodes` 不能只是标题字符串数组；每个节点都必须提供运行时要求的最小字段。

### 成功输出

```json
{
  "stored_outline_nodes": 2,
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
      "selection_reason": "综述职责集中在前两章",
      "covered_sections": ["Introduction", "Related Work"]
    }
  },
  "error": null
}
```

### 常见失败原因

- `citation_scope` 缺少可执行的范围信息
- `outline_nodes` 无法支持后续章节顺序判断

## `persist_digest`

### 命令

```bash
python scripts/stage_runtime.py persist_digest \
  [--db-path PATH] \
  [--payload-file FILE]
```

### 支持的输入方式

- `--payload-file FILE`
- stdin JSON

### Payload 顶层结构

```json
{
  "digest_slots": {},
  "section_summaries": []
}
```

### 字段说明

- `digest_slots`
  - 必填。固定 5 个 digest 槽位：
    - `tldr.paragraphs`
    - `research_question_and_contributions.research_question`
    - `research_question_and_contributions.contributions`
    - `method_highlights.items`
    - `key_results.items`
    - `limitations_and_reproducibility.items`
- `section_summaries`
  - 必填。章节摘要数组。
  - `source_heading`：对应原文章节标题。
  - `items`：该章节的要点列表。

### 最小合法示例

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

### 典型非法示例

```json
{
  "sections": [
    {"heading": "## TL;DR", "body_md": "..."}
  ]
}
```

原因：旧 `sections[]` 接口已废弃。

### 成功输出

```json
{
  "stored_digest_slots": 5,
  "stored_section_summaries": 1,
  "error": null
}
```

### 常见失败原因

- 固定槽位缺失
- `section_summaries` 顺序或结构不合法

## `prepare_references_workset`

### 命令

```bash
python scripts/stage_runtime.py prepare_references_workset \
  [--db-path PATH] \
  [--out PATH] \
  [--persist-db-only]
```

### 支持的输入方式

- 不接受业务 payload
- 只依赖前序已入库决策：标准化文本与 `references_scope`
- deterministic splitting 固定采用 `line-first`：先按行切，单行内再做 inline split；疑似跨行续写只会进入 review，不会自动合并

### 输出字段说明

- `workset_path`
  - 完整 workset 导出路径；每个 entry 带 `patterns[]`
- `review_path`
  - 轻量审阅视图路径；只保留 `entry_index`、`detected_ref_number`、`raw`、`pattern_summaries`
- `stored_reference_entries`
  - 写入 `reference_entries` 的 raw 条目数
- `stored_reference_candidates`
  - 写入 `reference_parse_candidates` 的候选总数
- `warnings`
  - 编号异常、pattern 歧义、title 边界可疑等 warning 列表
- `entry_style`
  - 当前 references workset 的著录风格：`numeric` / `author-year` / `mixed`
- `split_mode`
  - 当前 deterministic splitting 策略；固定为 `line-first`
- `requires_split_review`
  - 若为 `true`，说明 deterministic splitting 之后仍存在边界存疑的 block，下一步必须先执行 `persist_reference_entry_splits`
- `suspect_blocks`
  - 仍需要边界复核的 block 及原因说明
  - 每个 block 至少带 `block_index`、`source_text`、`line_start`、`line_end`、`reasons`、`proposed_entries`、`suspicion_kind`

### 最小合法示例

```bash
python scripts/stage_runtime.py prepare_references_workset --out /tmp/references_workset.json
```

### 典型非法示例

```bash
python scripts/stage_runtime.py prepare_references_workset --payload-file /tmp/references_payload.json
```

原因：本步不接受业务 payload，references workset 必须完全由脚本从 DB 决策生成。

### 成功输出

```json
{
  "stored_reference_entries": 1,
  "stored_reference_candidates": 2,
  "numbering_warnings": [],
  "warnings": ["reference_pattern_ambiguous: entry_index=0"],
  "workset_path": "/tmp/references_workset.json",
  "review_path": "/tmp/references_workset_review.json",
  "entry_style": "numeric",
  "split_mode": "line-first",
  "grouping_suspect_count": 0,
  "requires_split_review": false,
  "suspect_blocks": [],
  "error": null
}
```

### 常见失败原因

- `references_scope` 缺失或越界
- 标准化文本中 references 区块为空
- 误以为脚本只会保留一个“最像”的 pattern
- author-year bibliography 中多条著录仍被 grouped 成单条 entry，但未先进入 split review

## `persist_reference_entry_splits`

### 命令

```bash
python scripts/stage_runtime.py persist_reference_entry_splits \
  [--db-path PATH] \
  [--payload-file FILE] \
  [--out PATH] \
  [--persist-db-only]
```

### 支持的输入方式

- `--payload-file FILE`
- stdin JSON

### Payload 顶层结构

```json
{
  "blocks": []
}
```

### 字段说明

- `blocks`
  - 必填。仅包含当前 `suspect_blocks` 的局部复核结果。
- `blocks[*].block_index`
  - 必填。必须对应当前 workset 返回的 suspect block。
- `blocks[*].resolution`
  - 必填。只允许 `split` / `keep` / `merge`。
- `blocks[*].entries`
  - 必填。复核后的 raw entry 列表。
  - 这些文本只能调整边界，不能改写原文内容。
  - 全部 `blocks[*].entries[]` 连接后的规范化文本必须与对应 suspect block 的 `source_text` 完全一致。

### 最小合法示例

```json
{
  "blocks": [
    {
      "block_index": 3,
      "resolution": "split",
      "entries": [
        "Joshua Ainslie, Santiago Ontanon, Chris Alberti, Philip Pham, Anirudh Ravula, and Sumit Sanghai. Etc: Encoding long and structured data in transformers. arXiv preprint arXiv:2004.08483, 2020.",
        "Iz Beltagy, Matthew E Peters, and Arman Cohan. Longformer: The long-document transformer. arXiv preprint arXiv:2004.05150, 2020."
      ]
    }
  ]
}
```

### 典型非法示例

```json
{
  "blocks": [
    {
      "block_index": 3,
      "resolution": "split",
      "entries": [
        "Joshua Ainslie, Santiago Ontanon, Chris Alberti, Philip Pham, Anirudh Ravula, and Sumit Sanghai. Etc: Encoding long and structured data in transformers. arXiv preprint arXiv:2004.08483, 2020."
      ]
    }
  ]
}
```

原因：`resolution=split` 但只提交了一个 entry，脚本会以 `reference_entry_splitting_failed` 拒绝。

### 成功输出

```json
{
  "stored_reference_entries": 2,
  "stored_reference_candidates": 6,
  "warnings": [],
  "workset_path": "/tmp/references_workset.json",
  "review_path": "/tmp/references_workset_review.json",
  "entry_style": "author-year",
  "grouping_suspect_count": 0,
  "requires_split_review": false,
  "error": null
}
```

### 常见失败原因

- 跳过条目、乱序或改写 raw 文本
- 复核后仍把多条著录 grouped 在一个 `raw` 里
- 在这一步就开始抽 `author` / `title` / `year`

## `persist_references`

### 命令

```bash
python scripts/stage_runtime.py persist_references \
  [--db-path PATH] \
  [--payload-file FILE]
```

### 支持的输入方式

- `--payload-file FILE`
- stdin JSON

### Payload 顶层结构

```json
{
  "items": []
}
```

### 字段说明

- `items`
  - 必填。最终结构化参考文献项数组。
  - 每项至少应包含：`entry_index`、`selected_pattern`、`author`、`title`、`year`、`raw`、`confidence`。
  - `selected_pattern` 必须能在 `reference_parse_candidates` 中找到对应候选。
  - 若所选 `pattern_candidate.author_candidates` 已给出稳定作者边界，则 `author` 必须保持同级边界；脚本只允许轻微规范化，不允许再次拆开单个作者。
  - `ref_index` 由脚本按 `entry_index` 稳定生成，不需要 agent 单独填写。
  - `year` 优先取条目末尾出版年份，不要误取 arXiv 编号前缀。

### 最小合法示例

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

### 典型非法示例

```json
{
  "items": [
    {
      "entry_index": 0,
      "selected_pattern": "authors_colon_title_in_year",
      "author": ["Al-Rfou", "R.", "Choe", "D."],
      "title": "Character-level language modeling with deeper self-attention",
      "year": 2019,
      "raw": "1. Al-Rfou, R., Choe, D.: Character-level language modeling with deeper self-attention. In: AAAI Conference on Artificial Intelligence (2019)",
      "confidence": 0.92
    }
  ]
}
```

原因：`author` 把已稳定的 `author_candidates` 再次拆碎，脚本会以 `reference_author_refinement_invalid` 失败。

### 成功输出

```json
{
  "stored_reference_items": 1,
  "warnings": [],
  "error": null
}
```

### 常见失败原因

- 把 `pattern_candidate.author_candidates` 再次拆成“姓 + 缩写”碎片
- `selected_pattern` 缺失或与 prepared candidate 不匹配
- `title` 以前导标点开头
- 把 arXiv 标识中的数字前缀误判成出版年

## `prepare_citation_workset`

### 命令

```bash
python scripts/stage_runtime.py prepare_citation_workset \
  [--db-path PATH] \
  [--out PATH] \
  [--persist-db-only]
```

### 支持的输入方式

- 不接受业务 payload
- 只依赖前序已入库决策：标准化文本、`citation_scope`、`reference_items`
- 本步只接受 `--out` 与 `--persist-db-only` 这两个可选 CLI 参数

### 输出字段说明

- `workset_path`
  - 可选导出文件路径。
- `scope`
  - 本次实际使用的 citation 范围。
- `scope_source`
  - 范围来源。
- `scope_decision`
  - 范围选择与 fallback 说明。
- `resolved_items`
  - 已成功聚合成 workset 的条目数量。
- `unresolved_mentions`
  - 无法稳定映射的 mention 数量。
- `filtered_false_positive_mentions`
  - 被图片链接、URL、资源路径、图片/PDF 尾缀或日期型字符串过滤掉的假阳性数量。
- `review_path`
  - 轻量审阅视图路径，只保留 `ref_index`、`title`、`mention_count`、`snippets`。

### 最小合法示例

```bash
python scripts/stage_runtime.py prepare_citation_workset --out /tmp/workset.json
```

### 典型非法示例

```bash
python scripts/stage_runtime.py prepare_citation_workset --scope-file /tmp/scope.json
```

原因：主路径不允许在本步重新传 `citation_scope`。

### 成功输出

```json
{
  "workset_path": "/tmp/workset.json",
  "review_path": "/tmp/workset_review.json",
  "scope": {
    "section_title": "Introduction + Related Work",
    "line_start": 1,
    "line_end": 48
  },
  "scope_source": "db",
  "scope_decision": {
    "selection_reason": "沿用 stage 2 已确定的范围",
    "covered_sections": ["Introduction", "Related Work"],
    "fallback_from": null,
    "fallback_reason": ""
  },
  "resolved_items": 14,
  "unresolved_mentions": 2,
  "filtered_false_positive_mentions": 3,
  "error": null
}
```

### 常见失败原因

- DB 中缺少 `citation_scope`
- 试图在本步重开范围决策
- 忽略轻量审阅视图，反复让模型消费完整大 payload

## `persist_citation_semantics`

### 命令

```bash
python scripts/stage_runtime.py persist_citation_semantics \
  [--db-path PATH] \
  [--payload-file FILE]
```

### 支持的输入方式

- `--payload-file FILE`
- stdin JSON

### Payload 顶层结构

```json
{
  "items": []
}
```

### 字段说明

- `items[*].ref_index`
  - 必填。指向一条 `citation_workset_item`。
- `items[*].function`
  - 必填。条目级引文功能类别；脚本会校验枚举。
- `items[*].topic`
  - 必填。该文献在当前综述范围内代表的主题、路线或对象。
- `items[*].usage`
  - 必填。原文为什么在这里引用它，用于做什么论证。
- `items[*].keywords`
  - 必填。非空短词组数组；脚本会 trim、去空、去重、保序。不能把标题整句原样拆词。
- `items[*].summary`
  - 必填。该参考文献在当前 citation scope 中的作用总结；必须先写“原文如何使用它”，不能只写泛化标签同义改写。
- `items[*].is_key_reference`
  - 必填。是否属于当前综述范围内需要在全局总结中显式点出的关键文献。
- `items[*].confidence`
  - 必填。0~1 置信度。

### 最小合法示例

```json
{
  "items": [
    {
      "ref_index": 12,
      "function": "historical",
      "topic": "早期注意力机制",
      "usage": "原文借它回溯 transformer 之前的注意力思想来源，为后续 transformer 论述铺垫背景。",
      "keywords": ["attention", "historical lineage", "pre-transformer"],
      "summary": "该工作被用来交代 transformer 之前的注意力思想来源，帮助原文把自身方法放回更早的技术谱系中。",
      "is_key_reference": true,
      "confidence": 0.86
    }
  ]
}
```

### 典型非法示例

```json
{
  "items": [
    {
      "ref_index": 12,
      "function": "background",
      "summary": "……",
      "confidence": 0.86
    }
  ]
}
```

原因：缺少 `topic`、`usage`、`keywords`、`is_key_reference`，不满足本步 payload 结构。

### 成功输出

```json
{
  "stored_citation_items": 1,
  "error": null
}
```

### 常见失败原因

- 缺少 `ref_index`
- `function` 不合法且未被脚本正常归一
- `topic` / `usage` 为空
- `keywords` 为空、包含空字符串，或被写成整句
- `is_key_reference` 不是布尔值
- 把不同文献都写成“提供背景支持/作为方法对比”式的批量套话
- 传入了不属于本步 payload 的额外字段

## `persist_citation_timeline`

### 命令

```bash
python scripts/stage_runtime.py persist_citation_timeline \
  [--db-path PATH] \
  [--payload-file FILE]
```

### 支持的输入方式

- `--payload-file FILE`
- stdin JSON

### Payload 顶层结构

```json
{
  "timeline": {
    "early": { "summary": "", "ref_indexes": [] },
    "mid": { "summary": "", "ref_indexes": [] },
    "recent": { "summary": "", "ref_indexes": [] }
  }
}
```

### 字段说明

- `timeline.early` / `timeline.mid` / `timeline.recent`
  - 必填。固定三段时间线 bucket。
- `timeline.*.summary`
  - 必填。该时段在当前综述范围内的研究脉络总结。
- `timeline.*.ref_indexes`
  - 必填。落入该时间段的 `ref_index` 数组。
- bucket 边界由 agent 判断，不使用固定年份阈值。
- 所有有稳定年份的 citation items 必须恰好进入一个 bucket。
- 无稳定年份的条目允许不进入 timeline；脚本会记录 `citation_timeline_missing_year` warning。

### 最小合法示例

```json
{
  "timeline": {
    "early": {
      "summary": "早期工作主要奠定了基础建模思想与任务定义。",
      "ref_indexes": [2, 8]
    },
    "mid": {
      "summary": "中期工作把这些思想推进到更成熟的检测与匹配路线。",
      "ref_indexes": [15, 24]
    },
    "recent": {
      "summary": "近期工作更直接收束到与本文最接近的路线。",
      "ref_indexes": [38]
    }
  }
}
```

### 典型非法示例

```json
{
  "timeline": {
    "early": { "summary": "early", "ref_indexes": [2] },
    "mid": { "summary": "mid", "ref_indexes": [2] }
  }
}
```

原因：缺少 `recent`；同一 `ref_index` 不允许出现在多个 bucket。

### 成功输出

```json
{
  "stored_citation_timeline": true,
  "warnings": [],
  "error": null
}
```

### 常见失败原因

- 缺少 `early` / `mid` / `recent`
- 同一 `ref_index` 出现在多个 bucket
- 有稳定年份的条目没有进入任何 bucket

## `persist_citation_summary`

### 命令

```bash
python scripts/stage_runtime.py persist_citation_summary \
  [--db-path PATH] \
  [--payload-file FILE]
```

### 支持的输入方式

- `--payload-file FILE`
- stdin JSON

### Payload 顶层结构

```json
{
  "summary": "",
  "basis": {}
}
```

### 字段说明

- `summary`
  - 必填。scope 级自然语言总括，最终会进入 `citation_analysis.json.summary`；必须围绕原文如何使用相关工作来梳理研究脉络，而不是做功能统计。
- `basis`
  - 必填。说明总括依据的结构化对象。
  - `basis.research_threads`
    - 必填。2 条及以上研究脉络。
  - `basis.argument_shape`
    - 必填。2 条及以上原文组织这些文献的叙述动作。
  - `basis.key_ref_indexes`
    - 必填。非空整数数组；每个 `ref_index` 都必须能在当前 `citation_workset_items` 中找到。
- `persist_citation_summary` 只能在 `persist_citation_timeline` 之后执行。

### 最小合法示例

```json
{
  "summary": "本节先铺设 transformer 之前的注意力与序列建模背景，再对比依赖后处理的检测路线与直接集合预测路线，最后把几篇关键文献串成本文方法的直接来路。",
  "basis": {
    "research_threads": [
      "从注意力与 seq2seq 到 transformer 的建模脉络",
      "从依赖后处理的检测器到直接集合预测路线的演进"
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

### 典型非法示例

```json
{
  "basis": {
    "research_threads": ["只有一条线索"]
  }
}
```

原因：缺少必填 `summary`，且 `basis` 结构不完整。

### 成功输出

```json
{
  "stored_citation_summary": true,
  "error": null
}
```

### 常见失败原因

- `summary` 为空字符串
- `basis` 缺少 `research_threads`、`argument_shape` 或 `key_ref_indexes`
- `basis.key_ref_indexes` 引用不存在的 `ref_index`
- timeline 尚未写入
- 把 `summary` 写成背景/基线/对比数量统计
- 把这里写成完整 `report_md`

## `render_and_validate`

### 正式发布路径

#### 命令

```bash
python scripts/stage_runtime.py render_and_validate [--db-path PATH] --mode render
```

#### 输入方式

- 不接受外部业务 payload
- 正式发布只从 DB 派生最终成品
- 正式 render 的写盘目录只读取 `runtime_inputs.output_dir`
- 若库中缺失 `runtime_inputs.output_dir`，回退到当前工作目录
- `citation_analysis.md` / `citation_analysis.json.report_md` 会共同包含由 renderer 生成的“关键文献”与“时间线分析”小节
- numeric 型引用保留原始 `[n]`
- author-year 型引用在最终渲染时按首次出现顺序合成 `[AY-k]`
- `author_year_label` 优先由 `第一作者 + 年份` 派生；缺作者或年份时回退到标题

#### 最小合法示例

```bash
python scripts/stage_runtime.py render_and_validate --mode render
```

#### 典型非法示例

```bash
python scripts/stage_runtime.py render_and_validate --mode render --source-path /tmp/paper.md
```

原因：正式发布路径不允许覆盖输入来源。

```bash
python scripts/stage_runtime.py render_and_validate --mode render --out-dir /abs/path/artifacts
```

原因：正式发布路径不再接受输出目录覆盖；该目录必须在 `bootstrap_runtime_db` 中先写入 DB。

#### 成功输出

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

最终 stdout JSON 的权威示例以本页代码块与 `SKILL.md` 的“核心执行指令”部分为准。

render 还会把同一个 JSON 对象镜像写入当前工作目录下固定文件 `./literature-digest.result.json`。

#### 失败输出示例

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
    "message": "render mode does not accept explicit source/preprocess/stdin/output-dir inputs; render output location is DB-authoritative"
  }
}
```

#### 常见失败原因

- DB 中缺少 digest / references / citation 所需前序数据
- 试图通过 CLI 覆盖正式发布输入来源
- 误以为可以在 render 阶段临时覆盖输出目录

### 辅助工具路径

#### 命令

```bash
python scripts/stage_runtime.py render_and_validate --mode fix [--in FILE] [--source-path PATH] [--out-dir DIR] [--preprocess-artifact FILE]
python scripts/stage_runtime.py render_and_validate --mode check [--in FILE] [--source-path PATH] [--out-dir DIR] [--preprocess-artifact FILE]
```

#### 说明

- 仅作公共 payload 校验与修复辅助工具
- 不属于 gate 主路径

## `export_citation_workset`

### 命令

```bash
python scripts/stage_runtime.py export_citation_workset [--db-path PATH] [--out PATH]
```

### 输入方式

- 不接受业务 payload
- 只读导出已准备好的 citation workset

### 输出字段说明

- `meta`
  - 导出上下文，例如 scope、生成时间、总 mention 数。
- `mentions`
  - 原始 mention 列表。
- `mention_links`
  - mention 到 `ref_index` 的稳定映射。
- `reference_index`
  - 供语义阶段使用的 reference 摘要索引。
- `workset_items`
  - 已聚合好的待分析 workset。
- `review_items`
  - 轻量审阅视图，只保留 `ref_index`、`title`、`mention_count`、`snippets`。
- `unresolved_mentions`
  - 无法稳定映射的 mention 列表。
- `suggested_batches`
  - 基于 workset 的建议批次。

### 最小合法示例

```bash
python scripts/stage_runtime.py export_citation_workset --out /tmp/workset_export.json
```

若提供 `--out`，脚本还会额外写出同目录下的轻量审阅视图，例如 `/tmp/workset_export_review.json`。

### 常见失败原因

- 在尚未执行 `prepare_citation_workset` 时调用导出

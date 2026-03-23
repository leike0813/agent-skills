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
- `persist_references`
- `prepare_citation_workset`
- `persist_citation_semantics`
- `persist_citation_summary`
- `render_and_validate --mode render`

主路径强约束：

- 一旦某项信息已由前序阶段写入 DB，后续主路径 subcommand 不得再通过 CLI / JSON 重传或覆盖
- 例如：
  - `normalize_source` 只能读 `source_path`
  - `prepare_citation_workset` 只能读前序已确定的 `citation_scope`
  - `render_and_validate --mode render` 只能读 DB，不能显式指定 `source_path` 或 `out_dir`

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
- `--generated-at`
  - 可选。若不提供，由脚本生成 UTC 时间。
- `--model`
  - 可选。写入 provenance。

### 最小合法示例

```bash
python scripts/stage_runtime.py bootstrap_runtime_db \
  --source-path "/abs/path/paper.md" \
  --language "zh-CN"
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
- 不再接受 `--source-path`、`--language`

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
  - 必填。references 抽取范围定义，供 `persist_references` 直接使用。
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
  "entries": [],
  "batches": [],
  "items": []
}
```

### 字段说明

- `entries`
  - 必填。原始 references 条目数组。
  - 每项至少应包含：`entry_index`、`raw`。
- `batches`
  - 必填。references 处理批次定义。
  - 每项至少应包含：`batch_index`、`entry_start`、`entry_end`。
- `items`
  - 必填。最终结构化参考文献项数组。
  - 每项至少应包含：`ref_index`、`author`、`title`、`year`、`raw`、`confidence`。
  - 当作者细拆不稳时，`author` 允许保守为单元素数组。
  - `year` 优先取条目末尾出版年份，不要误取 arXiv 编号前缀。

### 最小合法示例

```json
{
  "entries": [
    {"entry_index": 0, "raw": "[1] Smith J. Paper title. 2020."}
  ],
  "batches": [
    {"batch_index": 0, "entry_start": 0, "entry_end": 0}
  ],
  "items": [
    {
      "ref_index": 0,
      "author": ["Smith, J."],
      "title": "Paper title",
      "year": 2020,
      "raw": "[1] Smith J. Paper title. 2020.",
      "confidence": 0.92
    }
  ]
}
```

### 典型非法示例

```json
{
  "items": [
    {"title": "Paper title"}
  ]
}
```

原因：缺少 `entries` / `batches`，且 item 不满足最小字段要求。

### 成功输出

```json
{
  "stored_reference_items": 1,
  "numbering_warnings": [],
  "warnings": [],
  "error": null
}
```

### 常见失败原因

- `items` 缺少 `raw` 或 `confidence`
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
- 不再接受 `--md-path`、`--language`、`--scope-file`、`--scope-start`、`--scope-end`、`--scope-title`

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
- `items[*].summary`
  - 必填。该参考文献在当前 citation scope 中的作用总结。
- `items[*].confidence`
  - 必填。0~1 置信度。

### 最小合法示例

```json
{
  "items": [
    {
      "ref_index": 12,
      "function": "background",
      "summary": "该工作被用来界定问题背景并说明研究起点。",
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
      "confidence": 0.86,
      "mentions": []
    }
  ]
}
```

原因：旧字段 `mentions`、`reference`、`report_md` 已禁止出现在本步 payload 中。

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
- 传入了 `mentions`、`reference`、`report_md` 等旧字段

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
  - 必填。scope 级自然语言总括，最终会进入 `citation_analysis.json.summary`。
- `basis`
  - 可选。说明总括依据的补充结构。

### 最小合法示例

```json
{
  "summary": "本节主要把既有工作分成问题背景、方法对比与数据资源三类，其中背景性引用占主导。",
  "basis": {
    "grouping": ["background", "baseline", "dataset"]
  }
}
```

### 典型非法示例

```json
{
  "basis": {
    "grouping": ["background"]
  }
}
```

原因：缺少必填 `summary`。

### 成功输出

```json
{
  "stored_citation_summary": true,
  "error": null
}
```

### 常见失败原因

- `summary` 为空字符串
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

#### 最小合法示例

```bash
python scripts/stage_runtime.py render_and_validate --mode render
```

#### 典型非法示例

```bash
python scripts/stage_runtime.py render_and_validate --mode render --source-path /tmp/paper.md
```

原因：正式发布路径不允许覆盖输入来源。

#### 成功输出

```json
{
  "digest_path": "/abs/path/digest.md",
  "references_path": "/abs/path/references.json",
  "citation_analysis_path": "/abs/path/citation_analysis.json",
  "citation_analysis_report_path": "/abs/path/citation_analysis.md",
  "warnings": [],
  "error": null
}
```

#### 常见失败原因

- DB 中缺少 digest / references / citation 所需前序数据
- 试图通过 CLI 覆盖正式发布输入

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

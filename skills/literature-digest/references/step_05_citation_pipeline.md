# Step 05: Citation Pipeline

本文件按 `SKILL.md` 的“参数词表（全项目统一）”定义；这里只补 stage 5 的额外约束，不重复定义字段基础含义。

本文件定义 `citation_analysis` 结构、`Citation Analysis（Dynamic Citation Scope）细则`、预处理契约、支持体例、边界情况、阶段失败语义以及 citation 阶段的当前 DB-first 约束。

## citation_analysis 输出格式

`citation_analysis_path` 指向的文件内容必须是 JSON 对象，至少包含：
- `meta`
  - `language`
  - `scope`
- `summary`
- `timeline`
- `items`
- `unmapped_mentions`
- `report_md`

### `items` 数组中条目的最小结构

- `ref_index`
- `ref_number`
- `reference`
- `mentions`
  - `mention_id`
  - `marker`
  - `style`
  - `line_start`
  - `line_end`
  - `snippet`
- `function`
- `topic`
- `usage`
- `keywords`
- `summary`
- `is_key_reference`
- `confidence`

### `report_md` 建议结构（由 renderer 根据 DB 内容派生）

```md
## 文献综述章节引文线索

### 按功能归类
- Background:
- Baseline:
- Contrast:
- Component:
- Dataset:
- Tooling:
- Historical:

### 时间线分析
#### 早期
- [AY-1] Smith, 2020: ...
#### 中期
- [5] Vaswani, 2017: ...
#### 近期
- [12] Carion, 2020: ...
```

## Citation Analysis（Dynamic Citation Scope）细则

目标：辅助用户撰写文献综述。仅基于论文中的“文献综述职责范围”（由 LLM 在 stage 2 生成并写入 DB 的 `citation_scope`）整理：
- 本文引用了哪些文献（与运行时 `reference_items` 关联）
- 本文在该范围内如何介绍/定位这些被引工作（背景/基线/对比/组件等）

### 执行流水线（强制，按顺序）

2) **预处理阶段（确定性）**
- 在 `citation_scope` 内抽取 mention，并将结果写入 `citation_mentions`。
- mention 统计至少要能支持：`scope`、`mentions[]`、`stats.total_mentions`。
- `prepare_citation_workset` 只允许读取 `section_scopes.citation_scope`，不得再通过 CLI / payload 重传 scope。
- 只有当 DB 中已有的 `citation_scope` 与当前标准化源内容越界时，脚本才允许 fallback；fallback 必须写明 `fallback_from`、`fallback_reason`、`scope_source`。
- 任何语义分析前，都必须先有这批持久化后的 mention 数据。
- mention 去噪规则（强制）：
  - 过滤 `![](...)` 图片链接
  - 过滤普通 URL
  - 过滤资源路径
  - 过滤 `.jpg` / `.png` / `.pdf` 等尾缀
  - 过滤日期型字符串
- 被过滤的假阳性必须计入 `citation_false_positive_filtered` warning 与 workset 统计。

3) **映射阶段（规则优先）**
- 运行时输入只允许使用：`reference_items` + 已持久化的 mention 数据 + `citation_scope` + mention 所在 snippet。
- numeric 先按 `ref_number -> ref_index`；author-year 先按 `year + first-author surname`。
- 若多候选冲突或证据不足，不可硬猜，直接进入 `unmapped_mentions`。
- 如需辅助 join，可使用 `export_citation_workset` 只读导出候选，不得把它当作新的真源。

4) **语义阶段（LLM）**
- 仅对 `citation_workset_items` 执行语义任务，不得再做全文盲扫或重复 join。
- 对每个 workset item 生成：`function`、`topic`、`usage`、`keywords`、`summary`、`is_key_reference`、`confidence`。
- `function` 只是粗分类，不等于真正分析。
- `topic` 必须说明这篇文献在当前综述范围中代表的主题、路线或对象。
- `usage` 必须回答“原文为什么在这里引用它，用它完成什么论证”。
- `keywords` 必须是短词组数组，用于提炼任务、方法、对象或路线；不能把标题整句原样拆词。
- `summary` 必须是“该引用在当前 `citation_scope` 中的具体作用”，优先写原文如何使用它，其次才写文献本身是什么，不能写成泛化文献简介。
- 同一 `function` 下的不同文献，`summary` 也必须体现具体差异，不得批量复用“提供背景支持”“作为方法对比”这类套话。
- `is_key_reference` 用来标记当前综述范围内必须在全局总结中点出的关键文献。
- 这里写入的是条目级引文语义判断，不是最终引文报告。
- `function` 只允许使用固定枚举：
  - `background`
  - `baseline`
  - `contrast`
  - `component`
  - `dataset`
  - `tooling`
  - `historical`
  - `uncategorized`
- 非枚举值会被脚本归一为 `uncategorized` 并写 warning。

### Function 级写作规则（强制）

- `background`
  - 应写清原文借它铺什么背景、提出什么问题，不要只写“提供背景支持”。
  - 正例：`原文借该工作说明 attention 已经成为序列建模中的成熟机制，从而为后续引入 transformer 铺垫背景。`
  - 反例：`该工作为研究提供背景支持。`
- `baseline`
  - 应写清它为什么被当作现有主流基线，以及原文借它界定哪条既有路线。
  - 正例：`该工作被原文当作 two-stage 检测器代表，用来界定现有强基线仍依赖 proposal 管线。`
  - 反例：`该工作是一个基线方法。`
- `contrast`
  - 应写清原文拿它来反衬什么限制、缺点或设计差异。
  - 正例：`原文引用该工作来说明围绕 NMS 的改良仍依赖后处理，从而反衬本文试图去除这类启发式。`
  - 反例：`该工作与本文形成对比。`
- `component`
  - 应写清它是本文方案中的哪类关键组件或训练构件。
  - 正例：`该工作被原文当作 Hungarian matching 组件来源，用来固定本文集合预测损失中的匹配机制。`
  - 反例：`该工作是一个组件。`
- `dataset`
  - 应写清它在实验设置或评价基准中的作用，而不是泛泛说“用了数据集”。
  - 正例：`原文引用该工作来说明 COCO 是实验评测基准，并借其标准划分与指标定义实验环境。`
  - 反例：`该工作是一个数据集。`
- `historical`
  - 应写清它在技术谱系中处于什么位置，以及原文为何回溯到它。
  - 正例：`原文借该工作回溯早期 seq2seq 范式，说明并行 transformer 之前主流生成模型仍依赖自回归解码。`
  - 反例：`该工作是历史文献。`

5) **全局总结阶段（LLM）**
- 在 item 级语义结果全部完成后，先额外生成一个 timeline，再生成全局 `summary`。
- timeline 必须通过 `persist_citation_timeline` 写入 DB，固定分为 `early` / `mid` / `recent` 三段。
- 每一段都必须包含 `summary` 与 `ref_indexes`。
- 所有有稳定 `year` 的条目都必须恰好落入一个 timeline bucket。
- `year == null` 的条目允许不进入 timeline，但应触发 `citation_timeline_missing_year` warning。
- author-year 型条目在最终渲染中会按首次出现顺序合成 `[AY-k]`，不得与原始 numeric 编号混用。
- 这个 `summary` 必须概括原文如何使用这些文献来组织 Introduction / Related Work 的论述。
- `summary` 必须梳理研究领域或研究方向的脉络，而不是只统计 `background` / `baseline` / `contrast` 的数量或占比。
- `summary` 必须点出关键文献或关键路线，不能只给百分比、条目数或泛化分类统计。
- `summary` 必须通过 `persist_citation_summary` 写入 DB。
- `basis.research_threads` / `basis.argument_shape` / `basis.key_ref_indexes` 是必填结构，用来先固定研究脉络、论述动作与关键文献，再写自然语言 summary。
- 这里写入的是全局自然语言总结，不是按功能分组后的最终 `report_md`。

6) **渲染阶段（脚本）**
- `report_md` 不由 LLM 直接写入。
- renderer 必须根据 `citation_summary.summary_text`、`citation_timeline`、`citation_items.function`、`citation_items.summary`、`citation_items.keywords`、`citation_unmapped_mentions` 与 `citation_scope` 派生 `report_md`。
- `citation_analysis.md` 与 `citation_analysis.json.report_md` 必须复用同一份渲染结果。
- `report_md` 是 renderer 派生结果，不是 agent 输出物。

7) **门禁阶段（必须通过）**
- `citation_workset_items` 必须完全覆盖所有已稳定映射的 mentions。
- `persist_citation_semantics` 必须完全覆盖所有 workset `ref_index`。
- `persist_citation_timeline` 必须覆盖所有有稳定年份的 `ref_index`，且每个条目只能出现在一个 bucket。
- `summary` 缺失时禁止进入最终渲染。

### 预处理结果契约（DB 视角）

workset 准备完成后，运行时至少应持久化并可查询：

- `section_scopes.citation_scope`
- `citation_mentions`
- `citation_mention_links`
- `citation_workset_items`
- `citation_batches`
- `citation_unmapped_mentions`

若调用方需要人工审计，可额外导出 sidecar，但 sidecar 只是副产物，不是过程真源。

### Citation workset（只读辅助工具）

`scripts/stage_runtime.py export_citation_workset` 可输出：

- `mentions`
- `mention_links`
- `reference_index`
- `workset_items`
- `unresolved_mentions`
- `suggested_batches`

它只帮助 LLM 查看已经写入 DB 的关联结果；不写 DB，不参与 gate 主路径。

此外，`prepare_citation_workset` / `export_citation_workset` 还应额外提供轻量审阅视图，只保留：

- `ref_index`
- `title`
- `mention_count`
- `snippets`

该视图用于后续语义阶段快速消费。语义阶段应优先消费 `ref_index/title/mention_count/snippets`，避免回到全文盲扫。该视图不替代完整 workset，也不是新的真源。

### 支持的引文体例（必须同时支持）

1) numeric（编号型）：
- 支持：`[5, 36]`、`[4,15,38]`、`[40-42]`、`[40–42]`
- 映射：优先 `ref_number -> ref_index`

2) author-year（作者-年份型，高质量要求）：
  - 必须识别：`(Smith, 2020)`、`Smith et al. (2020)`、`(Smith & Jones, 2020; Brown, 2019)` 等
- 映射规则（禁止硬猜）：
  - 优先在 `reference_items` 中按 `year + first-author surname` 匹配
  - 必要时结合 `raw` 和 snippet 做二次判别
  - 无法可靠映射时写入 `unmapped_mentions`

### 边界情况判定与回退

- `citation_scope` 不存在或范围不可判定：
  - 输出 schema 兼容 JSON，`citation_analysis_path=""`，`error={code,message}`。
- `citation_scope` 过窄：
  - 输出 schema 兼容 JSON，`citation_analysis_path=""`，`error={code,message}`。
- `citation_scope` 存在但未检测到任何 citation：
  - 允许输出空 `items=[]`、`unmapped_mentions=[]`，并由 renderer 在 `report_md` 明确“本章节未检测到稳定引用标记”。
- `reference_items` 不足或不可用：
  - mention 仍需抽取；无法映射的 mention 全部进入 `unmapped_mentions(reason=reference_unavailable)`。
- 门禁失败（`coverage < 1.0`）：
  - 必须回退为失败输出（`error` 非空），不得“假成功”返回 citation_analysis。

## Citation 阶段的 DB-first 门禁规则

### Citation Analysis 分阶段规则

1. LLM 先给出唯一 `citation_scope`
2. mention 预处理结果写入 `citation_mentions`
3. 批次信息写入 `citation_batches`
   - 每批最多 `12` 个聚合后的 citation items
   - 或最多 `30` 个 mentions
   - 先命中哪个上限就按哪个切分
4. mention -> reference 链接写入 `citation_mention_links`
5. 聚合后的 workset 写入 `citation_workset_items`
6. agent 仅为这些 workset items 写入 `citation_items`
7. agent 再写入 `citation_timeline`
8. agent 最后写入全局 `citation_summary`
9. `stage_6_render_and_validate` 再基于 `citation_summary` / `citation_timeline` / `citation_items` / `citation_unmapped_mentions` / `citation_scope` 生成最终 `report_md`
10. 仅当唯一性、workset 覆盖、timeline、summary 与 report 渲染都通过时，才可发布最终 `citation_analysis.json`

### Merge 门禁（强制）

- `mention_id` 必须全局唯一
- 同一 `ref_index` 只能有一个最终 item
- `sum(len(item.mentions)) + len(unmapped_mentions)` 必须严格等于抽取出的总 mention 数
- 任一门禁不通过，都必须视为失败，不允许“猜测修复后继续成功”

### 阶段级失败码（强制）

- `references_stage_failed`
- `references_merge_failed`
- `citation_scope_failed`
- `citation_semantics_failed`
- `citation_report_failed`
- `citation_merge_failed`

### Warning 分类（运行时）

当前阶段至少会使用这些 warning 分类：

- `citation_false_positive_filtered`
- `scope_fallback_used`
- `reference_numbering_anomaly_detected`
- `reference_parse_low_confidence`

## Citation 阶段持久化要求

用途：
- 从 `section_scopes.citation_scope` 驱动 mention 抽取
- 将 mention 级记录写入 `citation_mentions`
- 将 mention 解析结果写入 `citation_mention_links`
- 将聚合后的 workset items 写入 `citation_workset_items`
- 将最终语义判断写入 `citation_items`
- 将时间线分析写入 `citation_timeline`
- 将全局自然语言总结写入 `citation_summary`
- 仅在唯一性、workset 覆盖、timeline、summary 与 report 校验全部通过后，才允许 renderer 发布最终 `citation_analysis.json`

要求：
- 不得重复抽取已持久化的 mentions
- 不得容忍 duplicate `mention_id`
- 不得容忍 duplicate `ref_index`
- 不得接受 LLM 直接提交 `report_md`
- 脚本派生 `report_md` 失败时必须直接失败，不得发布最终 `citation_analysis.json`

### `persist_citation_semantics` 合法 payload 示例

```json
{
  "items": [
    {
      "ref_index": 0,
      "function": "contrast",
      "topic": "依赖后处理的检测改良路线",
      "usage": "原文借它说明围绕 NMS 的改良仍依赖后处理，从而反衬本文去除这类启发式的目标。",
      "keywords": ["NMS", "post-processing", "detection refinement"],
      "summary": "该工作被用来代表依赖后处理的检测改良思路，原文通过它反衬本文试图摆脱 NMS 系列启发式的设计取向。",
      "is_key_reference": true,
      "confidence": 0.9
    }
  ]
}
```

### `persist_citation_timeline` 合法 payload 示例

```json
{
  "timeline": {
    "early": {
      "summary": "早期工作主要奠定了注意力与匹配式检测的思想基础。",
      "ref_indexes": [2, 8]
    },
    "mid": {
      "summary": "中期工作把这些思想推进到更成熟的检测与关系建模路线。",
      "ref_indexes": [15, 24, 29]
    },
    "recent": {
      "summary": "近期工作更直接收束到与本文最接近的直接集合预测和 transformer 检测路线。",
      "ref_indexes": [38, 42]
    }
  }
}
```

### `persist_citation_summary` 合法 payload 示例

```json
{
  "summary": "该综述范围先回顾早期注意力与序列建模工作来铺垫 transformer 背景，再把依赖 NMS 的检测路线与直接集合预测思路并置比较，最后用几篇关键匹配式与 transformer 文献把本文的方法定位为一条更统一的检测路线。",
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

### 非法 payload 示例

包含已废弃 `report_md`：

```json
{
  "items": [],
  "report_md": "## Report"
}
```

duplicate `ref_index`：

```json
{
  "batches": [],
  "items": [
    { "ref_index": 0, "ref_number": 1, "reference": {}, "mentions": [], "function": "background", "summary": "a", "confidence": 0.9 },
    { "ref_index": 0, "ref_number": 1, "reference": {}, "mentions": [], "function": "baseline", "summary": "b", "confidence": 0.8 }
  ],
  "unmapped_mentions": []
}
```

timeline bucket 缺失或覆盖不闭合：

```json
{
  "timeline": {
    "early": { "summary": "early", "ref_indexes": [2] },
    "mid": { "summary": "mid", "ref_indexes": [2] }
  }
}
```

coverage 不闭合：

```json
{
  "batches": [],
  "items": [],
  "unmapped_mentions": []
}
```

统计型 summary / 缺少 basis：

```json
{
  "summary": "本节共引用 39 篇文献，其中 background 占 40%，contrast 占 55%。"
}
```

包含非法 scope override 语义：

```json
{
  "scope": {
    "section_title": "Introduction",
    "line_start": 1,
    "line_end": 20
  }
}
```

## 当前阶段动作提示

适用 gate 阶段：
- `stage_5_citation`

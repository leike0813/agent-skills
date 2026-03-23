# Step 05: Citation Pipeline

本文件按 `SKILL.md` 的“参数词表（全项目统一）”定义；这里只补 stage 5 的额外约束，不重复定义字段基础含义。

本文件定义 `citation_analysis` 结构、`Citation Analysis（Dynamic Citation Scope）细则`、预处理契约、支持体例、边界情况、阶段失败语义以及 citation 阶段的当前 DB-first 约束。

## citation_analysis 输出格式

`citation_analysis_path` 指向的文件内容必须是 JSON 对象，至少包含：
- `meta`
  - `language`
  - `scope`
- `summary`
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
- `summary`
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

### 按引用编号/作者-年份列举
- [5] ...（一句话：本文如何定位这篇）
- (Smith, 2020) ...（若未映射成功则提示 unmapped）
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
- 对每个 workset item 生成：`function`、`summary`、`confidence`。
- `summary` 必须是“该引用在当前 `citation_scope` 中的作用”，不能写成泛化的文献简介。
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

5) **全局总结阶段（LLM）**
- 在 item 级语义结果全部完成后，再额外生成一个全局 `summary`。
- 这个 `summary` 必须概括该范围内引用组织方式、主要功能分布和整体叙述倾向。
- `summary` 必须通过 `persist_citation_summary` 写入 DB。
- 这里写入的是全局自然语言总结，不是按功能分组后的最终 `report_md`。

6) **渲染阶段（脚本）**
- `report_md` 不由 LLM 直接写入。
- renderer 必须根据 `citation_summary.summary_text`、`citation_items.function`、`citation_items.summary`、`citation_unmapped_mentions` 与 `citation_scope` 派生 `report_md`。
- `citation_analysis.md` 与 `citation_analysis.json.report_md` 必须复用同一份渲染结果。
- `report_md` 是 renderer 派生结果，不是 agent 输出物。

7) **门禁阶段（必须通过）**
- `citation_workset_items` 必须完全覆盖所有已稳定映射的 mentions。
- `persist_citation_semantics` 必须完全覆盖所有 workset `ref_index`。
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

该视图用于后续语义阶段快速消费，不替代完整 workset，也不是新的真源。

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
7. agent 再写入全局 `citation_summary`
8. `stage_6_render_and_validate` 再基于 `citation_summary` / `citation_items` / `citation_unmapped_mentions` / `citation_scope` 生成最终 `report_md`
9. 仅当唯一性、workset 覆盖、summary 与 report 渲染都通过时，才可发布最终 `citation_analysis.json`

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
- 将全局自然语言总结写入 `citation_summary`
- 仅在唯一性、workset 覆盖、summary 与 report 校验全部通过后，才允许 renderer 发布最终 `citation_analysis.json`

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
      "function": "background",
      "summary": "被用作背景工作",
      "confidence": 0.9
    }
  ]
}
```

### `persist_citation_summary` 合法 payload 示例

```json
{
  "summary": "该综述范围内的引用主要被组织为背景工作与组件性工作，整体叙述以构建问题背景和方法拼装线索为主。"
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

coverage 不闭合：

```json
{
  "batches": [],
  "items": [],
  "unmapped_mentions": []
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

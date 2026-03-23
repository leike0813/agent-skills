# Step 02: Outline And Scopes

本文件按 `SKILL.md` 的“参数词表（全项目统一）”定义；这里只补 stage 2 的额外约束，不重复定义字段基础含义。

本文件描述结构化骨架、references/citation scope 决策，以及当前 DB-first runtime 中的阶段持久化要求。

## 处理步骤（建议工作流）中的结构化骨架阶段

4) 基于标准化源内容生成“结构化骨架”（建议为 JSON）：包含大纲、references 区块位置，以及可能承担文献综述职责的章节范围（例如 Introduction、Related Works、Background 等，按原始 md 行号 1-based）。
   - 运行时真源是 `source_documents.normalized_source`
   - `source.md` 仅是可视化副产物，不是阶段输入真源
5) 基于骨架：
- 后续阶段将生成 digest 结构化槽位与分章节摘要
- 后续阶段将定位 references 区块并抽取结构化引文条目
- 由 LLM 从骨架中生成**唯一 `citation_scope` 定义对象**（可覆盖一个或多个章节）并覆盖必要子章节，后续 citation 阶段再基于 DB 行执行抽取、聚合与最终渲染

在当前 SQLite runtime 中，这些语义结果对应：
- `outline_nodes`
- `section_scopes.references_scope`
- `section_scopes.citation_scope`

## 分阶段执行与持久化（强制）

为避免 `references` 与 `citation_analysis` 的长静默单轮生成触发下游超时，本 skill 必须在内部采用分阶段执行，但**最终公开契约保持不变**。

- 大纲结果写入 `outline_nodes`
- references 范围与 citation 范围写入 `section_scopes`
- 本阶段只负责把骨架与 scope 决策写入 DB
- `digest.md`、`references.json` 与 `citation_analysis.json` 一律在 `stage_6_render_and_validate` 统一渲染发布
- **禁止跳过 DB 持久化直接构造最终公开文件**

当前阶段的核心表语义：
- `outline_nodes`
  - 全文大纲、层级、行号与父子关系
- `section_scopes`
  - `references_scope` 与 `citation_scope` 的标题、边界和附加 metadata
- `workflow_state`
  - 记录当前 stage/substep/gate，作为下一动作的唯一真源

硬约束：

- `citation_scope` 与 `references_scope` 一旦在本阶段写入 DB，就成为后续阶段唯一合法输入来源
- 后续主路径不得再通过 CLI / JSON 重传 scope 文件、scope 边界或 scope 标题

### `persist_outline_and_scopes` payload 形状

本阶段写库输入应保持为结构化 payload，而不是接近最终产物的文本。当前脚本只接受这一套字段形状：

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
    }
  ],
  "references_scope": {
    "section_title": "References",
    "line_start": 201,
    "line_end": 260,
    "metadata": {}
  },
  "citation_scope": {
    "section_title": "Introduction + Related Works",
    "line_start": 1,
    "line_end": 80,
    "metadata": {
      "selection_reason": "综述职责覆盖引言与相关工作",
      "covered_sections": ["Introduction", "Related Works"]
    }
  }
}
```

硬约束：

- `outline_nodes` 不接受“只有标题字符串”的简写。
- `references_scope` / `citation_scope` 不接受“章节名列表”或“语义描述”充当 payload。
- `parent_node_id` 必须显式出现；一级标题写 `null`。
- `metadata` 必须显式出现；没有补充信息时传 `{}`。

## Citation Analysis（Dynamic Citation Scope）中的 scope 决策前半段

### 执行流水线（强制，按顺序）

1) **范围决策阶段（LLM）**
- 先让 LLM 抽取“结构化骨架”：至少包含
  - `outline`（大纲，需保留标题层级关系）
  - `references_scope`（参考文献章节范围）
  - `review_scope_candidates`（候选综述章节范围，含标题、层级、行号）
- 再让 LLM 基于骨架生成 `citation_scope`（最终分析范围定义）。
- `citation_scope` 是**单一定义对象**，但语义上可覆盖**多个章节**（例如 `Introduction + Related Works`），不是“只能单章”。
- **禁止双层 scope 决策**：不得再输出 `review_scopes + analysis_scope` 两段式决策结果，应直接输出 `citation_scope`。
- **子章节覆盖规则（强制）**：
  - 若 `citation_scope` 选中了父章节（例如 `Related Works`、`Background`、`Prior Work`），则必须覆盖其全部子章节正文；
  - 结束边界应为“下一个同级或更高层级标题之前”，不得只截取父章节标题下的首段；
  - 若父章节存在多个子标题而 scope 未覆盖这些子标题内容，视为范围无效（过窄）。
- **跨章节覆盖规则（强制）**：
  - 当骨架显示文献综述职责分布在多个章节（如 `Introduction` 与 `Related Works`）时，`citation_scope` 必须覆盖这些章节，而不是只保留其中之一。
  - 若章节之间是连续的，可用一个连续行号范围覆盖；`section_title` 可写为组合名称（如 `Introduction + Related Works`）。
- 若 `citation_scope` 无法可靠确定，必须回退为失败输出（`error` 非空），不得让脚本盲猜。
- 若本阶段已成功写入 `citation_scope`，后续阶段只能读取它；不存在“后面再改一次 scope”的主路径。

## 当前阶段动作提示

适用 gate 阶段：
- `stage_2_outline_and_scopes`

常见动作：
- `persist_outline_and_scopes`
- `repair_db_state`

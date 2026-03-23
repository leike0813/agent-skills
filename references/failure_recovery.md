# Failure Recovery

本文件按 `SKILL.md` 的“参数词表（全项目统一）”定义；这里只覆盖运行失败后的恢复路径。

## 什么时候读本文件

- gate 返回 `repair_db_state`
- gate 返回 `repair_workflow_state`
- 当前阶段脚本返回 `error.code`，且重新跑 gate 后仍未回到 `ready`

## 先看什么

1. 先运行 `python scripts/gate_runtime.py`
2. 看 `status_summary`
3. 看 `last_error_code`
4. 再看当前阶段的 `instruction_refs`

如果错误与 payload 形状有关，优先回到 `stage_runtime_interface.md`。

## DB 已有旧状态时怎么判断能否续跑

- 若 gate 返回的是正常主路径 `next_action`，说明可以续跑，不要清库。
- 若 gate 返回 `repair_db_state`，优先补缺失的前置数据，不要直接重建全部 DB。
- 若 `runtime_inputs.source_path` 指向的源文件已经换了，当前 DB 不应复用，应删除整个 `.literature_digest_tmp/` 后重新 bootstrap。

## 哪些文件可以删除重跑

可以安全删除并让脚本重建：

- `<cwd>/.literature_digest_tmp/source.md`
- `<cwd>/.literature_digest_tmp/source_meta.json`
- `prepare_citation_workset` 或 `export_citation_workset` 导出的 sidecar JSON
- 最终公开产物 `digest.md`、`references.json`、`citation_analysis.json`、`citation_analysis.md`

前提是：不要手改 DB 内容，然后重新从 gate 指定的动作继续。

## 哪些内容不要手改

- 不要手改 SQLite 表行
- 不要手改 `workflow_state`
- 不要手改 `artifact_registry`
- 不要手改 `citation_scope`
- 不要手改已经发布的最终 JSON 再假装它们来自 renderer

## 常见卡点

### gate 卡在 `persist_outline_and_scopes`

优先检查：

- `source_documents.normalized_source` 是否存在
- payload 是否使用了唯一合法字段：
  - `outline_nodes[*].node_id`
  - `outline_nodes[*].heading_level`
  - `outline_nodes[*].title`
  - `outline_nodes[*].line_start`
  - `outline_nodes[*].line_end`
  - `outline_nodes[*].parent_node_id`
  - `references_scope.section_title/line_start/line_end/metadata`
  - `citation_scope.section_title/line_start/line_end/metadata`

### gate 卡在 `persist_references`

优先检查：

- `entries` / `batches` / `items` 是否同时存在
- `batches` 是否使用 `entry_start` / `entry_end`
- `items[*].year` 是否误取了 arXiv 编号前缀
- `author` 是否需要退回保守模式

### gate 卡在 `prepare_citation_workset`

优先检查：

- `section_scopes.citation_scope` 是否已经写入
- `reference_items` 是否存在
- 当前 scope 是否越界
- 是否有大量图片链接、URL、资源路径、日期型字符串导致去噪后 mention 过少

### gate 卡在 `persist_citation_semantics`

优先检查：

- `prepare_citation_workset` 是否已经成功
- payload 是否只包含 `items`
- `items[*]` 是否只按 `ref_index` 提交
- 是否错误地传入了 `mentions` / `reference` / `report_md`

### gate 卡在 `persist_citation_summary`

优先检查：

- `citation_items` 是否已完整写入
- `summary` 是否为空字符串

### gate 卡在 `render_and_validate`

优先检查：

- `digest_slots`
- `digest_section_summaries`
- `reference_items`
- `citation_workset_items`
- `citation_items`
- `citation_summary`

正式发布路径不接受显式 `source_path`、`out_dir` 或业务 payload。

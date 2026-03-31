# SQL Playbook

本文件用于解释 gate `sql_examples` 的背景，不替代 gate 当前动作给出的最小 SQL。文中涉及的参数名与 payload 字段均按 `SKILL.md` 的“参数词表（全项目统一）”理解。

## 通用原则

- 先查再写：先确认前置数据是否存在，再执行写入
- 以 UPSERT 为默认写法，避免恢复执行时重复插入
- `workflow_state` 只能在修复或阶段推进时改写
- 最终公开产物路径统一登记到 `artifact_registry`
- repair 场景必须先看 gate 返回的 `status_summary` 与 `instruction_refs`

## 常见表职责

- `runtime_inputs`
  - 输入路径、语言、时间戳、hash、模型信息
- `workflow_state`
  - 当前阶段、子步骤、gate 状态、下一动作
- `source_documents`
  - 标准化源内容与相关元数据
- `outline_nodes`
  - 大纲节点骨架
- `section_scopes`
  - 参考文献范围与引文分析范围定义
- `digest_slots`
  - digest 结构化内容槽位
- `digest_section_summaries`
  - 分章节摘要列表
- `reference_entries`
  - 参考文献条目：从 references 范围切分出的原始条目
- `reference_batches`
  - 参考文献条目批次边界与状态
- `reference_parse_candidates`
  - 参考文献预解析候选：每个 `entry_index` 的多组 pattern 切分结果，供 agent 选择 `selected_pattern`
  - 若 deterministic splitting 仍不可靠，应先通过 `persist_reference_entry_splits` 复核 `suspect_blocks`，再重建 `reference_entries` 与这些候选
- `reference_items`
  - 参考文献项：最终 `references.json` 的结构化行
- `citation_mentions`
  - 引文标记：scope 内逐条抽取出的 citation 出现位置
- `citation_mention_links`
  - 引文映射：每条引文标记到 `reference_items.ref_index` 的稳定解析结果
- `citation_workset_items`
  - 引文工作集项：按 `ref_index` 聚合后、供语义阶段消费的唯一分析输入
- `citation_batches`
  - 引文工作集批次边界与状态
- `citation_items`
  - 引文语义判断：agent 针对每个 `ref_index` 写入的条目级分析结果
- `citation_unmapped_mentions`
  - 无法稳定映射的引文标记
- `citation_summary`
  - 引文全局总结：agent 在条目分析完成后写入的总体自然语言总结
- `artifact_registry`
  - 公开产物登记表：最终 artifacts 的路径与来源表

## gate SQL 示例阅读方式

- gate 输出里的 `sql_examples` 是当前 `next_action` 的最小示例
- 本文件只说明这些 SQL 为什么出现，不提供 stage 级全集
- 若 gate 返回 repair 类动作，应优先查看对应 `step_*.md`，再参考这里的表职责

## 当前门禁关注点

- `section_scopes` 定义 references 与 citation 的分析范围
- `reference_batches` / `citation_batches` 记录批次边界与状态
- `reference_parse_candidates` 决定 references refine 时可被选择的合法 pattern 集合
- `reference_entries` 若仍出现 grouped-entry 或 multiline-entry suspicion，必须先做 block-level split review，再允许 `persist_references`
- `digest_slots`、`digest_section_summaries`、`reference_items`、`citation_workset_items`、`citation_items`、`citation_summary`、`citation_unmapped_mentions` 共同决定最终发布是否可进行
- `citation_mention_links` 必须完整解释已稳定映射的 mention -> reference 关系
- `citation_items` 只负责语义判断，不再承载 reference snapshot 或 mention 列表真源
- `citation_summary` 是 `citation_analysis.json.summary` 的唯一真源
- merge 门禁依然有效：
  - `mention_id` 唯一
  - `ref_index` 唯一
  - coverage 完整

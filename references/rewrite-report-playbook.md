# Rewrite Report Playbook

`rewrite-report.md` 是最终 bundle 的 DB-rendered 正式输出。

## 固定结构

- `## Run Summary`
- `## Stage Decisions`
- `## Final Draft Section Map`
- `## Key Paragraph And Element Notes`
- `## Unresolved Risks / Follow-up`

## 参照规则

- 对最终稿每个 top-level section 都提供 section 级原文参照。
- 对关键段落、关键图表、关键引用提供更细说明。
- section 级参照的主要来源应是：
  - `semantic_source_units`
  - `section_rewrite_plan_sources`
  - `draft_section_sources`
  - `draft_section_events`
- 若某个 section 吸收了 aux 支撑材料，报告应能让用户看出这些 provenance 来自 aux，而不是 main。
- 不做无差别逐段全文映射。

## 真源约束

报告内容必须基于以下 DB-backed 信息：

- manuscript analysis
- raw scope segments
- semantic source units
- target settings
- style profile
- condensation plan
- section rewrite plan
- draft sections / sources / events
- final outputs
- supporting elements inventory

不得编造原文依据或未发生的变更。

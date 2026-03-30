# Stage 5 Playbook

Stage 5 对应 `stage_5_condensation_plan`。

## 正式写库动作

1. `persist_condensation_plan`
2. `persist_section_rewrite_plan`

## 1. `persist_condensation_plan`

### Payload 要求

- `core_message`
- `priority_map`
- `target_outline`
- `length_allocation`
- `omit_merge_strategy`
- `figure_table_plan`
- `reference_plan`
- `approval_status`

可选：

- `pending_confirmations`

### 作用

- 固定整体凝缩策略
- 收敛 supporting elements 保留/删改策略
- 收敛参考文献迁移策略

## 2. `persist_section_rewrite_plan`

### Payload 要求

- `sections`

每个 section 至少包含：

- `section_id`
- `section_title`
- `planned_count_value`
- `count_unit`
- `must_cover`
- `simplify_first`
- `must_avoid`
- `sources`

### 作用

- 将整体方案细化为 section 级转写真源
- 为每个目标 section 绑定 semantic source units、图表、引用和预计篇幅
- 作为 Stage 6 唯一允许的写作依据
- 必须消费 Stage 3 已确认的 `must_keep` / `simplify_first` / `must_avoid`
- 若某个 section 需要吸收 main 范围之外的背景、综述或方法概述，必须通过带 aux 成员的 semantic unit 间接使用

### 渲染视图

- `09-section-rewrite-plan.md`

### 来源约束

- section rewrite plan 的主路径必须是 `semantic_unit:<unit_id>`
- 若需要单独引用 supporting elements，可再补 `figure` / `table` / `citation` / `bibliography`
- 不得直接绑定 raw scope segments
- 若某个 semantic unit 含 aux 成员，必须写 usage note 说明为何使用 aux
- 若 Stage 3 已确认存在 `simplify_first` 项，section rewrite plan 至少要在一个 section 中显式消费它

## 完成标准

- condensation plan 已批准
- section rewrite plan 已落库
- Stage 6 可以从该计划中逐节推进

## 禁止事项

- 不得只给大纲和粗略字数目标就进入最终撰写
- 不得让 Stage 6 脱离 `section_rewrite_plan` 自由发挥

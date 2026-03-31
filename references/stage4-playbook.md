# Stage 4 Playbook

Stage 4 对应 `stage_4_condensation_plan`。

## 正式写库动作

1. `persist_condensation_plan`
2. `confirm_condensation_plan`
3. `persist_section_rewrite_plan`
4. `confirm_section_rewrite_plan`

## 1. `persist_condensation_plan`

### Minimal Payload Example

```json
{
  "core_message": "A concise multimodal tunneling-state paper centered on the fusion method and its gains.",
  "priority_map": "Prioritize motivation, method, and key experimental evidence; downplay implementation detail.",
  "target_outline": "Introduction; Method; Experiments; Conclusion",
  "length_allocation": "Introduction 900; Method 1800; Experiments 2600; Conclusion 400",
  "omit_merge_strategy": "Merge redundant thesis-style transitions and remove chapter-summary language.",
  "figure_table_plan": "Keep the core architecture figure and simplify large result tables.",
  "reference_plan": "Retain core comparative citations and compress background citation clusters."
}
```

### Notes

- `pending_confirmations` 仍可选；只有整体方案还需要显式确认点时再写。

### 作用

- 固定整体凝缩策略。
- 收敛 supporting elements 保留/删改策略。
- 收敛参考文献迁移策略。

## 2. `confirm_condensation_plan`

### Minimal Payload Example

```json
{
  "approved": true
}
```

### 作用

- 接收用户对整体 condensation plan 的显式批准或退回修改。
- 只有整体 plan 已批准后，才允许生成 section rewrite plan。

## 3. `persist_section_rewrite_plan`

### Minimal Payload Example

```json
{
  "sections": [
    {
      "section_id": "sec-introduction",
      "section_title": "Introduction",
      "planned_count_value": 900,
      "count_unit": "words",
      "must_cover": [
        "Research motivation",
        "Gap statement"
      ],
      "simplify_first": [
        "Extended tutorial background"
      ],
      "must_avoid": [
        "Chapter-summary wording"
      ],
      "section_summary": "Introduce the problem, gap, and paper contribution.",
      "section_strategy": "Start from the practical problem, compress background, then state the method contribution.",
      "figure_table_usage": [],
      "reference_usage": [
        "Use only the most representative related-work citations."
      ],
      "sources": [
        {
          "source_kind": "semantic_unit",
          "source_ref": "u01",
          "usage_note": ""
        }
      ]
    }
  ]
}
```

### Notes

- 若使用 aux-backed semantic units，必须补 `aux_usage_rationale`。
- `figure_table_usage` 为空列表是允许的；若写 `simplify`，对应 item 必须带说明 note。

### 作用

- 将整体方案细化为 section 级转写真源。
- 为每个目标 section 绑定 semantic source units、图表、引用和预计篇幅。
- 为每个目标 section 提供可供用户预演的章节摘要、组织策略、图表使用策略和引用策略。
- 作为 Stage 5 唯一允许的写作依据。
- 必须消费 Stage 3 已确认的 `must_keep` / `simplify_first` / `must_avoid`。
- 若某个 section 需要吸收 main 范围之外的背景、综述或方法概述，必须通过带 aux 成员的 semantic unit 间接使用。

### 渲染视图

- `09-condensation-plan.md`
- `10-section-rewrite-plan.md`

### 来源约束

- section rewrite plan 的主路径必须是 `semantic_unit:<unit_id>`。
- 若需要单独引用 supporting elements，可再补 `figure` / `table` / `citation` / `bibliography`。
- 不得直接绑定 raw scope segments。
- 若某个 semantic unit 含 aux 成员，必须写 usage note 说明为何使用 aux。
- 若 Stage 3 已确认存在 `simplify_first` 项，section rewrite plan 至少要在一个 section 中显式消费它。

## 4. `confirm_section_rewrite_plan`

### Minimal Payload Example

```json
{
  "approved": true
}
```

### 作用

- 接收用户对整份 section rewrite plan 的显式批准或退回修改。
- 只有详细 section plan 已批准后，才允许进入 Stage 5。

## 完成标准

- condensation plan 已获得用户批准。
- section rewrite plan 已落库并获得用户批准。
- Stage 5 可以从该计划中逐节推进。

## 禁止事项

- 不得只给大纲和粗略字数目标就进入最终撰写。
- 不得在整体 plan 未批准时就开始生成 section rewrite plan。
- 不得在 section rewrite plan 未批准时就进入 Stage 5。
- 不得让 Stage 5 脱离 `section_rewrite_plan` 自由发挥。

# Stage 3 Playbook

Stage 3 对应 `stage_3_target_settings`。

## 正式写库动作

1. `persist_target_settings_basics`
2. `persist_content_selection_board`
3. `confirm_content_selection`
4. `persist_style_profile`
5. `finalize_target_settings`

## 1. `persist_target_settings_basics`

### Minimal Payload Example

```json
{
  "target_form": "journal article",
  "target_journal_type": "SCI engineering journal",
  "latex_template_id": "generic-en-journal",
  "target_body_length": {
    "value": 7000,
    "unit": "words"
  },
  "figure_table_preference": "Keep only core figures and simplify tables",
  "reference_handling_preference": "Preserve key citations and keep BibTeX structure"
}
```

### Notes

- `pending_confirmations` 仍可选；只有当前阶段确实需要时再写。
- `target_language` 不再由该动作直接提交；脚本会根据 `target_form` / `target_journal_type` / `latex_template_id` 推导最终目标语言，并覆盖 Stage 2 的初值。

### 作用

- 先固定 Stage 3 的机械目标设置
- 最终确定 `target_language`
- 暂不在这一步要求用户同时完成内容取舍三列表

## 2. `persist_content_selection_board`

### Minimal Payload Example

```json
{
  "items": [
    {
      "item_id": "keep-001",
      "bucket": "must_keep",
      "title": "Core multimodal method description",
      "summary": "Retain the problem formulation and fused-model pipeline.",
      "rationale": "This is the paper's core contribution.",
      "semantic_unit_ids": [
        "u01"
      ]
    }
  ]
}
```

### Notes

- 每个建议项都必须是语义聚合内容，不是机械段落映射。

### 作用

- 基于 `semantic_source_units` 生成三份建议列表：
  - `must_keep`
  - `simplify_first`
  - `must_avoid`
- 每项都必须是语义聚合内容，而不是机械段落映射
- 每项都必须能回溯到 semantic unit，再间接回溯到 raw segments

## 3. `confirm_content_selection`

### Minimal Payload Example

```json
{
  "items": [
    {
      "item_id": "keep-001",
      "bucket": "must_keep",
      "title": "Core multimodal method description",
      "summary": "Retain the problem formulation and fused-model pipeline.",
      "rationale": "User confirmed this should stay.",
      "semantic_unit_ids": [
        "u01"
      ]
    }
  ]
}
```

### Notes

- 若用户做了额外说明，可加可选字段 `note`。

### 作用

- 接收用户对三份建议列表的确认或调整
- 支持：
  - 直接接受已有建议
  - 在三类 bucket 间移动项目
  - 删除项目
  - 新增用户自定义项目
- 最终确认结果会汇总回 `target_settings.must_keep` / `simplify_first` / `must_avoid`

## 4. `persist_style_profile`

### Minimal Payload Example

```json
{
  "source_style": "Technical but thesis-like, with long background passages.",
  "problems_to_fix": "Reduce tutorial tone and compress repetitive exposition.",
  "target_style_guidance": "Write in concise journal style with direct problem-method-result flow.",
  "open_questions": []
}
```

### Notes

- `pending_confirmations` 仍可选；只有风格边界确实需要用户确认时再写。

### 作用

- 在 Stage 3 内完成独立的风格画像子步。
- 总结原稿风格、识别需要修正的问题，并形成目标稿应遵循的风格指导。
- 这一步仍写入独立的 `style_profile` 真源和 `08-style-profile.md` 视图，但不再被视为独立 workflow stage。

## 5. `finalize_target_settings`

### Minimal Payload Example

```json
{
  "user_confirmed": true
}
```

### Notes

- `pending_confirmations` 仍可选；若该阶段还残留待确认项，就不能在这一步真正封口。

### 作用

- 完成 Stage 3 总确认
- 只有内容取舍三列表确认后，才允许把 `user_confirmed` 置为 `true`

## 渲染视图

- `06-target-settings.md`
- `07-content-selection-board.md`
- `08-style-profile.md`

## 执行规则

- Stage 3 的正确顺序固定为：
  1. 基本目标设置
  2. 内容取舍建议板
  3. 用户确认 / 调整三列表
  4. 风格画像
  5. 最终确认
- gate 不允许跳过内容取舍建议板或风格画像直接完成 Stage 3。
- `simplify_first` 是正式列表，和 `must_keep` / `must_avoid` 同级，不得被当作 `must_avoid` 处理。

## 完成标准

- 基本目标设置已写库
- 内容取舍建议板已生成
- 三类列表已确认并汇总回 `target_settings`
- style profile 已写库
- `user_confirmed=true`
- 无该阶段残留 `pending_confirmations`

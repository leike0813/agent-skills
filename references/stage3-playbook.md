# Stage 3 Playbook

Stage 3 对应 `stage_3_target_settings`。

## 正式写库动作

1. `persist_target_settings_basics`
2. `persist_content_selection_board`
3. `confirm_content_selection`
4. `finalize_target_settings`

## 1. `persist_target_settings_basics`

### Payload 要求

- `target_language`
- `target_form`
- `target_journal_type`
- `latex_template_id`
- `target_body_length`
- `figure_table_preference`
- `reference_handling_preference`

可选：

- `pending_confirmations`

### 作用

- 先固定 Stage 3 的机械目标设置
- 暂不在这一步要求用户同时完成内容取舍三列表

## 2. `persist_content_selection_board`

### Payload 要求

- `items`

每个建议项至少包含：

- `item_id`
- `bucket`
- `title`
- `summary`
- `rationale`
- `semantic_unit_ids`

### 作用

- 基于 `semantic_source_units` 生成三份建议列表：
  - `must_keep`
  - `simplify_first`
  - `must_avoid`
- 每项都必须是语义聚合内容，而不是机械段落映射
- 每项都必须能回溯到 semantic unit，再间接回溯到 raw segments

## 3. `confirm_content_selection`

### Payload 要求

- `items`

每个确认项至少包含：

- `item_id`
- `bucket`
- `title`
- `summary`
- `rationale`
- `semantic_unit_ids`

可选：

- `note`

### 作用

- 接收用户对三份建议列表的确认或调整
- 支持：
  - 直接接受已有建议
  - 在三类 bucket 间移动项目
  - 删除项目
  - 新增用户自定义项目
- 最终确认结果会汇总回 `target_settings.must_keep` / `simplify_first` / `must_avoid`

## 4. `finalize_target_settings`

### Payload 要求

- `user_confirmed=true`

可选：

- `pending_confirmations`

### 作用

- 完成 Stage 3 总确认
- 只有内容取舍三列表确认后，才允许把 `user_confirmed` 置为 `true`

## 渲染视图

- `03-target-settings.md`
- `11-content-selection-board.md`

## 执行规则

- Stage 3 的正确顺序固定为：
  1. 基本目标设置
  2. 内容取舍建议板
  3. 用户确认 / 调整三列表
  4. 最终确认
- gate 不允许跳过内容取舍建议板直接完成 Stage 3。
- `simplify_first` 是正式列表，和 `must_keep` / `must_avoid` 同级，不得被当作 `must_avoid` 处理。

## 完成标准

- 基本目标设置已写库
- 内容取舍建议板已生成
- 三类列表已确认并汇总回 `target_settings`
- `user_confirmed=true`
- 无该阶段残留 `pending_confirmations`

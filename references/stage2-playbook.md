# Stage 2 Playbook

本文件只展开 Stage 2。全局约束、脚本职责和阶段门禁以 `SKILL.md` 为准。

## 适用范围

- 本 playbook 只处理目标设置、图表处理偏好、参考文献处理偏好与保留/避免项。
- Stage 2 的正式真源是 `.paper-condenser-tmp/<document-slug>/target-settings.json`。
- 本阶段不新增脚本，但需要把 `latex_template_id` 纳入目标设置。

## 子步骤顺序

### 1. 进入 Stage 2

- 前置条件：
  - Stage 1 已完成。
  - `manuscript-profile.json` 已形成可用理解草案。
- 操作：
  - 基于 Stage 1 结果判断当前目标设置是否已经足够明确。
  - 若仍为空或不完整，开始逐项提问。

### 2. 核心目标设置采集

- 建议顺序：
  1. `target_language`
  2. `target_form`
  3. `target_journal_type`
  4. `latex_template_id`
  5. `target_body_length.value`
  6. `target_body_length.unit`
  7. `figure_table_preference`
  8. `reference_handling_preference`
- 规则：
  - 每收集到一个答案，就回写对应字段。
  - 在整组设置确认前，保持 `user_confirmed=false`。
  - `latex_template_id` 只能从 skill 内置 preset 中选择：
    - `generic-article`
    - `generic-cn-journal`
    - `generic-en-journal`

### 3. 保留项与避免项采集

- 继续询问：
  - `figure_table_preference`
  - `reference_handling_preference`
  - `must_keep`
  - `must_avoid`
- 规则：
  - 这些约束都属于 Stage 2 完成门禁的一部分，不能默认推迟到后续阶段。
  - 允许先形成草案，再在 readback 阶段统一确认。

### 4. 整组 Readback

- 当所有字段都已填写后：
  - 用一轮完整 readback 向用户复述当前 Stage 2 设置。
  - readback 必须覆盖所有字段，而不是只重复最后一次提问的结果。
  - readback 必须包含 `latex_template_id`、图表处理偏好和参考文献处理偏好。

### 5. 明确确认

- 只有在用户明确表示认可整组设置后：
  - 才把 `user_confirmed` 更新为 `true`
- 如果用户要求修改任一字段：
  - 先更新字段
  - 保持或恢复 `user_confirmed=false`
  - 重新做整组 readback

## 必问条件

- 任一核心目标设置字段为空。
- `latex_template_id` 尚未明确。
- `figure_table_preference` 尚未明确。
- `reference_handling_preference` 尚未明确。
- `must_keep` 尚未明确。
- `must_avoid` 尚未明确。
- 用户修改了先前已给出的目标设置。
- 已经收集完字段，但还未做整组 readback。

## 禁止提问条件

- 不得在 Stage 2 提前分析原稿风格。
- 不得在 Stage 2 提前讨论重点/非重点。
- 不得在 Stage 2 提前讨论目标大纲。
- 不得在 Stage 2 提前讨论篇幅分配和删改策略。
- 不得在 Stage 2 提前决定具体保留哪些图表或删掉哪些引用。
- 不得在 Stage 2 接受外部模板路径或多文件模板工程作为首版正式模板来源。

## 常见失败场景

### 只做部分提问

- 表现：
  - 只问了语言和体例，就试图推进到下一阶段
- 处理：
  - 回到剩余字段，补齐期刊类型、模板选择、正文长度、保留项和避免项

### 已填字段但未确认

- 表现：
  - `target-settings.json` 看起来已经完整，但没有 readback，或 `user_confirmed=false`
- 处理：
  - 做整组 readback
  - 获取明确确认后再置 `user_confirmed=true`

### 修改后沿用旧确认状态

- 表现：
  - 用户修改某一字段后，`user_confirmed` 仍保持为 `true`
- 处理：
  - 立即恢复为 `false`
  - 重新做整组 readback

## Stage 3 交接检查清单

- `target_language` 非空
- `target_form` 非空
- `target_journal_type` 非空
- `latex_template_id` 非空
- `target_body_length.value` 已写入
- `target_body_length.unit` 已写入
- `figure_table_preference` 已写入
- `reference_handling_preference` 已写入
- `must_keep` 已写入
- `must_avoid` 已写入
- 已完成整组 readback
- `user_confirmed=true`

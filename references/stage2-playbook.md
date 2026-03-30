# Stage 2 Playbook

Stage 2 对应 `stage_2_manuscript_analysis`。

## 正式写库动作

1. `persist_manuscript_analysis`
2. `persist_raw_scope_segments`
3. `persist_semantic_source_units`

## 1. `persist_manuscript_analysis`

- 由 LLM 生成 payload，再通过 `stage_runtime.py` 写库。
- payload 至少包含：
  - `main_scope`
  - `main_scope_locator`
  - `aux_scopes`
  - `topic`
  - `main_work`
  - `novelty`
  - `section_outline`
  - `removable_candidates`
  - `open_questions`
- 可选：
  - `pending_confirmations`

### 作用

- 固定本轮处理的主转写范围与辅助支撑范围
- 形成主题、主要工作、创新点和结构理解
- 为后续 raw segmentation 提供 machine-readable `main_scope_locator` 与 `aux_scopes[*].locator`

### 范围语义

- `main_scope` 是主要转写目标
- `aux_scopes` 是支撑来源，可用于背景、综述、方法概述等补充材料
- `aux_scopes` 是列表；每项至少包含：
  - `aux_id`
  - `label`
  - `purpose`
  - `locator`
- `aux` 不是第二主 scope，不得把它当成并列主转写目标

## 2. `persist_raw_scope_segments`

- 由脚本完成，不接受 LLM 语义 payload。
- 基于 source + 已写库的 `main_scope_locator` 与 `aux_scopes[*].locator`，在统一 raw 表中做 deterministic block 提取。
- 额外要求：
  - `figure` / `table` / `display_block` 必须独立成段
  - 每条 raw segment 必须带 `scope_role=main|aux`
  - 每条 raw segment 必须带 `scope_bucket_id` 与 `scope_label`
  - 不做语义取舍，只写事实型 segmentation

### 写入真源

- `raw_scope_segments`

### 渲染视图

- `07-scope-segments.md`

## 3. `persist_semantic_source_units`

- 由 LLM 读取 raw segmentation 后提交结构化 payload。
- payload 至少包含：
  - `units`
- 每个 unit 至少包含：
  - `unit_id`
  - `unit_title`
  - `unit_kind`
  - `summary`
  - `member_segment_ids`
- 可选：
  - `elements`

### 作用

- 将 raw blocks 合并/拆分为真正可供 Stage 5 / 6 使用的语义写作单元
- 给每个 unit 写出最小语义摘要
- 将 supporting elements 线索吸收到 unit 层
- semantic unit 可以混合 main 和 aux 的 raw members，但成员必须保留 role 标记

### 写入真源

- `semantic_source_units`
- `semantic_source_unit_members`
- `semantic_source_unit_elements`

### 渲染视图

- `08-semantic-source-units.md`

## 完成标准

- manuscript analysis 已写库
- `raw_scope_segments` 已落库
- `semantic_source_units` 已落库
- 若仍有理解层待确认事项，必须写入 `pending_confirmations`

## 禁止事项

- 不得跳过 `persist_raw_scope_segments`
- 不得把脚本切出的 raw blocks 直接当作最终写作真源
- 不得跳过 `persist_semantic_source_units`
- 不得把 semantic consolidation 只留在聊天上下文
- 不得让脚本决定哪些段应合并成论证单元

# Stage 2 Playbook

Stage 2 对应 `stage_2_manuscript_analysis`。

## 正式写库动作

1. `confirm_language_context`
2. `persist_runtime_template_translation`（仅当工作语言不是 `zh/en`）
3. `persist_manuscript_analysis`
4. `persist_raw_scope_segments`
5. `persist_semantic_source_units`

## 1. `confirm_language_context`

### Minimal Payload Example

```json
{
  "working_language": "Chinese",
  "target_language": "English"
}
```

### Notes

- `working_language` 由 Agent 优先从当前用户 prompt 推断，再交给用户确认。
- `target_language` 在 Stage 2 只是初始值；Stage 3 会根据最终体例/模板覆盖它。
- 该动作完成后立即处理工作区模板副本：
  - `zh/en`：直接复制预置模板集
  - 其他语言：先复制 English 基础模板，再进入 `persist_runtime_template_translation`

### 作用

- 固定后续运行态文本内容的统一工作语言
- 初始化工作区 `render-templates/`
- 为 Stage 3 的最终目标语言覆盖提供初值

## 2. `persist_runtime_template_translation`

### Minimal Payload Example

```json
{
  "templates": {
    "01-agent-resume.md.j2": "# 请将该模板翻译为工作语言\\n",
    "02-manuscript-profile.md.j2": "# 请将该模板翻译为工作语言\\n"
  }
}
```

### Notes

- 仅当 `working_language` 不在 `zh/en` 时才会出现这个动作。
- payload 必须覆盖整套运行时模板文件，而不是只翻译一部分。
- 完成前不得继续 Stage 2。

## 3. `persist_manuscript_analysis`

### Minimal Payload Example

```json
{
  "main_scope": "Methods and results chapter about tunnel boring data fusion",
  "main_scope_locator": {
    "mode": "line_range",
    "line_start": 120,
    "line_end": 420
  },
  "aux_scopes": [
    {
      "aux_id": "aux-background",
      "label": "General background and related work",
      "purpose": "Support introduction and positioning",
      "locator": {
        "mode": "line_range",
        "line_start": 1,
        "line_end": 119
      }
    }
  ],
  "topic": "TBM tunneling state recognition with multimodal data fusion",
  "main_work": [
    "Define the journal-facing problem statement",
    "Summarize the core multimodal method"
  ],
  "novelty": [
    "Joint use of muck morphology and surrounding-rock context"
  ],
  "section_outline": [
    "Background",
    "Method",
    "Experiments"
  ],
  "removable_candidates": [
    "Thesis-style tutorial exposition"
  ],
  "open_questions": []
}
```

### Notes

- 由 LLM 生成 payload，再通过 `stage_runtime.py` 写库。
- `pending_confirmations` 仍可选；只有当前阶段确实存在待确认项时再加。

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

## 4. `persist_raw_scope_segments`

### Minimal Payload Example

No payload; only `--artifact-root`.

### Notes

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

- `04-scope-segments.md`

## 5. `persist_semantic_source_units`

### Minimal Payload Example

```json
{
  "units": [
    {
      "unit_id": "u01",
      "unit_title": "Research motivation and gap",
      "unit_kind": "argument",
      "summary": "Why the journal paper is needed and what gap it addresses.",
      "member_segment_ids": [
        "seg-0001",
        "seg-0002"
      ],
      "elements": []
    }
  ]
}
```

### Notes

- 由 LLM 读取 raw segmentation 后提交结构化 payload。
- `elements` 可选；只有该 unit 明确吸收图表、citation 或 bibliography 线索时再写。

### 作用

- 将 raw blocks 合并/拆分为真正可供 Stage 4 / 5 使用的语义写作单元
- 给每个 unit 写出最小语义摘要
- 将 supporting elements 线索吸收到 unit 层
- semantic unit 可以混合 main 和 aux 的 raw members，但成员必须保留 role 标记

### 写入真源

- `semantic_source_units`
- `semantic_source_unit_members`
- `semantic_source_unit_elements`

### 渲染视图

- `05-semantic-source-units.md`

## 完成标准

- manuscript analysis 已写库
- `working_language` 与初始 `target_language` 已确认
- 工作区模板副本已就绪
- `raw_scope_segments` 已落库
- `semantic_source_units` 已落库
- 若仍有理解层待确认事项，必须写入 `pending_confirmations`

## 禁止事项

- 不得在语言上下文未确认时继续 Stage 2 的后续步骤
- 不得在工作区模板副本未就绪时继续生成新的只读视图
- 不得跳过 `persist_raw_scope_segments`
- 不得把脚本切出的 raw blocks 直接当作最终写作真源
- 不得跳过 `persist_semantic_source_units`
- 不得把 semantic consolidation 只留在聊天上下文
- 不得让脚本决定哪些段应合并成论证单元

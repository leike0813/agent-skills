# Stage 6 Playbook

Stage 6 对应 `stage_6_final_drafting`。

## 正式写库动作

1. `prepare_section_drafting`
2. `persist_section_draft`
3. `approve_section_draft`
4. `persist_output_target`
5. `render_final_output_bundle`

## 执行顺序

### 1. `prepare_section_drafting`

- 根据 `section_rewrite_plan` 找到下一个未批准 section
- 通过 gate 暴露 `active_section_id`
- 重渲染 `10-section-drafting-board.md`

### 2. `persist_section_draft`

- 只允许针对 `active_section_id` 写库
- 必须提交：
  - `section_id`
  - `draft_tex`
  - `source_refs`
- `source_refs` 只允许引用 `semantic_unit:<unit_id>`
- 脚本会：
  - 计算实际字数
  - 按计划值执行 `±15%` 容差校验
  - 写入 provenance 与事件日志
  - 渲染 `section-reviews/<section_order>-<section_id>.md`

### 3. `approve_section_draft`

- 用户必须显式批准或驳回当前 section
- 驳回后，gate 退回 `persist_section_draft`
- 批准后，gate 才能推进到下一节

### 4. `persist_output_target`

- 仅在所有 section 均已批准后才允许执行
- 若用户未指定目录，默认当前工作目录
- 输出目录选择必须写库

### 5. `render_final_output_bundle`

- 仅在输出目录确认后才允许执行
- 脚本负责：
  - 装配最终 `final-draft.tex`
  - 生成最终 `rewrite-report.md`
  - 复制实际引用图片到 `<output_dir>/images/`
  - 改写图像路径为 `images/<filename>`

## Section 审阅工件

每个 section 的审阅工件必须至少包含：

- 当前 section 转写结果
- planned vs actual count
- 使用到的 semantic source units
- 每个 semantic unit 的 main/aux 构成
- 通过 semantic source units 间接追溯到的图 / 表 / citation / bibliography 参照
- 本轮撰写事件记录

## 完成标准

- 所有 section 均已获批准
- 输出目录已确认
- `final-draft.tex` 与 `rewrite-report.md` 已渲染
- 若最终稿使用图片，输出目录下的 `images/` 已准备好

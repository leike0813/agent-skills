# Stage 5 Playbook

Stage 5 对应 `stage_5_final_drafting`。

## 正式写库动作

1. `prepare_section_drafting`
2. `persist_section_draft`
3. `approve_section_draft`
4. `persist_output_target`
5. `persist_translated_sections`
6. `render_final_output_bundle`

## 执行顺序

### 1. `prepare_section_drafting`

### Minimal Payload Example

No payload; only `--artifact-root`.

### Notes

- 根据 `section_rewrite_plan` 找到下一个未批准 section。
- 通过 gate 暴露 `active_section_id`。
- 重渲染 `11-section-drafting-board.md`。

### 2. `persist_section_draft`

### Minimal Payload Example

```json
{
  "section_id": "sec-introduction",
  "draft_tex": "\\section{Introduction}\nThis paper addresses ...",
  "source_refs": [
    {
      "source_kind": "semantic_unit",
      "source_ref": "u01",
      "usage_note": ""
    }
  ]
}
```

### Notes

- 只允许针对 `active_section_id` 写库。
- `draft_tex` 应始终使用当前 `working_language`。
- `source_refs` 只允许引用 `semantic_unit:<unit_id>`。
- 脚本会：
  - 计算实际字数
  - 按计划值执行 `±15%` 容差校验
  - 写入 provenance 与事件日志
  - 渲染 `section-reviews/<section_order>-<section_id>.md`

### 3. `approve_section_draft`

### Minimal Payload Example

```json
{
  "section_id": "sec-introduction",
  "approved": true
}
```

### Notes

- 用户必须显式批准或驳回当前 section。
- 驳回后，gate 退回 `persist_section_draft`。
- 批准后，gate 才能推进到下一节。

### 4. `persist_output_target`

### Minimal Payload Example

```json
{
  "user_confirmed": true,
  "output_dir": "./journal-paper-output"
}
```

### Notes

- 仅在所有 section 均已批准后才允许执行。
- 若用户未指定目录，默认当前工作目录。
- 输出目录选择必须写库。

### 5. `persist_translated_sections`

### Minimal Payload Example

```json
{
  "sections": [
    {
      "section_id": "sec-introduction",
      "translated_tex": "\\section{Introduction}\nThis paper addresses ...",
      "source_draft_updated_at": "2026-03-31T09:00:00+00:00"
    }
  ]
}
```

### Notes

- 仅在所有 section 均已批准，且输出目录已确认后才允许执行。
- 该动作把 working-language section drafts 翻译成最终 `target_language`。
- payload 必须覆盖全部已批准 section。
- `rewrite-report.md` 不在这一步翻译，仍保留为 `working_language`。

### 6. `render_final_output_bundle`

### Minimal Payload Example

No payload; only `--artifact-root`.

### Notes

- 仅在输出目录确认后才允许执行。
- 仅在 `persist_translated_sections` 完成后才允许执行。
- 脚本负责：
  - 装配最终 `final-draft.tex`
  - 生成最终 `rewrite-report.md`
  - 复制实际引用图片到 `<output_dir>/images/`
  - 改写图像路径为 `images/<filename>`
- 该动作是 assembly-only：
  - 只允许按 section 顺序装配已翻译的 `translated_sections`
  - 不允许改写 section 正文
  - 不允许新增未在 section drafts 中出现的论述
  - 不允许在最终渲染时顺手润色

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
- 所有已批准 section drafts 都已翻译为最终 `target_language`
- `final-draft.tex` 与 `rewrite-report.md` 已渲染
- 若最终稿使用图片，输出目录下的 `images/` 已准备好

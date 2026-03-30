# Stage 4 Playbook

Stage 4 对应 `stage_4_style_profile`。

## 唯一正式写库动作

- `persist_style_profile`

## Payload 要求

- `source_style`
- `problems_to_fix`
- `target_style_guidance`
- `open_questions`

可选：

- `pending_confirmations`

## 执行规则

- 风格画像的语义判断由 LLM 完成。
- 脚本只负责把 payload 写入 DB 并重渲染 `04-style-profile.md`。
- 若仍有风格边界待确认，必须显式进入 `pending_confirmations`。

## 完成标准

- style profile 已写库
- `04-style-profile.md` 已渲染
- 无阻塞推进的待确认事项

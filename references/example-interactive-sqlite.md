# Example: Interactive SQLite Skill

## What This Example Teaches

本样例基于 `review-master` 的设计抽象，用来说明：长程人机协作任务既需要 SQLite/gate 的强恢复能力，也需要清楚的用户确认门禁。它适合阶段多、用户决策多、最终产物需要完整追踪的交互式复杂 skill。

## When To Use This Pattern

适用于：

- 多轮、多阶段的人机协作，例如审稿修回、复杂计划制定、逐项处理反馈。
- 每个用户确认都会影响后续执行。
- 需要 revision log、决策记录、恢复包和最终执行指令。
- 上下文压缩后必须知道哪些问题已处理、哪些仍阻塞。

## Architecture Shape

推荐结构：

```text
skill-name/
├── SKILL.md
├── references/
│   ├── gate-and-render.md
│   ├── user-confirmation.md
│   ├── revision-log.md
│   └── resume-protocol.md
└── scripts/
    ├── gate_runtime.py
    ├── stage_runtime.py
    ├── render_review_packet.py
    └── render_final_outputs.py
```

## SKILL.md Design

主文件应该放：

- 交互阶段：导入、归类、策略、逐项确认、执行指令、最终核对。
- 用户确认门禁：哪些动作没有用户确认绝不能推进。
- SQLite 真源规则：用户决策、策略卡、修订记录必须结构化保存。
- gate-and-render 纪律：每轮先看 gate，给用户看的内容由 renderer 输出。
- resume protocol：上下文压缩后如何恢复当前未完成项。

主文件不应该放：

- 让 LLM 只凭对话历史记住用户已确认事项。
- 把用户确认变成可选建议。
- 把复杂交互压成一次性自动化流程。

## References / Scripts / Assets

- `references/user-confirmation.md`：写确认点、确认文本语义、拒绝和修改路径。
- `references/revision-log.md`：写决策记录、变更追踪和审计边界。
- `references/resume-protocol.md`：写恢复包字段、当前任务、未决 blocker。
- `scripts/gate_runtime.py`：返回下一步、待确认项、阻塞原因。
- `scripts/render_review_packet.py`：渲染给用户确认的只读包。
- `scripts/render_final_outputs.py`：从 DB 生成最终交付物。

## LLM vs Script Boundary

- LLM 负责理解用户反馈、归纳策略、提出选项、解释取舍。
- 脚本负责持久化用户确认、生成恢复包、渲染最终指令和日志。
- 禁止 LLM 手工拼 revision log 或把未确认内容标为已确认。

## Failure Modes Prevented

- 用户已确认的策略在后续轮次丢失。
- 未确认事项被 agent 自动推进。
- 长程协作中无法解释某个最终决策来自哪里。
- 上下文压缩后重复处理或漏处理条目。

## Do Not Copy

不要复制原示例的审稿修回领域流程、评论字段、策略卡字段或最终输出模板。可复用的是“长程交互 + 用户确认门禁 + SQLite 记录 + 恢复与渲染”的设计模式。

## Reusable Design Rules

- 交互式 SQLite skill 的核心是把用户决策变成可恢复的结构化状态。
- 用户确认门禁必须写成硬约束，而不是礼貌提醒。
- 给用户看的复杂状态应由 renderer 生成，避免 LLM 漏项或改写。
- revision log 不只是记录结果，也记录为什么这样决策。

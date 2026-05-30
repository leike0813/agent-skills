# Example: Gate-driven Writing Workflow

## What This Example Teaches

本样例基于 `paper-condenser` 的设计抽象，用来说明：当写作任务由多个强依赖阶段组成，且不能跳步时，可以使用 gate-driven workflow。gate 约束阶段推进，LLM 仍负责写作判断、取舍和与用户协商。

## When To Use This Pattern

适用于：

- 从大量材料中逐步提炼结构、章节、论证和成稿。
- 每一阶段依赖前一阶段的结构化产物。
- 跳过阶段会导致后续写作失真或重复返工。
- 需要只读视图帮助用户确认，但最终真源不能靠 LLM 记忆。

## Architecture Shape

推荐结构：

```text
skill-name/
├── SKILL.md
├── references/
│   ├── gate-runtime.md
│   ├── stage-playbooks.md
│   └── writing-negotiation.md
└── scripts/
    ├── gate_runtime.py
    ├── stage_runtime.py
    └── render_views.py
```

如果阶段产物多、恢复要求强，可以进一步引入 SQLite 作为运行态真源。

## SKILL.md Design

主文件应该放：

- gate 纪律：首次进入和每次写入后运行 gate。
- 合法阶段列表和禁止跳步规则。
- 每个阶段的目标，而不是每个阶段的全部写作细节。
- 用户确认点：结构、范围、章节策略、重要取舍。
- 脚本调用示例和 `next_action` 的含义。
- 只读视图和正式写入真源的区别。

主文件不应该放：

- 大量写作模板。
- 让 LLM 凭记忆推进完成状态。
- 把 gate 的 `next_action` 当作建议而非约束。

## References / Scripts / Assets

- `references/gate-runtime.md`：写 gate 返回字段、blocker、repair。
- `references/stage-playbooks.md`：写每一阶段的 payload 语义、正例和反例。
- `references/writing-negotiation.md`：写用户确认、风格选择和冲突处理。
- `scripts/gate_runtime.py`：决定当前阶段和下一步。
- `scripts/stage_runtime.py`：验证 payload 并写入真源。
- `scripts/render_views.py`：生成只读视图供审阅和恢复。

## LLM vs Script Boundary

- LLM 负责阅读材料、提出结构、写作、解释取舍、与用户协商。
- 脚本负责判断阶段、校验 payload、写入状态、渲染只读视图。
- 禁止 LLM 手工标记阶段完成或伪造脚本渲染结果。

## Failure Modes Prevented

- agent 跳过关键分析阶段直接写稿。
- 上下文压缩后忘记已确认结构。
- 用户确认内容与后续写作输入不一致。
- 只读视图被误当成可编辑真源。

## Do Not Copy

不要复制原示例的论文压缩业务流程、章节模型、数据库字段或写作模板。可复用的是“gate 控制阶段 + LLM 主导写作语义 + 只读视图恢复”的设计方法。

## Reusable Design Rules

- gate-driven workflow 的核心是防跳步，不是把所有判断脚本化。
- `next_action` 必须可枚举，并且每个动作都有 payload 说明。
- 用户确认结果应进入真源或结构化记录，而不是只留在对话里。
- 只读视图用于恢复和审阅，不能成为写入入口。

# Example: Automation SQLite Skill

## What This Example Teaches

本样例基于 `literature-digest` 的设计抽象，用来说明：高度自动化、长程、弱模型友好的 skill 需要强契约。SQLite 作为唯一运行态真源，gate 约束执行，renderer 生成最终产物，stdout JSON 保持机器可消费。

## When To Use This Pattern

适用于：

- 后台批处理，不允许频繁向用户提问。
- 多阶段抽取、分析、渲染，且中间产物会被后续阶段反复使用。
- 输出被 runner、下游系统或另一个 skill 消费。
- 弱模型也必须按固定轨道执行，不能依赖复杂临场判断。
- 上下文压缩后必须继续运行。

## Architecture Shape

推荐结构：

```text
skill-name/
├── SKILL.md
├── assets/
│   ├── input.schema.json
│   └── output.schema.json
├── references/
│   ├── runtime-contract.md
│   ├── stage-playbooks.md
│   └── failure-recovery.md
└── scripts/
    ├── gate_runtime.py
    ├── stage_runtime.py
    ├── render_outputs.py
    └── validate_contract.py
```

## SKILL.md Design

主文件应该放：

- 非交互或低交互原则。
- stdout 成功/失败 JSON 硬契约。
- SQLite 真源边界：什么必须写库，什么只能渲染。
- gate-first 纪律和每步脚本调用示例。
- 弱模型友好的执行规则：按 gate 读 reference、按 payload 写入、不要自由发挥。
- 最终产物必须由 renderer 生成。

主文件不应该放：

- 让 agent 手拼最终 JSON/Markdown bundle。
- 需要大量用户协商的交互步骤。
- 未枚举的状态值、阶段名或失败码。

## References / Scripts / Assets

- `assets/input.schema.json` / `assets/output.schema.json`：定义机器契约。
- `references/runtime-contract.md`：写 DB、workspace、stdout、artifact 边界。
- `references/stage-playbooks.md`：写每个阶段的 payload 语义和正反例。
- `references/failure-recovery.md`：写 blocker、repair、resume packet。
- `scripts/gate_runtime.py`：返回 `next_action`、所需 reference、blocker 和命令示例。
- `scripts/render_outputs.py`：从 DB 生成最终权威产物。

## LLM vs Script Boundary

- LLM 负责语义抽取、判断材料含义、生成阶段 payload。
- 脚本负责状态推进、schema 校验、DB 写入、stdout JSON、最终渲染。
- 禁止 LLM 绕过 DB 直接生成最终机器消费产物。

## Failure Modes Prevented

- 长程任务中上下文压缩后无法恢复。
- 弱模型忘记阶段纪律或遗漏 required fields。
- stdout 混入解释文字导致 runner 解析失败。
- 最终产物与中间状态不一致。

## Do Not Copy

不要复制原示例的文献 digest 业务字段、分析阶段、数据库 schema 或脚本源码。可复用的是“自动化硬契约 + SQLite SSOT + gate + renderer + 弱模型友好”的架构模式。

## Reusable Design Rules

- 机器消费输出必须有成功和失败 shape。
- 长程自动化任务的最终公开产物应由脚本从真源渲染。
- gate 返回应尽量包含下一步所需 instruction refs 和命令示例。
- 弱模型友好来自窄动作、强枚举、结构化 payload 和少量自由裁量。

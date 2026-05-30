# Example: Interactive Evidence Skill

## What This Example Teaches

本样例基于 `literature-explainer` 的设计抽象，用来说明：中等复杂交互式 skill 可以采用轻状态机、记忆和证据验证，而不必默认上 SQLite。它适合“用户持续提问、LLM 做语义理解、脚本辅助记忆和证据边界”的任务。

## When To Use This Pattern

适用于：

- 用户围绕一个材料持续问答、追问、要求解释或生成学习笔记。
- 需要保留会话内问题、已引用证据、用户关注点。
- 输出质量依赖证据约束，但流程不需要强制多阶段写库。
- 用户交互是核心体验，而不是后台自动化。

## Architecture Shape

推荐结构：

```text
skill-name/
├── SKILL.md
├── references/
│   ├── evidence-rules.md
│   └── interaction-playbook.md
└── scripts/
    ├── memory_runtime.py         # 可选
    └── evidence_check.py         # 可选
```

状态可以是轻量文件、会话摘要或脚本维护的 memory，不必直接升级为 SQLite。

## SKILL.md Design

主文件应该放：

- 交互状态：载入材料、确认问题、回答、追问、生成笔记、结束。
- 证据纪律：回答必须基于可定位材料；不确定时说明缺口。
- 记忆使用规则：什么写入、何时读取、何时不信任旧记忆。
- 用户确认点：材料不完整、问题过宽、需要风格选择时才问。
- 脚本调用示例，如果 memory 或 evidence checker 是正式执行路径。

主文件不应该放：

- 全部论文理解方法或领域知识。
- 将证据验证脚本误写成语义判断器。
- 要求每轮都读取所有 reference。

## References / Scripts / Assets

- `references/evidence-rules.md`：写证据引用、缺证处理、禁止臆测。
- `references/interaction-playbook.md`：写不同问题类型的回答流程。
- `scripts/memory_runtime.py`：可记录会话摘要、问题历史、用户偏好。
- `scripts/evidence_check.py`：可验证引用位置、证据片段是否存在。

## LLM vs Script Boundary

- LLM 负责理解材料、回答问题、判断证据是否支持结论。
- 脚本负责检索已记录记忆、检查引用格式、确认证据片段存在。
- 禁止让脚本总结论文或替代 LLM 判断“这个证据是否足够支持回答”。

## Failure Modes Prevented

- 多轮对话中重复询问用户已经提供的信息。
- 回答看似充分但没有材料证据。
- 轻量交互任务被 SQLite/gate 压得过重。
- 旧记忆污染新回答，且没有证据复核。

## Do Not Copy

不要复制原示例的论文问答业务流程、字段名、证据格式或具体脚本实现。可复用的是“轻状态 + 证据边界 + 交互循环”的架构取舍。

## Reusable Design Rules

- 交互式中等 skill 要先保护对话体验，再增加状态工具。
- 记忆不是事实真源；证据材料才是回答依据。
- 证据验证脚本只能做确定性检查，不能替代语义判断。
- 只有当跨上下文恢复和阶段依赖变强时，才升级到 gate/SQLite。

# Example: Simple Contract Skill

## What This Example Teaches

本样例基于 `tag-regulator` 的设计抽象，用来说明：当任务很窄、输出稳定、交互很少时，高质量 skill 可以保持轻量。重点不是流程控制，而是把输入、输出、约束、合法值和失败边界写清楚。

## When To Use This Pattern

适用于：

- 标签规范化、字段归一、短文本分类、格式转换等单一动作。
- 输出需要稳定 JSON 或固定结构文本。
- 不需要跨轮状态，也不需要多阶段恢复。
- 脚本只负责校验、排序、整形，不负责语义判断。

## Architecture Shape

推荐结构：

```text
skill-name/
├── SKILL.md
├── assets/
│   └── output.schema.json        # 可选
└── scripts/
    └── validate_output.py        # 可选
```

如果 schema 和脚本都不是必要条件，可以只保留 `SKILL.md`。

## SKILL.md Design

主文件应该放：

- 任务目标和不适用场景。
- 输入字段、可选字段、默认行为。
- 输出对象的稳定 shape。
- 枚举值、受控词表或规范化规则。
- 执行顺序：理解输入、映射、检查合法性、输出。
- 至少一个合法示例和一个 near-miss 示例。
- 脚本调用示例，如果存在正式脚本。

主文件不应该放：

- 长篇领域背景。
- 多阶段状态机。
- SQLite 或 gate 纪律。
- 会让简单任务变慢的复杂恢复机制。

## References / Scripts / Assets

- `references/`：只有当规则、术语或示例太多时才添加。
- `scripts/`：适合做 JSON schema 校验、枚举校验、稳定排序、字段补齐。
- `assets/`：适合放 schema、受控词表或 runner contract。

## LLM vs Script Boundary

- LLM 负责判断输入语义、选择最合适的规范项、解释近义标签。
- 脚本负责检查输出字段是否存在、枚举是否合法、JSON 是否可解析。
- 禁止用脚本做语义相似度偷懒，除非 skill 明确把相似度算法作为确定性策略。

## Failure Modes Prevented

- 输出字段漂移，导致下游无法解析。
- 枚举值拼写不一致。
- 简单任务被过度工程化，agent 把时间花在维护无意义状态上。
- LLM 自由解释输出格式，混入 Markdown fence、说明文字或多余字段。

## Do Not Copy

不要复制原示例的具体领域词表、标签含义、Zotero 语境或业务字段。可复用的是“轻量契约 + 稳定输出 + 可选校验脚本”的设计方式。

## Reusable Design Rules

- 简单 skill 的质量来自契约清楚，不来自文件多。
- 输出被机器消费时，即使任务简单，也要写成功和失败 shape。
- 有脚本就必须给命令示例；无脚本也要给可手工检查的输出示例。
- 先证明 Prompt Skill 不够，再升级到 reference-backed 或 script-assisted。

# Complexity Model

## Purpose

先判断 skill 应该多厚，再决定文件结构。错误的厚度会导致两类失败：

- 简单任务被过度工程化，agent 花大量 token 维护无意义的状态。
- 长程任务被写成普通提示词，遇到上下文压缩、跳步、输出不稳定时无法恢复。

## Classification Questions

按顺序回答：

1. **任务跨度**
   - 单一动作还是多阶段工作流？
   - 阶段之间是否有强依赖？

2. **交互需求**
   - 是否必须向用户确认策略、范围、语言、取舍或阶段成果？
   - 是否允许非交互后台运行？

3. **状态需求**
   - 是否需要跨轮保存中间产物？
   - 上下文压缩后是否必须恢复执行？
   - 是否需要唯一运行态真源？

4. **输出稳定性**
   - 输出是否被机器消费？
   - 是否必须固定 schema、字段、目录和文件名？
   - 是否需要弱模型也能稳定执行？

5. **脚本需求**
   - 哪些步骤是确定性、重复性、可验证的？
   - 哪些步骤必须由 LLM 做语义判断？

6. **失败成本**
   - 跳步、错写、漏字段、误删内容的成本高不高？
   - 是否需要 gate 阻止错误推进？

## Tiers

### Tier 1: Simple Contract Skill

适合：

- 单一语义转换或规范化任务。
- 输出 schema 固定。
- 几乎不需要用户交互。
- 状态不需要跨轮保存。

推荐：

- 单一 `SKILL.md`。
- 清楚写目标、输入、输出、强约束、执行步骤、示例、失败示例。
- 可选轻量脚本做输入校验或输出整形。

说明性样例：[example-simple-contract.md](example-simple-contract.md)。

### Tier 2: Reference-backed Skill

适合：

- 任务本身不长，但有较多规则、术语、示例或领域文档。
- 细节不应全部塞进 `SKILL.md`。

推荐：

- `SKILL.md` 只保留主路径和关键约束。
- `references/` 按主题拆分，全部由 `SKILL.md` 直接链接。
- 每个 reference 有明确读取时机。

### Tier 3: Script-assisted Workflow Skill

适合：

- 有明确步骤，部分步骤可由脚本稳定完成。
- payload 结构较复杂，但不需要完整 SQLite runtime。

推荐：

- `SKILL.md` 写阶段顺序和最小调用示例。
- `references/` 写分步细则、正例、反例、字段语义。
- `scripts/` 负责校验、格式化、文件分发、确定性处理。
- 对枚举值、payload 字段、目录约定显式列出。

### Tier 4: Interactive Medium Workflow

适合：

- 需要用户持续提问、确认或协商。
- 需要轻量记忆、证据验证或会话内状态。
- 但流程不至于必须用强 gate 和数据库约束每一步。

推荐：

- 主状态机写在 `SKILL.md`。
- 记忆/验证脚本辅助，但 LLM 仍控制语义与交互。
- 每轮输出后有回到意图确认或继续当前循环的规则。

说明性样例：[example-interactive-evidence.md](example-interactive-evidence.md)。

### Tier 5: Gate-driven Long Workflow

适合：

- 多阶段强依赖。
- 跳步会损坏后续结果。
- 需要只读视图、恢复包或 gate 返回 `next_action`。

推荐：

- gate 脚本是唯一合法恢复与下一步判定入口。
- 每次正式写入后重新运行 gate。
- `SKILL.md` 只写核心纪律、阶段概览和 reference 路由。
- 详细 payload 放在 gate 返回示例或 stage playbook 中。

说明性样例：[example-gate-driven-writing.md](example-gate-driven-writing.md)。

### Tier 6: SQLite State-machine Skill

适合：

- 长程、可恢复、强输出稳定性。
- 后台自动化或弱模型友好。
- 需要最终产物由 DB 渲染而不是 LLM 手拼。

推荐：

- SQLite 作为唯一运行态真源。
- gate 负责状态、blocker、repair、`next_action`。
- stage runtime 负责结构化写库。
- renderer 从 DB 生成最终公开产物。
- resume packet 和只读视图服务上下文压缩恢复。

说明性样例：

- 自动化长程任务：[example-automation-sqlite.md](example-automation-sqlite.md)。
- 交互式长程任务：[example-interactive-sqlite.md](example-interactive-sqlite.md)。

### Tier 7: Automation-facing Skill

适合：

- skill 被上游 runner 调用，或输出给下游 skill/系统消费。
- 输出错误会污染后续流程。

推荐：

- `assets/` 放 JSON Schema 或 runner contract。
- `SKILL.md` 写 stdout/artifact 硬契约。
- reference 写合法/非法 payload 示例和枚举值。
- 脚本做 schema validation 和稳定排序/渲染。

说明性样例：

- 简单机器契约：[example-simple-contract.md](example-simple-contract.md)。
- 长程自动化契约：[example-automation-sqlite.md](example-automation-sqlite.md)。

## Decision Rule

选择最低但足够的 tier。只有出现下列信号时才升级：

- 需要跨上下文恢复。
- 阶段依赖强，跳步成本高。
- 输出被机器消费且必须稳定。
- 需要弱模型也能按固定轨道执行。
- 过程数据必须成为后续步骤唯一真源。

## Upgrade Signals

出现这些信号时，提高架构厚度：

- 用户要求“可恢复”“跨会话继续”“中途不要丢状态”。
- 任务包含多个必须按顺序完成的阶段，并且后续阶段依赖前序决策。
- 输出被 runner、另一个 agent、MCP、脚本或外部系统消费。
- 失败代价高，例如漏掉引用、误删稿件、污染标签库、错写数据库。
- 同一类确定性动作会反复出现，例如校验 payload、渲染 bundle、生成索引。
- 用户明确要求弱模型也能稳定执行。

## Downgrade Signals

出现这些信号时，不要上重型架构：

- 任务只需一次性回答或单次转换。
- 没有跨轮状态，也没有强恢复要求。
- 输出只给人读，格式不需要机器稳定解析。
- 脚本只能做很少的校验或排序。
- 用户更看重快速轻量，而不是完整工作流。

## Anti-overengineering Rule

SQLite、gate、renderer 是解决长程可靠性的工具，不是高质量 skill 的默认标配。若无法说清“没有它会发生什么具体失败”，就先不要引入。

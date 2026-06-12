# Skill Writing Playbook

## Purpose

本文件用于把设计判断落成可执行的 `SKILL.md`。读它的时机：已经完成复杂度判断，准备写 frontmatter、description、主章节、示例和反例。

## Frontmatter

必需字段：

```yaml
---
name: skill-name
description: Capability summary. Use when ...
---
```

规则：

- `name` 使用 kebab-case，和目录名一致。
- `description` 是触发接口，必须写“做什么”和“什么时候用”。
- 不要把触发条件只写在正文；正文加载时已经触发了。
- description 不要过短，例如 “Helps with PDFs” 不合格。
- description 也不要无限泛化，避免抢占相邻 skill。
- 通用 frontmatter 优先保持可移植；产品特定字段应作为目标环境扩展处理，不要和通用运行时指令混在一起。

## Description Formula

推荐结构：

```text
<Does what>. Use when <user/task contexts>, including <synonyms, artifacts, workflows, failure modes>.
```

应覆盖：

- 用户会说的动作词：create, update, review, extract, convert, validate, debug。
- 任务对象：skills, SKILL.md, scripts, schemas, state machines。
- 近义场景：turn this workflow into a skill, improve this skill, audit this skill。
- 边界场景：long-horizon, automation-facing, SQLite-backed, gate-driven。

## Description Trigger Optimization

`description` 可以适度主动，避免 agent 在复杂、专业或长程任务中 undertrigger。但主动不等于泛化到抢占相邻 skill。

优化触发时准备两类查询：

- `should-trigger`：真实用户会说的正例，覆盖正式/口语、不同工件、不同复杂度和不直接点名 skill 的说法。
- `should-not-trigger`：共享关键词但不该触发的 near-miss，例如相邻领域、简单到无需 skill 的任务、应由其它 skill 处理的任务。

触发查询集可用于改写 description，但不等同于正式 benchmark。正式评估反馈迭代必须满足用户同意、子代理可用、输入输出可评价三个硬条件。

## Source-backed Authoring

当 skill 来自用户经验、已有 skill、外部文档、第三方工具或失败记录时，先写清设计来源，再落稿。

最小记录：

- 哪些来源已经足够支撑设计。
- 哪些缺口会影响架构厚度、输出契约或脚本边界。
- 哪些规则来自重复失败，而不是主观偏好。
- 哪些地方仍需用户确认。

这不是默认的重型 research 流程。简单、低风险、单一契约 skill 可以只记录“来源足够，按轻量设计继续”。但如果来源不足，不要用模板填空伪装确定性。

## Current-state Only Writing

最终 `SKILL.md` 只呈现当前有效协议。更新 skill 时，直接重写字段、流程、脚本入口和输出契约，不保留历史演进说明。

必须删除或改写：

- 旧字段、旧命令、旧目录、旧流程仍可继续使用的说明。
- 兼容 fallback、legacy fallback、deprecated path、previous version behavior。
- “不要使用以前的 X”“曾经如何处理”“旧版如何处理”这类历史提醒。
- changelog、版本对比、迁移说明、过渡期说明。

如果旧调用方仍需要支持，把它设计成外部 adapter、上游转换或单独迁移任务。skill 运行时指令本身只描述当前入口和当前契约。

允许保留的是 runtime 概念，例如 state machine 的状态迁移、gate 的状态推进、恢复协议、发布到他人环境前的安全检查。这些不是历史协议说明。

## Template Selection

模板是写作支架，不是架构判断的替代品。先完成复杂度判断，再读取最少数量的模板。

所有 skill 从 [templates/minimal-skill-template.md](templates/minimal-skill-template.md) 起步。根据复杂度叠加扩展：

| Skill shape | Template combination |
| --- | --- |
| Simple contract | minimal only |
| Reference-backed | minimal + [templates/reference-backed-extension.md](templates/reference-backed-extension.md) |
| Script-assisted | minimal + [templates/script-assisted-extension.md](templates/script-assisted-extension.md) |
| Gate-driven | minimal + reference-backed + script-assisted + [templates/gate-driven-extension.md](templates/gate-driven-extension.md) |
| SQLite state-machine | minimal + reference-backed + script-assisted + gate-driven + [templates/sqlite-state-machine-extension.md](templates/sqlite-state-machine-extension.md) |
| Automation-facing | minimal + [templates/automation-facing-extension.md](templates/automation-facing-extension.md), plus any architecture extensions needed |

组合规则：

- 只读当前架构需要的模板，不要启动时通读全部模板。
- 扩展模板只补充章节；不要重复 minimal 中已有的 Mission、Inputs、Workflow。
- 如果两个模板都包含类似约束，以更具体的运行时契约为准，并合并成一个清楚章节。
- automation-facing 是叠加维度，不是单独复杂度；简单 JSON skill 可以是 minimal + automation extension，长程 runner skill 可以再叠加 gate/SQLite extension。

## Freedom Calibration

写 `SKILL.md` 前先判断目标任务需要多少自由度：

| Freedom | 适用场景 | 写法 |
| --- | --- | --- |
| High | 开放式写作、策略、解释、研究判断 | 写原则、偏好、反例和边界，保留 LLM 语义空间 |
| Medium | 有稳定流程但允许上下文调整 | 写阶段、检查点、payload 约定和脚本候选 |
| Low | 易错、可验证、强契约、机器消费 | 写正式脚本、schema、gate、枚举值和禁止绕过规则 |

任务越脆弱、越可验证、越容易造成不可逆副作用，越应降低自由度。开放式任务不要用脚本或硬 schema 过度约束。

## Body Structure By Complexity

模板组合后，目标 `SKILL.md` 至少应包含以下运行时能力。

### Simple Skill

来自 minimal 模板：

- Mission / Purpose
- When To Use / Do Not Use
- Inputs
- Workflow
- Constraints
- Output Contract
- Examples
- Failure Handling

### Reference-backed Skill

在 simple 基础上增加：

- Operating Modes 或 Routing Decision
- Reference Loading Guide
- Main File / Reference Boundary
- 明确的 reference 读取时机

### Script-assisted Skill

在 simple 或 reference-backed 基础上增加：

- Formal Entrypoints
- Script Call Examples
- Payload Examples
- LLM And Script Responsibilities
- Script Failure Handling

### Gate / SQLite Skill

在 script-assisted 基础上增加：

- Runtime Model
- Gate Discipline
- Valid `next_action` set
- State Machine
- Resume Protocol
- Read-only Views
- DB / Renderer Authority
- Repair / Failure Recovery

### Automation-facing Skill

在对应架构基础上增加：

- Automation Contract
- Input Schema
- Success Output
- Failure Output
- Directory Protocol
- Validation

## Examples And Anti-examples

每个 skill 至少应该有一种锚定示例。复杂度越高，示例越应覆盖失败路径。

简单输出型 skill：

- 成功输入/输出。
- 非法输入/失败输出。
- near-miss：看起来相关但不应触发或不应处理的情况。

脚本型 skill：

- 最小命令。
- 最小 payload。
- 典型非法 payload。
- 脚本失败后 agent 应做什么。

长程 skill：

- 首次进入。
- 恢复进入。
- gate blocker。
- 用户确认未完成。
- 最终渲染。

## Validation And Iteration Planning

简单 skill 通常只需要轻量验收：

- 2-3 个真实用户式 prompts。
- 每个 prompt 配一个 expected output 或 failure shape。
- 至少覆盖一个 near-miss。

复杂 skill 才考虑正式评估反馈迭代。正式迭代前必须记录：

- 用户是否明确同意。
- 当前环境是否可以调用子代理或等价独立执行器。
- 输入是否可模拟/可获取，输出是否可由用户、规则、schema 或脚本评价。

任一条件不满足时，不要设计 with-skill / baseline 的正式对照流程。改用人工 review checklist、轻量 prompts、trigger queries 或要求用户补充样例输入和评价标准。

如果多个验收场景都让 agent 重复临时写同类脚本，应把该动作列为正式 script candidate。

## Writing Rules

- 写给未来执行任务的 agent，不是写给人类读者做介绍。
- 用“必须做什么/何时做/不要做什么/失败后怎么办”的形式组织。
- 示例应锚定真实错误模式，不要只放理想 happy path。
- 对于容易被误用的规则，说明原因。
- 不要把所有内容塞进 `SKILL.md`；超过运行时常用范围的细节进入 references。
- 使用模板后必须改写为具体运行时指令；不要保留模板解释、占位符或 authoring hints。
- 只写 agent 不会自然知道、且对稳定完成任务有帮助的信息。
- 需要在执行过程中由 agent 填写的内容，可以提供 payload schema 及样例，由脚本校验 payload 合法性，避免 agent 随意发挥。
- 如果 payload 有枚举值，显式列出；不要让 agent 自行猜。
- payload 应尽量扁平化，字段名称应具有语义自明性，避免容易导致误解的字段名。
- 长程任务的阶段划分应以 agent 的决策点为依据，不需要 agent 决策的流程不应切分、不应中断，不应让 agent 仅成为驱动脚本执行的工具。
- 产品特定元数据如 `agents/openai.yaml` 只在目标环境需要时设计，不写进通用 frontmatter。
- 产品特定 metadata、hooks、tool permissions 或默认 prompt 不能替代 `SKILL.md` 的核心运行时指令。
- 只写当前有效协议；更新 skill 时删除历史说明、旧字段兼容、fallback 提醒、版本对比和迁移说明。

## Template Cleanup

落稿前必须删除：

- 所有 `<<...>>` 占位符。
- “Authoring Rules”“Authoring hint”“Use When” 等模板说明。
- 不适用于当前 skill 的章节。
- 空表格、空枚举、空 payload 示例。

落稿前必须补齐：

- frontmatter `name` 和 `description`。
- 第一步可执行的 workflow。
- 对应复杂度的扩展契约，例如脚本命令、gate 入口、schema shape 或恢复协议。
- 至少一个 happy path 和一个 near-miss / failure 行为。

## Bad Patterns

- 只有愿景，没有步骤。
- 只有文件结构，没有何时读取每个 reference。
- 有 scripts 但没有命令示例。
- 有 schema 但没有成功/失败 JSON 示例。
- 说“按需询问用户”，但没写什么时候必须问。
- 说“使用数据库”，但没写真源、gate、恢复和渲染边界。
- 把公开发布前的安全/脱敏检查完全省略。
- 直接把模板原文作为最终 `SKILL.md`，残留 `<<...>>` 或 authoring hints。
- 没有用户同意、没有子代理或输出不可评价时，仍建议正式评估迭代。
- 为了显得完整创建 README、安装指南、变更日志、quick reference 或空资源目录。
- 把 `agents/openai.yaml` 当作所有 skill 的必备文件，或让它与 `SKILL.md` 描述的能力不一致。
- 在来源不足时直接套模板，把上游文档、失败记录或第三方工具限制留给未来 agent 猜。
- 把产品特定字段写成通用规范，导致 skill 在其它 agent 环境中不可移植。
- 在最终 skill 中保留 legacy、deprecated、old field、previous version、fallback、兼容、旧字段、以前、曾经等历史协议痕迹。
- 用“不要使用旧流程”替代删除旧流程，导致 agent 仍把旧协议加载进上下文。

## Final Pass

写完 `SKILL.md` 后，问：

- 另一个 agent 只读这个文件，能否知道第一步做什么？
- 它遇到复杂问题时，能否知道该读哪个 reference？
- 它会不会误用脚本做语义任务？
- 它会不会对简单任务过度设计？
- 它会不会对长程任务缺少恢复机制？
- 它的输出是否可被用户或下游系统验收？
- 它的关键设计结论是否有来源支撑，缺口是否显式记录？
- 公开或共享时，是否已经语义脱敏并暴露权限、依赖和副作用？
- 它是否只呈现当前有效协议，没有历史兼容、fallback、迁移说明或版本对比？

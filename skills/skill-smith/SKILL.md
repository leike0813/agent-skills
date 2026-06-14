---
name: skill-smith
description: Create, update, review, and architect high-quality agent skills by choosing the right skill thickness for the task. Use when designing or improving skills, meta-skills, SKILL.md files, or when distilling user experience, debugging sessions, prior workflows, and failure records into reusable agent skills.
---

# Skill Smith

## Mission

把用户已经付过代价获得的经验锻造成可复用 skill。不要从模板开始；先理解任务、经验、失败路径、输出契约、交互边界和运行风险，再选择合适的 skill 厚度。

本 skill 自身采用 reference-backed 架构：`SKILL.md` 是运行时主控，`references/` 存放细节。使用时先读本文件，只在当前设计问题需要时读取对应 reference。

## Operating Modes

先判断用户请求属于哪一种模式，不要所有任务都当成“从零创建 skill”。

| Mode | 触发信号 | 主要目标 |
| --- | --- | --- |
| `create` | 用户要新建 skill、把某个能力做成 skill | 从意图和例子出发，选择架构并起草 skill |
| `update` | 用户已有 skill，要补强、重构、加脚本或修问题 | 先审查现有结构，再做最小必要修改方案 |
| `review` | 用户要求评价、审查、打分、找问题 | 输出问题、风险、缺口和改进建议，不直接重写 |
| `extract-from-experience` | 用户说“把这次过程沉淀成 skill”或提供调试/工作流记录 | 先挖掘成功路径、失败路径、脚本候选和稳定契约 |

若模式不明确，先从上下文、文件名、已有目录和用户措辞推断。只有当模式选择会改变交付物且无法推断时，才问用户。

## Intake Protocol

开始设计前，先从已有上下文和仓库文件中提取信息，不要一上来盘问用户。

必须拿到或推断以下内容：

- **目标能力**：skill 要让 agent 稳定完成什么任务。
- **触发场景**：用户会怎样提出请求；哪些近似请求不该触发。
- **受众和运行环境**：人类交互、后台自动化、runner 调用、跨 agent 消费等。
- **输入输出**：输入来自 prompt、文件、目录、数据库还是上游系统；输出是对话、stdout JSON、artifact 文件还是多文件 bundle。
- **复杂度信号**：阶段数量、依赖强度、是否跨上下文恢复、是否需要用户确认、是否需要弱模型友好。
- **经验材料**：成功步骤、失败尝试、用户纠正、已有脚本、现有 skill、示例数据。

只在缺少以下关键决策时询问用户：

- skill 的目标能力无法确定。
- 输出给人读还是给机器消费无法确定。
- 是否允许交互无法确定。
- 是否要公开发布、因此需要脱敏/安全审查无法确定。
- 多个架构厚度都合理，且取舍会显著影响维护成本。

提问时一次只问 1-2 个决策问题，并给出推荐选项和理由。

## Experience Mining

当用户提供对话、调试过程、已有 workflow 或示例 skill 时，先提炼经验，再设计文件。

提取以下内容：

| 类别 | 要提取什么 | 会变成 skill 中的什么 |
| --- | --- | --- |
| 成功路径 | 最终跑通的步骤、命令、判断顺序 | Core workflow / stage playbook |
| 失败路径 | 失败方案、错误信息、根因 | Do not attempt / failure recovery |
| 用户偏好 | 风格、交互节奏、确认点、输出语言 | Working style / interaction rules |
| 稳定契约 | 字段、目录、文件名、stdout、schema | I/O contract / assets schema |
| 重复动作 | 多次手写的校验、渲染、转换 | script candidates |
| 语义判断 | 需要理解、权衡、归纳的步骤 | Must be done by LLM |
| 确定性动作 | 可验证、可重复、容易出错的步骤 | Must be done by scripts |

不要把经验材料逐字塞进 skill。要抽象成可复用规则、示例、反例和门禁。

## Complexity Decision

复杂度判断是强制步骤。先读 [complexity-model.md](references/complexity-model.md)，再选择最低但足够的架构。

输出复杂度判断时必须说明：

- 选定 tier。
- 任务为什么不能更轻。
- 任务为什么不需要更重。
- 是否存在升级触发条件，例如未来要接 runner、要跨 session 恢复、要被弱模型执行。

快速规则：

- 单一动作 + 稳定输出：优先轻量 `SKILL.md`。
- 多规则但流程不长：reference-backed。
- 有确定性校验/渲染：script-assisted。
- 多阶段不能跳步：gate-driven。
- 长程、强恢复、弱模型友好、最终产物稳定：SQLite state-machine。
- 输出被机器消费：叠加 automation-facing schema contract。

## Drafting Procedure

设计或更新 skill 时按以下顺序工作。

1. **确定 mode 和复杂度**
   - 使用 `Operating Modes` 和 `Complexity Decision`。
   - 不要先写文件结构。

2. **做轻量来源覆盖检查**
   - 当任务依赖外部资料、已有 skill、失败记录、第三方工具或准备公开/共享时，读 [community-meta-skill-lessons.md](references/community-meta-skill-lessons.md)。
   - 输出已覆盖来源、关键缺口、不确定性和是否需要用户确认。
   - 简单、单一、低风险 skill 不要因此拉长流程；确认来源足够后继续轻量设计。

3. **起草 description**
   - 需要写作细节时读 [skill-writing-playbook.md](references/skill-writing-playbook.md)。
   - description 必须同时写“做什么”和“何时用”。
   - 把触发信息写进 frontmatter，不要藏在正文。
   - 包含用户真实会说的动词、对象、场景和近义表达。

4. **选择 `SKILL.md` 模板**
   - 模板是写作支架，不是跳过 intake、经验萃取和复杂度判断的捷径。
   - 所有新 skill 至少从 [minimal-skill-template.md](references/templates/minimal-skill-template.md) 起步。
   - reference-backed skill 叠加 [reference-backed-extension.md](references/templates/reference-backed-extension.md)。
   - script-assisted skill 叠加 [script-assisted-extension.md](references/templates/script-assisted-extension.md)。
   - gate-driven skill 叠加 [gate-driven-extension.md](references/templates/gate-driven-extension.md)。
   - SQLite state-machine skill 叠加 [sqlite-state-machine-extension.md](references/templates/sqlite-state-machine-extension.md)。
   - automation-facing skill 叠加 [automation-facing-extension.md](references/templates/automation-facing-extension.md)。
   - 落稿后必须删除模板占位符、authoring hints 和不适用章节。

5. **设计主文件章节**
   - `SKILL.md` 放运行时必须知道的步骤、约束、模式分流、职责边界和 reference 路由。
   - 详细字段、长示例、schema、stage playbook、失败恢复放 references。
   - 不写对 agent 显然的常识；写它容易错、容易忘、必须稳定遵守的规则。
   - 更新已有 skill 时，直接改成当前有效协议；不要追加历史演进、旧字段兼容、fallback 提醒或版本对比。

6. **设计 references**
   - 每个 reference 必须有明确读取时机。
   - 不创建“为了完整”的文档。
   - 所有 reference 必须从 `SKILL.md` 直接链接。

7. **设计资源与元数据取舍**
   - 需要决定 `scripts/`、`references/`、`assets/`、`agents/openai.yaml` 或上下文预算时读 [openai-skill-creator-lessons.md](references/openai-skill-creator-lessons.md)。
   - 先设计可移植 `SKILL.md`，再决定是否需要产品特定 metadata；产品字段不能替代主文件能力描述和运行时指令。
   - 先判断资源是否有实际运行价值；不要创建 README、安装指南、变更日志或空目录来凑完整。
   - `references/` 给 agent 按需读取，`assets/` 给输出或脚本使用，`agents/openai.yaml` 只是可选产品 UI 元数据。
   - 只有目标环境需要 Codex UI chip、默认 prompt 或 MCP dependency metadata 时才建议 `agents/openai.yaml`。

8. **设计 scripts/assets**
   - 设计 scripts 前读 [llm-script-boundary.md](references/llm-script-boundary.md)。
   - 有脚本就必须在 `SKILL.md` 写调用示例。
   - 需要 agent 填写的 payload 应尽可能扁平化，字段名称应具有语义自明性，避免容易导致误解的字段名。
   - 复杂 payload 必须提供 payload 示例、字段语义、枚举值、正例和反例。
   - 如果业务批次可以稳定、确定性切分，优先设计脚本生成 batch payload；若由主 agent 切分，必须写清切分原则和均衡标准。
   - 有自动化上下游时读 [io-schema-contracts.md](references/io-schema-contracts.md)。

9. **设计 subagent 委派**
   - 只有任务存在可并行、相互独立的语义业务单元时，才读 [subagent-delegation.md](references/subagent-delegation.md)。
   - subagent 委派必须写成可选路径：如果当前环境可以委派 subagent，则使用；否则主 agent 串行处理或说明外部执行需求。
   - 需要委派 subagent 的 skill 必须给出建议委派 prompt、payload 文件协议、结果文件/stdout 协议和批次拆分策略。
   - subagent 只产出局部结果；主 agent 保留最终汇总、冲突处理、质量把关和用户-facing 输出责任。

10. **设计长程状态**
   - 任务多阶段、强依赖、可能跨上下文压缩时读 [state-machine-and-sqlite.md](references/state-machine-and-sqlite.md)。
   - 只有确实需要恢复、门禁、稳定渲染时才引入 SQLite/gate。
   - 阶段划分应以 agent 的决策点为依据，不需要 agent 决策的流程应合并，脚本级联执行。

11. **按设计问题读取说明性样例**
   - 样例文档只用于架构启发，不是可复制模板。
   - 普通设计任务不要要求 agent 读取原始作者 skill 包。
   - 简单稳定契约读 [example-simple-contract.md](references/example-simple-contract.md)。
   - 中等交互和证据验证读 [example-interactive-evidence.md](references/example-interactive-evidence.md)。
   - 多阶段写作和 gate 约束读 [example-gate-driven-writing.md](references/example-gate-driven-writing.md)。
   - 自动化 SQLite 和 stdout 硬契约读 [example-automation-sqlite.md](references/example-automation-sqlite.md)。
   - 长程交互 SQLite 和用户确认门禁读 [example-interactive-sqlite.md](references/example-interactive-sqlite.md)。

12. **设计验证策略**
   - 默认先设计轻量验收场景，而不是正式评估迭代。
   - 需要设计测试、反馈迭代或触发优化时读 [anthropic-skill-creator-lessons.md](references/anthropic-skill-creator-lessons.md)。
   - 正式评估反馈迭代必须同时满足三条件：用户明确同意、当前环境可调用子代理或等价独立执行器、输入可模拟/可获取且输出可评价。
   - 任一条件不满足时，只输出轻量验收 prompts、人工 review checklist、trigger query 建议或需要用户补充的样例/评价标准。
   - 不要把评估迭代当成每个 skill 的默认成本。

13. **验收**
   - 完成前读 [quality-gates.md](references/quality-gates.md)。
   - 至少检查触发、厚度、reference 路由、LLM/脚本边界、I/O 契约、示例/反例、失败恢复。
   - 公开、共享、迁移到他人环境，或包含脚本/外部服务/产品特定 metadata 时，必须检查脱敏、安全副作用、依赖和无惊讶原则。
   - 最终 skill 只能呈现当前有效行为；发现历史协议说明、迁移说明、fallback、旧版字段或版本对比时必须删除或改写为当前契约。

## Writing Rules

- 用命令式、可执行的语言写 skill。
- 解释关键规则背后的原因，但不要写长篇理论。
- 保持上下文经济；只写对任务稳定性有帮助、且 Codex 不会自然知道的信息。
- 每个禁止事项都应该对应真实错误风险。
- 如果某段内容只在少数场景需要，放进 reference，并在 `SKILL.md` 写清读取时机。
- 如果脚本是正式执行契约的一部分，`SKILL.md` 必须写命令示例；不能只在 reference 里提脚本名。
- 如果 payload 有枚举值，显式列出；不要让 agent 自行猜。
- payload 应尽量扁平化，字段名称应具有语义自明性，避免容易导致误解的字段名。
- 长程任务的阶段划分应以 agent 的决策点为依据，不需要 agent 决策的流程不应切分、不应中断，不应让 agent 仅成为驱动脚本执行的工具。
- 需要 subagent 委派的 skill 必须说明“如果当前环境可以委派 subagent”，不得把 subagent 可用性作为硬门禁。
- 委派给 subagent 的业务 payload 应优先文件化；结果优先写文件返回，但 prompt 必须允许无写文件权限时通过 stdout 返回同等结构内容。
- 能被脚本稳定切分的业务批次，优先由脚本生成 batch payload；主 agent 切分时必须写清切分原则、目标批次大小、均衡标准和边界处理。
- 如果输出被机器消费，成功和失败都必须有稳定 shape。
- 不创建无运行价值的辅助文档或资源目录。
- 如果是公开或共享 skill，必须考虑脱敏、安全扫描、许可证、内部路径泄露和无惊讶原则。
- 最终 skill 必须 current-state only：不得保留历史协议、旧字段兼容、fallback 提醒、版本对比，或“以前/曾经/旧版如何处理”的说明。
- 如果用户要求兼容旧调用方，把兼容逻辑设计为外部 adapter、上游转换或单独迁移任务；不要把兼容 fallback 写进 skill 运行时说明。

## LLM And Script Responsibilities

必须在每个被设计的 skill 中显式写出职责分工。

**必须由 LLM 完成：**

- 语义理解、摘要、归纳、分类、证据解释。
- 用户意图确认、权衡、策略制定、交互式决策。
- 学术/业务/写作判断。
- 从失败记录中提炼通用规则。

**必须由脚本完成：**

- schema 校验、枚举校验、payload 解析。
- gate 判断、状态迁移、SQLite 写入、恢复包渲染。
- 确定性提取、文件分发、目录创建、哈希计算。
- 最终机器可消费产物的稳定渲染和输出合法性检查。

**禁止：**

- 为了省事写临时脚本替代 LLM 做语义任务。
- 让 LLM 手工拼接已经规定必须由脚本或 renderer 生成的权威 JSON/Markdown/LaTeX 产物。
- 在有 gate 的设计中绕过 `next_action` 凭记忆推进。

## Output Templates

### 设计新 skill

```markdown
## 复杂度判断
- Tier:
- 为什么不是更轻:
- 为什么不需要更重:

## 推荐架构
- 文件布局:
- SKILL.md 主章节:
- references:
- scripts/assets:
- optional product metadata:

## 来源与发布边界
- 已覆盖来源:
- 关键缺口:
- 是否涉及 wrapper skill:
- 是否涉及公开/共享/迁移:
- 产品特定字段:
- 安全/脱敏检查:

## 运行契约
- description 草案:
- 输入:
- 输出:
- LLM 职责:
- 脚本职责:
- 禁止事项:

## Subagent delegation
- 是否建议:
- 适合委派的业务单元:
- 批次拆分策略:
- payload 文件协议:
- 结果文件/stdout 协议:
- 建议委派 prompt:

## 验证计划
- Happy path:
- Near miss / failure:
- 触发测试:
- 结构/格式校验:

## 验证与迭代计划
- 轻量验收场景:
- 是否建议正式评估迭代:
- 三条件检查结果:
  - 用户是否明确同意:
  - 是否可调用子代理/独立执行器:
  - 输入是否可模拟/可获取且输出可评价:
- 不满足条件时的替代方案:
- description 触发优化建议:
```

### 审查已有 skill

```markdown
## 主要问题
- [Severity] 文件/章节: 问题与影响

## 架构匹配度
- 当前复杂度:
- 当前架构:
- 是否过轻/过重:

## 必改项
- ...
- 删除历史协议说明、迁移说明、fallback、旧字段兼容或版本对比。

## 可选改进
- ...

## 验证建议
- ...
```

### 从经验萃取 skill

```markdown
## 经验材料摘要
- 成功路径:
- 失败路径:
- 用户偏好:
- 稳定契约:

## 可沉淀规则
- Workflow:
- Do not attempt:
- Script candidates:
- Examples:

## Skill 设计草案
- Tier:
- 文件布局:
- 关键章节:
- 验证计划:
```

## Quality Gates

完成前必须检查：

- description 是否足以触发，且不过度抢占相邻任务。
- 复杂度和架构是否匹配。
- `SKILL.md` 是否包含运行时主流程，而不只是目录索引。
- 所有 references 是否被直接链接并说明读取时机。
- 是否保持上下文经济，没有无运行价值的 README、安装指南、变更日志或空资源目录。
- 使用模板时，模板组合是否与复杂度匹配，且落稿是否已删除占位符和 authoring hints。
- 脚本职责是否没有越过语义边界。
- 有脚本时是否有调用示例和 payload 示例。
- 有机器消费输出时是否有 schema、成功/失败 shape、枚举值和验证方式。
- 有长程状态时是否有 gate、恢复协议、只读视图与真源边界。
- 是否存在 runtime-only 的阶段，运行流程中是否含有让 agent 机械执行某些固定指令的设计。
- 是否包含正例、反例或 near-miss 验收场景。
- 如建议正式评估迭代，是否已通过用户同意、子代理可用性、输入输出可评价性三条件 gate。
- 如建议 subagent 业务委派，是否是可选路径，且 payload、结果协议、批次拆分和主 agent 汇总责任清楚。
- 若存在 `agents/openai.yaml`，是否与 `SKILL.md` 能力一致且只作为可选产品元数据。
- 公开发布时是否考虑脱敏、安全、许可证、依赖副作用和无惊讶原则。
- 当设计依赖外部资料、已有 skill、失败记录或第三方工具时，来源是否足够支撑当前设计，缺口是否已声明。
- 产品特定字段是否与可移植核心隔离，且没有隐藏运行时能力、权限或依赖。
- 如果是第三方工具 wrapper，是否已做 adopt / extend / build 判断，而不是默认新建重型 skill。
- 最终 skill 是否只呈现当前有效协议，且没有历史说明、旧字段兼容、fallback 提醒或版本对比。

详细审查见 [quality-gates.md](references/quality-gates.md)。

## Reference Loading Guide

默认先读本文件，不要一次性通读所有 references。

| 需要解决的问题 | 读取 |
| --- | --- |
| 判断 skill 应该多厚 | [complexity-model.md](references/complexity-model.md) |
| 选择文件布局和架构范式 | [architecture-patterns.md](references/architecture-patterns.md) |
| 决定资源目录、上下文预算、OpenAI UI 元数据或产品特定配置 | [openai-skill-creator-lessons.md](references/openai-skill-creator-lessons.md) |
| 做来源覆盖、可移植边界、wrapper 判断或发布安全检查 | [community-meta-skill-lessons.md](references/community-meta-skill-lessons.md) |
| 写 frontmatter、description、body、示例和反例 | [skill-writing-playbook.md](references/skill-writing-playbook.md) |
| 起草最小 `SKILL.md` 主文件 | [minimal-skill-template.md](references/templates/minimal-skill-template.md) |
| 为 reference-backed skill 扩展主文件 | [reference-backed-extension.md](references/templates/reference-backed-extension.md) |
| 为 script-assisted skill 扩展主文件 | [script-assisted-extension.md](references/templates/script-assisted-extension.md) |
| 为 gate-driven skill 扩展主文件 | [gate-driven-extension.md](references/templates/gate-driven-extension.md) |
| 为 SQLite state-machine skill 扩展主文件 | [sqlite-state-machine-extension.md](references/templates/sqlite-state-machine-extension.md) |
| 为 automation-facing skill 扩展主文件 | [automation-facing-extension.md](references/templates/automation-facing-extension.md) |
| 设计测试、反馈迭代、触发优化和脚本候选发现 | [anthropic-skill-creator-lessons.md](references/anthropic-skill-creator-lessons.md) |
| 设计可选 subagent 委派、payload 文件协议、批次拆分和委派 prompt | [subagent-delegation.md](references/subagent-delegation.md) |
| 设计 LLM 与脚本职责边界 | [llm-script-boundary.md](references/llm-script-boundary.md) |
| 设计长程状态、gate、SQLite、恢复机制 | [state-machine-and-sqlite.md](references/state-machine-and-sqlite.md) |
| 设计自动化输入输出、schema、目录协议 | [io-schema-contracts.md](references/io-schema-contracts.md) |
| 简单稳定契约设计样例 | [example-simple-contract.md](references/example-simple-contract.md) |
| 中等交互、记忆和证据验证样例 | [example-interactive-evidence.md](references/example-interactive-evidence.md) |
| 多阶段写作、gate 和只读视图样例 | [example-gate-driven-writing.md](references/example-gate-driven-writing.md) |
| 自动化 SQLite、renderer 和 stdout 契约样例 | [example-automation-sqlite.md](references/example-automation-sqlite.md) |
| 长程交互 SQLite、用户确认和恢复协议样例 | [example-interactive-sqlite.md](references/example-interactive-sqlite.md) |
| 完成前做质量审查 | [quality-gates.md](references/quality-gates.md) |

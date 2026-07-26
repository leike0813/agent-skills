---
name: skill-smith
description: Create, update, review, and architect high-quality agent skills by choosing the right skill thickness for the task. Use when designing or improving skills, meta-skills, SKILL.md files, or when distilling user experience, debugging sessions, prior workflows, and failure records into reusable agent skills.
---

# Skill Smith

## Mission

把用户已经付过代价获得的经验锻造成可复用 skill。不要从模板开始；先理解任务、经验、失败路径、输出契约、交互边界和运行风险，再选择合适的 skill 厚度。

本 skill 自身采用 reference-backed 架构：`SKILL.md` 是运行时主控，`references/` 存放细节。使用时先读本文件，只在当前设计问题需要时读取对应 reference。

## **Agent Skill Hard Constraints**

**将本节的指令要求视为起草、修订、审查 Skill 的硬约束，贯穿于整个设计过程，并且在交付前必须复查！**

### Structural Principles

- 遵守 Open Agent Skills 规范，除非用户明确要求或有特殊需求外，Skill 包中仅包含以下内容：(1) `SKILL.md` 写 Skill 指令，(2) `references/` 目录存放扩展指令、参考资料，(3) `scripts/` 目录存放执行脚本，(4) `assets/` 目录存放资源文件。
- **`SKILL.md` 中的 yaml frontmatter 中的 description 必须精炼，只写两件事：(1)这个 Skill 是做什么的；(2)这个 Skill 该在什么情况下使用。**
- **`SKILL.md` 中必须包含以下几部分内容（具体形式、内容、体量根据 Skill 特点来定，但结构上必须有）：(1) `目标`/`Goal`，即这个 Skill 是做什么的，执行怎样性质的任务，预期达到怎样的效果；(2) `非目标`/`Non-goal`，即这个 Skill 不做什么，不试图解决哪些问题；(3) `输入输出契约`/`I/O Contract`，即 Skill 的输入、输出应该遵守怎样的形式约定；(4) `禁止事项`/`FORBIDDEN`，即 Agent 在执行 Skill 时绝对不能做的事，通常以 `**` 包裹以示强调；(5) `执行流程`/`Execution Flow`，即 Skill 的执行步骤、阶段划分、决策点、失败恢复等；(6) `LLM 与脚本职责分工`/`LLM vs Script Responsibilities`，即 Skill 中哪些任务必须由 LLM (Agent) 完成，哪些任务必须由脚本完成；(7) `参考资料引用`/`References`，即 Skill 中需要引用哪些参考资料（指向 `references` 目录下的文档，或外部链接）以及在何时去阅读；Skill 执行依赖哪些脚本、各脚本的作用是什么、脚本的调用说明（如果有）去哪里找。** 
- `SKILL.md` 中还建议包含以下内容（若 `SKILL.md` 篇幅已接近建议阈值，也可以放在 `references` 目录下）：(1) `成功标准`/`Success Criteria`，即 Skill 执行成功的表现，如果有可量化验证的指标更好；(2) `易错点`/`Common Pitfalls`，即 Skill 执行中容易出错的地方，通常是 Agent 需要特别注意的地方；(3) `流程示例`/`Example Flow`，即 Skill 执行的示例流程，通常是一个完整的执行案例，帮助 Agent 理解 Skill 的执行方式。
- 参考资料、不适合放入 `SKILL.md` 的详细指令（例如长篇的语义解释、正/反例、最佳实践、执行技巧等），应放到 `references` 目录下，并在 `SKILL.md` 中显式引用并说明该在何时阅读，确保 Agent 可以按需加载。
- **确保 `SKILL.md` 是“最小完备可执行契约”，即假定 Skill 执行者（Agent）在没有任何额外信息的情况下，能够仅凭 `SKILL.md` 的内容就能理解并完整、稳定地执行 Skill；不能假定 Agent 一定会加载 `references` 目录中的指令，因此 `references` 目录中的指令必须视为补充信息而非强约束条件。**
- 如果脚本是正式执行契约的一部分，`SKILL.md` 必须写命令示例（可以放在 `执行流程` 中），不能只在 `References` 里简单引用。
- `references` 目录中不应出现短篇幅的碎片化指令，只要 `SKILL.md` 的篇幅未大幅超限，都应优先考虑将这些碎片指令并入 `SKILL.md`。

### **STRICTLY FORBIDDEN (Common Pitfalls)**

- **Skill 的指令必须是 current-state only：不得保留历史协议、旧字段兼容、fallback 提醒、版本对比，或“以前/曾经/旧版如何处理”的说明；修改/更新 Skill 后不得添加“不再怎么怎么做/XXX不再适用”之类的说明和指令！**
- **对 Skill 执行必要的流程说明、输入/输出契约、硬约束等关键内容不得分散至 `references` 目录下，而是必须直接写入 `SKILL.md`。**
- **不要随便给 Skill 写测试！Skill 的测试应该主要针对内置脚本的业务逻辑，切勿静态断言 Skill 包中的指令文本！**
- 不创建无运行价值的辅助文档或资源目录。

### Language Principles

- 用命令式、可执行的流畅自然语言语言写 Skill 指令。
- 解释关键规则背后的原因，但不要写长篇理论，确保 Skill 的执行者（可能是弱模型）能够理解和执行，并在遇到问题时能够根据理解来调整策略，但不偏离 Skill 指令的大方向。
- 保持上下文经济；只写对任务稳定性有帮助、且 Agent 不会自然知道的信息。具体哪些是“自然知道”，可以由你（本 Skill 的执行者）来判断。
- 制定 `禁止事项` 时应审慎，每个禁止事项都应该对应真实错误风险；优先确保那些会直接导致 Skill 执行失败的硬边界被禁止事项防住，对于可能存在的软错误，应放在 `易错点` 中。

### Script Principles

- 脚本应配有 `--help` 或 `-h` 参数，能输出脚本的功能、参数、输入输出约定和示例，以便 Agent 进行自探索。
- **如果脚本需要的 payload 有枚举值，必须在指令中显式列出，不要让 Agent 自行猜测或需要通过自探索/试错才能获得。**
- **脚本的 payload 应尽量扁平化，字段名称应具有语义自明性，避免容易导致误解的字段名。**
- 如果脚本的输出需要被机器消费，则脚本执行无论成功或失败，其输出都必须有稳定 shape/schema。

### Long-Running Task Principles

- **长程任务必须在 `SKILL.md` 中写明完整的执行流程、阶段划分、决策点、失败恢复和最终汇总责任。**
- 长程任务应在 `references` 目录中提供各阶段的详细指令、正/反例、最佳实践、执行技巧等，供 Agent 在执行至相应阶段时动态加载，起到提高上下文经济性、提升指令遵循质量的作用（LLM 普遍存在 Forget in the Middle 问题）。
- 长程任务的阶段划分应以 Agent 的决策点为依据，不需要 Agent 决策的流程不应切分、不应中断，不应让 Agent 仅成为驱动脚本执行的工具。
- 长程任务建议设计门禁机制，确保 Agent 不会擅自跳过某些步骤导致执行失败或给出不稳定的结果。
- 超长程任务建议配备可以提供 `Just In Time` （JIT）指令的门禁脚本，让 Agent 在通过门禁时可以自然地获得下一步的指令，保证 Skill 流程得以顺畅继续。

### Subagent Delegation Principles

- 需要 Subagent 委派的 Skill 必须考虑到 Agent 执行环境可能存在的差异，确保 Subagent 委派只是加快执行效率、优化上下文的一个可选项，而非 Skill 业务功能的硬约束；例如，在需要委派 Subagent 的位置可以使用“如果当前环境可以委派 Subagent，...”之类的软指令，给 Agent 选择空间。
- 委派给 Subagent 的业务 payload 应优先文件化；结果优先写文件返回，但 prompt 必须要求 subagent 先做写盘能力探测，无法写文件时通过 stdout 返回同等结构内容。
- 能被脚本稳定切分的业务批次，优先由脚本生成 batch payload；主 agent 切分时必须写清切分原则、目标批次大小、均衡标准和边界处理。

### Misc

- 如果是公开或共享 Skill，必须考虑脱敏、安全扫描、许可证、内部路径泄露和无惊讶原则。
- 如果用户要求兼容旧调用方，把兼容逻辑设计为外部 adapter、上游转换或单独迁移任务；不要把兼容 fallback 写进 Skill 运行时说明。

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
   - 需要委派 subagent 的 skill 必须给出建议委派 prompt、payload 文件协议、写盘能力探测、结果文件/stdout 协议和批次拆分策略。
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

## About `LLM vs Script Responsibilities`

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
- 写盘能力探测:
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

- Skill 包是否遵守 Open Agent Skills 结构约定；除非有明确需求，是否仅包含 `SKILL.md`、`references/`、`scripts/` 和 `assets/`，且没有无运行价值的文档、目录或资源。
- YAML frontmatter 的 description 是否只说明 Skill 做什么，以及应在何时使用；是否足以触发而不过度抢占相邻任务。
- 复杂度、模板组合和架构是否匹配；落稿中是否已删除占位符和 authoring hints。
- `SKILL.md` 是否完整包含目标、非目标、输入输出契约、禁止事项、执行流程、LLM 与脚本职责分工、参考资料引用，以及适用时的成功标准、易错点和流程示例。
- `SKILL.md` 是否构成最小完备可执行契约：即使不加载 `references/`，Agent 也能理解并稳定执行主流程、关键约束和 I/O 契约。
- 所有 references 是否都被直接链接并说明读取时机；必要流程、I/O 契约和硬约束是否全部留在 `SKILL.md`，且 references 中没有应合并回主文件的短小碎片化指令。
- 指令是否使用命令式、自然且可执行的语言；规则理由是否足够支撑理解和调整，但没有长篇理论或 Agent 自然已知的冗余信息。
- 每项禁止事项是否对应真实的执行风险，并优先覆盖会直接导致执行失败的硬边界。
- 使用脚本时，`SKILL.md` 是否提供命令、调用和 payload 示例；每个脚本是否支持 `--help` 或 `-h` 并清楚说明功能、参数、I/O 契约和示例。
- 脚本职责是否没有越过语义边界；payload 是否扁平、字段语义自明，枚举值是否在指令中明确列出。
- 有机器消费输出时，是否定义 schema、成功/失败的稳定 shape 及验证方式；测试是否只覆盖脚本的稳定业务行为，而未静态断言 Skill 指令文本。
- 有长程任务时，`SKILL.md` 是否明确完整流程、阶段、决策点、失败恢复和最终汇总责任；阶段是否按 Agent 决策点划分，而非让 Agent 机械驱动固定指令或脚本。
- 有长程状态时，是否具备 gate、恢复协议、只读视图与真源边界；超长程任务是否评估需要提供 Just In Time 指令的门禁脚本。
- 是否包含正例、反例或 near-miss 验收场景；如建议正式评估迭代，是否已通过用户同意、子代理可用性、输入输出可评价性三条件 gate。
- 如建议 subagent 业务委派，是否为可选路径；payload、写盘能力探测、结果协议、批次拆分和主 Agent 汇总责任是否清楚；可脚本化切分时，是否明确切分原则、目标批次大小、均衡标准和边界处理。
- 若存在 `agents/openai.yaml`，是否与 `SKILL.md` 能力一致且只作为可选产品元数据；产品特定字段是否与可移植核心隔离，且没有隐藏运行时能力、权限或依赖。
- 公开或共享时，是否考虑脱敏、安全扫描、许可证、依赖副作用、内部路径泄露和无惊讶原则。
- 当设计依赖外部资料、已有 Skill、失败记录或第三方工具时，来源是否足够支撑当前设计，缺口是否已声明；如果是第三方工具 wrapper，是否已做 adopt / extend / build 判断，而非默认新建重型 Skill。
- 最终 Skill 是否只呈现当前有效协议，没有历史说明、旧字段兼容、fallback 提醒、版本对比或反向的废弃说明；如需兼容旧调用方，是否已将兼容逻辑放在外部 adapter、上游转换或独立迁移任务中。

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
| 设计可选 subagent 委派、payload 文件协议、写盘能力探测、批次拆分和委派 prompt | [subagent-delegation.md](references/subagent-delegation.md) |
| 设计 LLM 与脚本职责边界 | [llm-script-boundary.md](references/llm-script-boundary.md) |
| 设计长程状态、gate、SQLite、恢复机制 | [state-machine-and-sqlite.md](references/state-machine-and-sqlite.md) |
| 设计自动化输入输出、schema、目录协议 | [io-schema-contracts.md](references/io-schema-contracts.md) |
| 简单稳定契约设计样例 | [example-simple-contract.md](references/example-simple-contract.md) |
| 中等交互、记忆和证据验证样例 | [example-interactive-evidence.md](references/example-interactive-evidence.md) |
| 多阶段写作、gate 和只读视图样例 | [example-gate-driven-writing.md](references/example-gate-driven-writing.md) |
| 自动化 SQLite、renderer 和 stdout 契约样例 | [example-automation-sqlite.md](references/example-automation-sqlite.md) |
| 长程交互 SQLite、用户确认和恢复协议样例 | [example-interactive-sqlite.md](references/example-interactive-sqlite.md) |
| 完成前做质量审查 | [quality-gates.md](references/quality-gates.md) |

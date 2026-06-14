# Architecture Patterns

## Prompt Skill

用于简单任务。

结构：

```text
skill-name/
└── SKILL.md
```

`SKILL.md` 必须包含：

- 目标。
- 输入来源。
- 执行步骤。
- 约束和禁止事项。
- 输出格式。
- 至少一个正例和一个失败/边界例。

不要加入 SQLite、gate 或复杂 reference，除非已有明确需求。

最小验收：

- 另一个 agent 能只读 `SKILL.md` 完成任务。
- 至少有一个成功示例和一个失败/边界示例。
- 输出格式明确。

说明性样例：[example-simple-contract.md](example-simple-contract.md)。

## Reference-backed Skill

用于细节较多但流程不长的任务。

结构：

```text
skill-name/
├── SKILL.md
└── references/
    ├── topic-a.md
    └── topic-b.md
```

规则：

- `SKILL.md` 是路由器，不是百科全书。
- reference 文件必须被 `SKILL.md` 直接链接。
- 每个链接说明“何时读取”。
- 不要让 reference 互相深层引用。

最小验收：

- `SKILL.md` 有完整主流程，不只是 reference 目录。
- 每个 reference 都有读取时机。
- 不读 reference 时也能知道第一步做什么。

说明性样例：[example-interactive-evidence.md](example-interactive-evidence.md)。

## Script-assisted Skill

用于存在确定性子任务的中等复杂流程。

结构：

```text
skill-name/
├── SKILL.md
├── references/
│   └── payload-contract.md
└── scripts/
    └── validate_or_render.py
```

规则：

- `SKILL.md` 至少给出每个正式脚本的调用示例。
- 复杂 payload 必须给 JSON 示例。
- reference 中补充字段语义、枚举值、正例和反例。
- 脚本只承担确定性职责。

最小验收：

- `SKILL.md` 中每个正式脚本都有命令示例。
- 复杂 payload 有最小合法示例。
- 写清脚本失败后停止、回退还是进入 repair。

说明性样例：

- 简单校验脚本：[example-simple-contract.md](example-simple-contract.md)。
- 交互记忆和证据检查：[example-interactive-evidence.md](example-interactive-evidence.md)。

## Gate-driven Workflow

用于不能跳步的多阶段 workflow。

结构：

```text
skill-name/
├── SKILL.md
├── references/
│   ├── gate-runtime.md
│   ├── stage-runtime.md
│   └── stage-n-playbook.md
└── scripts/
    ├── gate_runtime.py
    └── stage_runtime.py
```

核心契约：

- 首次进入和每次写入后先运行 gate。
- 只能执行 gate 返回的 `next_action`。
- gate 返回当前动作需要读的 references、payload 示例和 blocker。
- stage runtime 执行动作并写入状态。

最小验收：

- gate 是唯一下一步入口。
- `next_action` 集合可枚举。
- 有恢复入口和 blocker 处理。
- 禁止绕过 gate 手写完成状态。

说明性样例：[example-gate-driven-writing.md](example-gate-driven-writing.md)。

## SQLite State-machine Skill

用于长程、可恢复、高稳定性任务。

结构：

```text
skill-name/
├── SKILL.md
├── references/
│   ├── runtime-database-contract.md
│   ├── gate-and-stage-runtime.md
│   └── failure-recovery.md
├── scripts/
│   ├── gate_runtime.py
│   ├── stage_runtime.py
│   └── render_outputs.py
└── assets/
    └── output.schema.json
```

核心契约：

- SQLite 是唯一运行态真源。
- LLM 只产出语义 payload，不直接伪造完成状态。
- 脚本负责写库、状态推进、schema 校验和最终渲染。
- 只读 Markdown 视图用于人类确认和 agent 恢复，不是写入真源。

最小验收：

- DB 路径、workspace、只读视图、最终 artifact 的边界清楚。
- 每次写库后重新 gate 或 render。
- 最终机器消费产物由脚本渲染。
- 有上下文压缩后的恢复协议。

说明性样例：

- 自动化长程任务：[example-automation-sqlite.md](example-automation-sqlite.md)。
- 交互式长程任务：[example-interactive-sqlite.md](example-interactive-sqlite.md)。

## Automation-facing Skill

用于被 runner、其它 agent 或下游系统消费的 skill。

结构：

```text
skill-name/
├── SKILL.md
├── assets/
│   ├── input.schema.json
│   ├── output.schema.json
│   └── runner.json
├── references/
│   └── io-contract.md
└── scripts/
    └── validate_output.py
```

核心契约：

- stdout 或 artifact 输出只能有一种权威路径。
- 成功和失败都必须满足 schema。
- 所有枚举值显式列出。
- 输出稳定排序，避免字段漂移。

最小验收：

- 成功和失败输出都满足 schema。
- stdout 不混日志、解释或 Markdown fence。
- required keys 即使为空也保留。

说明性样例：

- 简单契约输出：[example-simple-contract.md](example-simple-contract.md)。
- 后台自动化输出：[example-automation-sqlite.md](example-automation-sqlite.md)。

## Wrapper Skill

用于把第三方 CLI、API、MCP、插件或本地工具操作沉淀为可复用能力。只有当工具调用本身是稳定任务的一部分时才使用，不要把普通语义任务包装成工具 skill。

先做 adopt / extend / build 判断：

| Decision | 选择条件 | 设计动作 |
| --- | --- | --- |
| Adopt | 现有工具已稳定，只缺 agent 调用规则 | 写轻量入口、参数、认证和失败处理 |
| Extend | 现有 skill 或工具接近可用，但缺少场景规则 | 最小更新现有 skill 或补 reference |
| Build | 工具链复杂、失败经验多、输出契约特殊 | 新建 wrapper skill，并沉淀安装/调用/恢复规则 |

最小验收：

- `SKILL.md` 写清何时调用工具、何时不要调用。
- 认证、环境变量、工作目录、输入文件和输出位置有明确约定。
- 脚本或命令失败时有停止、重试、回退或询问用户的规则。
- 如果 wrapper 会触发下游 skill 或外部服务，必须经过用户 opt-in，不能静默串联。

## Subagent-assisted Delegation

用于把可并行、相互独立的语义业务单元委派给 subagent。它是横向模式，不是新的复杂度 tier，可叠加在 Reference-backed、Script-assisted、Gate-driven 或 SQLite State-machine skill 上。

适用条件：

- 当前环境可以委派 subagent。
- 委派单元之间没有强依赖。
- subagent 的局部输出可以被主 agent 验收和合并。
- 主 agent 不需要把完整上下文或最终判断交给 subagent。

设计要求：

- 在 `SKILL.md` 中写明“如果当前环境可以委派 subagent”。
- 给出建议委派 prompt。
- 使用文件化 payload 描述批次、输入路径、约束和结果 shape。
- 结果优先写文件并返回路径；无法写文件时允许 stdout 返回同等结构。
- 主 agent 保留最终汇总、冲突处理、质量把关和用户-facing 输出责任。

批次拆分：

- 简单、均匀、低风险业务可由主 agent 切分。
- 复杂、不均匀、数量大或需要复现的业务，优先设计脚本生成 batch payload。
- 不写脚本时必须在 skill 指令中写清切分原则、目标批次大小、均衡标准和边界处理。

不要让 subagent 直接推进 gate、写 SQLite 权威状态、生成最终机器消费 artifact 或做最终策略裁决。

## Pattern Selection

从轻到重选择：

1. 能用 Prompt Skill 解决，不要加 reference。
2. 内容多但状态少，用 Reference-backed。
3. 有确定性子任务，用 Script-assisted。
4. 有强步骤依赖，用 Gate-driven。
5. 需要长程恢复和稳定渲染，用 SQLite State-machine。
6. 有机器上下游消费，叠加 Automation-facing contract。
7. 第三方工具操作本身是核心能力时，按需叠加 Wrapper Skill 判断。
8. 存在可并行语义业务单元时，按需叠加 Subagent-assisted Delegation。

## Resource Boundary

资源目录按职责选择，不按“看起来完整”创建。

- `SKILL.md`：运行时主控，必须包含第一步、主流程、硬约束和 reference 路由。
- `references/`：给 agent 按需读取的长细节，例如 schema、领域规则、stage playbook、正例和反例。
- `scripts/`：正式确定性入口，例如校验、转换、gate、写库和 renderer；有脚本就必须在 `SKILL.md` 给调用示例。
- `assets/`：输出资源或脚本/runner 使用的静态文件，例如模板、图标、字体、boilerplate、JSON schema。
- `agents/openai.yaml`：可选产品 UI 元数据，例如 `display_name`、`short_description`、`default_prompt` 或 MCP dependency metadata；不替代 `SKILL.md`。

不要创建 README、安装指南、变更日志、quick reference 或空资源目录，除非它们是目标平台明确要求的运行时输入。

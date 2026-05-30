# Anthropic Skill Creator Lessons

## Purpose

本文件提炼 `references/meta-skills/anthropic-skill-creator` 中可迁移的设计经验。读它的时机：需要为一个 skill 设计测试、评估、反馈迭代、触发优化或脚本候选发现策略。

不要把 Anthropic 原始包作为普通运行时必读材料。本文件只吸收设计原则，不复制其 viewer、runner、workspace、schema 全表、平台专用命令或完整评估流程。

## Useful Lessons

### 1. 先判断用户处在创建周期的哪一步

用户可能不是从零创建 skill，而是在以下任一阶段：

- 想把一个新能力做成 skill。
- 已有草稿，需要审查或补强。
- 已经试跑过，想根据失败反馈改进。
- 触发不准，需要优化 `description`。
- 想知道 skill 是否真的比无 skill 或旧版本更好。

`skill-smith` 应先识别阶段，再决定是否起草、审查、设计验收场景或建议评估迭代。

### 2. 测试 prompt 应像真实用户会说的话

验证 skill 时，测试 prompt 不应只写抽象任务名。好的 prompt 应包含真实上下文、工件、约束、含糊表达和近似说法。

简单 skill 通常只需要 2-3 个轻量验收 prompt：

- 一个 happy path。
- 一个 near-miss。
- 一个非法或缺失输入场景。

复杂 skill 可以增加更多 prompt，但仍要避免为了测试而测试。

### 3. expectations 要可评价

每个测试 prompt 应配套 human-readable expectations。好的 expectation 能被用户、审查者或脚本判断是否满足。

适合写成 expectation：

- 输出包含 required fields。
- 使用了正式脚本而不是手拼产物。
- gate 阶段没有被跳过。
- stdout 没有混入 Markdown fence。
- 用户确认前没有推进状态。

不适合强行量化：

- 纯主观风格偏好。
- 开放式创作质量。
- 没有样例输入或评价标准的复杂判断。

### 4. 反馈要抽象成通用规则

不要只为单个失败 prompt 打补丁。改 skill 前先问：

- 失败是否来自触发、流程、reference 路由、脚本边界、schema 还是示例不足？
- 这个失败会不会在其它真实任务中重复出现？
- 应该补工作流规则、反例、脚本、schema，还是只改 `description`？

如果多个测试都让 agent 临时写同类脚本，这是正式 `scripts/` 候选信号。

### 5. description 触发优化需要 near-miss

`description` 是触发接口。优化触发时，应同时准备：

- `should-trigger` queries：真实、具体、不同措辞的正例。
- `should-not-trigger` queries：共享关键词但实际不该触发的 near-miss。

不要只测试明显正例和明显负例。触发优化不等同于正式 benchmark；可以只作为轻量设计材料。

## Formal Eval Gate

正式“评估-反馈-迭代”不是默认流程。只有同时满足三个硬条件，才建议进入正式评估迭代：

1. **用户明确同意**
   - 必须先征求用户同意。
   - 不能从“帮我改 skill”“继续补强”中默认推断同意。

2. **可以调用子代理或等价独立执行器**
   - 正式 with-skill / baseline 对照需要独立执行，避免作者自己运行自己刚写的 skill 导致偏差。
   - 当前环境没有子代理或等价独立执行器时，不要声称完成正式 baseline 对照。

3. **输入可模拟或可获取，输出可评价**
   - 测试输入必须可构造、可访问或可由用户提供。
   - 输出必须能被用户、规则、schema、脚本或人工审查评价。

任一条件不满足时，输出替代方案：

- 轻量验收 prompts。
- 人工 review checklist。
- `should-trigger` / `should-not-trigger` 查询集。
- 需要用户补充的样例输入或评价标准。

## Evaluation Strategy By Skill Type

| Skill type | Recommended validation |
| --- | --- |
| Simple contract | 2-3 个 prompts + expected output / failure shape |
| Reference-backed | prompts 覆盖 reference 路由和 near-miss |
| Script-assisted | prompts + payload expectations + 脚本调用是否正确 |
| Gate-driven | gate blocker、禁止跳步、resume 场景 |
| SQLite state-machine | resume packet、DB 真源、renderer 输出一致性 |
| Automation-facing | schema、stdout 成功/失败 shape、枚举和目录协议 |

## Do Not Copy

- 不复制 Anthropic 的完整测试 workspace 结构。
- 不复制 viewer 或 runner 命令作为 `skill-smith` 必需步骤。
- 不复制完整 schema 表作为本 skill 的运行时契约。
- 不要求普通 agent 为每个 skill 都跑正式 benchmark。
- 不在没有子代理时模拟“正式对照实验”。

## Reusable Design Rules

- 先轻量验收，再考虑正式评估迭代。
- 正式评估迭代必须通过三条件 gate。
- 用户反馈要转化为通用设计规则，而不是针对单个 prompt 过拟合。
- 触发优化要同时看正例和 near-miss 负例。
- 重复临时脚本是正式脚本候选。

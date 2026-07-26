# Quality Gates

## Purpose

本文件用于完成前审查一个 skill 设计是否合格。读它的时机：已经起草或修改完 skill，准备向用户汇报或落盘。`SKILL.md` 中的 `Quality Gates` 是简明总清单；本文件用于对其中的检查项做细化审查，不替代主文件中的运行时契约。

## Gate 1: Trigger And Scope

- `description` 是否说明能力和使用时机？
- 是否只写这两项信息，而没有混入实现细节、安装步骤、兼容说明或产品营销语？
- 是否覆盖用户真实说法、近义词和关键工件？
- 是否存在明显误触发风险？
- 是否说明 near-miss 或不适用场景？

失败信号：

- description 只有 “helps with ...”。
- description 同时承诺工作流细节、未验证能力、权限或隐含依赖。
- 触发条件只写在正文。
- 覆盖范围大到会抢占其它 skill。

## Gate 2: Complexity Fit

- 是否先做复杂度判断？
- 当前架构是否是最低但足够的厚度？
- 模板组合是否与复杂度匹配，并已完全改写为当前 Skill 的运行时指令？
- 简单任务是否被不必要地引入 SQLite/gate？
- 长程任务是否缺少状态持久化和恢复协议？

失败信号：

- 单步任务有复杂 runtime。
- 多阶段强依赖任务只有普通步骤列表。
- 输出被机器消费却没有 schema 或稳定 shape。

## Gate 3: Structural Contract And Writing Quality

- 除非有明确需求，Skill 包是否只使用 Open Agent Skills 约定的 `SKILL.md`、`references/`、`scripts/` 和 `assets/`；任何额外文件或目录是否有直接运行价值？
- `SKILL.md` 是否明确包含目标、非目标、输入输出契约、禁止事项、执行流程、LLM 与脚本职责分工和参考资料引用？
- 是否按复杂度适当补充成功标准、易错点和流程示例，避免用空泛原则代替可验收行为？
- `SKILL.md` 是否是最小完备可执行契约：即使 Agent 不加载任何 reference，也能理解主流程、关键约束和 I/O 契约？
- 指令是否采用命令式、自然且可执行的语言；关键规则是否给出足够的理由，使执行者能在异常时调整策略而不偏离边界？
- 是否只保留对稳定执行有帮助、且 Agent 不会自然知道的信息？
- 每个禁止事项是否对应真实错误风险，并优先覆盖会直接导致执行失败的硬边界？

失败信号：

- `SKILL.md` 缺少非目标、I/O 契约、禁止事项或职责分工等必需部分。
- 把关键流程或硬约束放进 reference，导致只读 `SKILL.md` 时无法稳定执行。
- 用“注意质量”“合理处理”“必要时执行”等抽象表述代替明确动作、决策条件或输出要求。
- 禁止事项只是在罗列偏好，无法对应具体的失败模式。
- 创建 README、安装指南、变更日志、空资源目录或其他没有运行价值的辅助产物。

## Gate 4: Source Coverage And Portability

当设计依赖用户经验、已有 skill、外部文档、失败记录或第三方工具时检查：

- 来源是否足以支撑当前架构判断、输出契约和脚本边界？
- 关键缺口和不确定性是否已声明？
- 是否区分可移植核心和产品特定扩展？
- 产品特定 metadata、hooks、tool permissions 或默认 prompt 是否只是扩展，不替代 `SKILL.md`？
- 如果是第三方工具 wrapper，是否做过 adopt / extend / build 判断？

失败信号：

- 来源不足但直接套模板。
- 把平台字段、UI metadata 或工具权限写成所有 agent 都必须支持的通用规则。
- 第三方工具经验没有沉淀安装、认证、调用、失败处理或环境限制。
- 产品特定配置隐藏了 `SKILL.md` 未说明的能力、权限或副作用。

## Gate 5: Runtime Executability And Long-running Flow

- `SKILL.md` 是否告诉 agent 第一件事做什么？
- 是否有清楚的 mode / workflow / state transition？
- 遇到歧义时是否知道什么时候问用户？
- 是否有完成定义？
- 如果使用模板，是否已把模板提示改写成具体运行时指令？
- 长程任务是否在 `SKILL.md` 中完整写明流程、阶段、决策点、失败恢复和最终汇总责任？
- 阶段是否按 Agent 的决策点划分，而非无意义地中断流程，或让 Agent 机械驱动固定指令和脚本？
- 有长程状态时，是否定义 gate、恢复协议、只读视图和真源边界？
- 超长程任务是否评估了可提供 Just In Time 指令的门禁脚本，以便在通过门禁时获得下一阶段所需信息？

失败信号：

- 只有原则，没有流程。
- 只有目录结构，没有执行顺序。
- 没有失败处理。
- 残留 `<<...>>` 占位符、authoring hints、空表格或空示例。
- 长程任务只给出普通步骤列表，没有决策点、恢复路径或最终汇总责任。
- 将所有阶段细节塞进启动上下文，或把阶段切分为单纯的脚本驱动动作。

## Gate 6: Current-state Only Protocol

- 最终 skill 是否只描述当前有效字段、命令、脚本入口、目录协议和输出契约？
- 更新已有 skill 时，是否删除了历史演进说明，而不是追加“旧方式不要用”的提醒？
- 是否没有 legacy、deprecated、old field、previous version、fallback、兼容、旧字段、以前、曾经等历史协议痕迹？
- 如果旧调用方需要支持，是否把兼容处理放到外部 adapter、上游转换或单独迁移任务，而不是写进 skill runtime？
- 是否区分了被禁止的历史协议迁移说明和允许的 runtime state transition？

失败信号：

- “旧字段仍可继续使用”。
- “兼容 fallback 到旧路径”。
- “不要使用以前的 X”。
- “上一版/旧版/曾经如何处理”。
- 在最终 `SKILL.md` 中保留 changelog、版本对比、过渡期说明或协议迁移说明。

## Gate 7: Progressive Disclosure

- `SKILL.md` 是否只保留运行时高频规则？
- references 是否按主题拆分？
- 每个 reference 是否从 `SKILL.md` 直接链接？
- 是否说明每个 reference 的读取时机？
- references 是否只包含补充性的详细说明、正反例、最佳实践或执行技巧，而没有执行所必需的流程、I/O 契约或硬约束？
- 是否避免将本应纳入 `SKILL.md` 的短小碎片化指令拆散到 references？
- 普通设计任务是否只读取压缩后的说明性样例，而不是要求通读原始作者 skill 包？
- 模板读取是否按复杂度选择，而不是启动时通读全部模板？
- 是否避免无运行价值的 README、安装指南、变更日志、quick reference 或空资源目录？
- 大型 reference 是否有目录、检索提示或清晰分段？

失败信号：

- 启动时要求通读所有 references。
- reference 互相深层跳转。
- 存在未链接 reference。
- 要求 agent 把原始作者 skill 包作为普通设计任务的必读材料。
- 简单 skill 套用了 gate/SQLite 模板但没有具体恢复或门禁需求。
- `SKILL.md` 过长且没有拆分，或 reference 很大但没有导航。
- 创建了与运行无关的辅助文档。
- 只有加载 reference 才能知道必填字段、关键禁止事项、主流程或失败恢复方式。

## Gate 8: LLM / Script Boundary And Script Discoverability

- 语义任务是否明确归 LLM？
- 确定性任务是否归脚本？
- 是否禁止临时脚本替代语义判断？
- 是否禁止 LLM 手拼脚本/renderer 权威产物？
- 所有正式脚本是否支持 `--help` 或 `-h`，并输出功能、参数、I/O 契约和示例？
- `SKILL.md` 是否给出每个正式脚本的职责、调用命令和必要 payload 示例，而不是只在 reference 中提及脚本名？
- 测试是否只覆盖脚本可观察的稳定业务行为，而没有静态断言 Skill 指令文本？

失败信号：

- 脚本负责摘要、策略、语义合并。
- LLM 直接写最终机器消费 JSON。
- 有脚本但没有调用示例。
- 脚本没有可发现的参数和 I/O 说明，Agent 只能试错或依赖隐含知识调用。

## Gate 9: I/O And Schema

适用于 automation-facing 或 machine-facing skill。

- 是否写清输入字段、输出字段、成功 shape 和失败 shape？
- required keys 为空时是否仍保留？
- 枚举值是否显式列出？
- payload 是否尽量扁平，字段名是否语义自明，避免含混缩写或需依赖上下文猜测的名称？
- stdout 是否禁止混入日志和 Markdown fence？
- 是否有 schema 或验证脚本建议？

失败信号：

- “输出 JSON”但不给完整对象。
- 失败时自由发挥。
- 文件名/目录不固定。

## Gate 10: Examples And Failure Modes

- 是否至少有 happy path？
- 是否至少有 near-miss 或失败模式？
- 是否有非法输入示例？
- 是否记录了 “Do not attempt” 类失败经验？

失败信号：

- 只有抽象规则，没有锚定示例。
- 只展示成功，不展示失败。
- 没有说明哪些方案已经失败过。

## Gate 11: Evaluation And Iteration

- 是否区分轻量验收和正式评估反馈迭代？
- 是否默认先给轻量 prompts、expectations 或人工 review checklist？
- 若建议正式评估迭代，是否记录三条件 gate：
  - 用户明确同意。
  - 当前环境可调用子代理或等价独立执行器。
  - 输入可模拟/可获取，输出可被用户或规则评价。
- expectations 是否可评价，而不是只写主观愿望？
- description 触发优化是否包含 should-trigger 和 should-not-trigger near-miss？
- 是否从失败反馈中抽象通用规则，而不是只为单个 prompt 打补丁？

失败信号：

- 没有用户同意就设计长评估流程。
- 没有子代理仍声称可以做正式 with-skill / baseline 对照。
- 输出不可评价却强行量化。
- 只测 happy path，没有 near-miss。
- 用户反馈只导致过拟合式补丁，没有抽象为通用 skill 规则。

## Gate 12: Subagent Delegation

适用于设计了 subagent 业务委派的 skill。

- subagent 委派是否明确为可选路径，而不是硬门禁？
- 是否说明当前环境不能委派 subagent 时的串行处理或外部执行路径？
- 是否给出建议委派 prompt？
- payload 是否优先文件化，且字段扁平、语义自明？
- 如果结果优先写文件返回，prompt 是否要求 subagent 先做写盘能力探测？
- 结果协议是否支持“写文件并返回路径”和“stdout 返回同等结构”两种情况？
- 批次拆分策略是否匹配业务特点？
- 能由脚本稳定切分时，是否优先设计脚本生成 batch payload？
- 若由主 agent 切分，是否写清目标批次大小、均衡标准、排序/分组依据和依赖边界？
- 主 agent 是否保留最终汇总、冲突处理、质量把关和用户-facing 输出责任？

失败信号：

- “必须启动 subagent 才能继续”。
- “拆成若干批交给 subagent”，但没有切分原则或结果协议。
- subagent 直接推进 gate、写 SQLite 权威状态或生成最终机器消费 artifact。
- subagent prompt 依赖主 agent 对话上下文，而不是文件化 payload。
- subagent 无写文件权限时没有 probe 和 stdout 返回方案。

## Gate 13: Product Metadata

- 是否真的需要 `agents/openai.yaml` 或其它产品特定配置？
- 若存在 `agents/openai.yaml`，其 `display_name`、`short_description`、`default_prompt` 是否与 `SKILL.md` 能力一致？
- `default_prompt` 是否显式提到 `$skill-name`，且只是短启动提示而非隐藏运行时指令？
- MCP 或外部工具依赖是否只在确实需要时声明？

失败信号：

- 把 `agents/openai.yaml` 当作所有 skill 的默认必备文件。
- UI 元数据夸大能力，或与 `description` 冲突。
- 产品元数据里隐藏了 `SKILL.md` 中没有说明的关键约束或依赖。

## Gate 14: Safety, Privacy, Distribution

公开或共享 skill 需要检查：

- 是否包含真实人名、项目名、路径、客户、内部 API、会议片段？
- 是否包含 token、key、cookie、私有 URL？
- 是否说明依赖和许可证？
- 是否有脚本权限风险、hook、安装副作用？
- 是否包含用户不会预期的权限、外部服务、网络访问、上传、删除、覆盖或全局配置修改？
- 是否已经做过语义脱敏，而不只是关键词搜索？

失败信号：

- 只靠 grep 判断干净。
- 示例看起来像真实项目摘录。
- 脚本会修改全局 agent 配置但 description 没说明。
- skill 的真实意图、依赖或副作用会让用户感到意外。
- 公开版仍保留内部服务名、路径结构、业务字段或可识别的组织术语。

## Review Output Template

```markdown
## Findings
- [High/Medium/Low] <location>: <issue and impact>

## Architecture Fit
- Current tier:
- Recommended tier:
- Over/under-engineering:

## Required Fixes
- ...

## Optional Improvements
- ...

## Validation
- Trigger:
- Structure:
- Behavior:
- Evaluation:
- Product metadata:
- Source coverage:
- Current-state protocol:
- Subagent delegation:
- Safety:
```

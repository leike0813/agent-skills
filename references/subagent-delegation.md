# Subagent Delegation

## Purpose

本文件用于设计 skill 中的 subagent 委派机制。读它的时机：目标任务包含可并行、相互独立、数量较多的语义业务单元，并且希望在当前环境支持时把部分工作委派给 subagent。

Subagent 委派是可选执行模式，不是复杂度 tier，也不是正式评估迭代的替代品。skill 指令必须写成“如果当前环境可以委派 subagent，...”；不能把 subagent 可用性设为硬门禁。

## When To Delegate

适合委派：

- 多个业务单元相互独立，可以并行处理。
- 每个单元需要语义判断，但判断深度有限。
- 单元数量多，主 agent 串行处理会浪费上下文或时间。
- subagent 的局部结果可以被主 agent 统一合并和审查。

典型例子：

- 批量文献条目初筛。
- 多个独立文档的初步摘要。
- 多份材料的证据摘取。
- 多个候选方案的独立优缺点草拟。

不适合委派：

- 需要全局上下文连续推理的核心决策。
- 需要用户交互、确认或策略裁决的步骤。
- gate 状态推进、SQLite 权威写入、最终 renderer 输出等必须由主 agent 或脚本控制的动作。
- 脚本可以确定性完成且不需要语义判断的任务。
- subagent 结果无法被主 agent 验收或合并的任务。

## Availability Rule

skill 中必须明确前提：

```text
If the current environment can delegate to subagents, use the delegation path below.
If subagents are unavailable, process the same batches serially in the main agent and do not block the workflow.
```

不要写：

- “必须启动 subagent 后才能继续。”
- “如果没有 subagent，本 skill 不可用。”
- “subagent 会自动共享主 agent 的上下文。”

## Payload Protocol

Subagent 与主 agent 通常共享工作区，但不共享上下文。委派 payload 应优先文件化。

主 agent 应创建每个批次的 payload 文件，内容至少包括：

- `batch_id`：稳定批次 ID。
- `task_goal`：subagent 要完成的局部目标。
- `input_paths`：允许读取的输入文件路径。
- `output_path`：建议写入的结果文件路径。
- `probe_path`：用于写盘能力探测的临时文件路径，优先放在输出目录或 workspace 临时目录。
- `constraints`：必须遵守的规则和禁止事项。
- `expected_shape`：结果结构、字段、排序或引用要求。
- `stop_conditions`：无法完成时如何报告。

payload 应尽量扁平化，字段名称应语义自明。不要让 subagent 从主对话中猜任务边界。

如果 subagent 的任务需要全局上下文信息，可以根据上下文信息量选择通过 prompt 传递或是通过文件传递。

## Result Protocol

优先让 subagent 写文件返回结果，但必须保留 stdout 退路。不要让 subagent 直接假设自己有写文件权限；委派 prompt 应要求它先做写盘能力探测。

### Write Capability Probe

如果需要文件交付，payload 应提供 `probe_path`。subagent 在正式处理前先尝试创建一个空 probe 文件：

```text
Before producing the result, try to create an empty probe file at <probe_path>.
If the file can be created and observed, file writing is allowed.
If the probe fails because of permissions, read-only filesystem, missing directory, or any other write error, use stdout delivery instead.
```

探测成功后，subagent 可以写入 `output_path`，并返回路径与状态。探测失败时，subagent 必须直接在 stdout 中返回同等结构结果。主 agent 收到 stdout 后，如自身有写权限，可以代为写入目标结果文件。

probe 文件不属于业务结果。prompt 可以要求 subagent 在环境允许时清理 probe 文件；如果清理失败，不应阻塞业务结果返回。

如果希望 subagent 的返回结果必须经过主 agent 的 review，则可以优先考虑 stdout 返回。

主 agent 负责：

- 检查每个结果是否存在或 stdout 是否可解析。
- 判断结果是否满足 `expected_shape`。
- 汇总、去重、冲突处理和最终裁决。
- 把局部结果转化为用户-facing 输出或写入权威状态。

Subagent 不应直接：

- 推进 gate。
- 写 SQLite 权威状态。
- 生成最终机器消费 artifact。
- 替主 agent 做最终策略判断。

## Batch Splitting Strategy

批次拆分没有固定优先级，必须按业务特点决定。

| Strategy | When To Use | Requirements |
| --- | --- | --- |
| Main-agent split | 业务简单、条目均匀、数量不大、低风险 | 主 agent 可以按数量、文件、主题或自然边界切分 |
| Script split | 业务复杂、不均匀、数量大、需要稳定复现 | 设计确定性脚本生成 batch payload，脚本输出批次清单 |
| Instruction-guided split | 暂不写脚本，但仍需主 agent 认真切分 | 在 skill 指令中写清切分原则、目标批次大小、均衡标准和边界处理 |

无论采用哪种策略，都必须保证：

- 每个批次体量适当，不让单个 subagent 承担过大上下文。
- 各批次业务量尽量均衡。
- 强依赖关系不被拆断。
- 批次 ID、输入路径和输出路径稳定。

如果脚本已经能稳定、确定性地切分业务，优先让脚本生成 batch payload。不要让主 agent 重复手工做可脚本化的批处理。

## Delegation Prompt Template

被生成的 skill 若需要 subagent 委派，必须给出建议 prompt。可使用以下骨架：

```text
You are a subagent working on one delegated batch for <skill/task name>.

Read the batch payload at:
<payload_path>

Your task:
- Complete only the batch described in the payload.
- Use only the input files listed in the payload unless the payload explicitly allows more.
- Follow the constraints and expected output shape exactly.
- Do not make final decisions for the whole project.
- Do not advance gates, write authoritative state, or modify files outside the specified output path.

Output:
- Before producing the result, try to create an empty probe file at the payload's probe_path.
- If the probe succeeds, write the result to the payload's output_path and return only {"delivery": "file", "path": "<absolute_output_path>", "status": "ok"}.
- If the probe fails, return the same result structure directly in stdout.
- If a probe file was created and can be removed safely, remove it; if cleanup fails, continue with result delivery.

If blocked:
- Return a structured blocker with batch_id, reason, missing_input, and suggested_next_step.
```

按具体 skill 改写时，只替换任务名、payload 路径、允许读取的上下文和结果 shape。不要把主 agent 的完整推理、未定结论或无关上下文交给 subagent。

## Failure Handling

如果 subagent 不可用：

- 主 agent 串行处理同一批次。
- 或说明需要外部执行支持，但不要让 skill 卡死。

如果结果缺失或格式错误：

- 主 agent 要求重试该批次，或改为串行处理。
- 如果 subagent 声称写入文件但文件不存在，主 agent 要求 subagent stdout 重新提交，或改为串行处理。
- 若批次过大或不均衡，重新切分。
- 若使用脚本切分，优先重新运行脚本生成 batch payload。

如果多个 subagent 给出冲突结果：

- 主 agent 保留最终判断责任。
- 必要时读取原始输入核验。
- 不把冲突原样交给下游机器消费。

## Quality Checklist

- subagent 委派是否明确为可选路径？
- 是否说明当前环境不支持 subagent 时如何继续？
- 每个委派任务是否有 payload 文件协议？
- 结果是否支持文件返回和 stdout 返回两种方式？
- 委派 prompt 是否要求 subagent 先做写盘能力探测，再选择交付路径？
- 批次拆分策略是否匹配业务特点？
- 能脚本稳定切分时，是否优先设计脚本切分？
- 主 agent 是否保留最终汇总、冲突处理和用户-facing 输出责任？

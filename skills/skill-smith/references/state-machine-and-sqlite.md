# State Machine And SQLite

## When To Use

只有在以下条件成立时才推荐 SQLite/state-machine：

- 任务长、阶段多、步骤依赖强。
- 中途可能发生上下文压缩或跨 session 恢复。
- 后续步骤必须读取前序决策，不能让 agent 重新指定。
- 输出必须稳定、可审计、可重复渲染。
- 弱模型也需要被强轨道约束。

不要因为 skill “看起来高级”就使用 SQLite。中等任务优先考虑轻状态机、references 和辅助脚本。

## Core Concepts

### SQLite SSOT

SQLite 是唯一运行态真源：

- 语义结果先整理为 payload。
- stage 脚本校验后写入 DB。
- 后续阶段只读取 DB，不重新从 prompt 或记忆中指定前序决策。
- 最终产物由 DB 渲染。

### Gate

gate 是唯一合法的下一步判定入口：

- 读取当前 DB 状态。
- 检查 blocker、repair、pending confirmations。
- 返回唯一 `next_action`。
- 返回当前动作需要读的 references。
- 返回 payload 示例、runtime digest 或 resume packet。

### Stage Runtime

stage runtime 是唯一正式写入入口：

- 执行 `next_action`。
- 校验 payload。
- 写 DB。
- 记录 action receipt。
- 不决定下一步。

### Read-only Views

只读视图用于人和 agent 理解当前状态：

- `01-agent-resume.md`
- workboard
- coverage matrix
- drafting board
- output preview

只读视图不是写入真源，不能直接编辑来推进状态。

## Minimal Loop

```text
run gate
  -> read next_action, blocker, instruction_refs, payload example
  -> LLM performs semantic work if required
  -> stage runtime writes structured payload
  -> run gate again
  -> read refreshed resume/view
```

## Resume Protocol

长程 skill 必须写恢复协议：

1. 不凭对话记忆继续。
2. 先运行 gate 或 gate-and-render。
3. 读取 resume packet。
4. 读取当前阶段只读视图。
5. 读取 gate 指定的 reference。
6. 只执行 gate 返回的下一步。

## Gate Payload Should Include

- `current_stage`
- `stage_gate`
- `next_action`
- `status_summary`
- `instruction_refs`
- `core_instruction` 或 `runtime_digest`
- `execution_note`
- `next_action_payload_example`
- `blockers`
- `pending_user_confirmations`
- `repair_sequence`
- `resume_packet`

## Output Rendering

最终公开产物应由 renderer 从 DB 生成，尤其在以下场景：

- stdout JSON 被下游消费。
- Markdown/LaTeX 需要稳定结构。
- citation/reference/report 等多文件必须互相一致。
- 弱模型容易漏字段或改变顺序。

禁止 LLM 手拼 renderer 产物。LLM 可以生成语义字段，脚本负责装配和校验。

## Failure Recovery

必须定义：

- gate 卡住时看哪些字段。
- 哪些状态可以 repair。
- 哪些文件可以删除重跑。
- 哪些表或视图绝对禁止手改。
- 脚本失败时是否停止、回滚或进入 repair。

## Design Checklist

- 是否真的需要 SQLite？
- 是否有唯一 DB 路径和 workspace 约定？
- 是否每个阶段都有完成条件？
- 是否每次写入后必须重新 gate？
- 是否有恢复入口？
- 是否只读视图与真源边界清楚？
- 是否最终产物只能由 renderer 生成？

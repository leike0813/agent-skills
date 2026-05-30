# Gate-driven Extension Template

## Use When

适用于 Tier 5 gate-driven long workflow。任务多阶段、强依赖、不能跳步，但不一定需要完整 SQLite state-machine 时使用。通常与 minimal、reference-backed、script-assisted 模板组合。

## Authoring Rules

- gate 是唯一合法下一步入口；不要把 `next_action` 写成建议。
- 每个 `next_action` 必须可枚举，并有明确 payload 或执行规则。
- 每次正式写入后必须重新运行 gate。
- 删除所有 `<<...>>` 占位符和 authoring 提示。

## Extension Sections

把以下章节合并进目标 `SKILL.md`：

````markdown
## Runtime Model

This skill uses a gate-driven workflow:

- Gate script: `scripts/<<gate_script>>`
- Stage script: `scripts/<<stage_script>>`
- State source: <<文件、目录、数据库或其它真源>>
- Read-only views: <<可选；给用户或 agent 恢复用，不是真源>>

## Gate Discipline

1. Run the gate before starting work.
2. Execute only the returned `next_action`.
3. Read only the references returned or required for that action.
4. After any state-changing action, run the gate again.
5. Stop if the gate returns a blocker.

Minimal gate command:

```bash
<<gate command example>>
```

Expected gate fields:

- `next_action`: one of `<<action>>`, `<<action>>`, `blocked`, `done`.
- `instruction_refs`: references to read for the current action.
- `blockers`: missing inputs or invalid state.
- `command_example`: recommended script command for the next action.

## Valid Next Actions

| `next_action` | Meaning | Agent responsibility | Script responsibility |
| --- | --- | --- | --- |
| `<<action>>` | <<含义>> | <<LLM 要做的语义工作>> | <<脚本要做的确定性工作>> |
| `<<action>>` | <<含义>> | <<LLM 要做的语义工作>> | <<脚本要做的确定性工作>> |

## Stage Payloads

For `<<action>>`, submit:

```json
{
  "action": "<<action>>",
  "<<field>>": "<<value>>"
}
```

Do not mark a stage complete unless <<完成条件>>.

## Blockers And Repair

- If gate returns `blocked`, report <<用户需要知道的最小信息>>.
- If payload validation fails, <<修复规则>>.
- If context was compressed, resume by <<恢复入口>> instead of reconstructing state from memory.
````

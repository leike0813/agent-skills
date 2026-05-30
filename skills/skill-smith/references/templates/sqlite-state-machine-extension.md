# SQLite State-machine Extension Template

## Use When

适用于 Tier 6 SQLite state-machine skill：长程、可恢复、强输出稳定性、上下文压缩后必须继续，或最终产物必须由 DB 渲染。通常与 gate-driven 和 script-assisted 模板组合。

## Authoring Rules

- SQLite 是唯一运行态真源；只读视图不是写入入口。
- LLM 产出语义 payload，脚本负责写库、状态迁移和渲染。
- 最终机器消费产物必须由 renderer 从 DB 生成。
- 删除所有 `<<...>>` 占位符和 authoring 提示。

## Extension Sections

把以下章节合并进目标 `SKILL.md`：

````markdown
## SQLite Runtime Model

Runtime source of truth:

- Database: `<<runtime.db path or convention>>`
- Workspace: `<<workspace path convention>>`
- Read-only views: `<<views path convention>>`
- Final outputs: `<<artifact path convention>>`

The database is authoritative for:

- <<状态、阶段、用户确认、中间产物等>>

The LLM must not manually edit:

- <<DB 文件、renderer 输出、权威 JSON/Markdown bundle 等>>

## State Machine

Valid states:

- `<<state>>`: <<含义和进入条件>>
- `<<state>>`: <<含义和进入条件>>
- `blocked`: <<阻塞含义>>
- `done`: <<完成含义>>

State transitions must happen through `scripts/<<stage_script>>` or another formal runtime script.

## Resume Protocol

When resuming after context compression:

1. Run `scripts/<<gate_script>>`.
2. Read the rendered resume packet or read-only view returned by the gate.
3. Continue only with the returned `next_action`.
4. Do not infer completed work from conversation memory if it is absent from the DB.

Resume command:

```bash
<<resume or gate command example>>
```

## Renderer Authority

Use `scripts/<<renderer_script>>` to generate final outputs:

```bash
<<renderer command example>>
```

The renderer owns:

- <<final JSON / Markdown / report / bundle>>

The LLM may draft semantic content for DB payloads, but must not hand-assemble renderer-owned artifacts.

## Repair And Recovery

- If DB validation fails, <<repair procedure>>.
- If a required row or artifact is missing, return to gate and follow `next_action`.
- If user confirmation is missing, stop at the confirmation gate.
````

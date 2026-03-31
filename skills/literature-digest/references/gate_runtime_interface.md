# Gate Runtime Interface

本文件是 `scripts/gate_runtime.py` 的运行时接口说明。它不描述阶段业务细则；阶段细则仍由 `references/step_*.md` 负责。文中涉及的参数名与 payload 字段均按 `SKILL.md` 的“参数词表（全项目统一）”理解。

## 角色

`gate_runtime.py` 是唯一合法的状态机门禁入口。它负责：

- 读取 `<cwd>/.literature_digest_tmp/literature_digest.db`
- 读取 `workflow_state`
- 检查当前阶段前置条件是否满足
- 给出唯一 `next_action`
- 返回当前动作应读取的文档与 SQL 示例

`gate_runtime.py` **不执行阶段动作**；阶段动作只能通过 `scripts/stage_runtime.py <next_action>` 执行。

全局约束：

- gate 一旦确认某项前置状态已经存在于 DB，后续主路径阶段不得再通过 CLI / JSON 重新指定它
- stage 5 的固定顺序是：`prepare_citation_workset` → `persist_citation_semantics` → `persist_citation_timeline` → `persist_citation_summary` → `render_and_validate`
- 例如：
  - `runtime_inputs.source_path` 一旦在 bootstrap 写入，`normalize_source` 只能读取它
  - `section_scopes.citation_scope` 一旦在 stage 2 写入，`prepare_citation_workset` 只能读取它
  - `render_and_validate --mode render` 只能读取 DB 内容；它不允许重传输入源或临时覆盖输出目录

## CLI

命令：

```bash
python scripts/gate_runtime.py [--db-path PATH]
```

参数：

- `--db-path`
  - 可选。显式指定运行时 DB 路径。
  - 缺省时使用 `<cwd>/.literature_digest_tmp/literature_digest.db`。

## Exit Code

- `0`
  - gate 可继续执行。
  - 包括两种场景：
    - DB 不存在，此时 `next_action=bootstrap_runtime_db`
    - 当前阶段 `stage_gate=ready`
- `2`
  - gate 判定当前状态被阻塞，必须先修复。
  - 典型 `next_action`：
    - `repair_workflow_state`
    - `repair_db_state`

## stdout Payload

stdout 只输出一个 JSON 对象，字段固定为：

- `current_stage: string`
  - 当前状态机阶段。
- `current_substep: string`
  - 当前阶段中的子步骤标识。
- `stage_gate: string`
  - 当前门禁状态。
  - 当前实现使用：
    - `ready`
    - `blocked`
- `next_action: string`
  - 允许执行的唯一下一动作。
  - 该值直接映射到 `scripts/stage_runtime.py <next_action>`。
- `status_summary: string`
  - 当前状态摘要，供 agent 判断是正常推进还是 repair。
- `required_reads: string[]`
  - 当前阶段预期读取的表/字段。
- `required_writes: string[]`
  - 当前阶段预期写入的表/字段。
- `instruction_refs: object[]`
  - 当前动作需要优先阅读的文档列表。
  - 每项结构：
    - `path: string`
    - `section: string`
  - 用途：
    - 告诉 agent 当前这一步该补读哪些附录
    - 避免 agent 在启动阶段一次性读取全部 `references/` 文档
- `core_instruction: string`
  - gate 每一步都返回的固定核心指令块。
  - 用途：
    - 反复提醒跨阶段都必须遵守的主规则
    - 让长上下文场景中的 agent 不必只靠早先读过的 `SKILL.md` 记忆执行纪律
- `execution_note: string`
  - 当前动作的一条短执行提示。
  - 用途：
    - 收口当前一步最重要的即时约束
    - 与 `instruction_refs`、`core_instruction` 配合使用；`core_instruction` 给固定主指令，`execution_note` 给短提示，`instruction_refs` 给详细附录
- `sql_examples: object[]`
  - 当前动作对应的最小 SQL 示例列表。
  - 每项结构：
    - `purpose: string`
    - `sql: string`
    - `notes: string`
- `resume_packet: object`
  - 恢复执行所需的最小上下文。
  - 包含：
    - `db_path`
    - `active_batch_kind`
    - `active_batch_index`
    - `last_error_code`
    - `why_paused`

## `next_action` 集合

当前 gate 可能返回的动作包括：

- `bootstrap_runtime_db`
- `normalize_source`
- `persist_outline_and_scopes`
- `persist_digest`
- `prepare_references_workset`
- `persist_reference_entry_splits`
- `persist_references`
- `prepare_citation_workset`
- `persist_citation_semantics`
- `persist_citation_timeline`
- `persist_citation_summary`
- `render_and_validate`
- `repair_workflow_state`
- `repair_db_state`

除 repair 动作外，其余动作都必须通过 `scripts/stage_runtime.py` 执行。

## `instruction_refs` 约束

`instruction_refs` 的设计目标是把 agent 导航到“当前动作真正需要读的文档”，而不是要求通读整个 skill 包。

读取纪律：

- 启动时先读 `SKILL.md`
- 进入具体阶段后，再按 `instruction_refs` 读取附录
- 同时遵守 gate 返回的 `core_instruction` 与 `execution_note`
- 若当前 step 因 payload 错误被 gate 卡住，优先查看当前阶段文档和 `stage_runtime_interface.md` 中的 payload 约束
- 若 gate 已进入 repair 路径，再补读 `references/failure_recovery.md`

## `core_instruction` 约束

`core_instruction` 是 gate 每一步都返回的固定核心指令块，用来重复提醒跨阶段都必须遵守的主规则。

使用方式：

- 每次读取 gate payload 后，都先看 `next_action`
- 再看 `core_instruction`
- 再看 `execution_note`
- 然后按 `instruction_refs` 读取当前阶段附录

职责分工：

- `core_instruction`：跨阶段常驻规则
- `execution_note`：当前一步最关键的即时执行提示
- `instruction_refs`：当前一步需要按需阅读的详细附录

## `execution_note` 约束

`execution_note` 是 gate 给当前 `next_action` 的短提示，不替代附录，只负责强调这一步最关键的即时执行要求。

使用方式：

- 每次读取 gate payload 后，都先看 `next_action`
- 再看 `execution_note`
- 然后按 `instruction_refs` 读取当前阶段附录

特殊约束：

- 当 `next_action = bootstrap_runtime_db` 时，`execution_note` 会提示当前步先确定最终输出目录并写入 DB
- 当 `next_action = render_and_validate` 时，`execution_note` 会提示当前已经进入最终发布前一步
- 并提示最终 assistant 输出应直接采用 render 脚本 stdout 返回的 JSON
- 并说明 render 会读取 DB 中的 `output_dir`，同时把同一个 JSON 镜像写到 `./literature-digest.result.json`
- 这条约束只放在 stage 6 的 `execution_note` 中，不作为更高层的全局提示重复出现

返回规律：

- 阶段文档优先：
  - `stage_0_bootstrap` / `stage_1_normalize_source`
    - `references/step_01_bootstrap_and_source.md`
  - `stage_2_outline_and_scopes`
    - `references/step_02_outline_and_scopes.md`
  - `stage_3_digest`
    - `references/step_03_digest_generation.md`
  - `stage_4_references`
    - `references/step_04_references_extraction.md`
  - `stage_5_citation`
    - `references/step_05_citation_pipeline.md`
  - `stage_6_render_and_validate` / `stage_7_completed`
    - `references/step_06_render_and_validate.md`
- 通用补充文档：
  - `references/stage_runtime_interface.md`
  - `references/sql_playbook.md`
  - repair 阶段额外补 `references/failure_recovery.md`
  - references 阶段会额外补 `references/bibliography_formats.md`

## `sql_examples` 约束

`sql_examples` 只提供**当前 `next_action` 的最小 SQL 示例**，不提供全量 SQL 手册。

使用方式：

- 先看 `purpose`
- 再决定是否直接使用 `sql`
- 结合 `notes` 理解写入意图

如果当前动作是 repair，`sql_examples` 默认偏向：

- 先查缺什么
- 再修 `workflow_state`

## 前置条件检查逻辑

gate 至少检查这些关键前置：

- `stage_1_normalize_source`
  - `runtime_inputs.source_path`
- `stage_2_outline_and_scopes`
  - `source_documents.normalized_source`
- `stage_3_digest`
  - `outline_nodes`
- `stage_4_references`
  - `source_documents.normalized_source`
  - `section_scopes.references_scope`
  - 当 `next_action = persist_reference_entry_splits` 时，还要求：
    - `reference_entries`
    - `reference_parse_candidates`
    - 当前 `prepare_references_workset` 已返回 `requires_split_review=true`
    - 当前复核对象只来自 `suspect_blocks`
    - `execution_note` 只允许做 `split` / `keep` / `merge` 边界决策，不允许抽 `author/title/year`
  - 当 `next_action = persist_references` 时，还要求：
    - `reference_entries`
    - `reference_parse_candidates`
- `stage_5_citation`
  - `source_documents.normalized_source`
  - `section_scopes.citation_scope`
  - `reference_items`
- `stage_6_render_and_validate`
  - `digest_slots`
  - `digest_section_summaries`
  - `reference_items`
  - `section_scopes.citation_scope`
  - `citation_workset_items`
  - `citation_items`
  - `citation_summary`
  - `citation_unmapped_mentions`
- `stage_7_completed`
  - `artifact_registry.digest_path`
  - `artifact_registry.references_path`
  - `artifact_registry.citation_analysis_path`

若前置缺失，gate 会把：

- `stage_gate` 置为 `blocked`
- `next_action` 改为 `repair_db_state`
- `status_summary` 写成缺失项摘要

## 最小示例

### 1. DB 缺失

```json
{
  "current_stage": "stage_0_bootstrap",
  "current_substep": "bootstrap_runtime_db",
  "stage_gate": "blocked",
  "next_action": "bootstrap_runtime_db",
  "core_instruction": "## 核心执行指令\n..."
}
```

### 2. 正常推进

```json
{
  "current_stage": "stage_4_references",
  "current_substep": "prepare_references_workset",
  "stage_gate": "ready",
  "next_action": "prepare_references_workset",
  "core_instruction": "## 核心执行指令\n...",
  "execution_note": "Prepare the references workset from the stored references_scope first; let the script build entries, batches, and parse candidates."
}
```

### 3. 前置缺失

```json
{
  "current_stage": "stage_6_render_and_validate",
  "stage_gate": "blocked",
  "next_action": "repair_db_state",
  "status_summary": "missing prerequisites: digest_slots"
}
```

# Stage Workflow

本文件给出 gate-driven runtime 的阶段总览，阶段编号以 `workflow_state.workflow_stage` 为准。

它是状态机与门禁的总览文档，不是首次执行时的主入口。默认先读 `SKILL.md`；只有当你需要快速核对某个 stage 的 `next_action`、表归属或门禁时，再回来看本文件。

若你已经拿到了 gate 返回结果，执行具体动作时应先看 `next_action_payload_example`；只有样例仍不足以执行时，再去读对应 `stageN-playbook.md`。

## Workflow Table

| Workflow Stage | Playbook | Allowed `next_action` | 关键门禁 | 主要真源表 |
| --- | --- | --- | --- | --- |
| `stage_0_bootstrap` | `stage0-playbook.md` | `bootstrap_runtime_db` | 尚未建立 DB | `runtime_workspace`, `manuscript_source` |
| `stage_1_intake_and_inventory` | `stage1-playbook.md` | `persist_intake_and_inventory` | intake / supporting-elements inventory 未完成 | `manuscript_intake`, `supporting_elements_inventory` |
| `stage_2_manuscript_analysis` | `stage2-playbook.md` | `confirm_language_context`, `persist_runtime_template_translation`, `persist_manuscript_analysis`, `persist_raw_scope_segments`, `persist_semantic_source_units` | 语言上下文未确认，或工作区模板副本未就绪，或 analysis 未完成，或 raw segments / semantic units 尚未落库 | `target_settings`, `manuscript_analysis`, `raw_scope_segments`, `semantic_source_units`, `pending_confirmations` |
| `stage_3_target_settings` | `stage3-playbook.md` | `persist_target_settings_basics`, `persist_content_selection_board`, `confirm_content_selection`, `persist_style_profile`, `finalize_target_settings` | 基本设置未完成，或内容取舍三列表未确认，或 style profile 未完成，或 target settings 未最终确认 | `target_settings`, `content_selection_items`, `style_profile`, `pending_confirmations` |
| `stage_4_condensation_plan` | `stage4-playbook.md` | `persist_condensation_plan`, `confirm_condensation_plan`, `persist_section_rewrite_plan`, `confirm_section_rewrite_plan` | condensation plan 未批准，或 section rewrite plan 未落库/未批准 | `condensation_plan`, `section_rewrite_plan`, `pending_confirmations` |
| `stage_5_final_drafting` | `stage5-playbook.md` | `prepare_section_drafting`, `persist_section_draft`, `approve_section_draft`, `persist_output_target`, `persist_translated_sections`, `render_final_output_bundle` | section loop 未全部批准，或最终输出目录未确认，或 translated sections 未落库，或 final bundle 未渲染 | `draft_sections`, `translated_sections`, `draft_section_sources`, `draft_section_events`, `output_targets`, `final_outputs` |
| `stage_6_completed` | - | `completed` | 全部门禁满足 | 全表 |

## Gate Rules

- 任何时刻都先跑 gate，再决定下一步。
- 任何写库动作执行后，都必须重新跑 gate。
- 只能执行 gate 返回的 `next_action`。
- `blockers` 与 `pending_confirmations` 都属于正式门禁。
- Stage 5 是循环门禁：
  - 未准备 section 时，先 `prepare_section_drafting`
  - 当前 section 字数校验失败时，只能继续 `persist_section_draft`
  - 当前 section 未获批准时，只能继续 `approve_section_draft`
  - 所有 section 批准后，才可进入 `persist_output_target`
  - 输出目录确认后，才可进入 `render_final_output_bundle`

## Stage Notes

### Stage 1

- 只做 deterministic intake 与 supporting-elements inventory。
- 不接受语义 payload。

### Stage 2

- 先确认 `working_language` 与初始 `target_language`。
- 若工作语言不是 `zh/en`，必须先补齐工作区模板副本翻译，才能继续后续 Stage 2 动作。
- 先写 manuscript analysis。
- manuscript analysis 的范围模型固定为 `main_scope + main_scope_locator + aux_scopes[*]`。
- analysis 完成后，必须先执行 `persist_raw_scope_segments`。
- raw segmentation 完成后，必须再执行 `persist_semantic_source_units`。
- `raw_scope_segments` 只是事实层 raw blocks，且必须带 `scope_role=main|aux`。
- `semantic_source_units` 才是后续 section-level rewrite plan 的正式写作来源。

### Stage 3

- 先写基本目标设置，再进入内容取舍建议板。
- Stage 3 会根据最终体例/模板覆盖 Stage 2 的 `target_language` 初值。
- 内容取舍建议板基于 `semantic_source_units`，生成 `must_keep` / `simplify_first` / `must_avoid` 三类建议项。
- 三类列表未确认前，不得进入最终 Stage 3 确认。
- 内容取舍确认后，必须在 Stage 3 内继续完成 `persist_style_profile`。
- `user_confirmed=true` 只代表 Stage 3 的基本设置、内容取舍和风格画像都已完成。

### Stage 4

- 先写 condensation plan 主方案。
- 主方案批准后，必须再写 `section_rewrite_plan`。
- `section_rewrite_plan` 写完后，还必须先经过用户批准，才能进入 Stage 5。
- section rewrite plan 可以吸收 aux 支撑内容，但必须通过 semantic units 间接使用，并写清使用理由。
- Stage 5 的 section 写作只能基于 `section_rewrite_plan`，不得脱离它自由发挥。

### Stage 5

- 采用 top-level section 粒度的循环式 drafting gate。
- 每节都必须经历：准备 → 撰写 → 字数校验 → 审阅 → 批准。
- section 草稿真源始终保存 `working_language` 版本。
- 审阅工件位于 `section-reviews/`。
- section provenance 的主路径是 `semantic_unit:<unit_id>`。
- 审阅工件必须显示每个 semantic unit 的 main/aux 构成。
- 全部 section 批准后，先确认输出目录，再写入 translated sections，最后渲染最终 bundle。
- 最终 bundle 渲染是 assembly-only，只允许装配已翻译 section drafts，不允许在这一层继续写作或润色。

### Stage 6

- `final-draft.tex`、`rewrite-report.md` 与输出目录下的 `images/` 已完成渲染。
- gate 返回 `completed`，不再允许新的 stage write。

# Runtime Database Contract

运行态唯一真源：

- `.paper-condenser-tmp/<document-slug>/paper-condenser.db`

## 逻辑表

- `runtime_workspace`
  - workspace 元信息、slug、路径
- `workflow_state`
  - 当前阶段、`current_substep`、`active_section_id`、`next_action`、blockers、pending confirmations 摘要
- `manuscript_source`
  - source path、source type、source id
- `manuscript_intake`
  - `content_preview`、`source_stats`、`intake_status`
- `supporting_elements_inventory`
  - figures / tables / citations / bibliography inventory
- `manuscript_analysis`
  - `main_scope`、`main_scope_locator`、`aux_scopes`、`topic`、`main_work`、`novelty`、`section_outline`、`removable_candidates`、`open_questions`、`status`
- `raw_scope_segments`
  - main/aux 范围内 paragraph / figure / table / display block 的事实型 raw segmentation
  - 每条记录额外带 `scope_role`、`scope_bucket_id`、`scope_label`
- `semantic_source_units`
  - LLM 审核后的语义写作单元
- `semantic_source_unit_members`
  - semantic unit 与 raw segments 的映射
- `semantic_source_unit_elements`
  - semantic unit 关联的 figure / table / citation / bibliography 线索
- `target_settings`
  - Stage 3 基本设置、三类列表汇总与 `user_confirmed`
- `content_selection_items`
  - Stage 3 内容取舍建议 / 确认项
- `content_selection_item_units`
  - 每个内容取舍项绑定的 semantic units
- `style_profile`
  - 风格画像与 `status`
- `condensation_plan`
  - Stage 5 主方案与 `approval_status`
- `section_rewrite_plan`
  - 每个目标 section 的细化转写方案
- `section_rewrite_plan_sources`
  - 每个目标 section 对应的 semantic units / 图表 / citations 来源
- `draft_sections`
  - 每节 draft 内容、实际字数、字数校验状态、审阅状态
- `draft_section_sources`
  - 每节草稿的 semantic unit 溯源记录
- `draft_section_events`
  - 每节的准备、撰写、校验、审阅日志
- `output_targets`
  - 最终输出目录、图片目录、用户确认状态
- `final_outputs`
  - `final_draft_tex`、`rewrite_report_md`、`status`
- `pending_confirmations`
  - 当前仍待用户确认的事项
- `action_log`
  - 每次 stage write 的审计记录

## 状态字段

- `workflow_state.workflow_stage`
  - `stage_0_bootstrap`
  - `stage_1_intake_and_inventory`
  - `stage_2_manuscript_analysis`
  - `stage_3_target_settings`
  - `stage_4_style_profile`
  - `stage_5_condensation_plan`
  - `stage_6_final_drafting`
  - `stage_7_completed`
- `workflow_state.current_substep`
  - 当前唯一允许执行的子动作
- `workflow_state.active_section_id`
  - Stage 6 当前活跃 section
- `manuscript_analysis.status`
  - `draft` / `analysis_complete`
- `target_settings.user_confirmed`
  - `false` / `true`
- `target_settings.basics_completed`
  - `false` / `true`
- `target_settings.content_selection_board_ready`
  - `false` / `true`
- `target_settings.content_selection_confirmed`
  - `false` / `true`
- `style_profile.status`
  - `draft` / `complete`
- `condensation_plan.approval_status`
  - `draft` / `approved`
- `section_rewrite_plan.status`
  - 默认 `planned`
- `draft_sections.count_check_status`
  - `pending` / `failed` / `passed`
- `draft_sections.review_status`
  - `draft` / `pending_review` / `approved` / `rejected`
- `final_outputs.status`
  - `draft` / `complete`

## 渲染关系

- gate 负责根据数据库重渲染所有 Markdown 视图。
- 中间工件的渲染链路固定为：
  - DB record
  - `runtime_core.py` 生成 view-model
  - `runtime_rendering.py` 加载 `assets/render-templates/*.md.j2`
  - 输出只读 Markdown 视图
- Stage 2 的语义链路固定为：
  - manuscript analysis
  - `persist_raw_scope_segments`
  - `persist_semantic_source_units`
- manuscript analysis 的范围模型固定为：
  - 一个 `main_scope`
  - 一个 `main_scope_locator`
  - 零到多个 `aux_scopes[*]`
- raw segmentation 统一落在一张表中，但必须保留 main/aux role 信息。
- Stage 5 / 6 的写作规划与 provenance 主路径固定为：
  - `semantic_source_units`
  - `section_rewrite_plan_sources`
  - `draft_section_sources`
- Stage 3 的内容取舍链路固定为：
  - `persist_target_settings_basics`
  - `persist_content_selection_board`
  - `confirm_content_selection`
  - `finalize_target_settings`
- `final-draft.tex` 与 `rewrite-report.md` 也由数据库渲染。
- 文件从属于数据库，而不是与数据库并列。
- 若中间工件模板缺失或模板渲染失败，runtime 必须非零退出。

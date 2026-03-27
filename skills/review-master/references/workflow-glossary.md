# Workflow Glossary

这份文档是 `review-master` 的单一术语与命名真源。其他文档、playbook、样例路径和 fixture 都必须与这里保持一致。

## 正式阶段名称

- `stage_1`
  - 入口解析与 workspace 初始化
- `stage_2`
  - 原稿结构分析
- `stage_3`
  - 原始审稿意见块抽取、去重、归并和 canonical atomic item 形成
- `stage_4`
  - atomic workboard 规划
- `stage_5`
  - 逐条策略与执行
- `stage_6`
  - 交互式改稿、revision audit 与 thread-level response 覆盖闭环

## 正式对象命名

### 数据库真源

- `review-master.db`
  - 运行时唯一真源

### 只读渲染视图

- `01-agent-resume.md`
- `02-manuscript-structure-summary.md`
- `03-style-profile.md`
- `04-raw-review-thread-list.md`
- `05-atomic-review-comment-list.md`
- `06-thread-to-atomic-mapping.md`
- `07-review-comment-coverage.md`
- `08-atomic-comment-workboard.md`
- `09-supplement-suggestion-plan.md`
- `10-supplement-intake-plan.md`
- `11-manuscript-revision-guide.md`
- `12-manuscript-execution-graph.md`
- `13-revision-action-log.md`
- `14-response-coverage-matrix.md`
- `15-response-letter-preview.md`
- `16-response-letter-preview.tex`
- `17-final-assembly-checklist.md`
- `response-strategy-cards/{comment_id}.md`

### 最终导出产物

正式产物 id 固定为：

- `working_manuscript`
- `response_markdown`
- `response_latex`
- `latexdiff_manuscript`

如果需要给出样例文件路径，可以额外写出具体文件，但不得用样例路径替代正式产物 id。

## 正式脚本名称

- `review-master/scripts/detect_main_tex.py`
  - 入口辅助脚本
- `review-master/scripts/init_artifact_workspace.py`
  - workspace 初始化脚本
- `review-master/scripts/gate_and_render_workspace.py`
  - `gate-and-render` 核心脚本
- `review-master/scripts/capture_revision_action.py`
  - Stage 6 revision 审计捕获脚本
- `review-master/scripts/commit_revision_round.py`
  - Stage 6 正式提交流程脚本（capture -> gate-and-render）

`gate-and-render` 是唯一正式称呼。所有文档、恢复包和用户交互都使用这一称呼。

## 正式 action id 集合

### 阶段推进动作

- `enter_stage_2`
- `enter_stage_3`
- `enter_stage_4`
- `enter_stage_5`

### 确认动作

- `request_stage3_coverage_confirmation`
- `request_stage4_confirmation`
- `request_pending_confirmation`

### Stage 5 执行动作

- `set_active_comment`
- `author_strategy_card`
- `author_comment_drafts`
- `advance_active_comment`
- `resolve_blockers`

### Stage 6 动作

- `enter_stage_6`
- `record_revision_action`
- `refresh_response_coverage`
- `review_stage6_completion`
- `generate_latexdiff_preview`
- `stage_6_completed`

### 阻断动作

- `blocked_until_db_state_fixed`
- `blocked_enter_stage_5`
- `blocked_execute_active_comment`
- `blocked_complete_active_comment`
- `blocked_stage6_completion`

## action_id 与 recipe_id 的边界

- `action_id`
  - 表示当前推荐执行的 workflow 动作
- `recipe_id`
  - 表示为支撑该动作而应采用的标准写库 recipe

同一 recipe 可以服务多个 action，但 action 不能被 recipe 名字替代。

## Stage 6 运行时语义

- `workspace_manuscript_copies`
  - 记录 `source_snapshot` 与 `working_manuscript`
- `revision_plan_actions`
  - Stage 6 执行 backlog
- `revision_plan_dependencies`
  - Stage 6 执行依赖关系
- `revision_action_logs`
  - 每轮明确修改的正式审计记录
- `revision_action_log_file_diffs`
  - 每轮修改对应的文件级 diff 摘录
- `working_copy_file_state`
  - 记录当前稿件文件的 snapshot / audited / current 状态
- `response_thread_rows`
  - 由已确认策略、revision logs 与 thread-level 聚合共同生成
- `response_thread_action_log_links`
  - 记录 thread 与 revision log 的覆盖关系

## Stage 5 completion 字段语义

- `manuscript_execution_items_done`
  - 只表示 Stage 5 的 manuscript draft 真源已经写入
- `response_draft_done`
  - 只表示 Stage 5 的 response draft 真源已经写入
- 它们都不表示 Stage 6 的最终文案或最终导出已经完成

## 样例与 fixture 路径命名

playbook 示例中，保存脚本 JSON 输出的正式目录名固定为：

- `gate-and-render-output/`

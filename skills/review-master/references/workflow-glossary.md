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
  - 风格画像、位置级 manuscript 最终文案版本生成、thread-level row 组装与双阶段导出

## 正式对象命名

### 数据库真源

- `review-master.db`
  - 运行时唯一真源

### 只读渲染视图

- `01-agent-resume.md`
- `02-manuscript-structure-summary.md`
- `03-raw-review-thread-list.md`
- `04-atomic-review-comment-list.md`
- `05-thread-to-atomic-mapping.md`
- `07-atomic-comment-workboard.md`
- `08-style-profile.md`
- `09-action-copy-variants.md`
- `10-response-letter-outline.md`
- `11-export-patch-plan.md`
- `12-response-letter-table-preview.md`
- `13-response-letter-table-preview.tex`
- `14-supplement-suggestion-plan.md`
- `16-final-assembly-checklist.md`
- `response-strategy-cards/{comment_id}.md`

### 最终导出产物

正式产物 id 固定为：

- `marked_manuscript`
- `clean_manuscript`
- `response_markdown`
- `response_latex`

如果需要给出样例文件路径，可以额外写出具体文件，但不得用样例路径替代正式产物 id。

## 正式脚本名称

- `review-master/scripts/detect_main_tex.py`
  - 入口辅助脚本
- `review-master/scripts/init_artifact_workspace.py`
  - workspace 初始化脚本
- `review-master/scripts/gate_and_render_workspace.py`
  - `gate-and-render` 核心脚本
- `review-master/scripts/export_manuscript_variants.py`
  - manuscript 导出辅助脚本

`gate-and-render` 是唯一正式称呼。不要再把它称作 `validator`。

## 正式 action id 集合

### 阶段推进动作

- `enter_stage_2`
- `enter_stage_3`
- `enter_stage_4`
- `enter_stage_5`

### 确认动作

- `request_stage4_confirmation`
- `request_pending_confirmation`
- `request_variant_selection`

### Stage 5 执行动作

- `set_active_comment`
- `author_strategy_card`
- `author_comment_drafts`
- `advance_active_comment`
- `resolve_blockers`

### Stage 6 动作

- `author_style_profiles`
- `generate_action_copy_variants`
- `assemble_response_thread_rows`
- `prepare_export_patches`
- `export_marked_manuscript`
- `final_review_and_clean_export`
- `stage_6_completed`

### 阻断动作

- `blocked_until_db_state_fixed`
- `blocked_enter_stage_5`
- `blocked_execute_active_comment`
- `blocked_complete_active_comment`
- `blocked_final_export`
- `blocked_clean_export_before_marked_review`

## action_id 与 recipe_id 的边界

- `action_id`
  - 表示当前推荐执行的 workflow 动作
- `recipe_id`
  - 表示为支撑该动作而应采用的标准写库 recipe

同一 recipe 可以服务多个 action，但 action 不能被 recipe 名字替代。

## Stage 6 版本语义

- `action_copy_variants`
  - 只表示每个 `strategy_card_action` 的每个 `target_location` 的 manuscript 最终落地文案版本
- `selected_action_copy_variants`
  - 只表示用户为每个 `strategy_card_action` 的每个 `target_location` 选中的 manuscript 最终落地文案
- `response_thread_rows`
  - 由 Stage 5 已确认的策略/草案、已选 manuscript 文案和 thread-level 聚合共同生成
- Stage 6 不存在 action-level 的 response-side 三版本选择

## Stage 5 completion 字段语义

- `manuscript_draft_done`
  - 只表示 Stage 5 的 manuscript draft 真源已经写入
- `response_draft_done`
  - 只表示 Stage 5 的 response draft 真源已经写入
- 它们都不表示 Stage 6 的最终文案或最终导出已经完成

## 样例与 fixture 路径命名

playbook 示例中，保存脚本 JSON 输出的正式目录名固定为：

- `gate-and-render-output/`

不再使用：

- `validator-output/`

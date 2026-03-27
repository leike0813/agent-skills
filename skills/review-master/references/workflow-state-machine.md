# workflow_state 状态机指令

正式术语、action id 和脚本称呼以：

- `review-master/references/workflow-glossary.md`

为准。

## 总循环

1. 接收用户指令或恢复进入
2. 先运行 `gate-and-render` 核心脚本
3. 读取 `instruction_payload.resume_packet`
4. 读取 `01-agent-resume.md`
5. 按 `resume_read_order` 恢复当前视图与阶段文档
6. 更新 `review-master.db`
7. 再次运行 `gate-and-render` 核心脚本
8. 读取新的 `instruction_payload`
9. 若无用户显式覆盖，则按 `recommended_next_action` 继续
10. 若存在 `repair_sequence`，先修数据库，再重新验证

## 全局规则

- 运行时唯一真源是 `review-master.db`
- `runtime_language_context` 是文本语言与工作语言的唯一真源
- `workflow_state` 只保存在数据库中
- workspace 尚未初始化时，先确认文本语言与工作语言，再初始化 workspace
- workspace 已初始化后，首次调用和跨 Session 恢复都先走恢复协议，不允许绕开
- `workflow_pending_user_confirmations` 非空时，必须先完成用户确认
- `workflow_global_blockers` 非空时，必须先请求补材、澄清或额外输入
- `active_comment_id` 非空时，不得静默切换到别的 comment

## 阶段规则

### `stage_1`

- 允许：
  - 确认运行环境
  - 核对输入
  - 确认文本语言与工作语言
  - 确认主入口
  - 初始化 workspace
  - 初始化 `runtime_language_context` 与 `runtime-localization/`
  - 读取 bootstrap/continuation resume
  - 写 `recipe_stage1_set_entry_state`
- 推荐：
  - 先确认语言，再初始化 workspace
  - 入口明确且无阻断时进入阶段二
  - 若主入口不唯一或缺输入，则先请求用户确认
- 阻断：
  - 缺少必需输入
  - 文本语言或工作语言尚未确认
  - manuscript 主入口不唯一
  - 运行环境不满足且用户尚未批准安装
- 禁止：
  - 绕过恢复协议
  - 未确认主入口就进入阶段二
  - 直接写策略卡、直接导出

### `stage_2`

- 允许：
  - 更新 `manuscript_summary`
  - 更新 `manuscript_sections`
  - 更新 `manuscript_claims`
  - 更新 `style_profiles`
  - 更新 `style_profile_rules`
  - 更新 `resume_brief` 与 `resume_recent_decisions`
- 推荐：
  - 在结构摘要足以支撑后续 thread/atomic 映射时进入阶段三
  - 在 Stage 2 结束时同步形成 `03-style-profile.md`
- 阻断：
  - `manuscript_sections` 明显缺失
  - `manuscript_claims` 明显缺失
  - 高风险修改区尚未识别
- 禁止：
  - 跳过结构分析直接进入意见原子化
  - 跳过原子化直接进入阶段五

### `stage_3`

- 允许：
  - 写入 `raw_review_threads`
  - 写入 `atomic_comments`
  - 写入 `raw_thread_atomic_links`
  - 写入 `atomic_comment_source_spans`
  - 写入 `review_comment_source_documents`
  - 写入 `raw_thread_source_spans`
  - 写入 `workflow_pending_user_confirmations`
  - 更新 `resume_brief`、`resume_recent_decisions`、`resume_must_not_forget`
- 推荐：
  - 先稳定 raw thread 边界
  - 再做 canonical atomic 建模
  - 再生成 `07-review-comment-coverage.md`
  - 同步检查字符级覆盖率阈值（hard=`30%`，soft=`50%`；主指标包含 `duplicate_filtered`）
  - `primary/supporting` 用红色高亮，`duplicate_filtered` 用橙色高亮展示重复但已去重的原文片段
  - 先请求用户确认 Stage 3 覆盖率，再进入阶段四
- 阻断：
  - raw thread 边界不稳定
  - 是否合并存在高风险歧义
  - 存在未映射 thread 或孤立 atomic item
  - `raw_thread_source_spans` 不能精确回放到 `review_comment_source_documents.original_text`
  - 存在 `thread_id` 没有任何 `span_role='primary'`
  - 全局字符覆盖率低于 hard 阈值（`30%`）
  - `workflow_pending_user_confirmations` 非空
- 禁止：
  - 跳过 raw thread 层直接写 atomic
  - 为减少工作量而激进合并
  - 在用户未确认 Stage 3 覆盖率前进入 Stage 4
  - 跳过阶段四直接逐条执行

### `stage_4`

- 允许：
  - 写入 `atomic_comment_state`
  - 写入 `atomic_comment_target_locations`
  - 写入 `atomic_comment_analysis_links`
  - 写入 `workflow_pending_user_confirmations`
  - 更新 `resume_brief`、`resume_open_loops`、`resume_recent_decisions`
- 推荐：
  - 先形成完整 atomic workboard
  - 再默认进入用户确认门禁
  - 用户确认后才进入 Stage 5
- 阻断：
  - 存在 atomic item 没有 state / location / analysis
  - `priority`、`evidence_gap` 或 `next_action` 未定
  - 待确认事项尚未完成
- 禁止：
  - 在确认未完成时进入阶段五
  - 在 planning 仍为空壳时推进

### `stage_5`

- 允许：
  - 显式设置或切换 `active_comment_id`
  - 写入 `strategy_cards`
  - 写入 `strategy_card_actions`
  - 写入 `strategy_action_target_locations`
  - 写入 `strategy_card_evidence_items`
  - 写入 `strategy_card_pending_confirmations`
  - 写入 `supplement_suggestion_items`
  - 写入 `supplement_suggestion_intake_links`
  - 写入 `supplement_intake_items`
  - 写入 `supplement_landing_links`
  - 写入 `strategy_action_manuscript_execution_items`
  - 写入 `comment_response_drafts`
  - 写入 `comment_blockers`
  - 写入 `comment_completion_status`
  - 仅在真正的阶段级阻断下写入 `workflow_global_blockers`
- 推荐：
  - 先锁定 `active_comment_id`
  - 若存在 `evidence_gap = yes` 的 comment，先形成 `09-supplement-suggestion-plan.md`
  - 同步维护 `10-supplement-intake-plan.md`
  - 缺策略卡先补策略卡
  - 先完成逐条策略确认，再写 Stage 5 draft 真源
  - 若策略语义被修改，必须重开确认并清空当前已写入的 Stage 5 drafts
  - 当前 comment 有局部 blocker 时优先解决它，但用户仍可显式切到别的 comment
  - 只有 manuscript draft、response draft 与一一对应关系都落地后，才把该条 comment 记为完成
  - Stage 5 结束前形成 `11-manuscript-revision-guide.md` 与 `12-manuscript-execution-graph.md`
- 阻断：
  - 当前策略卡仍不足以面向用户确认
  - `workflow_pending_user_confirmations` 非空
  - `workflow_global_blockers` 非空
  - 当前策略未显式确认
  - manuscript draft 或 response draft 尚未形成
  - 一一对应关系尚未稳定
  - 存在补材文件尚未判定接收/拒收，或接收补材尚未完成落地映射
- 禁止：
  - 未确认时执行改稿
  - 证据缺口未关闭时标记完成
  - 静默切换 active comment
  - 只形成方案、不形成数据库中的正式草案真源就标记完成

### `stage_6`

- 允许：
  - 写入 `revision_action_logs`
  - 写入 `revision_action_log_plan_links`
  - 写入 `revision_action_log_thread_links`
  - 写入 `revision_action_log_file_diffs`
  - 写入 `working_copy_file_state`
  - 写入 `response_thread_rows`
  - 写入 `response_thread_action_log_links`
  - 写入 `export_artifacts`
  - 生成可选 `latexdiff_manuscript`
- 推荐：
  - 先读取 `11-manuscript-revision-guide.md` 与 `12-manuscript-execution-graph.md`
  - 参考 `03-style-profile.md`
  - 与用户协作修改 `working_manuscript`
  - 每轮明确修改后，通过 `commit_revision_round.py` 提交
  - 持续刷新 `13-17` 工件
- 阻断：
  - `revision_plan_actions` 未全部结案
  - `working_manuscript` 存在未审计 diff
  - `thread_id` 尚未形成最终 row
  - 某条 response row 没有 revision log 或 `response_only_resolution`
- 禁止：
  - 修改 `working_manuscript` 后绕过审计提交
  - 用 `comment_id` 顺序直接替代 `thread_id` 顺序输出最终 Response Letter
  - 修改 `source_snapshot`

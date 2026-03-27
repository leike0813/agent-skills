# SQL Write Recipes

这份文档是 `review-master` 运行时 SQL 写入动作的单一真源。

正式术语、脚本称呼、action id 和最终导出产物命名以：

- `review-master/references/workflow-glossary.md`

为准。

共同规则：

- 每次写库前都要先执行 `PRAGMA foreign_keys = ON`
- Stage 1 初始化后必须确保 `runtime_language_context` 已写入并与用户确认结果一致
- Stage 3-5 的分析层与草案层字段默认使用工作语言；Stage 6 的最终 copy 与导出层字段默认使用文本语言
- 当一个动作需要改多张表时，按对应 recipe 的推荐顺序写入
- 对“替换型”表更新，先删除旧记录范围，再插入新记录
- 每次写入后都必须运行 `gate-and-render` 核心脚本，让它校验状态机门禁并重渲染 Markdown 视图
- 每个阶段推进型 recipe 都必须同步维护 `resume_brief`
- 中后期阶段还应按需维护 `resume_open_loops`、`resume_recent_decisions`、`resume_must_not_forget`

## `recipe_stage1_set_entry_state`

- 适用阶段：`stage_1`
- 何时使用：初始化 workspace 后，补入口解析结果与初始阶段状态
- 必须更新的表：
  - `runtime_language_context`
  - `workflow_state`
  - `resume_brief`
  - 视情况更新 `workflow_pending_user_confirmations`
  - 视情况更新 `workflow_global_blockers`
  - 视情况更新 `resume_open_loops`
  - 视情况更新 `resume_recent_decisions`
  - 视情况更新 `resume_must_not_forget`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. 根据输入结果更新 `workflow_state.current_stage = 'stage_1'`
  3. `UPDATE runtime_language_context ...`
  4. 设置 `workflow_state.stage_gate`
     - 入口已明确且可继续时为 `ready`
     - 主入口未定、缺输入或环境待确认时为 `blocked`
  5. 设置 `workflow_state.next_action`
     - 正常推进时为 `enter_stage_2`
     - 待确认时改为对应请求动作
  6. `UPDATE resume_brief ...`
  7. 视情况清空并重建：
     - `workflow_pending_user_confirmations`
     - `workflow_global_blockers`
     - `resume_open_loops`
     - `resume_recent_decisions`
     - `resume_must_not_forget`
- 进入这条 recipe 之前应先完成：
  - 环境确认
  - 统一恢复入口
  - 必需输入核对
  - manuscript 主入口识别
- 写后门槛：
  - `gate-and-render` 返回允许继续
  - `instruction_payload.resume_packet` 与 `01-agent-resume.md` 已重新读取

## `recipe_stage2_upsert_manuscript_summary`

- 适用阶段：`stage_2`
- 何时使用：完成原稿结构分析后
- 必须更新的表：
  - `manuscript_summary`
  - `manuscript_sections`
  - `manuscript_claims`
  - `workflow_state`
  - `resume_brief`
  - 视情况更新 `resume_recent_decisions`
  - 视情况更新 `resume_open_loops`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `UPDATE manuscript_summary SET main_entry = ..., project_shape = ..., high_risk_areas = ... WHERE id = 1`
  3. `DELETE FROM manuscript_sections`
  4. 批量插入 `manuscript_sections`
  5. `DELETE FROM manuscript_claims`
  6. 批量插入 `manuscript_claims`
  7. `UPDATE resume_brief ...`
  8. 插入至少一条 `resume_recent_decisions`
  9. 若仍有结构性疑问，更新 `resume_open_loops`
  10. `UPDATE workflow_state SET current_stage = 'stage_2', stage_gate = 'ready', next_action = 'enter_stage_3' WHERE id = 1`
- 进入这条 recipe 之前应先确认：
  - Stage 1 已完成
  - 主入口已明确
  - manuscript 结构分析已经形成稳定的 section/claim 草案
- 写后门槛：
  - `02-manuscript-structure-summary.md` 已成功重渲染
  - 结构摘要足以支撑 Stage 3 thread 抽取与 atomic 建模

## `recipe_stage3_replace_threaded_atomic_model`

- 适用阶段：`stage_3`
- 何时使用：完成原始意见块抽取、去重、归并和 canonical atomic 建模后
- 必须更新的表：
  - `raw_review_threads`
  - `atomic_comments`
  - `raw_thread_atomic_links`
  - `atomic_comment_source_spans`
  - `review_comment_source_documents`
  - `raw_thread_source_spans`
  - `workflow_pending_user_confirmations`
  - `workflow_state`
  - `resume_brief`
  - `resume_recent_decisions`
  - `resume_must_not_forget`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `DELETE FROM raw_thread_source_spans`
  3. `DELETE FROM review_comment_source_documents`
  4. `DELETE FROM atomic_comment_source_spans`
  5. `DELETE FROM raw_thread_atomic_links`
  6. `DELETE FROM atomic_comments`
  7. `DELETE FROM raw_review_threads`
  8. 批量插入 `raw_review_threads`
  9. 批量插入 `atomic_comments`
  10. 批量插入 `raw_thread_atomic_links`
  11. 批量插入 `atomic_comment_source_spans`
  12. 批量插入 `review_comment_source_documents`
  13. 批量插入 `raw_thread_source_spans`（必须包含 `span_role`，取值仅 `primary` / `supporting` / `duplicate_filtered`）
  14. 重建 `workflow_pending_user_confirmations`
  15. `UPDATE resume_brief ...`
  16. 插入至少一条 `resume_recent_decisions`
  17. 视情况插入 `resume_must_not_forget`
  18. `UPDATE workflow_state SET current_stage = 'stage_3', stage_gate = 'blocked', active_comment_id = NULL, next_action = 'request_stage3_coverage_confirmation' WHERE id = 1`
- 进入这条 recipe 之前应先确认：
  - Stage 2 已完成
  - 结构摘要足以支撑 reviewer thread 与 atomic 建模
  - raw thread 边界已经稳定
  - atomic 合并与拆分判断已完成
- 写后门槛：
  - 每个 `thread_id` 至少映射到一个 `comment_id`
  - 每个 `comment_id` 至少被一个 `thread_id` 引用
  - `atomic_comment_source_spans` 足以解释跨 reviewer 合并依据
  - 每个 `thread_id` 至少有一条 `raw_thread_source_spans`
  - 每个 `thread_id` 至少有一条 `span_role='primary'`
  - 每条 `raw_thread_source_spans` 都满足 offset 与 span_text 对原文的精确匹配
  - 若存在语义重复但被摘要层去重的原文位置，应写入 `span_role='duplicate_filtered'` 以保证覆盖可见性
  - Stage 3 字符级覆盖率主指标（含 `duplicate_filtered`）不得低于 hard `30%`；若介于 `30%-50%`，属于软提示，需与用户复核
  - `07-review-comment-coverage.md` 已可供用户审阅
  - `gate-and-render` 返回 Stage 3 coverage confirmation 请求

## `recipe_stage3_clear_coverage_confirmation`

- 适用阶段：`stage_3`
- 何时使用：用户确认 `07-review-comment-coverage.md` 后，清除 Stage 3 覆盖率确认门禁
- 必须更新的表：
  - `workflow_pending_user_confirmations`
  - `workflow_state`
  - `resume_brief`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `DELETE FROM workflow_pending_user_confirmations`
  3. `UPDATE resume_brief ...`
  4. `UPDATE workflow_state SET current_stage = 'stage_3', stage_gate = 'ready', active_comment_id = NULL, next_action = 'enter_stage_4' WHERE id = 1`
- 进入这条 recipe 之前应先确认：
  - `07-review-comment-coverage.md` 已面向用户展示
  - 用户已确认 Stage 3 的覆盖率与映射结果
- 写后门槛：
  - `gate-and-render` 返回允许进入 Stage 4

## `recipe_stage4_upsert_atomic_workboard`

- 适用阶段：`stage_4`
- 何时使用：建立 atomic item 级 workboard 时
- 必须更新的表：
  - `atomic_comment_state`
  - `atomic_comment_target_locations`
  - `atomic_comment_analysis_links`
  - `workflow_state`
  - `resume_brief`
  - 视情况更新 `resume_open_loops`
  - 视情况更新 `resume_recent_decisions`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `DELETE FROM atomic_comment_analysis_links WHERE comment_id = ?` 或全量替换
  3. `DELETE FROM atomic_comment_target_locations WHERE comment_id = ?` 或全量替换
  4. `INSERT ... ON CONFLICT(comment_id) DO UPDATE` 到 `atomic_comment_state`
  5. 批量插入 `atomic_comment_target_locations`
  6. 批量插入 `atomic_comment_analysis_links`
  7. `UPDATE resume_brief ...`
  8. 视情况更新 `resume_open_loops`
  9. 视情况插入 `resume_recent_decisions`
  10. `UPDATE workflow_state SET current_stage = 'stage_4', stage_gate = 'ready', active_comment_id = NULL, next_action = 'request_stage4_confirmation' WHERE id = 1`
- 进入这条 recipe 之前应先确认：
  - Stage 3 已完成
  - 每条 atomic item 都已具备 planning 所需的最小语义理解
  - 可以接受有限的 provisional location 或分析项
- 写后门槛：
  - 每个 `comment_id` 都有一条 `atomic_comment_state`
  - 每个 `comment_id` 至少有一条位置记录和一条分析记录
  - `priority`、`evidence_gap`、`next_action` 均已明确
  - workboard 已足以进入默认确认门禁

## `recipe_stage4_set_pending_confirmations`

- 适用阶段：`stage_4`
- 何时使用：需要用户确认 thread-to-atomic 拆分、workboard 顺序或总体策略时
- 必须更新的表：
  - `workflow_pending_user_confirmations`
  - `workflow_state`
  - `resume_brief`
  - `resume_open_loops`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `DELETE FROM workflow_pending_user_confirmations`
  3. 按顺序插入新的确认事项
  4. `UPDATE resume_brief ...`
  5. 更新 `resume_open_loops`
  6. `UPDATE workflow_state SET current_stage = 'stage_4', stage_gate = 'blocked', next_action = 'request_stage4_confirmation' WHERE id = 1`
- 进入这条 recipe 之前应先确认：
  - Stage 4 主 workboard 已建立
  - 用户需要审阅 workboard、映射和执行顺序
- 写后门槛：
  - 待确认事项已面向用户展示
  - 在确认完成前不得进入 Stage 5

## `recipe_stage5_set_active_comment`

- 适用阶段：`stage_5`
- 何时使用：开始或切换当前处理中的 canonical atomic item
- 必须更新的表：
  - `workflow_state`
  - `resume_brief`
  - 视情况更新 `resume_open_loops`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `UPDATE workflow_state SET current_stage = 'stage_5', active_comment_id = ?, next_action = 'author_strategy_card' WHERE id = 1`
  3. `UPDATE resume_brief SET current_focus = ?, why_paused = ?, next_operator_action = ?`
  4. 若切换原因需要保留，更新 `resume_open_loops`
- 进入这条 recipe 之前应先确认：
  - Stage 4 默认确认门禁已通过
  - 当前条目具备足以支撑 Stage 5 的 workboard 信息
  - 切换 active item 不是静默发生
- 写后门槛：
  - `gate-and-render` 必须反映新的 `active_comment_id`
  - 若当前 item 仍需确认或存在 blocker，不得假设可直接执行
  - 切换不会清空旧 comment 已写入的策略、草案或 blocker 数据

## `recipe_stage5_upsert_strategy_card`

- 适用阶段：`stage_5`
- 何时使用：为当前 active atomic item 写入或修订策略立场
- 必须更新的表：
  - `strategy_cards`
  - `resume_brief`
  - 视情况更新 `resume_recent_decisions`
  - 视情况更新 `resume_must_not_forget`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `INSERT ... ON CONFLICT(comment_id) DO UPDATE` 到 `strategy_cards`
  3. `UPDATE resume_brief SET current_focus = ?, next_operator_action = ?`
  4. 若策略立场已稳定，插入 `resume_recent_decisions`
  5. 若存在高风险注意点，插入 `resume_must_not_forget`
- 进入这条 recipe 之前应先确认：
  - `workflow_state.active_comment_id` 已锁定
  - 当前 item 的核心 planning 已从 Stage 4 带入
- 写后门槛：
  - 当前 item 的 `proposed_stance` 与 `stance_rationale` 已可面向用户确认
  - 若策略仍然模糊，不得推进到草案执行

## `recipe_stage5_replace_strategy_actions`

- 适用阶段：`stage_5`
- 何时使用：替换某条策略卡的具体稿件修改动作时
- 必须更新的表：
  - `strategy_card_actions`
  - 视情况更新 `resume_recent_decisions`
  - 视情况更新 `resume_must_not_forget`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `DELETE FROM strategy_card_actions WHERE comment_id = ?`
  3. 批量插入新的 `strategy_card_actions`
  4. 视情况记录 `resume_recent_decisions` 和 `resume_must_not_forget`
- 进入这条 recipe 之前应先确认：
  - 策略立场已足以支撑动作设计
  - 每条动作都确实服务当前 atomic item
- 写后门槛：
  - 至少有一条动作
  - 动作足以进入逐条确认或草案形成

## `recipe_stage5_replace_action_target_locations`

- 适用阶段：`stage_5`
- 何时使用：替换某条策略动作对应的多个修改位置时
- 必须更新的表：
  - `strategy_action_target_locations`
  - 视情况更新 `resume_recent_decisions`
  - 视情况更新 `resume_must_not_forget`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `DELETE FROM strategy_action_target_locations WHERE comment_id = ?`
  3. 批量插入新的动作-位置关系
  4. 视情况记录位置仍不稳定的注意事项
- 进入这条 recipe 之前应先确认：
  - `strategy_card_actions` 已存在
  - 动作需要一个以上位置或需要比 workboard 更细的定位
- 写后门槛：
  - 多位置动作的定位关系已显式可追溯
  - 多位置动作的定位关系必须显式落库

## `recipe_stage5_replace_strategy_evidence`

- 适用阶段：`stage_5`
- 何时使用：补充或修订证据需求与可用证据时
- 必须更新的表：
  - `strategy_card_evidence_items`
  - `resume_brief`
  - 视情况更新 `resume_open_loops`
  - 视情况更新 `resume_must_not_forget`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `DELETE FROM strategy_card_evidence_items WHERE comment_id = ?`
  3. 批量插入新的证据条目
  4. `UPDATE resume_brief ...`
  5. 若存在待补材料，更新 `resume_open_loops`
  6. 若存在高风险证据约束，更新 `resume_must_not_forget`
- 进入这条 recipe 之前应先确认：
  - 当前 item 的立场和动作已经基本明确
  - 需要判断是否存在 evidence gap
- 写后门槛：
  - 当前 item 的证据结构已可判断为“足够”或“存在缺口”
  - 若缺口成立，应继续进入 blocker 处理，而不是直接标记完成

## `recipe_stage5_replace_supplement_intake_and_landing`

- 适用阶段：`stage_5`
- 何时使用：用户提交补材后，需要形成文件级接收判定与落地映射时
- 必须更新的表：
  - `supplement_intake_items`
  - `supplement_landing_links`
  - 视情况更新 `workflow_global_blockers`
  - 视情况更新 `resume_open_loops`
  - `resume_brief`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `DELETE FROM supplement_landing_links WHERE round_id = ?`
  3. `DELETE FROM supplement_intake_items WHERE round_id = ?`
  4. 批量插入新的 `supplement_intake_items`
  5. 批量插入新的 `supplement_landing_links`（仅 accepted 补材）
  6. `UPDATE resume_brief ...`
  7. 根据是否仍有缺口刷新 `workflow_global_blockers` 与 `resume_open_loops`
- 进入这条 recipe 之前应先确认：
  - 当前补材轮次对应的文件清单已明确
  - 每个文件都能给出接收/拒收结论
  - accepted 文件已能映射到 action/location
- 写后门槛：
  - 本轮每个文件都有接收判定与理由
  - 所有 accepted 文件都已有落地映射
  - 若仍缺关键信息，应继续保持 blocker，而不是误置为 ready

## `recipe_stage5_replace_strategy_pending_confirmations`

- 适用阶段：`stage_5`
- 何时使用：某条策略卡需要用户逐条确认时
- 必须更新的表：
  - `strategy_card_pending_confirmations`
  - 视情况更新 `workflow_pending_user_confirmations`
  - 视情况更新 `resume_open_loops`
  - `resume_brief`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `DELETE FROM strategy_card_pending_confirmations WHERE comment_id = ?`
  3. 批量插入新的策略卡待确认项
  4. 视情况刷新 `workflow_pending_user_confirmations`
  5. 更新 `resume_brief` 与 `resume_open_loops`
- 进入这条 recipe 之前应先确认：
  - 当前 item 已形成可被用户评审的策略卡
  - 正准备进入 manuscript draft 或 response draft
- 写后门槛：
  - 用户待确认事项已显式展示
  - 在确认完成前，不得进入真正的草案执行

## `recipe_stage5_confirm_strategy`

- 适用阶段：`stage_5`
- 何时使用：用户显式确认当前策略卡后
- 必须更新的表：
  - `strategy_card_pending_confirmations`
  - `workflow_pending_user_confirmations`
  - `comment_completion_status`
  - `workflow_state`
  - `resume_brief`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `DELETE FROM strategy_card_pending_confirmations WHERE comment_id = ?`
  3. `DELETE FROM workflow_pending_user_confirmations`
  4. `UPDATE comment_completion_status SET user_strategy_confirmed = 'yes' WHERE comment_id = ?`
  5. `UPDATE workflow_state SET current_stage = 'stage_5', stage_gate = 'ready', active_comment_id = ?, next_action = 'author_comment_drafts' WHERE id = 1`
  6. `UPDATE resume_brief ...`
- 写后门槛：
  - 当前策略已被显式确认
  - 下一步才允许进入 Stage 5 drafts

## `recipe_stage5_set_blockers`

- 适用阶段：`stage_5`
- 何时使用：出现真正阻断整个 Stage 5 的全局问题时
- 必须更新的表：
  - `workflow_global_blockers`
  - `workflow_state`
  - `resume_brief`
  - `resume_open_loops`
  - 视情况更新 `resume_must_not_forget`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `DELETE FROM workflow_global_blockers`
  3. 插入新的 blocker 列表
  4. `UPDATE workflow_state SET current_stage = 'stage_5', stage_gate = 'blocked', active_comment_id = ?, next_action = 'resolve_blockers' WHERE id = 1`
  5. `UPDATE resume_brief ...`
  6. 更新 `resume_open_loops`
  7. 视情况更新 `resume_must_not_forget`
- 进入这条 recipe 之前应先确认：
  - 该 blocker 确实属于阶段级阻断，而不是某条 comment 的局部 blocker
  - blocker 不是暂时的措辞问题，而是真正阻碍整个 Stage 5 的问题
- 写后门槛：
  - blocker 已对用户可见
  - 在 blocker 解除前，不得继续执行 Stage 5 的任何 comment

## `recipe_stage5_replace_comment_blockers`

- 适用阶段：`stage_5`
- 何时使用：当前 active comment 需要局部 blocker，但不应阻断整个 Stage 5 时
- 必须更新的表：
  - `comment_blockers`
  - `resume_brief`
  - `resume_open_loops`
  - 视情况更新 `resume_must_not_forget`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `DELETE FROM comment_blockers WHERE comment_id = ?`
  3. 为该 comment 批量插入新的 blocker 列表
  4. `UPDATE resume_brief ...`
  5. 更新 `resume_open_loops`
  6. 视情况更新 `resume_must_not_forget`
- 进入这条 recipe 之前应先确认：
  - blocker 只阻断当前 comment 的完成
  - 其他 comment 在无全局 blocker 时仍可继续处理
- 写后门槛：
  - 当前 comment 不得被标记完成
  - `gate-and-render` 仍允许显式 `set_active_comment`

## `recipe_stage5_replace_supplement_suggestions`

- 适用阶段：`stage_5`
- 何时使用：进入 Stage 5 后首次生成补材建议 backlog，或策略修改后刷新某条 comment 的补材建议时
- 必须更新的表：
  - `supplement_suggestion_items`
  - `supplement_suggestion_intake_links`
  - `resume_brief`
  - 视情况更新 `resume_open_loops`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. 删除并重写当前 comment 需要更新的 suggestion rows
  3. 仅在需要重绑 intake 时更新 `supplement_suggestion_intake_links`
  4. `UPDATE resume_brief ...`
- 写后门槛：
  - 每个 `evidence_gap = yes` 的 comment 至少有一条 suggestion row
  - `09-supplement-suggestion-plan.md` 可被用户审阅

## `recipe_stage5_replace_manuscript_drafts`

- 适用阶段：`stage_5`
- 何时使用：需要为当前 comment 的 action/location 写入或替换 manuscript draft 真源时
- 必须更新的表：
  - `strategy_action_manuscript_execution_items`
  - `resume_brief`
  - 视情况更新 `resume_recent_decisions`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `DELETE FROM strategy_action_manuscript_execution_items WHERE comment_id = ?`
  3. 按 `(comment_id, action_order, location_order)` 批量插入新的 draft 行
  4. `UPDATE resume_brief ...`
  5. 视情况更新 `resume_recent_decisions`
- 进入这条 recipe 之前应先确认：
  - 当前 comment 的 `strategy_card_actions` 与 `strategy_action_target_locations` 已稳定
  - 这些文本只是 Stage 5 草案，不是 Stage 6 最终落稿版本
- 写后门槛：
  - 当前 comment 每个需要的 action/location 都已有 manuscript draft 行
  - 之后才允许把 `manuscript_execution_items_done` 置为 `yes`

## `recipe_stage5_replace_execution_drafts`

- 适用阶段：`stage_5`
- 何时使用：当前策略已经确认，需要一次性写入 manuscript draft 与 response draft 时
- 必须更新的表：
  - `strategy_action_manuscript_execution_items`
  - `comment_response_drafts`
  - `comment_completion_status`
  - `resume_brief`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `DELETE FROM strategy_action_manuscript_execution_items WHERE comment_id = ?`
  3. 重写当前 comment 的 manuscript draft rows
  4. `INSERT ... ON CONFLICT(comment_id) DO UPDATE` 到 `comment_response_drafts`
  5. `UPDATE comment_completion_status SET manuscript_execution_items_done = 'yes', response_draft_done = 'yes' WHERE comment_id = ?`
  6. `UPDATE resume_brief ...`
- 进入这条 recipe 之前应先确认：
  - `user_strategy_confirmed = yes`
  - 当前策略卡与补材建议已稳定到足以形成草案
- 写后门槛：
  - 当前条目已拥有正式的 Stage 5 drafts 真源

## `recipe_stage5_upsert_response_draft`

- 适用阶段：`stage_5`
- 何时使用：需要为当前 comment 写入或更新 response draft 真源时
- 必须更新的表：
  - `comment_response_drafts`
  - `resume_brief`
  - 视情况更新 `resume_recent_decisions`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `INSERT ... ON CONFLICT(comment_id) DO UPDATE` 到 `comment_response_drafts`
  3. `UPDATE resume_brief ...`
  4. 视情况更新 `resume_recent_decisions`
- 进入这条 recipe 之前应先确认：
  - 当前 comment 的策略、证据和 manuscript draft 方向已经足以支撑回复草案
- 写后门槛：
  - 当前 comment 已有 response draft 真源
  - 之后才允许把 `response_draft_done` 置为 `yes`

## `recipe_stage5_upsert_completion_status`

- 适用阶段：`stage_5`
- 何时使用：某条 atomic item 的草案、证据和一一对应检查推进后
- 必须更新的表：
  - `comment_completion_status`
  - `workflow_state`
  - `resume_brief`
  - `resume_recent_decisions`
  - 视情况更新 `resume_open_loops`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `INSERT ... ON CONFLICT(comment_id) DO UPDATE` 到 `comment_completion_status`
  3. `UPDATE resume_brief ...`
  4. 插入 `resume_recent_decisions`
  5. 视情况清理 `resume_open_loops`
  6. 视情况更新 `workflow_state.next_action`
- 进入这条 recipe 之前应先确认：
  - 策略卡完成
  - 证据判断完成
  - manuscript draft 完成
  - response draft 完成
  - 一一对应检查通过
- 写后门槛：
  - 当前条目才可视为可完成态
  - 若上述任一条件缺失，不得通过该 recipe 把条目标记完成

## `recipe_stage2_upsert_style_profiles`

- 适用阶段：`stage_2`
- 何时使用：完成原稿结构分析后，需要同步建立 manuscript 与 response_letter 的全局风格基线时
- 必须更新的表：
  - `style_profiles`
  - `style_profile_rules`
  - `resume_brief`
  - `resume_recent_decisions`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `INSERT ... ON CONFLICT(profile_target) DO UPDATE` 到 `style_profiles`
  3. `DELETE FROM style_profile_rules WHERE profile_target IN ('manuscript', 'response_letter')`
  4. 批量插入新的 `style_profile_rules`
  5. `UPDATE resume_brief ...`
  6. 插入 `resume_recent_decisions`
- 写后门槛：
  - `03-style-profile.md` 已可供 Stage 6 读取

## `recipe_stage5_build_revision_backlog`

- 适用阶段：`stage_5`
- 何时使用：全部策略卡达到可执行状态，需要为 Stage 6 建立 revision backlog 时
- 必须更新的表：
  - `revision_plan_actions`
  - `revision_plan_dependencies`
  - `resume_brief`
  - `resume_recent_decisions`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. 删除并重写当前稳定范围内的 `revision_plan_dependencies`
  3. 删除并重写当前稳定范围内的 `revision_plan_actions`
  4. `UPDATE resume_brief ...`
  5. 插入 `resume_recent_decisions`
- 写后门槛：
  - 每个已确认可执行策略至少派生一条 plan action
  - `11-manuscript-revision-guide.md` 与 `12-manuscript-execution-graph.md` 可供 Stage 6 读取

## `recipe_stage6_commit_revision_round`

- 适用阶段：`stage_6`
- 何时使用：一轮明确的 `working_manuscript` 修改已经发生，需要把增量修改写入 revision audit 真源时
- 必须更新的表：
  - `revision_action_logs`
  - `revision_action_log_plan_links`
  - `revision_action_log_thread_links`
  - `revision_action_log_file_diffs`
  - `working_copy_file_state`
  - `resume_brief`
  - 视情况更新 `resume_recent_decisions`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. 写入一条 `revision_action_logs`
  3. 批量插入对应的 plan/thread links
  4. 批量插入文件级 diff 摘录
  5. 刷新 `working_copy_file_state`
  6. `UPDATE resume_brief ...`
  7. 视情况更新 `resume_recent_decisions`
- 写后门槛：
  - 本轮修改已可追溯到明确的 `log_id`
  - 本轮涉及的文件状态已刷新到最新审计状态

## `recipe_stage6_refresh_response_rows`

- 适用阶段：`stage_6`
- 何时使用：revision audit 更新后，需要刷新 thread-level response rows 与覆盖关系时
- 必须更新的表：
  - `response_thread_action_log_links`
  - `response_thread_rows`
  - `resume_brief`
  - 视情况更新 `resume_recent_decisions`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. 替换当前稳定范围内的 `response_thread_action_log_links`
  3. 替换对应 `response_thread_rows`
  4. `UPDATE resume_brief ...`
  5. 视情况更新 `resume_recent_decisions`
- 写后门槛：
  - 每条已闭环 thread 都能在 response rows 中回映
  - `14-response-coverage-matrix.md` 可正确展示覆盖状态

## `recipe_stage6_finalize_outputs`

- 适用阶段：`stage_6`
- 何时使用：所有 revision plan action 已结案、response 覆盖已闭环，需要确认最终输出时
- 必须更新的表：
  - `export_artifacts`
  - `workflow_state`
  - `resume_brief`
  - `resume_recent_decisions`
  - 视情况清理 `resume_open_loops`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. 更新 `export_artifacts` 中 `working_manuscript`、`response_markdown`、`response_latex`
  3. 若环境可用，补充 `latexdiff_manuscript`
  4. `UPDATE workflow_state SET current_stage = 'stage_6', stage_gate = 'ready', active_comment_id = NULL, next_action = 'stage_6_completed' WHERE id = 1`
  5. `UPDATE resume_brief ...`
  6. 插入最终 `resume_recent_decisions`
  7. 视情况清理 `resume_open_loops`
- 写后门槛：
  - `working_manuscript`、`response_markdown`、`response_latex` 已稳定
  - 若存在 `latexdiff_manuscript`，它已作为辅助产物可读取

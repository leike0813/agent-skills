# SQL Write Recipes

这份文档是 `review-master` 运行时 SQL 写入动作的单一真源。

正式术语、脚本称呼、action id 和最终导出产物命名以：

- `review-master/references/workflow-glossary.md`

为准。

共同规则：

- 每次写库前都要先执行 `PRAGMA foreign_keys = ON`
- 当一个动作需要改多张表时，按对应 recipe 的推荐顺序写入
- 对“替换型”表更新，先删除旧记录范围，再插入新记录
- 每次写入后都必须运行 `gate-and-render` 核心脚本，让它校验状态机门禁并重渲染 Markdown 视图
- 每个阶段推进型 recipe 都必须同步维护 `resume_brief`
- 中后期阶段还应按需维护 `resume_open_loops`、`resume_recent_decisions`、`resume_must_not_forget`

## `recipe_stage1_set_entry_state`

- 适用阶段：`stage_1`
- 何时使用：初始化 workspace 后，补入口解析结果与初始阶段状态
- 必须更新的表：
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
  3. 设置 `workflow_state.stage_gate`
     - 入口已明确且可继续时为 `ready`
     - 主入口未定、缺输入或环境待确认时为 `blocked`
  4. 设置 `workflow_state.next_action`
     - 正常推进时为 `enter_stage_2`
     - 待确认时改为对应请求动作
  5. `UPDATE resume_brief ...`
  6. 视情况清空并重建：
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
  - `instruction_payload.resume_packet` 与 `agent-resume.md` 已重新读取

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
  - `manuscript-structure-summary.md` 已成功重渲染
  - 结构摘要足以支撑 Stage 3 thread 抽取与 atomic 建模

## `recipe_stage3_replace_threaded_atomic_model`

- 适用阶段：`stage_3`
- 何时使用：完成原始意见块抽取、去重、归并和 canonical atomic 建模后
- 必须更新的表：
  - `raw_review_threads`
  - `atomic_comments`
  - `raw_thread_atomic_links`
  - `atomic_comment_source_spans`
  - `workflow_state`
  - `resume_brief`
  - `resume_recent_decisions`
  - `resume_must_not_forget`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. `DELETE FROM atomic_comment_source_spans`
  3. `DELETE FROM raw_thread_atomic_links`
  4. `DELETE FROM atomic_comments`
  5. `DELETE FROM raw_review_threads`
  6. 批量插入 `raw_review_threads`
  7. 批量插入 `atomic_comments`
  8. 批量插入 `raw_thread_atomic_links`
  9. 批量插入 `atomic_comment_source_spans`
  10. `UPDATE resume_brief ...`
  11. 插入至少一条 `resume_recent_decisions`
  12. 视情况插入 `resume_must_not_forget`
  13. `UPDATE workflow_state SET current_stage = 'stage_3', stage_gate = 'ready', active_comment_id = NULL, next_action = 'enter_stage_4' WHERE id = 1`
- 进入这条 recipe 之前应先确认：
  - Stage 2 已完成
  - 结构摘要足以支撑 reviewer thread 与 atomic 建模
  - raw thread 边界已经稳定
  - atomic 合并与拆分判断已完成
- 写后门槛：
  - 每个 `thread_id` 至少映射到一个 `comment_id`
  - 每个 `comment_id` 至少被一个 `thread_id` 引用
  - `atomic_comment_source_spans` 足以解释跨 reviewer 合并依据
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
  - 不再依赖口头说明或隐含位置推断

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
  - 正准备进入稿件修改草案或 response 草案
- 写后门槛：
  - 用户待确认事项已显式展示
  - 在确认完成前，不得进入真正的草案执行

## `recipe_stage5_set_blockers`

- 适用阶段：`stage_5`
- 何时使用：出现证据缺口、用户补材缺失或其他全局阻塞时
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
  - 当前 item 的 blocker 已稳定识别
  - blocker 不是暂时的措辞问题，而是真正阻碍草案执行的问题
- 写后门槛：
  - blocker 已对用户可见
  - 在 blocker 解除前，不得把当前条目标记完成

## `recipe_stage5_upsert_completion_status`

- 适用阶段：`stage_5`
- 何时使用：某条 atomic item 的修改、回复段落、证据和一一对应检查推进后
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
  - 稿件修改草案完成
  - response 段落草案完成
  - 一一对应检查通过
- 写后门槛：
  - 当前条目才可视为可完成态
  - 若上述任一条件缺失，不得通过该 recipe 把条目标记完成

## `recipe_stage6_upsert_style_profiles`

- 适用阶段：`stage_6`
- 何时使用：开始最终成文前，需要先提炼 manuscript 与 response_letter 的全局风格画像时
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
  5. 更新 `resume_brief` 与 `resume_recent_decisions`

## `recipe_stage6_replace_action_copy_variants`

- 适用阶段：`stage_6`
- 何时使用：为每个 `strategy_card_actions` 的每个 `target_location` 生成 3 个 manuscript-side 最终落稿文本版本时
- 必须更新的表：
  - `action_copy_variants`
  - `resume_recent_decisions`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. 按 `(comment_id, action_order, location_order)` 删除旧版本
  3. 为每个 target location 批量插入 `v1` / `v2` / `v3` 三个最终落稿文本版本
  4. 更新 `resume_recent_decisions`

## `recipe_stage6_select_action_copy_variants`

- 适用阶段：`stage_6`
- 何时使用：用户已确认每个 action 的每个 `target_location` 的最终 manuscript 文案版本，需要落库时
- 必须更新的表：
  - `selected_action_copy_variants`
  - `workflow_pending_user_confirmations`
  - `resume_recent_decisions`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. 以 `(comment_id, action_order, location_order)` 为范围删除旧选择
  3. 插入新的 `selected_action_copy_variants`
  4. 清理已完成的版本选择确认项
  5. 更新 `resume_recent_decisions`

## `recipe_stage6_upsert_response_thread_rows`

- 适用阶段：`stage_6`
- 何时使用：需要把已选 manuscript 文案和 Stage 5 草案回映为 thread-level 4 列最终表格行时
- 必须更新的表：
  - `response_thread_resolution_links`
  - `response_thread_rows`
  - `resume_recent_decisions`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. 替换 `response_thread_resolution_links`
  3. 结合 Stage 5 已确认的策略与草案替换 `response_thread_rows`
  4. 更新 `resume_recent_decisions`

## `recipe_stage6_replace_export_patches`

- 适用阶段：`stage_6`
- 何时使用：需要为完整 manuscript 导出准备可执行 patch 真源时
- 必须更新的表：
  - `export_patch_sets`
  - `export_patches`
  - `resume_recent_decisions`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. 按 `artifact_kind` 替换 `export_patch_sets`
  3. 按 `patch_set_id` 删除旧的 `export_patches`
  4. 批量插入新的 `export_patches`
  5. 更新 `resume_recent_decisions`
- 进入这条 recipe 之前应先确认：
  - `response_thread_rows` 已稳定
  - 每个修改位置都已选定最终落稿文本
  - 每条 patch 都有显式 `anchor_text`
- 写后门槛：
  - `marked_manuscript` 与 `clean_manuscript` 各自都有 patch set
  - 每个 patch set 至少有一条 patch

## `recipe_stage6_export_marked_manuscript`

- 适用阶段：`stage_6`
- 何时使用：thread-level rows 与 export patches 已稳定，需要先导出带 `changes` 标注的完整稿件供用户复核时
- 必须更新的表：
  - `export_artifacts`
  - `workflow_pending_user_confirmations`
  - `resume_brief`
  - `resume_open_loops`
  - `resume_recent_decisions`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. 调用 `review-master/scripts/export_manuscript_variants.py --artifact-root <ARTIFACT_ROOT> --patch-set-id <MARKED_PATCH_SET_ID>`
  3. 更新 `export_artifacts` 中 `marked_manuscript`
  4. 写入最终复核相关的 `workflow_pending_user_confirmations`
  5. 更新 `resume_brief` 与 `resume_open_loops`
  6. 更新 `resume_recent_decisions`
- 写后门槛：
  - `marked_manuscript` 已导出
  - 导出结果是完整稿件，而非局部摘录
  - 下一步必须先让用户复核

## `recipe_stage6_export_clean_manuscript`

- 适用阶段：`stage_6`
- 何时使用：marked manuscript 已经复核，最终确认已通过，需要导出 clean manuscript 与双格式 response letter 时
- 必须更新的表：
  - `export_artifacts`
  - `workflow_pending_user_confirmations`
  - `workflow_global_blockers`
  - `workflow_state`
  - `resume_brief`
  - `resume_open_loops`
  - `resume_recent_decisions`
- 推荐 SQL 顺序：
  1. `PRAGMA foreign_keys = ON`
  2. 调用 `review-master/scripts/export_manuscript_variants.py --artifact-root <ARTIFACT_ROOT> --patch-set-id <CLEAN_PATCH_SET_ID>`
  3. 更新 `export_artifacts` 中 `clean_manuscript`、`response_markdown`、`response_latex`
  4. `DELETE FROM workflow_pending_user_confirmations`
  5. `DELETE FROM workflow_global_blockers`
  6. `UPDATE workflow_state SET current_stage = 'stage_6', stage_gate = 'ready', active_comment_id = NULL, next_action = 'stage_6_completed' WHERE id = 1`
  7. 更新 `resume_brief`、清理 `resume_open_loops`
  8. 更新 `resume_recent_decisions`
- 写后门槛：
  - `clean_manuscript` 与用户确认后的 `marked_manuscript` 内容一致，只去掉标记
  - `response_latex` 是带 front matter 的完整可编译文件

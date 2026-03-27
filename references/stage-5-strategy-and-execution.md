# 阶段五：逐条策略与执行

本阶段使用的正式术语、脚本称呼和 action id 以：

- `review-master/references/workflow-glossary.md`

为准。

## 目标

- 围绕当前 `active_comment_id` 的 canonical atomic item 形成可执行策略
- 在进入 Stage 6 前，先把该条的 manuscript draft、response draft、证据与确认闭环写入数据库
- 让 Stage 5 的策略卡、补材判断与草案统一使用工作语言
- 把局部 blocker 留在 comment 作用域，而不是把整个 Stage 5 都锁死
- 允许用户显式切换当前焦点 comment，但禁止静默切换
- 在 Stage 5 完成时形成 `11-manuscript-revision-guide.md` 与 `12-manuscript-execution-graph.md`

## 进入条件

只有满足以下条件，才允许进入 Stage 5：

- Stage 4 已完成
- `08-atomic-comment-workboard.md` 已形成
- Stage 4 默认确认门禁已通过
- `gate-and-render` 核心脚本已允许进入 `stage_5`
- 当前准备处理的 `comment_id` 已在 workboard 中具备足够 planning 信息

## 必读材料

进入每条 item 的 Stage 5 前，至少要读：

- `response-strategy-cards/{comment_id}.md`（若已存在）
- `08-atomic-comment-workboard.md`
- `06-thread-to-atomic-mapping.md`
- `09-supplement-suggestion-plan.md`
- `10-supplement-intake-plan.md`
- 当前 `instruction_payload.resume_packet`
- 当前 `01-agent-resume.md`

必要时回读：

- `02-manuscript-structure-summary.md`
- `04-raw-review-thread-list.md`
- 原始 reviewer / editor 输入

## 子流程

### 1. 锁定或切换 active item

- 在 `workflow_state.active_comment_id` 中显式锁定当前 `comment_id`
- Stage 5 允许显式切换到任一非 `done` comment，但必须通过写库更新 `active_comment_id` 后再重跑 `gate-and-render`
- 切换时不得清空前一条 comment 的：
  - `strategy_cards`
  - `strategy_card_actions`
  - `strategy_action_target_locations`
  - `strategy_card_evidence_items`
  - `supplement_*`
  - `strategy_action_manuscript_execution_items`
  - `comment_response_drafts`
  - `comment_blockers`
  - `comment_completion_status`

禁止静默切换 `active_comment_id`。

### 2. 形成策略卡

至少要为当前 item 写入：

- `strategy_cards`
  - `proposed_stance`
  - `stance_rationale`
- `strategy_card_actions`
  - 至少一条修改动作
- `strategy_action_target_locations`
  - 当某条动作需要一个以上位置，或需要比 workboard 更细粒度的位置时写入
- `strategy_card_evidence_items`
  - 记录需要的证据、现有证据和缺口
- `strategy_card_pending_confirmations`
  - 记录该条策略卡在执行前仍需用户确认的事项
- `supplement_suggestion_items`
  - 记录 Stage 5 全局补材建议 backlog；进入 Stage 5 后即应生成
- `supplement_suggestion_intake_links`
  - 把补材建议项与后续实际 intake 文件关联起来
- `supplement_intake_items`
  - 记录本轮每个补材文件的接收判定（accepted/rejected）与理由
- `supplement_landing_links`
  - 对 accepted 补材记录其落地到 `comment_id/action_order/location_order` 的映射

### 3. 执行前逐条确认

Stage 5 默认要求逐条策略确认。

这意味着：

- Stage 4 的总确认只说明 workboard 可接受
- 它不能替代当前 item 的局部执行确认
- 在进入 manuscript draft 与 response draft 前，必须先让用户确认：
  - 当前立场是否可接受
  - 当前修改动作是否合适
  - 当前证据方案是否足够
  - 当前补材建议清单是否遗漏关键项

若用户尚未确认，Stage 5 默认停在等待确认态，而不是直接执行。

若策略卡在确认后又发生语义变更，必须：

- 把 `user_strategy_confirmed` 重置为 `no`
- 重建 `strategy_card_pending_confirmations`
- 清空旧的 `strategy_action_manuscript_execution_items`
- 清空旧的 `comment_response_drafts`
- 重新请求用户确认

### 4. 识别 blocker / evidence gap

以下情况应判定为 blocker 候选：

- `evidence_gap = yes` 且关键材料尚未到位
- 策略立场仍依赖用户补充事实或明确授权
- 修改动作会显著改变主线、核心 claim 或关键实验结论
- 当前 item 无法在不追加用户决策的情况下安全推进
- 本轮存在补材文件尚未给出接收/拒收判定
- 本轮存在 accepted 补材但未完成落地映射

comment-scoped blocker 的处理规则：

- 写入 `comment_blockers`
- 该 comment 不得标记为完成
- 仍允许显式切换到其他非 `done` comment

global blocker 的处理规则：

- 写入 `workflow_global_blockers`
- 整个 Stage 5 进入 blocked
- 不得切换 comment

### 5. 形成 Stage 5 草案真源

在策略确认完成后，才允许形成：

- `strategy_action_manuscript_execution_items`
  - 以 `comment_id + action_order + item_order` 为粒度
  - 保存当前条目的 manuscript execution items 与简短 rationale
- `comment_response_drafts`
  - 以 `comment_id` 为粒度
  - 保存当前条目的 response 草案与简短 rationale

这些真源用于派生 Stage 6 的 revision backlog、revision audit 和 response 覆盖闭环。

若仍存在 evidence gap，当前条目仍可继续保留 blocker；但 draft authoring 的前置条件始终是“策略已确认”，而不是“blocker 已全部关闭”。

语言规则：

- `strategy_cards`、`strategy_card_actions`、`strategy_card_evidence_items`、`supplement_intake_items.decision_rationale`、`comment_blockers` 使用工作语言
- `strategy_action_manuscript_execution_items` 与 `comment_response_drafts` 也使用工作语言
- reviewer / editor 原文摘录与 source span 仍保持原语言

Stage 6 会在这些真源基础上继续完成：

- `revision_plan_actions`
- `revision_action_logs`
- `response_thread_rows`
- 最终 `working_manuscript` 与双格式 response letter

### 6. 写入完成状态

只有当以下内容都已成立时，才允许更新 `comment_completion_status` 为可完成态：

- 策略卡完成
- 证据判断完成
- `manuscript_execution_items_done = yes`
- `response_draft_done = yes`
- 一一对应检查通过

其中：

- `manuscript_execution_items_done = yes`
  - 只表示当前 comment 需要的 `strategy_action_manuscript_execution_items` 已形成
- `response_draft_done = yes`
  - 只表示当前 comment 的 `comment_response_drafts` 已形成

它们都不表示 Stage 6 的最终文案已导出。

## 最低必须明确的策略卡内容

每条 Stage 5 item 至少要明确：

- `proposed_stance`
- `stance_rationale`
- 至少一条 `strategy_card_actions`
- 需要时的 `strategy_action_target_locations`
- 证据条目
- 待确认事项
- manuscript draft
- response draft

如果这些内容不足，说明该 item 仍停留在 planning 草图阶段，不能视为 Stage 5 可执行。

## blocker / evidence gap 判断口径

### evidence gap = yes 的典型场景

- reviewer 明确要求新增实验、数据、图表、统计或外部证据
- 当前已有证据不足以支撑打算采用的回复立场
- 不补材就无法形成可信的 response draft

### 默认不应淡化 blocker 的情形

- 位置已经明确，但证据仍缺
- 立场已经想好，但材料还没到
- 用户尚未授权高风险改写
- 补材已读但未形成 intake 判定
- 补材已接收但没有 action/location 级落地映射

这些情况下，不得因为“策略已想清楚”就把条目标记为完成。

## 一一对应检查口径

Stage 5 的一一对应检查至少要回答：

- 当前 response draft 是否直接回应当前 atomic item
- 当前 manuscript drafts 是否确实支撑当前 response draft
- 当前草案是否错把别的 item 的修改混到本条里
- 当前 item 的 thread-level 回映是否在 Stage 6 中可聚合

只要这层关系还不稳定，就不能把该条记为完成。

## 何时必须向用户提问

以下情况必须向用户提问，而不是自己补决策：

- 策略立场存在高风险歧义
- evidence gap 成立且需要补材
- 修改动作会显著改变论文主线或关键论点
- 当前条目无法在不追加用户决策的情况下安全推进

## 禁止动作

- 未确认就执行该条
- 证据缺口未关闭就标记完成
- 静默切换 `active_comment_id`
- 只写策略立场、不形成数据库中的正式草案真源就标记完成
- 把 Stage 4 总确认误当成 Stage 5 逐条执行确认

## 用户可读视图

- `response-strategy-cards/{comment_id}.md`
- 必要时同时展示：
  - `08-atomic-comment-workboard.md`
  - `06-thread-to-atomic-mapping.md`
  - `09-supplement-suggestion-plan.md`
  - `10-supplement-intake-plan.md`

## 完成定义

当前 active atomic item 只有在以下全部成立时，才算完成：

- 策略卡完成
- 证据判断完成
- manuscript draft 已形成
- response draft 已形成
- 一一对应检查通过
- `comment_completion_status` 已更新为可完成态
- `gate-and-render` 核心脚本允许继续推进当前条目或显式切换下一条目

## 与 Stage 6 的边界

Stage 5 到这里为止，必须已经完成：

- 策略、立场与证据判断
- 修改方向与草案边界
- manuscript draft 与 response draft

Stage 5 不负责：

- 最终成文润色
- revision audit 记录
- thread-level response row 组装
- `working_manuscript` 最终交付
- 可选 `latexdiff_manuscript`

这些工作都留给 Stage 6。

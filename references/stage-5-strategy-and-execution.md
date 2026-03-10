# 阶段五：逐条策略与执行

本阶段使用的正式术语、脚本称呼和 action id 以：

- `review-master/references/workflow-glossary.md`

为准。

## 目标

- 围绕当前 `active_comment_id` 的 canonical atomic item 形成可执行策略
- 在进入草案执行前完成逐条策略确认
- 对 evidence gap、blocker、补材和完成条件做严格门禁
- 让每条 atomic item 在进入 Stage 6 前都具备可追溯的策略、草案和一一对应关系

## 进入条件

只有满足以下条件，才允许进入 Stage 5：

- Stage 4 已完成
- `atomic-comment-workboard.md` 已形成
- Stage 4 默认确认门禁已通过
- `gate-and-render` 核心脚本已允许进入 `stage_5`
- 当前准备处理的 `comment_id` 已在 workboard 中具备足够 planning 信息

若 Stage 4 的待确认事项尚未清空，或 planning 仍为空壳，则不得进入 Stage 5。

## 必读材料

进入每条 item 的 Stage 5 前，至少要读：

- `response-strategy-cards/{comment_id}.md`（若已存在）
- `atomic-comment-workboard.md`
- `thread-to-atomic-mapping.md`
- `response-letter-outline.md`
- 当前 `instruction_payload.resume_packet`
- 当前 `agent-resume.md`

必要时回读：

- `manuscript-structure-summary.md`
- `raw-review-thread-list.md`
- 原始 reviewer / editor 输入

## 子流程

### 1. 锁定 active item

- 在 `workflow_state.active_comment_id` 中锁定当前 `comment_id`
- 只有当以下任一条件成立时，才允许切换：
  - 当前 item 已完成
  - 当前 item 已明确 blocked，且暂停理由已写入
  - 用户明确要求改变处理顺序

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
- `supplement_intake_items`
  - 记录本轮每个补材文件的接收判定（accepted/rejected）与理由
- `supplement_landing_links`
  - 对 accepted 补材记录其落地到 `comment_id/action_order/location_order` 的映射

### 3. 执行前逐条确认

Stage 5 默认要求逐条策略确认。

这意味着：

- Stage 4 的总确认只说明 workboard 可接受
- 它不能替代当前 item 的局部执行确认
- 在进入稿件修改草案和 response 段落草案前，必须先让用户确认：
  - 当前立场是否可接受
  - 当前修改动作是否合适
  - 当前证据方案是否足够

若用户尚未确认，Stage 5 默认停在等待确认态，而不是直接执行。

### 4. 识别 blocker / evidence gap

以下情况应判定为 blocker 候选：

- `evidence_gap = yes` 且关键材料尚未到位
- 策略立场仍依赖用户补充事实或明确授权
- 修改动作会显著改变主线、核心 claim 或关键实验结论
- 当前 item 无法在不追加用户决策的情况下安全推进
- 本轮存在补材文件尚未给出接收/拒收判定
- 本轮存在 accepted 补材但未完成落地映射

一旦 blocker 成立：

- 必须写入 `workflow_global_blockers`
- 必须更新 `resume_brief` 与 `resume_open_loops`
- 不得把当前 item 标记为完成
- 必须先请求补材、澄清或确认

### 5. 形成草案

在策略确认完成且 blocker 已解除后，才允许形成：

- 稿件修改草案
- response 段落草案

形成草案时必须保证：

- 修改动作和位置能落到当前 atomic item
- response 段落直接服务当前 atomic item
- 若一条动作对应多个位置，必须在 `strategy_action_target_locations` 中明确

### 6. 写入完成状态

只有当以下内容都已成立时，才允许更新 `comment_completion_status` 为可完成态：

- 策略卡完成
- 证据判断完成
- 稿件修改草案完成
- response 段落草案完成
- 一一对应检查通过

## 最低必须明确的策略卡内容

每条 Stage 5 item 至少要明确：

- `proposed_stance`
- `stance_rationale`
- 至少一条 `strategy_card_actions`
- 需要时的 `strategy_action_target_locations`
- 证据条目
- 待确认事项

如果这些内容不足，说明该 item 仍停留在 planning 草图阶段，不能视为 Stage 5 可执行。

## blocker / evidence gap 判断口径

### evidence gap = yes 的典型场景

- reviewer 明确要求新增实验、数据、图表、统计或外部证据
- 当前已有证据不足以支撑打算采用的回复立场
- 不补材就无法形成可信的 response 段落草案

### 默认不应淡化 blocker 的情形

- 位置已经明确，但证据仍缺
- 立场已经想好，但材料还没到
- 用户尚未授权高风险改写
- 补材已读但未形成 intake 判定
- 补材已接收但没有 action/location 级落地映射

这些情况下，不得因为“策略已想清楚”就把条目标记为完成。

## 一一对应检查口径

Stage 5 的一一对应检查至少要回答：

- 当前 response 段落草案是否直接回应当前 atomic item
- 当前稿件修改草案是否确实支撑当前 response 段落
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
- 只写策略立场、不形成草案就标记完成
- 把 Stage 4 总确认误当成 Stage 5 逐条执行确认

## 用户可读视图

- `response-strategy-cards/{comment_id}.md`
- 必要时同时展示：
  - `atomic-comment-workboard.md`
  - `thread-to-atomic-mapping.md`
  - `response-letter-outline.md`

## 完成定义

当前 active atomic item 只有在以下全部成立时，才算完成：

- 策略卡完成
- 证据判断完成
- 稿件修改草案完成
- response 段落草案完成
- 一一对应检查通过
- `comment_completion_status` 已更新为可完成态
- `gate-and-render` 核心脚本允许继续推进当前条目或切换下一条目

## 与 Stage 6 的边界

Stage 5 到这里为止，必须已经完成：

- 策略、立场与证据判断
- 修改方向与草案边界
- 稿件修改草案与 response 段落草案

Stage 5 不负责最终成文润色，也不负责给 response letter 做 action-level 的三版本选择。

Stage 6 只负责：

- 把 Stage 5 已确认的方案转成最终稿里真正落下去的 manuscript 文案
- 让用户对每个 action 的每个 target location 的最终落稿文本做三选一
- 在此基础上组装 thread-level 的最终 response rows

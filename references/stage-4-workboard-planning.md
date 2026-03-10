# 阶段四：atomic workboard 规划

本阶段使用的正式术语、脚本称呼和 action id 以：

- `review-master/references/workflow-glossary.md`

为准。

## 目标

- 围绕 canonical atomic item 建立阶段四主工作板
- 把优先级、依赖、证据缺口、原文位置与下一步动作统一到 atomic 层
- 在进入 Stage 5 之前，默认形成一次用户可审阅、可确认的 planning 结果

## 进入条件

- Stage 3 已完成
- `raw_review_threads`、`atomic_comments`、`raw_thread_atomic_links`、`atomic_comment_source_spans` 已稳定
- 最近一次 `gate-and-render` 已返回允许进入 Stage 4 的结果

## 必读材料

- `thread-to-atomic-mapping.md`
- `atomic-review-comment-list.md`
- `manuscript-structure-summary.md`
- `review-master/references/sql-write-recipes.md`
- `review-master/references/workflow-state-machine.md`
- `review-master/references/stage-4-workboard-planning.md`

## 子流程

### 1. 为每条 atomic item 建立状态真源

- 对每个 `comment_id`，必须写一条 `atomic_comment_state`
- 最低必须明确的 planning 字段：
  - `status`
  - `priority`
  - `evidence_gap`
  - `user_confirmation_needed`
  - `next_action`
- 若这些字段仍为空，Stage 4 不得视为完成

### 2. 建立位置规划

- 对每个 `comment_id`，至少写一条 `atomic_comment_target_locations`
- `target_location` 的使用口径：
  - 可以先写到章节级
  - 可以临时写 `TBD`
  - 但必须足够支撑 Stage 5 的下一步动作选择
- “位置不够精确”不等于“不能 planning”
- 若 `TBD` 已多到无法支撑 Stage 5，则 Stage 4 不得视为完成

### 3. 建立分析条目

- 对每个 `comment_id`，至少写一条 `atomic_comment_analysis_links`
- 分析条目用于承载：
  - `manuscript_claim_or_section`
  - `existing_evidence`
  - `gap_summary`
  - `dependency_comment_id`
- 一条 atomic item 可以有多个分析条目
- 一个分析条目可以依赖另一条 canonical atomic item

### 4. 判断 priority / evidence gap / dependency / next action

- `priority`
  - 根据对论文主线影响、实现工作量和风险判断
- `evidence_gap`
  - 当前已有证据不足以支撑后续回复或修改方案时写 `yes`
- `dependency_comment_id`
  - 某条 atomic item 的 planning 必须等待另一条 atomic item 先推进时才设置
- `next_action`
  - 应明确指出下一步最小前进行动，例如：
    - 进入 Stage 5
    - 等待确认
    - 请求补充定位
    - 请求补充材料

### 5. 默认进入确认门禁

- Stage 4 的默认主路径不是“建完 workboard 立即进入 Stage 5”
- 默认流程固定为：
  1. 建立完整 atomic workboard
  2. 写入 `workflow_pending_user_confirmations`
  3. 运行 `gate-and-render`
  4. 向用户展示 `atomic-comment-workboard.md` 与 `thread-to-atomic-mapping.md`
  5. 用户确认后再清空待确认项并进入 Stage 5
- `user_confirmation_needed` 应默认倾向于 `yes`，除非已经没有实质不确定性

### 6. 更新恢复信息并重新 gate

- 更新：
  - `resume_brief`
  - `resume_open_loops`
  - 视情况更新 `resume_recent_decisions`
- 写库后立即运行 `gate-and-render`
- 读取最新 `instruction_payload`
- 进入“等待确认”态，或在确认后进入 Stage 5

## 何时必须向用户提问

- planning 存在高风险歧义
- `target_location` 过于不确定
- dependency 会影响后续执行顺序
- evidence gap 是否成立无法稳定判断

## 多对多要求

- 一条 atomic item 可以对应多个 `target_location`
- 一条 atomic item 可以有多个分析条目
- 一个分析条目可以依赖另一条 canonical atomic item
- 阶段四必须始终面向 canonical atomic item，而不是回退到 raw thread 直接做 planning

## 用户可读视图

- `atomic-comment-workboard.md`
- `thread-to-atomic-mapping.md`

## 禁止动作

- 跳过 Stage 4 默认确认门禁直接进 Stage 5
- 在 planning 仍为空壳时推进
- 因为位置还不够精确就假装 evidence gap 不存在
- 把 provisional planning 当成最终定稿

## 完成标准

- 每个 `comment_id` 都有：
  - 一条 `atomic_comment_state`
  - 至少一条 `atomic_comment_target_locations`
  - 至少一条 `atomic_comment_analysis_links`
- 所有待确认事项已成功写入并面向用户展示
- `gate-and-render` 核心脚本允许进入“等待确认”态或确认后的 Stage 5

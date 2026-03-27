# 阶段三：原始意见块与 canonical atomic item 建模

本阶段使用的正式术语、脚本称呼和 action id 以：

- `review-master/references/workflow-glossary.md`

为准。

## 目标

- 先保留 reviewer / editor 的原始条目层
- 再把这些原始条目整理为内部执行所需的 canonical atomic item
- 明确原始意见块到 atomic item 的拆分、合并与去重关系
- 生成一份面向用户审阅的 `07-review-comment-coverage.md`，让用户确认原始审稿意见已被充分覆盖（`primary/supporting` 红色高亮，`duplicate_filtered` 橙色高亮，未覆盖片段保持默认文本色）
- 计算 Stage 3 字符级覆盖率（全字符口径，主指标包含 `duplicate_filtered`），并在视图与 `instruction_payload.coverage_review_metrics` 中展示阈值判定（hard=`30%`，soft=`50%`）

## 进入条件

- Stage 2 已完成
- `02-manuscript-structure-summary.md` 已足以支撑后续 thread 与 atomic 映射
- 最近一次 `gate-and-render` 已返回允许进入 Stage 3 的结果

## 必读材料

- `02-manuscript-structure-summary.md`
- `04-raw-review-thread-list.md`
- `review-master/references/sql-write-recipes.md`
- `review-master/references/workflow-state-machine.md`
- `review-master/references/stage-3-comment-atomization.md`

## 子流程

### 1. 先抽 raw review threads

- 优先保留 reviewer / editor 原文中的自然条目边界
- `raw_review_threads.original_text` 保留原语言
- 对有明确编号、列表项、bullet 的输入：
  - 先按原始编号或列表项切分
- 对没有明确编号、但按自然段呈现多条意见的输入：
  - 先按自然段边界保留
- 在 raw thread 层不做语义合并
- reviewer comment 与 editor comment 都进入 `raw_review_threads`

### 2. 判断 thread 边界

- 原始条目边界应尽量贴近用户最终要看的 reviewer / editor 原文结构
- 同一原始编号项中若包含多个实质问题：
  - 在 raw thread 层仍保留一个 `thread_id`
  - 在 atomic 层再拆成多个 `comment_id`
- 若 reviewer 原文边界本身含混，且无法稳定判定：
  - 必须向用户追问
  - 不要擅自重排 reviewer 原文结构

### 3. 形成 canonical atomic item

- 原子化由 LLM 主导，不由脚本替代
- `raw_review_threads.normalized_summary`、`atomic_comments.canonical_summary` 与 `atomic_comments.required_action` 使用工作语言
- 一个 canonical atomic item 必须满足：
  - 可独立回应
  - 可独立制定修改动作
  - 可独立判定完成
- 应拆开的情况：
  - 一个 reviewer thread 中包含多个独立的实质问题
  - 同一主题下存在不同期望动作
  - 同一段意见同时要求解释、补实验、改写不同部分
- 不应过度拆分的情况：
  - 同一行动的背景说明
  - 解释同一修改动作的修辞性补充
  - 不能独立判定完成的支撑性短句

### 4. 采用保守合并

- 不同 reviewer 的重复意见默认采用保守合并
- 只有以下条件同时满足时，才应合并成同一个 canonical atomic item：
  - 核心问题一致
  - 期望动作一致
  - 所需证据和修改方向无明显分叉
- 默认不合并的情况：
  - 一个 reviewer 要求补实验，另一个只要求解释原因
  - 一个指向 method，另一个指向 results / discussion
  - 合并后无法写出单一明确的 `required_action`
- 合并后必须通过 `atomic_comment_source_spans` 保存依据，解释：
  - 某 atomic item 来自哪些原始 thread
  - 为什么这些 thread 被视为同一 canonical item
- `atomic_comment_source_spans.excerpt_text` 保留原语言，不翻译

### 5. 建立映射关系

- 写入 `raw_thread_atomic_links`
- 保证：
  - 每个 `thread_id` 至少映射到一个 `comment_id`
  - 每个 `comment_id` 至少被一个 `thread_id` 引用
- Stage 3 的核心不是“尽量少 comment”，而是建立稳定、可执行、可回映的 canonical atomic 集合

### 6. 更新恢复信息并重新 gate

- 更新：
  - `resume_brief`
  - `resume_recent_decisions`
  - `resume_must_not_forget`
- 同步写入：
  - `review_comment_source_documents`
  - `raw_thread_source_spans`
- 写库后立即运行 `gate-and-render`
- 读取最新的 `instruction_payload`
- 先向用户展示 `07-review-comment-coverage.md`、`04-raw-review-thread-list.md` 和 `06-thread-to-atomic-mapping.md`
- 只有当用户确认覆盖率审阅结果且 gate 明确允许时，才进入 Stage 4

## 稳定 ID 规则

- `thread_id`
  - 固定格式：`<reviewer_id>_thread_<3-digit-seq>`
- `comment_id`
  - 固定格式：`atomic_<3-digit-seq>`
- `comment_id` 使用稳定的原子意见序列编号；reviewer 来源通过 `raw_thread_atomic_links` 与 `atomic_comment_source_spans` 表达

## 何时必须向用户提问

- reviewer 原始条目边界无法稳定识别
- 多条评论是否应合并存在高风险歧义
- editor 要求与 reviewer 要求冲突，无法仅靠当前材料判断

## 用户可读视图

- `04-raw-review-thread-list.md`
- `04-atomic-review-comment-list.md`
- `06-thread-to-atomic-mapping.md`
- `07-review-comment-coverage.md`

## 禁止动作

- 跳过 raw thread 层直接写 atomic
- 为了减少工作量而激进合并
- 仅凭关键词匹配做去重
- 用脚本替代 Agent 执行原子化语义判断

## 完成标准

- `raw_review_threads` 已稳定
- `atomic_comments` 已形成 canonical atomic item 集合
- 每个 `thread_id` 至少映射到一个 `comment_id`
- 每个 `comment_id` 至少被一个 `thread_id` 引用
- `atomic_comment_source_spans` 足以解释每个合并来源
- `raw_thread_source_spans` 能把每个 `thread_id` 精确锚定到原文 offset（`span_text == original_text[start_offset:end_offset]`），且每个 `thread_id` 至少有一条 `span_role='primary'`
- `07-review-comment-coverage.md` 已生成，且覆盖映射附录能稳定映射到 `thread_id` / `comment_id`
- gate 若提示“仅标题覆盖、正文疑似漏抽”，需与用户复核并按需补写 `supporting` span；该提示默认不作为硬阻断
- gate 若提示全局字符覆盖率低于 hard（`30%`），必须先回写 Stage 3 真源并重跑；`[30%, 50%)` 属于软提示，需与用户复核但不单独阻断
- 用户已确认 Stage 3 覆盖率审阅结果
- `gate-and-render` 核心脚本允许进入阶段四

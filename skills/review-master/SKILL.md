---
name: review-master
description: 适用于 LaTeX 论文原稿与 Markdown/txt 审稿意见文件的交互式审稿回复流程。运行时以 SQLite 为唯一真源，gate-and-render 核心脚本负责状态门禁、视图重渲染和下一步指令输出。
---

# review-master

## 目标

- 帮助用户以阶段化方式推进论文修回，而不是一步到位改稿
- 将原始审稿意见块整理为 canonical atomic item，并在用户确认下逐条闭环
- 以 `review-master.db` 维持运行时唯一真源
- 持续向用户提供只读 Markdown 视图，辅助确认当前进度和下一步动作

## 非目标

- 不直接一步到位修改论文原稿
- 不替用户做未经授权的学术决策
- 不把脚本当作核心语义判断的替代品
- 不把只读 Markdown 视图当成运行时真源

## 输入

### 必需输入

- `manuscript_source`
  - 单个主 `.tex` 文件路径，或完整 LaTeX 工程目录路径
- `review_comments_source`
  - `.md` 或 `.txt` 文件路径

### 可选输入

- `editor_letter_source`
  - 编辑部来信、格式要求或截止要求的文件路径
- `user_notes`
  - 用户补充说明、限制、策略偏好或自由文本说明

## 语言上下文

- 文本语言：指 manuscript 与最终落地文案使用的语言
  - 默认以 `manuscript_source` 语言为准
  - 若 `review_comments_source` 与 manuscript 语言不同，仍以 manuscript 语言为准
- 工作语言：指用户与 Agent 交互、中间视图和中间工件描述使用的语言
  - 默认从当前用户 prompt 语言推断
  - Stage 1 必须显式向用户确认；若用户覆盖，以用户覆盖为准
- 语言使用规则：
  - 任何 reviewer / editor 原文、原稿原文摘录、`raw_review_threads.original_text`、`atomic_comment_source_spans.excerpt_text` 都保留原语言
  - Stage 3-5 的 normalized summary、canonical summary、strategy card、workboard、resume、gate 输出和 Stage 5 execution items / response drafts 使用工作语言
  - Stage 6 的 manuscript final copy、response rows、最终导出稿件与 response letter 必须使用文本语言
- 运行时真源：
  - `runtime_language_context`
  - `runtime-localization/`

## 输出

### 运行时输出

artifact workspace 根目录固定包含：

- `review-master.db`
- `runtime-localization/`
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

### 最终输出

- `working_manuscript`
  - workspace 内协作修改并持续审计的最终工作稿
- `response_markdown`
  - Point-to-point 表格形式的 Markdown 回复信
- `response_latex`
  - Point-to-point 表格形式的 LaTeX 回复信
- `latexdiff_manuscript`
  - 可选的稿件比较稿；仅在环境可用时生成

## 第三方运行时依赖

脚本驱动模式依赖以下运行时：

- Python 3
- `PyYAML`
- `Jinja2`

若这些第三方依赖不可用，先询问用户是否批准安装；若用户不批准，则数据库仍可作为真源继续使用，但只读 Markdown 视图必须由 Agent 手工拼接。

## 核心脚本

关于运行时的核心只读检查与渲染脚本，统一约定如下：

- 正式称呼：`gate-and-render` 核心脚本
- 文件路径：`review-master/scripts/gate_and_render_workspace.py`
- 标准执行方式：

```bash
conda run --no-capture-output -n DataProcessing python -u \
  review-master/scripts/gate_and_render_workspace.py \
  --artifact-root <ARTIFACT_ROOT>
```

这个正式称呼在本 skill 中是唯一有效称呼。所有文档、恢复包和用户交互都使用 `gate-and-render` 这一称呼。

## 术语与命名真源

以下对象、动作名、脚本称呼和最终导出产物的正式命名统一以：

- `review-master/references/workflow-glossary.md`

为单一真源。

## 职责分工与强制脚本纪律

### 必须由 Agent 大语言模型完成的任务

以下任务属于语义理解、分析判断或学术交互职责，必须由 Agent 大语言模型完成，不得转交给确定性脚本：

- 理解用户意图、约束和补充说明
- 理解论文结构、论点、证据和高风险修改区
- 理解 reviewer / editor 原始意见的真实含义
- 原始意见块的拆分、合并、去重和 canonical atomic item 建模
- 审稿意见与原文、证据、修改策略之间的语义映射
- 优先级、依赖关系、evidence gap、回复立场和工作计划判断
- 用户交互、确认请求、补材请求和最终回复信措辞组织

原则：凡是需要语义理解、学术判断、策略制定或与用户协商的工作，一律由 Agent 大语言模型承担。

### 只允许脚本承担的任务

脚本只承担确定性、重复性高、可验证的工作，例如：

- 入口辅助判断
- workspace 初始化
- 读取 SQLite 真源
- 状态门禁检查
- 只读视图重渲染
- 恢复包输出

脚本不得承担原子化语义判断、回复策略制定、学术论证或其他需要语义理解的核心任务。

### 必须执行的脚本

以下脚本属于正式 workflow 的强制组成部分：

1. 入口辅助脚本：`review-master/scripts/detect_main_tex.py`
   - 当 `manuscript_source` 是 LaTeX 工程目录，且主入口需要辅助识别时必须调用
   - 当 `manuscript_source` 已经是单个明确的主 `.tex` 文件时通常不调用

2. 初始化脚本：`review-master/scripts/init_artifact_workspace.py`
   - 当 workspace 尚未初始化时必须调用
   - 不允许跳过初始化直接假设数据库或视图已就绪

3. `gate-and-render` 核心脚本：`review-master/scripts/gate_and_render_workspace.py`
   - 统一恢复入口时必须调用
   - 每次正式写库后必须调用
   - 每个阶段完成后必须调用，不能凭记忆直接推进到下一阶段

### 禁止临时脚本承担语义任务

- 不允许为了原子化、去重、语义映射、优先级判断、回复策略制定等任务临时编写脚本
- 不允许用一次性的 Python、Shell 或其他临时程序替代 Agent 大语言模型的语义理解职责
- 若已有正式脚本不覆盖某项语义任务，正确做法是由 Agent 直接完成，而不是新增临时脚本绕过约束

## 核心运行契约

1. 运行时唯一真源固定为 artifact workspace 根目录下的 `review-master.db`。
2. `workflow_state` 只保存在数据库中，由 `gate-and-render` 读取并反映到恢复包与只读视图。
3. `runtime_language_context` 记录文本语言、工作语言、检测结果、来源与确认状态；所有语言切换都以它为准。
4. `runtime-localization/` 是 workspace 级本地化覆盖层；优先级高于 skill 包默认消息目录，但不替代 skill 包脚本。
5. 运行时 Markdown 文件全部是只读渲染视图，Agent 不得直接编辑。
6. 每次数据库写入后，都必须重新运行 `gate-and-render` 核心脚本。
7. `gate-and-render` 核心脚本负责四件事：
   - 状态门禁校验
   - 只读视图重渲染
   - 输出 `instruction_payload`
   - 输出并重渲染恢复包（`instruction_payload.resume_packet` 与 `01-agent-resume.md`）
8. 若脚本给出 `repair_sequence`，必须先修数据库真源，再重新运行脚本。
9. 若存在待确认事项或 blocker，不得绕过状态机继续推进。
10. 首次调用、跨 Session 恢复和上下文压缩后的继续执行，全部走同一条“先恢复，后执行”协议；但在 workspace 尚未初始化的首次进入场景下，必须先确认文本语言与工作语言，再初始化 workspace。

## 核心数据模型

本 skill 采用三层 comment/workflow 索引：

1. 原始审稿意见块：`raw_review_threads`
   - 这是最终 response letter 的正式索引层
   - 一条原始 reviewer 条目可以映射到多个 canonical atomic item
2. 规范化原子意见：`atomic_comments`
   - 这是内部执行真源索引层
   - 不同 reviewer 的重复意见应在这一层真正合并
3. response letter 聚合层：`response_thread_action_log_links` 与 `response_thread_rows`
   - 最终回复信必须回到原始 `thread_id` 顺序输出
   - 最终导出必须使用 thread-level response row，而不是 `comment_id` 扁平列表
4. 语言上下文层：`runtime_language_context`
   - 记录 `document_language`、`working_language` 及检测/确认来源
   - `gate-and-render`、workspace 视图与导出脚本都必须显式消费这一层

关键关系全部表化，不使用 JSON/TEXT 多值列：

- `raw_thread_atomic_links`
- `atomic_comment_source_spans`
- `atomic_comment_target_locations`
- `atomic_comment_analysis_links`
- `strategy_action_target_locations`
- `response_thread_action_log_links`
- `workspace_manuscript_copies`
- `revision_action_logs`

## 状态机图示

```text
环境确认
  -> stage_1 入口解析与 workspace 初始化
  -> stage_2 原稿结构分析
  -> stage_3 原始意见块抽取 / 去重 / canonical atomic item 形成
  -> stage_4 atomic workboard 规划
       └─ 若 pending_user_confirmations 非空 -> 请求用户确认 -> 回到 stage_4
  -> stage_5 逐条策略与执行
       └─ 若 global_blockers / evidence_gap 未关闭 -> 请求补材 -> 回到 stage_5
  -> stage_6 working_manuscript 交互式改稿 / revision audit / thread-level response 覆盖闭环
       └─ 若存在未审计 diff 或 thread 覆盖未闭环 -> 记录 revision round -> 重新运行 gate-and-render 核心脚本

每次正式写入：
 SQL write -> review-master.db
           -> review-master/scripts/gate_and_render_workspace.py
           -> instruction_payload + resume_packet + 01-agent-resume.md
           -> 下一步动作 / 回修 / 请求用户输入
```

## 总体执行流程

### 0. 环境确认

先确认脚本运行环境是否满足要求。

- 检查宿主环境是否具备本 skill 所需第三方依赖
- 若环境满足，进入正常脚本驱动流程
- 若环境不满足，必须先询问用户是否批准安装缺失依赖
- 若用户批准，安装后再继续
- 若用户不批准，数据库仍可继续作为真源，但后续 Markdown 视图只能由 Agent 手工拼接

详细规则：

- `review-master/references/helper-scripts.md`
- `review-master/references/stage-1-entry-and-bootstrap.md`

### 0.5 统一恢复入口

无论是首次调用、跨 Session 恢复，还是上下文压缩后的继续执行，都必须先走同一条恢复协议。

固定顺序：

1. 运行 `review-master/scripts/gate_and_render_workspace.py`
2. 读取 `instruction_payload.resume_packet`
3. 读取 `01-agent-resume.md`
4. 按 `resume_read_order` 打开当前阶段主视图与参考文档
5. 只有完成恢复对齐后，才允许继续执行 SQL write recipe

要点：

- 首次调用也必须先恢复
- 首次调用得到的是 `bootstrap resume`
- 后续恢复调用得到的是 `continuation resume`
- 区别只在恢复包内容，不在入口流程

详细规则：

- `review-master/references/helper-scripts.md`
- `review-master/references/workflow-state-machine.md`
- `review-master/references/sql-write-recipes.md`
- `review-master/assets/runtime/skill-runtime-digest.md`

### 1. 阶段一：入口解析与 workspace 初始化

做什么：

- 先确认运行环境是否满足脚本驱动要求
- 读取 `manuscript_source`、`review_comments_source`
- 吸收 `editor_letter_source` 与 `user_notes`
- 先判断文本语言与工作语言，并请求用户确认
- 判断主入口是单文件还是 LaTeX 工程目录
- 初始化 artifact workspace
- 初始化 `runtime_language_context` 与 `runtime-localization/`
- 按统一恢复入口读取 `instruction_payload.resume_packet` 与 `01-agent-resume.md`
- 写入 `resume_brief`
- 视情况写入 `resume_open_loops`
- 视情况写入 `resume_recent_decisions`
- 视情况写入 `resume_must_not_forget`

操作摘要：

- 先检查第三方依赖；若不满足，先问用户是否批准安装
- workspace 尚未存在时，先基于 manuscript / review comments / 当前 prompt 判断文本语言与工作语言，并显式向用户确认
- 单文件主稿通常不需要 `detect_main_tex.py`；LaTeX 工程目录优先调用它辅助判断主入口
- 若主入口不唯一，必须停下来问用户
- `init_artifact_workspace.py` 必须带 `--document-language` 与 `--working-language`
- workspace 初始化后，不允许直接跳入 Stage 2 写库，必须先完成 bootstrap/continuation resume 对齐
- 阶段一的产物不是“写了多少内容”，而是“入口已明确、workspace 已就绪、恢复包已读完、下一步动作已清楚”

阻断条件：

- 缺必需输入
- 文本语言或工作语言尚未确认
- manuscript 主入口无法唯一确定
- 运行环境缺依赖且用户未批准安装
- `gate-and-render` 返回 repair 或阻断性门禁问题

完成定义：

- 主入口明确
- 文本语言与工作语言已确认
- workspace 成功初始化
- `gate-and-render` 返回可继续
- `instruction_payload.resume_packet` 与 `01-agent-resume.md` 已被读取并对齐

脚本：

- `review-master/scripts/detect_main_tex.py`
- `review-master/scripts/init_artifact_workspace.py`
- `review-master/scripts/gate_and_render_workspace.py`

参考文档：

- `review-master/references/stage-1-entry-and-bootstrap.md`
- `review-master/references/helper-scripts.md`
- `review-master/references/sql-write-recipes.md`
- `review-master/references/workflow-state-machine.md`

### 2. 阶段二：原稿结构分析

做什么：

- 写入 `manuscript_summary`
- 写入 `manuscript_sections`
- 写入 `manuscript_claims`
- 明确高风险修改区
- 更新 `resume_brief`
- 补充 `resume_recent_decisions`
- 视情况补充 `resume_open_loops`

操作摘要：

- 这一阶段的目标不是“读完整篇论文”，而是建立足以支撑 Stage 3 和 Stage 4 的结构真源
- 必须明确主入口、工程形态、章节层级、核心论点、主要证据和高风险修改区
- 若论文结构不清、claim 抽取不稳定或工程残缺，应先继续分析或追问用户，而不是匆忙进入意见原子化
- 阶段二结束时，`02-manuscript-structure-summary.md` 应足以支撑后续 thread 抽取与 atomic 映射

阻断条件：

- `manuscript_sections` 或 `manuscript_claims` 明显缺失
- 章节层级无法支撑后续定位
- 高风险修改区尚未识别
- 仍存在足以影响 Stage 3 的结构性疑问

完成定义：

- `manuscript_summary`、`manuscript_sections`、`manuscript_claims` 已入库
- `02-manuscript-structure-summary.md` 已重渲染
- 结构摘要足以支撑后续 thread/atomic 映射
- `gate-and-render` 推荐进入 Stage 3

脚本：

- `review-master/scripts/gate_and_render_workspace.py`

参考文档：

- `review-master/references/stage-2-manuscript-analysis.md`
- `review-master/references/sql-write-recipes.md`
- `review-master/references/workflow-state-machine.md`

### 3. 阶段三：原始审稿意见块与 canonical atomic item 建模

做什么：

- 先抽出原始 reviewer / editor 条目，写入 `raw_review_threads`
- 再由 LLM 做去重、归并、原子化，产出 canonical `atomic_comments`
- 再写 `raw_thread_atomic_links` 与 `atomic_comment_source_spans`
- 再写 `review_comment_source_documents` 与 `raw_thread_source_spans`
- 更新 `resume_brief`
- 补充 `resume_recent_decisions`
- 补充 `resume_must_not_forget`

操作摘要：

- Stage 3 先保留 raw thread 层，再进入 canonical atomic 建模，不能跳过中间映射层
- reviewer / editor 原始条目边界先按原文自然条目保留，不在 raw thread 层做语义合并
- `raw_review_threads.original_text` 与 `atomic_comment_source_spans.excerpt_text` 必须保留原语言
- `raw_review_threads.original_text` 必须可回溯到原始 reviewer/editor 文本，不得写成纯归纳改写句
- `raw_review_threads.normalized_summary`、`atomic_comments.canonical_summary` 与 `atomic_comments.required_action` 必须写成工作语言
- `raw_thread_source_spans.span_role` 采用三类：`primary`（主意见）、`supporting`（正文/补充论据）、`duplicate_filtered`（重复出现但摘要层去重）
- Stage 3 必须额外形成 `07-review-comment-coverage.md`，按完整原始 reviewer/editor 文档顺序展示：`primary/supporting` 用红色高亮，`duplicate_filtered` 用橙色高亮并附 `dup` 标签，未覆盖片段保持默认文本色，并在附录表中给出 `thread_id` / `comment_id` / `span_role` 与 offset 映射
- Stage 3 同时计算字符级覆盖率指标（字符口径使用 Python `len`，包含空白；主指标分子包含 `duplicate_filtered`）并写入覆盖率视图与 instruction payload：
  - hard 阈值：`30%`（低于即硬阻断）
  - soft 阈值：`50%`（介于 hard/soft 为软提示，不额外阻断）
- canonical atomic item 必须满足：可独立回应、可独立制定修改动作、可独立判定完成
- 跨 reviewer 的重复意见默认采用保守合并：只有核心问题和期望动作都基本一致时才合并
- 若诉求角度、修改范围或所需证据明显不同，则保留为不同 atomic item
- 合并后的依据必须写入 `atomic_comment_source_spans`
- Stage 3 完成建模后必须请求用户确认 coverage view；未确认前不得进入 Stage 4

阻断条件：

- raw thread 边界无法稳定识别
- 是否合并存在高风险歧义且无法仅凭现有材料判断
- editor 要求与 reviewer 要求冲突，无法直接决定建模方式
- 存在 `thread_id` 未映射任何 `comment_id` 或 `comment_id` 未被任何 `thread_id` 引用
- coverage view 仍存在无法解释的未覆盖残留，或覆盖映射附录无法稳定映射到正确 `thread_id` / `comment_id`
- 覆盖真源缺失或无法由 `review_comment_source_documents` 与 `raw_thread_source_spans` 重建时，需要基于原始 reviewer/editor 文件重跑 Stage 3
- Stage 3 全局字符覆盖率低于 `30%`（含 duplicate 主指标）
- gate 的 “仅标题覆盖、正文疑似漏抽” 提示属于弱提示：必须与用户核查，但不直接阻断 Stage 4

完成定义：

- `raw_review_threads` 已稳定
- `atomic_comments` 已形成 canonical atomic item 集合
- 每个 `thread_id` 至少映射到一个 `comment_id`
- 每个 `comment_id` 至少被一个 `thread_id` 引用
- `atomic_comment_source_spans` 足以解释每个合并来源
- 每个 `thread_id` 至少有一条 `raw_thread_source_spans`，且至少包含一条 `span_role='primary'`，并满足 span offset 与 span_text 能精确回放到 `review_comment_source_documents.original_text`
- `07-review-comment-coverage.md` 已生成并足以供用户审阅
- 用户已明确确认 coverage 审阅结果
- `gate-and-render` 允许进入 Stage 4

脚本：

- `review-master/scripts/gate_and_render_workspace.py`

参考文档：

- `review-master/references/stage-3-comment-atomization.md`
- `review-master/references/workflow-state-machine.md`
- `review-master/references/sql-write-recipes.md`

### 4. 阶段四：atomic workboard 规划

做什么：

- 围绕 canonical atomic item 写入 `atomic_comment_state`
- 写入 `atomic_comment_target_locations`
- 写入 `atomic_comment_analysis_links`
- 默认写入 `workflow_pending_user_confirmations`
- 更新 `resume_brief`
- 更新 `resume_open_loops`
- 视情况更新 `resume_recent_decisions`
- 向用户展示 `08-atomic-comment-workboard.md` 与 `06-thread-to-atomic-mapping.md`

操作摘要：

- Stage 4 的目标是把每条 canonical atomic item 变成可执行 planning，而不是立刻进入逐条执行
- 默认要形成一次用户可审阅的 workboard，并通过确认门禁后才进入 Stage 5
- `target_location` 和部分分析项允许暂时写到章节级或 `TBD`
- 但 `priority`、`evidence_gap`、`next_action` 这类核心 planning 字段不得为空
- “位置不够精确”不等于“不能 planning”；真正不能推进的是 planning 仍为空壳

阻断条件：

- 存在 atomic item 还没有 `atomic_comment_state`
- `priority`、`evidence_gap` 或 `next_action` 未定
- provisional 信息已多到不足以支撑 Stage 5
- 待确认事项尚未完成

完成定义：

- 每个 `comment_id` 都有一条 `atomic_comment_state`
- 每个 `comment_id` 至少有一条位置记录和一条分析记录
- 待确认事项已成功写入并面向用户展示
- `gate-and-render` 允许进入“等待确认”态或确认后的 Stage 5

脚本：

- `review-master/scripts/gate_and_render_workspace.py`

参考文档：

- `review-master/references/stage-4-workboard-planning.md`
- `review-master/references/workflow-state-machine.md`
- `review-master/references/sql-write-recipes.md`

### 5. 阶段五：逐条策略与执行

做什么：

- 在 `workflow_state.active_comment_id` 中锁定当前 canonical atomic item
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
- 若需补材或澄清，写入 `workflow_global_blockers`
- 更新 `resume_brief`
- 更新 `resume_open_loops`
- 更新 `resume_recent_decisions`
- 更新 `resume_must_not_forget`

操作摘要：

- Stage 5 以 `active_comment_id` 为唯一执行焦点，不按原始 reviewer thread 直接推进
- 每条 atomic item 都应形成 `response-strategy-cards/{comment_id}.md`
- 进入 Stage 5 后必须形成 `09-supplement-suggestion-plan.md`，用于展示全局补材建议 backlog，并高亮当前 `active_comment_id`
- Stage 5 的 strategy card、workboard 补充描述、supplement intake rationale、comment blocker 与 resume 文本都使用工作语言
- 默认必须先完成逐条策略确认，再进入 manuscript execution items 和 response draft
- 只要策略语义发生变化，就必须重新打开确认，并清空当前已写入的 Stage 5 execution truth
- Stage 4 的总确认不能替代 Stage 5 的局部执行确认
- 若存在 evidence gap，应显式进入 blocker 路径，请求补材或澄清
- `09-supplement-suggestion-plan.md` 与 `10-supplement-intake-plan.md` 职责不同：前者是补材建议清单，后者是用户已提交文件的接收/落地视图
- 每轮补材必须形成文件级接收判定（accepted/rejected + rationale）
- 被接收的补材必须映射到 `comment_id/action_order/location_order`，并在 `10-supplement-intake-plan.md` 可追溯
- `strategy_action_manuscript_execution_items` 与 `comment_response_drafts` 是工作语言草案真源，不是最终文本语言成稿
- 只有当策略卡、证据判断、manuscript execution items、response draft 以及一一对应检查都完成后，当前条目才允许标记完成
- 只要没有 `workflow_global_blockers`，Stage 5 就允许显式 `set_active_comment` 切换焦点

阻断条件：

- evidence gap 未关闭
- 当前条目仍存在待确认事项
- 当前条目还没有形成足以确认的策略卡
- 草案尚未形成或一一对应检查尚未稳定
- 存在补材文件尚未判定接收/拒收，或接收补材尚未完成落地映射
- `gate-and-render` 返回 blocker 或 repair

完成定义：

- 当前 atomic item 的策略、证据、确认与完成状态已闭环
- manuscript draft 与 response draft 都已落地到正式真源表
- 一一对应检查通过
- `comment_completion_status` 已更新为可完成态
- `gate-and-render` 允许继续推进当前条目或显式切换下一条目

脚本：

- `review-master/scripts/gate_and_render_workspace.py`

参考文档：

- `review-master/references/stage-5-strategy-and-execution.md`
- `review-master/references/workflow-state-machine.md`
- `review-master/references/sql-write-recipes.md`

### 6. 阶段六：交互式改稿、revision audit 与 response 覆盖闭环

做什么：

- 读取并消费 `03-style-profile.md`
- 基于 Stage 5 已确认策略与 execution items 派生 `revision_plan_actions`
- 与用户协作，直接修改 `working_manuscript`
- 通过 `capture_revision_action.py` 记录每一轮明确修改
- 通过 `commit_revision_round.py` 以固定顺序执行 `capture -> gate-and-render`
- 写入 `response_thread_rows`
- 写入 `response_thread_action_log_links`
- 写入 `export_artifacts`
- 更新 `resume_brief`
- 清理或收缩 `resume_open_loops`
- 记录最终 `resume_recent_decisions`
- 先向用户展示：
  - `11-manuscript-revision-guide.md`
  - `12-manuscript-execution-graph.md`
  - `13-revision-action-log.md`
  - `14-response-coverage-matrix.md`
  - `15-response-letter-preview.md`
  - `16-response-letter-preview.tex`
  - `17-final-assembly-checklist.md`
- 允许可选生成 `latexdiff_manuscript`
- 在所有 revision plan action 结案且 response 覆盖闭环后，保持 `working_manuscript` 与双格式 response letter 为正式输出

操作摘要：

- Stage 6 的正式协作路径是 `working_manuscript`、revision audit 与 thread-level response 覆盖闭环
- Stage 6 以 `working_manuscript` 为唯一协作修改稿，以 `source_snapshot` 为只读基准
- Agent 每完成一轮明确修改，都必须通过 `commit_revision_round.py` 提交，不能只改文件不记审计
- `gate-and-render` 保持只读；它只检查未审计 diff、response 覆盖与完成度，不替用户补写 revision log
- `response_thread_rows` 必须由已确认策略、已完成 revision logs 与 thread-level 聚合共同驱动
- `response_only_resolution` 只用于无需直接改稿、但必须在回复信中解释的 thread
- `working_manuscript`、`response_thread_rows` 与最终 response letter 必须使用文本语言
- `latexdiff_manuscript` 是可选辅助，不是 Stage 6 硬门禁

阻断条件：

- revision backlog 尚未建立
- 仍有 `revision_plan_actions.status` 不是 `completed` 或 `dismissed`
- `working_manuscript` 存在未审计 diff
- 某个 `thread_id` 尚无最终 `response_thread_rows`
- 某条 `response_thread_rows` 既没有 linked revision log，也没有显式标记 `response_only_resolution`
- `gate-and-render` 返回 blocker 或 repair

完成定义：

- 所有 `revision_plan_actions` 都已结案
- 所有已发生的 `working_manuscript` 修改都已通过 revision audit 写库
- 每个 `thread_id` 都已有最终 response row，且 coverage matrix 显示闭环
- `working_manuscript`、Markdown response letter、LaTeX response letter 已稳定可交付
- 若环境支持，`latexdiff_manuscript` 已作为辅助视图生成

脚本：

- `review-master/scripts/gate_and_render_workspace.py`
- `review-master/scripts/capture_revision_action.py`
- `review-master/scripts/commit_revision_round.py`

参考文档：

- `review-master/references/stage-6-final-review-and-export.md`
- `review-master/references/workflow-state-machine.md`
- `review-master/references/sql-write-recipes.md`

## 核心约束

- 数据库写入前显式执行 `PRAGMA foreign_keys = ON`
- 优先复用标准 SQL recipe，不要临场发明写法
- 只读视图可以读取，但不得作为写入目标
- 原始意见块到 canonical atomic item 的拆分、合并与去重由 LLM 主导，不由脚本替代
- 有 `pending_user_confirmations` 时先请求确认
- 有 `global_blockers` 时先请求补材或澄清
- 最终 response letter 必须按原始 `thread_id` 顺序回映，而不是按 `comment_id` 直接展开
- `01-agent-resume.md` 是 Agent 恢复视图，不是用户主确认工件
- `instruction_payload.resume_packet` 与 `01-agent-resume.md` 是恢复协议的正式入口
- Stage 6 必须以 `working_manuscript` 与 revision audit 为正式闭环路径

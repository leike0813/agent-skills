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

## 输出

### 运行时输出

artifact workspace 根目录固定包含：

- `review-master.db`
- `agent-resume.md`
- `manuscript-structure-summary.md`
- `raw-review-thread-list.md`
- `atomic-review-comment-list.md`
- `thread-to-atomic-mapping.md`
- `atomic-comment-workboard.md`
- `style-profile.md`
- `action-copy-variants.md`
- `response-letter-outline.md`
- `export-patch-plan.md`
- `response-letter-table-preview.md`
- `response-letter-table-preview.tex`
- `supplement-intake-plan.md`
- `final-assembly-checklist.md`
- `response-strategy-cards/{comment_id}.md`

### 最终输出

- `marked_manuscript`
  - 使用 `changes` 宏包标注修改点的稿件
- `clean_manuscript`
  - 最终无修改标注的稿件
- `response_markdown`
  - Point-to-point 表格形式的 Markdown 回复信
- `response_latex`
  - Point-to-point 表格形式的 LaTeX 回复信

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

这个正式称呼在本 skill 中是唯一有效称呼。不要再把它称为 `validator`、`校验脚本` 或其他含糊名称。

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
2. `workflow_state` 只保存在数据库中，不再渲染成单独的 Markdown 文件。
3. 运行时 Markdown 文件全部是只读渲染视图，Agent 不得直接编辑。
4. 每次数据库写入后，都必须重新运行 `gate-and-render` 核心脚本。
5. `gate-and-render` 核心脚本负责四件事：
   - 状态门禁校验
   - 只读视图重渲染
   - 输出 `instruction_payload`
   - 输出并重渲染恢复包（`instruction_payload.resume_packet` 与 `agent-resume.md`）
6. 若脚本给出 `repair_sequence`，必须先修数据库真源，再重新运行脚本。
7. 若存在待确认事项或 blocker，不得绕过状态机继续推进。
8. 首次调用、跨 Session 恢复和上下文压缩后的继续执行，全部走同一条“先恢复，后执行”协议。

## 核心数据模型

本 skill 采用三层 comment/workflow 索引：

1. 原始审稿意见块：`raw_review_threads`
   - 这是最终 response letter 的正式索引层
   - 一条原始 reviewer 条目可以映射到多个 canonical atomic item
2. 规范化原子意见：`atomic_comments`
   - 这是内部执行真源索引层
   - 不同 reviewer 的重复意见应在这一层真正合并
3. response letter 聚合层：`response_thread_resolution_links` 与 `response_thread_rows`
   - 最终回复信必须回到原始 `thread_id` 顺序输出
   - 最终导出必须使用 thread-level response row，而不是 `comment_id` 扁平列表

关键关系全部表化，不使用 JSON/TEXT 多值列：

- `raw_thread_atomic_links`
- `atomic_comment_source_spans`
- `atomic_comment_target_locations`
- `atomic_comment_analysis_links`
- `strategy_action_target_locations`
- `response_thread_resolution_links`

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
  -> stage_6 风格画像 / 版本生成 / thread-level row 组装 / 双阶段导出
       └─ 若 export gates 未闭环 -> 回到数据库修订 -> 重新运行 gate-and-render 核心脚本

每次正式写入：
 SQL write -> review-master.db
           -> review-master/scripts/gate_and_render_workspace.py
           -> instruction_payload + resume_packet + agent-resume.md
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
3. 读取 `agent-resume.md`
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
- 按统一恢复入口读取 `instruction_payload.resume_packet` 与 `agent-resume.md`
- 读取 `manuscript_source`、`review_comments_source`
- 吸收 `editor_letter_source` 与 `user_notes`
- 判断主入口是单文件还是 LaTeX 工程目录
- 初始化 artifact workspace
- 写入 `resume_brief`
- 视情况写入 `resume_open_loops`
- 视情况写入 `resume_recent_decisions`
- 视情况写入 `resume_must_not_forget`

操作摘要：

- 先检查第三方依赖；若不满足，先问用户是否批准安装
- 单文件主稿通常不需要 `detect_main_tex.py`；LaTeX 工程目录优先调用它辅助判断主入口
- 若主入口不唯一，必须停下来问用户
- workspace 初始化后，不允许直接跳入 Stage 2 写库，必须先完成 bootstrap/continuation resume 对齐
- 阶段一的产物不是“写了多少内容”，而是“入口已明确、workspace 已就绪、恢复包已读完、下一步动作已清楚”

阻断条件：

- 缺必需输入
- manuscript 主入口无法唯一确定
- 运行环境缺依赖且用户未批准安装
- `gate-and-render` 返回 repair 或阻断性门禁问题

完成定义：

- 主入口明确
- workspace 成功初始化
- `gate-and-render` 返回可继续
- `instruction_payload.resume_packet` 与 `agent-resume.md` 已被读取并对齐

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
- 阶段二结束时，`manuscript-structure-summary.md` 应足以支撑后续 thread 抽取与 atomic 映射

阻断条件：

- `manuscript_sections` 或 `manuscript_claims` 明显缺失
- 章节层级无法支撑后续定位
- 高风险修改区尚未识别
- 仍存在足以影响 Stage 3 的结构性疑问

完成定义：

- `manuscript_summary`、`manuscript_sections`、`manuscript_claims` 已入库
- `manuscript-structure-summary.md` 已重渲染
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
- 更新 `resume_brief`
- 补充 `resume_recent_decisions`
- 补充 `resume_must_not_forget`

操作摘要：

- Stage 3 先保留 raw thread 层，再进入 canonical atomic 建模，不能跳过中间映射层
- reviewer / editor 原始条目边界先按原文自然条目保留，不在 raw thread 层做语义合并
- canonical atomic item 必须满足：可独立回应、可独立制定修改动作、可独立判定完成
- 跨 reviewer 的重复意见默认采用保守合并：只有核心问题和期望动作都基本一致时才合并
- 若诉求角度、修改范围或所需证据明显不同，则保留为不同 atomic item
- 合并后的依据必须写入 `atomic_comment_source_spans`

阻断条件：

- raw thread 边界无法稳定识别
- 是否合并存在高风险歧义且无法仅凭现有材料判断
- editor 要求与 reviewer 要求冲突，无法直接决定建模方式
- 存在 `thread_id` 未映射任何 `comment_id` 或 `comment_id` 未被任何 `thread_id` 引用

完成定义：

- `raw_review_threads` 已稳定
- `atomic_comments` 已形成 canonical atomic item 集合
- 每个 `thread_id` 至少映射到一个 `comment_id`
- 每个 `comment_id` 至少被一个 `thread_id` 引用
- `atomic_comment_source_spans` 足以解释每个合并来源
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
- 向用户展示 `atomic-comment-workboard.md` 与 `thread-to-atomic-mapping.md`

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
- 写入 `supplement_intake_items`
- 写入 `supplement_landing_links`
- 写入 `strategy_action_manuscript_drafts`
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
- 默认必须先完成逐条策略确认，再进入 manuscript draft 和 response draft
- Stage 4 的总确认不能替代 Stage 5 的局部执行确认
- 若存在 evidence gap，应显式进入 blocker 路径，请求补材或澄清
- 每轮补材必须形成文件级接收判定（accepted/rejected + rationale）
- 被接收的补材必须映射到 `comment_id/action_order/location_order`，并在 `supplement-intake-plan.md` 可追溯
- 只有当策略卡、证据判断、manuscript draft、response draft 以及一一对应检查都完成后，当前条目才允许标记完成
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

### 6. 阶段六：风格画像、版本生成、thread-level 成文与双阶段导出

做什么：

- 写入 `style_profiles`
- 写入 `style_profile_rules`
- 写入 `action_copy_variants`
- 写入 `selected_action_copy_variants`
- 写入 `response_thread_resolution_links`
- 写入 `response_thread_rows`
- 写入 `export_patch_sets`
- 写入 `export_patches`
- 写入 `export_artifacts`
- 更新 `resume_brief`
- 清理或收缩 `resume_open_loops`
- 记录最终 `resume_recent_decisions`
- 先向用户展示：
  - `style-profile.md`
  - `action-copy-variants.md`
  - `response-letter-outline.md`
  - `export-patch-plan.md`
  - `response-letter-table-preview.md`
  - `response-letter-table-preview.tex`
  - `final-assembly-checklist.md`
- 先导出 marked manuscript
- 用户最终确认后再导出 clean manuscript、Markdown response letter 与 LaTeX response letter

操作摘要：

- Stage 6 先做全局风格画像，再做位置级的三版本落稿文本生成，不能直接从 Stage 5 草案跳到最终文案
- 风格画像必须同时覆盖 manuscript 与 response letter 两类文本，并明确去 AI 化约束
- Stage 5 已经锁定策略、修改方向、证据判断和草案边界；Stage 6 只负责把这些既定方案转成最终成文文案
- 每个 `strategy_card_actions` 的每个 `target_location` 默认都要生成 3 个 manuscript-side 最终落地文案版本
- 用户完成 manuscript 最终文案选择后，才能按原始 `thread_id` 聚合最终 4 列 point-to-point response row
- response letter 在 Stage 6 只有单一路径成文，不做 action-level 的三选一
- 在导出 manuscript 之前，必须先在 `review-master.db` 中写实 `export_patch_sets` 与 `export_patches`
- `export_manuscript_variants.py` 只负责复制导出副本，并按显式锚点补丁执行替换/插入；语义判断和最终文案生成仍由 Agent 完成
- 导出必须分两步：
  - 先导出 marked manuscript
  - 最终确认后再导出 clean manuscript 与双格式 response letter
- marked manuscript 必须是完整稿件，只是修改位置带 `changes` 宏包标记
- clean manuscript 必须与用户确认后的 marked manuscript 内容一致，只去掉标记
- `response_latex` 必须是带 front matter 的完整可编译 LaTeX 文件，而不是表格正文片段

阻断条件：

- style profile 缺失
- 某个 action 的某个 `target_location` 没有达到 3 个 manuscript 最终文案版本
- 用户尚未完成版本选择
- thread-level row 尚未完整
- final checklist 仍有关键 `TBD`、blocker 或未闭环导出门禁
- 用户尚未完成最终确认

完成定义：

- style profiles 与规则已稳定
- 每个 action 的每个 `target_location` 都已生成 3 个最终落稿文本版本，且用户已完成逐位置选择
- 每个 `thread_id` 都有最终 response row
- marked manuscript 已导出并复核
- clean manuscript、Markdown response letter、LaTeX response letter 已导出到独立输出位置

脚本：

- `review-master/scripts/gate_and_render_workspace.py`
- `review-master/scripts/export_manuscript_variants.py`

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
- `agent-resume.md` 是 Agent 恢复视图，不是用户主确认工件
- `instruction_payload.resume_packet` 与 `agent-resume.md` 是恢复协议的正式入口
- Stage 6 必须先导出 marked manuscript，再在最终确认后导出 clean manuscript 与双格式 response letter

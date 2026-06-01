---
name: paper-drafter
description: Guide an agent through rigorous, interactive academic paper drafting from research intent to chapter-level manuscript sections. Use when the user wants to plan, outline, draft, or progressively refine a scholarly paper through staged research design, evidence checks, style profiling, and section-by-section drafting rather than one-shot text generation.
---

# paper-drafter

## 目标

- 帮助用户以交互式、多阶段方式形成学术论文初稿，而不是一次性生成全文
- 将研究意图、宏观图景、研究方案、论文大纲、章节写作方案、证据计划、风格画像和章节草稿写入 SQLite 真源
- 通过 `gate-and-render` 持续渲染只读 Markdown 视图，支持长程协作、上下文压缩和跨 session 恢复
- 在正式起草前强制经过用户确认、证据缺口、风格画像和章节提纲门禁

## 非目标

- 不一步到位生成完整论文
- 不基于臆测补全实验结果、数据、访谈、史料、引文、法律材料、伦理审批、图表或来源文件
- 不用脚本替代研究设计、创新性判断、证据充分性判断、风格画像或正文写作
- 不直接编辑只读 Markdown 视图来推进状态
- 不把领域写作指南当作模板机械套用；指南只用于校准学科范式和写作标准

## 输入

本 skill 可以从不完整信息启动，但在 `intake` 未确认前不得进入研究方案或大纲阶段。

### 必需输入

在 `intake` 可确认前，必须拿到或明确标记暂无：

- 研究主题、暂定标题或预期贡献
- canonical paper domain 与 research area
- `document_language`：正文最终使用语言
- `working_language`：用户交互、中间视图和诊断使用语言
- 可用输入来源清单，例如笔记、数据描述、图表、引用、前稿、来源文件或 inline text
- 约束、禁止假设、隐私边界和用户不希望作出的 claim

### 可选输入

- 目标期刊、会议、课程、毕业论文或其它 target venue
- 论文类型、格式限制、目标读者或审稿标准
- 用户已有 rough outline、图表、表格、实验日志、访谈材料、法条、案例、代码、证明草稿或 source files
- 用户过往写作样本、用户改写样例和显式风格偏好

若用户提供 existing artifact workspace，不要重新从对话记忆收集 intake；先走统一恢复入口。

## 语言上下文

- `document_language` 指最终 manuscript prose 的语言
- `working_language` 指用户交互、计划、诊断、resume 和只读中间视图的语言
- 用户提供的证据、引用、来源摘录和 citation string 默认保留原语言，除非用户要求翻译
- 阶段 payload 与只读视图默认使用 `working_language`
- 正文 section draft 默认使用 `document_language`，除非用户明确要求用其它语言先写 planning draft

Stage 1 必须确认 `document_language` 与 `working_language`，初始化 workspace 时必须传入这两个值。

## 运行时输出

artifact workspace 根目录固定包含：

- `paper-drafter.db`
  - SQLite 运行时唯一真源
- `01-agent-resume.md`
  - 当前 gate 状态、下一步动作、阻断点和恢复摘要
- `02-intake-and-domain.md`
  - intake、领域、来源、语言和约束
- `03-macro-picture.md`
  - 研究问题、gap、贡献、边界和风险
- `04-research-plan.md`
  - 已确认研究方案
- `05-outline.md`
  - 已确认论文大纲与各 section role
- `06-section-writing-plan.md`
  - 逐章节写作方案、材料、图表和依赖
- `07-evidence-board.md`
  - evidence item、evidence gap、严重程度和关闭状态
- `08-style-profile.md`
  - 用户风格画像、样本依据和写作规则
- `09-drafting-board.md`
  - draft unit、draft status、blocker 和 revision 状态
- `10-reference-route-board.md`
  - 已记录的参考文档导航路线
- `11-manuscript-preview.md`
  - 从 DB draft versions 渲染出的 manuscript preview
- `sections/<section_id>-outline.md`
  - 单章节提纲只读视图
- `sections/<section_id>-draft.md`
  - 单章节最新草稿只读视图

所有 Markdown 视图都是 renderer-owned read-only views。缺失或过期时运行 `gate-and-render`，不得手工重建或手工编辑后当作状态。

## 核心运行契约

1. SQLite 真源固定为 artifact workspace 根目录下的 `paper-drafter.db`。
2. 所有正式语义成果必须先由 LLM 形成结构化 JSON payload，再通过 `submit_stage_payload.py` 写入 DB。
3. `gate-and-render` 是唯一合法下一步判定入口。
4. 每次正式写库后必须读取新的 gate 结果；如果中断或不确定，重新运行 `gate-and-render`。
5. 只读 Markdown 视图只用于恢复、审阅和协作展示，不是写入入口。
6. 若 gate 返回 `blockers`、`pending_user_confirmations` 或 `repair_sequence`，不得继续后续阶段。
7. 若存在 open evidence gap，不得起草依赖该证据的 section。
8. 若 DB 中没有某项确认或语义成果，不得凭聊天记忆假定它已完成。

合法 `next_action`：

- `collect_intake`
- `confirm_macro_picture`
- `confirm_research_plan`
- `confirm_outline`
- `confirm_section_writing_plan`
- `plan_evidence`
- `intake_evidence`
- `build_style_profile`
- `plan_section_outline`
- `draft_section`
- `revise_section`
- `final_consistency_check`
- `completed`

合法 `stage_id`：

- `intake`
- `macro_picture`
- `research_plan`
- `outline`
- `section_writing_plan`
- `evidence_plan`
- `evidence_intake`
- `style_profile`
- `section_outline`
- `section_draft`
- `confirmation`
- `reference_route`

正式命名、DB 表、视图名和 enum 含义见 [workflow-glossary.md](references/workflow-glossary.md)。

## 核心脚本

所有 Python 命令使用：

```bash
python <script> ...
```

初始化 workspace：

```bash
python scripts/init_artifact_workspace.py \
  --artifact-root <ARTIFACT_ROOT> \
  --document-language <language> \
  --working-language <language>
```

恢复、gate 与渲染：

```bash
python scripts/gate_and_render_workspace.py \
  --artifact-root <ARTIFACT_ROOT>
```

提交阶段 payload：

```bash
python scripts/submit_stage_payload.py \
  --artifact-root <ARTIFACT_ROOT> \
  --stage <stage_id> \
  --payload-file <payload.json>
```

导航领域写作指南：

```bash
python scripts/reference_guide.py nav \
  --domain computational-algorithm-data-driven \
  --drafting-phase section-drafting \
  --paper-section method
```

`reference_guide.py` 只负责参考文档渐进披露。它不写 DB、不判断证据、不生成研究方案、不起草正文。重要 route 只有在后续恢复需要看见时才用 `--stage reference_route` 记录。

## 状态机图示

```text
环境确认
  -> stage_1 collect_intake
  -> stage_2 confirm_macro_picture
  -> stage_3 confirm_research_plan
  -> stage_4 confirm_outline
  -> stage_5 confirm_section_writing_plan
  -> stage_6 plan_evidence
       └─ 若 evidence gap open -> intake_evidence -> 回到 stage_6
  -> stage_7 build_style_profile
  -> stage_8 plan_section_outline
       -> draft_section
       -> revise_section when requested
       -> repeat for every confirmed outline section
  -> stage_9 final_consistency_check
  -> completed

每次正式写入：
 semantic payload -> submit_stage_payload.py
                  -> paper-drafter.db
                  -> gate-and-render
                  -> refreshed read-only views + next_action
```

## 总体执行流程

### 0. 环境确认

做什么：

- 判断用户是要新建 `paper-drafter` workspace，还是继续已有 workspace
- 确认 artifact root 的位置或让用户提供
- 确认 `document_language` 与 `working_language`
- 确认当前任务确实需要本 staged drafting workflow，而不是简单写一段文字

操作摘要：

- 若用户提供已有 artifact root，先检查其中是否存在 `paper-drafter.db`
- 若 DB 存在，跳到 `0.5 统一恢复入口`
- 若 DB 不存在，先收集语言上下文和初始论文信息，再初始化 workspace
- 若用户只想快速生成一段 introduction、abstract 或润色文字，应说明本 skill 是长程分阶段起草流程，并询问是否建立 workspace

阻断条件：

- artifact root 不明确且用户没有授权选择
- `document_language` 或 `working_language` 无法确认
- 用户目标只是单次文本生成且不希望建立 workspace

完成定义：

- 明确是新建还是恢复
- artifact root 明确
- 语言上下文明确
- 下一步是初始化 workspace 或统一恢复入口

脚本：

- `paper-drafter/scripts/init_artifact_workspace.py`
- `paper-drafter/scripts/gate_and_render_workspace.py`

参考文档：

- [helper-scripts.md](references/helper-scripts.md)
- [workflow-state-machine.md](references/workflow-state-machine.md)
- [skill-runtime-digest.md](assets/runtime/skill-runtime-digest.md)

### 0.5 统一恢复入口

做什么：

- 从 DB 和 rendered views 恢复当前状态
- 确认 `next_action`、blocker、pending confirmation 和 repair sequence
- 只执行 gate 返回的下一步，不凭聊天历史继续

操作摘要：

1. 运行 `gate-and-render`
2. 读取 stdout JSON
3. 读取 `01-agent-resume.md`
4. 读取 [workflow-state-machine.md](references/workflow-state-machine.md)
5. 读取 `next_action` 对应 stage playbook
6. 读取相关只读视图
7. 只有完成恢复对齐后，才允许形成或提交 payload

阻断条件：

- `gate-and-render` 返回 `ok=false`
- `repair_sequence` 非空
- schema validation failure
- `blockers` 或 `pending_user_confirmations` 需要用户处理

完成定义：

- 当前 `next_action` 已明确
- 当前阶段主视图已读取
- 当前 stage playbook 已读取
- 若需要写入，payload recipe 已读取

脚本：

- `paper-drafter/scripts/gate_and_render_workspace.py`

参考文档：

- [workflow-state-machine.md](references/workflow-state-machine.md)
- [workflow-glossary.md](references/workflow-glossary.md)
- [helper-scripts.md](references/helper-scripts.md)
- [payload-and-sql-recipes.md](references/payload-and-sql-recipes.md)

### 1. 阶段一：intake 与领域确认

做什么：

- 收集并确认研究主题、领域、研究方向、来源材料、语言上下文和约束
- 建立 `paper_domain_profile` 与 `input_sources`
- 为后续参考文档路由选择 canonical domain

操作摘要：

- 不要急于提出研究方案；先把用户真正要写什么、有什么材料、不能假设什么问清楚
- 若领域分类不确定，调用 `reference_guide.py taxonomy`，只披露可能相关的 taxonomy section
- 对每个 input source 写明来源类型、路径或 inline text、摘要和可用性
- 向用户展示 intake profile，要求确认或修正
- 用户确认后提交 `intake` payload

阻断条件：

- 主题仍只是宽泛方向，无法形成 research area
- canonical domain 不明确且会影响写作标准
- 语言上下文未确认
- 来源材料清单缺失且用户没有明确声明暂无材料
- 约束、隐私边界或禁止假设不清

完成定义：

- `paper_domain_profile.confirmed = true`
- `input_sources` 已记录现有材料或明确暂无材料
- `02-intake-and-domain.md` 可读且足以支持 macro picture
- gate 不再返回 `collect_intake`

脚本：

- `paper-drafter/scripts/reference_guide.py taxonomy`
- `paper-drafter/scripts/submit_stage_payload.py --stage intake`
- `paper-drafter/scripts/gate_and_render_workspace.py`

参考文档：

- [stage-1-intake-and-macro.md](references/stage-1-intake-and-macro.md)
- [taxonomy.md](references/taxonomy.md)
- [payload-and-sql-recipes.md](references/payload-and-sql-recipes.md)

### 2. 阶段二：论文宏观图景

做什么：

- 基于已确认 intake 建立论文宏观图景
- 明确 research question、gap、method/material path、contribution、boundaries 和 risks
- 让用户确认 agent 对论文方向的理解是否正确

操作摘要：

- 先读取 `02-intake-and-domain.md`
- 参考 [general_framework.md](references/general_framework.md) 和必要的 domain guide
- 将用户宽泛想法压缩成可讨论的 research question
- 主动暴露弱假设、证据不足和贡献边界
- 向用户展示 macro picture card，要求确认、修正或重定方向
- 用户确认后提交 `macro_picture` payload

阻断条件：

- research question 不可回答或过宽
- gap 只是泛泛表述，无法被论证
- contribution 超出可用或计划中的证据路径
- method/material path 无法支撑 research question
- 用户尚未确认关键方向

完成定义：

- `macro_picture.confirmed = true`
- `03-macro-picture.md` 明确呈现问题、gap、方法路径、贡献、边界和风险
- gate 不再返回 `confirm_macro_picture`

脚本：

- `paper-drafter/scripts/reference_guide.py nav`
- `paper-drafter/scripts/submit_stage_payload.py --stage macro_picture`
- `paper-drafter/scripts/gate_and_render_workspace.py`

参考文档：

- [stage-1-intake-and-macro.md](references/stage-1-intake-and-macro.md)
- [general_framework.md](references/general_framework.md)
- [execution-patterns-and-output-templates.md](references/execution-patterns-and-output-templates.md)

### 3. 阶段三：研究方案

做什么：

- 把 macro picture 转化为可执行、可论证、可被证据支持的 research plan
- 与用户讨论创新性、可行性、方法路线、证据策略和 claim scope
- 明确哪些 claim 需要后续证据支持，哪些 claim 必须保持保守

操作摘要：

- 读取 `03-macro-picture.md`
- 对 research question、novelty、method design、evidence strategy 做语义压力测试
- 若用户提供的创新点不成立，要直接指出并给出可收缩版本
- 若方法路线有多个合理选项，说明 tradeoff 并请求用户选择
- 输出 research plan card 与 risk/fallback note
- 用户确认后提交 `research_plan` payload

阻断条件：

- novelty 只是口号或普通应用，不能支撑论文贡献
- method design 与 claim 不匹配
- evidence strategy 无法支撑最强 claim
- claim scope 没有边界
- 用户未确认方案或关键 tradeoff

完成定义：

- `research_plan.confirmed = true`
- `04-research-plan.md` 足以指导 outline、section planning 和 evidence planning
- gate 不再返回 `confirm_research_plan`

脚本：

- `paper-drafter/scripts/reference_guide.py nav`
- `paper-drafter/scripts/submit_stage_payload.py --stage research_plan`
- `paper-drafter/scripts/gate_and_render_workspace.py`

参考文档：

- [stage-2-research-plan-and-outline.md](references/stage-2-research-plan-and-outline.md)
- [general_framework.md](references/general_framework.md)
- [execution-patterns-and-output-templates.md](references/execution-patterns-and-output-templates.md)

### 4. 阶段四：论文大纲

做什么：

- 基于 confirmed research plan 制定论文大纲
- 确定稳定 `section_id`、章节顺序、层级、标题、argument role 和 expected evidence
- 让用户确认二级结构和章节功能

操作摘要：

- 读取 `04-research-plan.md`
- 根据 domain guide 判断常见结构，但不得机械套模板
- 每个 section 必须说明它在论证链中的工作，而不是只写标题
- expected evidence 必须能被 Stage 6 evidence planning 继续追踪
- 向用户展示 outline review board，要求确认或调整
- 用户确认后提交 `outline` payload

阻断条件：

- section role 为空或只是泛泛描述
- outline 与 research plan 不一致
- 某章节暗含未批准的强 claim
- section_id 不稳定或将导致后续引用混乱
- 用户未确认大纲

完成定义：

- 至少有一组 confirmed `outline_sections`
- `05-outline.md` 显示章节顺序、角色和 expected evidence
- gate 不再返回 `confirm_outline`

脚本：

- `paper-drafter/scripts/reference_guide.py nav`
- `paper-drafter/scripts/submit_stage_payload.py --stage outline`
- `paper-drafter/scripts/gate_and_render_workspace.py`

参考文档：

- [stage-2-research-plan-and-outline.md](references/stage-2-research-plan-and-outline.md)
- [payload-and-sql-recipes.md](references/payload-and-sql-recipes.md)

### 5. 阶段五：逐章节写作方案

做什么：

- 将每个 confirmed outline section 转化为 section writing plan
- 明确每章的 content logic、key claims、materials、expected visuals 和 dependencies
- 在 evidence planning 前暴露章节之间的依赖和潜在证据需求

操作摘要：

- 逐个读取 `05-outline.md` 中 confirmed section
- 对每个 section 写出它要推进的 section-specific argument
- 将 key claims 和所需材料说清楚，避免后续只凭标题写作
- 对 expected visuals 说明其论证功能，不写装饰性图表
- 可以批量提交多个 plan，但前提是用户已经审阅整批内容
- 用户确认后提交 `section_writing_plan` payload

阻断条件：

- 某个 confirmed outline section 没有 confirmed writing plan
- plan 只写 topic，没有 claim/evidence/dependency logic
- section 会改变 research plan 但未回到前序阶段确认
- dependencies 不清，导致后续章节无法稳定衔接

完成定义：

- 每个 confirmed outline section 都有 confirmed `section_writing_plans`
- `06-section-writing-plan.md` 可用于生成 evidence plan
- gate 不再返回 `confirm_section_writing_plan`

脚本：

- `paper-drafter/scripts/reference_guide.py nav`
- `paper-drafter/scripts/submit_stage_payload.py --stage section_writing_plan`
- `paper-drafter/scripts/gate_and_render_workspace.py`

参考文档：

- [stage-3-section-writing-plan.md](references/stage-3-section-writing-plan.md)
- [execution-patterns-and-output-templates.md](references/execution-patterns-and-output-templates.md)

### 6. 阶段六：证据计划与证据 intake

做什么：

- 根据 section writing plans 建立 evidence board
- 识别每个 key claim 的证据需求和 evidence gap
- 接收用户补充证据，判断其真正支持哪些 claim
- 关闭或 dismiss gap，但不得用措辞掩盖证据不足

操作摘要：

- 读取 `06-section-writing-plan.md`
- 对每个 key claim 判断需要数据、实验、观察、访谈、文本、法条、案例、证明、引用、图表还是用户事实说明
- 对缺失、部分支持或不明确的证据创建 evidence gap
- 高/中严重度 gap 必须向用户解释其阻断影响
- 用户补充材料后，先判断支持范围，再写 evidence item
- 只关闭真正被证据满足的 gap；只有 claim 被删除、收窄、延后或明确接受为 scope 外时才 dismiss

阻断条件：

- 尚未写入 evidence plan
- 存在 open evidence gap
- 用户希望继续但缺口仍支撑不了 planned claim
- evidence item 未映射到 section 或 claim
- dismiss gap 会改变 claim scope 但未获用户确认

完成定义：

- 至少写入一次 `evidence_plan`
- 所有 blocking gap 均为 `closed` 或 `dismissed`
- `07-evidence-board.md` 清楚展示证据状态
- gate 不再返回 `plan_evidence` 或 `intake_evidence`

脚本：

- `paper-drafter/scripts/submit_stage_payload.py --stage evidence_plan`
- `paper-drafter/scripts/submit_stage_payload.py --stage evidence_intake`
- `paper-drafter/scripts/gate_and_render_workspace.py`

参考文档：

- [stage-4-evidence-and-style.md](references/stage-4-evidence-and-style.md)
- [general_framework.md](references/general_framework.md)
- [execution-patterns-and-output-templates.md](references/execution-patterns-and-output-templates.md)

### 7. 阶段七：用户风格画像

做什么：

- 在正式 drafting 前建立用户风格画像
- 使用用户样本、用户改写、显式偏好和 anti-AI polishing 约束形成 style profile
- 让用户确认写作风格规则

操作摘要：

- 先询问用户是否能提供过往写作样本
- 若样本不足，可基于研究方案生成少量示例段落，让用户用自己的语言转写
- 分析用户的句式、段落节奏、术语习惯、语气、过渡方式和禁忌表达
- 输出 style profile card，包含 do rules、don't rules、tone terms 和依据
- 用户确认后提交 `style_profile` payload

阻断条件：

- 用户尚未确认 style profile
- 样本与用户显式偏好冲突且未解决
- 没有样本却生成了过强的个性化画像
- 画像会鼓励 unsupported claim 或 AI 味套话

完成定义：

- `style_profile.confirmed = true`
- `08-style-profile.md` 足以指导 section drafting
- gate 不再返回 `build_style_profile`

脚本：

- `paper-drafter/scripts/submit_stage_payload.py --stage style_profile`
- `paper-drafter/scripts/gate_and_render_workspace.py`

参考文档：

- [stage-4-evidence-and-style.md](references/stage-4-evidence-and-style.md)
- [anti-ai_polishing_guide.md](references/anti-ai_polishing_guide.md)
- [execution-patterns-and-output-templates.md](references/execution-patterns-and-output-templates.md)

### 8. 阶段八：逐章节提纲、起草与修订

做什么：

- 逐个 section unit 制定三级以上细化提纲
- 在 confirmed section outline 基础上起草正文
- 根据用户反馈或 gate blocker 写入新 draft version
- 让 `11-manuscript-preview.md` 持续反映 DB draft versions

操作摘要：

- gate 返回 `plan_section_outline` 时，先为当前 section 写 section-level outline，不写正文
- section outline 必须包含 section thesis、subclaims、evidence placement、paragraph sequence、figure/table/citation hooks 和 transitions
- 用户确认 section outline 后提交 `section_outline`
- gate 返回 `draft_section` 时，读取 research plan、section plan、evidence board、style profile 和 section outline
- 起草时只能写 evidence scope 内的 claim；未解决 citation/figure/data/proof/source needs 必须显式标记
- gate 返回 `revise_section` 时，先判断 revision 是否改变 claim/evidence/scope；必要时请用户确认 revision direction
- revision 通过新的 `section_draft` payload 写入，不编辑 rendered draft

阻断条件：

- 当前 section unit 未确认
- open evidence gap 阻断该 section
- style profile 未确认
- section outline 太浅，无法支撑正文
- revision 会改变 research plan 或 claim scope，但未回到相应阶段处理

完成定义：

- 每个 confirmed outline section 都有 confirmed draft unit
- 每个 confirmed draft unit 至少有一条 draft version
- requested revisions 已写为新版本
- `09-drafting-board.md` 与 `11-manuscript-preview.md` 已重渲染
- gate 可进入 `final_consistency_check`

脚本：

- `paper-drafter/scripts/reference_guide.py nav`
- `paper-drafter/scripts/submit_stage_payload.py --stage section_outline`
- `paper-drafter/scripts/submit_stage_payload.py --stage section_draft`
- `paper-drafter/scripts/gate_and_render_workspace.py`

参考文档：

- [stage-5-drafting-and-finalization.md](references/stage-5-drafting-and-finalization.md)
- [anti-ai_polishing_guide.md](references/anti-ai_polishing_guide.md)
- [execution-patterns-and-output-templates.md](references/execution-patterns-and-output-templates.md)

### 9. 阶段九：最终一致性检查

做什么：

- 检查 macro picture、research plan、outline、section plans、evidence board、style profile 和 drafts 是否一致
- 找出未闭合 claim、隐藏 placeholder、证据不匹配、风格不一致和超范围结论
- 请求用户确认最终一致性

操作摘要：

- 读取 `11-manuscript-preview.md`，但不要把它当成可编辑源
- 逐项核对 research question 是否被回答、每个 major claim 是否有证据路径、limitations 是否可见
- 检查所有图表、引用、数据、审批、来源材料是否真实存在或显式标记 unresolved
- 输出 final consistency report
- 用户确认后提交 `confirmation` payload，`target_type=final_consistency`

阻断条件：

- 任一 major claim 无证据支持
- draft 与 research plan 或 outline 冲突
- unresolved placeholder 被伪装成完成文本
- 用户未确认 final consistency

完成定义：

- final consistency confirmation 已写入 `user_confirmations`
- gate 返回 `next_action=completed`

脚本：

- `paper-drafter/scripts/submit_stage_payload.py --stage confirmation`
- `paper-drafter/scripts/gate_and_render_workspace.py`

参考文档：

- [stage-5-drafting-and-finalization.md](references/stage-5-drafting-and-finalization.md)
- [anti-ai_polishing_guide.md](references/anti-ai_polishing_guide.md)
- [execution-patterns-and-output-templates.md](references/execution-patterns-and-output-templates.md)

### 10. completed

做什么：

- 停止必需 workflow
- 向用户说明 workspace 已完成，以及最终可读视图在哪里
- 若用户请求继续修改，重新运行 `gate-and-render`，按返回动作处理 revision 或前序修订

操作摘要：

- 不因为 `11-manuscript-preview.md` 存在就提前宣布完成
- 只有 `next_action=completed` 才表示 workflow 完成
- 后续新增材料、改研究方案、改大纲或改章节，都必须回到 DB/gate 路径

阻断条件：

- gate 未返回 `completed`
- final consistency 未确认
- 用户指出仍有未解决问题

完成定义：

- `gate-and-render` 返回 `next_action=completed`
- `01-agent-resume.md` 与 `11-manuscript-preview.md` 已重渲染

脚本：

- `paper-drafter/scripts/gate_and_render_workspace.py`

参考文档：

- [workflow-state-machine.md](references/workflow-state-machine.md)

## Reference Loading Guide

默认先读本文件；只在当前 gate、阶段动作或写入前需要时读取 reference。

| Need | Read |
| --- | --- |
| runtime names、enum、视图和 DB 表含义 | [workflow-glossary.md](references/workflow-glossary.md) |
| gate loop、状态迁移、blocker、repair、resume 顺序 | [workflow-state-machine.md](references/workflow-state-machine.md) |
| 用户交互话术、阶段卡片、确认模板、输出模板 | [execution-patterns-and-output-templates.md](references/execution-patterns-and-output-templates.md) |
| intake、领域分类、macro picture | [stage-1-intake-and-macro.md](references/stage-1-intake-and-macro.md) |
| research plan 与 outline | [stage-2-research-plan-and-outline.md](references/stage-2-research-plan-and-outline.md) |
| section writing plan | [stage-3-section-writing-plan.md](references/stage-3-section-writing-plan.md) |
| evidence planning、evidence intake、style profile | [stage-4-evidence-and-style.md](references/stage-4-evidence-and-style.md) |
| section outline、drafting、revision、final consistency | [stage-5-drafting-and-finalization.md](references/stage-5-drafting-and-finalization.md) |
| payload 字段、合法 `stage_id`、常见写入错误 | [payload-and-sql-recipes.md](references/payload-and-sql-recipes.md) |
| 脚本命令、stdout、失败处理 | [helper-scripts.md](references/helper-scripts.md) |
| 上下文压缩后的短恢复摘要 | [skill-runtime-digest.md](assets/runtime/skill-runtime-digest.md) |
| 领域 taxonomy | [taxonomy.md](references/taxonomy.md) |
| 通用科研论文标准 | [general_framework.md](references/general_framework.md) |
| 理工科 Introduction / Related Work | [scientific_introduction_related_work_writing_guide_zh.md](references/scientific_introduction_related_work_writing_guide_zh.md) |
| 去 AI 化润色与最终一致性 | [anti-ai_polishing_guide.md](references/anti-ai_polishing_guide.md) |

领域写作指南通过 `reference_guide.py` 渐进披露，避免一次性打开全部长文档。

| Canonical domain | Guide |
| --- | --- |
| `experimental-observational-natural-science` | [experimental_observational_natural_science_writing_guide.md](references/experimental_observational_natural_science_writing_guide.md) |
| `engineering-system-design` | [engineering_system_design_writing_guide.md](references/engineering_system_design_writing_guide.md) |
| `computational-algorithm-data-driven` | [computational_algorithm_data_driven_writing_guide.md](references/computational_algorithm_data_driven_writing_guide.md) |
| `mathematical-theory-proof` | [mathematical_theory_proof_writing_guide.md](references/mathematical_theory_proof_writing_guide.md) |
| `medical-clinical-public-health` | [medical_clinical_public_health_writing_guide.md](references/medical_clinical_public_health_writing_guide.md) |
| `quantitative-social-behavioral-science` | [quantitative_social_and_behavioral_science_writing_guide.md](references/quantitative_social_and_behavioral_science_writing_guide.md) |
| `qualitative-interpretive-social-science` | [qualitative_interpretive_social_science_writing_guide.md](references/qualitative_interpretive_social_science_writing_guide.md) |
| `humanities-textual-historical` | [humanities_textual_interpretation_historical_argumentation_writing_guide.md](references/humanities_textual_interpretation_historical_argumentation_writing_guide.md) |
| `law-normative-policy-analysis` | [law_normative_policy_analysis_writing_guide.md](references/law_normative_policy_analysis_writing_guide.md) |

## LLM 与脚本职责边界

必须由 LLM 完成：

- 理解用户研究意图、约束、材料和目标读者
- 判断 research question、novelty、method fit、evidence sufficiency 和 argument closure
- 与用户开展 brainstorming、confirmation、revision 和 tradeoff discussion
- 生成 macro picture、research plan、outline、section plans、evidence plans、style profile、section outlines 和 drafts
- 判断领域指南如何适配当前论文

必须由脚本完成：

- 初始化 workspace 和 SQLite schema
- 校验 payload 基本结构、必需字段和 enum
- 写入 SQLite、追加 action log
- 计算 gate 与 `next_action`
- 渲染只读 Markdown views
- 导航 reference index

禁止：

- 不写临时脚本总结来源、判断创新、设计研究、判断证据充分性、建立风格画像或起草正文
- 不绕过 `gate-and-render`
- 不手工拼接 renderer-owned views
- 不把 unsupported claim 写得更流畅；应收窄、标记或阻断

## Failure Handling

- workspace 缺失：确认语言上下文后运行 `init_artifact_workspace.py`
- `blockers` 非空：解释 blocker，只询问清除 blocker 所需的证据、决定或修正
- `pending_user_confirmations` 非空：请求用户确认，不得提前提交确认性 payload
- `repair_sequence` 非空：视为 DB/workspace 不健康，修复后重新运行 `gate-and-render`
- open evidence gap：不得起草依赖该 gap 的 section
- rendered view 缺失或过期：运行 `gate-and-render`
- schema invalid：停止并报告结构化失败，不经用户授权不得手工改 DB 表

## Completion Standard

只有 `gate-and-render` 返回 `next_action=completed` 时 workflow 才完成。`11-manuscript-preview.md` 已生成、某些章节已起草、或用户满意某一节，都不等于完成。

## Acceptance Scenarios

Happy path:

1. 用户提供 topic 和材料
2. Agent 确认语言并初始化 workspace
3. Agent 按 gate 完成 intake、macro picture、research plan、outline、section plans、evidence/style、section drafting 和 final consistency
4. gate 返回 `completed`

Evidence blocker:

1. gate 返回 `intake_evidence` 且存在 open gaps
2. Agent 请求缺失证据，或与用户确认 claim narrowing / gap dismissal
3. Agent 写入 `evidence_intake`
4. gate 通过后才进入 drafting

Resume:

1. 用户要求继续已有 workspace
2. Agent 运行 `gate-and-render`
3. Agent 读取 `01-agent-resume.md`、对应 stage playbook 和只读视图
4. Agent 只执行返回的 `next_action`

Near miss:

- 若用户只要求“根据这个主题快速写一段 introduction”，不要静默建立完整 workspace。说明本 skill 是分阶段起草流程，并询问是否要进入 `paper-drafter` workspace。

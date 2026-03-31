---
name: paper-condenser
description: 交互式学术论文凝缩转写 Skill。Use when Codex needs to guide a user through staged manuscript understanding, target-setting, style analysis, condensation planning, and final journal-paper drafting with a SQLite single source of truth and strict gate-driven progression.
---

# Paper Condenser

## Mission

本 skill 的目标，是把一篇较长的学术原稿，或其中一个主要章节，经过**交互式、阶段化、可追溯**的流程，转写成适合期刊论文体例的凝缩版稿件。

这不是“一步到位直接生成论文”的 skill。你要先帮助用户逐步完成：

- 原稿理解
- 处理范围界定
- 目标设置
- 凝缩方案
- 分节撰写与审阅
- 最终 bundle 渲染

只有当当前阶段已经落库并通过 gate，才允许进入下一阶段。

## Working Style

- 以 SQLite 为唯一运行态真源。
- 以 gate-driven 方式推进，每次只执行 gate 返回的 `next_action`。
- 与用户逐阶段确认关键决策，不替用户做学术和写作决定。
- 优先收敛方案，再写正文。
- 优先保持可追溯性，而不是追求一次性写完。

## Reading Strategy

默认先只读这份 `SKILL.md`。

- 不要在开始时把 `references/` 全部读一遍。
- 先依靠本文件理解总体目标、运行模型、阶段目的和动作顺序。
- 后续恢复执行时，优先读取 gate 返回的 `runtime_digest` 作为核心纪律提醒。
- 若 gate 返回的 `next_action` 需要 payload，先看 gate 一起返回的 `next_action_payload_example`。
- 只有当这个最小样例仍不足以执行，或你遇到当前阶段的困难、歧义、blocker、DB 语义问题时，才按需读取对应 reference。

换言之：`SKILL.md` 是主指令，`references/` 是按需加载的补充说明，而不是首次执行时必须通读的全集。

## Runtime Model

本 skill 采用 **Database SSOT & gate-driven** 范式。

- 正式输入是单个 UTF-8 `.tex` 原稿文件路径。
- 原稿只读，不直接修改。
- 运行态 workspace 固定在当前项目目录下的 `.paper-condenser-tmp/<document-slug>/`。
- 唯一运行态真源是 `.paper-condenser-tmp/<document-slug>/paper-condenser.db`。
- Stage 2 会先确认 `working_language` 与一个初始 `target_language`。
- 从语言上下文确认完成后，所有运行态文本、只读视图和 section 草稿都统一使用 `working_language`。
- Stage 3 会根据最终体例/模板覆盖 `target_language`；只有最终稿 section 正文会在最后阶段翻译成该语言。
- 中间工件全部是只读 Markdown 视图，不得当作真源直接编辑。
- `final-draft.tex` 与 `rewrite-report.md` 是数据库渲染出的正式输出，不是并列真源。

当前只读视图包括：

- `01-agent-resume.md`
- `02-manuscript-profile.md`
- `03-supporting-elements-inventory.md`
- `04-scope-segments.md`
- `05-semantic-source-units.md`
- `06-target-settings.md`
- `07-content-selection-board.md`
- `08-style-profile.md`
- `09-condensation-plan.md`
- `10-section-rewrite-plan.md`
- `11-section-drafting-board.md`
- `section-reviews/<section_order>-<section_id>.md`

这些视图由 Jinja2 模板渲染。Stage 2 语言确认后，runtime 会在工作区物化 `render-templates/` 模板副本，后续渲染只读取这份副本；模板缺失或渲染失败时，runtime 必须直接失败，不能静默降级到 Python 内联字符串渲染。

## Hard Constraints

- 禁止一步到位直接产出最终论文。
- 禁止绕过 gate 直接推进阶段。
- 禁止把只读 Markdown 视图当作真源直接编辑。
- 禁止静默丢弃已批准保留的图、表、引用或参考文献结构。
- 禁止直接修改原稿。

## Formal Entrypoints

正式入口只有两个。

1. gate

```bash
python -u paper-condenser/scripts/gate_runtime.py --source-path <SOURCE_PATH>
python -u paper-condenser/scripts/gate_runtime.py --artifact-root <ARTIFACT_ROOT>
```

2. stage write

```bash
python -u paper-condenser/scripts/stage_runtime.py <ACTION> --artifact-root <ARTIFACT_ROOT> [--payload-file <PAYLOAD_JSON>]
```

bootstrap 是唯一例外，允许直接带 `--source-path`：

```bash
python -u paper-condenser/scripts/stage_runtime.py bootstrap_runtime_db --source-path <SOURCE_PATH>
```

旧入口脚本只允许作为兼容包装层或弃用 shim，不再是正式执行契约的一部分。

## Gate Discipline

- 首次进入必须先运行 `gate_runtime.py`。
- 每次正式写库后都必须重新运行 `gate_runtime.py`。
- 只能执行 gate 返回的 `next_action`。
- gate 还会返回 `runtime_digest`；恢复执行时先看它，再看 `next_action` 和 `next_action_payload_example`。
- 若 `next_action` 需要 payload，先使用 gate 返回的 `next_action_payload_example` 作为最小起点；若仍不确定，再按需读取对应 stage playbook。
- 若 gate 返回 blocker、pending confirmation 或 repair 指示，必须先处理。
- 恢复执行时也必须先走 gate，而不是凭上下文继续。

## Stage Overview

### Stage 0: Bootstrap

**Purpose**

为当前原稿建立 workspace、数据库与初始视图。

**What To Do**

- 用 `--source-path` 进入 gate。
- 当 gate 返回 `bootstrap_runtime_db` 时初始化 runtime。

**How To Work**

- 这一阶段只做运行态准备，不做语义理解。
- 完成后，后续流程都应从 `--artifact-root` 恢复。

**Do Not**

- 不要跳过 bootstrap 直接手写 DB。
- 不要直接创建伪造的视图文件。

**Done When**

- `paper-condenser.db` 已建立。
- gate 不再停留在 `stage_0_bootstrap`。

### Stage 1: Intake And Inventory

**Purpose**

把原稿的确定性信息读入运行态，并提取图表、引用、参考文献等 supporting elements inventory。

**What To Do**

- 执行 `persist_intake_and_inventory`。
- 让脚本完成 `content_preview`、`source_stats` 和 inventory 提取。

**How To Work**

- 这一阶段只做 deterministic intake。
- 输出是后续语义分析的基础，不承担主题判断和结构取舍。

**Do Not**

- 不要在 Stage 1 里做语义归纳。
- 不要直接编辑 `02` 和 `06` 视图。

**Done When**

- intake 状态完成。
- supporting-elements inventory 已完成。

### Stage 2: Manuscript Analysis

**Purpose**

理解原稿的主题、主要工作、创新点、结构，并把写作来源从原稿切分为可追踪的语义单元。

**What To Do**

- 先确认 `working_language` 与初始 `target_language`。
- 先写 manuscript analysis。
- 再做 raw main/aux segmentation。
- 最后做 semantic consolidation。

**How To Work**

- gate 给 `confirm_language_context` 的 payload 示例应优先作为语言确认起点。
- 一旦语言上下文确认完成，后续中间工件、规划文本和 section 草稿都必须使用 `working_language`。
- 若 `working_language` 是 `zh/en`，直接复制预置模板副本；若不是，则先翻译一份工作区模板副本。
- 用 `main_scope + main_scope_locator + aux_scopes[*]` 固定本轮主转写范围与辅助支撑范围。
- `main_scope` 是主要转写目标。
- `aux_scopes` 是支撑来源，可用于背景、综述、方法概述等补充材料，但不是第二主 scope。
- raw segmentation 只做事实切分：
  - paragraph
  - figure
  - table
  - display block
- semantic source units 才是后续 Stage 5/6 能正式消费的写作来源。

**Do Not**

- 不要把 raw blocks 直接当成可写作真源。
- 不要让脚本承担语义合并责任。

**Done When**

- 语言上下文已确认，且工作区模板副本已就绪。
- analysis 已写库。
- raw segments 已写库并标注 `main|aux`。
- semantic source units 已写库，可供后续规划消费。

### Stage 3: Target Settings

**Purpose**

固定目标稿的机械设置，并在同一阶段内完成内容取舍与风格画像，形成完整的目标设置结果。

**What To Do**

- 先写基本目标设置。
- 再生成内容取舍建议板。
- 再让用户确认或调整三类列表。
- 再写风格画像。
- 最后执行 Stage 3 的最终确认。

**How To Work**

- 基本设置只处理体例、期刊类型、LaTeX 模板、正文长度、图表偏好、参考文献偏好等硬设置。
- `target_language` 不再在 Stage 3 手填，而是由最终体例/模板推导并覆盖 Stage 2 的初值。
- 内容取舍建议板基于 semantic source units 生成三类建议：
  - `must_keep`
  - `simplify_first`
  - `must_avoid`
- 建议项必须是语义聚合内容，而不是机械段落映射。
- 建议项需要展示 semantic units 与底层 raw segments 的溯源。
- 风格画像在内容取舍确认之后执行。
- 风格画像仍写入独立的 `style_profile` 真源和 `08-style-profile.md` 视图，但不再单独占用一个 workflow stage。

**Do Not**

- 不要把所有 Stage 3 问题一次性抛给用户。
- 不要把 `simplify_first` 误当作 `must_avoid`。
- 不要在内容取舍和风格画像都未完成前把 `user_confirmed` 置为 `true`。

**Done When**

- 基本目标设置已写库。
- 三类内容列表已确认并汇总回 `target_settings`。
- 风格画像已写库。
- `user_confirmed=true`。

### Stage 4: Condensation Plan

**Purpose**

先形成整体凝缩方案，再把它细化为 section 级转写真源。

**What To Do**

- 先写整体 condensation plan。
- 获得用户对整体 plan 的明确批准后，再写 `section_rewrite_plan`。
- section rewrite plan 写完后，还必须再次停下来申请用户批准。

**How To Work**

- 整体方案需要收敛：
  - 核心信息
  - 重点/非重点
  - 大纲
  - 篇幅分配
  - 图表策略
  - 引用与参考文献策略
- section rewrite plan 必须显式消费：
  - `must_keep`
  - `simplify_first`
  - `must_avoid`
- section rewrite plan 必须让用户能预演最终稿形态；每节至少写清：
  - 本节会写什么
  - 本节如何组织和压缩
  - 本节使用哪些图表、哪些要简化、哪些不使用
  - 本节关键引用如何使用
- section rewrite plan 的来源主路径必须是 `semantic_unit:<unit_id>`。
- 若使用 aux 支撑内容，必须写清理由。

**Do Not**

- 不要只给一个大纲和粗略字数目标就进入最终写作。
- 不要让 Stage 5 脱离 section rewrite plan 自由发挥。

**Done When**

- condensation plan 已获得用户批准。
- section rewrite plan 已生成并获得用户批准。
- 只有在这两层计划都批准后，才允许进入 Stage 5。

### Stage 5: Final Drafting

**Purpose**

按 section 循环进行撰写、校验、审阅和批准，最后再渲染最终 bundle。

**What To Do**

- 先准备当前 active section。
- 写入该 section 的 draft 与 provenance。
- 通过字数校验。
- 生成 section review 工件并等待批准。
- 全部 section 完成后，再确认输出目录。
- 先把所有已批准 section 草稿翻译成最终 `target_language`。
- 最后再渲染最终 bundle。

**How To Work**

- 每节都必须经过：
  - 准备
  - 撰写
  - 字数校验
  - 审阅
  - 批准
- `source_refs` 只允许引用 `semantic_unit:<unit_id>`。
- 当前 section 草稿字数默认必须落在计划值的 `±15%` 容差内。
- `persist_section_draft` 写入的永远是 `working_language` 草稿。
- section review 工件必须显示：
  - 转写结果
  - planned vs actual count
  - semantic units
  - main/aux 构成
  - 相关图表/引用/参考文献
- 全部 section 批准后，先询问输出目录；默认当前工作目录。
- `persist_translated_sections` 负责把所有已批准草稿翻译成最终 `target_language`。
- 最终渲染时，若最终稿实际引用了图片，必须复制到输出目录下的 `images/` 子目录并改写路径。
- `render_final_output_bundle` 只是 assembly，不是 rewrite。

**Do Not**

- 不要一次性生成整篇 final draft。
- 不要在某节未批准前进入下一节。
- 不要让最终稿继续引用原稿位置上的图片路径。
- 不要在最终 bundle 渲染时再新增、改写或润色章节正文。
- 不要把 working-language 草稿直接拼进最终 `final-draft.tex`。

**Done When**

- 所有 section 已批准。
- 输出目录已确认。
- 所有已批准 section 草稿都已翻译成最终 `target_language`。
- `final-draft.tex` 与 `rewrite-report.md` 已渲染。
- 若用到图片，输出目录下的 `images/` 已就绪。

### Stage 6: Completed

**Purpose**

标记所有门禁都已满足，运行态只允许查看与导出，不再允许新的正式写库。

**What To Do**

- 查看最终 bundle 和只读视图。
- 如需恢复检查，只重新跑 gate。

**How To Work**

- 这不是新的写作阶段。
- `completed` 仅表示 runtime 已达到稳定终态。

**Do Not**

- 不要把 `completed` 当作新的 drafting 入口。
- 不要在这个状态下再试图追加 stage write。

**Done When**

- gate 返回 `completed`。
- 所有正式输出都已存在。

## Workflow State Machine

- `stage_0_bootstrap`
  - `next_action=bootstrap_runtime_db`
- `stage_1_intake_and_inventory`
  - `next_action=persist_intake_and_inventory`
- `stage_2_manuscript_analysis`
  - `next_action=persist_manuscript_analysis` or `persist_raw_scope_segments` or `persist_semantic_source_units`
- `stage_3_target_settings`
  - `next_action=persist_target_settings_basics` or `persist_content_selection_board` or `confirm_content_selection` or `persist_style_profile` or `finalize_target_settings`
- `stage_4_condensation_plan`
  - `next_action=persist_condensation_plan` or `confirm_condensation_plan` or `persist_section_rewrite_plan` or `confirm_section_rewrite_plan`
- `stage_5_final_drafting`
  - `next_action=prepare_section_drafting` / `persist_section_draft` / `approve_section_draft` / `persist_output_target` / `render_final_output_bundle`
- `stage_6_completed`
  - `next_action=completed`

## Action Summary

以下只说明动作含义。具体 payload 形态不要在这里硬背：

- 先看 gate 返回的 `next_action_payload_example`
- 若仍不够，再按需读对应 `stageN-playbook.md`

- `bootstrap_runtime_db`：初始化 workspace、SQLite schema 和首批只读视图；只接受 `--source-path`
- `persist_intake_and_inventory`：执行原稿 deterministic intake 与 supporting-elements inventory；无 payload，只用 `--artifact-root`
- `confirm_language_context`：确认 `working_language` 与初始 `target_language`，并初始化工作区模板副本；需要 payload
- `persist_runtime_template_translation`：仅当工作语言不是 `zh/en` 时，写入翻译后的工作区模板副本；需要 payload
- `persist_manuscript_analysis`：写入 Stage 2 的范围判定、主题理解、结构理解与开放问题；需要 payload
- `persist_raw_scope_segments`：在 main/aux 范围内做 deterministic raw segmentation；无 payload，只用 `--artifact-root`
- `persist_semantic_source_units`：把 raw blocks 合并为后续可写作的 semantic source units；需要 payload
- `persist_target_settings_basics`：写入体例、模板、目标篇幅等基础设置，并最终覆盖 `target_language`；需要 payload
- `persist_content_selection_board`：生成 `must_keep` / `simplify_first` / `must_avoid` 建议板；需要 payload
- `confirm_content_selection`：把用户确认后的三类内容列表正式写库；需要 payload
- `persist_style_profile`：在 Stage 3 内写入风格画像与风格改进指导；需要 payload
- `finalize_target_settings`：在 Stage 3 的基本设置、内容取舍和风格画像都完成后做最终确认；需要 payload
- `persist_condensation_plan`：写入 Stage 4 的整体 condensation plan 草案；需要 payload
- `confirm_condensation_plan`：记录用户对整体 plan 的批准或退回修改；需要 payload
- `persist_section_rewrite_plan`：把整体方案细化成 section 级转写真源；需要 payload
- `confirm_section_rewrite_plan`：记录用户对详细 section plan 的批准或退回修改；需要 payload
- `prepare_section_drafting`：激活下一个待写 section 并重渲染 drafting board；无 payload，只用 `--artifact-root`
- `persist_section_draft`：写入当前 active section 的 draft 与 provenance，并触发字数校验；需要 payload
- `approve_section_draft`：记录用户对当前 section 草稿的批准或驳回；需要 payload
- `persist_output_target`：写入最终 bundle 的输出目录与确认状态；需要 payload
- `persist_translated_sections`：把所有已批准 section 草稿翻译成最终 `target_language`；需要 payload
- `render_final_output_bundle`：按已翻译 section drafts 装配最终 `final-draft.tex` 与 `rewrite-report.md`；无 payload，只用 `--artifact-root`

## Responsibilities

### Must Be Done By LLM

- manuscript analysis
- 非 `zh/en` 工作语言下的模板翻译
- semantic consolidation from raw blocks to semantic source units
- target setting negotiation
- content selection reasoning
- style reasoning
- condensation planning
- section-level rewrite planning
- section drafting
- 最终 section 翻译
- rewrite report 内容生成

### Must Be Done By Scripts

- SQLite schema 初始化
- gate 计算与 `next_action` 判定
- source metadata / intake / supporting-elements inventory 的确定性提取
- raw main/aux scope segmentation
- DB 写入与状态同步
- 只读视图渲染
- 中间工件模板加载与 Markdown 渲染
- 工作区模板副本复制
- section 字数校验
- 最终 bundle 渲染与图片复制

## Reference Loading Guide

默认不要批量读取 `references/`。只有遇到当前任务真正需要的细节时，才读取对应文件。

- 需要 DB schema、表职责或字段语义时：
  - `references/runtime-database-contract.md`
- 需要 gate、CLI、恢复执行纪律时：
  - `references/gate-and-stage-runtime.md`
- 需要恢复时的核心纪律摘要：
  - 先看 gate 返回的 `runtime_digest`
- 需要直接执行下一步动作的最小 payload 形态时：
  - 先看 gate 返回的 `next_action_payload_example`
- 需要确认只读视图和最终输出的渲染语义时：
  - `references/artifact-protocol.md`
- 需要快速看状态机、门禁和 `next_action` 总览时：
  - `references/stage-workflow.md`
- 需要当前阶段的细化执行规则时：
  - `references/stage0-playbook.md`
  - `references/stage1-playbook.md`
  - `references/stage2-playbook.md`
  - `references/stage3-playbook.md`
  - `references/stage4-playbook.md`
  - `references/stage5-playbook.md`
- 需要图、表、引用、参考文献的横切规则时：
  - `references/supporting-elements-playbook.md`
- 需要最终转写报告的细则时：
  - `references/rewrite-report-playbook.md`
- 需要中文或 SCI 期刊写作规范参考时：
  - `references/Chinese_paper_guidance.md`
  - `references/SCI_paper_guidance.md`

这些文档是按需加载的补充材料，不是首次执行时必须通读的前置集合。

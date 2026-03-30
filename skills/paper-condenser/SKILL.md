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
- 风格画像
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
- 只有在遇到当前阶段的困难、歧义、blocker，或需要更细的 payload / gate / DB 规则时，才按需读取对应 reference。

换言之：`SKILL.md` 是主指令，`references/` 是按需加载的补充说明，而不是首次执行时必须通读的全集。

## Runtime Model

本 skill 采用 **Database SSOT & gate-driven** 范式。

- 正式输入是单个 UTF-8 `.tex` 原稿文件路径。
- 原稿只读，不直接修改。
- 运行态 workspace 固定在当前项目目录下的 `.paper-condenser-tmp/<document-slug>/`。
- 唯一运行态真源是 `.paper-condenser-tmp/<document-slug>/paper-condenser.db`。
- 中间工件全部是只读 Markdown 视图，不得当作真源直接编辑。
- `final-draft.tex` 与 `rewrite-report.md` 是数据库渲染出的正式输出，不是并列真源。

当前只读视图包括：

- `01-agent-resume.md`
- `02-manuscript-profile.md`
- `03-target-settings.md`
- `04-style-profile.md`
- `05-condensation-plan.md`
- `06-supporting-elements-inventory.md`
- `07-scope-segments.md`
- `08-semantic-source-units.md`
- `09-section-rewrite-plan.md`
- `10-section-drafting-board.md`
- `11-content-selection-board.md`
- `section-reviews/<section_order>-<section_id>.md`

这些视图由 `assets/render-templates/` 下的 Jinja2 模板渲染。模板缺失或渲染失败时，runtime 必须直接失败，不能静默降级到 Python 内联字符串渲染。

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

- 先写 manuscript analysis。
- 再做 raw main/aux segmentation。
- 最后做 semantic consolidation。

**How To Work**

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

- analysis 已写库。
- raw segments 已写库并标注 `main|aux`。
- semantic source units 已写库，可供后续规划消费。

### Stage 3: Target Settings

**Purpose**

固定目标稿的机械设置，并把“保留什么、优先精简什么、必须排除什么”单独收敛成经用户确认的三类列表。

**What To Do**

- 先写基本目标设置。
- 再生成内容取舍建议板。
- 再让用户确认或调整三类列表。
- 最后执行 Stage 3 的最终确认。

**How To Work**

- 基本设置只处理目标语言、体例、期刊类型、LaTeX 模板、正文长度、图表偏好、参考文献偏好等硬设置。
- 内容取舍建议板基于 semantic source units 生成三类建议：
  - `must_keep`
  - `simplify_first`
  - `must_avoid`
- 建议项必须是语义聚合内容，而不是机械段落映射。
- 建议项需要展示 semantic units 与底层 raw segments 的溯源。

**Do Not**

- 不要把所有 Stage 3 问题一次性抛给用户。
- 不要把 `simplify_first` 误当作 `must_avoid`。
- 不要在内容取舍未确认前把 `user_confirmed` 置为 `true`。

**Done When**

- 基本目标设置已写库。
- 三类内容列表已确认并汇总回 `target_settings`。
- `user_confirmed=true`。

### Stage 4: Style Profile

**Purpose**

总结原稿风格、识别需要修正的问题，并形成目标稿应遵循的风格指导。

**What To Do**

- 写入 `source_style`
- 写入 `problems_to_fix`
- 写入 `target_style_guidance`
- 写入 `open_questions`

**How To Work**

- 既要尊重原稿已有风格，也要指出需要纠正的表达、规范和结构问题。
- 若风格边界仍需用户决定，必须进入待确认状态。

**Do Not**

- 不要把 Stage 4 变成简单的原稿风格复述。
- 不要跳到具体 section 写作。

**Done When**

- 风格画像已写库。
- 无阻塞推进的待确认项，或这些待确认项已明确暴露给 gate。

### Stage 5: Condensation Plan

**Purpose**

先形成整体凝缩方案，再把它细化为 section 级转写真源。

**What To Do**

- 先写整体 condensation plan。
- 获得批准后，再写 `section_rewrite_plan`。

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
- section rewrite plan 的来源主路径必须是 `semantic_unit:<unit_id>`。
- 若使用 aux 支撑内容，必须写清理由。

**Do Not**

- 不要只给一个大纲和粗略字数目标就进入最终写作。
- 不要让 Stage 6 脱离 section rewrite plan 自由发挥。

**Done When**

- condensation plan 已批准。
- section rewrite plan 已落库，足以驱动逐节写作。

### Stage 6: Final Drafting

**Purpose**

按 section 循环进行撰写、校验、审阅和批准，最后再渲染最终 bundle。

**What To Do**

- 先准备当前 active section。
- 写入该 section 的 draft 与 provenance。
- 通过字数校验。
- 生成 section review 工件并等待批准。
- 全部 section 完成后，再确认输出目录并渲染最终 bundle。

**How To Work**

- 每节都必须经过：
  - 准备
  - 撰写
  - 字数校验
  - 审阅
  - 批准
- `source_refs` 只允许引用 `semantic_unit:<unit_id>`。
- 当前 section 草稿字数默认必须落在计划值的 `±15%` 容差内。
- section review 工件必须显示：
  - 转写结果
  - planned vs actual count
  - semantic units
  - main/aux 构成
  - 相关图表/引用/参考文献
- 全部 section 批准后，先询问输出目录；默认当前工作目录。
- 最终渲染时，若最终稿实际引用了图片，必须复制到输出目录下的 `images/` 子目录并改写路径。

**Do Not**

- 不要一次性生成整篇 final draft。
- 不要在某节未批准前进入下一节。
- 不要让最终稿继续引用原稿位置上的图片路径。

**Done When**

- 所有 section 已批准。
- 输出目录已确认。
- `final-draft.tex` 与 `rewrite-report.md` 已渲染。
- 若用到图片，输出目录下的 `images/` 已就绪。

## Workflow State Machine

- `stage_0_bootstrap`
  - `next_action=bootstrap_runtime_db`
- `stage_1_intake_and_inventory`
  - `next_action=persist_intake_and_inventory`
- `stage_2_manuscript_analysis`
  - `next_action=persist_manuscript_analysis` or `persist_raw_scope_segments` or `persist_semantic_source_units`
- `stage_3_target_settings`
  - `next_action=persist_target_settings_basics` or `persist_content_selection_board` or `confirm_content_selection` or `finalize_target_settings`
- `stage_4_style_profile`
  - `next_action=persist_style_profile`
- `stage_5_condensation_plan`
  - `next_action=persist_condensation_plan` or `persist_section_rewrite_plan`
- `stage_6_final_drafting`
  - `next_action=prepare_section_drafting` / `persist_section_draft` / `approve_section_draft` / `persist_output_target` / `render_final_output_bundle`
- `stage_7_completed`
  - `next_action=completed`

## Action Summary

### `bootstrap_runtime_db`

- 用途：
  - 初始化 workspace 与 SQLite schema
  - 写入 source metadata
  - 首次渲染只读视图
- 输入：
  - `--source-path`

### `persist_intake_and_inventory`

- 用途：
  - 读取源文件
  - 写入 deterministic intake
  - 写入 supporting-elements inventory
- 输入：
  - `--artifact-root`
- 不接受 LLM 语义 payload

### `persist_manuscript_analysis`

- 用途：
  - 持久化 Stage 2 的 manuscript analysis 结果
- 输入 payload 至少包含：
  - `main_scope`
  - `main_scope_locator`
  - `aux_scopes`
  - `topic`
  - `main_work`
  - `novelty`
  - `section_outline`
  - `removable_candidates`
  - `open_questions`
- 可选：
  - `pending_confirmations`

### `persist_raw_scope_segments`

- 用途：
  - 在 `main_scope` 与 `aux_scopes` 内执行 deterministic raw segmentation
  - 将 paragraph / figure / table / display block 写入 DB，并标记 `scope_role=main|aux`
- 输入：
  - `--artifact-root`
- 不接受 LLM 语义 payload

### `persist_semantic_source_units`

- 用途：
  - 基于 raw segmentation 写入真正可供 Stage 5 / 6 使用的 semantic source units
- 输入 payload 至少包含：
  - `units`
- 每个 unit 至少包含：
  - `unit_id`
  - `unit_title`
  - `unit_kind`
  - `summary`
  - `member_segment_ids`
- 可选：
  - `elements`

### `persist_target_settings_basics`

- 用途：
  - 先持久化 Stage 3 的基本目标设置
  - 暂不要求在这一步完成三类内容取舍的最终确认
- 输入 payload 至少包含：
  - `target_language`
  - `target_form`
  - `target_journal_type`
  - `latex_template_id`
  - `target_body_length`
  - `figure_table_preference`
  - `reference_handling_preference`

### `persist_content_selection_board`

- 用途：
  - 基于 `semantic_source_units` 生成内容取舍建议板
  - 组织 `must_keep` / `simplify_first` / `must_avoid`
- 输入 payload 至少包含：
  - `items`

### `confirm_content_selection`

- 用途：
  - 接收用户对三类内容列表的确认与调整
  - 将最终确认结果汇总回 `target_settings`
- 输入 payload 至少包含：
  - `items`

### `finalize_target_settings`

- 用途：
  - 在基本设置和内容取舍都完成后执行 Stage 3 最终确认
- 输入 payload 至少包含：
  - `user_confirmed=true`

### `persist_style_profile`

- 用途：
  - 持久化风格画像
- 输入 payload 至少包含：
  - `source_style`
  - `problems_to_fix`
  - `target_style_guidance`
  - `open_questions`

### `persist_condensation_plan`

- 用途：
  - 持久化凝缩方案与批准状态
- 输入 payload 至少包含：
  - `core_message`
  - `priority_map`
  - `target_outline`
  - `length_allocation`
  - `omit_merge_strategy`
  - `figure_table_plan`
  - `reference_plan`
  - `approval_status`

### `persist_section_rewrite_plan`

- 用途：
  - 按目标 section 持久化更细的转写方案
  - 绑定 semantic units、supporting elements 和篇幅计划
  - 消费已确认的 `must_keep` / `simplify_first` / `must_avoid`
- 输入 payload 至少包含：
  - `sections`

### `prepare_section_drafting`

- 用途：
  - 选择下一个未批准 section
  - 设置 active section 并重渲染 drafting board
- 输入：
  - `--artifact-root`

### `persist_section_draft`

- 用途：
  - 持久化当前 active section 的 draft 内容与 provenance
  - 计算实际字数并执行 `±15%` 容差校验
  - 生成当前 section 的独立审阅工件
- 输入 payload 至少包含：
  - `section_id`
  - `draft_tex`
  - `source_refs`

### `approve_section_draft`

- 用途：
  - 记录用户对当前 active section 的批准或驳回
- 输入 payload 至少包含：
  - `section_id`
  - `approved`

### `persist_output_target`

- 用途：
  - 持久化最终 bundle 的输出目录
  - 若用户未指定目录，默认当前工作目录
- 输入 payload 至少包含：
  - `user_confirmed`
- 可选：
  - `output_dir`

### `render_final_output_bundle`

- 用途：
  - 将全部已批准 section 装配为 `final-draft.tex`
  - 生成最终 `rewrite-report.md`
  - 复制最终稿实际引用图片到输出目录下的 `images/`
  - 改写 LaTeX 图像路径
- 输入：
  - `--artifact-root`

## Responsibilities

### Must Be Done By LLM

- manuscript analysis
- semantic consolidation from raw blocks to semantic source units
- target setting negotiation
- content selection reasoning
- style reasoning
- condensation planning
- section-level rewrite planning
- section drafting
- rewrite report 内容生成

### Must Be Done By Scripts

- SQLite schema 初始化
- gate 计算与 `next_action` 判定
- source metadata / intake / supporting-elements inventory 的确定性提取
- raw main/aux scope segmentation
- DB 写入与状态同步
- 只读视图渲染
- 中间工件模板加载与 Markdown 渲染
- section 字数校验
- 最终 bundle 渲染与图片复制

## Reference Loading Guide

默认不要批量读取 `references/`。只有遇到当前任务真正需要的细节时，才读取对应文件。

- 需要 DB schema、表职责或字段语义时：
  - `references/runtime-database-contract.md`
- 需要 gate、CLI、恢复执行纪律时：
  - `references/gate-and-stage-runtime.md`
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
  - `references/stage6-playbook.md`
- 需要图、表、引用、参考文献的横切规则时：
  - `references/supporting-elements-playbook.md`
- 需要最终转写报告的细则时：
  - `references/rewrite-report-playbook.md`
- 需要中文或 SCI 期刊写作规范参考时：
  - `references/Chinese_paper_guidance.md`
  - `references/SCI_paper_guidance.md`

这些文档是按需加载的补充材料，不是首次执行时必须通读的前置集合。

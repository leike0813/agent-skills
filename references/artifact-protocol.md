# Artifact Protocol

本文件定义 **Database SSOT & gate-driven** 范式下各运行态文件的语义。

## Single Source Of Truth

唯一运行态真源：

- `.paper-condenser-tmp/<document-slug>/paper-condenser.db`

除数据库以外，所有 Markdown / LaTeX 文件都只是渲染结果，不是运行态真源。

## Render Template Layer

只读 Markdown 视图必须通过 Jinja2 模板渲染。

- Stage 2 语言上下文确认后，runtime 会在工作区创建 `render-templates/` 模板副本
- 后续只读视图渲染只读取工作区模板副本
- 若语言上下文尚未确认，则暂时回退到包内 English 基础模板

固定映射如下：

- `01-agent-resume.md` ← `01-agent-resume.md.j2`
- `02-manuscript-profile.md` ← `02-manuscript-profile.md.j2`
- `03-supporting-elements-inventory.md` ← `03-supporting-elements-inventory.md.j2`
- `04-scope-segments.md` ← `04-scope-segments.md.j2`
- `05-semantic-source-units.md` ← `05-semantic-source-units.md.j2`
- `06-target-settings.md` ← `06-target-settings.md.j2`
- `07-content-selection-board.md` ← `07-content-selection-board.md.j2`
- `08-style-profile.md` ← `08-style-profile.md.j2`
- `09-condensation-plan.md` ← `09-condensation-plan.md.j2`
- `10-section-rewrite-plan.md` ← `10-section-rewrite-plan.md.j2`
- `11-section-drafting-board.md` ← `11-section-drafting-board.md.j2`
- `section-reviews/<section_order>-<section_id>.md` ← `section-review.md.j2`

这些模板是发布包的一部分。缺失模板、模板语法错误或渲染失败都必须视为硬错误，不允许静默退回到 Python 内联字符串渲染。

## Read-only Rendered Views

## `01-agent-resume.md`

- 真源：
  - `runtime_workspace`
  - `workflow_state`
  - `pending_confirmations`
- 用途：
  - 给 Agent 和用户查看当前阶段、`next_action`、blockers、待确认事项和渲染文件清单
  - 显示当前 `working_language`、`target_language` 与 `target_language_source`

## `02-manuscript-profile.md`

- 真源：
  - `manuscript_source`
  - `manuscript_intake`
  - `supporting_elements_inventory`
  - `manuscript_analysis`
- 用途：
  - 展示原稿来源、intake、inventory 摘要和 analysis 结论

## `03-supporting-elements-inventory.md`

- 真源：
  - `supporting_elements_inventory`
- 用途：
  - 展示图、表、citation、bibliography inventory

## `04-scope-segments.md`

- 真源：
  - `raw_scope_segments`
- 用途：
  - 只展示 main/aux 范围内 paragraph / figure / table / display block 的事实型 raw segmentation
  - 必须显式展示每条 raw block 的 `scope_role`、`scope_bucket_id`、`scope_label`
  - 不直接作为 Stage 4 / 5 的写作真源

## `05-semantic-source-units.md`

- 真源：
  - `semantic_source_units`
  - `semantic_source_unit_members`
  - `semantic_source_unit_elements`
- 用途：
  - 展示 LLM 基于 raw blocks 整理出的 semantic source units
  - 必须显式展示每个 unit 的 raw members 来自 `main` 还是 `aux`
  - 作为 Stage 4 / 5 可引用的正式写作来源视图

## `06-target-settings.md`

- 真源：
  - `target_settings`
- 用途：
  - 展示语言上下文、Stage 3 基本目标设置、`must_keep` / `simplify_first` / `must_avoid` 汇总结果，以及确认状态

## `07-content-selection-board.md`

- 真源：
  - `content_selection_items`
  - `content_selection_item_units`
  - `semantic_source_units`
  - `semantic_source_unit_members`
- 用途：
  - 展示 Stage 3 的三类内容取舍建议项
  - 每项必须显示语义标题、摘要、推荐 bucket、semantic units，以及底层 raw segment 溯源
  - 这是 Stage 3 中 `must_keep` / `simplify_first` / `must_avoid` 的详细决策板，不是最终汇总视图

## `08-style-profile.md`

- 真源：
  - `style_profile`
- 用途：
  - 展示风格画像与改写指导
  - 它是 Stage 3 的独立子步视图，而不是独立 workflow stage 的视图

## `09-condensation-plan.md`

- 真源：
  - `condensation_plan`
- 用途：
  - 展示整体凝缩方案与批准状态
  - 这是进入 section rewrite plan 之前必须先获批的整体计划
  - 属于 `stage_4_condensation_plan`

## `10-section-rewrite-plan.md`

- 真源：
  - `section_rewrite_plan`
  - `section_rewrite_plan_sources`
- 用途：
  - 展示每个目标 section 的细化转写方案、预计篇幅与来源绑定
  - 展示每节的内容摘要、组织策略、图表使用策略、引用使用策略与 aux 使用理由
  - 这是进入 Stage 5 之前必须先获批的详细转写计划
  - 主要来源绑定应是 `semantic_unit:<unit_id>`
  - 若绑定的 semantic unit 含 aux 成员，必须能看出其 main/aux 构成与使用理由

## `11-section-drafting-board.md`

- 真源：
  - `workflow_state`
  - `section_rewrite_plan`
  - `draft_sections`
  - `output_targets`
- 用途：
  - 展示 section-loop drafting 的总览面板、当前 active section 与各 section 状态
  - 只在两层计划均已批准后才会进入这一阶段
  - 属于 `stage_5_final_drafting`

## `section-reviews/<section_order>-<section_id>.md`

- 真源：
  - `section_rewrite_plan`
  - `draft_sections`
  - `draft_section_sources`
  - `draft_section_events`
- 用途：
  - 作为每节的审阅工件
  - 包含当前 section 转写结果、planned vs actual count、溯源记录与撰写事件
  - provenance 的主路径应是 `semantic_unit:<unit_id>`，如需回溯原稿细节，再通过 semantic unit 反查 raw members
  - 必须显式显示 semantic unit 的 main/aux 构成，便于检查是否越界使用 aux

## Final Outputs

## `final-draft.tex`

- 真源：
  - `final_outputs.final_draft_tex`
- 用途：
  - 最终 LaTeX 凝缩稿交付物
- 规则：
  - 由数据库渲染
  - 不作为运行态真源
  - 最终渲染只允许装配已翻译的 section drafts，不允许在这一层继续改写正文
  - section 正文在最终交付前需要先从 `working_language` 翻译到最终 `target_language`

## `rewrite-report.md`

- 真源：
  - `final_outputs.rewrite_report_md`
- 用途：
  - 最终转写报告交付物
- 规则：
  - 由数据库渲染
  - 不作为运行态真源
  - 内容应基于已批准的 section drafts 与 provenance 汇总生成
  - 保持 `working_language`，不随最终稿一起翻译

## Output Directory Assets

- 最终 bundle 还会写入用户确认的输出目录：
  - `<output_dir>/final-draft.tex`
  - `<output_dir>/rewrite-report.md`
  - `<output_dir>/images/`
- `images/` 只保存最终稿实际引用到的图片副本。
- 图片路径必须在最终 LaTeX 中改写为 `images/<filename>`，不得继续引用原稿路径。

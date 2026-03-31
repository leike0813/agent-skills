# paper-condenser Runtime Digest

## Goals

- 以阶段化、可追溯的方式把长篇学术原稿或其中一个主要章节转写成期刊体例稿件
- 用 SQLite 维持运行态唯一真源
- 先收敛理解与方案，再进入逐节写作与审阅

## Non-Goals

- 不一步到位直接生成最终论文
- 不替用户做未经确认的学术或写作决策
- 不把只读 Markdown 视图当成真源
- 不在最终 bundle 合成时继续自由发挥正文

## Runtime Rules

- 正式输入是单个 UTF-8 `.tex` 原稿
- 运行态真源只有 `.paper-condenser-tmp/<document-slug>/paper-condenser.db`
- 每次都先跑 gate，再执行唯一允许的 `next_action`
- 写库后必须重新跑 gate
- Stage 2 先确认 `working_language` 与初始 `target_language`
- 中间工件、数据库文本和 section 草稿统一使用 `working_language`
- Stage 3 会根据最终体例/模板覆盖 `target_language`
- 若有 `pending_confirmations` 或 blocker，先处理它们
- 需要 payload 时，先看 `next_action_payload_example`
- 仍不确定时，再按需读对应 playbook

## Six Stages

1. Bootstrap：建 workspace 和数据库，不做语义理解
2. Intake And Inventory：做 deterministic intake 与 supporting elements 提取
3. Manuscript Analysis：先确认语言上下文与模板副本，再确定 main/aux scope，完成 raw segmentation 与 semantic units
4. Target Settings：完成基本设置、内容取舍、风格画像和最终确认
5. Condensation Plan：先批准整体 plan，再批准详细 section rewrite plan
6. Final Drafting：逐节撰写、字数校验、审阅批准，确认输出目录后先翻译 sections，再 assembly-only 渲染最终 bundle

## Hard Red Lines

- 不得跳过任何 gate 门禁
- 不得把 raw blocks 直接当成写作真源
- 不得在 Stage 4 计划未批准时进入正式写作
- 不得在某节未批准时推进到下一节
- 不得把 working-language 草稿直接拼进最终稿
- `render_final_output_bundle` 只做 assembly，不做 rewrite
- 最终稿若使用图片，必须复制到输出目录 `images/` 并改写路径

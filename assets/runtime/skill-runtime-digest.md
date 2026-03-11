# review-master Runtime Digest

## Goals

- 以阶段化方式推进论文修回，而不是一步到位改稿
- 用 SQLite 维持运行时唯一真源
- 把原始 reviewer thread 整理为 canonical atomic item，并在用户确认下逐条闭环
- 最终 response letter 必须回到原始 `thread_id` 顺序组织，并以 point-to-point 表格输出

## Non-Goals

- 不直接一步到位修改论文原稿
- 不替用户做未经授权的学术决策
- 不把脚本当作核心语义判断的替代品
- 不把只读 Markdown 视图当成运行时真源

## Responsibilities

- Agent 负责语义理解、学术判断、策略制定、意见映射和用户交互
- 脚本只负责确定性且可验证的工作：workspace 初始化、数据库读写辅助、状态门禁检查、恢复包输出和只读视图重渲染
- Stage 5 的 manuscript draft 与 response draft 由 Agent 写入正式真源表，Stage 6 再继续做最终成文和导出

## Workflow Discipline

- 先恢复，后执行
- 每次写库后都必须运行 `gate-and-render` 核心脚本
- 有 `pending_user_confirmations` 时先请求确认
- 有 `global_blockers` 时先请求补材或澄清
- 每轮补材都要形成文件级 intake 判定；`accepted` 补材必须有落地映射
- `active_comment_id` 允许显式切换，但不得静默切换 comment
- 不满足导出门禁时，禁止导出 marked manuscript 之后的任何最终文件
- Stage 6 manuscript 导出必须先写实 `export_patch_sets` 与 `export_patches`
- marked manuscript 必须是完整稿件
- clean manuscript 必须与用户确认后的 marked manuscript 内容一致，只去掉 `changes` 标记
- `response_latex` 必须是带 front matter 的完整可编译 LaTeX 文件

## Inputs And Outputs

- 必需输入：`manuscript_source`、`review_comments_source`
- 可选输入：`editor_letter_source`、`user_notes`
- 运行时真源：`review-master.db`
- 只读视图：`agent-resume.md`、`manuscript-structure-summary.md`、`raw-review-thread-list.md`、`atomic-review-comment-list.md`、`thread-to-atomic-mapping.md`、`atomic-comment-workboard.md`、`style-profile.md`、`action-copy-variants.md`、`response-letter-outline.md`、`export-patch-plan.md`、`response-letter-table-preview.md`、`response-letter-table-preview.tex`、`supplement-intake-plan.md`、`final-assembly-checklist.md`、`response-strategy-cards/{comment_id}.md`
- 最终输出：`marked_manuscript`、`clean_manuscript`、`response_markdown`、`response_latex`

## Six Stages

1. 入口解析与 workspace 初始化
2. 原稿结构分析
3. 原始审稿意见块抽取、去重、归并和 canonical atomic item 形成
4. atomic workboard 规划
5. 逐条策略与执行
6. 风格画像、位置级 manuscript 最终文案版本生成、thread-level row 组装、完整 marked manuscript 导出与最终 clean export

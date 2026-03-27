# 阶段六：交互式改稿、revision audit 与 response 覆盖闭环

本阶段使用的正式术语、脚本称呼、action id 和最终导出产物命名以：

- `review-master/references/workflow-glossary.md`

为准。

## 目标

- 以 `working_manuscript` 作为唯一协作修改稿
- 以 `source_snapshot` 作为只读基准
- 让每一轮明确修改都形成 revision audit 记录
- 让最终 response letter 回到原始 `thread_id` 索引层
- 以 response 覆盖矩阵和 plan action 结案状态作为 Stage 6 闭环判断

## 输入与前置产物

Stage 6 启动前应已具备：

- `03-style-profile.md`
- `11-manuscript-revision-guide.md`
- `12-manuscript-execution-graph.md`
- `workspace_manuscript_copies`
  - `source_snapshot`
  - `working_manuscript`
- `revision_plan_actions`
- `revision_plan_dependencies`

其中：

- `03-style-profile.md` 提供风格基线与语气约束
- `11-manuscript-revision-guide.md` 提供稿件修改指南
- `12-manuscript-execution-graph.md` 提供执行顺序与依赖关系

## 主循环

Stage 6 的固定循环是：

1. 读取 `11-manuscript-revision-guide.md`
2. 读取 `12-manuscript-execution-graph.md`
3. 参考 `03-style-profile.md`
4. 用户与 Agent 直接修改 `working_manuscript`
5. 调用 `commit_revision_round.py`
6. 读取更新后的 `13-17` 工件
7. 继续下一轮，直到全部闭环

## revision audit 机制

Stage 6 的每一轮明确修改都必须形成一条 revision action log。

正式脚本职责：

- `capture_revision_action.py`
  - 读取 `source_snapshot`
  - 读取 `working_manuscript`
  - 识别自上次审计以来的增量 diff
  - 写入 revision audit 真源
- `commit_revision_round.py`
  - 作为正式提交入口
  - 固定执行 `capture -> gate-and-render`

每一轮提交至少要写入：

- `revision_action_logs`
- `revision_action_log_plan_links`
- `revision_action_log_thread_links`
- `revision_action_log_file_diffs`
- `working_copy_file_state`

## response rows 的形成

最终 response letter 仍然以原始 `thread_id` 为正式索引。

`response_thread_rows` 的生成输入包括：

- Stage 5 已确认的策略与 execution items
- 已完成的 revision logs
- thread-level 聚合关系

固定要求：

- 一条原始 reviewer/editor thread 对应一条最终 response row
- 输出顺序按原始 `thread_order`
- response row 使用文本语言
- 每条 response row 必须满足其一：
  - 关联至少一条已完成 revision log
  - 显式标记为 `response_only_resolution`

## 用户可读工件

Stage 6 必须持续刷新并展示：

- `13-revision-action-log.md`
- `14-response-coverage-matrix.md`
- `15-response-letter-preview.md`
- `16-response-letter-preview.tex`
- `17-final-assembly-checklist.md`

这些工件的职责分别是：

- `13-revision-action-log.md`
  - 展示每轮修改摘要、操作者、关联 plan action、关联 thread 与关键 diff
- `14-response-coverage-matrix.md`
  - 展示每个 `thread_id` 的覆盖状态、关联 `log_id` 与 response row 闭环情况
- `15-response-letter-preview.md`
  - 展示 Markdown 回复信预览
- `16-response-letter-preview.tex`
  - 展示 LaTeX 回复信预览
- `17-final-assembly-checklist.md`
  - 展示 Stage 6 结案检查项

## `latexdiff` 规则

- `latexdiff_manuscript` 是可选辅助产物
- 环境支持时可以生成并写入 `export_artifacts`
- 环境不支持时只写 advisory，不阻断 Stage 6 完成

## 何时必须向用户提问

- 当前修改会显著改变论文主线、核心 claim 或关键结论
- 某条 thread 的 closing strategy 仍需用户授权
- `response_only_resolution` 是否可接受仍不明确
- 当前 revision plan action 的关闭条件仍有实质歧义

## 禁止动作

- 直接修改 `source_snapshot`
- 修改 `working_manuscript` 后不记录 revision audit
- 在未刷新 `13-17` 工件的情况下假定 Stage 6 已闭环
- 用 `comment_id` 顺序直接替代 `thread_id` 顺序输出最终 response letter
- 在存在未审计 diff 时继续推进 Stage 6 完成态

## 完成标准

- 所有 `revision_plan_actions` 都是 `completed` 或 `dismissed`
- 所有已发生的 `working_manuscript` 修改都已审计入库
- 每个 `thread_id` 都有最终 `response_thread_rows`
- `14-response-coverage-matrix.md` 显示所有 thread 已闭环
- `working_manuscript`、`response_markdown`、`response_latex` 已稳定可交付

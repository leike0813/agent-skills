# Helper Scripts

这份文档描述 `review-master` 当前运行时使用的正式脚本集合与职责边界。

正式术语、脚本称呼和 action id 以：

- `review-master/references/workflow-glossary.md`

为准。

## 总原则

- 脚本只负责确定性、可验证、重复性高的工作
- 语义理解、atomic 建模、策略制定、证据判断、用户交互由 Agent 负责
- 正式写库后必须重新运行 `gate-and-render` 核心脚本
- Stage 6 的每一轮改稿提交都必须通过正式提交入口完成

## `detect_main_tex.py`

- 路径：`review-master/scripts/detect_main_tex.py`
- 作用：当 `manuscript_source` 是 LaTeX 工程目录时，辅助识别主入口 `.tex`
- 输入：工程目录路径
- 输出：候选主入口及其判断依据
- 使用时机：
  - Stage 1
  - 仅在 manuscript 为目录且主入口需要辅助判断时
- 不负责：
  - 替用户在多个高置信候选中做最终选择
  - 任何后续阶段分析

## `init_artifact_workspace.py`

- 路径：`review-master/scripts/init_artifact_workspace.py`
- 作用：初始化 workspace 运行时真源、只读视图骨架和稿件副本目录
- 必须显式传入：
  - `--document-language`
  - `--working-language`
- Stage 1 初始化后至少建立：
  - `review-master.db`
  - `runtime-localization/`
  - 只读 Markdown 工件骨架
  - `source_snapshot`
  - `working_manuscript`
- 不负责：
  - Stage 2 之后的分析写库
  - Stage 3-6 的语义判断

## `gate_and_render_workspace.py`

- 路径：`review-master/scripts/gate_and_render_workspace.py`
- 正式称呼：`gate-and-render` 核心脚本
- 作用：
  - 读取 `review-master.db`
  - 检查状态机门禁
  - 重渲染只读视图
  - 输出 `instruction_payload`
  - 重建恢复包与 `01-agent-resume.md`
- 必须在以下时机运行：
  - 统一恢复入口
  - 每次正式写库后
  - 每个阶段完成后
  - Stage 6 每轮提交后
- Stage 6 中额外职责：
  - 检查 `working_manuscript` 是否存在未审计 diff
  - 检查 `revision_plan_actions` 是否全部结案
  - 检查 `response_thread_rows` 与 revision audit 的覆盖闭环
- 不负责：
  - 自动补写 revision log
  - 替用户生成语义判断

## `capture_revision_action.py`

- 路径：`review-master/scripts/capture_revision_action.py`
- 作用：把一轮已经发生的 `working_manuscript` 修改写入 revision audit 真源
- 固定输入语境：
  - `source_snapshot`
  - `working_manuscript`
  - 上次已审计的文件状态
- 写入内容：
  - `revision_action_logs`
  - `revision_action_log_plan_links`
  - `revision_action_log_thread_links`
  - `revision_action_log_file_diffs`
  - `working_copy_file_state`
- 典型职责：
  - 计算自上次审计以来的增量 diff
  - 记录 `before_excerpt` / `after_excerpt`
  - 记录关联的 `plan_action_id` 与 `thread_id`
- 不负责：
  - 门禁判定
  - 只读视图渲染

## `commit_revision_round.py`

- 路径：`review-master/scripts/commit_revision_round.py`
- 作用：作为 Stage 6 的正式提交入口，固定执行：
  1. `capture_revision_action.py`
  2. `gate_and_render_workspace.py`
- 使用规则：
  - Agent 每完成一轮明确改稿后，必须通过它提交
  - 用户手动改稿后，若希望纳入正式审计，也应通过它提交
- 价值：
  - 把“改稿后立即 capture + gate”的动作绑定为单一入口
  - 让 Stage 6 的 revision audit 与只读视图刷新保持同步

## Stage 6 审计纪律

- `working_manuscript` 是唯一允许直接修改的稿件副本
- `source_snapshot` 是只读基准
- 每次明确修改完成后，都要形成一条 revision action log
- 若用户绕过正式提交入口直接改了 `working_manuscript`，下一次运行 `gate-and-render` 时会被识别为未审计 diff，并返回 `record_revision_action`

## 统一调用顺序

### Stage 1

1. 识别主入口
2. 初始化 workspace
3. 写 Stage 1 真源
4. 运行 `gate-and-render`

### Stage 2-5

1. Agent 完成语义分析
2. 写对应阶段真源
3. 运行 `gate-and-render`

### Stage 6

1. Agent 与用户修改 `working_manuscript`
2. 运行 `commit_revision_round.py`
3. 读取更新后的 `13-17` 工件与 `instruction_payload`

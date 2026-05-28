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
  - 检查 `revision_plan_actions` 是否全部结案
  - 检查 `response_thread_rows` 与 semantic revision log 的覆盖闭环
- 不负责：
  - 自动补写 revision log
  - 替用户生成语义判断

## `capture_revision_action.py`

- 路径：`review-master/scripts/capture_revision_action.py`
- 作用：把 Agent 汇总的一轮 `working_manuscript` 语义修改 log 写入 revision 真源
- 固定输入语境：
  - Agent-authored JSON payload
  - 本轮涉及的 `plan_action_id`
  - 本轮涉及的 `thread_id`
- 写入内容：
  - `revision_action_logs`
  - `revision_action_log_plan_links`
  - `revision_action_log_thread_links`
  - `revision_action_log_entries`
  - 视情况更新 `revision_plan_actions.status`
- 典型职责：
  - 校验结构化 semantic revision log payload
  - 记录 Agent 汇总的目标位置、改动类型、改动摘要、修改理由、证据来源和回复信用途
  - 记录关联的 `plan_action_id` 与 `thread_id`
- 不负责：
  - 门禁判定
  - 只读视图渲染
  - 读取稿件文件或生成 diff

## `commit_revision_round.py`

- 路径：`review-master/scripts/commit_revision_round.py`
- 作用：作为 Stage 6 的正式提交入口，固定执行：
  1. `capture_revision_action.py --payload ...`
  2. `gate_and_render_workspace.py`
- 使用规则：
  - Agent 每完成一轮明确改稿后，必须先汇总语义修改条目，再通过它提交
  - 用户手动改稿后，若希望纳入正式审计，也必须由 Agent 汇总为 payload 后提交
- 价值：
  - 把“Agent 写入 semantic log + gate”的动作绑定为单一入口
  - 让 Stage 6 的 semantic revision log 与只读视图刷新保持同步

## Stage 6 审计纪律

- `working_manuscript` 是唯一允许直接修改的稿件副本
- `source_snapshot` 是只读备份，不参与 revision log 或完成门禁
- 每次明确修改完成后，都要由 Agent 形成一条结构化 revision action log
- `gate-and-render` 不读取稿件 diff，不自动补写 log；它只依据 plan action 状态、revision log links 与 response row 覆盖判断 Stage 6 是否闭环

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
2. Agent 汇总 semantic revision log payload，并运行 `commit_revision_round.py --payload ...`
3. 读取更新后的 `13-17` 工件与 `instruction_payload`

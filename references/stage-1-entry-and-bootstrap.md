# 阶段一：入口解析与 workspace 初始化

本阶段使用的正式术语、脚本称呼和 action id 以：

- `review-master/references/workflow-glossary.md`

为准。

## 目标

- 明确 `manuscript_source` 的入口形态
- 明确 `review_comments_source` 及可选输入是否可用
- 初始化运行时数据库与首批只读视图
- 完成 bootstrap/continuation resume 对齐，让 Agent 在进入实质工作前先知道当前状态、当前焦点和下一步动作

## 进入条件

- 用户已调用本 skill
- 用户至少提供：
  - `manuscript_source`
  - `review_comments_source`
- 若是跨 Session 或上下文压缩后的继续执行，也仍然从本阶段定义的恢复入口开始

## 必读材料

- `review-master/SKILL.md`
- `review-master/references/helper-scripts.md`
- `review-master/references/workflow-state-machine.md`
- `review-master/references/sql-write-recipes.md`
- `review-master/assets/runtime/skill-runtime-digest.md`

## 子流程

### 1. 先确认运行环境

- 先检查脚本驱动模式所需依赖是否可用：
  - Python 3
  - `PyYAML`
  - `Jinja2`
- 若依赖齐全，继续进入统一恢复入口
- 若依赖不齐全，必须问用户是否批准安装
- 若用户不批准，则数据库仍可继续作为真源，但后续只读 Markdown 视图只能由 Agent 手工拼接

### 2. 统一恢复入口

- 无论是首次调用还是恢复调用，都必须先运行 `gate-and-render` 核心脚本
- 先读取：
  - `instruction_payload.resume_packet`
  - `agent-resume.md`
- 首次调用时看到的是 bootstrap resume
- 恢复调用时看到的是 continuation resume
- 这一步不能绕过

### 3. 核对输入

- 检查必需输入是否都存在且可读
- 吸收可选输入：
  - `editor_letter_source`
  - `user_notes`
- 若必需输入缺失，必须立刻向用户提问，不能继续初始化

### 4. 识别 manuscript 入口

- `manuscript_source` 是单个 `.tex` 文件时：
  - 一般直接视为主入口
  - 通常不需要调用 `detect_main_tex.py`
- `manuscript_source` 是 LaTeX 工程目录时：
  - 优先调用 `detect_main_tex.py`
  - 若工具返回多个候选主入口，必须问用户确认
  - 不允许擅自替用户选择

### 5. 初始化 workspace

- 需要调用 `init_artifact_workspace.py`
- 初始化只创建运行时真源与只读视图骨架，不执行任何后续阶段分析
- 初始化后的 workspace 至少应包含：
  - `review-master.db`
  - `agent-resume.md`
  - `manuscript-structure-summary.md`
  - `raw-review-thread-list.md`
  - `atomic-review-comment-list.md`
  - `thread-to-atomic-mapping.md`
  - `atomic-comment-workboard.md`
  - `response-letter-outline.md`
  - `final-assembly-checklist.md`
  - `response-strategy-cards/`

### 6. 执行 Stage 1 写库

- 采用 `recipe_stage1_set_entry_state`
- 最少要更新：
  - `workflow_state`
  - `resume_brief`
- 视情况更新：
  - `workflow_pending_user_confirmations`
  - `workflow_global_blockers`
  - `resume_open_loops`
  - `resume_recent_decisions`
  - `resume_must_not_forget`

### 7. 首次 gate-and-render 对齐

- Stage 1 写库后，立即运行 `gate-and-render` 核心脚本
- 再次读取：
  - `instruction_payload.resume_packet`
  - `agent-resume.md`
- 对齐当前状态、当前焦点、当前停顿原因和推荐下一步动作

## 何时必须向用户提问

- 缺少 `manuscript_source` 或 `review_comments_source`
- LaTeX 工程目录的主入口不唯一
- 运行环境缺依赖且需要用户批准安装
- 用户给了额外结构限制、路径限制或目录约束，而当前输入无法直接满足

## 数据库关注点

- `workflow_state`
- `resume_brief`
- `resume_open_loops`
- `resume_recent_decisions`
- `resume_must_not_forget`

## 脚本要求

- `detect_main_tex.py`
  - 仅在 manuscript 是工程目录、且主入口需要辅助判断时调用
- `init_artifact_workspace.py`
  - 仅在 workspace 尚未初始化时调用
- 完成阶段一写库后，立即运行 `gate-and-render` 核心脚本：
  `conda run --no-capture-output -n DataProcessing python -u review-master/scripts/gate_and_render_workspace.py --artifact-root <ARTIFACT_ROOT>`
- 运行后先读取：
  - `instruction_payload.resume_packet`
  - `agent-resume.md`

## 禁止动作

- 未完成 Stage 1 就推进到 Stage 2 及之后阶段
- 不经确认擅自选择主入口
- 绕过恢复协议，直接开始写其他业务表
- 在依赖不满足且用户未批准安装时，假装脚本仍可用

## 完成标准

- 主入口明确
- workspace 初始化完成
- `gate-and-render` 核心脚本无阻断性问题
- bootstrap/continuation resume 已被读取并对齐
- 推荐下一步动作已清楚，且允许进入 Stage 2

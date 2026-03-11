# 辅助脚本说明

正式术语、脚本称呼、action id 和最终导出产物命名以：

- `review-master/references/workflow-glossary.md`

为准。

## 总原则

`review-master` 采用 SQLite 唯一真源模式。

脚本职责：

- 入口辅助
- 确定性初始化
- 状态门禁校验
- 只读视图重渲染
- 恢复包生成
- Stage 6 导出副本复制与显式锚点补丁应用

脚本不负责：

- 原子化语义判断
- 学术策略决策
- 越过用户确认直接推进流程
- 任何需要语义理解的临时替代流程

Stage 3 特别规则：

- Stage 3 没有语义辅助脚本
- `raw_review_threads` 抽取、thread 边界判断、去重、归并、拆分和 canonical atomic 建模全部由 Agent 大语言模型完成
- `gate-and-render` 在 Stage 3 中只负责写后门禁与只读视图重渲染

Stage 4 特别规则：

- Stage 4 仍没有语义辅助脚本
- priority、dependency、evidence gap、provisional location 和用户确认需求都由 Agent 大语言模型判断
- `gate-and-render` 在 Stage 4 中只负责写后门禁、待确认态输出和只读视图重渲染

Stage 5 特别规则：

- Stage 5 仍没有语义辅助脚本
- `active_comment_id` 的锁定、策略立场判断、evidence gap 判断、逐条确认请求、blocker 判断、manuscript draft 和 response draft 形成都由 Agent 大语言模型完成
- `gate-and-render` 在 Stage 5 中只负责写后门禁、blocked/ready 状态输出、恢复包更新和只读视图重渲染
- 不允许为了逐条策略制定、草案形成或 blocker 识别临时编写语义脚本

## 运行时依赖

默认运行时依赖：

- Python 3
- `PyYAML`
- `Jinja2`
- `sqlite3` 标准库

执行前要求：

- 先确认宿主环境是否具备这些依赖
- 若不满足，先询问用户是否批准安装
- 若用户拒绝安装，数据库仍可作为真源继续使用，但渲染视图需要由 Agent 手工拼接

## 脚本清单

### `review-master/scripts/detect_main_tex.py`

用途：

- 阶段一入口辅助
- 判断 `manuscript_source` 是单文件还是工程目录
- 给出主入口候选

何时调用：

- `manuscript_source` 是工程目录时优先调用
- `manuscript_source` 已经是单个主 `.tex` 文件时通常不调用
- 若返回多个候选主入口，Agent 必须转而向用户确认，而不是继续自动推进

### `review-master/scripts/init_artifact_workspace.py`

用途：

- 初始化 artifact workspace
- 创建 `review-master.db`
- 从 `assets/schema/review-master-schema.yaml` 建表并插入 bootstrap 数据
- 从 `assets/templates/` 首次渲染只读 Markdown 视图
- 创建 bootstrap resume 所需的最小数据库状态
- 首次渲染的主要视图包括：
  - `01-agent-resume.md`
  - `02-manuscript-structure-summary.md`
  - `03-raw-review-thread-list.md`
  - `04-atomic-review-comment-list.md`
  - `05-thread-to-atomic-mapping.md`
  - `07-atomic-comment-workboard.md`
  - `08-style-profile.md`
  - `09-action-copy-variants.md`
  - `10-response-letter-outline.md`
  - `12-response-letter-table-preview.md`
  - `13-response-letter-table-preview.tex`
  - `16-final-assembly-checklist.md`

何时调用：

- 仅在 workspace 尚未初始化时调用
- 已存在 workspace 时，不应用它覆盖当前运行时真源
- Stage 1 中应在主入口基本明确后再调用，而不是在输入仍模糊时提前初始化

### `review-master/scripts/gate_and_render_workspace.py`

正式称呼：

- `gate-and-render` 核心脚本

用途：

- 读取 `review-master.db`
- 校验 schema 以外的补充规则与状态机门禁
- 从 `assets/templates/` 全量重渲染只读视图
- 输出 `instruction_payload`
- 在每次输出中附带 `instruction_payload.resume_packet`
- 重渲染 `01-agent-resume.md`

Stage 1 / Stage 2 调用时机：

- Stage 1：
  - workspace 初始化后立即调用
  - `recipe_stage1_set_entry_state` 写库后再次调用
- Stage 2：
  - `recipe_stage2_upsert_manuscript_summary` 写库后立即调用

标准执行方式：

```bash
conda run --no-capture-output -n DataProcessing python -u \
  review-master/scripts/gate_and_render_workspace.py \
  --artifact-root <ARTIFACT_ROOT>
```

不要再把它称为 `validator`。这个脚本的正式称呼固定为 `gate-and-render` 核心脚本。

## 共同规则

- 输入通过命令行参数提供
- stdout 必须且只能输出一个 JSON 对象
- 写库后必须重新运行 `gate-and-render` 核心脚本：
  `conda run --no-capture-output -n DataProcessing python -u review-master/scripts/gate_and_render_workspace.py --artifact-root <ARTIFACT_ROOT>`
- runtime schema 与模板不再硬编码在脚本中，而是从 `assets/` 读取
- 首次调用与恢复调用都先运行 `gate-and-render` 核心脚本，再读取恢复包
- Stage 1 结束前不得绕开这套恢复入口
- Stage 2 写库完成后也必须重新跑一次 `gate-and-render`，不能凭记忆直接进入 Stage 3
- Stage 3 写库完成后也必须重新跑一次 `gate-and-render`，不能凭记忆直接进入 Stage 4
- Stage 6 写库完成后也必须重新跑一次 `gate-and-render`，不能凭记忆直接进入 marked export 或 final export

### `review-master/scripts/export_manuscript_variants.py`

正式称呼：

- manuscript 导出辅助脚本

用途：

- 复制 LaTeX 原稿到独立导出目录
- 读取 `export_patch_sets` 与 `export_patches`
- 按显式 `anchor_text` 对导出副本执行：
  - `replace`
  - `insert_after`
  - `insert_before`
- 生成完整的 `marked_manuscript`
- 在用户确认后生成 `clean_manuscript`

何时调用：

- Stage 6D：导出完整 `marked_manuscript`
- Stage 6E：在最终确认后导出 `clean_manuscript`

不负责：

- 语义理解
- 最终文案生成
- 自动选择修改策略
- 自动推断插入位置

关键约束：

- 只对导出副本生效，绝不修改原始输入文件
- 必须依赖数据库中已写实的显式锚点补丁真源
- `marked_manuscript` 必须是完整稿件，不允许只导出局部摘录

## Stage 6 特别说明

### `gate-and-render` 核心脚本在 Stage 6 中做什么

- 读取 `review-master.db`
- 校验：
  - `style_profiles`
  - `style_profile_rules`
  - `action_copy_variants`
  - `selected_action_copy_variants`
  - `response_thread_rows`
  - `export_patch_sets`
  - `export_patches`
  - `export_artifacts`
- 重渲染：
  - `08-style-profile.md`
  - `09-action-copy-variants.md`
  - `10-response-letter-outline.md`
  - `11-export-patch-plan.md`
  - `12-response-letter-table-preview.md`
  - `13-response-letter-table-preview.tex`
  - `16-final-assembly-checklist.md`
- 输出 Stage 6A-6E 的 ready / blocked 指令

### Stage 6 不是语义脚本阶段

- 风格画像、去 AI 化约束、每个 target location 的 manuscript 最终落稿文本三版本生成、版本优选和 thread-level row 成文都由 Agent 完成
- `gate-and-render` 只负责写后门禁与只读视图重渲染
- manuscript 导出辅助脚本只负责把 Agent 已经决定好的文本应用到导出副本
- Stage 4 写库完成后也必须重新跑一次 `gate-and-render`，不能凭记忆直接进入 Stage 5
- Stage 5 写库完成后也必须重新跑一次 `gate-and-render`，不能凭记忆继续当前条目或切换下一条
- 不允许为原子化、去重、语义映射、优先级判断或回复策略制定临时编写脚本


## 人工回退

- 若 `detect_main_tex.py` 不可用，Agent 手工确认主入口
- 若初始化脚本不可用但 SQLite 可用，Agent 手工创建数据库并遵循 schema 约束
- 若 `gate-and-render` 核心脚本因环境依赖不可用而无法运行，Agent 手工校验数据库状态并手工拼接只读视图
- 若 Stage 1 或 Stage 2 遇到主入口/输入/环境阻断，先问用户，不得绕过问题继续推进

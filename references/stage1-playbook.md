# Stage 1 Playbook

本文件只展开 Stage 1。全局约束、脚本职责和阶段门禁以 `SKILL.md` 为准。

## 适用范围

- 本 playbook 只适用于单文件 `.tex` 路径输入。
- Stage 1 的正式真源是 `.paper-condenser-tmp/<document-slug>/manuscript-profile.json`。
- `bootstrap_runtime.py`、`init_artifacts.py`、`stage1_intake.py`、`extract_supporting_elements.py` 只负责确定性准备；其后所有理解动作都由 LLM 完成。

## 子步骤顺序

### 1. 运行态准备

- 输入：源文件路径。
- 操作：
  - 运行 `bootstrap_runtime.py --source-path <SOURCE_PATH>`。
  - 若已知 `artifact-root` 但工件不完整，运行 `init_artifacts.py --artifact-root <ARTIFACT_ROOT>`。
- 结果：
  - 任务目录建立完成。
  - 四个核心工件齐备。
  - `manuscript-profile.json` 已具备来源层字段。

### 2. Deterministic Intake

- 输入：`artifact-root`。
- 操作：
  - 运行 `stage1_intake.py --artifact-root <ARTIFACT_ROOT>`。
  - 确认 `intake_status=complete`。
- 应写入字段：
  - `content_preview`
  - `source_stats`
  - `intake_status`

### 3. Supporting-Elements Inventory

- 输入：`artifact-root`。
- 操作：
  - 运行 `extract_supporting_elements.py --artifact-root <ARTIFACT_ROOT>`。
  - 确认 `supporting_elements_status=complete`。
  - 确认 `supporting_elements` 中已形成 figure、table、citation 与 bibliography 的事实层清单。
- 应写入字段：
  - `supporting_elements_status`
  - `supporting_elements`

### 4. 处理范围识别

- 输入：原稿文本、`content_preview`、源文件路径。
- 操作：
  - 判断当前对象是整篇论文、单章、附录式材料，还是局部片段。
  - 若原稿过长或边界不清，先锁定当前处理范围。
- 应写入字段：
  - `scope`

### 5. 主题与研究问题归纳

- 输入：完整原稿或当前处理范围内的主要内容。
- 操作：
  - 归纳论文主题。
  - 提炼核心研究问题或研究目标。
- 应写入字段：
  - `topic`

### 6. 主要工作与创新点提炼

- 输入：原稿中的方法、结果、贡献描述。
- 操作：
  - 把主要工作拆成结构化列表。
  - 提炼创新点，允许保留初步判断口径。
- 应写入字段：
  - `main_work`
  - `novelty`

### 7. 章节结构与可裁剪内容识别

- 输入：原稿章节标题、结构单元、内容分布。
- 操作：
  - 形成原稿结构概览。
  - 审阅 supporting-elements inventory，判断哪些图表或引用显然属于核心证据层，哪些更像补充信息。
  - 标记可能属于背景堆叠、重复说明、实现细节过多、非核心扩展内容的段落类型。
- 应写入字段：
  - `section_outline`
  - `removable_candidates`

### 8. 开放问题整理与门禁判断

- 输入：前六步结果。
- 操作：
  - 把仍未解决但不阻塞推进的问题写入 `open_questions`。
  - 在形成可用理解草案后，把 `status` 更新为 `analysis_complete`。
- 应写入字段：
  - `open_questions`
  - `status`

## 必问条件

- 当前文件明显不是整篇稿件，但边界不清楚。
- 文件中存在多个候选章节或多个可处理对象，无法判断目标范围。
- 当前片段缺少上文才能确认研究问题或章节归属。
- 原稿过长，若不先缩小范围就无法稳健完成 Stage 1。

## 禁止提问条件

- 不得在 Stage 1 询问目标语言。
- 不得在 Stage 1 询问目标文体或目标期刊类型。
- 不得在 Stage 1 询问目标正文长度。
- 不得把 Stage 2 的约束收集提前成 Stage 1 的问题。

## 常见失败场景

### Intake 尚未完成

- 表现：
  - `intake_status != complete`
- 处理：
  - 先重新执行 `stage1_intake.py`
  - 不进入语义分析

### 范围不清

- 表现：
  - 无法判断当前文件对应整篇还是局部内容
- 处理：
  - 先向用户确认处理范围
  - 将范围歧义写入 `open_questions`

### 语义结果只存在于上下文

- 表现：
  - 对话中已经讨论出主题和结构，但 `manuscript-profile.json` 未更新
- 处理：
  - 立即回写工件
  - 未回写前不得进入 Stage 2

## Stage 2 交接检查清单

- `intake_status=complete`
- `supporting_elements_status=complete`
- `scope` 已写入
- `topic` 非空
- `main_work` 非空
- `novelty` 非空
- `section_outline` 非空
- `removable_candidates` 已列出
- `open_questions` 已写入
- `status=analysis_complete`

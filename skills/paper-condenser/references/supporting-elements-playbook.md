# Supporting Elements Playbook

本文件展开图、表、引用与参考文献的横切处理流程。全局约束以 `SKILL.md` 为准；本文件只补 supporting elements 在 Stage 1、Stage 4、Stage 5 中的专门处理规则。

## 适用范围

- supporting elements 指 figure、table、citation 与 bibliography structure。
- 首版正式输入仍是单文件 `.tex` 原稿。
- 首版正式参考文献模式以 `BibTeX / citekey` 优先，但允许原稿输入使用 `thebibliography`。
- 本流程不引入独立中间工件；状态继续复用现有四个真源。

## Stage 1：事实层 Inventory

### 必调脚本

- `extract_supporting_elements.py --artifact-root <ARTIFACT_ROOT>`

### 脚本职责

- 提取原稿中的 `figure` 环境清单。
- 提取原稿中的 `table` 环境清单。
- 提取 citation command 与 citekeys。
- 提取 bibliography resource 或 `thebibliography` / `\bibitem` 结构。
- 把结果写入 `manuscript-profile.json.supporting_elements`。

### LLM 职责

- 阅读 inventory，判断 supporting elements 是否构成核心证据层。
- 识别哪些图表、表格或引用在 Stage 4 必须被单独决策。
- 把阻塞性歧义写入 `open_questions`。

### Stage 1 门禁

- `supporting_elements_status=complete`
- `supporting_elements` 已落盘
- 相关歧义已进入 `open_questions`

## Stage 2：目标偏好确认

### 必收集字段

- `figure_table_preference`
- `reference_handling_preference`

### 规则

- 这里收集的是偏好和边界，不是具体 keep/drop 清单。
- 必须在 Stage 2 readback 中一起确认。
- 只要这两个字段为空，`user_confirmed` 就不能置为 `true`。

## Stage 3：风格指导

### 关注点

- figure caption / table title 的表达风格
- citation sentence 的叙述方式
- references presentation 的规范风格

### 落盘位置

- `style-profile.md`

## Stage 4：迁移方案收敛

### 必写章节

- `## Figure / Table Plan`
- `## Reference Plan`

### Figure / Table Plan 最低要求

- 明确保留哪些图表
- 明确哪些表格改写为正文
- 明确哪些元素删除或仅保留占位
- 明确这些决策如何服务于目标稿的论证结构

### Reference Plan 最低要求

- 明确保留哪些关键引用
- 明确哪些引用可压缩或删除
- 明确最终稿是否沿用 BibTeX / citekey 结构
- 明确 bibliography 层如何在最终稿中表示

### Stage 4 门禁

- 以上两节都非空
- `Approval` 已记录 `Status: approved`

## Stage 5：最终落地

### 必须做到

- 已批准保留的 supporting elements 不能静默丢失。
- 能完整迁移的元素应完整迁移。
- 当前轮次不能精修的元素必须保留清晰占位。
- 最终稿中的 supporting-elements 表达应遵循 `Target Style Guidance`。
- `rewrite-report.md` 必须对关键图表、关键表格、关键引用给出可追踪的说明。

### 常见失败场景

#### 只有正文，没有 supporting elements

- 表现：
  - 最终稿正文写完了，但已批准保留的图、表或引用没有出现在 `final-draft.tex`
- 处理：
  - 回到 Stage 5，按 `Figure / Table Plan` 和 `Reference Plan` 补齐迁移或占位

#### 引用被重写时失去 citekey 结构

- 表现：
  - 原稿是 BibTeX / citekey 流程，但最终稿把引用关系改写成不可追踪的纯文本
- 处理：
  - 回到 Stage 5，恢复可追踪的 citation / bibliography 结构

#### 图表取舍只留在聊天里

- 表现：
  - 对话中已经讨论保留哪些图表，但 `Figure / Table Plan` 为空或不完整
- 处理：
  - 回到 Stage 4，把决策写入真源后再继续写作

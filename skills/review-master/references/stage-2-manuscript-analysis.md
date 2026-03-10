# 阶段二：原稿结构分析

本阶段使用的正式术语、脚本称呼和 action id 以：

- `review-master/references/workflow-glossary.md`

为准。

## 目标

- 建立足以支撑后续映射和策略制定的全文结构理解

## 进入条件

- Stage 1 已完成
- 主入口明确
- workspace 已初始化
- 最近一次 `gate-and-render` 已返回允许进入 Stage 2 的结果

## 必读材料

- `manuscript-structure-summary.md`
- `agent-resume.md`
- `review-master/references/sql-write-recipes.md`
- `review-master/references/workflow-state-machine.md`
- `review-master/references/stage-2-manuscript-analysis.md`

## 固定关注点

做 Stage 2 时，至少要覆盖以下结构要素：

- `main_entry`
- `project_shape`
- section hierarchy
- core claims
- supporting evidence
- high-risk modification areas

## 子流程

### 1. 建立全文结构框架

- 先确认主稿是单文件还是工程目录
- 梳理章节层级，而不是只摘录几个标题
- 识别各章节的作用，例如：
  - 问题定义
  - 方法说明
  - 实验设置
  - 结果与讨论
  - limitation / conclusion

### 2. 抽取核心 claims

- 识别论文的主要结论和贡献点
- 每条 claim 都要能指出其主要支撑证据来自哪里
- 若 claim 无法稳定归纳，说明 Stage 2 仍未完成

### 3. 识别高风险修改区

- 明确哪些区域后续最可能被频繁修改，例如：
  - abstract
  - results / discussion
  - method 关键定义
  - limitation / conclusion

### 4. 写入结构真源

- 采用 `recipe_stage2_upsert_manuscript_summary`
- 需要写入：
  - `manuscript_summary`
  - `manuscript_sections`
  - `manuscript_claims`
  - `workflow_state`
  - `resume_brief`
  - `resume_recent_decisions`
- 视情况写入：
  - `resume_open_loops`

### 5. 重新运行 gate-and-render

- 写库完成后，立即运行 `gate-and-render`
- 确认 `manuscript-structure-summary.md` 已重新渲染
- 读取新的 `instruction_payload`，确认推荐推进动作是否已稳定指向 Stage 3

## 何时需要向用户追问

- 主入口文件虽已确定，但论文结构仍然不清
- 工程残缺、引用文件缺失、章节关系无法判断
- 用户另有结构性约束，例如要求只分析主稿、不分析 supplement，或要求特殊的章节视角

## 用户可读视图

- `manuscript-structure-summary.md`

## 禁止动作

- 跳过结构分析直接进入意见原子化
- 在 `manuscript_sections` 或 `manuscript_claims` 明显缺失时推进
- 在高风险修改区尚未识别时假装结构分析已经完成

## 如何判断“结构摘要足够支撑 Stage 3”

满足以下条件时，才视为 Stage 2 已足以支撑 Stage 3：

- 主入口明确且工程形态清楚
- section hierarchy 足以支持后续 location 映射
- 至少主要 claims 已成型，且能指出主要支撑证据
- 高风险修改区已识别
- `manuscript-structure-summary.md` 的内容足以让 Agent 在 Stage 3 中理解 reviewer thread 可能落向哪里

## 完成标准

- 主入口、项目形态、章节结构、核心论点均已入库
- 高风险修改区已识别
- `gate-and-render` 已重渲染结构摘要视图
- 结构摘要足以支撑阶段三和阶段四

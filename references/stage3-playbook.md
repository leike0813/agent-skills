# Stage 3 Playbook

本文件只展开 Stage 3。全局约束、脚本职责和阶段门禁以 `SKILL.md` 为准。

## 适用范围

- 本 playbook 只处理风格画像、问题诊断和目标稿风格指导。
- Stage 3 的正式真源是 `artifacts/<document-slug>/style-profile.md`。
- 本阶段不新增脚本，也不修改 `style-profile.md` 的四段模板结构。

## 子步骤顺序

### 1. 进入 Stage 3

- 前置条件：
  - Stage 1 已完成。
  - `target-settings.json` 已完成整组确认，且 `user_confirmed=true`。
- 操作：
  - 基于原稿理解与目标设置，判断当前需要保留哪些原稿风格特征、纠正哪些问题。

### 2. Source Style 观察

- 输入：
  - 原稿文本
  - Stage 1 的原稿理解
  - Stage 2 的目标设置
- 操作：
  - 记录原稿的表达风格、句式习惯、论述密度、结构节奏、常用措辞和已有优点。
- 应写入章节：
  - `## Source Style`

### 3. Problems To Fix 诊断

- 操作：
  - 识别需要纠偏的风格、规范、语气或表达问题。
  - 区分“应保留的特色”和“应纠正的问题”。
- 应写入章节：
  - `## Problems To Fix`

### 4. Target Style Guidance 形成

- 操作：
  - 给出面向目标稿的可执行写作原则。
  - 将 Stage 2 的目标设置转化为写作层面的风格指导，而不是停留在抽象偏好。
- 应写入章节：
  - `## Target Style Guidance`

### 5. Open Questions 收敛

- 操作：
  - 把仍未确认的风格偏好、语气边界或表达规范选择写入 `Open Questions`。
  - 若当前没有未决项，也保留该章节。
- 应写入章节：
  - `## Open Questions`

## 必问条件

- 当前存在多种合理的风格方向，但无法判断用户偏好。
- 语气边界、表达规范或修辞程度会明显影响最终成稿。
- 某项原稿风格缺陷是否应保留、弱化或完全去除，需要用户拍板。

## 禁止提问条件

- 不得在 Stage 3 提前讨论重点/非重点。
- 不得在 Stage 3 提前讨论目标大纲。
- 不得在 Stage 3 提前讨论篇幅分配。
- 不得在 Stage 3 提前讨论删改策略。

## 常见失败场景

### 只有观察，没有指导

- 表现：
  - 只总结了原稿是什么风格，但没有写需要修正的问题和目标指导
- 处理：
  - 补齐 `Problems To Fix`
  - 补齐 `Target Style Guidance`

### 未决问题留在对话里

- 表现：
  - 对话里已经提到风格偏好不确定，但 `Open Questions` 为空或未更新
- 处理：
  - 立即把未决项写回 `Open Questions`

### 提前进入 Stage 4

- 表现：
  - 在 Stage 3 中已经开始讨论重点/非重点、目标大纲或篇幅分配
- 处理：
  - 停止方案收敛
  - 先完成 `style-profile.md` 四个章节

## Stage 4 交接检查清单

- `Source Style` 已写入原稿风格特征
- `Problems To Fix` 已写入明确问题
- `Target Style Guidance` 已写入可执行指导
- `Open Questions` 已显式保留并记录未决风格问题

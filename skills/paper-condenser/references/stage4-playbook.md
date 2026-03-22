# Stage 4 Playbook

本文件只展开 Stage 4。全局约束、脚本职责和阶段门禁以 `SKILL.md` 为准。

## 适用范围

- 本 playbook 只处理凝缩方案收敛与批准。
- Stage 4 的正式真源是 `artifacts/<document-slug>/condensation-plan.md`。
- 本阶段不新增脚本，也不修改 `condensation-plan.md` 的六段模板结构。

## 子步骤顺序

### 1. 进入 Stage 4

- 前置条件：
  - Stage 1、Stage 2、Stage 3 已完成。
- 操作：
  - 基于原稿理解、目标设置和风格画像，判断当前目标稿必须保留什么、可以压缩什么、如何组织成稿。

### 2. Core Message 锁定

- 操作：
  - 提炼目标稿必须保留的核心信息、核心论旨和不可丢失的研究价值。
- 应写入章节：
  - `## Core Message`

### 3. Priority Map 收敛

- 操作：
  - 明确重点、非重点和优先级。
  - 把“必须保留”“可以弱化”“可以省略”的内容分开。
- 应写入章节：
  - `## Priority Map`

### 4. Target Outline 形成

- 操作：
  - 形成目标稿的大纲结构。
  - 让结构和核心信息、优先级保持一致。
- 应写入章节：
  - `## Target Outline`

### 5. Length Allocation 分配

- 操作：
  - 记录目标稿各部分篇幅分配。
  - 确保分配和目标正文长度相容。
- 应写入章节：
  - `## Length Allocation`

### 6. Omit / Merge Strategy 制定

- 操作：
  - 记录压缩、合并、删除策略。
  - 说明哪些内容将被合并、压缩或移除。
- 应写入章节：
  - `## Omit / Merge Strategy`

### 7. Approval 记录

- 操作：
  - 在方案完整后请求用户批准。
  - 仅在用户明确批准后，把 `Status` 更新为 `approved`。
  - 若未批准，则保持 `Status: not approved`。
- 应写入章节：
  - `## Approval`

## 必问条件

- 重点/非重点还未收敛。
- 目标大纲存在多个合理版本，无法自行判断用户偏好。
- 篇幅分配取决于用户取舍。
- 某项删改策略可能改变用户想保留的重点。
- 当前方案已成形，但还未得到明确批准。

## 禁止提问条件

- 不得在 Stage 4 直接开始最终写作。
- 不得在未批准方案前把 Stage 5 当作默认下一步。

## 常见失败场景

### 方案章节不完整

- 表现：
  - 只写了核心信息和大纲，但没有篇幅分配或删改策略
- 处理：
  - 补齐缺失章节
  - 未补齐前不得请求最终批准

### 口头批准未写回

- 表现：
  - 用户已经在对话里同意方案，但 `Approval` 仍是 `Status: not approved`
- 处理：
  - 立即把批准结果写回 `Approval`

### 提前进入 Stage 5

- 表现：
  - 方案还未批准，就已经开始写正文
- 处理：
  - 停止写作
  - 回到 Stage 4 完成批准记录

## Stage 5 交接检查清单

- `Core Message` 已写入核心论旨与必须保留信息
- `Priority Map` 已写入重点/非重点
- `Target Outline` 已写入目标稿大纲
- `Length Allocation` 已写入篇幅分配
- `Omit / Merge Strategy` 已写入删改策略
- `Approval` 已记录 `Status: approved`

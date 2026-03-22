# Stage 5 Playbook

本文件只展开 Stage 5。全局约束、脚本职责和阶段门禁以 `SKILL.md` 为准。

## 适用范围

- 本 playbook 处理最终 LaTeX 凝缩稿的生成、整合、转写报告生成和联合校对。
- Stage 5 的正式真源是 `.paper-condenser-tmp/<document-slug>/final-draft.tex`。
- Stage 5 的正式伴随输出是 `.paper-condenser-tmp/<document-slug>/rewrite-report.md`。
- 本阶段使用一个最小 helper script 做 preflight 与骨架初始化；正文生成与整稿整合仍由 LLM 承担。

## 子步骤顺序

### 1. Drafting Preflight

- 前置条件：
  - 四个核心工件都已存在。
  - `target-settings.json.user_confirmed=true`。
  - `target-settings.json.latex_template_id` 非空。
  - `condensation-plan.md` 的 `Approval` 记录 `Status: approved`。
  - `condensation-plan.md` 已写入 `Figure / Table Plan` 与 `Reference Plan`。
- 操作：
  - 运行 `init_final_draft.py --artifact-root <ARTIFACT_ROOT>`。
  - 由 helper script 逐项核对四个核心工件、模板选择和批准状态。
  - 如果发现缺口，不继续写作，直接回退到相应阶段。

### 2. 初始化 `final-draft.tex`

- 操作：
  - 由 `init_final_draft.py` 根据 `latex_template_id` 选取 skill 内置 preset。
  - 由 `init_final_draft.py` 用对应模板建立单文件 LaTeX 骨架。
  - 在开始正文写作前，先明确标题、摘要、章节骨架和必要占位。

### 3. 分段写作

- 操作：
  - 按 `Target Outline` 的顺序逐段生成目标稿内容。
  - 每一段都必须同时遵循：
    - `Core Message`
    - `Priority Map`
    - `Length Allocation`
    - `Omit / Merge Strategy`
    - `Figure / Table Plan`
    - `Reference Plan`
    - `Target Style Guidance`
  - 不允许在局部段落写作时偏离已批准方案。

### 4. 整稿整合

- 操作：
  - 统一标题、摘要、章节标题层级、过渡关系和 LaTeX 结构。
  - 统一术语、符号和叙述口径。
  - 对已批准保留的图表、引用和参考文献做完整迁移；若无法在当前轮次精修，则保留清晰占位，而不是静默省略。

### 5. 整稿校对

- 检查项：
  - 术语一致性
  - 风格一致性
  - 目标篇幅遵循情况
  - 是否遵循 `Priority Map`
  - 是否遵循 `Omit / Merge Strategy`
  - 是否遵循 `Figure / Table Plan`
  - 是否遵循 `Reference Plan`
  - 是否保留了 `must_keep`
  - 是否违反了 `must_avoid`

### 6. 转写报告生成

- 操作：
  - 生成 `rewrite-report.md`。
  - 报告必须包含：
    - `Run Summary`
    - `Stage Decisions`
    - `Final Draft Section Map`
    - `Key Paragraph And Element Notes`
    - `Unresolved Risks / Follow-up`
  - 对最终稿的每个章节或小节都提供章节级原文参照。
  - 对关键段落、关键图表、关键引用提供更细粒度说明。

### 7. 联合校对

- 检查项：
  - `rewrite-report.md` 中的章节映射与最终稿结构一致
  - 关键段落与关键 supporting elements 的说明没有脱离真源
  - 报告没有编造原文依据或未发生的变更

### 8. 回退判定

- 如果整稿校对暴露以下问题，则回退而不是强行交付：
  - Stage 1 理解仍有关键歧义
  - Stage 2 目标设置仍不足以支撑模板或写作决策
  - Stage 3 风格指导无法覆盖关键写作选择
  - Stage 4 凝缩方案无法支撑具体段落取舍
- 只有在以上问题都不构成阻塞时，才保留 `final-draft.tex` 与 `rewrite-report.md` 作为正式交付。

## 必问条件

- 模板选择仍不明确。
- 方案虽然已批准，但用户对最终 LaTeX 呈现还有补充边界要求。
- 写作过程中发现当前方案与用户明确要求冲突。

## 禁止提问条件

- 不得把 Stage 5 变成重新收集 Stage 2 目标设置的阶段。
- 不得把 Stage 5 变成重新谈判 Stage 4 核心方案的默认入口。
- 不得在未确认存在真正阻塞缺口时，反复打断写作去追问非关键偏好。

## 常见失败场景

### 方案已批准但没有落到文件

- 表现：
  - 只在聊天中给出最终稿或转写说明，没有生成 `final-draft.tex` 或 `rewrite-report.md`
- 处理：
  - 回到 Stage 5，先建立 LaTeX 骨架，再把最终稿和转写报告都写入运行态文件

### 跳过模板初始化直接写正文

- 表现：
  - 直接输出段落内容，没有先确定 LaTeX 骨架
- 处理：
  - 回到模板初始化步骤，基于 `latex_template_id` 建立单文件框架

### 写作过程中偏离已批准方案

- 表现：
  - 最终稿与 `Priority Map`、`Length Allocation` 或 `Omit / Merge Strategy` 明显不一致
- 处理：
  - 先校对并修正；若冲突来自上游方案缺口，则回退到对应阶段

## 交付检查清单

- `final-draft.tex` 已创建
- `rewrite-report.md` 已创建
- 使用的模板与 `latex_template_id` 一致
- 正文结构与 `Target Outline` 一致
- 内容取舍与 `Priority Map`、`Omit / Merge Strategy` 一致
- 图表处理与 `Figure / Table Plan` 一致
- 引用和参考文献处理与 `Reference Plan` 一致
- 表达风格与 `Target Style Guidance` 一致
- `must_keep` 已体现
- `must_avoid` 未被违反
- 报告对每个最终稿章节或小节都提供了章节级原文参照
- 报告对关键段落或关键元素提供了更细粒度说明

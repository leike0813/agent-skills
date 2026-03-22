---
name: paper-condenser
description: 交互式学术论文凝缩转写 Skill。Use when Codex needs to guide a user through staged manuscript understanding, target-setting, style analysis, condensation planning, and only then final journal-paper drafting with explicit confirmations and persistent intermediate artifacts.
---

# Paper Condenser

## Overview

将长篇学术论文、研究报告或章节转写为期刊论文式凝缩稿时，先做确定性初始化与 intake，再做语义理解、提问、方案确认，最后才进入正式撰写。本 skill 的运行方式是强约束协作：脚本负责确定性、重复性高、可验证的工作，LLM 负责语义理解、用户交互、判断与写作。

## Input Contract

- 首版正式输入是单个 UTF-8 `.tex` 原稿文件路径。
- 只读读取原稿文件，不直接修改原文件。
- 文件路径输入场景下，必须先建立 `artifacts/<document-slug>/` 任务目录，再继续任何语义分析。
- 如果用户没有明确目标约束，必须先收集目标语言、目标体例、目标期刊类型、LaTeX 模板和目标正文长度，再继续推进。

## Hard Constraints

- 禁止一步到位直接生成目标论文全文。
- 禁止替用户做语言、体例、目标期刊、正文长度、重点取舍等关键决策。
- 禁止直接修改原稿。
- 禁止跳过阶段门禁直接进入后续阶段。
- 仅把 `paper-condenser/references/` 下的文件视为包内参考资料；仓库根 `references/` 是开发资料，不是运行时包资源。

## Script Responsibilities

- `scripts/bootstrap_runtime.py`
  - 只负责文件路径输入场景下的统一运行入口。
  - 负责生成 `document-slug`、创建 `artifacts/<document-slug>/`、初始化运行期工件、并首填充 `manuscript-profile.json` 的确定性字段。
- `scripts/init_artifacts.py`
  - 只负责在已知 `artifact-root` 的前提下创建或补齐缺失工件。
  - 负责从 `assets/artifact-templates/` 复制模板，不负责语义判断。
- `scripts/stage1_intake.py`
  - 只负责 Stage 1 的确定性 intake。
  - 负责读取单文件 `.tex` 原稿、写入 `content_preview`、`source_stats`、`intake_status`。
- `scripts/init_final_draft.py`
  - 只负责 Stage 5 的确定性 preflight 与 `final-draft.tex` 骨架初始化。
  - 负责校验四个核心工件、读取 `latex_template_id`、确认方案已批准，并从内置模板复制出 `final-draft.tex`。
- 所有脚本都只能承担确定性、重复性高、可验证的工作。

## LLM Responsibilities

- 理解原稿主题、主要工作、创新点、章节结构和可裁剪内容。
- 判断哪些内容必须保留、哪些内容可以压缩或删除。
- 询问并确认所有用户拥有决策权的事项。
- 分析原稿风格、提出修正建议、形成目标风格原则。
- 制定凝缩方案，包括重点/非重点、大纲、篇幅分配、删改策略。
- 在所有门禁满足后，根据已锁定方案撰写最终凝缩稿。

## Forbidden Delegation

- 禁止让脚本承担主题判断、研究问题理解、创新点归纳、重点/非重点决策。
- 禁止让脚本自动生成目标文稿大纲、篇幅分配或删改策略。
- 禁止让脚本替用户决定目标语言、体例、目标期刊类型、正文长度和保留项。
- 禁止让脚本承担最终写作策略和目标稿正文撰写。

## Artifact Protocol

必须维护以下四个核心工件，且职责边界不能混淆：

- `manuscript-profile.json`
  - 保存原稿事实层信息、确定性 intake 元信息，以及后续语义分析结果。
- `target-settings.json`
  - 保存用户确认后的目标约束，包括 LaTeX preset 选择。
- `style-profile.md`
  - 保存风格观察、问题诊断、修正建议和目标风格原则。
- `condensation-plan.md`
  - 保存凝缩执行方案、篇幅分配和用户批准记录。
- `final-draft.tex`
  - 保存 Stage 5 的正式 LaTeX 成稿；它不是中间工件，但它是最终输出的运行态真源。

文件路径输入场景下，优先运行统一运行入口：
`python -u paper-condenser/scripts/bootstrap_runtime.py --source-path <SOURCE_PATH>`

完成 runtime bootstrap 后，必须运行 Stage 1 intake：
`python -u paper-condenser/scripts/stage1_intake.py --artifact-root <ARTIFACT_ROOT>`

若只需要对一个已确定的工件目录做底层初始化，则运行：
`python -u paper-condenser/scripts/init_artifacts.py --artifact-root <ARTIFACT_ROOT>`

进入 Stage 5 前，必须先初始化最终稿骨架：
`python -u paper-condenser/scripts/init_final_draft.py --artifact-root <ARTIFACT_ROOT>`

## Stage Workflow

### Stage 1. 原稿理解

**Preconditions**

- 文件路径输入场景下，`artifacts/<document-slug>/` 已存在。
- `manuscript-profile.json` 已存在。

**Required Script Calls**

- 收到新的原稿文件路径时，先运行 `bootstrap_runtime.py`。
- 若已知 `artifact-root` 但工件不完整，必须运行 `init_artifacts.py`。
- 在任何语义分析前，必须运行 `stage1_intake.py` 并确认 `intake_status=complete`。

**LLM Tasks**

- 按以下顺序执行 Stage 1：
  1. 识别处理范围，判断当前输入对应整篇原稿、单章、附录式材料还是其他局部片段，并写入 `scope`。
  2. 归纳主题与核心研究问题，形成可工作的 `topic` 草案。
  3. 提炼 `main_work` 与 `novelty`，要求是结构化列表而不是口头总结。
  4. 形成 `section_outline`，至少覆盖当前处理范围内的主要章节或结构单元。
  5. 识别可疑的非核心内容并写入 `removable_candidates`。
  6. 把仍未解决的理解歧义写入 `open_questions`，而不是留在聊天上下文里。
- 只有当范围不清、文档边界不清、原稿明显过长且需要先锁定处理部分时，才向用户发起 Stage 1 提问。

**Outputs**

- 更新 `manuscript-profile.json`，至少补齐 `scope`、`topic`、`main_work`、`novelty`、`section_outline`、`removable_candidates`、`open_questions`。
- 当 Stage 1 达到可用理解草案时，把 `status` 更新为 `analysis_complete`。

**Do Not Advance Until**

- 已完成 deterministic intake。
- 已识别当前处理范围并写入 `scope`。
- `topic`、`main_work`、`novelty`、`section_outline`、`removable_candidates` 都已形成可用草案。
- `open_questions` 已作为显式列表写回工件，即使当前为空也必须保留。
- `manuscript-profile.json` 已成为 Stage 1 真源，而不是只在上下文中存在分析结论。

### Stage 2. 目标设置

**Preconditions**

- Stage 1 的基础理解已完成。

**Required Script Calls**

- 在开始正文写作前，必须先运行 `init_final_draft.py` 初始化 `final-draft.tex`。

**LLM Tasks**

- 按以下顺序执行 Stage 2：
  1. 基于 Stage 1 的原稿理解，先询问并写入 `target_language`。
  2. 询问并写入 `target_form`。
  3. 询问并写入 `target_journal_type`。
  4. 询问并写入 `latex_template_id`；首版只允许选择 skill 内置 preset。
  5. 询问并写入 `target_body_length.value` 与 `target_body_length.unit`。
  6. 询问并写入 `must_keep`。
  7. 询问并写入 `must_avoid`。
  8. 在字段逐步补齐过程中持续更新 `target-settings.json`，但在正式确认前保持 `user_confirmed=false`。
  9. 当整组设置齐备后，向用户做一次完整 readback，其中必须包含模板选择。
  10. 只有在用户明确确认整组设置后，才把 `user_confirmed` 更新为 `true`。

**Outputs**

- 更新 `target-settings.json`。

**Do Not Advance Until**

- `target_language`、`target_form`、`target_journal_type`、`target_body_length`、`must_keep`、`must_avoid` 都已写入。
- `latex_template_id` 已写入。
- 已对整组设置做过完整 readback。
- 用户已明确确认，且 `user_confirmed=true`。

### Stage 3. 风格画像

**Preconditions**

- Stage 1 的原稿理解已完成。
- `target-settings.json` 已完成整组确认，且 `user_confirmed=true`。

**Required Script Calls**

- 无新增必调脚本。

**LLM Tasks**

- 按以下顺序执行 Stage 3：
  1. 基于 Stage 1 与 Stage 2 的结果审视原稿的表达风格、结构习惯、语气和论述方式。
  2. 在 `Source Style` 中记录原稿已有的风格特征、优点、惯用表达和结构习惯。
  3. 在 `Problems To Fix` 中记录需要纠正的风格、规范、语气或表达问题。
  4. 在 `Target Style Guidance` 中形成面向目标稿的可执行写作原则和风格指导。
  5. 在 `Open Questions` 中记录仍需用户确认的风格偏好、语气边界或规范选择。
- 只有在风格偏好、语气边界或表达规范存在不确定性时，才向用户发起 Stage 3 提问。

**Outputs**

- 更新 `style-profile.md`。

**Do Not Advance Until**

- `Source Style` 已写入原稿风格特征。
- `Problems To Fix` 已写入明确问题。
- `Target Style Guidance` 已写入可执行指导。
- `Open Questions` 已写入未决风格问题；若当前无未决项，也必须保留该章节。

### Stage 4. 凝缩方案

**Preconditions**

- 已具备原稿理解、目标设置和风格画像。

**Required Script Calls**

- 无新增必调脚本。

**LLM Tasks**

- 按以下顺序执行 Stage 4：
  1. 基于 Stage 1 到 Stage 3 的结果锁定目标稿必须保留的核心信息。
  2. 在 `Core Message` 中记录目标稿的核心论旨与必须保留的信息。
  3. 在 `Priority Map` 中记录重点/非重点和保留优先级。
  4. 在 `Target Outline` 中记录目标稿大纲。
  5. 在 `Length Allocation` 中记录各部分篇幅分配。
  6. 在 `Omit / Merge Strategy` 中记录压缩、合并、删除策略。
  7. 在 `Approval` 中记录当前是否获得用户批准；仅在用户明确批准后将 `Status` 更新为 `approved`。
- 只有在方案收敛或批准存在不确定性时，才向用户发起 Stage 4 提问。

**Outputs**

- 更新 `condensation-plan.md`。

**Do Not Advance Until**

- `Core Message`、`Priority Map`、`Target Outline`、`Length Allocation`、`Omit / Merge Strategy` 都已写入可执行内容。
- `Approval` 已显式记录 `Status: approved`。

### Stage 5. 最终撰写

**Preconditions**

- 四个核心工件齐备。
- `target-settings.json` 已确认。
- `target-settings.json.latex_template_id` 非空。
- `condensation-plan.md` 已记录用户批准。

**Required Script Calls**

- 无新增必调脚本。

**LLM Tasks**

1. 先通过 `init_final_draft.py` 执行 drafting preflight，并初始化 `final-draft.tex` 的单文件骨架。
2. 按 `Target Outline` 顺序逐段写作，把内容持续落到 `final-draft.tex`。
3. 完成整稿整合，统一标题、摘要、章节层级、过渡关系和 LaTeX 结构。
4. 做整稿校对，检查术语一致性、风格一致性、长度分配遵循情况，以及是否满足 `must_keep` / `must_avoid`。
5. 若发现上游工件仍有关键缺口，暂停最终写作并回到相应阶段补齐；否则保留 `final-draft.tex` 作为正式成稿。

**Outputs**

- 生成 `artifacts/<document-slug>/final-draft.tex` 作为正式成稿。

**Do Not Advance Until**

- 已确认不存在未补齐的关键方案缺口。
- `final-draft.tex` 已落盘。

## Question Policy

- 只要遇到用户拥有决策权的事项，就必须提问，不得自行假定。
- 每一阶段优先问完成该阶段所需的最少问题，避免一次抛出过多无关问题。
- Stage 1 只允许询问原稿范围、边界、章节归属和理解阻塞点，不得提前询问目标语言、目标体例、目标期刊类型或目标篇幅。
- 如果 Stage 1 存在未决但不阻塞进入下一阶段的问题，先把它们写入 `manuscript-profile.json.open_questions`。
- Stage 2 只允许询问目标语言、目标体例、目标期刊类型、LaTeX 模板选择、目标正文长度、`must_keep` 和 `must_avoid`，不得提前进入风格画像或凝缩方案。
- Stage 2 的模板选择只允许使用 skill 内置 preset，不接受首版外部模板路径。
- Stage 2 收集到部分设置后，应先回写 `target-settings.json`，再继续补齐剩余字段；没有完整 readback 和明确确认前，不得把 `user_confirmed` 置为 `true`。
- Stage 3 只允许询问风格偏好、语气边界、表达规范和修辞层面的取舍，不得提前进入 Stage 4 的重点/非重点、大纲或篇幅分配讨论。
- 如果 Stage 3 存在未决但不阻塞进入下一阶段的风格问题，先把它们写入 `style-profile.md` 的 `Open Questions`。
- Stage 4 只允许询问核心信息保留、重点/非重点、大纲、篇幅分配、删改策略和方案批准，不得提前进入最终撰写。
- 如果 Stage 4 仍未获得明确批准，先把结果写回 `condensation-plan.md`，保持 `Approval` 为 `Status: not approved`。
- Stage 5 只允许处理最终 LaTeX 撰写、整稿整合、整稿校对和必要的回退判定，不得把 Stage 5 变成重新谈判 Stage 2-4 的默认入口。
- 如果发现原稿风格、结构或规范存在明显问题，可以提出建议，但建议不能替代用户确认。
- 如果用户试图跳过分析和方案确认，明确说明当前缺失的工件或确认项，并把流程拉回到最近未完成阶段。

## Drafting Gate

只有同时满足以下条件，才允许进入最终撰写阶段：

- `artifacts/<document-slug>/manuscript-profile.json` 已形成可用版本。
- `artifacts/<document-slug>/target-settings.json` 中关键目标设置已获得用户确认。
- `artifacts/<document-slug>/target-settings.json` 中 `latex_template_id` 已明确。
- `artifacts/<document-slug>/style-profile.md` 已总结出可执行的风格指导。
- `artifacts/<document-slug>/condensation-plan.md` 已记录目标大纲、篇幅分配和用户批准。
- `artifacts/<document-slug>/final-draft.tex` 是正式成稿的运行态真源。

只要其中任一条件不成立，就继续分析、提问或修订方案，不得生成最终凝缩稿。

## Resources

- `references/stage-workflow.md`：分阶段配方与门禁的展开说明。
- `references/artifact-protocol.md`：四个工件的最小字段、内容边界和更新时间。
- `references/stage1-playbook.md`：Stage 1 子步骤、提问边界、失败处理与交接检查清单。
- `references/stage2-playbook.md`：Stage 2 子步骤、提问顺序、失败处理与交接检查清单。
- `references/stage3-playbook.md`：Stage 3 子步骤、提问边界、失败处理与交接检查清单。
- `references/stage4-playbook.md`：Stage 4 子步骤、提问边界、失败处理与交接检查清单。
- `references/stage5-playbook.md`：Stage 5 LaTeX 模板初始化、分段写作、整稿整合、整稿校对与回退判定。
- `references/SCI_paper_guidance.md`：SCI 论文体例、IMRaD 结构、图表与引文规范参考；在判断英文期刊稿的结构和表达规范时按需查阅。
- `references/Chinese_paper_guidance.md`：中文期刊论文体例、摘要/图表/参考文献规范参考；在判断中文期刊稿的结构和表达规范时按需查阅。
- `assets/artifact-templates/`：四个运行期工件的初始化模板。
- `assets/latex-templates/`：Stage 5 使用的内置单文件 LaTeX preset。
- `scripts/bootstrap_runtime.py`：文件路径输入场景的统一运行入口。
- `scripts/stage1_intake.py`：单文件 `.tex` 原稿的 Stage 1 确定性 intake 入口。
- `scripts/init_artifacts.py`：正式工件初始化入口。
- `scripts/init_final_draft.py`：Stage 5 的最终稿骨架初始化入口。

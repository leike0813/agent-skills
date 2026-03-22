# Stage Workflow

本文件是 `SKILL.md` 中执行契约的配方展开版。硬约束以 `SKILL.md` 为准；本文件只补充每阶段的操作视角，不改变主契约。

## Stage 1. 原稿理解

### Preconditions

- 文件路径输入场景下，已存在 `artifacts/<document-slug>/`。
- `manuscript-profile.json` 已存在。

### Required Script Calls

- 新的原稿文件路径进入流程：先调用 `bootstrap_runtime.py`。
- 已知 `artifact-root` 但工件不完整：调用 `init_artifacts.py`。
- 任何语义分析前：调用 `stage1_intake.py`，并确认 `intake_status=complete`。

### LLM Tasks

1. 锁定处理范围，判断当前输入对应整篇、章节、附录式材料还是局部片段。
2. 归纳主题与核心研究问题，形成可工作的 `topic` 草案。
3. 提炼 `main_work`，要求每项工作都可独立陈述。
4. 提炼 `novelty`，允许是初步判断，但不得留空。
5. 形成 `section_outline`，至少覆盖主要章节或结构单元。
6. 识别 `removable_candidates`，列出可能压缩、合并或删除的非核心内容。
7. 把当前仍未解决的理解歧义写入 `open_questions`。

### Stage 1 Question Triggers

- 原稿显然不是整篇论文，而用户没有说明处理边界。
- 文件包含多个可选处理对象，当前无法判断哪个才是目标内容。
- 当前章节或片段脱离上下文后无法判断其研究定位。
- 原稿过长，继续分析前需要用户指定处理范围。

### Stage 1 Question Boundaries

- Stage 1 可以询问原稿范围、边界、章节归属和理解阻塞点。
- Stage 1 不得提前询问目标语言、目标文体、目标期刊类型、目标正文长度。

### Outputs

- 更新 `manuscript-profile.json` 中的 `scope`、`topic`、`main_work`、`novelty`、`section_outline`、`removable_candidates`、`open_questions`。
- 当形成可用理解草案时，把 `status` 更新为 `analysis_complete`。

### Do Not Advance Until

- 已完成 deterministic intake。
- 已识别当前处理范围。
- 已形成非空的 `topic`、`main_work`、`novelty`、`section_outline`、`removable_candidates` 草案。
- `open_questions` 已作为显式列表写回工件，即使当前为空也必须保留。
- 所有未决问题都已写回工件，而不是只留在对话中。

## Stage 2. 目标设置

### Preconditions

- Stage 1 已完成基础理解。

### Required Script Calls

- 在开始正文写作前，先调用 `init_final_draft.py` 初始化 `final-draft.tex`。

### LLM Tasks

1. 询问并写入 `target_language`。
2. 询问并写入 `target_form`。
3. 询问并写入 `target_journal_type`。
4. 询问并写入 `latex_template_id`。
5. 询问并写入 `target_body_length.value` 与 `target_body_length.unit`。
6. 询问并写入 `must_keep`。
7. 询问并写入 `must_avoid`。
8. 在正式确认前持续回写 `target-settings.json`，保持 `user_confirmed=false`。
9. 当整组设置齐备后，对用户做一次完整 readback，其中必须包含模板选择。
10. 仅在用户明确确认后，把 `user_confirmed` 更新为 `true`。

### Stage 2 Question Triggers

- 任一核心目标设置字段仍为空。
- `latex_template_id` 尚未确定。
- `must_keep` 或 `must_avoid` 尚未收敛。
- 已完成部分填写，但尚未做整组 readback。
- 用户改变前面已经给出的目标设置。

### Stage 2 Question Boundaries

- Stage 2 只处理目标设置与保留/避免项。
- Stage 2 不提前进入风格画像。
- Stage 2 不提前进入重点/非重点、目标大纲或篇幅分配讨论。

### Outputs

- 更新 `target-settings.json`。

### Do Not Advance Until

- `target_language`、`target_form`、`target_journal_type`、`target_body_length`、`must_keep`、`must_avoid` 都已写入。
- `latex_template_id` 已写入。
- 已做完整 readback。
- `user_confirmed=true`。

## Stage 3. 风格画像

### Preconditions

- Stage 1 已完成关键前置。
- `target-settings.json` 已完成整组确认，且 `user_confirmed=true`。

### Required Script Calls

- 无。

### LLM Tasks

1. 审视原稿的表达风格、结构习惯、语气和论述方式。
2. 在 `Source Style` 中记录已有风格特征、优点和惯用表达。
3. 在 `Problems To Fix` 中记录需要纠正的风格、规范和表达问题。
4. 在 `Target Style Guidance` 中形成面向目标稿的可执行风格原则。
5. 在 `Open Questions` 中记录仍未确认的风格偏好或表达边界。

### Stage 3 Question Triggers

- 风格偏好、语气边界或表达规范存在歧义。
- 当前原稿存在多种可选风格方向，无法自行判断用户更偏好的取向。
- 某些需要纠偏的问题是否保留，取决于用户的明确偏好。

### Stage 3 Question Boundaries

- Stage 3 只处理风格观察、问题诊断、修正建议和风格偏好确认。
- Stage 3 不提前进入 Stage 4 的重点/非重点讨论。
- Stage 3 不提前进入目标大纲、篇幅分配或删改策略讨论。

### Outputs

- 更新 `style-profile.md`。

### Do Not Advance Until

- `Source Style` 已写入原稿风格特征。
- `Problems To Fix` 已写入明确问题。
- `Target Style Guidance` 已写入可执行指导。
- `Open Questions` 已显式保留并记录未决风格问题。

## Stage 4. 凝缩方案

### Preconditions

- 原稿理解、目标设置、风格画像都已具备。

### Required Script Calls

- 无。

### LLM Tasks

1. 锁定目标稿必须保留的核心信息。
2. 在 `Core Message` 中记录核心论旨与必须保留的信息。
3. 在 `Priority Map` 中记录重点/非重点和优先级。
4. 在 `Target Outline` 中形成目标稿大纲。
5. 在 `Length Allocation` 中记录各部分篇幅分配。
6. 在 `Omit / Merge Strategy` 中记录压缩、合并、删除策略。
7. 在 `Approval` 中记录是否已获用户批准。

### Stage 4 Question Triggers

- 重点/非重点尚未收敛。
- 目标大纲存在多个可行版本。
- 篇幅分配依赖用户取舍。
- 删改策略会影响用户要求保留的重点。
- 当前方案已成形，但还未得到明确批准。

### Stage 4 Question Boundaries

- Stage 4 只处理方案收敛与批准。
- Stage 4 不提前进入最终撰写。

### Outputs

- 更新 `condensation-plan.md`。

### Do Not Advance Until

- `Core Message`、`Priority Map`、`Target Outline`、`Length Allocation`、`Omit / Merge Strategy` 都已写入可执行内容。
- `Approval` 已显式记录 `Status: approved`。

## Stage 5. 最终撰写

### Preconditions

- 四个核心工件齐备。
- `target-settings.json` 已确认。
- `target-settings.json.latex_template_id` 非空。
- `condensation-plan.md` 已记录用户批准。

### Required Script Calls

- 无。

### LLM Tasks

1. 先通过 `init_final_draft.py` 执行 drafting preflight，并初始化 `final-draft.tex` 的单文件骨架。
2. 按 `Target Outline` 顺序逐段写作，把内容持续落到 `final-draft.tex`。
3. 完成整稿整合，统一标题、摘要、章节层级、过渡关系和 LaTeX 结构。
4. 做整稿校对，检查术语一致性、风格一致性、长度分配遵循情况以及方案遵循情况。
5. 若发现上游工件仍有关键缺口，回退到相应阶段补齐，而不是继续把当前稿件视为正式成稿。

### Outputs

- 生成并保留 `artifacts/<document-slug>/final-draft.tex`。

### Do Not Advance Until

- 已确认不存在未补齐的关键方案缺口。
- `final-draft.tex` 已作为单文件 LaTeX 成稿落盘。

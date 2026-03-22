# Artifact Protocol

所有工件都放在 `artifacts/<document-slug>/` 下。`<document-slug>` 默认基于原稿文件名生成；如果文件名不稳定或不适合作为标识，要求用户提供一个短名称。

## manuscript-profile.json

### 用途

- 保存原稿事实层信息和提炼性判断。

### 最小字段

```json
{
  "source_id": "",
  "source_path": "",
  "source_type": "",
  "scope": "",
  "content_preview": "",
  "source_stats": {
    "char_count": 0,
    "line_count": 0,
    "file_size_bytes": 0
  },
  "intake_status": "pending",
  "topic": "",
  "main_work": [],
  "novelty": [],
  "section_outline": [],
  "removable_candidates": [],
  "open_questions": [],
  "status": "draft"
}
```

### 更新时间

- 第一次完成原稿理解后创建。
- 当原稿范围、主题判断或结构提取发生变化时更新。

### Intake 层字段

- `content_preview`：只读预览文本，用于在真正语义分析前快速建立确定性上下文。
- `source_stats`：源文件的确定性统计信息，至少包括 `char_count`、`line_count`、`file_size_bytes`。
- `intake_status`：Stage 1 intake 的状态标记；初始化模板默认为 `pending`，完成 intake 后更新为 `complete`。

这些字段属于确定性 intake 层，不代表任何主题判断、结构理解或学术结论。

### Stage 1 语义层字段

- `scope`：Stage 1 必填。用于说明当前处理对象是整篇论文、单章、附录式材料还是其他局部范围。
- `topic`：Stage 1 必填。要求形成可工作的主题归纳，而不是空泛标签。
- `main_work`：Stage 1 必填。必须是结构化列表，记录论文的主要工作或主要贡献动作。
- `novelty`：Stage 1 必填。允许为初步判断，但 Stage 1 完成时不得为空。
- `section_outline`：Stage 1 必填。至少覆盖当前处理范围内的主要章节或结构单元。
- `removable_candidates`：Stage 1 必填。列出当前判断下可能压缩、合并或删除的非核心内容候选。
- `open_questions`：Stage 1 必填。记录未决但尚不阻塞推进的问题，不能只留在聊天上下文中。
- `status`：Stage 1 完成前可为 `draft` 或 `initialized`；形成可用理解草案后更新为 `analysis_complete`。

### Stage 1 最小完成标准

Stage 1 可以进入下一阶段时，`manuscript-profile.json` 至少满足以下条件：

- `intake_status` 已为 `complete`
- `scope` 非空
- `topic` 非空
- `main_work` 非空
- `novelty` 非空
- `section_outline` 非空
- `removable_candidates` 已列出候选
- `open_questions` 已显式记录当前未决问题，即使为空列表也应作为真源保留
- `status` 为 `analysis_complete`

### 字段来源边界

- 脚本负责 `source_id`、`source_path`、`source_type`、`content_preview`、`source_stats`、`intake_status` 等确定性字段。
- LLM 负责 `scope`、`topic`、`main_work`、`novelty`、`section_outline`、`removable_candidates`、`open_questions`、`status` 的语义层更新。
- LLM 不得把 Stage 1 语义结果只保留在对话中而不写回 JSON。

## target-settings.json

### 用途

- 保存用户明确确认过的目标稿约束。

### 最小字段

```json
{
  "target_language": "",
  "target_form": "",
  "target_journal_type": "",
  "latex_template_id": "",
  "target_body_length": {
    "value": 0,
    "unit": ""
  },
  "must_keep": [],
  "must_avoid": [],
  "user_confirmed": false
}
```

### 更新时间

- 每当用户确认或修改目标设置时更新。
- `user_confirmed` 只能在关键设置完整后置为 `true`。

### Stage 2 字段语义

- `target_language`：目标稿语言。Stage 2 完成前不得留空。
- `target_form`：目标稿体例或文体类型。Stage 2 完成前不得留空。
- `target_journal_type`：目标投稿对象的期刊类型或刊物类别。Stage 2 完成前不得留空。
- `latex_template_id`：目标稿使用的 LaTeX preset 标识。Stage 2 完成前不得留空；首版仅允许选择 skill 内置模板。
- `target_body_length.value` 与 `target_body_length.unit`：目标正文长度及其单位。Stage 2 完成前必须同时写入。
- `must_keep`：用户明确要求必须保留的信息、内容或约束。
- `must_avoid`：用户明确要求避免出现的内容、表达或结构。
- `user_confirmed`：Stage 2 唯一正式完成标记。只有在整组设置做过完整 readback 且用户明确确认后，才能更新为 `true`。

### Stage 2 草案态与确认态

- 不扩充 schema 的前提下，Stage 2 草案态通过“字段部分填写 + `user_confirmed=false`”表达。
- 只要任一关键字段为空，或 `must_keep` / `must_avoid` 尚未收敛，Stage 2 仍视为未完成。
- 即使所有字段都已暂时写入，只要还没做完整 readback 并得到明确确认，`user_confirmed` 仍必须保持为 `false`。
- 用户修改任一已确认设置后，应立即把 `user_confirmed` 恢复为 `false`，直到新的整组设置重新确认。

### 内置 LaTeX Template Presets

- `generic-article`：通用单文件 article 骨架，适合中性学术稿件。
- `generic-cn-journal`：通用中文期刊单文件骨架。
- `generic-en-journal`：基于 `elsarticle` 的通用英文期刊单文件骨架。

这些 preset 都位于 `assets/latex-templates/`，首版不支持外部模板路径，也不支持多文件模板工程。

## style-profile.md

### 用途

- 保存风格观察、问题诊断和面向目标稿的写作建议。

### 建议结构

- `## Source Style`
- `## Problems To Fix`
- `## Target Style Guidance`
- `## Open Questions`

### 更新时间

- 完成风格分析后创建。
- 当用户补充风格偏好，或风格建议需要修正时更新。

### Stage 3 章节语义

- `Source Style`：记录原稿已有的风格特征、优点、惯用表达和结构习惯。
- `Problems To Fix`：记录需要纠偏的风格、规范、语气或表达问题。
- `Target Style Guidance`：记录目标稿应遵循的写作原则、风格方向和表达约束。
- `Open Questions`：记录尚未明确的风格偏好、语气边界或规范选择。

### Stage 3 完成规则

- 不修改模板结构的前提下，Stage 3 的完成态通过四个章节都已写入可执行内容来判断。
- 只写 `Source Style` 而没有 `Problems To Fix` 或 `Target Style Guidance`，不视为 Stage 3 完成。
- 未决风格问题必须写入 `Open Questions`，不能只停留在聊天上下文中。
- 即使当前没有未决风格问题，`Open Questions` 章节也必须显式保留。

## condensation-plan.md

### 用途

- 保存最终撰写前的凝缩执行方案。

### 建议结构

- `## Core Message`
- `## Priority Map`
- `## Target Outline`
- `## Length Allocation`
- `## Omit / Merge Strategy`
- `## Approval`

### 更新时间

- 每轮方案收敛后更新。
- `## Approval` 段必须明确记录用户是否已批准当前方案。

### Stage 4 章节语义

- `Core Message`：记录目标稿必须保留的核心信息和核心论旨。
- `Priority Map`：记录重点/非重点与保留优先级。
- `Target Outline`：记录目标稿的大纲结构。
- `Length Allocation`：记录各部分篇幅分配。
- `Omit / Merge Strategy`：记录压缩、合并、删除策略。
- `Approval`：记录批准状态，使用 `Status: not approved|approved`。

### Stage 4 完成规则

- 不修改模板结构的前提下，Stage 4 的完成态通过五个方案章节都已写入可执行内容，再加上 `Approval` 记录 `Status: approved` 来判断。
- 只写部分方案章节，不视为 Stage 4 完成。
- 用户批准必须写回 `Approval`，不能只停留在聊天上下文中。
- `Approval` 继续只使用现有 `Status: not approved|approved` 状态行，不新增其他状态字段。

## final-draft.tex

### 用途

- 保存 Stage 5 的正式 LaTeX 成稿。

### 运行态位置

- `artifacts/<document-slug>/final-draft.tex`

### 生成前提

- 四个核心工件齐备。
- `target-settings.json.user_confirmed=true`
- `target-settings.json.latex_template_id` 非空。
- `condensation-plan.md` 的 `Approval` 记录 `Status: approved`。

### Stage 5 生成规则

- `final-draft.tex` 是 Stage 5 的运行态真源，不是聊天输出的附属副本。
- `final-draft.tex` 的骨架应先通过 `scripts/init_final_draft.py` 初始化。
- 初始骨架应基于 `assets/latex-templates/` 中与 `latex_template_id` 对应的 preset 建立。
- 正文内容必须遵循 `Target Outline`、`Priority Map`、`Length Allocation`、`Omit / Merge Strategy` 和 `Target Style Guidance`。
- 若 Stage 5 发现上游工件仍存在关键缺口，应回退到对应阶段，而不是把缺口静默吞掉。

## 边界规则

- JSON 工件存事实、约束、枚举式结论，不存大段自由分析。
- Markdown 工件存解释、判断、建议和方案，不替代 JSON 里的结构化约束。
- 如果某条信息既是事实又要用于方案判断，事实写入 JSON，解释写入 Markdown，不重复堆砌相同文本。

## 模板与运行态文件的关系

- `assets/artifact-templates/` 下的四个文件是包内初始化模板，不是运行中的任务状态。
- 开始处理一份新原稿时，先把同名模板复制到 `artifacts/<document-slug>/`，再在该任务目录内更新运行态文件。
- 运行过程中修改的是 `artifacts/<document-slug>/` 下的副本，而不是包内模板。

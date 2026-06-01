# Runtime Protocol

## Purpose

本文件定义 `paper-reviewer` 的可恢复执行协议。只有在需要阶段细则、恢复运行、处理 blocker 或确认是否可以导出时读取本文件。

## Resume Rule

恢复已有审稿运行时：

1. 不凭对话历史继续。
2. 先运行 `status`。
3. 如果 `pending_confirmations` 非空，先处理确认项。
4. 如果当前阶段不清楚，运行 `instructions --stage <current_stage>`。
5. 只写入当前阶段或已完成阶段允许补充的记录；不要写 future-stage 记录。

```bash
uv run --project="$HOME/.ar" --locked -- python paper-reviewer/scripts/review_runtime.py status --run-root <RUN_ROOT>
uv run --project="$HOME/.ar" --locked -- python paper-reviewer/scripts/review_runtime.py instructions --run-root <RUN_ROOT> --stage <STAGE>
```

## Stage Contract

### S0_INIT

Goal: 创建运行态并记录 source metadata。

Allowed records: none. `init` 只写 manifest。

Completion: `init` 成功返回 `run_root`，manifest 进入 `S1_PROFILE_AND_SCOPE`。

Do not: 在本阶段写审稿判断。

### S1_PROFILE_AND_SCOPE

Goal: 建立论文画像，判断领域，确认审稿范围。

Required semantic work:

- 读取原稿足够部分以识别标题、摘要、章节、研究对象、方法类型和证据类型。
- 基于论文内容和 `taxonomy.md` 初判 canonical domain name。
- 确认用户是否需要全文审阅、局部审阅或特定重点。

Allowed records:

- `paper_profile`
- `section_map`
- `decision` with `domain_confirmation`
- `decision` with `scope_confirmation`
- `open_question`

Completion: `paper_profile` 已写入，且 domain / scope confirmation 都已清空。

Do not: 在论文画像之前要求用户确认一个没有依据的领域分类。

### S2_DEEP_UNDERSTANDING

Goal: 形成可执行理解，避免在理解不足时直接审稿。

Required semantic work:

- 记录研究问题、贡献主张、方法/材料/数据、关键结果、局限和章节功能。
- 标记后续审稿需要重点检查的证据链。
- 如果论文材料不足，写入 `open_question`。

Allowed records:

- `stage_summary` for `S2_DEEP_UNDERSTANDING`
- `open_question`
- 必要时补充 `paper_profile`

Completion: 写入 S2 `stage_summary`。

Do not: 从 S2 直接跳到最终报告。

### S3_MACRO_REVIEW

Goal: 审阅标题、摘要、研究问题、贡献、结构和整体论证路线。

Required semantic work:

- 对每个检查对象运行 `reference_guide.py nav --review-stage macro`。
- 只在需要具体标准时运行 `show`。
- 将每个宏观问题写成独立 `finding`。

Allowed records:

- `finding` with `stage=S3_MACRO_REVIEW`
- `stage_summary` for `S3_MACRO_REVIEW`
- `open_question`

Completion: 当前范围内宏观检查完成，并写入 S3 `stage_summary`。

Do not: 把标题、摘要、结构问题合并成无法定位的一条泛泛意见。

### S4_MICRO_REVIEW

Goal: 按章节或指定范围审阅段落级和章节级问题。

Required semantic work:

- 对每个章节 pass 运行 `reference_guide.py nav --review-stage micro --paper-section <section>`.
- 审阅 `introduction` 或 `literature` 时，通过 `nav` 中的 cross-cutting review topics，或 `reference_guide.py topic show --topic scientific-introduction-related-work`，检查问题定位、相关工作组织、研究缺口、引用支撑和作者判断。
- 定位具体段落、图表、公式、实验设置或论证环节。
- 每条问题包含位置、论文证据、影响和修订方向。

Allowed records:

- `finding` with `stage=S4_MICRO_REVIEW`
- `stage_summary` for `S4_MICRO_REVIEW`
- `open_question`

Completion: 当前范围内微观检查完成，并写入 S4 `stage_summary`。

Do not: 把语言润色、格式规范问题混入主要微观论证问题，除非它直接影响理解或证据强度；不要把 Introduction / Related Work topic 写成模板套用要求，finding 必须回到论文原文证据。

### S5_FORMAL_REVIEW

Goal: 审阅形式、语言、图表、参考文献格式线索、伦理/合规、可复现性线索，并做一次 AI-style diagnostics pass。

Required semantic work:

- 只记录可在论文材料中定位的问题。
- 将外部核验需求写为 `open_question`，不要在基础运行态中假装已经核验。
- 对领域特定报告规范使用 `reference_guide.py nav --review-stage formal`。
- 审阅 `references` 时，通过 `reference_guide.py nav --review-stage formal --paper-section references` 中的 cross-cutting review topics，或 `reference_guide.py topic show --topic bibliography-format-diagnostics`，识别可见参考文献条目的格式、著录、切分、一致性和抽取噪声问题。
- 通过 `reference_guide.py nav --review-stage formal` 中的 cross-cutting review topics，或 `reference_guide.py topic show --topic ai-style-diagnostics`，检查模板化表达、低信息密度、过度圆滑、作者判断不足和 AI 使用合规线索。
- AI-style diagnostics finding 只能表述为风格、信息密度、作者判断或合规风险问题；不要写成 AI 代写判定。

Allowed records:

- `finding` with `stage=S5_FORMAL_REVIEW`
- `stage_summary` for `S5_FORMAL_REVIEW`
- `open_question`

Completion: 写入 S5 `stage_summary` 后，runtime 会加入 `report_export_confirmation` pending item 并进入 S6。

Do not: 对参考文献真实性、DOI、期刊信息做未联网验证的断言；不要臆造缺失的参考文献元数据；不要建议降低 AI 率、绕过 AI 检测、加入口语噪声、错别字或随机不流畅。

### S6_SYNTHESIS_CONFIRMATION

Goal: 导出前汇总 findings，并获得用户确认。

Required semantic work:

- 汇总 major/minor/note findings。
- 指出低置信度问题和仍开放的问题。
- 问用户是否基于当前发现导出，或是否继续补审某部分。

Allowed records:

- `stage_summary` for `S6_SYNTHESIS_CONFIRMATION`
- `decision` with `report_export_confirmation`
- 必要时将 findings 标记为 `confirmed` / `dismissed`

Completion: 用户确认导出，写入 `report_export_confirmation` 且 pending confirmations 清空。

Do not: 在用户还要求补审时导出最终报告。

### S7_REPORT_EXPORT

Goal: 从结构化记忆生成审稿报告草稿。

Required action:

```bash
uv run --project="$HOME/.ar" --locked -- python paper-reviewer/scripts/review_runtime.py export --run-root <RUN_ROOT>
```

Completion: `artifacts/review-report.md` 存在，manifest 进入 `S8_DONE`。

Do not: 回读长参考文档拼接报告，也不要添加没有 finding 支撑的新问题。

### S8_DONE

Goal: 运行完成。

Required action: 报告 `review-report.md` 路径和导出概况。

Do not: 主动开启新审稿运行；除非用户明确要求补审或重新审阅。

## Confirmation Rules

必须确认：

- domain：论文领域分类会影响参考标准选择。
- scope：全文审阅、局部审阅或特定重点会影响工作量和 findings 范围。
- report export：最终导出前需确认是否还有补审需求。

可以直接推进：

- 用户已经明确给出领域、范围和“直接导出/按当前结果生成”。
- 当前确认项只是对用户已明确指令的结构化记录。

## Completion Definition

一次审稿运行完成需满足：

- manifest `current_stage` 为 `S8_DONE`。
- `pending_confirmations` 为空。
- `artifacts/review-report.md` 已生成。
- 最终报告中的每个问题都能追溯到 `finding.paper_evidence`。

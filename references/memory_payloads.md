# Memory Payloads

## Purpose

本文件定义 `review_runtime.py update` 接受的记录类型、枚举值和 payload 示例。准备写入 runtime 记忆、修复 schema 错误或需要构造 payload 时读取本文件。

所有 payload 都通过文件传入：

```bash
uv run --project="$HOME/.ar" --locked -- python paper-reviewer/scripts/review_runtime.py update --run-root <RUN_ROOT> --payload-file <PAYLOAD_JSON>
```

需要脚本生成最小模板时：

```bash
uv run --project="$HOME/.ar" --locked -- python paper-reviewer/scripts/review_runtime.py template --record-type finding
```

## Enumerations

Stages:

- `S0_INIT`
- `S1_PROFILE_AND_SCOPE`
- `S2_DEEP_UNDERSTANDING`
- `S3_MACRO_REVIEW`
- `S4_MICRO_REVIEW`
- `S5_FORMAL_REVIEW`
- `S6_SYNTHESIS_CONFIRMATION`
- `S7_REPORT_EXPORT`
- `S8_DONE`

Record types:

- `paper_profile`
- `section_map`
- `stage_summary`
- `finding`
- `decision`
- `open_question`

Finding severity:

- `major`
- `minor`
- `note`

Finding confidence:

- `high`
- `medium`
- `low`

Finding status:

- `candidate`
- `confirmed`
- `dismissed`

Decision types:

- `domain_confirmation`
- `scope_confirmation`
- `report_export_confirmation`

Open question status:

- `open`
- `answered`
- `dismissed`

## Record Payloads

### `paper_profile`

Use when: S1 建立或修正论文画像。

Minimum payload:

```json
{
  "record_type": "paper_profile",
  "title": "Paper title",
  "abstract": "One-paragraph abstract summary or original abstract summary.",
  "sections": ["Abstract", "Introduction", "Methods", "Results", "Discussion"],
  "research_question": "What the paper tries to answer.",
  "contribution_claims": ["Claim 1", "Claim 2"],
  "method_summary": "Method, data, material, proof, or argument structure.",
  "evidence_type": "experimental results"
}
```

Notes:

- `title` and non-empty `sections` are required.
- Do not store the whole manuscript or long abstract text.

### `section_map`

Use when: 需要标准化章节 id，方便逐章节审阅。

Minimum payload:

```json
{
  "record_type": "section_map",
  "sections": [
    {
      "section_id": "introduction",
      "title": "Introduction",
      "location": "Section 1"
    },
    {
      "section_id": "method",
      "title": "Methods",
      "location": "Section 2"
    }
  ]
}
```

Notes:

- 每个 section 必须包含非空 `section_id` 和 `title`。
- `section_id` 尽量使用 reference navigation 支持的 paper-section id。

### `stage_summary`

Use when: 当前阶段语义工作完成，需要推进 manifest。

Minimum payload:

```json
{
  "record_type": "stage_summary",
  "stage": "S3_MACRO_REVIEW",
  "summary": "Macro review completed for title, abstract, research question, contribution claims, and structure.",
  "completed_checks": ["title", "abstract", "contribution", "structure"]
}
```

Notes:

- `stage` 不能是 future stage。
- 写入 S5 summary 后 runtime 会进入 S6 并要求导出确认。

### `finding`

Use when: 发现一个可定位、可解释、可操作的审稿问题。

Minimum payload:

```json
{
  "record_type": "finding",
  "finding_id": "F-S3-001",
  "stage": "S3_MACRO_REVIEW",
  "paper_section": "abstract",
  "severity": "major",
  "issue_type": "contribution_overclaim",
  "location": "Abstract, final sentence",
  "claim": "The abstract claims a general solution but the experiments only cover one dataset.",
  "paper_evidence": "The abstract says the method is broadly applicable; the Results section reports only Dataset A.",
  "impact": "Readers may overestimate the scope and validity of the contribution.",
  "suggested_revision": "Limit the claim to the evaluated setting or add evidence across additional datasets.",
  "confidence": "high",
  "status": "candidate"
}
```

Notes:

- `paper_evidence` 可以是字符串或非空字符串数组。
- `paper_evidence` 必须来自论文材料本身，不得来自参考指南。
- 一条 finding 只表达一个主要问题；不要把多个无关问题塞进同一条。

### `decision`

Use when: 用户确认高影响决策，或用户已在指令中明确给出决策，需要结构化记录。

Minimum payload:

```json
{
  "record_type": "decision",
  "decision_type": "scope_confirmation",
  "value": "Full manuscript review, with extra attention to methods and results.",
  "rationale": "User requested a full review."
}
```

Export confirmation payload:

```json
{
  "record_type": "decision",
  "decision_type": "report_export_confirmation",
  "value": true,
  "rationale": "User confirmed export based on current findings."
}
```

Notes:

- `value` 不能为空。
- `report_export_confirmation.value` 用 `true` 或明确确认语义。

### `open_question`

Use when: 论文材料不足、用户范围不明确或需要作者澄清。

Minimum payload:

```json
{
  "record_type": "open_question",
  "question_id": "Q-S2-001",
  "stage": "S2_DEEP_UNDERSTANDING",
  "question": "The manuscript mentions supplementary experiments, but the provided file does not include the supplement. Should the review treat them as unavailable?",
  "status": "open"
}
```

Notes:

- open questions can remain in the final report if unanswered.
- Close an answered or dismissed question by writing another record with the same `question_id` and updated `status`.

## Typical Invalid Payloads

Invalid: reference guide text used as paper evidence.

```json
{
  "record_type": "finding",
  "finding_id": "F-BAD-001",
  "stage": "S3_MACRO_REVIEW",
  "paper_section": "abstract",
  "severity": "major",
  "issue_type": "abstract_missing_result",
  "location": "Abstract",
  "claim": "The abstract lacks key results.",
  "paper_evidence": "The general framework says abstracts should include key results.",
  "impact": "Not grounded in manuscript evidence.",
  "suggested_revision": "Add results.",
  "confidence": "high",
  "status": "candidate"
}
```

Why invalid: the claim may be reasonable, but `paper_evidence` cites the guideline instead of the manuscript.

Invalid: future-stage finding.

```json
{
  "record_type": "finding",
  "finding_id": "F-BAD-002",
  "stage": "S7_REPORT_EXPORT",
  "paper_section": "discussion",
  "severity": "minor",
  "issue_type": "unclear_discussion",
  "location": "Discussion",
  "claim": "Discussion is unclear.",
  "paper_evidence": "Discussion is short.",
  "impact": "Unclear impact.",
  "suggested_revision": "Revise discussion.",
  "confidence": "low",
  "status": "candidate"
}
```

Why invalid: export stage is not a review stage for new findings.

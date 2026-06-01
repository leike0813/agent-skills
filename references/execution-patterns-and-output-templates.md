# Execution Patterns And Output Templates

Read this before presenting a stage artifact to the user or before turning a confirmed artifact into a payload. This reference defines reusable interaction patterns for `paper-drafter`; exact payload fields remain in [payload-and-sql-recipes.md](payload-and-sql-recipes.md).

## General Interaction Rules

- Present every major stage result as a decision artifact, not polished paper prose.
- Ask the user to approve, revise, or reject a stage artifact before submitting any confirming payload.
- When a choice changes the paper's argument, evidence burden, or section order, show 2-3 concrete options and recommend one.
- When evidence is missing, state the blocked claim and the minimum evidence needed; do not ask broad questions like "please provide more evidence".
- When user instructions conflict with evidence or prior confirmed DB state, name the conflict and route back to the required earlier stage.
- Keep user-facing summaries in `working_language`; draft prose uses `document_language`.

## Confirmation Request Pattern

Use this shape when asking for confirmation:

```markdown
我准备将下面这份 <artifact name> 写入 `paper-drafter.db`。请确认是否接受：

- 关键结论：
- 需要你特别确认的取舍：
- 我保留的风险或边界：
- 写入后会推进到：

请回复：确认 / 修改以下几点 / 暂停。
```

Do not submit a confirming payload until the user confirms or explicitly delegates the decision.

## Stage Artifact Card

Use this shape for macro picture, research plan, section plan, style profile, and final check outputs:

```markdown
## <Artifact Name>

### Core Decision
- ...

### Rationale
- ...

### Evidence / Source Basis
- ...

### Risks And Boundaries
- ...

### User Decision Needed
- ...
```

## Intake Summary Template

```markdown
## Intake Profile

- Topic / tentative title:
- Canonical domain:
- Research area:
- Target venue or audience:
- Document language:
- Working language:
- Available sources:
- Missing or deferred sources:
- Constraints and forbidden assumptions:
- Privacy boundaries:
```

## Macro Picture Template

```markdown
## Macro Picture

- Topic:
- Research question:
- Gap / problem:
- Method or material path:
- Contribution:
- Boundaries / non-claims:
- Risks / weak assumptions:
- Confirmation question:
```

## Research Plan Template

```markdown
## Research Plan

- Research question:
- Objectives:
- Novelty / contribution mechanism:
- Method design:
- Evidence strategy:
- Claim scope:
- Risks:

## Stress Test
- Answerability:
- Novelty risk:
- Method-claim fit:
- Evidence sufficiency:
- Claims to weaken if evidence is missing:
```

## Outline Review Board Template

```markdown
## Outline Review Board

| section_id | title | role in argument | expected evidence | risk |
| --- | --- | --- | --- | --- |
| ... | ... | ... | ... | ... |

## Confirmation Needed
- Keep this order?
- Merge, split, or remove any section?
- Any venue-required section missing?
```

## Section Writing Plan Template

```markdown
## Section Writing Plan: <section_id>

- Section role:
- Content logic:
- Key claims:
- Materials / evidence:
- Expected visuals:
- Dependencies from earlier sections:
- Outputs needed by later sections:
- Risk:
```

## Evidence Gap Board Template

```markdown
## Evidence Gap Board

| gap_id | section_id | claim | severity | required evidence | proposed action |
| --- | --- | --- | --- | --- | --- |
| ... | ... | ... | high/medium/low | ... | provide / narrow / dismiss |

## Blocking Summary
- Blocks drafting:
- Can proceed after:
```

## Style Profile Template

```markdown
## Style Profile

- Basis:
- Summary:
- Do rules:
- Don't rules:
- Tone / terminology:
- Weakness of evidence:
- Confirmation question:
```

## Section Outline Template

```markdown
## Section Outline: <section_id>

- Section thesis:
- Subclaims:
- Evidence placement:
- Paragraph sequence:
- Figure/table/citation/proof/source hooks:
- Transition in:
- Transition out:
- Known blockers:
```

## Draft Handoff Note

Use this after drafting or revising a section:

```markdown
## Draft Handoff: <unit_id>

- What this draft covers:
- Evidence used:
- Explicit unresolved markers:
- Style constraints applied:
- Claims intentionally narrowed:
- Suggested user review focus:
```

## Final Consistency Report Template

```markdown
## Final Consistency Report

- Research question answered:
- Macro picture / research plan / outline alignment:
- Claim-evidence alignment:
- Style profile applied:
- Limitations and boundaries visible:
- Unresolved placeholders:
- Figures/tables/citations/source materials verified:
- Recommendation:
```

## Payload Readiness Checklist

Before writing any payload:

- The current gate `next_action` matches the intended `stage_id`.
- The user has confirmed the artifact when confirmation is required.
- The relevant rendered views and stage playbook were read after the latest gate.
- The payload does not close evidence gaps without actual support or approved claim narrowing.
- Stable IDs are used for sections, gaps, evidence items, samples, draft units, and reference routes.
- The payload contains only semantic content that should become DB truth.
- The payload is saved as UTF-8 JSON and submitted through `submit_stage_payload.py`.

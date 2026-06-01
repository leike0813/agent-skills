# Payload And SQLite Recipes

Read this before calling `submit_stage_payload.py`. It is the runtime payload contract for the SQLite-backed paper-drafter workflow. The LLM authors semantic JSON; scripts validate and write it.

## Allowed `stage_id`

Use only these values with `submit_stage_payload.py --stage`:

| `stage_id` | Use when `next_action` is | Writes |
| --- | --- | --- |
| `intake` | `collect_intake` | `paper_domain_profile`, `input_sources` |
| `macro_picture` | `confirm_macro_picture` | `macro_picture` |
| `research_plan` | `confirm_research_plan` | `research_plan` |
| `outline` | `confirm_outline` | `outline_sections` |
| `section_writing_plan` | `confirm_section_writing_plan` | `section_writing_plans` |
| `evidence_plan` | `plan_evidence` | `evidence_gaps`, optional `evidence_items` |
| `evidence_intake` | `intake_evidence` | `evidence_items`, selected `evidence_gaps` updates |
| `style_profile` | `build_style_profile` | `style_samples`, `style_profile` |
| `section_outline` | `plan_section_outline` | `draft_units` |
| `section_draft` | `draft_section`, `revise_section` | `draft_versions`, optional `draft_units.status` |
| `confirmation` | `final_consistency_check` or explicit confirmation repair | `user_confirmations` |
| `reference_route` | any stage where route should survive resume | `reference_routes` |

If `next_action` and `stage_id` do not match this table, stop and rerun `gate-and-render` before writing.

## Shared Rules

- The LLM creates semantic payloads; scripts validate and write them.
- Save payloads as UTF-8 JSON files and pass them with `--payload-file`.
- Use stable IDs. Do not change IDs casually after later stages reference them.
- After every submit, read stdout JSON and follow the returned `next_action`.
- If the script returns `ok=false`, stop and repair the payload or workspace before continuing.
- Use `confirmed: true` only for artifacts the user has accepted or explicitly delegated.
- Do not close or dismiss evidence gaps through payloads unless the semantic reason has been discussed or is already clear from supplied evidence.
- Do not use `reference_route` as proof that evidence or user confirmation exists.

Command:

```bash
python scripts/submit_stage_payload.py \
  --artifact-root <ARTIFACT_ROOT> \
  --stage <stage_id> \
  --payload-file <payload.json>
```

Expected success stdout includes:

```json
{
  "ok": true,
  "stage": "stage_id",
  "next_action": "next_action",
  "stage_gate": "ready-or-blocked",
  "blockers": [],
  "pending_user_confirmations": []
}
```

The returned `next_action`, blockers, and pending confirmations are the next gate result. Treat them as authoritative; if you need the full resume packet or payload example, immediately run `gate-and-render`.

## `intake`

Use when `next_action=collect_intake`.

Writes:

- `paper_domain_profile`
- `input_sources`
- `action_log`

Required semantic fields:

```json
{
  "topic": "string",
  "canonical_domain_name": "computational-algorithm-data-driven",
  "domain_label": "计算 / 算法 / 数据驱动型论文",
  "research_area": "string",
  "target_venue": "string",
  "constraints": ["string"],
  "input_sources": [
    {
      "source_id": "source_001",
      "source_type": "note",
      "label": "user note",
      "path_or_text": "optional path or inline source",
      "summary": "string"
    }
  ],
  "confirmed": true
}
```

Common errors:

- using a broad theme as `topic` without domain confirmation,
- omitting source summaries,
- setting `confirmed=true` before user acceptance.

## `macro_picture`

Use when `next_action=confirm_macro_picture`.

Writes `macro_picture`.

```json
{
  "topic": "string",
  "research_question": "string",
  "gap": "string",
  "method_path": "string",
  "contribution": "string",
  "boundaries": "string",
  "risks": "string",
  "confirmed": true
}
```

Common errors:

- making the contribution stronger than the evidence path,
- hiding risks,
- writing introduction prose instead of a decision artifact.

## `research_plan`

Use when `next_action=confirm_research_plan`.

Writes `research_plan`.

```json
{
  "research_question": "string",
  "objectives": "string",
  "novelty": "string",
  "method_design": "string",
  "evidence_strategy": "string",
  "claims_scope": "string",
  "risks": "string",
  "confirmed": true
}
```

Common errors:

- novelty is a slogan rather than a difference from existing work,
- evidence strategy does not match claims,
- risks omit feasibility concerns.

## `outline`

Use when `next_action=confirm_outline`.

Writes `outline_sections`.

```json
{
  "confirmed": true,
  "sections": [
    {
      "section_id": "introduction",
      "ordinal": 1,
      "parent_id": "",
      "level": 1,
      "title": "Introduction",
      "role": "Frame the problem and contribution",
      "expected_evidence": "Problem motivation and gap",
      "status": "planned",
      "confirmed": true
    }
  ]
}
```

Common errors:

- unstable `section_id`,
- generic section role,
- outline copied from a template without research-plan alignment.

## `section_writing_plan`

Use when `next_action=confirm_section_writing_plan`.

Writes `section_writing_plans`. Supports one plan or a `plans` array.

```json
{
  "plans": [
    {
      "section_id": "introduction",
      "content_logic": "Problem -> gap -> contribution",
      "key_claims": "string",
      "materials": "string",
      "expected_visuals": "string",
      "dependencies": "string",
      "confirmed": true
    }
  ]
}
```

Common errors:

- planning only topics, not claims,
- skipping dependencies,
- planning visuals without evidence purpose.

## `evidence_plan`

Use when `next_action=plan_evidence`.

Writes `evidence_gaps` and optionally `evidence_items`.

```json
{
  "gaps": [
    {
      "gap_id": "gap_001",
      "section_id": "method",
      "claim": "string",
      "description": "Need evidence for this claim.",
      "severity": "high",
      "status": "open",
      "required_evidence": "string"
    }
  ],
  "items": []
}
```

Open gaps block drafting. Use `dismissed` only when the claim has been removed, narrowed, or explicitly deferred.

## `evidence_intake`

Use when `next_action=intake_evidence`.

Writes `evidence_items` and updates selected `evidence_gaps`.

```json
{
  "items": [
    {
      "evidence_id": "evidence_001",
      "evidence_type": "result",
      "label": "smoke test result",
      "summary": "string",
      "source_path": "path or note",
      "supports_section": "method",
      "status": "available"
    }
  ],
  "close_gaps": [
    {"gap_id": "gap_001", "status": "closed"}
  ]
}
```

Common errors:

- closing gaps with partial evidence,
- using evidence not tied to a section or claim,
- treating user preference as evidence.

## `style_profile`

Use when `next_action=build_style_profile`.

Writes `style_samples` and `style_profile`.

```json
{
  "samples": [
    {
      "sample_id": "sample_001",
      "sample_type": "user_rewrite",
      "content": "string",
      "notes": "string"
    }
  ],
  "summary": "string",
  "do_rules": ["string"],
  "dont_rules": ["string"],
  "tone_terms": ["string"],
  "confirmed": true
}
```

Do not synthesize a strong style profile from no samples unless the user explicitly declines style profiling.

## `section_outline`

Use when `next_action=plan_section_outline`.

Writes `draft_units`.

```json
{
  "section_id": "introduction",
  "unit_id": "introduction",
  "outline": "三级提纲或结构化段落计划",
  "confirmed": true,
  "status": "planned",
  "blockers": ""
}
```

Common errors:

- outline is too shallow,
- user has not confirmed the section unit,
- blockers are omitted.

## `section_draft`

Use when `next_action=draft_section` or `revise_section`.

Writes `draft_versions`, and optionally updates `draft_units.status`.

```json
{
  "unit_id": "introduction",
  "content": "draft text",
  "evidence_notes": "claim-evidence notes and unresolved markers",
  "status": "drafted",
  "unit_status": "drafted"
}
```

Do not submit a draft that silently hides missing citations, figures, data, or user decisions.

## `confirmation`

Use for explicit confirmations not covered by a stage payload, especially final consistency.

```json
{
  "target_type": "final_consistency",
  "target_id": "1",
  "decision": "confirmed",
  "notes": "string"
}
```

Known `target_type` values used by scripts:

- `intake`
- `macro_picture`
- `research_plan`
- `outline`
- `outline_section`
- `section_writing_plan`
- `style_profile`
- `draft_unit`
- `final_consistency`

## `reference_route`

Use when a reference navigation result should be recorded for later recovery.

```json
{
  "route_id": "method_route_001",
  "domain": "computational-algorithm-data-driven",
  "drafting_phase": "section-drafting",
  "paper_section": "method",
  "headings": ["5.6 Method / Model / Algorithm 方法、模型或算法"]
}
```

This records what was consulted; it does not prove evidence or user confirmation.

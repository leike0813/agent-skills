# Workflow State Machine

Read this after every `gate-and-render` call, after context compression, or when a blocker/repair result is unclear. It defines the global loop, legal state transitions, and recovery discipline for the SQLite-backed paper drafting workflow.

## Runtime Loop

1. Run `gate-and-render`.
2. Read stdout JSON and `01-agent-resume.md`.
3. Identify `current_stage`, `stage_gate`, `next_action`, `blockers`, `pending_user_confirmations`, `repair_sequence`, and `next_action_payload_example`.
4. Read [workflow-glossary.md](workflow-glossary.md) if any name or enum is unclear.
5. Read the stage playbook mapped to `next_action`.
6. Let the LLM perform the semantic work with the user.
7. Ask for the required user confirmation before any confirming payload.
8. Save a UTF-8 JSON payload.
9. Submit it through `submit_stage_payload.py`.
10. Read the returned gate result and refreshed views.

Never continue from chat memory alone. If the DB does not contain a decision, that decision is not runtime truth.

## Gate Payload Shape

`gate-and-render` and successful payload submission return JSON with this shape:

```json
{
  "ok": true,
  "artifact_root": "path",
  "current_stage": "stage_1",
  "stage_gate": "blocked",
  "next_action": "collect_intake",
  "status_summary": "string",
  "instruction_refs": ["path-or-command"],
  "core_instruction": "string",
  "execution_note": "string",
  "next_action_payload_example": {},
  "blockers": [],
  "pending_user_confirmations": [],
  "repair_sequence": [],
  "resume_packet": {}
}
```

If `ok=false` or `repair_sequence` is non-empty, stop semantic work and repair first.

## State Transition Map

| Current state | Required DB truth | If missing, gate returns | Required playbook |
| --- | --- | --- | --- |
| `stage_1` | confirmed `paper_domain_profile` | `collect_intake` | [stage-1-intake-and-macro.md](stage-1-intake-and-macro.md) |
| `stage_2` | confirmed `macro_picture` | `confirm_macro_picture` | [stage-1-intake-and-macro.md](stage-1-intake-and-macro.md) |
| `stage_3` | confirmed `research_plan` | `confirm_research_plan` | [stage-2-research-plan-and-outline.md](stage-2-research-plan-and-outline.md) |
| `stage_4` | confirmed `outline_sections` | `confirm_outline` | [stage-2-research-plan-and-outline.md](stage-2-research-plan-and-outline.md) |
| `stage_5` | confirmed `section_writing_plans` for confirmed sections | `confirm_section_writing_plan` | [stage-3-section-writing-plan.md](stage-3-section-writing-plan.md) |
| `stage_6` | at least one `evidence_plan` action and no open gaps | `plan_evidence` or `intake_evidence` | [stage-4-evidence-and-style.md](stage-4-evidence-and-style.md) |
| `stage_7` | confirmed `style_profile` | `build_style_profile` | [stage-4-evidence-and-style.md](stage-4-evidence-and-style.md) |
| `stage_8` | confirmed draft units and draft versions for confirmed sections | `plan_section_outline`, `draft_section`, or `revise_section` | [stage-5-drafting-and-finalization.md](stage-5-drafting-and-finalization.md) |
| `stage_9` | final consistency confirmation | `final_consistency_check` | [stage-5-drafting-and-finalization.md](stage-5-drafting-and-finalization.md) |
| `completed` | all required gates complete | `completed` | stop unless user requests revision |

## Action-To-Payload Map

| `next_action` | Submit stage | Primary semantic artifact |
| --- | --- | --- |
| `collect_intake` | `intake` | intake/domain/source/language profile |
| `confirm_macro_picture` | `macro_picture` | macro research diagnosis |
| `confirm_research_plan` | `research_plan` | confirmed research design |
| `confirm_outline` | `outline` | confirmed paper outline |
| `confirm_section_writing_plan` | `section_writing_plan` | section-level writing plans |
| `plan_evidence` | `evidence_plan` | evidence gaps and initial evidence board |
| `intake_evidence` | `evidence_intake` | evidence items and gap closure updates |
| `build_style_profile` | `style_profile` | user style profile |
| `plan_section_outline` | `section_outline` | confirmed section-level outline |
| `draft_section` | `section_draft` | section draft version |
| `revise_section` | `section_draft` | revised draft version |
| `final_consistency_check` | `confirmation` | final consistency confirmation |
| `completed` | none | no required action |

Use [payload-and-sql-recipes.md](payload-and-sql-recipes.md) for exact fields and common mistakes.

## Global Confirmation Discipline

A stage is not complete because the agent drafted a plausible artifact. It is complete only when the relevant DB record exists and is confirmed, or when gate returns a later `next_action`.

User confirmation is required for:

- intake/domain profile and language context;
- macro picture;
- research plan;
- outline;
- section writing plans;
- evidence plan sufficiency, gap dismissal, or claim narrowing;
- style profile;
- each section outline;
- final consistency check.

For `draft_section`, confirmation is not always required before the write because the section outline has already been confirmed. Still ask the user before changing claims, narrowing scope, dismissing evidence needs, or applying a substantial revision direction.

## Blocker Rules

If `blockers` is non-empty:

- Explain the blocker in working language.
- Ask only for the missing evidence, decision, source, or correction needed to clear it.
- Do not perform later-stage semantic work.
- Do not "draft around" the blocker with vague prose.

Evidence blockers are especially strict: an open `evidence_gaps` row blocks dependent drafting until the gap is `closed` or `dismissed`.

## Repair Rules

If `repair_sequence` is non-empty:

- Treat the DB or workspace as unhealthy.
- Follow the repair sequence before any semantic work.
- Prefer rerunning `gate-and-render` after repair.
- Do not manually recreate rendered views.
- Do not hand-edit DB tables unless the user explicitly authorizes a repair plan.

If schema validation fails, stop and report the structured failure. A damaged schema is not a cue to continue from visible Markdown.

## Resume Read Order

On resume, context compression, "where are we?", or any uncertainty:

1. `gate-and-render` stdout JSON.
2. `01-agent-resume.md`.
3. [workflow-glossary.md](workflow-glossary.md).
4. This state-machine reference.
5. The stage playbook mapped from `next_action`.
6. The relevant read-only view:
   - `02-intake-and-domain.md` for intake/domain;
   - `03-macro-picture.md` for macro picture;
   - `04-research-plan.md` for research plan;
   - `05-outline.md` for outline;
   - `06-section-writing-plan.md` for section planning;
   - `07-evidence-board.md` for evidence;
   - `08-style-profile.md` for style;
   - `09-drafting-board.md`, `sections/*-outline.md`, or `sections/*-draft.md` for drafting.
7. [payload-and-sql-recipes.md](payload-and-sql-recipes.md) before writing.
8. Domain writing guides through `reference_guide.py` only when the current decision needs disciplinary guidance.

## Reference Route Discipline

Domain guides should be consulted progressively:

- `taxonomy` during domain classification;
- `general_framework.md` during macro picture, research plan, outline, and evidence planning;
- domain-specific guides via `reference_guide.py nav` when a phase or section needs disciplinary norms;
- `anti-ai_polishing_guide.md` during style, revision, and final consistency checks.

Record a `reference_route` only when it affects later recovery, such as a method-section guide route used to shape a section outline.

## Completion Standard

The workspace is complete only when gate returns `next_action=completed`. A populated manuscript preview is not enough; final consistency must be confirmed and recorded in `user_confirmations`.

# paper-drafter Runtime Digest

Use this short digest during recovery, gate handling, or context compression.

## Must Not Forget

- SQLite is the only runtime truth.
- Run `gate-and-render` before continuing.
- Follow only the returned `next_action`.
- Read the mapped stage playbook.
- Write confirmed semantic results through `submit_stage_payload.py`.
- Treat rendered Markdown views as read-only.
- Do not draft around open evidence gaps.
- Do not invent data, citations, results, approvals, figures, or source materials.
- `11-manuscript-preview.md` is a preview, not completion.
- Completion requires `next_action=completed`.

## Read Order

1. `gate-and-render` stdout JSON.
2. `01-agent-resume.md`.
3. `references/workflow-glossary.md`.
4. `references/workflow-state-machine.md`.
5. The stage playbook mapped to `next_action`.
6. The relevant rendered view.
7. `references/payload-and-sql-recipes.md` before a write.
8. `references/helper-scripts.md` if a command fails or is unclear.
9. Domain guides through `reference_guide.py`.

## Stage Playbooks

- `collect_intake`, `confirm_macro_picture`: `stage-1-intake-and-macro.md`
- `confirm_research_plan`, `confirm_outline`: `stage-2-research-plan-and-outline.md`
- `confirm_section_writing_plan`: `stage-3-section-writing-plan.md`
- `plan_evidence`, `intake_evidence`, `build_style_profile`: `stage-4-evidence-and-style.md`
- `plan_section_outline`, `draft_section`, `revise_section`, `final_consistency_check`: `stage-5-drafting-and-finalization.md`

## Hard Gates

- Missing confirmation blocks stage advancement.
- Open evidence gaps block dependent drafting.
- Schema errors block all semantic work.
- Stale or missing views are repaired only by `gate-and-render`.
- A user request to "just draft" does not override the gate.

## Completion

Stop only when `next_action=completed`, or when the user explicitly changes scope and a new gate-aligned action is recorded.

# Stage 5: Drafting And Finalization

Read this when `next_action` is `plan_section_outline`, `draft_section`, `revise_section`, or `final_consistency_check`. This stage drafts the manuscript one section unit at a time under confirmed research, evidence, section-plan, and style constraints.

## Goal

- Plan each section at section-outline level before prose.
- Draft only confirmed units.
- Preserve version history through `draft_versions`.
- Revise by writing new draft versions, not by editing rendered views.
- Complete only after final consistency is confirmed.

## Entering Conditions

- Research plan, outline, section writing plans, evidence board, and style profile are confirmed.
- Gate returns `plan_section_outline`, `draft_section`, `revise_section`, or `final_consistency_check`.
- User requests revision to a section draft or final consistency check finds an issue.

## Required Read Surfaces

- `01-agent-resume.md`.
- `04-research-plan.md`.
- `05-outline.md`.
- `06-section-writing-plan.md`.
- `07-evidence-board.md`.
- `08-style-profile.md`.
- `09-drafting-board.md`.
- Relevant `sections/<section_id>-outline.md` or `sections/<section_id>-draft.md`.
- [workflow-state-machine.md](workflow-state-machine.md).
- Domain guide route through `reference_guide.py nav`.
- [anti-ai_polishing_guide.md](anti-ai_polishing_guide.md) for revision and final checks.

## Next Action Task Cards

### `plan_section_outline`

- Entry check: evidence gaps are closed or dismissed, style profile is confirmed, and gate returns `plan_section_outline`.
- Semantic work: create a section-level outline with thesis, subclaims, evidence placement, paragraph sequence, hooks, transitions, and blockers.
- User-facing output: present a section outline card for the active section.
- Must ask: ask the user to confirm the section outline before drafting.
- Payload readiness: outline is sufficiently detailed for prose drafting and does not introduce unapproved claims.
- Exit gate: submit `section_outline`, then follow the returned `next_action`.
- Do-not-advance: do not draft from a title, shallow outline, or unconfirmed unit.

### `draft_section`

- Entry check: gate returns `draft_section`; section unit is confirmed; no open evidence gap blocks it.
- Semantic work: draft one section unit using research plan, section plan, evidence board, style profile, and section outline.
- User-facing output: provide the draft plus a draft handoff note that lists evidence used and unresolved markers.
- Must ask: ask before adding a claim outside confirmed scope; otherwise present draft for review after writing.
- Payload readiness: draft content and evidence notes are ready; unresolved needs are explicit, not hidden.
- Exit gate: submit `section_draft`, then follow the returned `next_action`.
- Do-not-advance: do not hide missing citations, figures, data, proofs, or sources as polished prose.

### `revise_section`

- Entry check: gate returns `revise_section` or user requests revision to an existing draft unit.
- Semantic work: identify requested changes, affected claims, evidence implications, and whether prior confirmed artifacts need revision.
- User-facing output: present revision direction when it changes scope, evidence, limitations, or section role.
- Must ask: ask before making revisions that alter research plan, claim scope, or evidence interpretation.
- Payload readiness: revised draft is a new `section_draft` version; evidence notes explain changes.
- Exit gate: submit `section_draft`, then follow the returned `next_action`.
- Do-not-advance: do not overwrite rendered draft views or erase draft history.

### `final_consistency_check`

- Entry check: all confirmed sections have draft versions and gate returns `final_consistency_check`.
- Semantic work: check alignment across macro picture, research plan, outline, section plans, evidence, style, and drafts.
- User-facing output: present a final consistency report with unresolved placeholders and recommendation.
- Must ask: ask the user to confirm final consistency or choose repairs.
- Payload readiness: user confirms final consistency; notes record any accepted limitations.
- Exit gate: submit `confirmation` with `target_type=final_consistency`, then run/read gate.
- Do-not-advance: do not declare completion until gate returns `completed`.

## Subflow: Section Outline Planning

Before drafting a section, create a section-level outline with at least three levels of detail in prose or structured bullets. It should specify:

- section thesis;
- subclaims;
- evidence placement;
- paragraph sequence;
- figure, table, citation, proof, source, or example hooks;
- transition into and out of the section;
- known blockers or unresolved placeholders.

Ask the user to confirm the section outline. Submit `section_outline` only after confirmation.

## Section Outline Quality Checks

- The outline implements the confirmed section writing plan.
- Every major claim has an evidence placement or an explicit unresolved marker.
- The sequence is readable as argument logic, not a content dump.
- The outline does not create new claims outside the research plan.
- The outline makes transitions clear enough for later prose.

## Subflow: Section Drafting

Before drafting, check:

- gate returns `draft_section`;
- the section unit is confirmed;
- no open evidence gap blocks the section;
- style profile is confirmed;
- the relevant domain route has been consulted when disciplinary form matters.

The draft must:

- make claims only within evidence scope;
- mark unresolved citation, figure, data, proof, or source needs explicitly;
- avoid generic filler;
- follow user style rules;
- preserve section role and dependencies;
- avoid hiding limitations as polished prose.

Submit `section_draft` after drafting. The script writes a new draft version and refreshes the preview. Do not edit `sections/<section_id>-draft.md` directly.

## Subflow: Revision

Use `revise_section` when:

- the user requests changes;
- gate identifies a draft unit with `revision_requested`;
- final consistency check finds a section-level issue.

Revision creates a new draft version. Before revising, identify:

- what changed;
- why it changed;
- whether the change affects research plan, evidence, or other sections;
- whether user confirmation is needed before the revision.

Ask the user before revising when the revision changes claims, evidence interpretation, limitations, scope, or section role.

## Subflow: Final Consistency Check

Before completion, check the whole workspace:

- research question is answered;
- macro picture, research plan, outline, section plans, and drafts align;
- major claims map to evidence;
- all open placeholders are visible and acceptable;
- style profile has been applied without forcing unnatural phrasing;
- limitations and boundaries are visible;
- references to figures, tables, citations, data, approvals, or source materials are not invented;
- `11-manuscript-preview.md` is a preview, not an editable manuscript source.

Ask the user to confirm final consistency. Record final acceptance with a `confirmation` payload:

```json
{
  "target_type": "final_consistency",
  "target_id": "1",
  "decision": "confirmed",
  "notes": "string"
}
```

## Must Ask The User When

- A draft would introduce a claim not already approved.
- A section cannot be drafted without unresolved evidence.
- A revision changes the paper's main line, claim scope, or conclusion.
- The final consistency check finds a gap the user may choose to fix, narrow, or explicitly accept.
- The user asks for a stylistic change that conflicts with evidence clarity.

## Payload Handoff

- For `plan_section_outline`, submit `--stage section_outline`.
- For `draft_section`, submit `--stage section_draft`.
- For `revise_section`, submit `--stage section_draft`.
- For `final_consistency_check`, submit `--stage confirmation`.
- Read [payload-and-sql-recipes.md](payload-and-sql-recipes.md) before writing.
- After submit, read the returned gate result.

## DB Concerns

- `draft_units`
- `draft_versions`
- `evidence_gaps`
- `evidence_items`
- `style_profile`
- `user_confirmations`
- `reference_routes`
- `action_log`

## Forbidden

- Do not draft unconfirmed units.
- Do not draft around open evidence gaps.
- Do not strengthen unsupported claims with polished language.
- Do not treat `11-manuscript-preview.md` as an editable manuscript source.
- Do not overwrite draft history by editing rendered files.
- Do not declare completion before final consistency is confirmed and gate returns `completed`.

## Completion Standard

- Every confirmed outline section has a confirmed draft unit.
- Every confirmed draft unit has at least one draft version.
- Required revisions have been written as new draft versions.
- Final consistency confirmation is written to DB.
- Gate returns `next_action=completed`.

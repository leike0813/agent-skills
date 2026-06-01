# Stage 4: Evidence And Style

Read this when `next_action` is `plan_evidence`, `intake_evidence`, or `build_style_profile`. This stage prevents unsupported drafting and establishes the user's writing style before section prose begins.

## Goal

- Convert section plans into an evidence board.
- Identify all evidence gaps that could weaken or block claims.
- Ingest user-supplied evidence without overstating what it supports.
- Build and confirm a user style profile for later drafting.

## Entering Conditions

- Section writing plans are confirmed.
- Gate returns `plan_evidence`, `intake_evidence`, or `build_style_profile`.
- User supplies new evidence or asks to revise gap status.
- User supplies style samples, rewrites, or style preferences.

## Required Read Surfaces

- `01-agent-resume.md`.
- `04-research-plan.md`.
- `06-section-writing-plan.md`.
- `07-evidence-board.md`.
- `08-style-profile.md` when building or revising style.
- [workflow-state-machine.md](workflow-state-machine.md).
- [general_framework.md](general_framework.md) for evidence standards.
- Domain guide route through `reference_guide.py nav` when the domain has special evidence rules.
- [anti-ai_polishing_guide.md](anti-ai_polishing_guide.md) for style and anti-AI checks.

## Next Action Task Cards

### `plan_evidence`

- Entry check: all section writing plans are confirmed and gate returns `plan_evidence`.
- Semantic work: map key claims to existing evidence, required evidence, and evidence gaps.
- User-facing output: present an evidence gap board with severity and proposed action for each gap.
- Must ask: ask the user to confirm whether to provide evidence, narrow claims, dismiss out-of-scope gaps, or pause.
- Payload readiness: every blocking claim has either support or an evidence gap; severity and required evidence are explicit.
- Exit gate: submit `evidence_plan`, then follow the returned `next_action`.
- Do-not-advance: do not proceed to style or drafting if planned claims have unrecorded evidence gaps.

### `intake_evidence`

- Entry check: gate returns `intake_evidence` with open gaps, or user provides evidence while gaps exist.
- Semantic work: read supplied material, decide what it supports, and update only actually satisfied gaps.
- User-facing output: show which gaps are closed, still open, or proposed for dismissal with rationale.
- Must ask: ask when evidence only partially supports a claim or closing a gap requires claim narrowing.
- Payload readiness: each evidence item has ID, type, label, summary, source path/note, supported section, and status.
- Exit gate: submit `evidence_intake`, then follow the returned `next_action`.
- Do-not-advance: do not close gaps because the user wants to move on; close only when support is real.

### `build_style_profile`

- Entry check: evidence blockers are cleared or dismissed, and gate returns `build_style_profile`.
- Semantic work: infer style rules from user samples, rewrites, explicit preferences, and anti-AI constraints.
- User-facing output: present a style profile card with basis, do rules, don't rules, tone terms, and limitations.
- Must ask: ask the user to confirm the style profile and resolve conflicts between samples and stated preferences.
- Payload readiness: profile includes summary, rules, tone terms, sample basis, and confirmation.
- Exit gate: submit `style_profile`, then follow the returned `next_action`.
- Do-not-advance: do not draft from a generic style profile if user samples exist or if the profile is unconfirmed.

## Subflow: Evidence Planning

For every important planned claim, ask what would make the claim credible in the chosen domain. Support may include:

- data;
- experiment;
- observation;
- interview or field material;
- textual evidence;
- legal or policy source;
- theorem or proof;
- citation;
- figure or table;
- system design artifact;
- user-provided factual note.

Create an `evidence_gaps` item when support is missing, partial, ambiguous, or not yet supplied. The plan should make the minimum evidence needs explicit; it should not lower standards just to move into drafting.

## Evidence Gap Severity

- `high`: blocks a major claim, result, method detail, proof, section, or conclusion.
- `medium`: blocks a supporting claim or substantially weakens the argument.
- `low`: can be handled by narrowing wording, adding a citation, marking a limitation, or moving detail out of the main claim.

Open gaps block drafting. Only `closed` or `dismissed` gaps allow dependent drafting to proceed.

## Subflow: Evidence Intake

When the user provides evidence:

1. Read the material or summary.
2. Decide semantically what claim and section it supports.
3. Record it as an `evidence_items` payload.
4. Close only gaps actually satisfied by the material.
5. Leave partial or ambiguous gaps open and explain why.
6. Dismiss a gap only when the claim has been removed, narrowed, deferred, or explicitly accepted as out of scope.

Do not close a gap because the user wants to proceed. Close it only when the claim can be supported.

## Subflow: Style Profile

Build the style profile only after evidence blockers are cleared or the gate asks for style profiling. Use:

- user writing samples;
- user rewrites of generated example paragraphs;
- explicit user preferences;
- observed terminology, rhythm, tone, and paragraph habits;
- anti-AI polishing constraints.

The profile must include:

- summary;
- do rules;
- don't rules;
- tone or terminology preferences;
- source notes explaining where the profile came from.

If the user declines to provide samples, record the limitation and keep the profile conservative. Do not invent a rich personal style profile from no evidence.

## Must Ask The User When

- A high or medium evidence gap requires material only the user can provide.
- Closing or dismissing a gap would narrow a claim.
- Evidence appears to support a weaker claim than planned.
- Style samples conflict with explicit user preferences.
- The user wants to proceed despite unresolved evidence risk.

## Payload Handoff

- For `plan_evidence`, submit `--stage evidence_plan`.
- For `intake_evidence`, submit `--stage evidence_intake`.
- For `build_style_profile`, submit `--stage style_profile`.
- Read [payload-and-sql-recipes.md](payload-and-sql-recipes.md) before writing.
- After submit, read the returned gate result.

## DB Concerns

- `section_writing_plans`
- `evidence_items`
- `evidence_gaps`
- `style_samples`
- `style_profile`
- `reference_routes`
- `action_log`

## Forbidden

- Do not fabricate missing evidence.
- Do not close gaps based on confidence, rhetorical plausibility, or user impatience.
- Do not use a generic academic style profile when the user has provided samples.
- Do not start section drafting while gate returns `plan_evidence`, `intake_evidence`, or `build_style_profile`.
- Do not treat citations, figures, or tables as available unless the user has supplied or authorized them.

## Completion Standard

- Evidence plan has been written.
- All evidence gaps are `closed` or `dismissed`, or the related claim has been narrowed so the gap no longer blocks drafting.
- Style profile is confirmed and written to DB.
- Gate moves to `plan_section_outline`.

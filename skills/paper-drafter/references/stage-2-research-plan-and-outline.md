# Stage 2: Research Plan And Outline

Read this when `next_action` is `confirm_research_plan` or `confirm_outline`. This stage converts the confirmed macro picture into a defensible research plan and a confirmed paper outline.

## Goal

- Stress-test the macro picture before drafting structure.
- Produce a research plan that names the research question, objectives, novelty, method design, evidence strategy, claim scope, and risks.
- Produce an outline with stable section IDs, section roles, and expected evidence.

## Entering Conditions

- `03-macro-picture.md` is confirmed in DB.
- Gate returns `confirm_research_plan` or `confirm_outline`.
- User asks to revise the research plan or outline after seeing a later conflict.

## Required Read Surfaces

- `01-agent-resume.md`.
- `03-macro-picture.md`.
- `04-research-plan.md` if revising a plan.
- `05-outline.md` if revising an outline.
- [workflow-state-machine.md](workflow-state-machine.md).
- [general_framework.md](general_framework.md).
- A domain guide route from `reference_guide.py nav` when disciplinary structure or evidence standards matter.

## Next Action Task Cards

### `confirm_research_plan`

- Entry check: macro picture is confirmed and gate returns `confirm_research_plan`.
- Semantic work: stress-test answerability, novelty, method-claim fit, evidence strategy, claim scope, and fallback narrowing.
- User-facing output: present a research plan card and stress-test summary using [execution-patterns-and-output-templates.md](execution-patterns-and-output-templates.md).
- Must ask: ask the user to confirm major tradeoffs, especially novelty, method route, and claim scope.
- Payload readiness: user has confirmed; plan includes objectives, novelty, method design, evidence strategy, claim scope, and risks.
- Exit gate: submit `research_plan`, then follow the returned `next_action`.
- Do-not-advance: do not create outline if novelty, method route, or evidence strategy is still unresolved.

### `confirm_outline`

- Entry check: research plan is confirmed and gate returns `confirm_outline`.
- Semantic work: produce stable section IDs, order, levels, titles, section roles, and expected evidence.
- User-facing output: present an outline review board; highlight sections that carry major claims or evidence risk.
- Must ask: ask the user to approve order, merge/split choices, and venue-required sections.
- Payload readiness: each section has stable `section_id`, role, expected evidence, status, and confirmation state.
- Exit gate: submit `outline`, then follow the returned `next_action`.
- Do-not-advance: do not write section plans if the outline only lists generic headings without argument roles.

## Subflow: Research Plan

Create the plan as a structured decision artifact. It must settle:

- research question;
- objectives;
- novelty or contribution mechanism;
- method, proof, design, empirical, interpretive, or source-material strategy;
- evidence strategy;
- claim scope;
- feasibility risks and fallback narrowing.

Before asking for confirmation, run this semantic stress test:

- Is the research question answerable with the planned evidence?
- Is the novelty more than renaming, repackaging, or applying a routine template?
- Does the method match the strongest claim?
- Would the planned evidence convince a skeptical reader in this domain?
- Which claims must be weakened if evidence does not arrive?
- What would make the paper fail even if the prose is polished?

Present weaknesses plainly. The user should approve a realistic plan, not a smoothed-over version.

## Research Plan Confirmation

Ask the user to approve, reject, or revise the plan. Submit `research_plan` only after confirmation or explicit delegation. If the user wants to proceed despite a weakness, record that weakness in `risks` or `claims_scope`; do not erase it.

## Subflow: Outline

Create the outline after the research plan is confirmed. The outline should be conceptually detailed to at least second-level headings, even if the first DB skeleton stores top-level sections and adds finer draft units later.

Each outline section needs:

- stable `section_id`;
- order;
- level;
- title;
- role in the argument;
- expected evidence, material, figure, table, proof, case, or source type;
- confirmation status.

The outline should express the paper's argument path, not merely list IMRaD-like headings.

## Outline Quality Checks

- The outline follows from the confirmed research plan.
- Each section has a specific job.
- The sequence explains how the reader moves from problem to contribution.
- Results, analysis, or argument sections are not evidence dumps.
- Literature/background sections serve the research question.
- Discussion/conclusion sections do not merely repeat earlier claims.
- No section requires evidence that Stage 4 cannot plausibly plan for.

## Must Ask The User When

- More than one outline structure is plausible and the choice changes the argument.
- Target venue or discipline imposes a section structure.
- The user wants to preserve a section unsupported by the research plan.
- A section would imply a stronger claim than the research plan permits.
- The plan requires evidence that the user may not be able to provide.

## Payload Handoff

- For `confirm_research_plan`, submit `--stage research_plan`.
- For `confirm_outline`, submit `--stage outline`.
- Read [payload-and-sql-recipes.md](payload-and-sql-recipes.md) before writing.
- After submit, read the returned gate result.

## DB Concerns

- `macro_picture`
- `research_plan`
- `outline_sections`
- `reference_routes`
- `user_confirmations`
- `action_log`

## Forbidden

- Do not generate section drafts while the research plan is unconfirmed.
- Do not hide weak novelty by making the outline look complete.
- Do not add sections only because generic papers often have them.
- Do not use a domain guide as a template that overrides the user's research plan.
- Do not mark outline sections confirmed if the user has not seen their roles and evidence expectations.

## Completion Standard

- Research plan is confirmed and written to DB.
- Outline sections have stable IDs, roles, expected evidence, and confirmation status.
- Gate no longer returns `confirm_research_plan` or `confirm_outline`.

# Stage 3: Section Writing Plan

Read this when `next_action` is `confirm_section_writing_plan`. This stage turns the confirmed paper outline into section-level writing plans before evidence planning and drafting.

## Goal

- Define what each confirmed outline section will argue.
- Identify the materials, evidence, visuals, citations, or source types each section needs.
- Make section dependencies explicit.
- Prevent later drafting from relying only on section titles.

## Entering Conditions

- `04-research-plan.md` and `05-outline.md` are confirmed.
- Gate returns `confirm_section_writing_plan`.
- User asks to revise section logic after later evidence or drafting conflicts.

## Required Read Surfaces

- `01-agent-resume.md`.
- `04-research-plan.md`.
- `05-outline.md`.
- `06-section-writing-plan.md` if revising existing plans.
- [workflow-state-machine.md](workflow-state-machine.md).
- Domain guide sections located through `reference_guide.py nav` when section form matters.

## Next Action Task Cards

### `confirm_section_writing_plan`

- Entry check: research plan and outline are confirmed; gate returns `confirm_section_writing_plan`.
- Semantic work: for every confirmed outline section, define content logic, key claims, materials, expected visuals, and dependencies.
- User-facing output: present section writing plan cards, grouped by section order.
- Must ask: ask the user to confirm the claim/evidence/dependency logic, especially for sections with high evidence burden.
- Payload readiness: every confirmed outline section has a plan; batch payload is allowed only after user reviews the whole batch.
- Exit gate: submit `section_writing_plan`, then follow the returned `next_action`.
- Do-not-advance: do not enter evidence planning while any confirmed section lacks a confirmed writing plan.

## Planning Unit

The planning unit is one confirmed outline section. For each section, define:

- content logic;
- key claims and subclaims;
- materials or evidence needed;
- expected visuals, tables, equations, proofs, cases, or citations;
- dependencies on earlier sections;
- outputs later sections need from it.

## Procedure

1. Read the section's role in `05-outline.md`.
2. Identify the section-specific argument, not only the topic.
3. Identify the claims that must be supported.
4. Name the material or evidence category needed for each important claim.
5. Identify figure/table/citation/proof/source hooks and why they matter.
6. Identify upstream and downstream dependencies.
7. Present the plan to the user for confirmation or revision.
8. Submit `section_writing_plan`.

The payload may contain one plan or a `plans` array. Batch submission is acceptable only when the user has reviewed the whole batch.

## Quality Checks

- The plan states a section-specific argument.
- Key claims are scoped to available or planned evidence.
- Materials are concrete enough to support Stage 4 evidence planning.
- Expected visuals are justified by claims, not decorative.
- Dependencies are explicit.
- The section does not duplicate another section's job.
- The plan remains within the confirmed research plan.

## Must Ask The User When

- A section's role is unclear.
- A section depends on evidence the user may not be able to provide.
- The section plan would change the confirmed research plan.
- A section appears redundant, unsupported, or better merged.
- The order of sections affects the logic of the paper.

## Payload Handoff

- Submit `--stage section_writing_plan`.
- Read [payload-and-sql-recipes.md](payload-and-sql-recipes.md) before writing.
- After submit, read the returned gate result.

## DB Concerns

- `outline_sections`
- `section_writing_plans`
- `reference_routes`
- `action_log`

## Forbidden

- Do not draft a section from only a title.
- Do not mark a section plan confirmed if the user has not seen its claim/evidence/dependency logic.
- Do not use reference guide headings as a substitute for the actual section plan.
- Do not ignore a plan-evidence mismatch; surface it before Stage 4.

## Completion Standard

- Every confirmed outline section has a confirmed section writing plan.
- `06-section-writing-plan.md` shows the argument, evidence/materials, visuals, and dependencies for each section.
- Gate no longer returns `confirm_section_writing_plan`.

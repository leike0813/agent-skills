# Workflow Glossary

Read this when a document, script output, or user conversation needs stable names for the `paper-drafter` runtime. This file is the naming source for actions, payload stages, read-only views, and core SQLite tables.

## Runtime Truth

- `paper-drafter.db`: SQLite database at the artifact workspace root. It is the only runtime source of truth.
- Artifact workspace: the user-chosen directory that contains `paper-drafter.db`, rendered views, and `sections/`.
- Read-only views: Markdown files rendered by `gate-and-render`. They are for reading, review, and collaboration, not state mutation.

## Formal Script Names

- `paper-drafter/scripts/init_artifact_workspace.py`: workspace initialization script.
- `paper-drafter/scripts/gate_and_render_workspace.py`: `gate-and-render`, the only formal gate and renderer.
- `paper-drafter/scripts/submit_stage_payload.py`: formal semantic payload write entrypoint.
- `paper-drafter/scripts/reference_guide.py`: reference navigation helper.

Use `gate-and-render` as the conversational name for `gate_and_render_workspace.py`.

## Valid `next_action`

- `collect_intake`: collect and confirm topic, domain, source inventory, language context, and constraints.
- `confirm_macro_picture`: create or revise the paper macro picture.
- `confirm_research_plan`: create or revise the research plan.
- `confirm_outline`: create and confirm the paper outline.
- `confirm_section_writing_plan`: create confirmed section writing plans for all confirmed outline sections.
- `plan_evidence`: create the evidence plan and evidence gaps.
- `intake_evidence`: ingest supplied evidence and close only satisfied evidence gaps.
- `build_style_profile`: build and confirm the user style profile.
- `plan_section_outline`: prepare a section-level outline for one confirmed outline section.
- `draft_section`: draft one confirmed section unit.
- `revise_section`: submit a new version for a section unit that needs revision.
- `final_consistency_check`: run final consistency checks and record final user confirmation.
- `completed`: no required workflow action remains.

## Valid `stage_id`

- `intake`: writes `paper_domain_profile` and `input_sources`.
- `macro_picture`: writes `macro_picture`.
- `research_plan`: writes `research_plan`.
- `outline`: writes `outline_sections`.
- `section_writing_plan`: writes `section_writing_plans`.
- `evidence_plan`: writes `evidence_gaps` and optionally `evidence_items`.
- `evidence_intake`: writes `evidence_items` and updates selected `evidence_gaps`.
- `style_profile`: writes `style_samples` and `style_profile`.
- `section_outline`: writes `draft_units`.
- `section_draft`: writes `draft_versions` and optionally updates `draft_units.status`.
- `confirmation`: writes `user_confirmations`.
- `reference_route`: writes `reference_routes`.

## Formal Stages

- `stage_1`: intake and domain confirmation.
- `stage_2`: macro picture confirmation.
- `stage_3`: research plan confirmation.
- `stage_4`: outline confirmation.
- `stage_5`: section writing plan confirmation.
- `stage_6`: evidence planning and evidence intake.
- `stage_7`: style profile confirmation.
- `stage_8`: section outline planning, section drafting, and revision.
- `stage_9`: final consistency check.
- `completed`: all required drafting workflow gates are complete.
- `invalid_schema`: the database does not match the required runtime tables.

## Read-Only Views

- `01-agent-resume.md`: current gate state, blockers, pending confirmations, and next action.
- `02-intake-and-domain.md`: topic, domain, source inventory, language context, and constraints.
- `03-macro-picture.md`: research question, gap, contribution, boundaries, and risks.
- `04-research-plan.md`: research objectives, novelty, method design, evidence strategy, claim scope, and risks.
- `05-outline.md`: outline sections, section roles, and expected evidence.
- `06-section-writing-plan.md`: section logic, key claims, materials, expected visuals, and dependencies.
- `07-evidence-board.md`: available evidence, open/closed/dismissed gaps, severity, and required evidence.
- `08-style-profile.md`: style samples, profile summary, do rules, don't rules, and terminology preferences.
- `09-drafting-board.md`: planned draft units, draft statuses, blockers, and revision requests.
- `10-reference-route-board.md`: reference routes recorded for recovery.
- `11-manuscript-preview.md`: preview assembled from DB draft versions.
- `sections/<section_id>-outline.md`: rendered section outline.
- `sections/<section_id>-draft.md`: latest rendered section draft.

## Core SQLite Tables

- `workflow_state`: current stage, gate, next action, and status summary.
- `runtime_context`: document language and working language.
- `input_sources`: user-provided notes, paths, files, or inline materials.
- `paper_domain_profile`: topic, canonical domain, research area, venue, and constraints.
- `macro_picture`: first paper-level research diagnosis.
- `research_plan`: confirmed research design and claim boundaries.
- `outline_sections`: paper outline sections and their roles.
- `section_writing_plans`: section argument and evidence plans.
- `evidence_items`: available evidence records.
- `evidence_gaps`: missing evidence records and closure state.
- `style_samples`: user samples and rewrites used for style profiling.
- `style_profile`: confirmed user style profile.
- `draft_units`: planned section-level drafting units.
- `draft_versions`: versioned section draft content.
- `user_confirmations`: confirmation records not otherwise covered by stage payloads.
- `reference_routes`: recorded domain guide navigation routes.
- `action_log`: formal payload write history.

## Boundary Terms

- Semantic payload: JSON authored by the LLM from user interaction and analysis, then written by script.
- Gate: deterministic check of DB state that returns `next_action`, blockers, pending confirmations, repair steps, and a payload example.
- Evidence gap: a claim-support problem that blocks dependent drafting until closed or dismissed.
- Dismissed gap: a gap no longer blocks because the claim was removed, narrowed, deferred, or explicitly accepted as out of scope.
- Closed gap: a gap satisfied by actual evidence.
- Draft unit: the section-level unit represented in `draft_units` and drafted through `draft_versions`.

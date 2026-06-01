# Stage 1: Intake And Macro Picture

Read this when `next_action` is `collect_intake` or `confirm_macro_picture`. This stage establishes the paper's working context before any research plan or outline is drafted.

## Goal

- Confirm what paper the user is trying to write.
- Classify the paper into a canonical drafting domain.
- Confirm document language, working language, source inventory, and constraints.
- Create a macro picture that exposes the research question, gap, contribution, boundaries, and risks.

## Entering Conditions

- New workspace after `init_artifact_workspace.py`.
- Existing workspace where gate returns `collect_intake`.
- Existing workspace where gate returns `confirm_macro_picture`.
- User asks to revise intake, domain, language context, or macro picture.

## Required Read Surfaces

- `01-agent-resume.md`.
- `02-intake-and-domain.md` if it exists.
- `03-macro-picture.md` if gate requests macro confirmation.
- [workflow-glossary.md](workflow-glossary.md) for naming.
- [taxonomy.md](taxonomy.md) when the canonical domain is unclear.
- [general_framework.md](general_framework.md) for research question, contribution, and evidence standards.

Use this command when taxonomy navigation is needed:

```bash
python scripts/reference_guide.py taxonomy
```

## Next Action Task Cards

### `collect_intake`

- Entry check: gate returns `collect_intake`; workspace exists; language context is known or can be confirmed now.
- Semantic work: collect topic, domain, research area, target venue, sources, constraints, privacy boundaries, and forbidden assumptions.
- User-facing output: present an intake profile using the template in [execution-patterns-and-output-templates.md](execution-patterns-and-output-templates.md).
- Must ask: confirm `document_language`, `working_language`, canonical domain, and source inventory.
- Payload readiness: user has confirmed the intake profile; each source has `source_id`, `source_type`, label, and summary; unavailable sources are explicitly noted.
- Exit gate: submit `intake`, then read the returned gate result.
- Do-not-advance: do not create macro picture if domain, language, or source inventory is unconfirmed.

### `confirm_macro_picture`

- Entry check: intake/domain profile is confirmed and gate returns `confirm_macro_picture`.
- Semantic work: turn the intake profile into research question, gap, method/material path, contribution, boundaries, and risks.
- User-facing output: present a macro picture card with explicit weak assumptions.
- Must ask: ask the user to confirm whether this is the intended paper direction.
- Payload readiness: the macro picture is confirmed; risks and boundaries are not blank; contribution does not exceed evidence path.
- Exit gate: submit `macro_picture`, then follow the returned `next_action`.
- Do-not-advance: do not write a research plan while macro picture is unconfirmed or while the research question remains broad.

## Subflow: Intake

Collect enough information to make the workspace stable:

1. Identify the topic, draft title, or intended contribution.
2. Classify the paper domain using the canonical domain names in the reference index.
3. Record research area or subfield.
4. Ask for target venue or audience if it affects structure, evidence, or language.
5. Confirm `document_language` and `working_language`.
6. Inventory input sources, including notes, figures, data descriptions, citations, prior drafts, or inline text.
7. Record constraints, forbidden assumptions, privacy boundaries, and claims the user does not want made.
8. Ask the user to confirm the intake profile.

Use `confirmed: true` only when the user has accepted the profile or clearly delegated the decision.

## Intake Quality Checks

- The domain is specific enough to choose a writing guide.
- The source inventory states what exists and what is missing.
- Language context is explicit.
- Constraints are usable by later stages.
- The profile does not silently assume data, results, citations, or approvals.

## Subflow: Macro Picture

Build the first paper-level diagnosis after intake is confirmed. It must include:

- topic;
- research question;
- gap or problem the paper addresses;
- likely method, proof, design, dataset, case, source, or material path;
- contribution;
- boundaries and non-claims;
- risks and weak assumptions.

The macro picture is a decision artifact, not introduction prose. It should be short enough for user correction and explicit enough to block a vague research plan.

## Macro Picture Quality Checks

- The topic is narrowed into an answerable research question.
- The gap is contestable, not a generic "few studies" claim.
- The method or material path can plausibly answer the question.
- The contribution does not exceed the evidence path.
- Risks are visible instead of hidden behind polished wording.

## Must Ask The User When

- Domain classification changes the writing standard or evidence burden.
- `document_language` or `working_language` is unconfirmed.
- Source availability is too vague to infer the paper type.
- The macro picture depends on user facts or evidence not yet provided.
- More than one research question is plausible and choosing one changes the paper.

## Payload Handoff

- For `collect_intake`, submit `--stage intake`.
- For `confirm_macro_picture`, submit `--stage macro_picture`.
- Read [payload-and-sql-recipes.md](payload-and-sql-recipes.md) before writing.
- After submit, read the returned gate result and continue only according to the new `next_action`.

## DB Concerns

- `runtime_context`
- `input_sources`
- `paper_domain_profile`
- `macro_picture`
- `user_confirmations`
- `action_log`

## Forbidden

- Do not create an outline before intake and macro picture are confirmed.
- Do not convert a broad topic into a fake research question.
- Do not infer experimental results, case facts, citations, datasets, source materials, ethical approvals, or legal authorities.
- Do not classify the domain only by title keywords if source materials point elsewhere.

## Completion Standard

- Intake/domain/language/source profile is confirmed and written to DB.
- Macro picture is confirmed and written to DB.
- `gate-and-render` no longer returns `collect_intake` or `confirm_macro_picture`.

# Full-mode workflow

Use this playbook only after `SKILL.md` routes the request to full mode. First read `agents/review.md`, `references/diagnostic-guidance.md`, and `references/document-yaml-contract.md` completely.

## Contents

1. Runtime model
2. Gate discipline
3. Initialize and review
4. Negotiate and approve the plan
5. Execute the approved plan
6. Verify the candidate
7. Acceptance and rejection loops
8. Payload contracts
9. Recovery and failures
10. Responsibilities

## 1. Runtime model

Full mode is an interactive, gate-driven workflow:

```text
review → plan negotiation ↔ user
                    ↓ explicit current-plan approval
                 execute
                    ↓
                  verify
          failed ↙     ↘ pass
              plan     user acceptance
                         ↙ reject  ↘ accept
                       plan         done
```

The user's initial request authorizes review and plan creation only. It never approves an edit or final candidate by itself.

Use one task-local workspace outside the Skill package. Its `state.yaml` is the sole workflow authority. These files are regenerated read-only views:

- `review-report.md`
- `revision-plan.md`
- `verification-report.md`
- `resume.md`

Never edit a view to advance state. Never reconstruct approval, candidate identity, or the next stage from conversation memory.

## 2. Formal commands and gate discipline

Run commands from the Skill package directory with Python 3.11 or later:

```bash
python scripts/full_workflow.py init --document DOCUMENT.yaml --workspace WORKSPACE
python scripts/full_workflow.py gate --workspace WORKSPACE
python scripts/full_workflow.py apply --workspace WORKSPACE --action ACTION --payload-file PAYLOAD.json
python scripts/full_workflow.py validate --workspace WORKSPACE
python scripts/full_workflow.py render --workspace WORKSPACE
```

Every command emits exactly `ok`, `command`, `artifact`, `summary`, and `error` on stdout. Logs go to stderr. Stop on a nonzero exit or non-null `error`.

Apply this discipline:

1. Run `gate` before semantic work or any state transition.
2. Execute only its `next_action`; use only an action listed in `allowed_actions`.
3. Read the playbook needed for that action.
4. Put semantic output in a JSON payload file; never hand-edit `state.yaml`.
5. Run `apply`, then run `gate` again.
6. Present the current rendered view when the workflow awaits a user decision.
7. Stop when the gate returns `blocked` or `done`.

`next_action` is one of:

- `record_review`
- `await_plan_approval`
- `revise_plan_after_rejection`
- `revise_plan_after_verification`
- `execute_revision`
- `record_verification`
- `await_user_acceptance`
- `done`
- `blocked`

## 3. Initialize and record the review

### Full-only voice calibration

If the user provides a writing sample or governing house style, read it in full mode before drafting the review plan or revising text. Record only acceptable form: vocabulary level, sentence-length range, paragraph openings, punctuation, recurring phrases, transitions, stance, and deliberate irregularities. Use that evidence to constrain approved candidate edits without importing the sample's subject matter, facts, claims, examples, or structure. This calibration is a full-mode revision aid; reference and review modes do not perform it.

Full mode always uses structured artifacts, including for pasted text:

1. Save pasted input exactly to a task-local `.txt`, `.md`, `.qmd`, or `.tex` source when needed. Use `.qmd` when the input is Quarto.
2. Extract it with `scripts/document_pipeline.py` according to `references/document-yaml-contract.md`.
3. Create a new or empty workflow directory; never reuse another task's workspace.
4. Run `full_workflow.py init` with the fresh document artifact.
5. Run `gate` and require `record_review`.
6. Complete the exhaustive review and initial plan defined in `agents/review.md`.
7. Submit that exact payload:

```bash
python scripts/full_workflow.py apply \
  --workspace WORKSPACE \
  --action record_review \
  --payload-file REVIEW.json
```

The runtime copies exact sentence analysis from the document artifact, stores the review and plan, computes plan version 1 and its hash, and renders the report and plan.

Present `review-report.md` and `revision-plan.md` together. Ask one concise question inviting the user to approve the current plan, name items to include/exclude, change operations, add constraints, supply context, or ask questions. Do not include a full rewritten source or create an edited document.

## 4. Negotiate and approve the plan

The plan stage can span any number of dialogue turns.

- If the user only asks a question, answer it without changing state; the gate remains at the same action.
- If the user changes scope, dispositions, operations, preservation constraints, or preferences, submit a complete replacement plan with `revise_plan`.
- Preserve stable `RP-###` IDs for conceptually unchanged items. Allocate a new ID for a genuinely new operation.
- Every revision increments `plan.version`, recomputes `plan.hash`, and invalidates approval.
- Treat vague assent, silence, or approval of an older version as insufficient.

Plan revision payload uses exactly the `plan` object from `agents/review.md`:

```bash
python scripts/full_workflow.py apply \
  --workspace WORKSPACE \
  --action revise_plan \
  --payload-file PLAN.json
```

Only approve when every item disposition is `include` or `exclude` and the user explicitly accepts the current rendered version. Read `plan_version` and `plan_hash` from the latest gate result:

```json
{
  "plan_version": 2,
  "plan_hash": "<current hash>",
  "decision_note": "User approved this exact plan."
}
```

Submit it with `--action approve_plan`. Never copy a version or hash from an earlier turn.

If the plan contains no actionable items, approve a no-op plan only after the user agrees to close without manufactured edits. Execution may use an unchanged fresh document artifact and an empty item-results array.

## 5. Execute the approved plan

Run `gate` and require `execute_revision`.

Before editing, map the information units for each included plan item:

- claims, propositions, evidence, and citations;
- entities, numbers, dates, terminology, scope, conditions, certainty, negation, contrast, and causality;
- paragraph and section function;
- deliberate voice features.

Edit only the `text` fields of approved `prose` segments in the current base artifact. Do not touch excluded, pending, or protected content. Prefer the smallest operation that resolves the supported mechanism.

After editing:

```bash
python scripts/document_pipeline.py analyze --input EDITED.yaml --output CANDIDATE.yaml
python scripts/document_pipeline.py validate --input CANDIDATE.yaml
```

Do not render the public output yet. Record execution with:

```json
{
  "approved_plan_hash": "<approved hash>",
  "base_content_sha256": "<approved base content hash>",
  "candidate_document": "/absolute/path/to/CANDIDATE.yaml",
  "item_results": [
    {
      "plan_item_id": "RP-001",
      "status": "applied",
      "note": "The bounded operation was applied."
    }
  ]
}
```

`status` is exactly `applied`, `partly_applied`, or `unchanged_for_safety`. Include one result for every plan item whose disposition is `include`, and none for excluded items.

The runtime rejects a stale plan, stale base, invalid candidate, changed source anchor, changed manifest, or incomplete item results.

## 6. Verify the candidate

Run `gate` and require `record_verification`. Verify before rendering a public document.

### Bidirectional information check

- Map every original-source information unit to the candidate.
- Map every candidate unit to the original source or separately authorized user input.
- Compare facts, numbers, names, dates, citations, terms, claim strength, uncertainty, scope, time, population, causality, negation, and contrast.
- Also compare the candidate with its immediate base to identify the current cycle's changes.

### Structure and protection check

- Require successful document validation.
- Confirm heading and section order, paragraph functions, lists, tables, links, code, formulas, citations, labels, identifiers, and protected syntax retain their roles.
- Confirm unapproved spans remain unchanged.

### Style and finding check

- Rescan approved findings as `resolved`, `partly_resolved`, or `unchanged_for_safety`.
- Mark excluded findings `not_in_scope` when included in the verification list.
- Search for newly introduced instances of all numbered patterns.
- Compare register, lexical level, stance, and recognizable voice with the source and any supplied writing sample.
- Interpret refreshed sentence statistics descriptively; never edit merely to raise variation.

Submit the verification payload defined below. Use:

- `pass`: every required check passes and there are no material residuals;
- `pass_with_residuals`: required checks pass and disclosed non-blocking residuals remain;
- `failed`: at least one required check fails.

A `failed` result automatically returns to plan, increments the cycle, keeps the pre-execution base, clears approval, and exposes the verification residuals for repair planning. Present the verification report before proposing the repair plan.

## 7. User acceptance and rejection

When verification passes, run `gate` and require `await_user_acceptance`. Render the candidate document to a new output path, then present:

1. the revised text or agreed output path;
2. `verification-report.md`;
3. resolved, retained, new, and residual findings;
4. one explicit acceptance question.

Acceptance payload:

```json
{"decision_note": "User accepted the latest verified candidate."}
```

Submit with `--action accept`. Acceptance is legal only for the latest `pass` or `pass_with_residuals` verification and makes the workflow terminal.

Rejection requires actionable feedback:

```json
{"feedback": "Preserve the original technical term in P3 S2."}
```

Submit with `--action reject`. The runtime increments the cycle, promotes the latest verified candidate to the working base, preserves the original document as the drift anchor, clears approval, and returns `revise_plan_after_rejection`.

If the user says only that the candidate is unacceptable, request the smallest actionable reason before recording rejection. Do not invent a repair plan from an unspecified dislike.

After rejection, submit a complete revised plan, obtain fresh approval, execute, verify, and request acceptance again. Repeat without a fixed round limit.

## 8. Verification payload

Use exactly:

```json
{
  "candidate_content_sha256": "<latest candidate content hash>",
  "status": "pass_with_residuals",
  "summary": "Verification summary.",
  "information_check": {
    "status": "pass",
    "summary": "Every source and candidate information unit has a counterpart."
  },
  "structure_check": {
    "status": "pass",
    "summary": "Protected content and document functions are intact."
  },
  "style_check": {
    "status": "pass",
    "summary": "Approved findings were rescanned and no blocking new pattern appeared."
  },
  "finding_results": [
    {
      "finding_id": "PH-001",
      "status": "resolved",
      "note": "The approved mechanism is absent."
    }
  ],
  "new_findings": [],
  "residuals": ["A low-risk excluded finding remains."]
}
```

Check status is exactly `pass` or `failed`. Finding status is exactly `resolved`, `partly_resolved`, `unchanged_for_safety`, or `not_in_scope`. Each new finding uses the complete finding object from `agents/review.md`.

## 9. Recovery and failures

To resume after context loss:

1. Locate the workflow workspace.
2. Run `full_workflow.py gate`.
3. Read `resume.md` and the view named by the current stage.
4. Read the directly routed playbook for that action.
5. Execute only the returned `next_action`.

Failure rules:

- `invalid_transition`: rerun gate; do not force the intended action.
- `stale_plan`: present or reread the current plan and obtain approval for its exact version and hash.
- `stale_document` or `document_changed`: return to the state-referenced artifact; do not replace hashes manually.
- `candidate_mismatch`: rebuild the candidate from the current base and preserve the original manifest.
- invalid payload: correct the payload file; never hand-edit state.
- failed document extraction, analysis, validation, or rendering: follow `references/document-yaml-contract.md` and stop until repaired.
- missing workspace or authoritative state: report the blocker. Do not reconstruct an approval history from prose conversation.

Use `--action cancel` with `{"reason": "..."}` only when the user explicitly cancels. `done` and `cancelled` reject every later mutation.

## 10. LLM and script responsibilities

The LLM must:

- interpret meaning, genre, voice, evidence, and user intent;
- perform the exhaustive review and create findings;
- negotiate and write the revision plan;
- revise only approved prose;
- perform semantic and stylistic verification;
- explain reports and obtain explicit decisions.

The scripts must:

- extract and validate protected documents and exact sentence statistics;
- validate payload fields and enums;
- calculate hashes, bind approval, enforce transitions, and update state atomically;
- render authoritative reports and recovery views.

Never use a temporary script for diagnosis, planning, rewriting, or semantic verification. Never hand-assemble `state.yaml`, invent a gate result, edit a read-only view as state, or bypass the workflow because the intended next step seems obvious.

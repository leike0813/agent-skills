# Review-mode workflow

Use this workflow only after `SKILL.md` routes the request to review or full mode. `SKILL.md` remains authoritative for invariants, protected content, and the numbered taxonomy.

## Contents

1. Required inputs
2. Coverage and statistics
3. Exhaustive scan
4. Findings
5. Revision plan
6. Structured payload
7. Delivery

Read `references/diagnostic-guidance.md` and `references/document-yaml-contract.md` completely before starting. Review mode diagnoses eligible prose and never edits the source.

## 1. Establish the review contract

Record:

- input form and format: pasted text or file; plain, Markdown, Quarto, or LaTeX;
- language mix and genre, when identifiable;
- requested coverage and user exclusions;
- eligible prose and protected regions;
- locator system;
- parser, context, and coverage limitations.

Use verifiable locators:

- Plain text: `P3 S2`, optionally followed by a short opening phrase.
- Markdown: heading path plus paragraph, list, table, and sentence location.
- Quarto: Markdown locator plus fenced div, callout, or executable-cell context when relevant.
- LaTeX: section or environment path plus paragraph, retaining useful command context.
- Structured artifact: include `seg-######`, source lines, and a human-readable locator when possible.

Stop and request the smallest missing input when the text is unavailable, unreadable, or too incomplete to judge local mechanisms.

## 2. Build the document and coverage ledger

Use `scripts/document_pipeline.py extract` for every file. In full mode, also use it for pasted text by saving the exact input to a task-local temporary source outside the Skill package. Standalone review may handle simple pasted plain text directly only when protection and exact sentence counting remain reliable.

Check the command envelope and continue only when `ok` is `true`. Build a coverage ledger for every eligible prose segment or paragraph. Resolve each entry as:

- `finding:<IDs>`: one or more supported findings cover it;
- `clear`: the scan found no supported feature;
- `unresolved`: context or parsing prevents judgment;
- `excluded`: protected or outside scope.

Never leave an entry pending. Report the aggregate coverage, not the full ledger unless the user asks.

Record the exact validated `source.format` in the review scope. A `.qmd` source uses `quarto`; never relabel it as `markdown`.

## 3. Capture the sentence profile

Use the fresh artifact analysis. Report:

- eligible sentence count and unit label;
- mean, median, population standard deviation, coefficient of variation, quartiles, minimum, and maximum;
- individual lengths when fewer than five eligible sentences exist;
- uniform-run locators;
- parser warnings and coverage limits;
- a genre- and language-aware interpretation.

Statistics are descriptive. Record a uniform-rhythm finding only when close reading also shows mechanical openings, clause shapes, subjects, punctuation, or rhetorical movement that the genre does not explain.

## 4. Run the exhaustive scan

Complete every pass even after finding obvious issues.

### Pass A: information and claims

Test patterns 1–6 and 34 for inflated significance, vague notability or attribution, participial pseudo-analysis, promotion, generic challenge/future movement, repetition, and zero-information expansion.

### Pass B: words and syntax

Test patterns 7–13, 23–24, 26–28, 35, 38, and 39. Confirm a mechanism rather than matching watched words. Check whether academic framing delays the concrete claim and whether the prose erases a stance that the source or genre requires.

### Pass C: organization and formatting

Test patterns 15–20, 25, 29–30, and 36. Compare headings, paragraphs, lists, openings, and conclusions. Preserve real navigation, taxonomy, comparison, and required genre structure.

### Pass D: rhythm and rhetoric

Test patterns 14, 21–22, 31–33, and 37. Combine sentence statistics with local reading. Distinguish repeated manufactured cadence from one purposeful short sentence or punctuation choice.

### Pass E: false-positive and protection challenge

For every provisional finding, ask:

1. Is this the author's eligible prose rather than a quotation, title, term, identifier, mandated wording, or markup artifact?
2. Is the mechanism visible, or did only a watched word trigger attention?
3. Does genre, discipline, translation, or structure explain it?
4. Would the suggestion risk a fact, qualification, relation, register, stance, or deliberate voice feature?
5. Can one cause cover related spans without hiding distinct locations?

Discard false positives. Move context-dependent cases to unresolved items.

### Pass F: completeness reconciliation

Resolve every coverage entry. Search once for unreviewed prose and uniform runs. Every suspected span must appear in a finding or unresolved item.

## 5. Write findings

Assign stable IDs in source order: `PH-001`, `PH-002`, and so on. One finding represents one primary mechanism.

Each finding contains:

- `locators`: every affected location or bounded range;
- `excerpt`: only enough source text to verify the issue;
- `pattern`: number and name;
- `family`: primary feature family;
- `evidence`: local, distributional, and contextual cues actually present;
- `explanation`: why the mechanism is suspicious here;
- `confidence`: `high`, `medium`, or `low`;
- `severity`: `high`, `medium`, or `low`;
- `suggestion`: bounded operation, not an unapproved full rewrite;
- `preserve`: information, wording, structure, or voice that must survive;
- `risk`: `high`, `medium`, or `low` semantic/structural risk.

Keep confidence and severity separate. Quote each unique passage once and cross-reference overlapping secondary findings.

Use `UR-001`, `UR-002`, and so on for unresolved items. Each records locators, the reason for uncertainty, and the specific context needed.

## 6. Build the revision plan

In standalone review, use findings and priorities as recommendations but do not create workflow state. In full mode, create an initial plan in the same review payload.

Assign `RP-001`, `RP-002`, and so on. Group findings only when they share one edit operation or must change together. Each plan item contains:

- linked finding IDs and exact locators;
- one bounded operation;
- expected effect;
- preservation constraints;
- risk: `high`, `medium`, or `low`;
- recommendation: `include`, `optional`, or `defer`;
- disposition: `include`, `exclude`, or `pending`.

Use a conservative default. Mark an item `pending` when it needs user judgment or missing context. Never add stance, evidence, disagreement, limitations, or surprise absent from the source. A missing author voice may become an edit only when existing wording or user input supplies the stance; otherwise keep it unresolved.

## 7. Full-mode structured payload

Write a JSON object to a task-local payload file. JSON is the supported YAML 1.2 subset. Use exactly these top-level keys:

```json
{
  "scope": {
    "input_form": "file",
    "format": "markdown",
    "languages": ["English"],
    "genre": "research article",
    "included": ["eligible prose"],
    "excluded": ["bibliography"],
    "locator_system": "heading path, paragraph, sentence, segment ID",
    "limitations": []
  },
  "assessment": "Evidence-based overall assessment without an authorship verdict.",
  "sentence_interpretation": "Contextual interpretation; do not copy numerical statistics here.",
  "findings": [],
  "unresolved": [],
  "coverage": {
    "eligible_regions": 0,
    "reviewed_regions": 0,
    "clear_regions": 0,
    "finding_regions": 0,
    "unresolved_regions": 0,
    "excluded_regions": 0,
    "complete": true
  },
  "plan": {
    "summary": "Conservative intervention scope.",
    "user_constraints": [],
    "items": []
  }
}
```

The workflow runtime copies numerical analysis from the validated document artifact. Do not hand-copy or estimate those values in the payload.

A finding object uses exactly:

```json
{
  "id": "PH-001",
  "locators": ["P1 S1"],
  "excerpt": "source excerpt",
  "pattern": "8. Copula avoidance",
  "family": "language and grammar",
  "evidence": "visible mechanism",
  "explanation": "contextual explanation",
  "confidence": "high",
  "severity": "low",
  "suggestion": "bounded operation",
  "preserve": ["claim strength"],
  "risk": "low"
}
```

A plan item uses exactly:

```json
{
  "id": "RP-001",
  "finding_ids": ["PH-001"],
  "locators": ["P1 S1"],
  "operation": "Restore the simple copula.",
  "expected_effect": "Remove formulaic inflation.",
  "preserve": ["the proposition"],
  "risk": "low",
  "recommendation": "include",
  "disposition": "include"
}
```

## 8. Deliver the review

Standalone review returns, in order:

1. scope and coverage;
2. overall assessment;
3. sentence-length profile;
4. all supported findings;
5. priorities;
6. unresolved items;
7. coverage closeout.

If no finding survives the false-positive pass, say so plainly and still report scope, statistics, limitations, and coverage.

In full mode, submit the structured payload through `agents/full.md`. Present the rendered review report and revision plan together, ask one concise plan-decision question, and do not edit the source.

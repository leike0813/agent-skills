# Document YAML contract

Read this reference before using or editing an artifact produced by `scripts/document_pipeline.py`. The artifact is JSON text with a `.yaml` suffix. JSON is a YAML 1.2 subset and allows the dependency-free runtime to preserve strings exactly.

## Contents

1. Commands and stable results
2. Artifact shape and immutable fields
3. Protected-content and sentence-analysis rules
4. Editing and full-mode candidate cycles
5. Error recovery

## Commands

Run from the Skill package directory with Python 3.11 or later:

```bash
python scripts/document_pipeline.py extract --input INPUT --format auto --output DOCUMENT.yaml
python scripts/document_pipeline.py analyze --input EDITED.yaml --output ANALYZED.yaml
python scripts/document_pipeline.py validate --input ANALYZED.yaml
python scripts/document_pipeline.py render --input ANALYZED.yaml --output OUTPUT
```

`extract` accepts `--format auto|plain|markdown|quarto|latex`. Auto detection recognizes common `.txt`, `.text`, `.md`, `.markdown`, `.mdown`, `.qmd`, `.tex`, and `.latex` suffixes. `.qmd` maps to the distinct `quarto` format. Specify the format for other suffixes.

`extract`, `analyze`, and `render` refuse an existing destination. Pass `--overwrite` only when replacing that exact path is intentional and authorized. Writes are atomic when the destination directory is on one filesystem.

## Stable command result

Every command emits exactly one JSON object on stdout:

```json
{
  "ok": true,
  "command": "extract",
  "artifact": "/absolute/path/document.yaml",
  "summary": {},
  "error": null
}
```

The five top-level keys are always present. On failure, `ok` is `false`, `artifact` is `null`, `summary` is empty, and `error` contains `code` and `message`. The process exits nonzero and also writes a diagnostic to stderr. Branch on `ok` or the exit status, not on diagnostic prose.

## Artifact shape

```json
{
  "schema_version": "paper-humanizer.document/v1",
  "source": {
    "name": "paper.md",
    "format": "markdown",
    "sha256": "...",
    "byte_order_mark": false
  },
  "segments": [
    {
      "id": "seg-000001",
      "kind": "prose",
      "role": "markdown_prose",
      "locator": {"line_start": 1, "line_end": 1},
      "text": "Eligible prose.",
      "analysis_effect": "text",
      "checksum": null
    },
    {
      "id": "seg-000002",
      "kind": "protected",
      "role": "inline_code",
      "locator": {"line_start": 1, "line_end": 1},
      "text": "`fixed()`",
      "analysis_effect": "one",
      "checksum": "..."
    }
  ],
  "manifest_sha256": "...",
  "analysis": {
    "content_sha256": "...",
    "unit_label": "words",
    "sentence_count": 1,
    "reliable_distribution": false,
    "sentences": [],
    "statistics": {},
    "uniform_runs": [],
    "warnings": []
  }
}
```

The validator requires the exact schema keys. Unknown, missing, or reordered segment identities are errors.

## Editable and immutable fields

The only editable values are `text` fields on segments whose `kind` is `prose`.

Treat all of these as immutable:

- artifact and source metadata;
- segment count, order, IDs, kinds, roles, and locators;
- every `protected` segment's text and checksum;
- `analysis_effect`;
- `manifest_sha256`;
- the existing `analysis` object, which the `analyze` command replaces.

Do not add, remove, split, join, or reorder segments. Do not copy a new checksum into a changed protected segment. The manifest deliberately permits prose-text edits while detecting immutable-structure changes.

After any prose edit, `analysis.content_sha256` is stale. `validate` and `render` reject stale analysis. Run `analyze` to a new artifact first.

## Protected analysis effects

Protected content remains byte-for-byte present for rendering but contributes to analysis according to `analysis_effect`:

- `zero`: contributes no countable text;
- `one`: contributes one placeholder unit, used for inline code or formulas when they function inside a sentence;
- `boundary`: contributes a paragraph boundary so sentences do not join across blocks;
- `text`: eligible text; prose segments always use this effect.

The adapters conservatively protect:

- plain-text blank paragraph separators;
- Markdown frontmatter, fenced and indented code, inline code, HTML comments/tags, math, citations, link destinations, image syntax, autolinks, table delimiters, and markup tokens;
- Quarto's shared Markdown structures plus shortcodes, Pandoc citation and cross-reference identifiers, valid attribute blocks, and fenced div markers; visible prose inside fenced divs remains editable;
- LaTeX comments, math, protected environments, command syntax and non-prose arguments, citation/label-like commands, and structural markup.

An inline Quarto shortcode contributes one placeholder unit. A shortcode on an otherwise blank line and each fenced div marker contribute a paragraph boundary. The adapter does not execute code, evaluate shortcodes, resolve includes, or infer generated text.

Supported text-bearing LaTeX commands expose their prose arguments while retaining wrappers. If extraction cannot balance a required fence, delimiter, environment, group, or brace, it fails instead of guessing.

## Sentence boundary rules

Analysis operates on eligible prose after protected effects are applied.

1. Sentence terminators are `.`, `?`, `!`, `。`, `？`, and `！`.
2. Closing quotes and brackets attach to the preceding sentence.
3. Decimal points, common abbreviations, initials, URLs, email-like tokens, and obvious non-terminal periods are protected from splitting.
4. A line break by itself is not a sentence boundary. Protected blocks and blank paragraph separators are boundaries.
5. A final nonempty span without terminal punctuation counts as a sentence.

This is deterministic segmentation, not full linguistic parsing. Inspect warnings and source context around abbreviations or specialized notation.

## Length units

For all-English eligible prose, `unit_label` is `words`. Each Latin-script word or numeric token counts as one; a hyphenated or apostrophe-linked token counts as one when matched as a unit.

For Chinese, mixed-language, or placeholder-bearing prose, `unit_label` is `length_units`:

- each Han character: one unit;
- each Latin-script word or numeric token: one unit;
- each inline protected placeholder: one unit;
- citation markers recognized by the adapter/counting rule: zero units.

URLs collapse to one placeholder rather than contributing their components.

## Analysis fields

Each entry in `sentences` contains a stable sentence ID for that analysis, the contributing segment IDs, and its integer `length`.

`statistics` contains:

- `mean`;
- `median`;
- `population_stddev`;
- `coefficient_of_variation`, equal to population standard deviation divided by the mean;
- `q1` and `q3`, calculated as medians of the lower and upper halves;
- `minimum` and `maximum`.

With no eligible sentences, numeric statistics are null. With fewer than five, `reliable_distribution` is false and warnings state that distributional interpretation is unreliable.

`uniform_runs` reports non-overlapping runs of at least four adjacent sentences whose maximum and minimum lengths differ by no more than the larger of two units or ten percent of the run median. Each run includes sentence endpoints, contributing segment IDs, and lengths. Treat it as a location hint, not a defect.

`content_sha256` binds analysis to the current segment text and effects. A prose edit changes the expected hash.

## Editing cycle

1. Extract the exact source to a new artifact.
2. Confirm the success envelope and inspect parser warnings.
3. Review eligible `prose` segments. Keep all protected content untouched.
4. In full mode, edit approved prose text fields only when the workflow gate returns `execute_revision` for the current plan hash and base content hash.
5. Analyze the edited artifact to a new path.
6. Validate the analyzed artifact.
7. Render it to a new output path.
8. Compare the output's structure and protected content with the source, then run the semantic preservation check against both the immediate base and the original source anchor.

## Full-mode candidate chains

`scripts/full_workflow.py` stores workflow state separately from this document artifact. Do not add findings, plan decisions, approvals, verification, or acceptance fields to the document schema.

Each full-mode execution starts from the `current_document` returned by the workflow state and produces a fresh analyzed candidate artifact. The workflow runtime checks that every candidate retains the original source hash, manifest, and format. After a user rejects a verified candidate, that candidate becomes the next cycle's base; the first extracted document remains the semantic-drift anchor for every verification round.

Document validation proves deterministic structure and analysis integrity. It does not prove that edits match the approved plan or preserve meaning; the full workflow's LLM verification and state gate own those checks.

No-op extraction followed by rendering must reproduce the original UTF-8 bytes, including a UTF-8 byte-order mark and original line endings.

## Recovery by error code

| Error code or class | Meaning | Recovery |
|---|---|---|
| `unknown_format` | Auto detection cannot identify the input | Re-run `extract` with an explicit supported format |
| `invalid_utf8` | Input is not UTF-8 | Obtain or create an authorized UTF-8 source; do not guess transcoding |
| `unclosed_*`, `unbalanced_*`, `missing_text_argument` | Markup cannot be separated safely | Fix the source syntax with authorization or narrow to a valid excerpt |
| `output_exists` | Destination already exists | Choose a new path or obtain permission to use `--overwrite` |
| `invalid_artifact_json`, `invalid_schema` | Artifact is not the exact JSON-compatible contract | Return to a valid extracted artifact and reapply prose-only edits |
| `protected_content_changed` | Protected text differs from its checksum | Restore it from the extracted artifact; do not regenerate the checksum |
| `invalid_manifest` | Segment order or immutable metadata changed | Restore the original structure and reapply prose-only edits |
| `stale_analysis` | Prose changed after the last analysis | Run `analyze`, then validate the new artifact |

If a command returns `internal_error`, preserve the input and artifact, report the command and error envelope, and stop. Do not render manually or claim statistics that the engine did not produce.

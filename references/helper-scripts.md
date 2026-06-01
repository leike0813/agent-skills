# Helper Scripts

Read this when invoking or diagnosing paper-drafter runtime scripts.

All commands use:

```bash
python <script> ...
```

## `init_artifact_workspace.py`

Path: `paper-drafter/scripts/init_artifact_workspace.py`

Use when:

- a new artifact workspace is needed,
- `paper-drafter.db` does not exist.

Do not use when:

- an existing workspace already has `paper-drafter.db`; run `gate-and-render` instead.
- document language or working language has not been confirmed or reasonably inferred.

Command:

```bash
python scripts/init_artifact_workspace.py \
  --artifact-root <ARTIFACT_ROOT> \
  --document-language <language> \
  --working-language <language>
```

Writes:

- `paper-drafter.db`,
- read-only view files,
- `sections/`.

On success:

- read stdout JSON,
- read `01-agent-resume.md`,
- follow `next_action`.

Expected success stdout includes `ok=true`, `artifact_root`, `db_path`, and `next_action`.

On failure:

- stop,
- report the error,
- do not create manual substitute views.

## `gate_and_render_workspace.py`

Path: `paper-drafter/scripts/gate_and_render_workspace.py`

Use when:

- resuming,
- after context compression,
- after a user asks "where are we?",
- after any suspected view drift,
- after a script failure has been repaired.

Command:

```bash
python scripts/gate_and_render_workspace.py \
  --artifact-root <ARTIFACT_ROOT>
```

Output:

- stdout JSON with `next_action`, blockers, confirmations, repair sequence, and payload example.
- refreshed read-only Markdown views.

Expected success stdout includes:

```json
{
  "ok": true,
  "current_stage": "stage_id",
  "stage_gate": "ready-or-blocked",
  "next_action": "next_action",
  "status_summary": "string",
  "instruction_refs": [],
  "core_instruction": "string",
  "next_action_payload_example": {},
  "blockers": [],
  "pending_user_confirmations": [],
  "repair_sequence": [],
  "resume_packet": {}
}
```

If it returns `ok=false`:

- treat the workspace as blocked,
- follow `repair_sequence`,
- do not continue semantic drafting.

Safe to rerun:

- after every formal write,
- after context compression,
- after a view was manually deleted,
- after a repair,
- when the user asks for current status.

## `submit_stage_payload.py`

Path: `paper-drafter/scripts/submit_stage_payload.py`

Use when:

- a semantic artifact has been confirmed by the user,
- the current `next_action` requires a DB write,
- a final confirmation must be recorded.

Command:

```bash
python scripts/submit_stage_payload.py \
  --artifact-root <ARTIFACT_ROOT> \
  --stage <stage_id> \
  --payload-file <payload.json>
```

Allowed stages are documented in `payload-and-sql-recipes.md`.

On success:

- the script writes DB state,
- appends `action_log`,
- recomputes gate,
- renders views,
- returns the next gate result.

Expected success stdout includes `ok=true`, `stage`, `next_action`, `stage_gate`, `blockers`, and `pending_user_confirmations`.

On failure:

- repair the JSON payload or DB issue,
- rerun the script,
- do not manually patch rendered views.

If you need the full `next_action_payload_example` after a submit, run `gate-and-render`.

## `reference_guide.py`

Path: `paper-drafter/scripts/reference_guide.py`

Use when:

- choosing a canonical domain,
- locating writing-guide headings for a phase and paper section,
- checking reference index health.

Common commands:

```bash
python scripts/reference_guide.py check
python scripts/reference_guide.py list
python scripts/reference_guide.py nav \
  --domain computational-algorithm-data-driven \
  --drafting-phase section-drafting \
  --paper-section method
python scripts/reference_guide.py show \
  --domain computational-algorithm-data-driven \
  --heading "5.6 Method / Model / Algorithm 方法、模型或算法"
```

It does not:

- write SQLite state,
- decide evidence sufficiency,
- summarize papers,
- generate drafts.

Record important reference routes through `submit_stage_payload.py --stage reference_route` only when the route should be visible after resume.

## Failure Handling Matrix

| Failure | Required action |
| --- | --- |
| `paper-drafter.db` missing | Confirm this is the intended artifact root; initialize only if it is a new workspace. |
| Schema validation failure | Stop and report; do not continue from Markdown views. |
| Payload validation failure | Fix the JSON or semantic payload; do not patch DB manually. |
| `blockers` non-empty | Resolve blocker with the user or evidence before later-stage work. |
| `pending_user_confirmations` non-empty | Ask for confirmation; do not submit a confirming payload before user acceptance. |
| Rendered view missing | Rerun `gate-and-render`; do not recreate view by hand. |

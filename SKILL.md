---
name: openspec-finalize
description: >-
  Finalize the sole active OpenSpec change that has every planning artifact
  complete and every implementation task checked. Require and delegate to the
  official project-local OpenSpec sync/archive skills, then create one verified
  Git commit while preserving relevant pre-existing staging.
  Use when the user wants a hands-off finalization of whichever change is
  uniquely ready. Do not use to force-archive a named change or to choose among
  multiple ready changes; use openspec-archive-change directly for those cases.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
license: MIT
compatibility: >-
  Requires Git, the openspec CLI, and project-level official OpenSpec skills
  openspec-archive-change and openspec-sync-specs, either in the active skill
  catalog or in a recognized project-scoped skill directory.
metadata:
  author: local
  version: "0.2.0"
---

Finalize exactly one uniquely ready OpenSpec change, synchronize its delta specs,
archive it, and create one Git commit without assuming that the repository is an
isolated worktree.

This skill is intentionally stricter than `openspec-archive-change`. It has no
change picker and grants no override for incomplete artifacts or tasks.

## Non-negotiable invariant

Act only when the selected OpenSpec root contains **exactly one eligible active
change**.

A change is eligible only when all of the following are true:

1. OpenSpec can load its status without a diagnostic.
2. `isPlanningComplete` is `true`.
3. Every artifact status is `done` or `skipped`.
4. Its apply instructions expose a real implementation task list:
   - `progress.total > 0`;
   - `progress.complete === progress.total`;
   - `progress.remaining === 0`;
   - `state === "all_done"`;
   - every returned task has `done: true`.

A change with no task file, no task checkboxes, an unreadable task list, or an
intentionally taskless schema is **not eligible** for this skill. The user can
invoke the official archive skill directly when that behavior is desired.

A change name supplied by the user is only an assertion. It must equal the sole
eligible change; it never breaks a tie or bypasses the invariant.

## Required official-skill resolution

OpenSpec installs its agent integration at the **project level by default**.
Do not treat the absence of a user-global skill copy as evidence that OpenSpec is
not installed for the current project.

Before any filesystem or Git mutation, resolve both required skills in this exact
order:

1. Inspect the active harness's already loaded or injected skill catalog for the
   exact names:
   - `openspec-archive-change`
   - `openspec-sync-specs`
2. For each skill missing from that catalog, inspect only the current project's
   recognized project-scoped skill roots:
   - the current harness's documented project-level skill directory or
     directories;
   - `.agents/skills/<skill-name>/SKILL.md` when that shared project-level root
     exists;
   - another project-scoped root under the current Git top level only when the
     harness or the project's OpenSpec integration explicitly declares it.
3. Do not recursively search arbitrary repository directories. Check only known
   project-level skill roots associated with the current project and harness.
4. If a required skill exists as a valid project-level `SKILL.md` but is absent
   from the injected catalog, read its full instructions directly and execute
   those instructions as the delegated workflow. A catalog omission alone is
   **not** a failure.
5. Never search, inspect, or load a fallback copy from any user-global,
   machine-global, or system-global skill directory. This includes skill roots
   under the user's home directory, XDG config/data directories, AppData,
   application-support directories, globally installed packages, or other
   locations outside the current project. A global copy cannot satisfy this
   gate.
6. Verify that each resolved skill has the exact required name. When metadata is
   visible, require `metadata.author: openspec`. If several project-level copies
   are found and their instructions differ, stop and report the conflicting
   paths rather than choosing silently.
7. Read the current full instructions of both resolved skills before continuing.

If either skill is absent from both the active catalog and the recognized
project-level roots, unreadable, or clearly not the official OpenSpec skill, stop
without modifying files. Recommend that the user regenerate the project-level
integration with `openspec update` or initialize the current tool with
`openspec init`, but do not run either command automatically and do not search
for a global substitute.

Never replace the official semantic sync workflow with file copying, a custom
merge, or a direct `openspec archive` call. This skill owns selection, Git scope,
commit creation, and optional Orca bookkeeping; the official OpenSpec skills own
spec synchronization and archiving.

## Root selection

Use one OpenSpec root for the entire run.

- If the user explicitly names a registered OpenSpec store, resolve it once and
  keep `--store <id>` on every applicable OpenSpec command and on the delegated
  workflow.
- Otherwise let OpenSpec resolve the nearest/default root from the current
  directory.
- Record the successful command's `root.path`, `root.source`, and optional
  `root.store_id`. Do not switch roots later.
- Resolve real paths, not only lexical paths.

This version creates one commit in the current Git repository. Before any
mutation, require the selected OpenSpec root and every path that the archive may
write to be inside the current Git top level. If a selected store lives in a
separate repository or outside the current Git worktree, stop and explain that a
single safe commit cannot span both roots.

## Phase 1: Discover the sole eligible change

1. Confirm that the current directory is inside a Git repository and record:

   ```bash
   git rev-parse --show-toplevel
   git rev-parse --verify HEAD
   ```

2. Discover all active changes in the selected OpenSpec root.

   Prefer:

   ```bash
   openspec status --all --json
   ```

   If and only if the installed CLI rejects `--all` as an unknown option, fall
   back to:

   ```bash
   openspec list --json
   openspec status --change "<name>" --json
   ```

   for every listed active change. Do not fall back after arbitrary command,
   root-resolution, schema, or parse failures.

3. Treat any malformed JSON, root mismatch, missing change entry, duplicate
   change name, or per-change load diagnostic as a failure to prove uniqueness.
   Stop without modifying files.

4. For every change whose planning artifacts appear complete, run:

   ```bash
   openspec instructions apply --change "<name>" --json
   ```

   using the same selected-root flags. Evaluate eligibility using the exact
   invariant above. Do not infer task completion only from filenames, prose, Git
   history, branch names, or conversation context.

5. Partition active changes into:
   - eligible;
   - planning-incomplete;
   - task-incomplete or taskless;
   - unreadable/error.

6. Continue only when the eligible set contains exactly one change.

   - Zero eligible changes: stop and summarize why no change qualifies.
   - More than one eligible change: list the eligible names and stop.
   - Do not ask the user to choose one.
   - Do not use recency, branch name, workspace name, supplied change name, or
     conversational context as a tiebreaker.

7. Announce and record:
   - selected change name;
   - schema name;
   - change root;
   - planning root;
   - artifact paths;
   - task count;
   - optional user-supplied name assertion and whether it matched.

8. Before the change is moved, capture its title and intent with:

   ```bash
   openspec show "<change>" --json --diff
   ```

   If `--diff` is unsupported, retry only without `--diff`. Also retain the
   successful `instructions apply` response and read every available planning
   artifact needed to understand the change's implementation scope.

## Phase 2: Establish a safe Git commit scope

This skill may run in a shared working tree, but it must never sweep unrelated
work into the final commit. A non-empty Git index is allowed. The authoritative
boundary is the fully inspected index immediately before commit, not whether the
index happened to be empty at the beginning.

1. Stop before archiving if any Git operation is in progress, including merge,
   rebase, cherry-pick, revert, or bisect, or if any unmerged path exists.

2. Preserve the user's initial staging state instead of requiring an empty
   index:

   - Resolve the real index path with `git rev-parse --git-path index`.
   - Make a byte-for-byte temporary backup of that index outside the working
     tree, using the platform's normal file-copy mechanism.
   - Record the initial staged patch and path set with:

     ```bash
     git diff --cached --binary --full-index
     git diff --cached --name-status -z
     git diff --cached --check
     ```

   - Do not reset, unstage, rewrite, or otherwise normalize the user's existing
     index during preflight.
   - The index may be empty or non-empty. Existing staged content is a
     user-supplied candidate for this commit, not an automatic error and not
     automatically trusted.

3. Read the complete repository state using a NUL-safe status form, including
   individual untracked files, and inspect staged and unstaged diffs separately:

   ```bash
   git status --porcelain=v2 -z --untracked-files=all
   git diff --cached --check
   git diff --check
   ```

4. Classify every pre-existing staged hunk and every unstaged path or hunk as one
   of:

   - **related**: the selected change's own artifacts, or a change directly tied
     to a checked task, requirement, scenario, design decision, dependency
     update, generated output, or test for the selected change;
   - **unrelated**: clearly belongs to other work and must remain outside this
     commit;
   - **ambiguous/mixed**: attribution cannot be established confidently, or one
     file contains both selected-change work and unrelated work.

   Rules:

   - Pre-existing staged content may remain staged and be committed only when
     every staged hunk is related to the selected change.
   - This skill does not silently unstage user-selected content. If any staged
     hunk is unrelated or ambiguous, stop before archiving and tell the user to
     separate or unstage it.
   - Files under another active change directory are unrelated.
   - A path is not related merely because it is in the same repository, branch,
     workspace, staging area, or recent diff.
   - Broad files such as lockfiles, manifests, shared configuration, generated
     registries, changelogs, and snapshots require diff-level inspection.
   - A main spec already dirty before synchronization must be wholly attributable
     to the selected change if the official workflow may edit the same file.
   - Binary or generated files are related only when a checked task or a clear
     source/generated relationship accounts for them.
   - For a partially staged file, inspect both `git diff --cached -- <path>` and
     `git diff -- <path>`. Do not collapse staged and unstaged changes into one
     path-level assumption.
   - If any path contains both related and unrelated hunks, stop before
     archiving. Do not use interactive or heuristic partial staging to guess.

5. Record separately:

   - the exact initial staged paths and hunks that are related;
   - related unstaged paths or hunks that the final commit must add;
   - unrelated unstaged paths that must remain untouched;
   - any expected OpenSpec paths that the official archive workflow may create,
     modify, delete, or move.

   Use exact file paths, not broad directory pathspecs, except for the selected
   change's exact old directory and its exact future archive directory.

6. Repeat the entire eligibility scan and Git-scope check immediately before the
   first archive mutation. The same change must still be the sole eligible
   candidate, the selected root must be unchanged, the user's existing staged
   content must still be classified as related, and no newly observed staged or
   unstaged change may remain unclassified.

## Phase 3: Delegate synchronization and archive

Invoke the official `openspec-archive-change` skill synchronously for the exact
selected change and selected root. Do not merely paraphrase its behavior and do
not call raw `openspec archive` as a substitute.

The user pre-authorizes only these ordinary delta-spec choices:

- If delta specs still need to be applied: choose **Sync now (recommended)**.
- If every delta is already synchronized: choose **Archive now**.
- If the change has no delta specs: continue with the official no-delta path.

Never choose:

- **Archive without syncing**;
- **Sync anyway** when the main specs already match;
- any validation bypass;
- any override for incomplete artifacts or tasks.

Do not pass `--no-validate`, do not use `--yes` to suppress an abnormal decision,
and do not authorize capability retirement unless the selected change already
contains the official marker required by the OpenSpec workflow.

If the official skill observes a condition that contradicts this skill's earlier
eligibility result, treat it as concurrent drift: cancel or stop. Do not answer
through the warning. In particular, stop on incomplete artifacts/tasks,
validation errors, failed spec synchronization, failed post-sync verification,
an existing archive target, unclear retirement, root drift, or any exceptional
choice not pre-authorized above.

Wait for semantic synchronization and its verification to finish before the
change is moved. Never run sync and archive concurrently or in the background.

Record the official result, including:

- archive path;
- whether specs were synchronized, already synchronized, or absent;
- every main spec created, modified, or retired;
- warnings and validation results.

If the official workflow fails after modifying files, stop without staging or
committing. Report exactly what changed. Do not roll back, reset, or improvise a
manual archive.

## Phase 4: Build and verify the final commit index

After a successful official archive:

1. Verify that the selected change is no longer active and that the reported
   archive path exists inside the recorded Git top level.

2. Re-read the complete Git status and inspect staged and unstaged diffs for
   every changed path. Reclassify the current state into:

   - related hunks that were already staged before this skill started;
   - selected-change implementation changes that still need staging;
   - finalization changes produced by the official workflow, including the exact
     old change path, exact archive path, and exact main-spec paths it changed;
   - unrelated changes that must remain unstaged;
   - ambiguous or unexpected changes.

3. Stop before adding anything to the index if:

   - an unexpected or ambiguous path or hunk appeared;
   - an official finalization path is outside the Git top level;
   - a path now mixes selected-change and unrelated hunks;
   - any pre-existing staged hunk is no longer attributable to the selected
     change;
   - the archive result cannot account for its own OpenSpec changes.

   The archive may already be complete at this point. Report that state clearly;
   do not move it back automatically.

4. Construct an exact commit scope containing only:

   - related hunks already present in the initial index;
   - related implementation changes identified before archive;
   - exact files under the selected change's old path that are now deleted;
   - exact files under the reported archive path;
   - exact main-spec files created, changed, or deleted by synchronization.

5. Preserve the user's valid pre-existing staged content and stage only missing
   related changes:

   - Do not unstage or rewrite a pre-existing staged hunk merely because it was
     present before this skill ran.
   - Use safely quoted exact path arguments and `--` only when every currently
     unstaged change at that path belongs in this commit:

     ```bash
     git add -A -- <exact-related-path-1> <exact-related-path-2> ...
     ```

   - For a partially staged path, run `git add -A -- <path>` only when every
     remaining unstaged hunk is related and should be committed. Otherwise stop;
     do not overwrite the user's partial staging boundary.
   - Never run bare `git add -A`, `git add .`, or stage a shared parent directory.
   - Leave every unrelated path unstaged.

6. Treat the final staged diff as the authoritative commit boundary:

   ```bash
   git diff --cached --check
   git diff --cached --name-status -z
   git diff --cached --stat
   git diff --cached --binary --full-index
   ```

   Inspect the complete staged diff, not only its path names. Continue only when
   all of the following are true:

   - every staged hunk is attributable to the selected change or its official
     OpenSpec synchronization/archive;
   - no unrelated or ambiguous hunk is staged;
   - every required archive move and synchronized main-spec change reported by
     the official workflow is staged;
   - all related implementation changes intended for this finalization are
     staged;
   - rename presentation does not hide an out-of-scope source or destination.

   The fact that the index was non-empty at the beginning is irrelevant once
   this final boundary passes.

7. If final staged-boundary verification fails before the commit command is
   attempted, restore the exact pre-run index from the temporary byte-for-byte
   backup, leave all working-tree content untouched, and verify that the staged
   diff again matches the recorded initial staged patch. If exact restoration
   cannot be verified, stop and report the index state explicitly. Never discard
   file content.

8. Do not create an empty commit. If no staged changes remain, report that the
   archive succeeded but no commit was created.

## Phase 5: Create exactly one commit

1. Inspect recent repository subjects:

   ```bash
   git log -12 --pretty=format:%s
   ```

2. Generate one concise subject, preferably no more than 72 characters:

   - Follow the repository's evident commit convention; do not impose
     Conventional Commits when the repository does not use them.
   - Use the captured OpenSpec title, proposal intent, change id, and staged diff.
   - If implementation files are included, describe the implemented behavior,
     not merely the mechanical archive.
   - If the staged diff contains only OpenSpec sync/archive files because the
     implementation was committed earlier, describe finalizing or archiving the
     change.
   - Humanize the change id when needed.

3. Commit exactly once and include this exact body trailer:

   ```text
   OpenSpec-Change: <change-name>
   ```

4. Do not amend, push, merge, rebase, tag, delete a branch/worktree, bypass hooks,
   or use `--no-verify`.

5. If a Git hook or commit command fails, stop. Leave the verified staged changes
   available for inspection and report the failure; do not retry with weaker
   safeguards.

6. On success, remove the temporary pre-run index backup and record:

   ```bash
   git rev-parse --short HEAD
   git show --stat --oneline --summary HEAD
   ```

7. Confirm that unrelated paths, if any, remain uncommitted and unstaged.

## Phase 6: Optional Orca bookkeeping

This phase is best effort and never changes the success of the OpenSpec/Git
finalization.

1. Attempt it only when Orca is installed, its runtime is reachable, and the
   current directory resolves to an Orca workspace with:

   ```bash
   orca worktree current --json
   ```

2. Update the workspace comment with the finalized change and commit SHA:

   ```bash
   orca worktree set --worktree active \
     --comment "OpenSpec <change> finalized and committed (<sha>)" \
     --json
   ```

3. Add `--workspace-status completed` only when both are true after the commit:

   - the Git working tree is completely clean; and
   - the selected OpenSpec root has no remaining active changes.

   Otherwise leave the workspace status unchanged. A shared workspace can have
   completed one OpenSpec change while still containing other work.

4. Report Orca failures as non-blocking. Never amend or revert the Git commit
   because bookkeeping failed.

## Success output

Return a compact report containing:

```markdown
## OpenSpec Finalized

- Change: <name>
- Schema: <schema>
- Tasks: <complete>/<total>
- Specs: <synced | already synced | no delta specs>
- Archive: <path>
- Commit: <short-sha> <subject>
- Pre-existing staged changes included: <none | paths/count>
- Unrelated working-tree changes left untouched: <none | paths/count>
- Orca: <updated and completed | comment updated, status unchanged | skipped | failed non-blockingly>
```

## Failure output

Always distinguish among:

- **Preflight stopped, no mutations; original staging left untouched**;
- **Official sync/archive stopped, working tree may contain partial spec edits**;
- **Archive succeeded, commit not created; index restored to its pre-run state when restoration was required and verified**;
- **Commit succeeded, optional Orca bookkeeping failed**.

Name the failed invariant or guard, list relevant changes/candidates/paths, and
state the safest next action. Also state whether the Git index was untouched,
restored exactly from the pre-run backup, or intentionally left with the final
staged changes after a commit or hook failure. Never claim a rollback occurred
unless it was actually performed and verified.

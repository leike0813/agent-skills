# Scenario Playbooks

Use this reference when the user asks for a multi-step Git or GitHub CLI workflow. Keep the final plan grounded in the live context returned by `scripts/git-context.py`.

## Shared Preflight

Before planning any scenario:

1. Confirm `git.available` is true from `scripts/check-command.py`.
2. Confirm `scripts/git-context.py` returned `ok: true`.
3. Stop and explain blockers when `in_merge`, `in_rebase`, or `conflicted_files` is non-empty unless the user's goal is to resolve that state.
4. Check dirty working tree state before checkout, pull, merge, rebase, reset, or clean.
5. Check `upstream`, `ahead`, and `behind` before push, pull, merge, or rebase.

## Create And Push A Branch

Read when the user wants to create a local branch and publish it.

Typical commands:

```bash
git switch -c <branch>
git push -u origin <branch>
```

Teaching focus:

- `switch -c` creates and moves to the new branch in one step.
- `push -u` publishes the branch and records the upstream relationship.

Risk checks:

- Confirm the current branch is the intended starting point.
- Confirm the remote name when more than one remote exists.

## Commit Changes

Read when the user wants to create a commit.

Typical commands:

```bash
git status
git diff
git add <paths>
git diff --staged
git commit -m "<message>"
```

Teaching focus:

- `add` chooses what goes into the commit.
- `diff --staged` reviews the commit contents before recording it.
- `commit -m` creates the repository snapshot with a message.

Risk checks:

- Do not use `git add .` when the context shows unrelated untracked or unstaged files.
- Ask for or propose a commit message when the user's intended message is unclear.

## Sync A Branch With Main

Read when the user wants to update a branch with `main`, `master`, or another base branch.

Merge path:

```bash
git fetch origin
git merge origin/<base>
```

Rebase path:

```bash
git fetch origin
git rebase origin/<base>
```

Teaching focus:

- `fetch` updates remote-tracking branches without touching the current branch.
- `merge` preserves branch history and may create a merge commit.
- `rebase` replays local commits onto the new base and rewrites local commit IDs.

Risk checks:

- Ask whether the user prefers merge or rebase when team convention is unknown.
- Avoid rebase when the branch has already been shared and collaborators may have based work on it, unless the user confirms.
- Require a clean or intentionally stashed working tree before starting.

## Resolve Merge Or Rebase Conflicts

Read when `conflicted_files` is non-empty or the user asks to resolve conflicts.

Typical inspection commands:

```bash
git status
git diff
```

After manual or agent-assisted conflict edits:

```bash
git add <resolved-files>
git merge --continue
```

For rebase conflicts:

```bash
git add <resolved-files>
git rebase --continue
```

Abort paths:

```bash
git merge --abort
git rebase --abort
```

Teaching focus:

- Conflict markers show competing versions.
- `add` marks a conflict as resolved.
- `--continue` resumes the paused operation.
- `--abort` returns to the pre-operation state when Git can safely do so.

Risk checks:

- Do not start a new merge, rebase, pull, checkout, reset, or clean while conflicts remain.
- Confirm with the user before choosing an abort path.

## Undo Recent Work

Read when the user wants to undo a commit or local changes.

Safer public-history path:

```bash
git revert <commit>
```

Local commit rewrite path:

```bash
git reset --soft HEAD~1
```

Destructive local path:

```bash
git reset --hard HEAD~1
```

Teaching focus:

- `revert` adds a new commit that cancels an old commit.
- `reset --soft` removes the commit but keeps changes staged.
- `reset --hard` discards commit and working tree changes.

Risk checks:

- Prefer `revert` for commits already pushed to a shared branch.
- Require explicit confirmation before any `--hard` reset.

## Stash Temporary Changes

Read when the user needs a clean working tree without committing current work.

Typical commands:

```bash
git stash push -m "<message>"
git stash list
git stash pop
```

Teaching focus:

- `stash push` stores work temporarily.
- `stash pop` reapplies the latest stash and removes it from the stash stack.

Risk checks:

- Use a message when multiple stashes may exist.
- Warn that `stash pop` can create conflicts.

## Create A Pull Request

Read when the user wants to create a PR with GitHub CLI.

Typical commands:

```bash
gh auth status
git push -u origin <branch>
gh pr create --base <base> --head <branch> --title "<title>" --body "<body>"
```

Teaching focus:

- `gh auth status` checks whether GitHub CLI can act on the user's account.
- `--base` is the target branch.
- `--head` is the source branch.

Risk checks:

- Confirm the pushed branch and base branch.
- Ask for title/body when they are not available from context.

## Inspect Or Merge A Pull Request

Read when the user wants to view, checkout, diff, or merge a PR via GitHub CLI.

Inspection commands:

```bash
gh pr view <number>
gh pr diff <number>
gh pr checkout <number>
```

Merge commands:

```bash
gh pr merge <number> --merge
gh pr merge <number> --squash
gh pr merge <number> --rebase
```

Teaching focus:

- `view` shows PR metadata and discussion.
- `diff` shows the code changes.
- `checkout` creates a local branch for testing.
- merge flags choose the repository history shape.

Risk checks:

- Treat `gh pr merge` as remote-state-changing and require explicit confirmation.
- Ask which merge method to use when repository convention is unknown.

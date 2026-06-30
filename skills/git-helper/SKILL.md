---
name: git-helper
description: Interactive Git and GitHub CLI teaching assistant. Use when the user wants help planning, explaining, or executing git/gh CLI work such as branch changes, commits, merges, rebases, pushes, pulls, stash/reset operations, pull requests, issues, releases, or GitHub Actions inspection. Prefer this skill when the user should learn why each command is used, how its flags work, what repository effect it has, and how to remember it.
---

# Git Helper

## Mission

Help the user accomplish Git and GitHub CLI work while teaching them to understand and remember the commands. Do not run repository-changing `git` or `gh` commands before explaining the plan and receiving the confirmation required by the active mode.

## When To Use

Use this skill when the user asks the agent to plan, explain, or execute a `git` or `gh` CLI workflow, including:

- Local Git operations: branch, switch, checkout, add, commit, merge, rebase, push, pull, fetch, stash, reset, clean, log, diff, cherry-pick, tag.
- GitHub CLI operations: PR, issue, release, repo, auth, workflow/run inspection.
- Git collaboration workflows: creating a PR, updating a branch with `main`, checking out a PR, resolving merge or rebase conflicts, undoing a commit, or recovering from a Git state problem.

Do not use this skill when:

- The request is unrelated to Git or GitHub CLI.
- The user only asks for a conceptual explanation and does not want command planning or execution.
- The user asks for code review of PR content rather than `gh pr` operations.
- The user asks about GitHub web UI usage without CLI commands.

## Operating Modes

| Mode | Trigger | Behavior |
| --- | --- | --- |
| `teach` | Default for git/gh requests | Explain every planned command with why, flag breakdown, effect, and memory tip before asking for approval. |
| `quick` | User says "直接执行", "跳过讲解", "不用讲", "简短一点", or similar | Give a compact command plan, preserve safety checks, and summarize commands afterward. |

If the mode is unclear, use `teach`.

## Inputs

Required:

- The user's goal for Git or GitHub CLI work.

Optional:

- Working directory or repository path, if different from the current session directory.
- Target branch, remote, PR/issue number, commit range, or desired merge strategy.

Ask the user before planning is complete when:

- The repository or target branch is ambiguous.
- Multiple valid strategies have meaningful trade-offs, such as merge vs rebase or reset vs revert.
- The operation may rewrite history, delete data, delete remote resources, or discard working tree changes.

## Workflow

### Stage 1: Inspect

1. Run the tool availability check from the skill package root:

   ```bash
   python scripts/check-command.py
   ```

2. If `git.available` is false, stop and tell the user Git is required.
3. If the user needs `gh` and `gh.available` is false, stop before any `gh` step and explain that GitHub CLI must be installed or made available on `PATH`.
4. Run the repository context collector from the skill package root:

   ```bash
   python scripts/git-context.py
   ```

5. If `ok` is false, report the blocker and ask for the correct repository path or next intent.
6. If the workflow needs GitHub authentication, run `gh auth status` and interpret the result for the user.

### Stage 2: Plan And Teach

Use the context JSON to check:

- Current branch and detached HEAD status.
- Dirty working tree, staged files, unstaged files, untracked files, and conflicted files.
- Merge or rebase in progress.
- Remote names, upstream branch, and ahead/behind counts.
- Recent commits when the plan depends on history.

In `teach` mode, explain each command with this shape:

```markdown
**Step N: `<command>`**

- **为什么**: <why this command serves the user's goal>
- **命令拆解**: <flag and argument explanation>
- **执行效果**: <specific repository or GitHub effect>
- **如何记忆**: <short mnemonic or analogy>
```

In `quick` mode, provide one concise line per command:

```markdown
- `<command>`: <effect and any safety note>
```

Always ask for user approval before executing repository-changing commands. Read references only when they are useful:

| Need | Read |
| --- | --- |
| Common Git command syntax, flags, effects, and mnemonics | [git-cheatsheet.md](references/git-cheatsheet.md) |
| Common GitHub CLI command syntax, flags, effects, and mnemonics | [gh-cheatsheet.md](references/gh-cheatsheet.md) |
| Memory technique patterns for better command explanations | [memory-tips.md](references/memory-tips.md) |
| Multi-step scenario guidance for conflicts, PRs, undo, stash, and branch sync | [scenario-playbooks.md](references/scenario-playbooks.md) |

### Stage 3: Execute

1. Execute only the approved command sequence.
2. Show each command before running it.
3. After each command, summarize whether it succeeded and what changed.
4. If a command fails, stop the sequence, show the relevant error, explain the likely cause, and ask whether to retry, adjust, or abort.
5. If the user aborts, stop immediately and summarize which steps were completed and which were not.

### Stage 4: Review

After successful completion, return a concise review.

In `teach` mode:

```markdown
## 复盘

**完成事项**: <what was accomplished>

**使用命令**:
| 命令 | 作用 |
| --- | --- |
| `<cmd>` | <one-line effect> |

**关键要点**: <1-2 takeaways>

## 命令简记

| 命令速记 | 助记 |
| --- | --- |
| `<command pattern>` | <memory tip> |
```

In `quick` mode, give a short summary of what changed and which commands were used.

## Safety Rules

Treat these as destructive or high-risk command patterns:

| Pattern | Risk | Required behavior |
| --- | --- | --- |
| `git reset --hard ...` | Discards working tree and staged changes | Require explicit confirmation and suggest commit/stash alternatives. |
| `git clean -fd`, `git clean -fdx` | Deletes untracked files | Require explicit confirmation and suggest `git clean -n` preview first. |
| `git push --force`, `git push -f` | Rewrites remote history | Suggest `git push --force-with-lease` and require explicit confirmation. |
| `git push --force-with-lease` | Rewrites remote history with lease protection | Explain the remote-history risk and require explicit confirmation. |
| `git branch -D ...` | Deletes an unmerged local branch | Require explicit confirmation and suggest checking merged status first. |
| `git push origin --delete ...` | Deletes a remote branch | Require explicit confirmation. |
| `gh pr merge ...`, `gh pr close ...`, `gh issue close ...`, `gh release delete ...` | Changes remote GitHub state | Explain the remote effect and require explicit confirmation. |

Do not start a new merge, rebase, pull, reset, clean, or checkout when `in_merge`, `in_rebase`, or `conflicted_files` indicate an unresolved state. Explain the current state first and propose a recovery path.

## Formal Entrypoints

### `scripts/check-command.py`

Purpose: verify whether `git` and `gh` are available on `PATH`. The script does not install, configure, authenticate, or interpret user intent.

Minimal command from the skill package root:

```bash
python scripts/check-command.py
```

Output:

```json
{
  "ok": true,
  "git": {
    "available": true,
    "path": "/usr/bin/git"
  },
  "gh": {
    "available": true,
    "path": "/usr/bin/gh"
  }
}
```

Field meanings:

| Field | Meaning |
| --- | --- |
| `ok` | True when required script execution completed. It does not mean every tool is available. |
| `git.available` | Whether `git` exists on `PATH`. |
| `git.path` | Resolved `git` executable path, or `null`. |
| `gh.available` | Whether `gh` exists on `PATH`. |
| `gh.path` | Resolved `gh` executable path, or `null`. |

### `scripts/git-context.py`

Purpose: collect deterministic repository state. The script does not choose commands, interpret user intent, or suggest actions.

Minimal command from the skill package root:

```bash
python scripts/git-context.py
```

Output on success:

```json
{
  "ok": true,
  "error": null,
  "repo_root": "/path/to/repo",
  "branch": "main",
  "is_detached_head": false,
  "status": "dirty",
  "staged_files": [],
  "unstaged_files": ["src/app.py"],
  "untracked_files": ["notes.txt"],
  "conflicted_files": [],
  "in_merge": false,
  "in_rebase": false,
  "remotes": ["origin"],
  "upstream": "origin/main",
  "ahead": 1,
  "behind": 0,
  "recent_commits": ["abc1234 fix typo"]
}
```

Output when blocked:

```json
{
  "ok": false,
  "error": "not a git repository"
}
```

Field meanings:

| Field | Meaning |
| --- | --- |
| `ok` | True when repository context was collected. |
| `error` | `null` on success, otherwise a short machine-readable blocker. |
| `repo_root` | Absolute repository root path. |
| `branch` | Current branch name, or `null` in detached HEAD. |
| `is_detached_head` | Whether HEAD is detached. |
| `status` | `clean` or `dirty`. |
| `staged_files` | Files staged for commit. |
| `unstaged_files` | Tracked files with unstaged changes. |
| `untracked_files` | Untracked files. |
| `conflicted_files` | Files with unresolved conflicts. |
| `in_merge` | Whether a merge is in progress. |
| `in_rebase` | Whether a rebase is in progress. |
| `remotes` | Configured remote names. |
| `upstream` | Upstream branch for the current branch, or `null`. |
| `ahead` | Commits local branch is ahead of upstream, or `null` if no upstream. |
| `behind` | Commits local branch is behind upstream, or `null` if no upstream. |
| `recent_commits` | Recent commits as `git log --oneline -n 5` strings. |

## LLM And Script Responsibilities

LLM must:

- Interpret the user's goal and repository context.
- Choose the Git/GH strategy and command sequence.
- Explain why each command is used, how flags work, what effects occur, and how to remember the command.
- Decide when trade-offs require user confirmation.
- Explain command failures and propose next steps.

Scripts must:

- Check whether required CLI tools exist.
- Collect deterministic Git repository state.
- Return stable JSON without Markdown fences or human commentary.

Never:

- Use scripts to decide user intent, choose a merge strategy, summarize PR content, or generate teaching text.
- Ignore a conflict, merge-in-progress, rebase-in-progress, detached HEAD, dirty working tree, or ahead/behind state when it affects the requested operation.
- Execute destructive or remote-state-changing commands without explicit user confirmation.

## Examples

### Happy Path

Input:

```text
帮我创建一个 feature-login 分支，推送到 origin
```

Expected behavior:

1. Run both scripts.
2. Explain `git switch -c feature-login` and `git push -u origin feature-login`.
3. Ask for approval.
4. Execute approved commands.
5. Review the completed workflow and memory tips.

### Near Misses

Input:

```text
帮我 force push 一下
```

Expected behavior: explain remote history rewriting, suggest `--force-with-lease`, and require explicit confirmation before any force push.

Input:

```text
review 一下这个 PR
```

Expected behavior: use this skill only if the user wants `gh pr view`, `gh pr checkout`, `gh pr diff`, or similar CLI operations. If they want code/content review, handle it as a code review task instead.

Input:

```text
帮我 rebase main
```

Expected behavior: inspect repository state first. If there are uncommitted changes, conflicts, or an existing rebase/merge in progress, explain the blocker before planning a new rebase.

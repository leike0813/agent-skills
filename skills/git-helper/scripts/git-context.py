"""Collect deterministic repository state snapshot.

Output: JSON to stdout. Never interprets state or suggests actions.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def emit(payload: dict) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False)
    print()


def git_path(path_name: str) -> Path | None:
    result = run(["git", "rev-parse", "--git-path", path_name])
    if result.returncode != 0:
        return None
    path = Path(result.stdout.strip())
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def git_path_exists(path_name: str) -> bool:
    path = git_path(path_name)
    return path.exists() if path is not None else False


def collect_status() -> tuple[list[str], list[str], list[str], list[str]]:
    staged_files: list[str] = []
    unstaged_files: list[str] = []
    untracked_files: list[str] = []
    conflicted_files: list[str] = []

    status_result = run(["git", "status", "--porcelain=v1"])
    if status_result.returncode != 0:
        return staged_files, unstaged_files, untracked_files, conflicted_files

    conflict_codes = {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}

    for line in status_result.stdout.splitlines():
        if not line:
            continue
        code = line[:2]
        filepath = line[3:]
        index_status = code[0]
        worktree_status = code[1]

        if code == "??":
            untracked_files.append(filepath)
            continue

        if code in conflict_codes:
            conflicted_files.append(filepath)
            continue

        if index_status != " ":
            staged_files.append(filepath)
        if worktree_status != " ":
            unstaged_files.append(filepath)

    return staged_files, unstaged_files, untracked_files, conflicted_files


def current_branch() -> tuple[str | None, bool]:
    result = run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"])
    if result.returncode == 0:
        return result.stdout.strip(), False
    return None, True


def upstream_status() -> tuple[str | None, int | None, int | None]:
    upstream_result = run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if upstream_result.returncode != 0:
        return None, None, None

    upstream = upstream_result.stdout.strip()
    count_result = run(["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"])
    if count_result.returncode != 0:
        return upstream, None, None

    parts = count_result.stdout.strip().split()
    if len(parts) != 2:
        return upstream, None, None

    return upstream, int(parts[0]), int(parts[1])


def main():
    if shutil.which("git") is None:
        emit({"ok": False, "error": "git unavailable"})
        return

    result = run(["git", "rev-parse", "--is-inside-work-tree"])
    if result.returncode != 0:
        emit({"ok": False, "error": "not a git repository"})
        return

    repo_root_result = run(["git", "rev-parse", "--show-toplevel"])
    repo_root = repo_root_result.stdout.strip() if repo_root_result.returncode == 0 else os.getcwd()

    branch, is_detached_head = current_branch()
    staged_files, unstaged_files, untracked_files, conflicted_files = collect_status()
    is_clean = not (staged_files or unstaged_files or untracked_files or conflicted_files)
    status = "clean" if is_clean else "dirty"

    remote_result = run(["git", "remote"])
    remotes = remote_result.stdout.strip().split("\n") if remote_result.returncode == 0 and remote_result.stdout.strip() else []

    upstream, ahead, behind = upstream_status()

    log_result = run(["git", "log", "--oneline", "-n", "5"])
    recent_commits = [line.strip() for line in log_result.stdout.strip().split("\n") if line.strip()] if log_result.returncode == 0 else []

    output = {
        "ok": True,
        "error": None,
        "repo_root": repo_root,
        "branch": branch,
        "is_detached_head": is_detached_head,
        "status": status,
        "staged_files": staged_files,
        "unstaged_files": unstaged_files,
        "untracked_files": untracked_files,
        "conflicted_files": conflicted_files,
        "in_merge": git_path_exists("MERGE_HEAD"),
        "in_rebase": git_path_exists("rebase-merge") or git_path_exists("rebase-apply"),
        "remotes": remotes,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "recent_commits": recent_commits,
    }

    emit(output)


if __name__ == "__main__":
    main()

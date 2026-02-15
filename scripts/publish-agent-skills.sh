#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# publish-agent-skills.sh
#
# Publish a local skill package directory (containing SKILL.md) into a local
# agent-skills aggregator repo (worktree), and push to remote such that local and
# remote are in sync after completion.
#
# Key behaviors:
# - Run from a skill dev repo worktree (current directory). Script can live elsewhere.
# - Operates on *local* aggregator worktree (default: script_dir/..).
# - Refuses to run if aggregator local/remote are not aligned (main & target skill branch).
# - Updates:
#   1) AGG_MAIN branch: skills/<skill>/  (vendored directory, not submodule)
#   2) SKILL_BRANCH (default: skill/<skill>): repo root becomes the skill package
#
# Requires: git, rsync, awk
# ==============================================================================

# -----------------------------
# helpers
# -----------------------------
die() {
  echo "ERROR: $*" >&2
  exit 1
}
log() { echo "==> $*" >&2; }

DRY_RUN="${DRY_RUN:-0}"
run() {
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "[dry-run] $*" >&2
  else
    eval "$@"
  fi
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

need_cmd git
need_cmd rsync
need_cmd awk

# -----------------------------
# config loading (KEY=VALUE only)
# -----------------------------
CFG_FILE=""
load_kv_config() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  log "Loading config: $f"
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    if [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
      export "$line"
    else
      die "Bad config line (expect KEY=VALUE): $line"
    fi
  done <"$f"
}

# -----------------------------
# defaults (can be overridden by env/config/cli)
# -----------------------------
DEV_ROOT=""
PKG_DIR=""
SKILL=""
EXCLUDES="${EXCLUDES:-}"
AGG_WT="${AGG_WT:-/home/joshua/Workspace/Code/Skill/agent-skills}"  # local aggregator worktree path
AGG_URL="${AGG_URL:-https://github.com/leike0813/agent-skills.git}" # aggregator remote origin URL (optional; will infer from AGG_WT/origin)
AGG_MAIN="${AGG_MAIN:-main}"
AGG_SKILLS_DIR="${AGG_SKILLS_DIR:-skills}"
SKILL_BRANCH_PREFIX="${SKILL_BRANCH_PREFIX:-skill/}"
ONLY_MAIN=0
ONLY_SKILL_BRANCH=0

usage() {
  cat <<'EOF'
Usage:
  publish-agent-skills.sh [options]

Run this script from within a skill dev repo (recommended). Script can be stored in agent-skills/scripts/.

Options:
  --dev-root <path>        Skill dev repo root. Default: git toplevel of current directory.
  --pkg-dir <dir>          Package directory under dev-root containing SKILL.md. Default: auto-detect.
  --skill <name>           Skill name. Default: parse from SKILL.md frontmatter name:, else pkg-dir basename.

  --agg-wt <path>          Local agent-skills worktree path. Default: script_dir/..
  --agg-url <url>          Expected origin URL for aggregator. Default: infer from agg-wt 'origin'.
  --agg-main <branch>      Aggregator main branch. Default: main
  --agg-skills-dir <dir>   Aggregator skills dir. Default: skills
  --skill-branch-prefix <p>Prefix for single-skill branch. Default: skill/

  --excludes <csv>         rsync excludes, comma-separated (e.g. node_modules,dist)
  --dry-run                Print commands without executing
  --only-main              Only update aggregator main skills/<skill>
  --only-skill-branch      Only update aggregator skill/<skill> branch (requires skills/<skill> exists on origin/<main>)
  --config <file>          Config file path. Default: <dev-root>/.agent-skills-publish.conf

Notes:
- This script refuses to run if the local aggregator repo differs from its remote for the branches it will touch.
- It operates directly on the *local* aggregator worktree and pushes changes, ensuring local == remote afterwards.
EOF
}

# -----------------------------
# parse args
# -----------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
  --dev-root)
    DEV_ROOT="${2:-}"
    shift 2
    ;;
  --pkg-dir)
    PKG_DIR="${2:-}"
    shift 2
    ;;
  --skill)
    SKILL="${2:-}"
    shift 2
    ;;
  --agg-wt)
    AGG_WT="${2:-}"
    shift 2
    ;;
  --agg-url)
    AGG_URL="${2:-}"
    shift 2
    ;;
  --agg-main)
    AGG_MAIN="${2:-}"
    shift 2
    ;;
  --agg-skills-dir)
    AGG_SKILLS_DIR="${2:-}"
    shift 2
    ;;
  --skill-branch-prefix)
    SKILL_BRANCH_PREFIX="${2:-}"
    shift 2
    ;;
  --excludes)
    EXCLUDES="${2:-}"
    shift 2
    ;;
  --dry-run)
    DRY_RUN=1
    shift
    ;;
  --only-main)
    ONLY_MAIN=1
    shift
    ;;
  --only-skill-branch)
    ONLY_SKILL_BRANCH=1
    shift
    ;;
  --config)
    CFG_FILE="${2:-}"
    shift 2
    ;;
  -h | --help)
    usage
    exit 0
    ;;
  *) die "Unknown arg: $1" ;;
  esac
done

# -----------------------------
# infer DEV_ROOT from current working directory (important!)
# -----------------------------
if [[ -z "${DEV_ROOT}" ]]; then
  if git rev-parse --show-toplevel >/dev/null 2>&1; then
    DEV_ROOT="$(git rev-parse --show-toplevel)"
  else
    die "Not inside a git repo. Run from your skill dev repo root, or pass --dev-root."
  fi
fi

# config file default & load
if [[ -z "${CFG_FILE}" ]]; then
  CFG_FILE="${DEV_ROOT}/.agent-skills-publish.conf"
fi
load_kv_config "${CFG_FILE}"

# re-apply env/config defaults if provided there
EXCLUDES="${EXCLUDES:-}"
AGG_MAIN="${AGG_MAIN:-main}"
AGG_SKILLS_DIR="${AGG_SKILLS_DIR:-skills}"
SKILL_BRANCH_PREFIX="${SKILL_BRANCH_PREFIX:-skill/}"
AGG_WT="${AGG_WT:-}"
AGG_URL="${AGG_URL:-}"

# -----------------------------
# infer AGG_WT from script location if not provided
# -----------------------------
if [[ -z "${AGG_WT}" ]]; then
  # script is expected in <agent-skills>/scripts/, so parent dir is aggregator worktree
  AGG_WT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

# validate aggregator worktree is git repo
git -C "${AGG_WT}" rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "AGG_WT is not a git worktree: ${AGG_WT}"

# infer AGG_URL from local agg repo origin if not provided
AGG_ORIGIN_URL="$(git -C "${AGG_WT}" remote get-url origin 2>/dev/null || true)"
if [[ -z "${AGG_URL}" ]]; then
  [[ -n "${AGG_ORIGIN_URL}" ]] || die "Cannot infer AGG_URL: aggregator has no 'origin' remote. Set AGG_URL in config or pass --agg-url."
  AGG_URL="${AGG_ORIGIN_URL}"
else
  # if user specified AGG_URL, ensure it matches local aggregator origin to prevent accidental publishing to wrong remote
  [[ -n "${AGG_ORIGIN_URL}" ]] || die "Aggregator has no 'origin' remote; cannot validate --agg-url."
  if [[ "${AGG_URL}" != "${AGG_ORIGIN_URL}" ]]; then
    die "AGG_URL (${AGG_URL}) does not match local aggregator origin (${AGG_ORIGIN_URL}). Refusing to proceed."
  fi
fi

# -----------------------------
# auto-detect PKG_DIR (dir containing SKILL.md) if not provided
# -----------------------------
if [[ -z "${PKG_DIR}" ]]; then
  mapfile -t candidates < <(find "${DEV_ROOT}" -mindepth 1 -maxdepth 2 -type f -name "SKILL.md" -printf '%h\n' | sort -u)
  if [[ "${#candidates[@]}" -eq 0 ]]; then
    die "Cannot auto-detect PKG_DIR: no SKILL.md found under ${DEV_ROOT} (depth<=2). Use --pkg-dir."
  elif [[ "${#candidates[@]}" -gt 1 ]]; then
    echo "Multiple SKILL.md found under ${DEV_ROOT} (depth<=2):" >&2
    printf '  - %s\n' "${candidates[@]}" >&2
    die "Ambiguous PKG_DIR. Use --pkg-dir."
  else
    PKG_DIR="$(basename "${candidates[0]}")"
  fi
fi

PKG_PATH="${DEV_ROOT}/${PKG_DIR}"
[[ -d "${PKG_PATH}" ]] || die "PKG_DIR not found: ${PKG_PATH}"
[[ -f "${PKG_PATH}/SKILL.md" ]] || die "SKILL.md not found in package dir: ${PKG_PATH}"

# -----------------------------
# infer SKILL from SKILL.md frontmatter (supports quotes) if not provided
# -----------------------------
if [[ -z "${SKILL}" ]]; then
  SKILL="$(awk '
    BEGIN{in_fm=0}
    /^---[[:space:]]*$/ {in_fm = 1 - in_fm; next}
    in_fm==1 && $0 ~ /^[[:space:]]*name:[[:space:]]*/ {
      sub(/^[[:space:]]*name:[[:space:]]*/, "", $0);
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0);
      gsub(/^["'\''"]|["'\''"]$/, "", $0);
      print $0; exit
    }
  ' "${PKG_PATH}/SKILL.md")"
  [[ -n "${SKILL}" ]] || SKILL="$(basename "${PKG_PATH}")"
fi

SKILL_BRANCH="${SKILL_BRANCH_PREFIX}${SKILL}"
AGG_SKILL_PATH="${AGG_SKILLS_DIR}/${SKILL}"

# -----------------------------
# rsync excludes
# -----------------------------
RSYNC_EX=(--exclude ".git")
if [[ -n "${EXCLUDES}" ]]; then
  IFS=',' read -r -a exarr <<<"${EXCLUDES}"
  for e in "${exarr[@]}"; do
    e="${e## }"
    e="${e%% }"
    [[ -n "$e" ]] && RSYNC_EX+=(--exclude "$e")
  done
fi

# -----------------------------
# print summary
# -----------------------------
log "DEV_ROOT        = ${DEV_ROOT}"
log "PKG_DIR         = ${PKG_DIR}"
log "PKG_PATH        = ${PKG_PATH}"
log "SKILL           = ${SKILL}"
log "AGG_WT          = ${AGG_WT}"
log "AGG_URL(origin) = ${AGG_URL}"
log "AGG_MAIN        = ${AGG_MAIN}"
log "AGG_SKILLS_DIR  = ${AGG_SKILLS_DIR}"
log "AGG_SKILL_PATH  = ${AGG_SKILL_PATH}"
log "SKILL_BRANCH    = ${SKILL_BRANCH}"
log "DRY_RUN         = ${DRY_RUN}"
log "EXCLUDES        = ${EXCLUDES}"

# ==============================================================================
# (4) Preflight check: aggregator clean and aligned with remote
# ==============================================================================

# Ensure aggregator worktree is clean
AGG_PORCELAIN="$(git -C "${AGG_WT}" status --porcelain)"
[[ -z "${AGG_PORCELAIN}" ]] || die "Aggregator repo has local changes. Please commit/stash in ${AGG_WT} and retry."

# Fetch remote
run "git -C \"${AGG_WT}\" fetch origin --prune"

# helper to compare local vs remote branch if local exists
check_branch_aligned() {
  local branch="$1"
  local remote_ref="refs/remotes/origin/${branch}"
  local local_ref="refs/heads/${branch}"

  # If remote branch doesn't exist, nothing to align (we may create it later)
  if ! git -C "${AGG_WT}" show-ref --verify --quiet "${remote_ref}"; then
    log "Remote branch origin/${branch} does not exist (will be created if needed)."
    return 0
  fi

  # If local branch doesn't exist, OK (we will checkout from origin when needed)
  if ! git -C "${AGG_WT}" show-ref --verify --quiet "${local_ref}"; then
    log "Local branch ${branch} does not exist (will be created from origin/${branch})."
    return 0
  fi

  local l r
  l="$(git -C "${AGG_WT}" rev-parse "${branch}")"
  r="$(git -C "${AGG_WT}" rev-parse "origin/${branch}")"

  if [[ "${l}" != "${r}" ]]; then
    die "Aggregator local branch '${branch}' differs from origin/${branch}.
Please align first in ${AGG_WT}, e.g.:
  git -C \"${AGG_WT}\" checkout ${branch}
  git -C \"${AGG_WT}\" pull --ff-only
Then retry."
  fi
}

# Must align main
check_branch_aligned "${AGG_MAIN}"

# Also align skill branch if it exists on remote (or local)
# - If remote exists and local differs -> refuse
# - If remote exists but local missing -> OK (we'll create local from origin)
# - If remote missing -> OK (we'll create remote)
check_branch_aligned "${SKILL_BRANCH}"

# ==============================================================================
# (3) Publish into local aggregator repo and push so local == remote
# ==============================================================================

# Remember current branch in aggregator to restore later
AGG_ORIG_REF="$(git -C "${AGG_WT}" rev-parse --abbrev-ref HEAD || echo HEAD)"
restore_agg_branch() {
  # restore only if repo clean (it should be)
  if [[ -z "$(git -C "${AGG_WT}" status --porcelain)" ]]; then
    run "git -C \"${AGG_WT}\" checkout \"${AGG_ORIG_REF}\" >/dev/null 2>&1 || true"
  fi
}
trap restore_agg_branch EXIT

commit_if_needed_in_agg() {
  local msg="$1"
  if git -C "${AGG_WT}" diff --cached --quiet; then
    log "No staged changes: ${msg}"
    return 1
  fi
  run "git -C \"${AGG_WT}\" commit -m \"${msg}\""
  return 0
}

# -----------------------------
# Step 1: Update main branch skills/<skill>
# -----------------------------
if [[ "${ONLY_SKILL_BRANCH}" != "1" ]]; then
  run "git -C \"${AGG_WT}\" checkout \"${AGG_MAIN}\""

  # Ensure main exists locally if remote exists but local doesn't
  if ! git -C "${AGG_WT}" show-ref --verify --quiet "refs/heads/${AGG_MAIN}"; then
    if git -C "${AGG_WT}" show-ref --verify --quiet "refs/remotes/origin/${AGG_MAIN}"; then
      run "git -C \"${AGG_WT}\" checkout -B \"${AGG_MAIN}\" \"origin/${AGG_MAIN}\""
    fi
  fi

  run "mkdir -p \"${AGG_WT}/${AGG_SKILL_PATH}\""
  # rsync package -> aggregator skills/<skill>
  # Note: source ends with / to copy contents
  run "rsync -a --delete ${RSYNC_EX[*]} \"${PKG_PATH}/\" \"${AGG_WT}/${AGG_SKILL_PATH}/\""

  run "git -C \"${AGG_WT}\" add \"${AGG_SKILL_PATH}\""
  commit_if_needed_in_agg "publish(${SKILL}): update ${AGG_SKILL_PATH}" || true

  # push main
  run "git -C \"${AGG_WT}\" push origin \"${AGG_MAIN}\""
fi

# -----------------------------
# Step 2: Sync (and create if missing) skill branch so repo root == package
# -----------------------------
if [[ "${ONLY_MAIN}" != "1" ]]; then
  # We need skills/<skill> to exist on origin/<main> for --only-skill-branch mode,
  # or at least in local main after Step 1.
  run "git -C \"${AGG_WT}\" fetch origin --prune"

  # (2) Ensure the skill branch exists locally (and create orphan if remote missing)
  if git -C "${AGG_WT}" show-ref --verify --quiet "refs/remotes/origin/${SKILL_BRANCH}"; then
    run "git -C \"${AGG_WT}\" checkout -B \"${SKILL_BRANCH}\" \"origin/${SKILL_BRANCH}\""
  else
    # Create a brand new orphan branch (no history) for first publish
    run "git -C \"${AGG_WT}\" checkout --orphan \"${SKILL_BRANCH}\""
    # Clean everything in worktree (safe because we required clean state)
    run "git -C \"${AGG_WT}\" rm -rf . >/dev/null 2>&1 || true"
    run "git -C \"${AGG_WT}\" clean -fdx"
  fi

  # Clear current branch content (tracked + untracked)
  run "git -C \"${AGG_WT}\" rm -rf . >/dev/null 2>&1 || true"
  run "git -C \"${AGG_WT}\" clean -fdx"

  # Copy package content from aggregator main's skills/<skill> directory to repo root.
  # Prefer local main's directory if present; otherwise fallback to origin/<main>.
  if [[ -d "${AGG_WT}/${AGG_SKILL_PATH}" ]]; then
    run "rsync -a --delete --exclude \".git\" \"${AGG_WT}/${AGG_SKILL_PATH}/\" \"${AGG_WT}/\""
  else
    # materialize from origin/main into a temp path inside worktree, then rsync
    # Use git checkout to bring skills/<skill> into this branch's worktree
    run "git -C \"${AGG_WT}\" checkout \"origin/${AGG_MAIN}\" -- \"${AGG_SKILL_PATH}\""
    run "rsync -a --delete --exclude \".git\" \"${AGG_WT}/${AGG_SKILL_PATH}/\" \"${AGG_WT}/\""
    run "git -C \"${AGG_WT}\" rm -rf \"${AGG_SKILLS_DIR}\" >/dev/null 2>&1 || true"
    run "git -C \"${AGG_WT}\" clean -fdx"
  fi

  run "git -C \"${AGG_WT}\" add -A"

  # Commit (ensure branch can be pushed even if no diff)
  if git -C "${AGG_WT}" diff --cached --quiet; then
    run "git -C \"${AGG_WT}\" commit --allow-empty -m \"init(${SKILL}): create ${SKILL_BRANCH}\""
  else
    run "git -C \"${AGG_WT}\" commit -m \"sync(${SKILL}): from ${AGG_MAIN}:${AGG_SKILL_PATH}\""
  fi

  # Push branch (creates remote branch if missing)
  run "git -C \"${AGG_WT}\" push -u origin \"${SKILL_BRANCH}\""
fi

# ==============================================================================
# (3) Post-check: ensure local == remote after push (main + skill branch)
# ==============================================================================
run "git -C \"${AGG_WT}\" fetch origin --prune"

verify_equal() {
  local branch="$1"
  local remote="origin/${branch}"
  if ! git -C "${AGG_WT}" show-ref --verify --quiet "refs/remotes/${remote}"; then
    die "Post-check failed: remote ${remote} not found after push."
  fi
  # local may not exist if ONLY_MAIN and not checked out? ensure local branch exists for compare
  if ! git -C "${AGG_WT}" show-ref --verify --quiet "refs/heads/${branch}"; then
    # create local tracking branch without touching worktree state too much
    run "git -C \"${AGG_WT}\" branch -f \"${branch}\" \"${remote}\""
  fi

  local l r
  l="$(git -C "${AGG_WT}" rev-parse "${branch}")"
  r="$(git -C "${AGG_WT}" rev-parse "${remote}")"
  [[ "${l}" == "${r}" ]] || die "Post-check failed: ${branch} (${l}) != ${remote} (${r})."
}

if [[ "${ONLY_SKILL_BRANCH}" != "1" ]]; then
  verify_equal "${AGG_MAIN}"
fi
if [[ "${ONLY_MAIN}" != "1" ]]; then
  verify_equal "${SKILL_BRANCH}"
fi

log "Done. Local aggregator (${AGG_WT}) and remote are aligned."

#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# publish-agent-skills.sh (v2)
#
# - Run from a SKILL dev repo worktree (current directory).
# - Script can live inside local agent-skills repo (e.g. agent-skills/scripts/).
# - Publishes the package dir (containing SKILL.md) into local agent-skills worktree:
#     1) <AGG_MAIN>: skills/<skill>/
#     2) <SKILL_BRANCH>: repo root == package
# - Refuses to run if local agent-skills repo is not aligned with remote (for touched branches).
# - Honors .gitignore by using: git ls-files -c -o --exclude-standard
#   (tracked + untracked-not-ignored from dev repo worktree)
#
# Dependencies: git, awk, tar
# ==============================================================================

die() {
  echo "ERROR: $*" >&2
  exit 1
}
log() { echo "==> $*" >&2; }

need_cmd() { command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"; }
need_cmd git
need_cmd awk
need_cmd tar

DRY_RUN="${DRY_RUN:-0}"
run() {
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "[dry-run] $*" >&2
  else
    eval "$@"
  fi
}

# -----------------------------
# config loading: KEY=VALUE only
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
# defaults (env/config/cli can override)
# -----------------------------
DEV_ROOT=""
PKG_DIR=""
SKILL=""
EXCLUDES="${EXCLUDES:-}" # comma-separated prefix excludes relative to package root (optional)

AGG_WT="${AGG_WT:-/home/joshua/Workspace/Code/Skill/agent-skills/}" # local agent-skills worktree path
AGG_URL="${AGG_URL:-https://github.com/leike0813/agent-skills.git}" # default allowed; will validate vs local origin

AGG_MAIN="${AGG_MAIN:-main}"
AGG_SKILLS_DIR="${AGG_SKILLS_DIR:-skills}"
SKILL_BRANCH_PREFIX="${SKILL_BRANCH_PREFIX:-skill/}"
ONLY_MAIN=0
ONLY_SKILL_BRANCH=0

usage() {
  cat <<'EOF'
Usage:
  publish-agent-skills.sh [options]

Options:
  --pkg-dir <dir>          Package dir under dev root containing SKILL.md (default: auto-detect)
  --skill <name>           Skill name override (default: parse SKILL.md frontmatter name:)
  --agg-wt <path>          Local agent-skills worktree (default: script_dir/..)
  --agg-url <url>          Expected agent-skills origin URL (default: built-in / env / config)
  --agg-main <branch>      Aggregator main branch (default: main)
  --agg-skills-dir <dir>   Aggregator skills directory (default: skills)
  --skill-branch-prefix <p>Prefix for single-skill branch (default: skill/)
  --excludes <csv>         Extra excludes by path prefix (e.g. ".DS_Store,node_modules,dist")
  --only-main              Only update <AGG_MAIN>:skills/<skill>
  --only-skill-branch      Only update <skill/<skill>> branch
  --dry-run                Print commands without executing
  --config <file>          Config file path (default: <dev-root>/.agent-skills-publish.conf)
EOF
}

# -----------------------------
# args
# -----------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
  --dev-root)
    DEV_ROOT="${2:-}"
    shift 2
    ;; # optional, mostly unused (auto from git)
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
  --only-main)
    ONLY_MAIN=1
    shift
    ;;
  --only-skill-branch)
    ONLY_SKILL_BRANCH=1
    shift
    ;;
  --dry-run)
    DRY_RUN=1
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
# infer DEV_ROOT: MUST be the skill dev repo you're currently in
# -----------------------------
if [[ -z "${DEV_ROOT}" ]]; then
  git rev-parse --show-toplevel >/dev/null 2>&1 || die "Run this from inside a skill dev git repo worktree."
  DEV_ROOT="$(git rev-parse --show-toplevel)"
fi

# config file load
if [[ -z "${CFG_FILE}" ]]; then
  CFG_FILE="${DEV_ROOT}/.agent-skills-publish.conf"
fi
load_kv_config "${CFG_FILE}"

# re-apply env/config defaults if present
EXCLUDES="${EXCLUDES:-}"
AGG_MAIN="${AGG_MAIN:-main}"
AGG_SKILLS_DIR="${AGG_SKILLS_DIR:-skills}"
SKILL_BRANCH_PREFIX="${SKILL_BRANCH_PREFIX:-skill/}"
AGG_WT="${AGG_WT:-}"
AGG_URL="${AGG_URL:-https://github.com/leike0813/agent-skills.git}"

# -----------------------------
# infer AGG_WT from script location if not provided
# -----------------------------
if [[ -z "${AGG_WT}" ]]; then
  AGG_WT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
git -C "${AGG_WT}" rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "AGG_WT is not a git worktree: ${AGG_WT}"

# validate AGG_URL matches local origin (safety)
LOCAL_AGG_ORIGIN="$(git -C "${AGG_WT}" remote get-url origin 2>/dev/null || true)"
[[ -n "${LOCAL_AGG_ORIGIN}" ]] || die "Local aggregator has no 'origin' remote: ${AGG_WT}"
if [[ "${AGG_URL}" != "${LOCAL_AGG_ORIGIN}" ]]; then
  die "AGG_URL (${AGG_URL}) != local aggregator origin (${LOCAL_AGG_ORIGIN}). Refusing."
fi

# -----------------------------
# auto-detect PKG_DIR (dir containing SKILL.md) if not provided
# -----------------------------
if [[ -z "${PKG_DIR}" ]]; then
  mapfile -t candidates < <(find "${DEV_ROOT}" -mindepth 1 -maxdepth 2 -type f -name "SKILL.md" -printf '%h\n' | sort -u)
  if [[ "${#candidates[@]}" -eq 0 ]]; then
    die "Cannot auto-detect PKG_DIR: no SKILL.md found under ${DEV_ROOT} (depth<=2). Use --pkg-dir."
  elif [[ "${#candidates[@]}" -gt 1 ]]; then
    echo "Multiple SKILL.md found:" >&2
    printf '  - %s\n' "${candidates[@]}" >&2
    die "Ambiguous PKG_DIR. Use --pkg-dir."
  else
    PKG_DIR="$(basename "${candidates[0]}")"
  fi
fi

PKG_PATH="${DEV_ROOT}/${PKG_DIR}"
[[ -d "${PKG_PATH}" ]] || die "PKG_DIR not found: ${PKG_PATH}"
[[ -f "${PKG_PATH}/SKILL.md" ]] || die "SKILL.md not found in: ${PKG_PATH}"

# -----------------------------
# infer SKILL from SKILL.md frontmatter name: (supports quotes)
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
AGG_SKILL_PATH="${AGG_WT}/${AGG_SKILLS_DIR}/${SKILL}"

log "DEV_ROOT       = ${DEV_ROOT}"
log "PKG_DIR        = ${PKG_DIR}"
log "PKG_PATH       = ${PKG_PATH}"
log "SKILL          = ${SKILL}"
log "AGG_WT         = ${AGG_WT}"
log "AGG_MAIN       = ${AGG_MAIN}"
log "AGG_SKILLS_DIR = ${AGG_SKILLS_DIR}"
log "AGG_SKILL_PATH = ${AGG_SKILL_PATH}"
log "SKILL_BRANCH   = ${SKILL_BRANCH}"
log "EXCLUDES       = ${EXCLUDES}"
log "DRY_RUN        = ${DRY_RUN}"

# ==============================================================================
# (4) Preflight: local aggregator clean & aligned with remote for touched branches
# ==============================================================================

# user identity check (prevents orphan branch left w/o commit)
AGG_EMAIL="$(git -C "${AGG_WT}" config --get user.email || true)"
AGG_NAME="$(git -C "${AGG_WT}" config --get user.name || true)"
if [[ -z "${AGG_EMAIL}" || -z "${AGG_NAME}" ]]; then
  # global fallback
  AGG_EMAIL_G="$(git config --global --get user.email || true)"
  AGG_NAME_G="$(git config --global --get user.name || true)"
  [[ -n "${AGG_EMAIL_G}" && -n "${AGG_NAME_G}" ]] || die "Git user.name/email not set (local or global). Set them before publishing."
fi

# aggregator worktree must be clean (including untracked)
[[ -z "$(git -C "${AGG_WT}" status --porcelain)" ]] || die "Aggregator worktree has local changes. Please commit/stash and retry: ${AGG_WT}"

run "git -C \"${AGG_WT}\" fetch origin --prune"

# helper: require local branch equals origin branch if both exist.
# If local missing, that's OK; we'll create it from origin when needed.
require_aligned_if_exists() {
  local branch="$1"
  local remote_ref="refs/remotes/origin/${branch}"
  local local_ref="refs/heads/${branch}"

  if ! git -C "${AGG_WT}" show-ref --verify --quiet "${remote_ref}"; then
    # remote branch missing is OK for SKILL_BRANCH (we may create), but not for main
    return 1
  fi

  if git -C "${AGG_WT}" show-ref --verify --quiet "${local_ref}"; then
    local l r
    l="$(git -C "${AGG_WT}" rev-parse "${branch}")"
    r="$(git -C "${AGG_WT}" rev-parse "origin/${branch}")"
    [[ "${l}" == "${r}" ]] || die "Aggregator local '${branch}' != origin/${branch}. Align first (pull --ff-only) then retry."
  fi
  return 0
}

# main must exist on origin and be aligned if local exists
if ! require_aligned_if_exists "${AGG_MAIN}"; then
  die "origin/${AGG_MAIN} does not exist in aggregator remote."
fi

# skill branch: if exists on origin and local exists, must be aligned
require_aligned_if_exists "${SKILL_BRANCH}" || true

# remember original branch to restore
AGG_ORIG_BRANCH="$(git -C "${AGG_WT}" rev-parse --abbrev-ref HEAD || echo HEAD)"
restore_branch() {
  # only restore if clean
  if [[ -z "$(git -C "${AGG_WT}" status --porcelain)" ]]; then
    run "git -C \"${AGG_WT}\" checkout \"${AGG_ORIG_BRANCH}\" >/dev/null 2>&1 || true"
  fi
}
trap restore_branch EXIT

# ==============================================================================
# helper: build publish file list (tracked + untracked-not-ignored) under PKG_DIR,
# and extract into destination directory (clearing destination first).
# ==============================================================================
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

LIST_RAW="${TMPDIR}/files_raw.txt"
LIST_REL="${TMPDIR}/files_rel.txt"
LIST_FINAL="${TMPDIR}/files_final.txt"

build_file_list() {
  # tracked + untracked but not ignored (respects .gitignore, .git/info/exclude, global excludes)
  git -C "${DEV_ROOT}" ls-files -c -o --exclude-standard -- "${PKG_DIR}" >"${LIST_RAW}"

  [[ -s "${LIST_RAW}" ]] || die "No publishable files found under ${PKG_DIR} (all ignored or missing)."

  # strip "<PKG_DIR>/" prefix -> paths relative to PKG_PATH
  sed "s#^${PKG_DIR}/##" "${LIST_RAW}" >"${LIST_REL}"

  # apply optional prefix excludes
  if [[ -n "${EXCLUDES}" ]]; then
    awk -v ex="${EXCLUDES}" '
      BEGIN{
        n=split(ex,a,",");
        for(i=1;i<=n;i++){
          gsub(/^[[:space:]]+|[[:space:]]+$/, "", a[i]);
          if(a[i]!="") exa[a[i]]=1;
        }
      }
      {
        for (p in exa) {
          if ($0==p) next;
          if (index($0, p"/")==1) next;
        }
        print
      }
    ' "${LIST_REL}" >"${LIST_FINAL}"
  else
    cp "${LIST_REL}" "${LIST_FINAL}"
  fi

  [[ -s "${LIST_FINAL}" ]] || die "After EXCLUDES filtering, nothing left to publish."
}

empty_dir() {
  local d="$1"
  [[ -d "$d" ]] || mkdir -p "$d"
  # Remove all contents (including dotfiles) inside d
  # shellcheck disable=SC2115
  rm -rf "${d:?}/"* "${d:?}/".* 2>/dev/null || true
  # Above may try to remove ..; safe due to rm -rf patterns, but errors ignored.
}

extract_to_dir() {
  local dest="$1"
  [[ -d "$dest" ]] || mkdir -p "$dest"
  empty_dir "$dest"

  # Create tar from PKG_PATH with LIST_FINAL and extract to dest.
  # This honors .gitignore because LIST_FINAL was built from git ls-files --exclude-standard.
  (cd "${PKG_PATH}" && tar -cf - -T "${LIST_FINAL}") | (cd "${dest}" && tar -xf -)
}

# ==============================================================================
# Publish step 1: update AGG_MAIN skills/<skill> (unless only-skill-branch)
# ==============================================================================
build_file_list

if [[ "${ONLY_SKILL_BRANCH}" != "1" ]]; then
  # checkout main (create local tracking if needed)
  if git -C "${AGG_WT}" show-ref --verify --quiet "refs/remotes/origin/${AGG_MAIN}"; then
    run "git -C \"${AGG_WT}\" checkout -B \"${AGG_MAIN}\" \"origin/${AGG_MAIN}\""
  else
    die "origin/${AGG_MAIN} missing."
  fi

  # ensure skills dir exists
  run "mkdir -p \"${AGG_WT}/${AGG_SKILLS_DIR}\""
  run "mkdir -p \"${AGG_SKILL_PATH}\""

  # extract package into aggregator skills/<skill>
  extract_to_dir "${AGG_SKILL_PATH}"

  run "git -C \"${AGG_WT}\" add \"${AGG_SKILLS_DIR}/${SKILL}\""
  if ! git -C "${AGG_WT}" diff --cached --quiet; then
    run "git -C \"${AGG_WT}\" commit -m \"publish(${SKILL}): update ${AGG_SKILLS_DIR}/${SKILL}\""
  else
    log "No changes on ${AGG_MAIN}:${AGG_SKILLS_DIR}/${SKILL}"
  fi

  run "git -C \"${AGG_WT}\" push origin \"${AGG_MAIN}\""
fi

# ==============================================================================
# Publish step 2: update/create SKILL_BRANCH where repo root == package (unless only-main)
# ==============================================================================
if [[ "${ONLY_MAIN}" != "1" ]]; then
  run "git -C \"${AGG_WT}\" fetch origin --prune"

  if git -C "${AGG_WT}" show-ref --verify --quiet "refs/remotes/origin/${SKILL_BRANCH}"; then
    run "git -C \"${AGG_WT}\" checkout -B \"${SKILL_BRANCH}\" \"origin/${SKILL_BRANCH}\""
  else
    # create orphan branch, so first publish is clean and always pushable
    run "git -C \"${AGG_WT}\" checkout --orphan \"${SKILL_BRANCH}\""
    # clear index and working tree (keep .git)
    run "git -C \"${AGG_WT}\" rm -rf . >/dev/null 2>&1 || true"
    # remove any remaining files except .git
    run "find \"${AGG_WT}\" -mindepth 1 -maxdepth 1 ! -name \".git\" -exec rm -rf {} +"
  fi

  # ensure worktree is empty (except .git), then extract package to repo root
  run "find \"${AGG_WT}\" -mindepth 1 -maxdepth 1 ! -name \".git\" -exec rm -rf {} +"
  extract_to_dir "${AGG_WT}"

  run "git -C \"${AGG_WT}\" add -A"
  if git -C "${AGG_WT}" diff --cached --quiet; then
    # still create branch on remote even if nothing staged (shouldn't happen, but safe)
    run "git -C \"${AGG_WT}\" commit --allow-empty -m \"init(${SKILL}): create ${SKILL_BRANCH}\""
  else
    run "git -C \"${AGG_WT}\" commit -m \"sync(${SKILL}): publish package root\""
  fi

  run "git -C \"${AGG_WT}\" push -u origin \"${SKILL_BRANCH}\""
fi

# ==============================================================================
# Post-check: ensure local == origin for touched branches
# ==============================================================================
run "git -C \"${AGG_WT}\" fetch origin --prune"

verify_equal() {
  local b="$1"
  local lref="refs/heads/${b}"
  local rref="refs/remotes/origin/${b}"
  git -C "${AGG_WT}" show-ref --verify --quiet "${rref}" || die "Remote branch origin/${b} missing after push."
  git -C "${AGG_WT}" show-ref --verify --quiet "${lref}" || run "git -C \"${AGG_WT}\" branch -f \"${b}\" \"origin/${b}\""
  local l r
  l="$(git -C "${AGG_WT}" rev-parse "${b}")"
  r="$(git -C "${AGG_WT}" rev-parse "origin/${b}")"
  [[ "${l}" == "${r}" ]] || die "Post-check failed: ${b} (${l}) != origin/${b} (${r})"
}

if [[ "${ONLY_SKILL_BRANCH}" != "1" ]]; then verify_equal "${AGG_MAIN}"; fi
if [[ "${ONLY_MAIN}" != "1" ]]; then verify_equal "${SKILL_BRANCH}"; fi

log "Done. Local and remote aggregator are aligned for touched branches."

#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# publish.sh (SAFE)
#
# Store this script in local aggregator repo: ~/Workspace/Code/Skill/agent-skills/scripts/
# Run it from a skill dev repo root (anywhere inside that repo is OK).
#
# Features:
# - True dry-run: no filesystem modifications, no worktree changes, no commits, no pushes
# - Publishes using file list derived from git (honors .gitignore via --exclude-standard)
# - Updates aggregator main only in skills/<skill> directory
# - Updates/creates skill/<skill> branch via TEMP worktree (never overwrites aggregator worktree)
# - Refuses to run if aggregator local branches are not aligned with origin (for touched branches)
#
# Dependencies: git, awk, tar, sed, find, mktemp
# ==============================================================================

die() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "==> $*" >&2; }

need_cmd() { command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"; }
need_cmd git
need_cmd awk
need_cmd tar
need_cmd sed
need_cmd find
need_cmd mktemp

DRY_RUN=0

# -----------------------------
# defaults (override via env / config / cli)
# -----------------------------
AGG_WT_DEFAULT=/home/joshua/Workspace/Code/Skill/agent-skills/
AGG_URL_DEFAULT="https://github.com/leike0813/agent-skills"

DEV_ROOT=""
PKG_DIR=""
SKILL=""
EXCLUDES="${EXCLUDES:-}"                 # comma-separated prefix excludes relative to package root (optional)

AGG_WT="${AGG_WT:-${AGG_WT_DEFAULT}}"                     # local aggregator worktree path (default: script_dir/..)
AGG_URL="${AGG_URL:-${AGG_URL_DEFAULT}}"
AGG_MAIN="${AGG_MAIN:-main}"
AGG_SKILLS_DIR="${AGG_SKILLS_DIR:-skills}"
SKILL_BRANCH_PREFIX="${SKILL_BRANCH_PREFIX:-skill/}"

ONLY_MAIN=0
ONLY_SKILL_BRANCH=0
CFG_FILE=""

usage() {
  cat <<'EOF'
Usage:
  publish.sh [options]

Options:
  --pkg-dir <dir>           Package dir under dev repo containing SKILL.md (default: auto-detect)
  --skill <name>            Skill name override (default: parse from SKILL.md frontmatter name:)
  --excludes <csv>          Extra excludes (prefix match, relative to package root), e.g. "node_modules,dist"
  --agg-wt <path>           Local agent-skills worktree (default: script_dir/..)
  --agg-url <url>           Expected origin URL for agent-skills (default: built-in)
  --agg-main <branch>       Aggregator main branch (default: main)
  --agg-skills-dir <dir>    Aggregator skills dir (default: skills)
  --skill-branch-prefix <p> Prefix for single-skill branch (default: skill/)
  --only-main               Only update <AGG_MAIN>:skills/<skill>
  --only-skill-branch       Only update skill/<skill> branch
  --config <file>           Config file (default: <dev-root>/.agent-skills-publish.conf)
  --dry-run                 Print what would happen; no changes.

Config file format (KEY=VALUE):
  AGG_URL=...
  AGG_MAIN=main
  EXCLUDES=node_modules,dist
EOF
}

# -----------------------------
# config loader (KEY=VALUE only)
# -----------------------------
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
  done < "$f"
}

# -----------------------------
# args
# -----------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dev-root) DEV_ROOT="${2:-}"; shift 2;;
    --pkg-dir) PKG_DIR="${2:-}"; shift 2;;
    --skill) SKILL="${2:-}"; shift 2;;
    --excludes) EXCLUDES="${2:-}"; shift 2;;
    --agg-wt) AGG_WT="${2:-}"; shift 2;;
    --agg-url) AGG_URL="${2:-}"; shift 2;;
    --agg-main) AGG_MAIN="${2:-}"; shift 2;;
    --agg-skills-dir) AGG_SKILLS_DIR="${2:-}"; shift 2;;
    --skill-branch-prefix) SKILL_BRANCH_PREFIX="${2:-}"; shift 2;;
    --only-main) ONLY_MAIN=1; shift;;
    --only-skill-branch) ONLY_SKILL_BRANCH=1; shift;;
    --config) CFG_FILE="${2:-}"; shift 2;;
    --dry-run) DRY_RUN=1; shift;;
    -h|--help) usage; exit 0;;
    *) die "Unknown arg: $1";;
  esac
done

# -----------------------------
# infer DEV_ROOT from current directory (must be skill dev repo)
# -----------------------------
if [[ -z "${DEV_ROOT}" ]]; then
  git rev-parse --show-toplevel >/dev/null 2>&1 || die "Run this from inside a skill dev git repo."
  DEV_ROOT="$(git rev-parse --show-toplevel)"
fi

# load config from dev repo root by default
if [[ -z "${CFG_FILE}" ]]; then
  CFG_FILE="${DEV_ROOT}/.agent-skills-publish.conf"
fi
load_kv_config "${CFG_FILE}"

# re-apply possibly updated env from config
EXCLUDES="${EXCLUDES:-}"
AGG_MAIN="${AGG_MAIN:-main}"
AGG_SKILLS_DIR="${AGG_SKILLS_DIR:-skills}"
SKILL_BRANCH_PREFIX="${SKILL_BRANCH_PREFIX:-skill/}"
AGG_WT="${AGG_WT:-}"
AGG_URL="${AGG_URL:-${AGG_URL_DEFAULT}}"

# infer aggregator worktree from script path by default
if [[ -z "${AGG_WT}" ]]; then
  AGG_WT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

# verify aggregator repo
git -C "${AGG_WT}" rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "AGG_WT is not a git repo: ${AGG_WT}"

# safety: validate AGG_URL matches local origin
LOCAL_ORIGIN="$(git -C "${AGG_WT}" remote get-url origin 2>/dev/null || true)"
[[ -n "${LOCAL_ORIGIN}" ]] || die "Aggregator has no origin remote: ${AGG_WT}"
if [[ "${AGG_URL}" != "${LOCAL_ORIGIN}" ]]; then
  die "AGG_URL (${AGG_URL}) != local origin (${LOCAL_ORIGIN}). Refusing."
fi

# auto-detect PKG_DIR (dir containing SKILL.md) if not provided
if [[ -z "${PKG_DIR}" ]]; then
  mapfile -t candidates < <(find "${DEV_ROOT}" -mindepth 1 -maxdepth 2 -type f -name "SKILL.md" -printf '%h\n' | sort -u)
  if [[ "${#candidates[@]}" -eq 0 ]]; then
    die "No SKILL.md found under ${DEV_ROOT} (depth<=2). Use --pkg-dir."
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

# infer SKILL from frontmatter name: (supports quotes)
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
AGG_SKILL_DIR="${AGG_WT}/${AGG_SKILLS_DIR}/${SKILL}"

log "DEV_ROOT       = ${DEV_ROOT}"
log "PKG_DIR        = ${PKG_DIR}"
log "PKG_PATH       = ${PKG_PATH}"
log "SKILL          = ${SKILL}"
log "AGG_WT         = ${AGG_WT}"
log "AGG_MAIN       = ${AGG_MAIN}"
log "AGG_SKILLS_DIR = ${AGG_SKILLS_DIR}"
log "AGG_SKILL_DIR  = ${AGG_SKILL_DIR}"
log "SKILL_BRANCH   = ${SKILL_BRANCH}"
log "EXCLUDES       = ${EXCLUDES}"
log "DRY_RUN        = ${DRY_RUN}"

# ==============================================================================
# Preflight safety checks (read-only)
# ==============================================================================
# aggregator must be clean
[[ -z "$(git -C "${AGG_WT}" status --porcelain)" ]] || die "Aggregator worktree has local changes: ${AGG_WT}"

# fetch
git -C "${AGG_WT}" fetch origin --prune

# ensure main exists on origin
git -C "${AGG_WT}" show-ref --verify --quiet "refs/remotes/origin/${AGG_MAIN}" || die "origin/${AGG_MAIN} not found."

# if we're going to update main, require AGG_WT is on main to keep things predictable
if [[ "${ONLY_SKILL_BRANCH}" != "1" ]]; then
  cur="$(git -C "${AGG_WT}" rev-parse --abbrev-ref HEAD)"
  [[ "${cur}" == "${AGG_MAIN}" ]] || die "Aggregator worktree is on '${cur}', please checkout '${AGG_MAIN}' in ${AGG_WT} and retry."
fi

# require local main equals origin/main (strict per your requirement)
local_main="$(git -C "${AGG_WT}" rev-parse "${AGG_MAIN}")"
remote_main="$(git -C "${AGG_WT}" rev-parse "origin/${AGG_MAIN}")"
[[ "${local_main}" == "${remote_main}" ]] || die "Aggregator local ${AGG_MAIN} != origin/${AGG_MAIN}. Please align (pull --ff-only) and retry."

# strict check for skill branch consistency:
# - if origin branch exists and local exists -> must match
# - if origin exists but local missing -> OK (will create tracking)
# - if local exists but origin missing -> refuse (inconsistent)
if git -C "${AGG_WT}" show-ref --verify --quiet "refs/heads/${_


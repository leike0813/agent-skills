#!/usr/bin/env bash
set -euo pipefail

# -----------------------------
# utils
# -----------------------------
die() {
  echo "ERROR: $*" >&2
  exit 1
}
log() { echo "==> $*" >&2; }

DRY_RUN=0
run() {
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "[dry-run] $*" >&2
  else
    eval "$@"
  fi
}

# -----------------------------
# config loading (KEY=VALUE)
# -----------------------------
CFG_FILE=""
load_kv_config() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  log "Loading config: $f"

  # 安全读取：只接受 KEY=VALUE（忽略注释/空行），避免 source 任意代码
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    if [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
      # shellcheck disable=SC2163
      export "$line"
    else
      die "Bad config line (expect KEY=VALUE): $line"
    fi
  done <"$f"
}

# -----------------------------
# args
# -----------------------------
DEV_ROOT=""
PKG_DIR=""
SKILL=""
AGG_URL="${AGG_URL:-}"
AGG_MAIN="${AGG_MAIN:-main}"
AGG_SKILLS_DIR="${AGG_SKILLS_DIR:-skills}"
SKILL_BRANCH_PREFIX="${SKILL_BRANCH_PREFIX:-skill/}"
EXCLUDES="${EXCLUDES:-}"
PUSH="${PUSH:-1}"
ONLY_MAIN=0
ONLY_SKILL_BRANCH=0

usage() {
  cat <<'EOF'
Usage:
  publish-agent-skills.sh [options]

Options:
  --dev-root <path>        Dev repo worktree root (default: git toplevel or script parent)
  --pkg-dir <dir>          Package dir under dev-root (default: auto-detect directory containing SKILL.md)
  --skill <name>           Skill name (default: parse from PKG_DIR/SKILL.md frontmatter name:, else pkg-dir basename)

  --agg-url <url>          agent-skills repo URL (required unless in config/env)
  --agg-main <branch>      agent-skills main branch (default: main)
  --agg-skills-dir <dir>   skills directory in agent-skills (default: skills)
  --skill-branch-prefix <p>prefix for single-skill branch (default: skill/)

  --excludes <csv>         rsync excludes, comma-separated (default: from config EXCLUDES)
  --no-push                do not push (local commit only)
  --dry-run                print commands without executing

  --only-main              update only agent-skills/<main>:skills/<skill>
  --only-skill-branch      update only agent-skills/<skill-branch>
  --config <file>          config file path (default: <dev-root>/.agent-skills-publish.conf)

Examples:
  ./scripts/publish-agent-skills.sh --agg-url git@github.com:me/agent-skills.git
  ./scripts/publish-agent-skills.sh --pkg-dir foo-bar --skill foo-bar
  ./scripts/publish-agent-skills.sh --only-main
EOF
}

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
  --no-push)
    PUSH=0
    shift
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
# infer dev-root
# -----------------------------
if [[ -z "${DEV_ROOT}" ]]; then
  # 1) git toplevel if possible
  if git rev-parse --show-toplevel >/dev/null 2>&1; then
    DEV_ROOT="$(git rev-parse --show-toplevel)"
  else
    # 2) script parent
    DEV_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  fi
fi

# load config (default: dev-root/.agent-skills-publish.conf) unless already specified
if [[ -z "${CFG_FILE}" ]]; then
  CFG_FILE="${DEV_ROOT}/.agent-skills-publish.conf"
fi
load_kv_config "${CFG_FILE}"

# re-apply defaults after config
AGG_URL="${AGG_URL:-https://github.com/leike0813/agent-skills.git}"
AGG_MAIN="${AGG_MAIN:-main}"
AGG_SKILLS_DIR="${AGG_SKILLS_DIR:-skills}"
SKILL_BRANCH_PREFIX="${SKILL_BRANCH_PREFIX:-skill/}"
EXCLUDES="${EXCLUDES:-}"
PUSH="${PUSH:-1}"
DRY_RUN="${DRY_RUN:-0}"

# -----------------------------
# auto-detect package dir
# -----------------------------
if [[ -z "${PKG_DIR}" ]]; then
  # find immediate subdir containing SKILL.md
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
[[ -f "${PKG_PATH}/SKILL.md" ]] || die "SKILL.md not found in package dir: ${PKG_PATH}"

# -----------------------------
# infer skill name
# -----------------------------
if [[ -z "${SKILL}" ]]; then
  # parse frontmatter name: from SKILL.md (very lightweight)
  # expects something like:
  # ---
  # name: foo-bar
  # ---
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
  [ -n "${SKILL}" ]] || SKILL="$(basename "${PKG_PATH}")"
fi

[[ -n "${AGG_URL}" ]] || die "AGG_URL is required (set in config/env or pass --agg-url)."

SKILL_BRANCH="${SKILL_BRANCH_PREFIX}${SKILL}"
AGG_SKILL_PATH="${AGG_SKILLS_DIR}/${SKILL}"

# excludes -> rsync args
RSYNC_EX=()
if [[ -n "${EXCLUDES}" ]]; then
  IFS=',' read -r -a exarr <<<"${EXCLUDES}"
  for e in "${exarr[@]}"; do
    e="${e## }"
    e="${e%% }"
    [[ -n "$e" ]] && RSYNC_EX+=(--exclude "$e")
  done
fi
# always exclude .git
RSYNC_EX+=(--exclude ".git")

log "DEV_ROOT       = ${DEV_ROOT}"
log "PKG_DIR        = ${PKG_DIR}"
log "SKILL          = ${SKILL}"
log "AGG_URL        = ${AGG_URL}"
log "AGG_MAIN       = ${AGG_MAIN}"
log "AGG_SKILLS_DIR = ${AGG_SKILLS_DIR}"
log "AGG_SKILL_PATH = ${AGG_SKILL_PATH}"
log "SKILL_BRANCH   = ${SKILL_BRANCH}"
log "PUSH           = ${PUSH}"
log "DRY_RUN        = ${DRY_RUN}"
log "EXCLUDES       = ${EXCLUDES}"

# -----------------------------
# work in temp clone
# -----------------------------
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
AGG_CLONE="${TMPDIR}/agent-skills"

run "git clone \"${AGG_URL}\" \"${AGG_CLONE}\""
run "cd \"${AGG_CLONE}\" && git fetch origin"

# helper: commit if staged
commit_if_needed() {
  local msg="$1"
  if git diff --cached --quiet; then
    log "No staged changes: ${msg}"
    return 0
  fi
  run "git commit -m \"${msg}\""
}

push_if_enabled() {
  local ref="$1"
  if [[ "${PUSH}" == "1" ]]; then
    run "git push origin \"${ref}\""
  else
    log "PUSH=0, skip push ${ref}"
  fi
}

# -----------------------------
# 1) update main: skills/<skill>
# -----------------------------
if [[ "${ONLY_SKILL_BRANCH}" != "1" ]]; then
  run "cd \"${AGG_CLONE}\" && git checkout \"${AGG_MAIN}\""
  run "cd \"${AGG_CLONE}\" && mkdir -p \"${AGG_SKILL_PATH}\""
  # rsync dev package -> aggregator path
  run "cd \"${AGG_CLONE}\" && rsync -a --delete ${RSYNC_EX[*]} \"${PKG_PATH}/\" \"${AGG_SKILL_PATH}/\""
  run "cd \"${AGG_CLONE}\" && git add \"${AGG_SKILL_PATH}\""
  commit_if_needed "publish(${SKILL}): update ${AGG_SKILL_PATH}"
  push_if_enabled "${AGG_MAIN}"
fi

# -----------------------------
# 2) sync single-skill branch: repo root == package
# -----------------------------
if [[ "${ONLY_MAIN}" != "1" ]]; then
  run "cd \"${AGG_CLONE}\" && git checkout -B \"${SKILL_BRANCH}\" \"origin/${SKILL_BRANCH}\" 2>/dev/null || git checkout -b \"${SKILL_BRANCH}\""
  # wipe tracked files
  run "cd \"${AGG_CLONE}\" && git rm -rf . || true"
  # checkout skills/<skill> from main then promote to root
  run "cd \"${AGG_CLONE}\" && git checkout \"origin/${AGG_MAIN}\" -- \"${AGG_SKILL_PATH}\""
  run "cd \"${AGG_CLONE}\" && rsync -a --delete \"${AGG_SKILL_PATH}/\" ./"
  run "cd \"${AGG_CLONE}\" && git rm -rf \"${AGG_SKILLS_DIR}\" || true"
  run "cd \"${AGG_CLONE}\" && git add -A"
  commit_if_needed "sync(${SKILL}): from ${AGG_MAIN}:${AGG_SKILL_PATH}"
  push_if_enabled "${SKILL_BRANCH}"
fi

log "Done."

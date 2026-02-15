#!/usr/bin/env bash
set -euo pipefail

die() {
  echo "ERROR: $*" >&2
  exit 1
}
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
# defaults
# -----------------------------
AGG_URL_DEFAULT="https://github.com/leike0813/agent-skills.git"
AGG_WT_DEFAULT="/home/joshua/Workspace/Code/Skill/agent-skills/"

DEV_ROOT=""
PKG_DIR=""
SKILL=""
EXCLUDES="${EXCLUDES:-}" # comma-separated prefix excludes relative to package root (optional)

AGG_WT="${AGG_WT:-${AGG_WT_DEFAULT}}"
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
  --excludes <csv>          Extra excludes (prefix match), e.g. "node_modules,dist"
  --agg-wt <path>           Local agent-skills worktree (default: AGG_WT_DEFAULT in script)
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
  AGG_WT=...
  AGG_MAIN=main
  EXCLUDES=node_modules,dist
EOF
}

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

normalize_git_url() {
  local u="$1"
  u="$(printf '%s' "$u" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
  u="${u%/}"
  u="${u%.git}"

  if [[ "$u" =~ ^git@([^:]+):(.+)$ ]]; then
    u="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
  elif [[ "$u" =~ ^ssh://git@([^/]+)/(.+)$ ]]; then
    u="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
  elif [[ "$u" =~ ^https?://([^/]+)/(.+)$ ]]; then
    u="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
  fi

  u="${u%/}"
  u="${u%.git}"
  printf '%s' "$u"
}

clear_dir_contents() {
  local d="$1"
  [[ -d "$d" ]] || mkdir -p "$d"
  local old_dotglob old_nullglob
  old_dotglob="$(shopt -p dotglob || true)"
  old_nullglob="$(shopt -p nullglob || true)"
  shopt -s dotglob nullglob
  rm -rf -- "$d"/*
  eval "${old_dotglob}" >/dev/null 2>&1 || true
  eval "${old_nullglob}" >/dev/null 2>&1 || true
}

# -----------------------------
# args
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
  --excludes)
    EXCLUDES="${2:-}"
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
  --dry-run)
    DRY_RUN=1
    shift
    ;;
  -h | --help)
    usage
    exit 0
    ;;
  *) die "Unknown arg: $1" ;;
  esac
done

# infer DEV_ROOT from current dir
if [[ -z "${DEV_ROOT}" ]]; then
  git rev-parse --show-toplevel >/dev/null 2>&1 || die "Run this from inside a skill dev git repo."
  DEV_ROOT="$(git rev-parse --show-toplevel)"
fi

# load config default
if [[ -z "${CFG_FILE}" ]]; then
  CFG_FILE="${DEV_ROOT}/.agent-skills-publish.conf"
fi
load_kv_config "${CFG_FILE}"

# re-apply defaults after config
EXCLUDES="${EXCLUDES:-}"
AGG_MAIN="${AGG_MAIN:-main}"
AGG_SKILLS_DIR="${AGG_SKILLS_DIR:-skills}"
SKILL_BRANCH_PREFIX="${SKILL_BRANCH_PREFIX:-skill/}"
AGG_WT="${AGG_WT:-${AGG_WT_DEFAULT}}"
AGG_URL="${AGG_URL:-${AGG_URL_DEFAULT}}"

# verify aggregator repo
git -C "${AGG_WT}" rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "AGG_WT is not a git repo: ${AGG_WT}"

LOCAL_ORIGIN="$(git -C "${AGG_WT}" remote get-url origin 2>/dev/null || true)"
[[ -n "${LOCAL_ORIGIN}" ]] || die "Aggregator has no origin remote: ${AGG_WT}"

if [[ "$(normalize_git_url "${AGG_URL}")" != "$(normalize_git_url "${LOCAL_ORIGIN}")" ]]; then
  die "AGG_URL does not match local origin after normalization.
  AGG_URL:      ${AGG_URL} -> $(normalize_git_url "${AGG_URL}")
  local origin: ${LOCAL_ORIGIN} -> $(normalize_git_url "${LOCAL_ORIGIN}")"
fi

# detect PKG_DIR
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

# infer SKILL from frontmatter name: (supports " and ', uses \047 for ')
if [[ -z "${SKILL}" ]]; then
  SKILL="$(awk '
    BEGIN{in_fm=0}
    /^---[[:space:]]*$/ {in_fm = 1 - in_fm; next}
    in_fm==1 && $0 ~ /^[[:space:]]*name:[[:space:]]*/ {
      sub(/^[[:space:]]*name:[[:space:]]*/, "", $0);
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0);
      gsub(/^["\047]|["\047]$/, "", $0);
      print $0; exit
    }
  ' "${PKG_PATH}/SKILL.md")"
  [[ -n "${SKILL}" ]] || SKILL="$(basename "${PKG_PATH}")"
fi

SKILL_BRANCH="${SKILL_BRANCH_PREFIX}${SKILL}"
AGG_SKILL_DIR_REL="${AGG_SKILLS_DIR}/${SKILL}"

log "DEV_ROOT       = ${DEV_ROOT}"
log "PKG_DIR        = ${PKG_DIR}"
log "PKG_PATH       = ${PKG_PATH}"
log "SKILL          = ${SKILL}"
log "AGG_WT         = ${AGG_WT}"
log "AGG_MAIN       = ${AGG_MAIN}"
log "AGG_SKILLS_DIR = ${AGG_SKILLS_DIR}"
log "AGG_SKILL_DIR  = ${AGG_WT}/${AGG_SKILL_DIR_REL}"
log "SKILL_BRANCH   = ${SKILL_BRANCH}"
log "EXCLUDES       = ${EXCLUDES}"
log "DRY_RUN        = ${DRY_RUN}"

# ==============================================================================
# Preflight (read-only)
# ==============================================================================
[[ -z "$(git -C "${AGG_WT}" status --porcelain)" ]] || die "Aggregator worktree has local changes: ${AGG_WT}"

git -C "${AGG_WT}" fetch origin --prune
git -C "${AGG_WT}" show-ref --verify --quiet "refs/remotes/origin/${AGG_MAIN}" || die "origin/${AGG_MAIN} not found."

# require AGG_WT currently on main if we will update main in-place
if [[ "${ONLY_SKILL_BRANCH}" != "1" ]]; then
  cur="$(git -C "${AGG_WT}" rev-parse --abbrev-ref HEAD)"
  [[ "${cur}" == "${AGG_MAIN}" ]] || die "Aggregator worktree must be on '${AGG_MAIN}' to publish main in-place. Current: ${cur}"
fi

# strict: local main == origin/main
local_main="$(git -C "${AGG_WT}" rev-parse "${AGG_MAIN}" 2>/dev/null || true)"
remote_main="$(git -C "${AGG_WT}" rev-parse "origin/${AGG_MAIN}")"
if [[ -n "${local_main}" && "${local_main}" != "${remote_main}" ]]; then
  die "Aggregator local ${AGG_MAIN} != origin/${AGG_MAIN}. Please align (pull --ff-only) and retry."
fi

# strict for skill branch if local exists
if git -C "${AGG_WT}" show-ref --verify --quiet "refs/heads/${SKILL_BRANCH}"; then
  if git -C "${AGG_WT}" show-ref --verify --quiet "refs/remotes/origin/${SKILL_BRANCH}"; then
    lsb="$(git -C "${AGG_WT}" rev-parse "${SKILL_BRANCH}")"
    rsb="$(git -C "${AGG_WT}" rev-parse "origin/${SKILL_BRANCH}")"
    [[ "${lsb}" == "${rsb}" ]] || die "Local ${SKILL_BRANCH} != origin/${SKILL_BRANCH}. Align first then retry."
  else
    die "Local ${SKILL_BRANCH} exists but origin/${SKILL_BRANCH} does not. Push/delete it first, then retry."
  fi
fi

# refuse if target path is submodule
if git -C "${AGG_WT}" ls-files --stage -- "${AGG_SKILL_DIR_REL}" | awk '{print $1}' | grep -q "^160000$"; then
  die "${AGG_SKILL_DIR_REL} is a submodule (gitlink). Convert it to a normal directory first."
fi

# ==============================================================================
# Build publish file list (honors .gitignore)
# ==============================================================================
TMPDIR="$(mktemp -d)"
cleanup() { rm -rf "${TMPDIR}"; }
trap cleanup EXIT

LIST_RAW="${TMPDIR}/files_raw.txt"
LIST_REL="${TMPDIR}/files_rel.txt"
LIST_FINAL="${TMPDIR}/files_final.txt"
TARFILE="${TMPDIR}/pkg.tar"

git -C "${DEV_ROOT}" ls-files -c -o --exclude-standard -- "${PKG_DIR}" >"${LIST_RAW}"
[[ -s "${LIST_RAW}" ]] || die "No publishable files found under ${PKG_DIR}."

sed "s#^${PKG_DIR}/##" "${LIST_RAW}" >"${LIST_REL}"

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

# ==============================================================================
# DRY-RUN: no side effects
# ==============================================================================
if [[ "${DRY_RUN}" == "1" ]]; then
  log "DRY RUN plan:"
  echo "  - Files to publish: $(wc -l <"${LIST_FINAL}")" >&2
  if [[ "${ONLY_SKILL_BRANCH}" != "1" ]]; then
    echo "  - Would update ${AGG_MAIN}:${AGG_SKILL_DIR_REL} in-place in AGG_WT and push origin/${AGG_MAIN}" >&2
  fi
  if [[ "${ONLY_MAIN}" != "1" ]]; then
    echo "  - Would create/update ${SKILL_BRANCH} via temp worktree (detached from origin/${AGG_MAIN}) and push origin/${SKILL_BRANCH}" >&2
  fi
  exit 0
fi

# create tarball
(cd "${PKG_PATH}" && tar -cf "${TARFILE}" -T "${LIST_FINAL}")

# ==============================================================================
# Step 1: update main IN-PLACE (no worktree add -> avoids your error)
# ==============================================================================
if [[ "${ONLY_SKILL_BRANCH}" != "1" ]]; then
  mkdir -p "${AGG_WT}/${AGG_SKILL_DIR_REL}"
  clear_dir_contents "${AGG_WT}/${AGG_SKILL_DIR_REL}"
  tar -xf "${TARFILE}" -C "${AGG_WT}/${AGG_SKILL_DIR_REL}"

  git -C "${AGG_WT}" add "${AGG_SKILL_DIR_REL}"
  if ! git -C "${AGG_WT}" diff --cached --quiet; then
    git -C "${AGG_WT}" commit -m "publish(${SKILL}): update ${AGG_SKILL_DIR_REL}"
    git -C "${AGG_WT}" push origin "${AGG_MAIN}"
  else
    log "No changes detected for ${AGG_MAIN}:${AGG_SKILL_DIR_REL}"
  fi
fi

# ==============================================================================
# Step 2: update/create skill branch via TEMP worktree (safe)
# ==============================================================================
if [[ "${ONLY_MAIN}" != "1" ]]; then
  git -C "${AGG_WT}" fetch origin --prune

  SKILL_WT="${TMPDIR}/agg-skill-wt"

  # ensure local tracking branch if remote exists
  if git -C "${AGG_WT}" show-ref --verify --quiet "refs/remotes/origin/${SKILL_BRANCH}" &&
    ! git -C "${AGG_WT}" show-ref --verify --quiet "refs/heads/${SKILL_BRANCH}"; then
    git -C "${AGG_WT}" branch --track "${SKILL_BRANCH}" "origin/${SKILL_BRANCH}"
  fi

  if git -C "${AGG_WT}" show-ref --verify --quiet "refs/heads/${SKILL_BRANCH}"; then
    git -C "${AGG_WT}" worktree add "${SKILL_WT}" "${SKILL_BRANCH}"
  else
    # base from origin/main but detached -> no branch lock
    git -C "${AGG_WT}" worktree add --detach "${SKILL_WT}" "origin/${AGG_MAIN}"
    git -C "${SKILL_WT}" checkout --orphan "${SKILL_BRANCH}"
  fi

  git -C "${SKILL_WT}" rm -rf . >/dev/null 2>&1 || true
  git -C "${SKILL_WT}" clean -fdx
  tar -xf "${TARFILE}" -C "${SKILL_WT}"

  git -C "${SKILL_WT}" add -A
  if git -C "${SKILL_WT}" diff --cached --quiet; then
    git -C "${SKILL_WT}" commit --allow-empty -m "init(${SKILL}): create ${SKILL_BRANCH}"
  else
    git -C "${SKILL_WT}" commit -m "sync(${SKILL}): publish package root"
  fi
  git -C "${SKILL_WT}" push -u origin "${SKILL_BRANCH}"

  git -C "${AGG_WT}" worktree remove --force "${SKILL_WT}"
  git -C "${AGG_WT}" worktree prune
fi

# ==============================================================================
# Post-check: ensure local == origin for touched branches
# ==============================================================================
git -C "${AGG_WT}" fetch origin --prune

if [[ "${ONLY_SKILL_BRANCH}" != "1" ]]; then
  lm2="$(git -C "${AGG_WT}" rev-parse "${AGG_MAIN}")"
  rm2="$(git -C "${AGG_WT}" rev-parse "origin/${AGG_MAIN}")"
  [[ "${lm2}" == "${rm2}" ]] || die "Post-check failed: ${AGG_MAIN} != origin/${AGG_MAIN}"
fi

if [[ "${ONLY_MAIN}" != "1" ]]; then
  lsb2="$(git -C "${AGG_WT}" rev-parse "${SKILL_BRANCH}")"
  rsb2="$(git -C "${AGG_WT}" rev-parse "origin/${SKILL_BRANCH}")"
  [[ "${lsb2}" == "${rsb2}" ]] || die "Post-check failed: ${SKILL_BRANCH} != origin/${SKILL_BRANCH}"
fi

log "Done. Publish completed; aggregator local & remote aligned."

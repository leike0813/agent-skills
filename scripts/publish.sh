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
VENDOR_ROOT_DEFAULT="vendor"

DEV_ROOT=""
PKG_DIR=""
SKILL=""
EXCLUDES="${EXCLUDES:-}" # comma-separated prefix excludes relative to package root (optional)
VENDOR_URL=""
VENDOR_BRANCH=""
VENDOR_SUBPATH=""
VENDOR_ROOT="${VENDOR_ROOT:-}"        # set after config load
VENDOR_MODE=0
AGG_WT="${AGG_WT:-${AGG_WT_DEFAULT}}"
AGG_URL="${AGG_URL:-${AGG_URL_DEFAULT}}"
AGG_MAIN="${AGG_MAIN:-main}"
AGG_SKILLS_DIR="${AGG_SKILLS_DIR:-skills}"
SKILL_BRANCH_PREFIX="${SKILL_BRANCH_PREFIX:-skill/}"

ONLY_MAIN=0
ONLY_SKILL_BRANCH=0
CFG_FILE=""
SKILL_EXPLICIT=0  # track whether --skill was explicitly provided

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

Auto-discovery:
  If --pkg-dir is not provided, the script auto-discovers packages to publish:
    1. If a .skills file exists in DEV_ROOT, read package dirs from it (one per line)
.skills file format (one package dir per line, relative to DEV_ROOT):
  skill-a
  skill-b

Config file format (KEY=VALUE):
  AGG_URL=...
  AGG_WT=...
  AGG_MAIN=main
  EXCLUDES=node_modules,dist

Vendor mode:
  --vendor-url <url>       GitHub URL of the third-party skill, e.g.
                           https://github.com/<owner>/<repo>/tree/<branch>/<path/to/skill>
                           or https://github.com/<owner>/<repo> (skill at repo root)
  --vendor-root <dir>      Submodule install path under AGG_WT (default: vendor)

  The URL is parsed to derive the upstream repo, branch, and skill subpath
  (or defaults to branch=main and subpath="" when no /tree/ segment is
  present). The third-party repo is added as a submodule under
  AGG_WT/<vendor-root>/<repo> and the skill is read from
  <vendor-root>/<repo>[/<subpath>]. /blob/<branch>/<file> URLs are rejected
  because they point to a single file, not a skill directory. Vendor mode
  must not be combined with --pkg-dir.

  Examples:
    publish.sh --vendor-url https://github.com/hugohe3/ppt-master/tree/main/skills/ppt-master \
               --skill ppt-master
    publish.sh --vendor-url https://github.com/hugohe3/ppt-master --skill ppt-master \
               --vendor-root libs
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

# parse_github_url <url>
#   https://github.com/<owner>/<repo>                          -> branch=main, subpath=""
#   https://github.com/<owner>/<repo>/                         -> same
#   https://github.com/<owner>/<repo>.git                      -> same
#   https://github.com/<owner>/<repo>/tree/<branch>            -> subpath=""
#   https://github.com/<owner>/<repo>/tree/<branch>/<subpath...>
# Anything else (ssh, gitlab, /blob/, malformed) -> die.
parse_github_url() {
  local input="$1"
  local owner="" repo="" branch="" subpath=""
  if [[ "$input" =~ ^https://github\.com/([^/]+)/([^/]+)/tree/([^/]+)(/(.*))?/?$ ]]; then
    owner="${BASH_REMATCH[1]}"
    repo="${BASH_REMATCH[2]}"
    branch="${BASH_REMATCH[3]}"
    subpath="${BASH_REMATCH[5]:-}"
  elif [[ "$input" =~ ^https://github\.com/([^/]+)/([^/]+)/blob/ ]]; then
    die "--vendor-url points to /blob/<branch>/<file>: this is a single file, not a skill directory. Got: $input"
  elif [[ "$input" =~ ^https://github\.com/([^/]+)/([^/]+)\.git/?$ ]]; then
    owner="${BASH_REMATCH[1]}"
    repo="${BASH_REMATCH[2]}"
    branch="main"
    subpath=""
  elif [[ "$input" =~ ^https://github\.com/([^/]+)/([^/]+)/?$ ]]; then
    owner="${BASH_REMATCH[1]}"
    repo="${BASH_REMATCH[2]}"
    branch="main"
    subpath=""
  else
    die "Only https://github.com/<owner>/<repo>[ /tree/<branch>/<subpath> | .git ] URLs are supported for --vendor-url. Got: $input"
  fi
  # Trim any trailing slash from the subpath.
  subpath="${subpath%/}"
  printf '%s\t%s\t%s\t%s\n' "$owner" "$repo" "$branch" "$subpath"
}
# ensure_vendor_submodule <owner> <repo> <branch>
# Requires VENDOR_ROOT and AGG_WT set. Adds <VENDOR_ROOT>/<repo> as a git
# submodule under AGG_WT pointing at https://github.com/<owner>/<repo>.git,
# commits the addition, and ensures the submodule is checked out in the
# working tree. The branch argument is recorded into .gitmodules so future
# `git submodule update --remote` will follow it. Sets VENDOR_REL (the path
# inside AGG_WT, e.g. vendor/ppt-master) and VENDOR_PATH (absolute on-disk).
ensure_vendor_submodule() {
  local owner="$1"
  local repo="$2"
  local branch="$3"

  local vendor_rel="${VENDOR_ROOT}/${repo}"
  local vendor_abs="${AGG_WT}/${vendor_rel}"

  if [[ -e "${vendor_abs}" ]]; then
    log "Vendor submodule already present: ${vendor_rel}"
    # Make sure .gitmodules records the desired branch even if the submodule
    # was added previously without one.
    git -C "${AGG_WT}" config -f .gitmodules "submodule.${vendor_rel}.branch" "${branch}" >/dev/null
    if ! git -C "${AGG_WT}" diff --cached --quiet -- .gitmodules; then
      git -C "${AGG_WT}" add .gitmodules
      git -C "${AGG_WT}" commit -m "chore(vendor): record branch ${branch} for ${vendor_rel}" -- .gitmodules || true
    fi
  else
    log "Adding vendor submodule: ${vendor_rel} -> https://github.com/${owner}/${repo}.git (branch=${branch})"
    git -C "${AGG_WT}" submodule add --force --branch "${branch}" "https://github.com/${owner}/${repo}.git" "${vendor_rel}"
    if ! git -C "${AGG_WT}" diff --cached --quiet; then
      git -C "${AGG_WT}" commit -m "chore(vendor): add ${owner}/${repo} as ${vendor_rel}"
    fi
  fi

  git -C "${AGG_WT}" submodule update --init --recursive "${vendor_rel}" >/dev/null
  git -C "${AGG_WT}" submodule update --remote "${vendor_rel}" 2>/dev/null || true

  VENDOR_REL="${vendor_rel}"
  VENDOR_PATH="${vendor_abs}"
  export VENDOR_REL VENDOR_PATH
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
extract_skill_info() {
  local skill_dir="$1"
  local skill_md="${skill_dir}/SKILL.md"
  [[ -f "$skill_md" ]] || return 1

  local name desc
  # name: a single-line scalar; strip surrounding quotes and trim.
  name="$(awk '
    BEGIN{in_fm=0}
    /^---[[:space:]]*$/ {in_fm = 1 - in_fm; next}
    in_fm==1 && $0 ~ /^[[:space:]]*name:[[:space:]]*/ {
      sub(/^[[:space:]]*name:[[:space:]]*/, "", $0);
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0);
      gsub(/^["'"'"']|["'"'"']$/, "", $0);
      print $0; exit
    }
  ' "$skill_md")"

  # description: YAML scalars may be inline ("..." or '...') or use a block
 # scalar header ("description: >" or "description: |" followed by indented
 # continuation lines until a blank line / lower indent). Fold ">" (folded
 # style) into single spaces; keep "|" (literal) as newlines.
  desc="$(awk '
    BEGIN{in_fm=0; mode=""; done=0}
    function flush() {
      if (mode != "" && !done) {
        done = 1;
        # Collapse whitespace for folded style, trim trailing spaces.
        gsub(/[ \t]+/, " ", buf);
        sub(/^ /, "", buf); sub(/ $/, "", buf);
        print buf;
        exit;
      }
    }
    /^---[[:space:]]*$/ { in_fm = 1 - in_fm; next }
    in_fm==1 {
      # Continuation lines (indented) come FIRST so a line like
      # "  AI-driven ..." is captured before any unindented check fires.
      if (mode != "" && $0 ~ /^[[:space:]]+[^[:space:]]/) {
        line = $0;
        sub(/^[[:space:]]+/, "", line);
        if (mode == "folded") {
          if (buf == "") buf = line;
          else buf = buf " " line;
        } else {
          if (buf == "") buf = line;
          else buf = buf "\n" line;
        }
        next;
      }
      if (mode != "" && $0 ~ /^[[:space:]]*$/) {
        # Blank line ends a block scalar.
        flush();
        next;
      }
      if (mode != "" && $0 ~ /^[^[:space:]]/) {
        # Unindented non-blank line: a new YAML key. End the block scalar.
        flush();
        next;
      }
      if ($0 ~ /^[[:space:]]*description:[[:space:]]*[|>][+-]?[[:space:]]*$/) {
        # Block scalar header. Capture style char (">" or "|").
        match($0, /[|>]/);
        style = substr($0, RSTART, 1);
        mode = (style == ">") ? "folded" : "literal";
        rest = $0;
        sub(/^[[:space:]]*description:[[:space:]]*[|>][+-]?[[:space:]]*/, "", rest);
        buf = rest;
        next;
      }
      if ($0 ~ /^[[:space:]]*description:[[:space:]]*"/) {
        # Double-quoted inline string.
        buf = $0;
        sub(/^[[:space:]]*description:[[:space:]]*/, "", buf);
        gsub(/^"|"$/, "", buf);
        done=1;
        print buf;
        exit;
      }
      if ($0 ~ /^[[:space:]]*description:[[:space:]]*'\''/) {
        buf = $0;
        sub(/^[[:space:]]*description:[[:space:]]*/, "", buf);
        gsub(/^'\''|'\''$/, "", buf);
        done=1;
        print buf;
        exit;
      }
      if ($0 ~ /^[[:space:]]*description:[[:space:]]*/) {
        # Plain single-line scalar.
        buf = $0;
        sub(/^[[:space:]]*description:[[:space:]]*/, "", buf);
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", buf);
        done=1;
        print buf;
        exit;
      }
    }
    END { flush() }
  ' "$skill_md")"
  [[ -n "$name" ]] || name="$(basename "$skill_dir")"
  [[ -n "$desc" ]] || desc="No description available."

  printf '%s\t%s\n' "$name" "$desc"
}

# record_vendor_source <agg_wt> <skill> <url>
# Upserts the skill -> vendor URL mapping into <agg_wt>/.vendor-sources.
# File format is "<skill>\t<url>" one per line, sorted by skill. Existing
# entries for the same skill are replaced; other entries are preserved.
# Used by sync_readme_skills_table to render a Vendor Sources section in
# the aggregator README.
record_vendor_source() {
  local agg_wt="$1"
  local skill="$2"
  local url="$3"
  local file="${agg_wt}/.vendor-sources"
  [[ -n "${skill}" && -n "${url}" ]] || return 0
  local tmp="${file}.new"
  # Drop any existing entry for this skill, then append the new one, then
 # sort the whole file by skill name for stable diffs.
  if [[ -f "${file}" ]]; then
    grep -v -E "^${skill//./\\.}"$'\t' "${file}" > "${tmp}" 2>/dev/null || true
  else
    : > "${tmp}"
  fi
  printf '%s\t%s\n' "${skill}" "${url}" >> "${tmp}"
  LC_ALL=C sort -u "${tmp}" > "${file}"
  rm -f "${tmp}"
}

sync_readme_skills_table() {
  local agg_wt="$1"
  local skills_dir="$2"
  local readme="${agg_wt}/README.md"

  log "Syncing README.md skills table..."

  [[ -d "${agg_wt}/${skills_dir}" ]] || return 0

  local tmpfile="${TMPDIR}/skills_table.md"
  local sources_file="${agg_wt}/.vendor-sources"

  {
    echo "# agent-skills"
    echo ""
    echo "This repo aggregates skills as git submodules."
    echo ""
    echo "## Available Skills"
    echo ""
    echo "| Skill-ID | 说明 |"
    echo "|----------|------|"
    local skill_dirs=()
    for entry in "${agg_wt}/${skills_dir}"/*/; do
      [[ -d "$entry" ]] || continue
      local skill_name
      skill_name="$(basename "$entry")"
      skill_dirs+=("$skill_name")
    done

    IFS=$'\n' sorted=($(sort <<<"${skill_dirs[*]}")); unset IFS

    for skill_name in "${sorted[@]}"; do
      local skill_path="${agg_wt}/${skills_dir}/${skill_name}"
      local info
      if info="$(extract_skill_info "$skill_path")"; then
        local name desc
        name="$(echo "$info" | cut -f1)"
        desc="$(echo "$info" | cut -f2)"
        desc="$(echo "$desc" | sed 's/|/\\|/g')"
        echo "| ${name} | ${desc} |"
      fi
    done

    # Render the Vendor Sources section if .vendor-sources has entries.
    # Source lines are "<skill>\t<url>"; only those skills still present in
    # the table are rendered, so removing a skill drops its line on the
    # next sync.
    if [[ -s "${sources_file}" ]]; then
      echo ""
      echo "## Vendor Sources"
      echo ""
      echo "以下 skill 通过第三方仓库发布,内容由对应仓库同步而来。"
      echo ""
      # Render only entries whose skill is still in the current table.
      while IFS=$'\t' read -r src_skill src_url; do
        [[ -z "${src_skill}" || -z "${src_url}" ]] && continue
        local match=0
        for s in "${sorted[@]}"; do
          [[ "${s}" == "${src_skill}" ]] && match=1 && break
        done
        [[ "${match}" == "1" ]] || continue
        echo "- \`${src_skill}\` — <${src_url}>"
      done < "${sources_file}"
    fi
  } > "$tmpfile"

  if [[ -f "$readme" ]]; then
    cp "$readme" "${readme}.bak"
  fi
  cp "$tmpfile" "$readme"

  git -C "${agg_wt}" add "README.md"
  # .vendor-sources may be newly created by record_vendor_source above; stage
  # it explicitly so the next sync reflects the latest mapping.
  if [[ -f "${sources_file}" ]]; then
    git -C "${agg_wt}" add "${sources_file}"
  fi
  if ! git -C "${agg_wt}" diff --cached --quiet; then
    git -C "${agg_wt}" commit -m "docs: sync skills table in README.md"
    git -C "${agg_wt}" push origin "${AGG_MAIN}"
    log "README.md synced and pushed."
  else
    log "No changes to README.md"
    [[ -f "${readme}.bak" ]] && rm -f "${readme}.bak"
  fi
}

# -----------------------------
# args
# ----------------------------=
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
    SKILL_EXPLICIT=1
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
  --vendor-url)
    VENDOR_URL="${2:-}"
    shift 2
    ;;
  --vendor-root)
    VENDOR_ROOT="${2:-}"
    shift 2
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

# ==============================================================================
# Vendor mode validation
# --vendor-url is the single user-supplied vendor input. The URL itself is
# parsed into (owner, repo, branch, subpath); see parse_github_url. Vendor
# mode must not be combined with --pkg-dir or the .skills auto-discovery
# path: vendor content is sourced from the third-party repo, not the local
# dev worktree.
if [[ -n "${VENDOR_URL}" ]]; then
  if [[ -n "${PKG_DIR}" ]]; then
    die "--vendor-url cannot be combined with --pkg-dir."
  fi
  VENDOR_MODE=1
fi

# infer DEV_ROOT from current dir (only required in local mode)
if [[ "${VENDOR_MODE}" != "1" ]]; then
  if [[ -z "${DEV_ROOT}" ]]; then
    git rev-parse --show-toplevel >/dev/null 2>&1 || die "Run this from inside a skill dev git repo."
    DEV_ROOT="$(git rev-parse --show-toplevel)"
  fi
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
VENDOR_ROOT="${VENDOR_ROOT:-${VENDOR_ROOT_DEFAULT}}"

LOCAL_ORIGIN="$(git -C "${AGG_WT}" remote get-url origin 2>/dev/null || true)"
[[ -n "${LOCAL_ORIGIN}" ]] || die "Aggregator has no origin remote: ${AGG_WT}"

if [[ "$(normalize_git_url "${AGG_URL}")" != "$(normalize_git_url "${LOCAL_ORIGIN}")" ]]; then
  die "AGG_URL does not match local origin after normalization.
  AGG_URL:      ${AGG_URL} -> $(normalize_git_url "${AGG_URL}")
  local origin: ${LOCAL_ORIGIN} -> $(normalize_git_url "${LOCAL_ORIGIN}")"
fi

# ==============================================================================
# Vendor submodule setup (vendor mode only)
# ==============================================================================
if [[ "${VENDOR_MODE}" == "1" ]]; then
  # parse URL -> owner / repo / branch / subpath
  IFS=$'\t' read -r VENDOR_OWNER VENDOR_REPO VENDOR_BRANCH VENDOR_SUBPATH < <(parse_github_url "${VENDOR_URL}")
  export VENDOR_OWNER VENDOR_REPO VENDOR_BRANCH VENDOR_SUBPATH

  # refuse .skills file in vendor mode (explicit)
  if [[ -f "${DEV_ROOT:-/nonexistent}/.skills" ]]; then
    die "(vendor mode) .skills file is not supported together with --vendor-url."
  fi

  # add / refresh vendor submodule, tracking the parsed branch.
  ensure_vendor_submodule "${VENDOR_OWNER}" "${VENDOR_REPO}" "${VENDOR_BRANCH}"

  # redirect package path: empty subpath means the skill lives at the repo root.
  if [[ -z "${VENDOR_SUBPATH}" ]]; then
    PKG_PATH="${VENDOR_PATH}"
  else
    PKG_PATH="${VENDOR_PATH}/${VENDOR_SUBPATH}"
  fi
  [[ -d "${PKG_PATH}" ]] || die "Vendor subpath not found: ${PKG_PATH}"
  [[ -f "${PKG_PATH}/SKILL.md" ]] || die "SKILL.md not found under vendor path: ${PKG_PATH}"

  # PKG_DIRS is just one entry; the publish loop below iterates over it.
  PKG_DIRS=("${VENDOR_SUBPATH:-}")
  PKG_DIR="${VENDOR_SUBPATH:-}"
  export PKG_DIRS PKG_DIR PKG_PATH

  # Note: aggregator worktree dirty / fetch / submodule-gitlink checks below
  # still apply; they protect against corrupting AGG_WT state. VENDOR_PATH
  # itself is a separate submodule, so the gitlink check on
  # AGG_SKILL_DIR_REL (skills/<skill>) is unaffected.
fi

# ==============================================================================
# Package discovery (local mode only)
# ==============================================================================
PKG_DIRS=()

if [[ "${VENDOR_MODE}" == "1" ]]; then
  # PKG_DIRS / PKG_DIR / PKG_PATH already set in the vendor setup block above.
  PKG_DIRS=("${VENDOR_SUBPATH}")
elif [[ -n "${PKG_DIR}" ]]; then
  # --pkg-dir explicitly provided, single package mode
  PKG_DIRS=("${PKG_DIR}")
else
  # 1) Try .skills file first
  if [[ -f "${DEV_ROOT}/.skills" ]]; then
    log "Loading packages from .skills..."
    while IFS= read -r line || [[ -n "$line" ]]; do
      # skip empty lines and comments
      [[ -z "$line" ]] && continue
      [[ "$line" =~ ^[[:space:]]*# ]] && continue
      # trim whitespace
      line="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
      [[ -z "$line" ]] && continue
      PKG_DIRS+=("$line")
    done <"${DEV_ROOT}/.skills"
    if [[ "${#PKG_DIRS[@]}" -eq 0 ]]; then
      die ".skills file found but contains no valid package dirs."
    fi
    log "Found ${#PKG_DIRS[@]} package(s) in .skills: ${PKG_DIRS[*]}"
  else
    # 2) Fall back to auto-detect
    mapfile -t candidates < <(find "${DEV_ROOT}" -mindepth 1 -maxdepth 2 -type f -name "SKILL.md" -printf '%h\n' | sort -u)
    if [[ "${#candidates[@]}" -eq 0 ]]; then
      die "No SKILL.md found under ${DEV_ROOT} (depth<=2). Use --pkg-dir or create a .skills file."
    elif [[ "${#candidates[@]}" -gt 1 ]]; then
      echo "Multiple SKILL.md found:" >&2
      printf '  - %s\n' "${candidates[@]}" >&2
      die "Ambiguous PKG_DIR. Use --pkg-dir or create a .skills file."
    else
      PKG_DIRS=("$(basename "${candidates[0]}")")
    fi
  fi
fi

# Validate all discovered package dirs (local mode only)
if [[ "${VENDOR_MODE}" != "1" ]]; then
  for pkg in "${PKG_DIRS[@]}"; do
    [[ -d "${DEV_ROOT}/${pkg}" ]] || die "Package dir not found: ${DEV_ROOT}/${pkg}"
    [[ -f "${DEV_ROOT}/${pkg}/SKILL.md" ]] || die "SKILL.md not found in: ${DEV_ROOT}/${pkg}"
  done
fi

# ==============================================================================
# Publish each package
# ==============================================================================
for PKG_DIR in "${PKG_DIRS[@]}"; do

# In vendor mode PKG_PATH was set in the vendor setup block above; in
# local mode it's derived from DEV_ROOT + PKG_DIR here.
if [[ "${VENDOR_MODE}" != "1" ]]; then
  PKG_PATH="${DEV_ROOT}/${PKG_DIR}"
fi
if [[ "${SKILL_EXPLICIT}" != "1" ]]; then
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
# refuse if target path is a submodule.
# Note: in vendor mode, AGG_SKILL_DIR_REL is skills/<skill>, which is a
# plain directory we control; the vendor submodule lives under
# VENDOR_ROOT/<repo> and never overlaps this path. The check therefore
# remains correct in both modes.
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

if [[ "${VENDOR_MODE}" == "1" ]]; then
  # Vendor mode: enumerate files directly. Vendor content is not tracked by
  # AGG_WT's git (it's a submodule), so `git ls-files` won't see it. We must
  # also exclude any nested .git directory (the vendor submodule's own meta).
  find "${PKG_PATH}" -mindepth 1 -maxdepth 5 -type f -not -path '*/.git/*' \
    | sed "s#^${PKG_PATH}/##" \
    > "${LIST_REL}"
else
  git -C "${DEV_ROOT}" ls-files -c -o --exclude-standard -- "${PKG_DIR}" >"${LIST_RAW}"
  [[ -s "${LIST_RAW}" ]] || die "No publishable files found under ${PKG_DIR}."
  sed "s#^${PKG_DIR}/##" "${LIST_RAW}" >"${LIST_REL}"
fi
[[ -s "${LIST_REL}" ]] || die "No publishable files found under ${PKG_PATH}."
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
if [[ "${DRY_RUN}" == "1" ]]; then
  log "DRY RUN plan:"
  if [[ "${VENDOR_MODE}" == "1" ]]; then
    echo "  - Vendor mode: would ensure submodule ${VENDOR_REL} (https://github.com/${VENDOR_OWNER}/${VENDOR_REPO}.git)" >&2
    echo "  - Would read files from ${PKG_PATH}" >&2
    echo "  - Files to publish: $(wc -l <"${LIST_FINAL}")" >&2
    if [[ "${ONLY_SKILL_BRANCH}" != "1" ]]; then
      echo "  - Would write/annotate ${AGG_SKILL_DIR_REL}/README.md with source URL" >&2
    fi
  else
    echo "  - Files to publish: $(wc -l <"${LIST_FINAL}")" >&2
  fi
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
# Step 1: update main IN-PLACE (no worktree add -> excludes your error)
# ==============================================================================
if [[ "${ONLY_SKILL_BRANCH}" != "1" ]]; then
  mkdir -p "${AGG_WT}/${AGG_SKILL_DIR_REL}"
  clear_dir_contents "${AGG_WT}/${AGG_SKILL_DIR_REL}"
  tar -xf "${TARFILE}" -C "${AGG_WT}/${AGG_SKILL_DIR_REL}"
  if [[ "${VENDOR_MODE}" == "1" ]]; then
    # Compose provenance README for the published skill on AGG main.
    # The source URL is the original --vendor-url the user supplied, so the
    # rendered URL exactly mirrors what they wrote (including /tree/<branch>).
    vendor_source_url="${VENDOR_URL}"
    readme_target="${AGG_WT}/${AGG_SKILL_DIR_REL}/README.md"
    prefix_line="> 来源: ${vendor_source_url}"
    if [[ -f "${readme_target}" ]]; then
      # Prepend blockquote line in-place (idempotent: avoid stacking on re-run).
      if ! head -n 1 "${readme_target}" | grep -qF "$(printf '%s' "${prefix_line}" | sed 's/^> //')"; then
        tmp_pre="${readme_target}.prepend"
        {
          printf '%s\n\n' "${prefix_line}"
          cat "${readme_target}"
        } > "${tmp_pre}"
        mv "${tmp_pre}" "${readme_target}"
      fi
    else
      {
        printf '# %s\n\n' "${SKILL}"
        printf '来源: %s\n\n' "${vendor_source_url}"
        printf '本目录内容通过 git submodule %s 同步。\n' "${VENDOR_REL}"
      } > "${readme_target}"
    fi
  fi

  git -C "${AGG_WT}" add "${AGG_SKILL_DIR_REL}"
  if ! git -C "${AGG_WT}" diff --cached --quiet; then
    git -C "${AGG_WT}" commit -m "publish(${SKILL}): update ${AGG_SKILL_DIR_REL}"
    git -C "${AGG_WT}" push origin "${AGG_MAIN}"
    # Vendor mode: track the source URL so the aggregator README can list it.
    if [[ "${VENDOR_MODE}" == "1" ]]; then
      record_vendor_source "${AGG_WT}" "${SKILL}" "${VENDOR_URL}"
    fi
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

log "Done publishing ${SKILL}."

done  # end for PKG_DIR

# ==============================================================================
# Sync README once after all packages are published
# ==============================================================================
if [[ "${ONLY_SKILL_BRANCH}" != "1" && "${DRY_RUN}" != "1" ]]; then
  sync_readme_skills_table "${AGG_WT}" "${AGG_SKILLS_DIR}"
fi

log "All packages published. Aggregator local & remote aligned."

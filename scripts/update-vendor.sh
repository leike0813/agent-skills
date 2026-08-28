#!/usr/bin/env bash
# update-vendor.sh — bulk re-sync every entry in .vendor-audit.jsonl.
#
# Reads the audit file written by publish.sh's vendor mode and re-publishes
# each entry in one pass. Same temp-clone + audit semantics as publish.sh
# --vendor-url, but applied to the full audit set.
#
# This script is intentionally self-contained: it does NOT source publish.sh.
# The four shared functions (die / log / need_cmd, normalize_git_url,
# parse_github_url, sync_readme_skills_table and its record_vendor_audit
# helper) are copied verbatim from publish.sh. The audit file is the
# contract between the two scripts.
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
need_cmd jq

DRY_RUN=0

# -----------------------------
# defaults
# -----------------------------
AGG_URL_DEFAULT="https://github.com/leike0813/agent-skills.git"
AGG_WT_DEFAULT="/home/joshua/Workspace/Code/Skill/agent-skills/"

AGG_WT="${AGG_WT:-${AGG_WT_DEFAULT}}"
AGG_URL="${AGG_URL:-${AGG_URL_DEFAULT}}"
AGG_MAIN="${AGG_MAIN:-main}"
AGG_SKILLS_DIR="${AGG_SKILLS_DIR:-skills}"
SKILL_BRANCH_PREFIX="${SKILL_BRANCH_PREFIX:-skill/}"

ONLY_MAIN=0
ONLY_SKILL_BRANCH=0

usage() {
  cat <<'EOF'
Usage:
  update-vendor.sh [options]

Re-publishes every entry in AGG_WT/.vendor-audit.jsonl using the same
temp-clone + JSONL-audit semantics as publish.sh --vendor-url. This is
the bulk re-sync counterpart to single-skill vendor publishes.

Options:
  --agg-wt <path>           Local agent-skills worktree (default: AGG_WT_DEFAULT in script)
  --agg-url <url>           Expected origin URL for agent-skills (default: built-in)
  --agg-main <branch>       Aggregator main branch (default: main)
  --agg-skills-dir <dir>    Aggregator skills dir (default: skills)
  --skill-branch-prefix <p> Prefix for single-skill branch (default: skill/)
  --only-main               Only update <AGG_MAIN>:skills/<skill>
  --only-skill-branch       Only update skill/<skill> branch
  --dry-run                 Print what would happen; no changes.
  -h | --help               Show this help.

Inputs are the audit file plus flags. There is no --pkg-dir / --vendor-url
/ --skill / --config; the script's contract is the audit file written by
publish.sh.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
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

# -----------------------------
# shared helpers (copied verbatim from publish.sh)
# -----------------------------
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

# record_vendor_audit <agg_wt> <skill> <url> <owner> <repo> <branch> <subpath> <commit> [fetched_at]
# Upserts the audit entry for <skill> in <agg_wt>/.vendor-audit.jsonl.
# File format: one JSON object per line; existing entries for the same skill
# are removed before appending so the file contains exactly one line per skill.
# Used by sync_readme_skills_table to render the Vendor Sources section in
# the aggregator README.
record_vendor_audit() {
  local agg_wt="$1" skill="$2" url="$3" owner="$4" repo="$5" branch="$6" subpath="$7" commit="$8"
  local fetched_at="${9:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
  [[ -n "${skill}" && -n "${url}" ]] || return 0
  local file="${agg_wt}/.vendor-audit.jsonl"
  local tmp="${file}.new"
  if [[ -f "${file}" ]]; then
    # keep every line whose "skill" field is not ${skill}
    awk -v s="${skill}" 'BEGIN{p = "\"skill\":\"" s "\""} index($0, p) == 0 {print}' "${file}" > "${tmp}" || true
  else
    : > "${tmp}"
  fi
  # build JSON safely: jq is required by this script, so always delegate.
  local entry
  entry="$(jq -nc --arg skill "${skill}" --arg url "${url}" \
    --arg owner "${owner}" --arg repo "${repo}" --arg branch "${branch}" \
    --arg subpath "${subpath}" --arg commit "${commit}" --arg fetched_at "${fetched_at}" \
    '{skill:$skill,url:$url,owner:$owner,repo:$repo,branch:$branch,subpath:$subpath,commit:$commit,fetched_at:$fetched_at}')"
  printf '%s\n' "${entry}" >> "${tmp}"
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
  local audit_file="${agg_wt}/.vendor-audit.jsonl"

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

    # Render the Vendor Sources section if .vendor-audit.jsonl has entries.
    # Audit lines are JSON objects with at least {skill,url}; only those
    # skills still present in the table are rendered, so removing a skill
    # drops its line on the next sync.
    if [[ -s "${audit_file}" ]]; then
      echo ""
      echo "## Vendor Sources"
      echo ""
      echo "以下 skill 通过第三方仓库发布,内容由对应仓库同步而来。"
      echo ""
      # Render only entries whose skill is still in the current table.
      # jq is mandatory in this script.
      while IFS=$'\t' read -r src_skill src_url; do
        [[ -z "${src_skill}" || -z "${src_url}" ]] && continue
        local match=0
        for s in "${sorted[@]}"; do
          [[ "${s}" == "${src_skill}" ]] && match=1 && break
        done
        [[ "${match}" == "1" ]] || continue
        echo "- \`${src_skill}\` — <${src_url}>"
      done < <(jq -r '"\(.skill)\t\(.url)"' "${audit_file}")
    fi
  } > "$tmpfile"

  if [[ -f "$readme" ]]; then
    cp "$readme" "${readme}.bak"
  fi
  cp "$tmpfile" "$readme"

  git -C "${agg_wt}" add "README.md"
  # .vendor-audit.jsonl may be newly created by record_vendor_audit above;
  # stage it explicitly so the next sync reflects the latest mapping.
  if [[ -f "${audit_file}" ]]; then
    git -C "${agg_wt}" add "${audit_file}"
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
# resolve and validate AGG_WT
# -----------------------------
[[ -d "${AGG_WT}" ]] || die "Aggregator worktree not found: ${AGG_WT}"
[[ -d "${AGG_WT}/.git" || -f "${AGG_WT}/.git" ]] || die "Aggregator path is not a git worktree: ${AGG_WT}"

LOCAL_ORIGIN="$(git -C "${AGG_WT}" remote get-url origin 2>/dev/null || true)"
[[ -n "${LOCAL_ORIGIN}" ]] || die "Aggregator has no origin remote: ${AGG_WT}"

if [[ "$(normalize_git_url "${AGG_URL}")" != "$(normalize_git_url "${LOCAL_ORIGIN}")" ]]; then
  die "AGG_URL does not match local origin after normalization.
  AGG_URL:      ${AGG_URL} -> $(normalize_git_url "${AGG_URL}")
  local origin: ${LOCAL_ORIGIN} -> $(normalize_git_url "${LOCAL_ORIGIN}")"
fi

[[ -z "$(git -C "${AGG_WT}" status --porcelain)" ]] || die "Aggregator worktree has local changes: ${AGG_WT}"

git -C "${AGG_WT}" fetch origin --prune

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

# -----------------------------
# read audit file
# -----------------------------
AUDIT_FILE="${AGG_WT}/.vendor-audit.jsonl"
if [[ ! -s "${AUDIT_FILE}" ]]; then
  die "No audit entries in ${AUDIT_FILE}; nothing to update."
fi

ENTRY_COUNT="$(wc -l < "${AUDIT_FILE}" | tr -d '[:space:]')"
log "Found ${ENTRY_COUNT} audit entr(ies) in ${AUDIT_FILE}."

# -----------------------------
# iterate per audit entry
# -----------------------------
TMPDIR_BASE="$(mktemp -d)"
trap 'rm -rf "${TMPDIR_BASE}"' EXIT
export TMPDIR="${TMPDIR_BASE}"

while IFS=$'\t' read -r ENTRY_SKILL ENTRY_URL ENTRY_COMMIT; do
  [[ -z "${ENTRY_SKILL}" || -z "${ENTRY_URL}" ]] && continue

  log "Updating ${ENTRY_SKILL} from ${ENTRY_URL} (audit commit=${ENTRY_COMMIT})"

  # parse the URL -> owner / repo / branch / subpath
  IFS=$'\t' read -r VENDOR_OWNER VENDOR_REPO VENDOR_BRANCH VENDOR_SUBPATH < <(parse_github_url "${ENTRY_URL}")
  VENDOR_URL="${ENTRY_URL}"
  export VENDOR_OWNER VENDOR_REPO VENDOR_BRANCH VENDOR_SUBPATH VENDOR_URL

  # fresh WORK_TMP per iteration; the trap fires when reassigned.
  WORK_TMP="$(mktemp -d)"
  trap 'rm -rf "${WORK_TMP}" "${TMPDIR_BASE}"' EXIT

  if ! git clone --depth 1 --branch "${VENDOR_BRANCH}" "https://github.com/${VENDOR_OWNER}/${VENDOR_REPO}.git" "${WORK_TMP}/repo" >/dev/null 2>&1; then
    log "WARN: git clone failed for ${ENTRY_SKILL} (https://github.com/${VENDOR_OWNER}/${VENDOR_REPO}.git @ ${VENDOR_BRANCH}); skipping."
    rm -rf "${WORK_TMP}"
    trap 'rm -rf "${TMPDIR_BASE}"' EXIT
    continue
  fi

  NEW_COMMIT="$(git -C "${WORK_TMP}/repo" rev-parse HEAD)"
  export NEW_COMMIT

  # empty commit in audit means "never published" -> run a full publish.
  if [[ -n "${ENTRY_COMMIT}" && "${NEW_COMMIT}" == "${ENTRY_COMMIT}" ]]; then
    log "${ENTRY_SKILL} up-to-date (commit ${NEW_COMMIT}); skipping."
    rm -rf "${WORK_TMP}"
    trap 'rm -rf "${TMPDIR_BASE}"' EXIT
    continue
  fi

  if [[ -z "${VENDOR_SUBPATH}" ]]; then
    PKG_PATH="${WORK_TMP}/repo"
  else
    PKG_PATH="${WORK_TMP}/repo/${VENDOR_SUBPATH}"
  fi
  if [[ ! -d "${PKG_PATH}" ]]; then
    log "WARN: vendor subpath not found for ${ENTRY_SKILL}: ${PKG_PATH}; skipping."
    rm -rf "${WORK_TMP}"
    trap 'rm -rf "${TMPDIR_BASE}"' EXIT
    continue
  fi
  if [[ ! -f "${PKG_PATH}/SKILL.md" ]]; then
    log "WARN: SKILL.md not found under vendor path for ${ENTRY_SKILL}: ${PKG_PATH}; skipping."
    rm -rf "${WORK_TMP}"
    trap 'rm -rf "${TMPDIR_BASE}"' EXIT
    continue
  fi

  SKILL="${ENTRY_SKILL}"
  PKG_DIR="${VENDOR_SUBPATH:-}"
  SKILL_BRANCH="${SKILL_BRANCH_PREFIX}${SKILL}"
  AGG_SKILL_DIR_REL="${AGG_SKILLS_DIR}/${SKILL}"
  VENDOR_COMMIT="${NEW_COMMIT}"
  export SKILL PKG_DIR SKILL_BRANCH AGG_SKILL_DIR_REL VENDOR_COMMIT

  log "SKILL          = ${SKILL}"
  log "PKG_PATH       = ${PKG_PATH}"
  log "AGG_SKILL_DIR  = ${AGG_WT}/${AGG_SKILL_DIR_REL}"
  log "SKILL_BRANCH   = ${SKILL_BRANCH}"
  log "NEW_COMMIT     = ${NEW_COMMIT}"

  # refuse if target path is a submodule (e.g. legacy state from before the
  # temp-clone migration).
  if git -C "${AGG_WT}" ls-files --stage -- "${AGG_SKILL_DIR_REL}" | awk '{print $1}' | grep -q "^160000$"; then
    log "WARN: ${AGG_SKILL_DIR_REL} is a submodule (gitlink); convert it to a normal directory first. Skipping ${ENTRY_SKILL}."
    rm -rf "${WORK_TMP}"
    trap 'rm -rf "${TMPDIR_BASE}"' EXIT
    continue
  fi

  # strict for skill branch if local exists
  if git -C "${AGG_WT}" show-ref --verify --quiet "refs/heads/${SKILL_BRANCH}"; then
    if git -C "${AGG_WT}" show-ref --verify --quiet "refs/remotes/origin/${SKILL_BRANCH}"; then
      lsb="$(git -C "${AGG_WT}" rev-parse "${SKILL_BRANCH}")"
      rsb="$(git -C "${AGG_WT}" rev-parse "origin/${SKILL_BRANCH}")"
      if [[ "${lsb}" != "${rsb}" ]]; then
        log "WARN: Local ${SKILL_BRANCH} != origin/${SKILL_BRANCH}. Align first then retry. Skipping ${ENTRY_SKILL}."
        rm -rf "${WORK_TMP}"
        trap 'rm -rf "${TMPDIR_BASE}"' EXIT
        continue
      fi
    else
      log "WARN: Local ${SKILL_BRANCH} exists but origin/${SKILL_BRANCH} does not. Push/delete it first. Skipping ${ENTRY_SKILL}."
      rm -rf "${WORK_TMP}"
      trap 'rm -rf "${TMPDIR_BASE}"' EXIT
      continue
    fi
  fi

  # ==============================================================================
  # Build publish file list (honors .gitignore exclusion only inside the clone)
  # ==============================================================================
  TMPDIR_PKG="$(mktemp -d)"
  LIST_RAW="${TMPDIR_PKG}/files_raw.txt"
  LIST_REL="${TMPDIR_PKG}/files_rel.txt"
  LIST_FINAL="${TMPDIR_PKG}/files_final.txt"
  TARFILE="${TMPDIR_PKG}/pkg.tar"

  find "${PKG_PATH}" -mindepth 1 -maxdepth 5 -type f -not -path '*/.git/*' \
    | sed "s#^${PKG_PATH}/##" \
    > "${LIST_REL}"
  [[ -s "${LIST_REL}" ]] || { log "WARN: no publishable files under ${PKG_PATH}; skipping ${ENTRY_SKILL}."; rm -rf "${WORK_TMP}" "${TMPDIR_PKG}"; trap 'rm -rf "${TMPDIR_BASE}"' EXIT; continue; }
  cp "${LIST_REL}" "${LIST_FINAL}"
  [[ -s "${LIST_FINAL}" ]] || { log "WARN: empty file list after filtering; skipping ${ENTRY_SKILL}."; rm -rf "${WORK_TMP}" "${TMPDIR_PKG}"; trap 'rm -rf "${TMPDIR_BASE}"' EXIT; continue; }

  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "  - [${ENTRY_SKILL}] would clone https://github.com/${VENDOR_OWNER}/${VENDOR_REPO}.git (branch ${VENDOR_BRANCH}) into temp" >&2
    echo "  - [${ENTRY_SKILL}] NEW_COMMIT=${NEW_COMMIT} (audit commit was ${ENTRY_COMMIT:-<empty>})" >&2
    echo "  - [${ENTRY_SKILL}] files to publish: $(wc -l <"${LIST_FINAL}")" >&2
    if [[ "${ONLY_SKILL_BRANCH}" != "1" ]]; then
      echo "  - [${ENTRY_SKILL}] would update ${AGG_MAIN}:${AGG_SKILL_DIR_REL} in-place in AGG_WT and push origin/${AGG_MAIN}" >&2
    fi
    if [[ "${ONLY_MAIN}" != "1" ]]; then
      echo "  - [${ENTRY_SKILL}] would create/update ${SKILL_BRANCH} via temp worktree and push origin/${SKILL_BRANCH}" >&2
    fi
    rm -rf "${WORK_TMP}" "${TMPDIR_PKG}"
    trap 'rm -rf "${TMPDIR_BASE}"' EXIT
    continue
  fi

  (cd "${PKG_PATH}" && tar -cf "${TARFILE}" -T "${LIST_FINAL}")

  # ==============================================================================
  # Step 1: update main IN-PLACE
  # ==============================================================================
  if [[ "${ONLY_SKILL_BRANCH}" != "1" ]]; then
    mkdir -p "${AGG_WT}/${AGG_SKILL_DIR_REL}"
    clear_dir_contents "${AGG_WT}/${AGG_SKILL_DIR_REL}"
    tar -xf "${TARFILE}" -C "${AGG_WT}/${AGG_SKILL_DIR_REL}"

    vendor_source_url="${VENDOR_URL}"
    readme_target="${AGG_WT}/${AGG_SKILL_DIR_REL}/README.md"
    prefix_line="> 来源: ${vendor_source_url}"
    if [[ -f "${readme_target}" ]]; then
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
        printf 'Upstream commit: %s\n' "${VENDOR_COMMIT}"
      } > "${readme_target}"
    fi

    git -C "${AGG_WT}" add "${AGG_SKILL_DIR_REL}"
    if ! git -C "${AGG_WT}" diff --cached --quiet; then
      git -C "${AGG_WT}" commit -m "publish(${SKILL}): update ${AGG_SKILL_DIR_REL}"
      git -C "${AGG_WT}" push origin "${AGG_MAIN}"
      record_vendor_audit "${AGG_WT}" "${SKILL}" "${VENDOR_URL}" \
        "${VENDOR_OWNER}" "${VENDOR_REPO}" "${VENDOR_BRANCH}" "${VENDOR_SUBPATH}" \
        "${VENDOR_COMMIT}"
    else
      log "No changes detected for ${AGG_MAIN}:${AGG_SKILL_DIR_REL}"
    fi
  fi

  # ==============================================================================
  # Step 2: update/create skill branch via TEMP worktree
  # ==============================================================================
  if [[ "${ONLY_MAIN}" != "1" ]]; then
    git -C "${AGG_WT}" fetch origin --prune

    SKILL_WT="${WORK_TMP}/agg-skill-wt"

    if git -C "${AGG_WT}" show-ref --verify --quiet "refs/remotes/origin/${SKILL_BRANCH}" &&
      ! git -C "${AGG_WT}" show-ref --verify --quiet "refs/heads/${SKILL_BRANCH}"; then
      git -C "${AGG_WT}" branch --track "${SKILL_BRANCH}" "origin/${SKILL_BRANCH}"
    fi

    if git -C "${AGG_WT}" show-ref --verify --quiet "refs/heads/${SKILL_BRANCH}"; then
      git -C "${AGG_WT}" worktree add "${SKILL_WT}" "${SKILL_BRANCH}"
    else
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
  # Post-check
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

  log "Done updating ${ENTRY_SKILL} (commit ${NEW_COMMIT})."

  rm -rf "${WORK_TMP}" "${TMPDIR_PKG}"
  trap 'rm -rf "${TMPDIR_BASE}"' EXIT

done < <(jq -rc 'select(.skill and .url) | [.skill, .url, (.commit // "")] | @tsv' "${AUDIT_FILE}")

# ==============================================================================
# Sync README once after all entries processed
# ==============================================================================
if [[ "${ONLY_SKILL_BRANCH}" != "1" && "${DRY_RUN}" != "1" ]]; then
  sync_readme_skills_table "${AGG_WT}" "${AGG_SKILLS_DIR}"
fi

log "All vendor entries processed. Aggregator local & remote aligned."

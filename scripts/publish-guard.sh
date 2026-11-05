#!/usr/bin/env bash
# Shared by both publication entrypoints; all candidate objects stay in a temporary repository.
validate_reviewed_targets() {
  local wt="$1" entry ref sha tip
  shift
  for entry in "$@"; do
    ref="${entry%%=*}"; sha="${entry#*=}"
    if [[ "$entry" != *=* || "$ref" != origin/* || ! "$sha" =~ ^([0-9a-f]{40}|[0-9a-f]{64})$ ]] ||
      ! git -C "$wt" show-ref --verify --quiet "refs/remotes/$ref"; then
      echo "ERROR: invalid --reviewed-target: $entry (requires existing origin ref=full commit SHA)" >&2
      return 1
    fi
    tip="$(git -C "$wt" rev-parse "$ref^{commit}")" || return 1
    if [[ "$tip" != "$sha" ]]; then
      echo "ERROR: stale --reviewed-target $entry; $ref currently points to $tip" >&2
      return 1
    fi
  done
}

# Advance only an existing acknowledgement, and only to a commit this process just pushed.
advance_reviewed_target() {
  local ref="$1" sha="$2" i
  for i in "${!REVIEWED_TARGETS[@]}"; do
    [[ "${REVIEWED_TARGETS[i]%%=*}" != "$ref" ]] || REVIEWED_TARGETS[i]="$ref=$sha"
  done
}

check_publish_target_reconciled() (
  local wt="$1" ref="$2" subtree="$3" skill="$4" candidate="$5"
  shift 5
  local entry tip target baseline="" commit subject tree base_tree repo objects format path wanted actual history
  local -a reviewed=() paths=()
  # A Step 2 recheck consumes only acknowledgements belonging to this target.
  for entry in "$@"; do
    [[ "${entry%%=*}" != "$ref" ]] || reviewed+=("$entry")
  done
  validate_reviewed_targets "$wt" "${reviewed[@]}" || return 1
  git -C "$wt" show-ref --verify --quiet "refs/remotes/$ref" || return 0
  tip="$(git -C "$wt" rev-parse "$ref^{commit}")" || return 1
  for entry in "${reviewed[@]}"; do [[ "${entry#*=}" != "$tip" ]] || return 0; done
  if [[ "$subtree" == . ]]; then target="$tip^{tree}"; else target="$tip:$subtree"; fi
  tree="$(git -C "$wt" rev-parse --verify "$target" 2>/dev/null)" || return 0
  [[ "$(git -C "$wt" cat-file -t "$tree")" == tree ]] || {
    echo "ERROR: $ref $tip: $subtree is not a package tree; merge effective corrections into the development source first" >&2
    return 1
  }
  history="$(git -C "$wt" rev-list --first-parent "$tip")" || return 1
  while IFS= read -r commit; do
    subject="$(git -C "$wt" show -s --format=%s "$commit")" || return 1
    if [[ "$subtree" == . ]]; then
      [[ "$subject" == "sync($skill): publish package root" || "$subject" == "init($skill): create ${ref#origin/}" ]] || continue
      baseline="$commit^{tree}"
    else
      [[ "$subject" == "publish($skill): update $subtree" ]] || continue
      baseline="$commit:$subtree"
    fi
    break
  done <<<"$history"
  repo="$(mktemp -d "${TMPDIR:-/tmp}/publish-guard.XXXXXXXX")" || return 1
  trap 'rm -rf "$repo"' EXIT
  format="$(git -C "$wt" rev-parse --show-object-format)" || return 1
  git init -q --bare --object-format="$format" "$repo" || return 1
  objects="$(git -C "$wt" rev-parse --path-format=absolute --git-path objects)" || return 1
  export GIT_ALTERNATE_OBJECT_DIRECTORIES="$objects"
  git -C "$candidate" --git-dir="$repo" --work-tree="$candidate" -c core.autocrlf=false -c core.filemode=true add -f -A -- . || return 1
  actual="$(git --git-dir="$repo" write-tree)" || return 1
  if [[ -n "$baseline" ]] && base_tree="$(git -C "$wt" rev-parse --verify "$baseline" 2>/dev/null)"; then
    git -C "$wt" diff-tree --no-commit-id --no-renames -r --name-only -z "$base_tree" "$tree" >"$repo/changed-paths" || return 1
    while IFS= read -r -d '' path; do
      wanted="$(git --literal-pathspecs -C "$wt" ls-tree "$tree" -- "$path")" || return 1
      entry="$(git --literal-pathspecs --git-dir="$repo" ls-tree "$actual" -- "$path")" || return 1
      [[ "$wanted" == "$entry" ]] || paths+=("$path")
    done <"$repo/changed-paths"
  else
    git --git-dir="$repo" diff-tree --no-commit-id --no-renames -r --name-only -z "$tree" "$actual" >"$repo/changed-paths" || return 1
    while IFS= read -r -d '' path; do paths+=("$path"); done <"$repo/changed-paths"
  fi
  [[ ${#paths[@]} -gt 0 ]] || return 0
  echo "ERROR: unreconciled publication target $ref at $tip ($subtree)" >&2
  printf '  %q\n' "${paths[@]}" >&2
  echo "Merge effective corrections into the development source first; after explicit review use --reviewed-target $ref=$tip." >&2
  return 1
)

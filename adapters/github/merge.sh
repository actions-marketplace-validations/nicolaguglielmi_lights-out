#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# merge-github: merges PR <number> with a merge commit (merge_method
# "merge": the merge sha's second parent is the head CI judged, docs/adr/
# 0019 §5) and prints "<merge sha> <head sha>" on stdout. <head sha> is the
# head CI judged: it goes in the payload as `sha`, so GitHub merges only
# while the PR's head is still that commit and answers 409 otherwise
# (ticket 0010's rule, docs/adr/0043 §3). Idempotent (docs/adr/0019 §9): a
# PR GitHub already reports merged is not merged again, its recorded shas
# are printed and the exit is 0, provided the head it merged is <head
# sha>. Not a gate: one stderr line and exit 1 on failure.
set -eu
number=${1:?usage: merge.sh <number> <head sha>}
head=${2:?usage: merge.sh <number> <head sha>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# shellcheck source=adapters/github/env.sh
. "$here/adapters/github/env.sh"

pr=$(sh "$here/adapters/github/pr.sh" "$number") || exit 1
if [ "$(printf '%s' "$pr" | jq -r .merged)" != true ]; then
  tmp=$(mktemp)
  trap 'rm -f "$tmp"' EXIT
  payload=$(jq -cn --arg h "$head" '{merge_method: "merge", sha: $h}')
  code=$(github_api PUT "/repos/$GITHUB_REPO/pulls/$number/merge" "$tmp" "$payload")
  case "$code" in
    200) : ;;
    409) printf 'merge-github: PR #%s head moved since CI judged %s; not merged\n' "$number" "$head" >&2; exit 1 ;;
    # 405: not mergeable, or merged between pr.sh and here; pr.sh below tells which.
    405) : ;;
    *) printf 'merge-github: merge PR #%s returned %s: %s\n' "$number" "$code" "$(jq -r '.message // empty' "$tmp" 2>/dev/null)" >&2; exit 1 ;;
  esac
  pr=$(sh "$here/adapters/github/pr.sh" "$number") || exit 1
  [ "$(printf '%s' "$pr" | jq -r .merged)" = true ] \
    || { printf 'merge-github: PR #%s still not merged after merge returned %s: %s\n' "$number" "$code" "$(jq -r '.message // empty' "$tmp" 2>/dev/null)" >&2; exit 1; }
fi
merged_head=$(printf '%s' "$pr" | jq -r .head_sha)
[ "$merged_head" = "$head" ] \
  || { printf 'merge-github: PR #%s was merged at head %s, CI judged %s\n' "$number" "$merged_head" "$head" >&2; exit 1; }
printf '%s' "$pr" | jq -r '"\(.merge_sha) \(.head_sha)"'

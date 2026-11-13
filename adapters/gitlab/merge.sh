#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# merge-gitlab: merges merge request <number> with a merge commit (the
# project's default method: the merge's second parent is the head CI judged,
# docs/adr/0019 §5) and prints "<merge sha> <head sha>". The head goes in as
# `sha`, so GitLab merges only while the head is still that commit and answers
# 409 otherwise (docs/adr/0058 §8). GitLab computes mergeability after a
# push in the background: 405, 406 and 422 are asked again once a second, for
# at most READY_TIMEOUT seconds. Idempotent: a merge request already merged
# at <head sha> prints its shas and exits 0. Not a gate: one stderr line and
# exit 1 on failure.
set -eu
number=${1:?usage: merge.sh <number> <head sha>}
head=${2:?usage: merge.sh <number> <head sha>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/gitlab/env.sh
. "$here/env.sh"

pr=$(sh "$here/pr.sh" "$number") || exit 1
if [ "$(printf '%s' "$pr" | jq -r .merged)" != true ]; then
  [ "$(printf '%s' "$pr" | jq -r .head_sha)" = "$head" ] \
    || { printf 'merge-gitlab: !%s head moved since CI judged %s; not merged\n' "$number" "$head" >&2; exit 1; }
  i=0
  while :; do
    tmp=$(mktemp)
    code=$(api -o "$tmp" -w '%{http_code}' -X PUT -G "$GITLAB_PROJECT/merge_requests/$number/merge" \
      --data-urlencode "sha=$head" --data-urlencode should_remove_source_branch=false) || code=000
    body=$(cat "$tmp"); rm -f "$tmp"
    case "$code" in
      200) break ;;
      409) printf 'merge-gitlab: !%s head moved since CI judged %s; not merged\n' "$number" "$head" >&2; exit 1 ;;
      405 | 406 | 422)
        pr=$(sh "$here/pr.sh" "$number") || exit 1
        [ "$(printf '%s' "$pr" | jq -r .merged)" != true ] || break
        i=$((i + 1))
        [ "$i" -lt "${READY_TIMEOUT:-60}" ] \
          || { printf 'merge-gitlab: !%s still not mergeable after %ss: %s %s\n' "$number" "$i" "$code" "$body" >&2; exit 1; }
        sleep 1 ;;
      *) printf 'merge-gitlab: merge !%s returned %s: %s\n' "$number" "$code" "$body" >&2; exit 1 ;;
    esac
  done
  pr=$(sh "$here/pr.sh" "$number") || exit 1
  [ "$(printf '%s' "$pr" | jq -r .merged)" = true ] \
    || { printf 'merge-gitlab: !%s still not merged after the merge answered\n' "$number" >&2; exit 1; }
fi
merged_head=$(printf '%s' "$pr" | jq -r .head_sha)
[ "$merged_head" = "$head" ] \
  || { printf 'merge-gitlab: !%s was merged at head %s, CI judged %s\n' "$number" "$merged_head" "$head" >&2; exit 1; }
printf '%s' "$pr" | jq -r '"\(.merge_sha) \(.head_sha)"'

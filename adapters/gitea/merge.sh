#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# merge-gitea: merges PR <number> with a merge commit ({"Do":"merge"}: the
# merge sha's second parent is the head CI judged, docs/adr/0019 §5) and
# prints "<merge sha> <head sha>" on stdout. <head sha> is the head CI
# judged: it goes in the payload as head_commit_id, so Gitea merges only
# while the PR's head is still that commit (ticket 0010; verified in Gitea
# 1.27.3's source: an empty head_commit_id skips the check, a different
# one answers 409 "head out of date"). Idempotent by design (docs/adr/
# 0019 §2, §9 crash case): a PR the host already reports merged is not
# merged again — its recorded shas are printed and the exit is 0, instead
# of Gitea's 405, provided the head it merged is <head sha>. Not a gate:
# one stderr line and exit 1 on failure.
set -eu
number=${1:?usage: merge.sh <number> <head sha>}
head=${2:?usage: merge.sh <number> <head sha>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# shellcheck source=adapters/gitea/env.sh
. "$here/adapters/gitea/env.sh"

pr=$(sh "$here/adapters/gitea/pr.sh" "$number") || exit 1
if [ "$(printf '%s' "$pr" | jq -r .merged)" != true ]; then
  payload=$(jq -cn --arg h "$head" '{Do: "merge", head_commit_id: $h}')
  # 405 is "already merged" (a merge between pr.sh and here) or "not
  # mergeable yet": Gitea re-checks a PR's mergeability in a queue after
  # its base branch moves, and a merge onto a moved main (docs/adr/0056
  # §1) can arrive before the check. Asked again once a second while it
  # is neither, for at most READY_TIMEOUT seconds (the adapters' own wait).
  i=0
  while :; do
    code=$(curl -sS --connect-timeout 2 --max-time 30 -o /dev/null -w '%{http_code}' \
      -u "$GITEA_USER:$GITEA_PASSWORD" -H 'Content-Type: application/json' \
      -d "$payload" "$GITEA_API/repos/$GITEA_OWNER/$GITEA_REPO/pulls/$number/merge") || code=000
    case "$code" in
      200) break ;;
      405) pr=$(sh "$here/adapters/gitea/pr.sh" "$number") || exit 1
           [ "$(printf '%s' "$pr" | jq -r .merged)" != true ] || break
           i=$((i + 1)); [ "$i" -lt "${READY_TIMEOUT:-60}" ] || break
           sleep 1 ;;
      409) printf 'merge-gitea: PR #%s head moved since CI judged %s; not merged\n' "$number" "$head" >&2; exit 1 ;;
      *) printf 'merge-gitea: merge PR #%s returned %s\n' "$number" "$code" >&2; exit 1 ;;
    esac
  done
  pr=$(sh "$here/adapters/gitea/pr.sh" "$number") || exit 1
  [ "$(printf '%s' "$pr" | jq -r .merged)" = true ] \
    || { printf 'merge-gitea: PR #%s still not merged after merge returned %s\n' "$number" "$code" >&2; exit 1; }
fi
merged_head=$(printf '%s' "$pr" | jq -r .head_sha)
[ "$merged_head" = "$head" ] \
  || { printf 'merge-gitea: PR #%s was merged at head %s, CI judged %s\n' "$number" "$merged_head" "$head" >&2; exit 1; }
printf '%s' "$pr" | jq -r '"\(.merge_sha) \(.head_sha)"'

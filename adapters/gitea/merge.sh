#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# merge-gitea: merges PR <number> with a merge commit ({"Do":"merge"}: the
# merge sha's second parent is the head CI judged, docs/adr/0019 §5) and
# prints "<merge sha> <head sha>" on stdout. Idempotent by design (docs/
# adr/0019 §2, §9 crash case): a PR the host already reports merged is
# not merged again — its recorded shas are printed and the exit is 0,
# instead of Gitea's 405. Not a gate: one stderr line and exit 1 on
# failure.
set -eu
number=${1:?usage: merge.sh <number>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# shellcheck source=adapters/gitea/env.sh
. "$here/adapters/gitea/env.sh"

pr=$(sh "$here/adapters/gitea/pr.sh" "$number") || exit 1
if [ "$(printf '%s' "$pr" | jq -r .merged)" != true ]; then
  code=$(curl -sS --connect-timeout 2 --max-time 30 -o /dev/null -w '%{http_code}' \
    -u "$GITEA_USER:$GITEA_PASSWORD" -H 'Content-Type: application/json' \
    -d '{"Do":"merge"}' "$GITEA_API/repos/$GITEA_OWNER/$GITEA_REPO/pulls/$number/merge") || code=000
  # 405 "already merged": a merge that happened between pr.sh and here.
  case "$code" in 200|405) : ;; *) printf 'merge-gitea: merge PR #%s returned %s\n' "$number" "$code" >&2; exit 1 ;; esac
  pr=$(sh "$here/adapters/gitea/pr.sh" "$number") || exit 1
  [ "$(printf '%s' "$pr" | jq -r .merged)" = true ] \
    || { printf 'merge-gitea: PR #%s still not merged after merge returned %s\n' "$number" "$code" >&2; exit 1; }
fi
printf '%s' "$pr" | jq -r '"\(.merge_sha) \(.head_sha)"'

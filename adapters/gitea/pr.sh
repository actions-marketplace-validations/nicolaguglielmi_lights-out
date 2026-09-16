#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# pr-gitea: prints PR <number> as the code host sees it, one JSON object
# on stdout: {"number","state","merged","head_sha","merge_sha"} — the
# audit's cross-check (docs/adr/0019 §6, owner addition: an audit that
# reads only its own archive confirms itself). merge_sha is null until
# the PR is merged. Not a gate: one stderr line and exit 1 when the PR
# does not exist or the host did not answer.
set -eu
number=${1:?usage: pr.sh <number>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# shellcheck source=adapters/gitea/env.sh
. "$here/adapters/gitea/env.sh"

resp=$(curl -fsS --connect-timeout 2 --max-time 10 -u "$GITEA_USER:$GITEA_PASSWORD" \
    "$GITEA_API/repos/$GITEA_OWNER/$GITEA_REPO/pulls/$number") \
  || { printf 'pr-gitea: GET PR #%s failed (no such PR, or %s unreachable)\n' "$number" "$GITEA_URL" >&2; exit 1; }
printf '%s' "$resp" | jq -c '{number: .number, state: .state, merged: (.merged // false),
  head_sha: .head.sha, merge_sha: (if .merged then .merge_commit_sha else null end)}'

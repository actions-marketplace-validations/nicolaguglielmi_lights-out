#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# pr-github: prints PR <number> as GitHub sees it, one JSON object on
# stdout, the shape adapters/gitea/pr.sh prints: {"number","state",
# "merged","head_sha","merge_sha"} (docs/adr/0019 §6). merge_sha is null
# until the PR is merged: GitHub fills merge_commit_sha with a test merge
# before that (docs/adr/0043 §3). Not a gate: one stderr line and exit 1
# when the PR does not exist or GitHub did not answer.
set -eu
number=${1:?usage: pr.sh <number>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# shellcheck source=adapters/github/env.sh
. "$here/adapters/github/env.sh"

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
code=$(github_api GET "/repos/$GITHUB_REPO/pulls/$number" "$tmp")
[ "$code" = 200 ] \
  || { printf 'pr-github: GET PR #%s on %s returned %s\n' "$number" "$GITHUB_REPO" "$code" >&2; exit 1; }
jq -c '{number: .number, state: .state, merged: (.merged // false),
  head_sha: .head.sha, merge_sha: (if .merged then .merge_commit_sha else null end)}' "$tmp"

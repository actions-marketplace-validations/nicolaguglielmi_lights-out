#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# pr-gitlab: merge request <number> (its iid) as GitLab sees it, one JSON
# object: {"number","state","merged","head_sha","merge_sha"} (docs/adr/0019
# §6). opened is open; merged and closed are closed, as Gitea and GitHub
# report a merged PR. merge_sha is null until merged. Not a gate.
set -eu
number=${1:?usage: pr.sh <number>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/gitlab/env.sh
. "$here/env.sh"
resp=$(api -f "$GITLAB_PROJECT/merge_requests/$number") \
  || { printf 'pr-gitlab: GET merge request !%s failed (no such merge request, or %s unreachable)\n' "$number" "$GITLAB_URL" >&2; exit 1; }
printf '%s' "$resp" | jq -c '{number: .iid, state: (if .state == "opened" then "open" else "closed" end),
  merged: (.state == "merged"), head_sha: .sha,
  merge_sha: (if .state == "merged" then .merge_commit_sha else null end)}'

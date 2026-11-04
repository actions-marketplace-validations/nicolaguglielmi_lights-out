#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# status-github: posts a commit status on <sha> (docs/adr/0019 §4, 0043
# §3): <state> is one of pending, success, failure, error; <context> names
# the check ("gates"); <description> is the gate's own one-line verdict,
# cut to the 140 characters GitHub accepts (longer is a 422). Statuses
# append, as on Gitea. Not a gate: silent on success, one stderr line and
# exit 1 on failure.
set -eu
sha=${1:?usage: status.sh <sha> <state> <context> <description>}
state=${2:?usage: status.sh <sha> <state> <context> <description>}
context=${3:?usage: status.sh <sha> <state> <context> <description>}
description=${4:?usage: status.sh <sha> <state> <context> <description>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# shellcheck source=adapters/github/env.sh
. "$here/adapters/github/env.sh"

payload=$(jq -cn --arg s "$state" --arg c "$context" --arg d "$description" \
  '{state: $s, context: $c, description: (if ($d | length) > 140 then $d[0:139] + "…" else $d end)}')
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
code=$(github_api POST "/repos/$GITHUB_REPO/statuses/$sha" "$tmp" "$payload")
[ "$code" = 201 ] \
  || { printf 'status-github: POST status %s on %s returned %s: %s\n' "$state" "$sha" "$code" "$(jq -r '.message // empty' "$tmp" 2>/dev/null)" >&2; exit 1; }

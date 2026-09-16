#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# status-gitea: posts a commit status on <sha> so the PR page shows the
# check (docs/adr/0019 §4): <state> is one of pending, success, failure,
# error; <context> names the check ("gates"); <description> is the gate's
# own one-line verdict. Statuses append, never replace, so a re-run is a
# second row, not a lie. Not a gate: silent on success, one stderr line
# and exit 1 on failure.
set -eu
sha=${1:?usage: status.sh <sha> <state> <context> <description>}
state=${2:?usage: status.sh <sha> <state> <context> <description>}
context=${3:?usage: status.sh <sha> <state> <context> <description>}
description=${4:?usage: status.sh <sha> <state> <context> <description>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# shellcheck source=adapters/gitea/env.sh
. "$here/adapters/gitea/env.sh"

payload=$(jq -cn --arg s "$state" --arg c "$context" --arg d "$description" \
  '{state: $s, context: $c, description: $d}')
curl -fsS -u "$GITEA_USER:$GITEA_PASSWORD" -H 'Content-Type: application/json' \
  -d "$payload" "$GITEA_API/repos/$GITEA_OWNER/$GITEA_REPO/statuses/$sha" >/dev/null \
  || { printf 'status-gitea: POST status %s on %s failed\n' "$state" "$sha" >&2; exit 1; }

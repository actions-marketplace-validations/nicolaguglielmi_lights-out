#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# open-pr-gitea: opens a PR from <branch> onto main, title and body from
# the harness's pr.json (docs/adr/0017 §1, §4). Idempotent: an already-open
# PR from this branch is reused, not duplicated — the caller may retry the
# same ticket. Prints "<number> <url>" on stdout. Not a gate.
set -eu
branch=${1:?usage: open-pr.sh <branch> <pr.json>}
pr_json=${2:?usage: open-pr.sh <branch> <pr.json>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# shellcheck source=adapters/gitea/env.sh
. "$here/adapters/gitea/env.sh"

[ -s "$pr_json" ] || { printf 'open-pr-gitea: %s is missing or empty\n' "$pr_json" >&2; exit 1; }
title=$(jq -r '.title // ""' "$pr_json")
body=$(jq -r '.body // ""' "$pr_json")
[ -n "$title" ] || { printf 'open-pr-gitea: %s has no title\n' "$pr_json" >&2; exit 1; }

existing=$(curl -fsS -u "$GITEA_USER:$GITEA_PASSWORD" \
    "$GITEA_API/repos/$GITEA_OWNER/$GITEA_REPO/pulls?state=open&limit=50" \
  | jq -r --arg h "$branch" '.[] | select(.head.ref == $h) | .number' | head -n1) || existing=""

if [ -n "$existing" ]; then
  number=$existing
else
  payload=$(jq -n --arg title "$title" --arg body "$body" --arg head "$branch" --arg base main \
    '{title: $title, body: $body, head: $head, base: $base}')
  resp=$(curl -fsS -u "$GITEA_USER:$GITEA_PASSWORD" -H 'Content-Type: application/json' \
      -d "$payload" "$GITEA_API/repos/$GITEA_OWNER/$GITEA_REPO/pulls") \
    || { printf 'open-pr-gitea: create PR failed\n' >&2; exit 1; }
  number=$(printf '%s' "$resp" | jq -r '.number // empty')
  [ -n "$number" ] || { printf 'open-pr-gitea: no PR number in response: %s\n' "$resp" >&2; exit 1; }
fi

printf '%s %s/%s/%s/pulls/%s\n' "$number" "$GITEA_URL" "$GITEA_OWNER" "$GITEA_REPO" "$number"

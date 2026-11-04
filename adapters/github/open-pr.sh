#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# open-pr-github: opens a PR from <branch> onto the repository's default
# branch, title and body from the harness's pr.json (docs/adr/0017 §1,
# 0043 §3): the default branch is what core/crew.sh cloned and based the
# work on. Idempotent: an already-open PR from this branch is reused, not
# duplicated. Prints "<number> <url>" on stdout. Not a gate.
set -eu
branch=${1:?usage: open-pr.sh <branch> <pr.json>}
pr_json=${2:?usage: open-pr.sh <branch> <pr.json>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# shellcheck source=adapters/github/env.sh
. "$here/adapters/github/env.sh"

[ -s "$pr_json" ] || { printf 'open-pr-github: %s is missing or empty\n' "$pr_json" >&2; exit 1; }
title=$(jq -r '.title // ""' "$pr_json")
body=$(jq -r '.body // ""' "$pr_json")
[ -n "$title" ] || { printf 'open-pr-github: %s has no title\n' "$pr_json" >&2; exit 1; }

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
owner=${GITHUB_REPO%%/*}
code=$(github_api GET "/repos/$GITHUB_REPO/pulls?state=open&head=$owner:$branch" "$tmp")
[ "$code" = 200 ] || { printf 'open-pr-github: list PRs on %s returned %s\n' "$GITHUB_REPO" "$code" >&2; exit 1; }
line=$(jq -r '.[0] | select(. != null) | "\(.number) \(.html_url)"' "$tmp")

if [ -z "$line" ]; then
  code=$(github_api GET "/repos/$GITHUB_REPO" "$tmp")
  [ "$code" = 200 ] || { printf 'open-pr-github: GET %s returned %s\n' "$GITHUB_REPO" "$code" >&2; exit 1; }
  base=$(jq -r '.default_branch // empty' "$tmp")
  [ -n "$base" ] || { printf 'open-pr-github: %s reports no default branch\n' "$GITHUB_REPO" >&2; exit 1; }
  payload=$(jq -cn --arg title "$title" --arg body "$body" --arg head "$branch" --arg base "$base" \
    '{title: $title, body: $body, head: $head, base: $base}')
  code=$(github_api POST "/repos/$GITHUB_REPO/pulls" "$tmp" "$payload")
  [ "$code" = 201 ] \
    || { printf 'open-pr-github: create PR %s → %s returned %s: %s\n' "$branch" "$base" "$code" "$(jq -c '.errors // .message // empty' "$tmp" 2>/dev/null)" >&2; exit 1; }
  line=$(jq -r '"\(.number) \(.html_url)"' "$tmp")
fi
case "$line" in
  [0-9]*' 'http*) printf '%s\n' "$line" ;;
  *) printf 'open-pr-github: no PR number in the response: %s\n' "$line" >&2; exit 1 ;;
esac

#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# await-gitea: polls the commit statuses on <sha> for <context> until it
# leaves pending, and prints the state it left at — success, failure or
# error (docs/adr/0025 §5). Statuses append, never replace
# (adapters/gitea/status.sh's own header), so this reads the newest entry
# for <context>, which Gitea's API returns first. Not a gate (docs/adr/
# 0012 §6): one stderr line and exit 1 on timeout, naming the context and
# the state it was stuck at.
#
# A status can also be posted by a Gitea Actions job of the same name
# (ci.yml's `image`; docs/adr/0025 §5, amended 2026-11-04). Such a job
# that ends without a final status would leave <context> pending until
# the timeout, so every 10th poll (a decision: one extra API call about
# every 10 s) this looks the job up by name and head sha and stops at
# once if it has completed. A skipped job never ran and is ignored: on
# Gitea the GitHub-only jobs, `gates` among them, are skipped on every
# commit, and the `gates` status comes from core, not from a job. On exit
# 1 the job's state and the tail of its log go to stderr, the evidence a
# hung `image` job left nowhere before.
set -eu
sha=${1:?usage: await.sh <sha> <context>}
context=${2:?usage: await.sh <sha> <context>}
: "${AWAIT_TIMEOUT:=300}"
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# shellcheck source=adapters/gitea/env.sh
. "$here/adapters/gitea/env.sh"

# The newest non-skipped job named <context> on <sha>, as one JSON line,
# or nothing.
job_of() {
  curl -fsS --connect-timeout 2 --max-time 15 -u "$GITEA_USER:$GITEA_PASSWORD" \
      "$GITEA_API/repos/$GITEA_OWNER/$GITEA_REPO/actions/jobs?limit=50" 2>/dev/null \
    | jq -c --arg s "$sha" --arg n "$context" \
      '[.jobs[]? | select(.head_sha == $s and .name == $n and .conclusion != "skipped")] | .[0] // empty' \
      2>/dev/null || true
}

# The job's state and the last 40 lines of its log, on stderr.
job_evidence() {
  job=$(job_of)
  if [ -z "$job" ]; then
    printf 'await-gitea: no Actions job named %s on %s\n' "$context" "$sha" >&2
    return 0
  fi
  printf 'await-gitea: job %s on %s: %s\n' "$context" "$sha" \
    "$(printf '%s' "$job" | jq -r '"status \(.status), conclusion \(.conclusion // "none"), started \(.started_at // "never"), completed \(.completed_at // "not yet")"')" >&2
  id=$(printf '%s' "$job" | jq -r '.id')
  curl -fsS --connect-timeout 2 --max-time 15 -u "$GITEA_USER:$GITEA_PASSWORD" \
      "$GITEA_API/repos/$GITEA_OWNER/$GITEA_REPO/actions/jobs/$id/logs" 2>/dev/null \
    | tail -n 40 | sed 's/^/  [job log] /' >&2 || true
}

i=0
state=""
while [ "$i" -lt "$AWAIT_TIMEOUT" ]; do
  state=$(curl -fsS --connect-timeout 2 --max-time 15 -u "$GITEA_USER:$GITEA_PASSWORD" \
      "$GITEA_API/repos/$GITEA_OWNER/$GITEA_REPO/commits/$sha/statuses" 2>/dev/null \
    | jq -r --arg c "$context" '[.[] | select(.context == $c)] | .[0].status // empty')
  case "$state" in
    success | failure | error)
      printf '%s\n' "$state"
      exit 0
      ;;
  esac
  i=$((i + 1))
  if [ $((i % 10)) -eq 0 ]; then
    job=$(job_of)
    if [ -n "$job" ] && [ "$(printf '%s' "$job" | jq -r '.status')" = completed ]; then
      printf 'await-gitea: %s on %s still %s, but its job has completed\n' "$context" "$sha" "${state:-pending}" >&2
      job_evidence
      exit 1
    fi
  fi
  sleep 1
done
printf 'await-gitea: %s on %s still %s after %ss\n' "$context" "$sha" "${state:-pending}" "$AWAIT_TIMEOUT" >&2
job_evidence
exit 1

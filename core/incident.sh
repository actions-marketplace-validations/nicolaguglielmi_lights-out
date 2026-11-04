#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-incident: a release record, a time window and a log excerpt in, one
# incident document out (docs/adr/0044 §1, §2). The document is what
# `./go postmortem` hands the ops-triage role: it holds everything the
# role may cite and nothing it could make up. Deterministic: the same
# inputs give the same bytes. Only TICKET=<id> touches anything beyond
# files (the state store, through the StateStore port); without it chain
# is null. Reuses ci/lib.sh's go/nogo.
#
#   ./go incident NAME=<slug> FROM=<utc> TO=<utc> [LOGS=<file>] [TICKET=<id>]
set -eu
name=incident
. ci/lib.sh

[ -n "${NAME:-}" ] || nogo "NAME not set; ./go incident NAME=<slug> FROM=<utc> TO=<utc>"
[ -n "${FROM:-}" ] || nogo "FROM not set; ./go incident NAME=<slug> FROM=<utc> TO=<utc>"
[ -n "${TO:-}" ] || nogo "TO not set; ./go incident NAME=<slug> FROM=<utc> TO=<utc>"
: "${RELEASE_RECORD:=.crew/release.json}"
: "${INCIDENT_OUT:=.crew/incidents}"

printf '%s' "$NAME" | grep -Eq '^[a-z0-9][a-z0-9-]*$' \
  || nogo "NAME \"$NAME\" is not a slug: lowercase letters, digits and dashes, not starting with a dash"
stamp='^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'
for t in "$FROM" "$TO"; do
  printf '%s' "$t" | grep -Eq "$stamp" || nogo "\"$t\" is not a UTC time like 2026-11-04T09:30:00Z"
done
# The fixed-width format sorts as time does; awk compares the strings.
awk -v a="$FROM" -v b="$TO" 'BEGIN { exit !(a <= b) }' || nogo "the window ends ($TO) before it starts ($FROM)"

[ -f "$RELEASE_RECORD" ] || nogo "no release record at $RELEASE_RECORD; run a release first (./go demo-rollback)"
record=$(jq -c . "$RELEASE_RECORD" 2>/dev/null) || nogo "$RELEASE_RECORD is not JSON"
verdict=$(printf '%s' "$record" | jq -r '.verdict // empty')
version=$(printf '%s' "$record" | jq -r '.version // empty')
case "$verdict" in
  held|rolled-back) ;;
  in-progress) nogo "release ${version:-?} is in-progress: a run died before its verdict (ticket 0008)" ;;
  *) nogo "$RELEASE_RECORD has no verdict of held or rolled-back (got \"$verdict\")" ;;
esac
[ -n "$version" ] || nogo "$RELEASE_RECORD names no version"

logs='[]'
if [ -n "${LOGS:-}" ]; then
  [ -f "$LOGS" ] || nogo "no log excerpt at $LOGS"
  logs=$(jq -Rs 'split("\n") | if .[-1] == "" then .[:-1] else . end' "$LOGS")
fi

chain=null
if [ -n "${TICKET:-}" ]; then
  : "${STATE_STORE:?STATE_STORE not set; run this via ./go, not directly}"
  doc=$(sh "adapters/$STATE_STORE/get.sh" tickets "$TICKET") \
    || nogo "no document for ticket $TICKET in $STATE_STORE; TICKET needs the plane"
  doc_version=$(printf '%s' "$doc" | jq -r '.release.version // empty')
  [ "$doc_version" = "$version" ] \
    || nogo "ticket $TICKET's document records release \"$doc_version\", the release record is \"$version\""
  chain=$(printf '%s' "$doc" | jq -c --arg t "$TICKET" '{ticket: $t, pr: .pr.number, merge: .merge.sha}')
  [ "$(printf '%s' "$chain" | jq '[.pr, .merge] | all(. != null)')" = true ] \
    || nogo "ticket $TICKET's document has no PR or merge to anchor to"
fi

mkdir -p "$INCIDENT_OUT"
out="$INCIDENT_OUT/$NAME.json"
printf '%s' "$record" | jq --arg name "$NAME" --arg from "$FROM" --arg to "$TO" \
  --argjson logs "$logs" --argjson chain "$chain" '
  . as $r
  | {kind: "incident", name: $name, window: {from: $from, to: $to}, release: $r,
     alerts: [$r.stages[]? | select(.verdict | startswith("GO") | not)
       | {headline: .verdict, version: $r.version, stable: $r.stable, stage: .}],
     logs: $logs, chain: $chain}' > "$out"
printf '[incident] %s: %s alert(s), %s log line(s), chain %s\n' "$NAME" \
  "$(jq '.alerts | length' "$out")" "$(jq '.logs | length' "$out")" "$(jq -c '.chain' "$out")" >&2
printf 'GO: incident — %s\n' "$out"

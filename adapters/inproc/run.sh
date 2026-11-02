#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# run-inproc: the Orchestrator at L0–L2 (docs/adr/0019 §3): pull one
# event, apply it with core/tower.sh, ack it, repeat; an empty pull ends
# the run. The bus carries the tower's own messages back to itself in one
# process — at L2 the same message starts a job, the machine does not
# change. A failed step is acked too (the state stayed where it was, the
# tower said which step and recorded the failed attempt) and makes this
# run exit 1 at the end; the loop does not stop early, so a second
# ticket's events are still applied. `./go resume TICKET=<id>` requests
# the failed step again (docs/adr/0034).
# Not a gate: stderr only, exit 0 when every step applied.
set -eu
: "${EVENT_BUS:?EVENT_BUS not set; run this via ./go, not directly}"

failed=0
applied=0
while :; do
  msg=$(sh "adapters/$EVENT_BUS/pull.sh") || exit 1
  [ -n "$msg" ] || break
  ackid=${msg%% *}
  data=${msg#* }
  ticket=$(printf '%s' "$data" | jq -r '.ticket // empty' 2>/dev/null) || ticket=""
  step=$(printf '%s' "$data" | jq -r '.step // empty' 2>/dev/null) || step=""
  if [ -z "$ticket" ] || [ -z "$step" ]; then
    printf '[inproc] dropping a message that is not {ticket, step}: %s\n' "$data" >&2
  elif ! sh core/tower.sh step "$ticket" "$step"; then
    failed=$((failed + 1))
  fi
  applied=$((applied + 1))
  sh "adapters/$EVENT_BUS/ack.sh" "$ackid" || exit 1
done
printf '[inproc] queue empty after %s event(s), %s failed\n' "$applied" "$failed" >&2
[ "$failed" -eq 0 ]

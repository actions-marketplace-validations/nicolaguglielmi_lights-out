#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-tower: the control plane's state machine (docs/adr/0019 §1, §2).
# Vendor-free: it only calls the STATE_STORE and EVENT_BUS adapter verbs
# the profile names, and the step scripts under $TOWER_STEPS. No
# Firestore, Pub/Sub or Gitea word appears below.
#
#   tower.sh open <ticket>          write the document at `opened`, publish `assign`
#   tower.sh step <ticket> <step>   apply one step: precondition, effect, write, publish next
#
# The document is plain JSON, one per ticket, id = ticket id. A step's
# precondition is the state it starts from; an event whose precondition
# is not the document's current state is dropped with one stderr line and
# exit 0 — that is the idempotency rule, and it covers both a duplicate
# event and a redelivery after a slow step. A step script gets the
# document on $DOC_FILE (plus TICKET, PR_NUMBER, BASE_SHA, HEAD_SHA for
# convenience) and prints a JSON object on stdout: at least {"state":
# "<next>"}, plus the fields it recorded; the tower merges it into the
# document. A step that exits non-zero leaves the document untouched and
# this script exits 1: no retries, no timeouts of the tower's own.
set -eu

: "${STATE_STORE:?STATE_STORE not set; run this via ./go, not directly}"
: "${EVENT_BUS:?EVENT_BUS not set; run this via ./go, not directly}"
: "${TOWER_STEPS:=core/steps}"
collection=tickets

cmd=${1:-}
ticket=${2:-}
[ -n "$cmd" ] && [ -n "$ticket" ] || { printf 'usage: tower.sh open <ticket> | step <ticket> <step>\n' >&2; exit 2; }

store() { sh "adapters/$STATE_STORE/$1.sh" "$collection" "$ticket"; }
publish() { sh "adapters/$EVENT_BUS/publish.sh" "$(jq -cn --arg t "$ticket" --arg s "$1" '{ticket: $t, step: $s}')"; }
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# The transition table. precondition STEP → the state the step starts
# from; next STATE → the step to request once the document is there, or
# nothing for a terminal state.
precondition() {
  case "$1" in
    assign) printf 'opened' ;;
    ci) printf 'pr-opened' ;;
    merge) printf 'ci-passed' ;;
    release) printf 'merged' ;;
    *) return 1 ;;
  esac
}
next() {
  case "$1" in
    pr-opened) printf 'ci' ;;
    ci-passed) printf 'merge' ;;
    merged) printf 'release' ;;
    *) : ;;
  esac
}

case "$cmd" in
  open)
    jq -cn --arg id "$ticket" --arg at "$(now)" \
      '{id: $id, state: "opened", history: [{step: "open", state: "opened", at: $at}]}' \
      | store put || { printf '[tower] %s: could not write the document\n' "$ticket" >&2; exit 1; }
    publish assign || { printf '[tower] %s: could not publish assign\n' "$ticket" >&2; exit 1; }
    printf '[tower] %s: opened, assign requested\n' "$ticket" >&2
    ;;
  step)
    step=${3:-}
    want=$(precondition "$step") || { printf '[tower] %s: unknown step "%s"\n' "$ticket" "$step" >&2; exit 2; }
    doc=$(store get) || { printf '[tower] %s: no document; open the ticket first\n' "$ticket" >&2; exit 1; }
    have=$(printf '%s' "$doc" | jq -r '.state // "none"')
    if [ "$have" != "$want" ]; then
      printf '[tower] %s: %s already applied (state %s), ignoring\n' "$ticket" "$step" "$have" >&2
      exit 0
    fi
    [ -f "$TOWER_STEPS/$step.sh" ] || { printf '[tower] %s: no %s/%s.sh\n' "$ticket" "$TOWER_STEPS" "$step" >&2; exit 1; }

    doc_file=$(mktemp)
    trap 'rm -f "$doc_file"' EXIT
    printf '%s\n' "$doc" > "$doc_file"
    printf '[tower] %s: %s (state %s)\n' "$ticket" "$step" "$have" >&2
    result=$(TICKET="$ticket" DOC_FILE="$doc_file" \
      PR_NUMBER="$(printf '%s' "$doc" | jq -r '.pr.number // empty')" \
      BASE_SHA="$(printf '%s' "$doc" | jq -r '.pr.base_sha // empty')" \
      HEAD_SHA="$(printf '%s' "$doc" | jq -r '.pr.head_sha // empty')" \
      sh "$TOWER_STEPS/$step.sh") \
      || { printf '[tower] %s: step %s failed; state stays %s\n' "$ticket" "$step" "$have" >&2; exit 1; }
    new_state=$(printf '%s' "$result" | jq -r '.state // empty' 2>/dev/null) || new_state=""
    [ -n "$new_state" ] || { printf '[tower] %s: step %s printed no state; state stays %s\n' "$ticket" "$step" "$have" >&2; exit 1; }

    printf '%s' "$doc" | jq -c --argjson r "$result" --arg step "$step" --arg at "$(now)" \
      '. * $r | .history += [{step: $step, state: $r.state, at: $at}]' \
      | store put || { printf '[tower] %s: could not write the document after %s\n' "$ticket" "$step" >&2; exit 1; }
    printf '[tower] %s: %s → %s\n' "$ticket" "$step" "$new_state" >&2

    following=$(next "$new_state")
    if [ -n "$following" ]; then
      publish "$following" || { printf '[tower] %s: could not publish %s\n' "$ticket" "$following" >&2; exit 1; }
    else
      printf '[tower] %s: %s is terminal, nothing requested\n' "$ticket" "$new_state" >&2
    fi
    ;;
  *) printf 'usage: tower.sh open <ticket> | step <ticket> <step>\n' >&2; exit 2 ;;
esac

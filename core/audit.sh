#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-audit: rebuilds the chain deploy → merge → PR → ticket → spec from
# the ticket's document (docs/adr/0019 §6) and prints it on stderr, one
# link per line; stdout is one line, GO: audit or NO-GO: audit — <what is
# missing or disagrees>. Two kinds of NO-GO: a missing link (a field the
# chain needs is absent, or the sha CI judged is not the sha that was
# merged), and a divergence between the record and the code host (owner
# addition, 2026-09-16: an audit that reads only its own archive confirms
# itself) — the document says merged and the host says the PR is open,
# or the host's merge sha is not the one recorded. Reads the store and
# the code host through PLANE_HOST; needs no engine socket.
#
# Not scanned by ci/contract.sh (core/, not ci/ gates/ verify/), but reuses
# ci/lib.sh's go/nogo for the same GO:/NO-GO: line shape.
set -eu
name=audit
. ci/lib.sh

: "${TICKET:?TICKET not set; run this via ./go audit TICKET=<id>}"
: "${STATE_STORE:?STATE_STORE not set; run this via ./go, not directly}"
: "${CODE_HOST:?CODE_HOST not set; run this via ./go, not directly}"

doc=$(sh "adapters/$STATE_STORE/get.sh" tickets "$TICKET") \
  || nogo "no document for ticket $TICKET in $STATE_STORE"
f() { printf '%s' "$doc" | jq -r "$1 // empty"; }

state=$(f .state)
[ -n "$state" ] || nogo "document for $TICKET has no state"

# The links, walked backwards from the deploy, each one required only
# once the document claims to have got that far.
missing=""
need() { [ -n "$(f "$1")" ] || missing="$missing $1"; }
case "$state" in
  rolled-back|held) need .release.verdict; need .release.version; need .merge.sha ;;
esac
case "$state" in
  merged|rolled-back|held) need .merge.sha; need .merge.head_sha; need .ci.verdict ;;
esac
case "$state" in
  ci-passed|review|ci-failed|merged|rolled-back|held) need .ci.verdict; need .ci.head_sha ;;
esac
# A reviewed merge with no review on the record is exactly what an audit
# exists to catch (docs/adr/0021 §9): "review" alone means the step has
# not run yet (nothing to need); any state past it must carry a verdict.
decision=$(f .ci.decision)
case "$state" in
  ci-passed|ci-failed|merged|rolled-back|held)
    [ "$decision" != review ] || { need .review.verdict; need .review.reason; } ;;
esac
case "$state" in
  opened) nogo "ticket $TICKET is only opened: no PR, no chain yet" ;;
  *) need .pr.number; need .pr.head_sha; need .spec.sha256; need .spec.title; need .task.harness ;;
esac
[ -z "$missing" ] || nogo "missing link(s) in the record:$missing"

pr_head=$(f .pr.head_sha); ci_head=$(f .ci.head_sha); merge_head=$(f .merge.head_sha)
[ -z "$ci_head" ] || [ "$ci_head" = "$pr_head" ] \
  || nogo "CI judged $ci_head but the PR was opened at $pr_head"
[ -z "$merge_head" ] || [ "$merge_head" = "$pr_head" ] \
  || nogo "merged head $merge_head is not the PR head $pr_head that CI judged"

# The code host's view, against the record.
host=$(sh "adapters/$CODE_HOST/pr.sh" "$(f .pr.number)") \
  || nogo "code host $CODE_HOST unreachable or PR #$(f .pr.number) unknown to it"
h() { printf '%s' "$host" | jq -r "$1 // empty"; }
host_merged=$(h .merged); host_state=$(h .state); host_head=$(h .head_sha); host_merge=$(h .merge_sha)
case "$state" in
  merged|rolled-back|held)
    [ "$host_merged" = true ] \
      || nogo "state store says $state, code host says PR #$(f .pr.number) is $host_state and not merged"
    [ "$host_merge" = "$(f .merge.sha)" ] \
      || nogo "state store records merge $(f .merge.sha), code host records $host_merge" ;;
  *)
    [ "$host_merged" != true ] \
      || nogo "state store says $state, code host says PR #$(f .pr.number) is already merged as $host_merge"
    [ "$host_head" = "$pr_head" ] \
      || nogo "state store records PR head $pr_head, code host has $host_head" ;;
esac

{
  case "$state" in
    rolled-back|held)
      printf 'deploy   %s %s — %s\n' "$(f .release.version)" "$state" "$(f .release.verdict)"
      printf '%s' "$doc" | jq -r '.release.numbers[]? | "         " + .'
      printf '         image: %s\n' "$(f .release.image)"
      printf '  ← merge  %s (code host agrees)\n' "$(f .merge.sha)" ;;
    merged)
      printf 'merge    %s (code host agrees), not released\n' "$(f .merge.sha)" ;;
    *)
      printf 'PR       stopped at %s\n' "$state" ;;
  esac
  printf '  ← PR     #%s %s (gates %s, risk %s, %s; head %s)\n' \
    "$(f .pr.number)" "$(f .pr.url)" "$(f .ci.verdict)" "$(f .ci.risk_level)" "$decision" "$pr_head"
  review_verdict=$(f .review.verdict)
  [ -z "$review_verdict" ] || printf '  ← review %s (%s): %s\n' "$(f .review.role)" "$review_verdict" "$(f .review.reason)"
  printf '  ← ticket %s (%s, harness %s, model %s)\n' \
    "$TICKET" "$(f .task.role)" "$(f .task.harness)" "$(printf '%s' "$doc" | jq -r '.task.model // "none"')"
  printf '  ← spec   sha256:%s "%s"\n' "$(f .spec.sha256)" "$(f .spec.title)"
} >&2

go

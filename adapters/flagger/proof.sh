#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# proof-flagger: what the Delivery suite cannot show about Flagger (docs/
# adr/0095 §6), on the cluster `./go flagger-conformance KEEP_CLUSTER=1`
# left up. Not a Delivery verb. Drives the adapter's verbs directly: the
# launchpad would roll back itself, and here nobody but Flagger may.
#   a. a canary that rolls back on bad metrics: the workload's committed
#      kill switch (on for CANARY_VERSION only), deploy, shift to 5, load;
#      GO when Flagger marks it Failed at weight 0 on its own failed
#      checks, with the rollback flag never opened;
#   b. a promotion that waits for the gate: the kill switch off, deploy,
#      shift to 5, 25 and 100, then the stage gate left open: GO when
#      Flagger holds WaitingPromotion at weight 100 for three ticks, and,
#      once a person points the promotion webhook at /gate/approve, reaches
#      Succeeded with the primary on the new version.
# One line on stdout (ci/lib.sh); the steps go to stderr.
set -eu
name=flagger
. ci/lib.sh
# shellcheck source=adapters/flagger/env.sh
. adapters/flagger/env.sh
: "${PLANE_HOST:=host.containers.internal}"
: "${APP_URL:=http://$PLANE_HOST:8080}"
: "${FLAGS:?FLAGS not set; run this via ./go flagger-proof}"
: "${FLAGS_FILE:?FLAGS_FILE not set; run this via ./go flagger-proof}"
: "${WORKLOAD_KILL_SWITCH:?WORKLOAD_KILL_SWITCH not set; run this via ./go flagger-proof}"
: "${CANARY_VERSION:?CANARY_VERSION not set; run this via ./go flagger-proof}"
: "${FLAGGER_IMAGE:?FLAGGER_IMAGE not set: the verified stable digest; run this via ./go flagger-proof}"
: "${WORKLOAD_CONTRACT:?WORKLOAD_CONTRACT not set; run this via ./go flagger-proof}"
# Ten-second ticks (the Canary's analysis.interval, docs/adr/0095).
tick=10
say() { printf '[flagger-proof] %s\n' "$*" >&2; }
phase() { canary_json | jq -r '.status.phase // ""'; }
weight() { canary_json | jq -r '.status.canaryWeight // 0'; }
events() {
  k get events --field-selector "involvedObject.kind=Canary,involvedObject.name=$FLAGGER_CANARY" -o json \
    | jq -r '[.items[] | .message] | join(" | ")'
}
# promotion_url URL: the Canary's confirm-promotion webhook, by name.
promotion_url() {
  i=$(canary_json | jq -r '[.spec.analysis.webhooks[].name] | index("lights-out-promotion")')
  [ "$i" != null ] || { printf 'flagger-proof: the Canary has no lights-out-promotion webhook\n' >&2; return 1; }
  k patch canaries.flagger.app "$FLAGGER_CANARY" --type json \
    -p "[{\"op\":\"replace\",\"path\":\"/spec/analysis/webhooks/$i/url\",\"value\":\"$1\"}]" >/dev/null
}
load_pid=""
stop_load() { [ -z "$load_pid" ] || { kill "$load_pid" 2>/dev/null || :; wait "$load_pid" 2>/dev/null || :; load_pid=""; }; }
# shellcheck disable=SC2329 # invoked by name via `trap` below, not called directly
cleanup() {
  stop_load
  promotion_url "http://flagger-loadtester.$FLAGGER_NAMESPACE/gate/halt" >/dev/null 2>&1 || :
  tester /gate/close 2>/dev/null || :
  sh "adapters/$FLAGS/set.sh" "$WORKLOAD_KILL_SWITCH" off >/dev/null 2>&1 || :
}
trap cleanup EXIT

[ -n "$(canary_json 2>/dev/null)" ] \
  || nogo "no canary $FLAGGER_NAMESPACE/$FLAGGER_CANARY; run ./go flagger-conformance KEEP_CLUSTER=1 first"
sh adapters/flagger/rollback.sh || nogo "could not roll back what was in flight before the proof"
start=$(date +%s)

# --- a: Flagger's own analysis rolls back ---------------------------------
# The committed flag file, in place (flagd watches the inode it mounted):
# the kill switch on for CANARY_VERSION only, so the canary fails and the
# stable does not.
git show "HEAD:$FLAGS_FILE" > "$FLAGS_FILE" || nogo "a: could not restore $FLAGS_FILE's committed targeting"
sleep 2
say "a: deploy $CANARY_VERSION with the kill switch on, shift to 5%"
sh adapters/flagger/deploy.sh "$CANARY_VERSION" "$FLAGGER_IMAGE" || nogo "a: deploy did not take"
sh adapters/flagger/shift.sh 5 || nogo "a: shift to 5% did not take"
sh "$WORKLOAD_CONTRACT/load.sh" >/dev/null & load_pid=$!
i=0
while [ "$(phase)" != Failed ]; do
  i=$((i + 1))
  [ "$i" -lt 180 ] || nogo "a: Flagger did not roll the canary back in 180 s ($(phase) at $(weight)): $(events)"
  sleep 1
done
a_s=$i
stop_load
case "$(events)" in
  *"failed checks threshold reached"*) ;;
  *) nogo "a: the canary is Failed, but not on Flagger's failed checks: $(events)" ;;
esac
s=$(sh adapters/flagger/status.sh) || nogo "a: status.sh failed after the rollback"
[ "$(printf '%s' "$s" | jq -c '[.canary, .weight]')" = '[null,0]' ] || nogo "a: status after Flagger's rollback is $s, want canary null at weight 0"
say "a: GO, Flagger rolled back on its own analysis in ${a_s}s: $s"

# --- b: the promotion waits for its gate -----------------------------------
sh "adapters/$FLAGS/set.sh" "$WORKLOAD_KILL_SWITCH" off >/dev/null || nogo "b: could not set $WORKLOAD_KILL_SWITCH off"
# The Canary's metric reads one minute of the canary job: a's errors stay in
# it that long, and Flagger would roll b back on them (seen on the first
# run, 2026-11-16, delta 0.14). The window plus two scrapes, as docs/adr/
# 0013 §2 keeps two verified stages apart.
say "b: waiting 70 s for a's errors to leave the metric's 1-minute window"
sleep 70
say "b: deploy $CANARY_VERSION with the kill switch off, shift to 5, 25, 100"
sh adapters/flagger/deploy.sh "$CANARY_VERSION" "$FLAGGER_IMAGE" || nogo "b: deploy did not take"
sh "$WORKLOAD_CONTRACT/load.sh" >/dev/null & load_pid=$!
for pct in 5 25 100; do
  sh adapters/flagger/shift.sh "$pct" || nogo "b: shift to $pct% did not take: $(events)"
done
# The stage gate open at 100: Flagger now asks confirm-promotion, /gate/halt.
tester /gate/open || nogo "b: could not open the stage gate"
i=0
while [ "$(phase)" != WaitingPromotion ]; do
  i=$((i + 1))
  [ "$i" -lt $((tick * 4)) ] || nogo "b: Flagger is $(phase) at $(weight), never WaitingPromotion: $(events)"
  sleep 1
done
say "b: WaitingPromotion at 100; holding three ticks"
i=0
while [ "$i" -lt $((tick * 3)) ]; do
  p=$(phase); w=$(weight)
  [ "$p" = WaitingPromotion ] && [ "$w" = 100 ] || nogo "b: the promotion gate did not hold: $p at $w after ${i}s: $(events)"
  i=$((i + 1))
  sleep 1
done
s=$(sh adapters/flagger/status.sh) || nogo "b: status.sh failed while held"
[ "$(printf '%s' "$s" | jq -c '[.canary, .weight]')" = "[\"$CANARY_VERSION\",100]" ] \
  || nogo "b: status while held is $s, want canary $CANARY_VERSION at 100"
say "b: a person answers: the promotion webhook to /gate/approve"
promotion_url "http://flagger-loadtester.$FLAGGER_NAMESPACE/gate/approve" || nogo "b: could not change the promotion webhook"
i=0
while [ "$(phase)" != Succeeded ]; do
  i=$((i + 1))
  [ "$i" -lt 180 ] || nogo "b: Flagger did not complete the promotion in 180 s ($(phase)): $(events)"
  sleep 1
done
stop_load
s=$(sh adapters/flagger/status.sh) || nogo "b: status.sh failed after the promotion"
[ "$(printf '%s' "$s" | jq -c '[.stable, .canary, .weight]')" = "[\"$CANARY_VERSION\",null,0]" ] \
  || nogo "b: status after the promotion is $s, want stable $CANARY_VERSION, canary null, weight 0"

go_with "Flagger rolled a failing canary back on its own analysis in ${a_s}s; the promotion held at its gate for $((tick * 3))s at 100% and completed on a person's answer; $(( $(date +%s) - start ))s"

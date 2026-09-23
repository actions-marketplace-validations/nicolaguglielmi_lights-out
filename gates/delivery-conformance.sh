#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-delivery-conformance: the Delivery/Flags port conformance suite
# (docs/adr/0026). Six cases, in the fixed order §6 requires — cases 1-4
# stage a real release each through `make release`/`make promote` (never
# calling an adapter script by hand: driven only through core/, per ADR
# 0024 §2), cases 5-6 stage nothing and sit last. The order is load-bearing:
# at L0 a canary revision is reused across releases, so two verified stages
# closer together than verify/slo.promql's window attribute one canary's
# errors to the next (docs/adr/0013 §2) — do not reorder the cases or run
# them concurrently with anything else that stages a release.
#
# Level-agnostic by construction: every assertion goes through
# adapters/$DELIVERY/status.sh (§2's three keys, nothing else) and
# $APP_URL/healthz, never Envoy's admin API — demo-rollback/demo-hold/
# demo-launch keep that L0-only proof, this suite proves the port.
#
# Leaves the workload's flag file ($FLAGS_FILE) changed on disk (verified
# 2026-09-20): the trap restores the workload's kill switch
# ($WORKLOAD_KILL_SWITCH) to "off" through the port, not to the committed
# per-version targeting rule (set.sh's two-argument contract cannot express
# a targeting rule, and restoring "on" instead would leave every version
# kill-switched, breaking a plain ./go demo afterward — see set.sh's own
# header and this repo's HANDOFF). A second run's own preflight catches
# this and NO-GOes naming the fix; `demo-rollback` run right after this
# suite without restoring first would not: `git checkout -- "$FLAGS_FILE"`
# before either.
#
# Lives in gates/, so ci/contract.sh cold-runs it inside `make ci` with no
# CONFORMANCE set and no plane up; the guard below must be the first thing
# that runs and must not touch a port. `make delivery-conformance` is the
# only caller that sets CONFORMANCE=1 — the acceptance commands are
# `./go delivery-conformance` (L0) and `./go delivery-conformance
# PROFILE=l2`, never a bare `make delivery-conformance`/`sh gates/…` in a
# criterion (CLAUDE.md).
set -eu
name=delivery-conformance
. ci/lib.sh

# Instant NO-GO, before any variable that needs a git call or a profile is
# even read: this is the line ci/contract.sh's cold run must see (docs/adr/
# 0026 §4).
if [ "${CONFORMANCE:-}" != "1" ]; then
  nogo "set CONFORMANCE=1: this suite drives real releases on the plane (./go delivery-conformance)"
fi

: "${RELEASE_RECORD:=.crew/release.json}"
: "${PLANE_HOST:=host.containers.internal}"
: "${APP_URL:=http://$PLANE_HOST:8080}"

[ -n "${DELIVERY:-}" ] || nogo "DELIVERY is not set; a profile sets it — run via make delivery-conformance"
[ -n "${FLAGS:-}" ] || nogo "FLAGS is not set; a profile sets it — run via make delivery-conformance"
[ -n "${WORKLOAD_KILL_SWITCH:-}" ] || nogo "WORKLOAD_KILL_SWITCH is empty; the workload's workload.env should set it (docs/adr/0030 §2)"
# CANARY_VERSION comes from the workload's workload.env, already exported
# by make (docs/adr/0030 §2) — no hardcoded fallback here, so a blank
# value NO-GOes naming the key instead of silently driving a release
# against "".
[ -n "${CANARY_VERSION:-}" ] || nogo "CANARY_VERSION is empty; the workload's workload.env should set it (docs/adr/0030 §2)"

# The tag ./go up publishes (docs/adr/0025 §3). Computed here, not defaulted
# by the Makefile as of this writing: every `make release` call below passes
# CANARY_TAG explicitly, so this gate never depends on a Makefile default
# existing or matching this value.
if [ -z "${CANARY_TAG:-}" ]; then
  head_sha=$(git rev-parse HEAD) || nogo "could not compute CANARY_TAG: git rev-parse HEAD failed"
  CANARY_TAG="sha-$head_sha"
fi

flags_adapter="adapters/$FLAGS"
delivery_adapter="adapters/$DELIVERY"

# ---------------------------------------------------------------------------
# Every flag the suite changes is restored through set.sh in a trap on EXIT,
# INT and TERM (docs/adr/0026 §5, the demo-hold pattern). This trap must
# never print to stdout — the one line this gate owns is already printed by
# the time it runs (go/nogo call exit, which fires this) — so a restore
# failure is a warning on stderr, not a second verdict line.
# ---------------------------------------------------------------------------
kill_switch_touched=0
freeze_touched=0

# shellcheck disable=SC2329 # invoked by name via `trap` below, not called directly
restore_flags() {
  ec=$?
  if [ "$freeze_touched" -eq 1 ]; then
    sh "$flags_adapter/set.sh" release-freeze off >&2 \
      || printf 'delivery-conformance: cleanup could not restore release-freeze; run: sh %s/set.sh release-freeze off\n' "$flags_adapter" >&2
  fi
  if [ "$kill_switch_touched" -eq 1 ]; then
    # "off", matching the workload's committed flags/flags.json defaultVariant
    # — not "on": set.sh's two-argument contract can set a flat default but
    # cannot reconstruct the committed per-version targeting rule, and "on"
    # here would leave *every* version kill-switched, not just
    # CANARY_VERSION, which breaks a plain ./go smoke/demo run afterward,
    # silently. "off" fails safe: a second delivery-conformance run's own
    # preflight NO-GOes with a clear reason instead of passing against a
    # subtly wrong state.
    sh "$flags_adapter/set.sh" "$WORKLOAD_KILL_SWITCH" off >&2 \
      || printf 'delivery-conformance: cleanup could not restore %s; run: sh %s/set.sh %s off\n' "$WORKLOAD_KILL_SWITCH" "$flags_adapter" "$WORKLOAD_KILL_SWITCH" >&2
  fi
  exit "$ec"
}
trap restore_flags EXIT INT TERM

# ---------------------------------------------------------------------------
# Helpers. None of these may be called inside a $(...) capture: a nogo
# inside one would only exit the subshell the capture runs in, not this
# script (a POSIX sh pitfall, not a hypothetical one).
# ---------------------------------------------------------------------------

# fetch_status CASE: sets $status_json to a §2-shape-validated read of
# adapters/$DELIVERY/status.sh, or NO-GOes naming CASE.
fetch_status() {
  case_label=$1
  if ! status_json=$(sh "$delivery_adapter/status.sh"); then
    nogo "$case_label: adapters/$DELIVERY/status.sh exited nonzero"
  fi
  if ! keys=$(printf '%s' "$status_json" | jq -r 'keys_unsorted | sort | join(",")' 2>/dev/null); then
    nogo "$case_label: adapters/$DELIVERY/status.sh did not print valid JSON: $status_json"
  fi
  [ "$keys" = "canary,stable,weight" ] \
    || nogo "$case_label: adapters/$DELIVERY/status.sh printed keys [$keys], want exactly stable, canary, weight"
  if ! printf '%s' "$status_json" | jq -e '
        (.stable | type) == "string"
        and ((.canary | type) == "string" or .canary == null)
        and ((.weight | type) == "number" and (.weight | floor) == .weight and .weight >= 0 and .weight <= 100)
      ' >/dev/null 2>&1
  then
    nogo "$case_label: adapters/$DELIVERY/status.sh printed the wrong shape: $status_json"
  fi
}

# fetch_record CASE: sets $record_json to the parsed $RELEASE_RECORD, or
# NO-GOes naming CASE.
fetch_record() {
  case_label=$1
  [ -f "$RELEASE_RECORD" ] || nogo "$case_label: $RELEASE_RECORD does not exist"
  record_json=$(cat "$RELEASE_RECORD")
  if ! printf '%s' "$record_json" | jq -e . >/dev/null 2>&1; then
    nogo "$case_label: $RELEASE_RECORD is not valid JSON"
  fi
}

# run_release CASE CANARY_VERSION_ARG CANARY_TAG_ARG: sets $release_out (the
# launchpad's one stdout line, through make release) and $release_rc.
# stderr is inherited, never captured, so a release's own progress and the
# slo: lines stream through live (docs/adr/0026 §7). $release_rc is `make
# release`'s own exit code, not core/launchpad.sh's: GNU Make reports a
# failed recipe as 2 regardless of the recipe's own exit status (verified
# live 2026-09-20 — launchpad.sh itself exits 1 via nogo, `make release`
# wrapping it exits 2). Every case below asserts 2, not 1, for that reason.
run_release() {
  case_label=$1; cv=$2; ct=$3
  printf '[delivery-conformance] %s: make release CANARY_VERSION=%s CANARY_TAG=%s\n' "$case_label" "$cv" "$ct" >&2
  if release_out=$(make --no-print-directory release CANARY_VERSION="$cv" CANARY_TAG="$ct"); then
    release_rc=0
  else
    release_rc=$?
  fi
}

# healthz_matches WANT_VERSION: prints how many of 10 GET $APP_URL/healthz
# report WANT_VERSION (docs/adr/0013 §4's count, reused here unchanged).
healthz_matches() {
  want=$1
  ok=0; i=0
  while [ "$i" -lt 10 ]; do
    v=$(curl -fsS --connect-timeout 1 --max-time 3 "$APP_URL/healthz" | jq -r .version 2>/dev/null) || v=""
    [ "$v" = "$want" ] && ok=$((ok + 1))
    i=$((i + 1))
  done
  printf '%s' "$ok"
}

# ---------------------------------------------------------------------------
# Preflight (docs/adr/0026 §5), through the ports, never through the tree.
# Each unmet precondition is its own one-line NO-GO naming the fix.
# ---------------------------------------------------------------------------

if ! freeze_val=$(sh "$flags_adapter/evaluate.sh" release-freeze); then
  nogo "adapters/$FLAGS/evaluate.sh release-freeze failed; is the plane up? (./go up)"
fi
[ "$freeze_val" = "false" ] \
  || nogo "release-freeze already evaluates $freeze_val, want false; run: sh $flags_adapter/set.sh release-freeze off"

if ! kill_switch_val=$(sh "$flags_adapter/evaluate.sh" "$WORKLOAD_KILL_SWITCH" "$CANARY_VERSION"); then
  nogo "adapters/$FLAGS/evaluate.sh $WORKLOAD_KILL_SWITCH $CANARY_VERSION failed; is the plane up? (./go up)"
fi
[ "$kill_switch_val" = "true" ] \
  || nogo "$WORKLOAD_KILL_SWITCH $CANARY_VERSION already evaluates $kill_switch_val, want true; the workload's committed flags/flags.json targeting rule may be missing"

fetch_status preflight
weight0=$(printf '%s' "$status_json" | jq -r .weight)
[ "$weight0" = "0" ] \
  || nogo "preflight: adapters/$DELIVERY/status.sh reports weight $weight0, want 0; run: sh $delivery_adapter/rollback.sh"

preflight_stable=$(printf '%s' "$status_json" | jq -r .stable)
printf '[delivery-conformance] preflight GO: DELIVERY=%s FLAGS=%s stable=%s CANARY_VERSION=%s CANARY_TAG=%s\n' \
  "$DELIVERY" "$FLAGS" "$preflight_stable" "$CANARY_VERSION" "$CANARY_TAG" >&2

# ---------------------------------------------------------------------------
# Case 1: rejects and rolls back. No setup — the committed targeting rule
# (the workload's own flags/flags.json, via $WORKLOAD_KILL_SWITCH) is the
# failure.
# ---------------------------------------------------------------------------

run_release "case1 rejects-and-rolls-back" "$CANARY_VERSION" "$CANARY_TAG"
[ "$release_rc" -eq 2 ] || nogo "case1 rejects-and-rolls-back: make release exited $release_rc, want 2"
case "$release_out" in
  "NO-GO: launchpad — 5%: "*) ;;
  *) nogo "case1 rejects-and-rolls-back: stdout was [$release_out], want a line starting with NO-GO: launchpad — 5%: " ;;
esac

fetch_record "case1 rejects-and-rolls-back"
verdict=$(printf '%s' "$record_json" | jq -r .verdict)
[ "$verdict" = "rolled-back" ] || nogo "case1 rejects-and-rolls-back: RELEASE_RECORD.verdict is $verdict, want rolled-back"
record_stable=$(printf '%s' "$record_json" | jq -r .stable)

fetch_status "case1 rejects-and-rolls-back"
w=$(printf '%s' "$status_json" | jq -r .weight)
[ "$w" = "0" ] || nogo "case1 rejects-and-rolls-back: status.sh weight is $w, want 0"
s=$(printf '%s' "$status_json" | jq -r .stable)
[ "$s" = "$record_stable" ] || nogo "case1 rejects-and-rolls-back: status.sh stable is $s, want $record_stable (the release record's)"

ok=$(healthz_matches "$record_stable")
[ "$ok" -eq 10 ] || nogo "case1 rejects-and-rolls-back: only $ok/10 healthz report $record_stable"
printf '[delivery-conformance] case1 rejects-and-rolls-back: GO\n' >&2

# ---------------------------------------------------------------------------
# Case 2: promotes. Setup: the workload's kill switch ($WORKLOAD_KILL_SWITCH
# off), the same way demo-hold already makes verify pass.
# ---------------------------------------------------------------------------

sh "$flags_adapter/set.sh" "$WORKLOAD_KILL_SWITCH" off >&2 || nogo "case2 promotes: adapters/$FLAGS/set.sh $WORKLOAD_KILL_SWITCH off failed"
kill_switch_touched=1

run_release "case2 promotes" "$CANARY_VERSION" "$CANARY_TAG"
[ "$release_rc" -eq 0 ] || nogo "case2 promotes: make release exited $release_rc, want 0 (stdout: $release_out)"

fetch_record "case2 promotes"
verdict=$(printf '%s' "$record_json" | jq -r .verdict)
[ "$verdict" = "held" ] || nogo "case2 promotes: RELEASE_RECORD.verdict is $verdict, want held"
held_at=$(printf '%s' "$record_json" | jq -r .held_at)
[ "$held_at" = "25" ] || nogo "case2 promotes: RELEASE_RECORD.held_at is $held_at, want 25"
record_stable=$(printf '%s' "$record_json" | jq -r .stable)
record_version=$(printf '%s' "$record_json" | jq -r .version)

fetch_status "case2 promotes (held at 25%)"
s=$(printf '%s' "$status_json" | jq -r .stable)
c=$(printf '%s' "$status_json" | jq -r .canary)
w=$(printf '%s' "$status_json" | jq -r .weight)
[ "$s" = "$record_stable" ] || nogo "case2 promotes: status.sh stable is $s, want $record_stable (the release record's)"
[ "$c" = "$record_version" ] || nogo "case2 promotes: status.sh canary is $c, want $record_version (the release record's)"
[ "$w" = "25" ] || nogo "case2 promotes: status.sh weight is $w, want 25"

printf '[delivery-conformance] case2 promotes: GO_FOR_LAUNCH=GO make promote\n' >&2
if promote_out=$(GO_FOR_LAUNCH=GO make --no-print-directory promote); then
  promote_rc=0
else
  promote_rc=$?
fi
[ "$promote_rc" -eq 0 ] || nogo "case2 promotes: GO_FOR_LAUNCH=GO make promote exited $promote_rc (stdout: $promote_out)"

fetch_status "case2 promotes (after promote)"
w=$(printf '%s' "$status_json" | jq -r .weight)
[ "$w" = "100" ] || nogo "case2 promotes: status.sh weight after promote is $w, want 100"

ok=$(healthz_matches "$record_version")
[ "$ok" -eq 10 ] || nogo "case2 promotes: only $ok/10 healthz report $record_version at 100%"
printf '[delivery-conformance] case2 promotes: GO\n' >&2

# No teardown release here (docs/adr/0026 §6.2): case 3's own `make release`
# rolls back unconditionally before it ever checks the freeze flag
# (core/launchpad.sh's opening `rollback`), which is what leaves traffic on
# stable for case 3. The kill switch flag itself is restored by the trap.

# ---------------------------------------------------------------------------
# Case 3: respects the freeze.
# ---------------------------------------------------------------------------

sh "$flags_adapter/set.sh" release-freeze on >&2 || nogo "case3 respects-the-freeze: adapters/$FLAGS/set.sh release-freeze on failed"
freeze_touched=1

fetch_status "case3 respects-the-freeze (snapshot)"
snap_stable=$(printf '%s' "$status_json" | jq -r .stable)

run_release "case3 respects-the-freeze" "$CANARY_VERSION" "$CANARY_TAG"
[ "$release_rc" -eq 2 ] || nogo "case3 respects-the-freeze: make release exited $release_rc, want 2"
[ "$release_out" = "NO-GO: launchpad — release-freeze is on" ] \
  || nogo "case3 respects-the-freeze: stdout was [$release_out], want exactly NO-GO: launchpad — release-freeze is on"

fetch_status "case3 respects-the-freeze"
w=$(printf '%s' "$status_json" | jq -r .weight)
[ "$w" = "0" ] || nogo "case3 respects-the-freeze: status.sh weight is $w, want 0"
s=$(printf '%s' "$status_json" | jq -r .stable)
[ "$s" = "$snap_stable" ] || nogo "case3 respects-the-freeze: status.sh stable is $s, want $snap_stable (the snapshot's)"
printf '[delivery-conformance] case3 respects-the-freeze: GO\n' >&2

# ---------------------------------------------------------------------------
# Case 4: rollback is idempotent. The same frozen release again, immediately;
# same three assertions as case 3, against the same snapshot (nothing
# between the two cases can have moved it).
# ---------------------------------------------------------------------------

run_release "case4 rollback-is-idempotent" "$CANARY_VERSION" "$CANARY_TAG"
[ "$release_rc" -eq 2 ] || nogo "case4 rollback-is-idempotent: make release exited $release_rc, want 2"
[ "$release_out" = "NO-GO: launchpad — release-freeze is on" ] \
  || nogo "case4 rollback-is-idempotent: stdout was [$release_out], want exactly NO-GO: launchpad — release-freeze is on"

fetch_status "case4 rollback-is-idempotent"
w=$(printf '%s' "$status_json" | jq -r .weight)
[ "$w" = "0" ] || nogo "case4 rollback-is-idempotent: status.sh weight is $w, want 0"
s=$(printf '%s' "$status_json" | jq -r .stable)
[ "$s" = "$snap_stable" ] || nogo "case4 rollback-is-idempotent: status.sh stable is $s, want $snap_stable (case 3's snapshot)"

sh "$flags_adapter/set.sh" release-freeze off >&2 || nogo "case4 rollback-is-idempotent: adapters/$FLAGS/set.sh release-freeze off failed"
freeze_touched=0
printf '[delivery-conformance] case4 rollback-is-idempotent: GO\n' >&2

# ---------------------------------------------------------------------------
# Case 5: refuses an image the Registry port cannot verify (added 2026-09-20,
# owner ruling). No setup. CANARY_VERSION is the snapshot's stable, not the
# targeted version: the case isolates the signature check, which the
# launchpad runs before staging and before either % stage (docs/adr/0025
# §6), from the kill-switch-targeting failure case 1 already covers.
# ---------------------------------------------------------------------------

fetch_status "case5 unsigned-image (snapshot)"
snap5_json=$status_json
stable5=$(printf '%s' "$snap5_json" | jq -r .stable)

run_release "case5 unsigned-image" "$stable5" "sha-0000000000000000000000000000000000000000"
[ "$release_rc" -eq 2 ] || nogo "case5 unsigned-image: make release exited $release_rc, want 2"
[ "$release_out" = "NO-GO: launchpad — unsigned image" ] \
  || nogo "case5 unsigned-image: stdout was [$release_out], want exactly NO-GO: launchpad — unsigned image"

fetch_status "case5 unsigned-image"
s=$(printf '%s' "$status_json" | jq -r .stable)
c=$(printf '%s' "$status_json" | jq -r .canary)
w=$(printf '%s' "$status_json" | jq -r .weight)
snap_s5=$(printf '%s' "$snap5_json" | jq -r .stable)
snap_c5=$(printf '%s' "$snap5_json" | jq -r .canary)
snap_w5=$(printf '%s' "$snap5_json" | jq -r .weight)
[ "$s" = "$snap_s5" ] || nogo "case5 unsigned-image: status.sh stable is $s, want $snap_s5 (the snapshot's)"
[ "$c" = "$snap_c5" ] || nogo "case5 unsigned-image: status.sh canary is $c, want $snap_c5 (the snapshot's)"
[ "$w" = "$snap_w5" ] || nogo "case5 unsigned-image: status.sh weight is $w, want $snap_w5 (the snapshot's)"
printf '[delivery-conformance] case5 unsigned-image: GO\n' >&2

# ---------------------------------------------------------------------------
# Case 6: reports state. Not a drive of its own (docs/adr/0026 §6.6): every
# status.sh read above already had to parse as the three-key shape and
# agree with the release record, or this script would already have NO-GOed
# naming the case that drove it. Reaching this line is case 6 passing.
# ---------------------------------------------------------------------------

printf '[delivery-conformance] case6 reports-state: every status.sh read above parsed and agreed: GO\n' >&2

go

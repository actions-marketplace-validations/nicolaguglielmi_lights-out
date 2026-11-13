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
# criterion (CLAUDE.md). The cases, the flag restore and the record are
# core/gates/delivery.py (docs/adr/0084).
set -eu
name=delivery-conformance
. ci/lib.sh

# Instant NO-GO, before any variable that needs a git call or a profile is
# even read: this is the line ci/contract.sh's cold run must see (docs/adr/
# 0026 §4).
if [ "${CONFORMANCE:-}" != "1" ]; then
  nogo "set CONFORMANCE=1: this suite drives real releases on the plane (./go delivery-conformance)"
fi
verdict core.gates.delivery

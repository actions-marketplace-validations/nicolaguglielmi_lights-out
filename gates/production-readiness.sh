#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-production-readiness: docs/adr/0057 §10, `./go production-readiness`.
# Whether this setup may take real traffic. GO only when all four hold;
# otherwise one NO-GO naming every item that fails, details on stderr:
#
#   delivery    DELIVERY's adapter has a rollback.sh, and a conformance
#               record (docs/adr/0057 §9, written by
#               gates/delivery-conformance.sh on GO) whose HASH is the
#               adapter's hash today: changed since it passed is not passed
#   metrics     METRICS=promql with METRICS_URL set, and that endpoint
#               answers count(target_info) with at least one sample; the
#               plane's own prometheus scrapes the demo app, not yours
#   secrets     .env holds no value, other than empty or replace-me, for a
#               key ending in _KEY, _TOKEN, _SECRET or _PASSWORD, or for
#               METRICS_AUTH_HEADER: production takes them from its
#               environment, where a secret manager puts them
#   human gate  GO_FOR_LAUNCH is not preset (a preset answer is silence
#               that promotes), and the console names who presses:
#               CONSOLE_AUTH=proxy, CONSOLE_IDENTITY_HEADER and a non-empty
#               CONSOLE_LAUNCHERS (docs/adr/0047)
#
# At L0 it is NO-GO by construction. Not one of the eight PR gates, never
# run by `gates`. READINESS_ENV_FILE (default .env) and CONFORMANCE_DIR
# (default .crew/conformance) let ci/production-readiness.sh judge
# constructed cases. The judgement is core/gates/readiness.py (docs/adr/0084).
set -eu
name=production-readiness
. ci/lib.sh
verdict core.gates.readiness

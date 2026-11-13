#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-sast: docs/adr/0015 §4, as amended by docs/adr/0072 §1. Static
# analysis over the workload's shipped code by the workload's own SAST_CMD
# (docs/adr/0042 §1), run where its TOOLCHAIN_IMAGE says (core/toolchain.sh).
# The runner prints one JSON line on stdout, `{"findings": N, "items":
# [{"rule", "file", "line"}]}`, `file` relative to the directory it runs
# from ($WORKLOAD/$WORKLOAD_TEST_ROOT), its report on stderr, non-zero only
# if the tool itself failed. For the bundled app the command is `sh
# tests/sast/run.sh` (bandit) in the compose service backend-test.
#
# The verdict is on the diff, as gates/deps.sh's (docs/adr/0072 §1): the
# runner scans HEAD's checkout, and, when HEAD has findings, the merge-base
# in a worktree of its own. core/sastdiff.py fingerprints each finding as
# (rule, file followed through renames, hash of the flagged line's text
# with whitespace stripped) and only a fingerprint HEAD has more times than
# the base is NO-GO; inherited findings are listed on stderr and in
# sast.json. A HEAD with no finding is GO without scanning the base. A
# runner that prints no `items`, on either side, predates ADR 0072: HEAD is
# judged whole, any finding NO-GO, as before, and stderr says so. No
# severity floor: it would be a number with no provenance. `# nosec` (or
# the stack's own) stays the escape hatch for a new finding.
#
# Both sides run the runner the checkout carries: in the tower's CI step a
# contract's runners/ are the base's (docs/adr/0033), and the merge-base's
# own are the base's by definition.
#
# The scans and the verdict are core/gates/sast.py (docs/adr/0084); this keeps
# the guards and the toolchain preflight.
set -eu
name=sast
. ci/lib.sh
require_range
. core/toolchain.sh

[ -n "${SAST_CMD:-}" ] || nogo "SAST_CMD is empty (docs/adr/0042 §1)"
toolchain_preflight
verdict core.gates.sast "$base" "$head" "$toolchain_where"

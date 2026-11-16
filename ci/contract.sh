#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-contract: meta-gate. Judges every other gate, and the light tier's
# entry point (docs/adr/0061), on its stdout alone, and fails unless each
# one honours the output contract in
# ci/lib.sh: exactly one stdout line, "GO: <name>" (optionally followed by
# " — <detail>", docs/adr/0042 §3) with exit 0 or "NO-GO: <name> — <reason>"
# with exit 1, no ANSI escape sequences. The gate's
# own verdict does not matter here, only its shape. Scans ci/, gates/ and
# verify/ (docs/adr/0011 §4), skipping directories that do not exist yet;
# gate basenames must be unique across the three. A ci/ check that this
# `./go ci` has already run is judged on the record of that run, the
# stdout and exit code `record_check` left in $CI_RECORDS, and not run a
# second time (docs/adr/0062 §3); every gate with no usable record, which
# is every gate when ci-contract runs alone, is run cold: stdout captured,
# stderr discarded. It also checks the lib's
# own side of the contract (docs/adr/0038 §5): `nogo` may leave its details
# in the file $NOGO_DETAILS names, and stdout stays the one line.
#
# The judging is ci/checks/contract.py (docs/adr/0094: a ci/ check's logic
# in ci/checks/, its unit tests in ci/tests/), whose docstring is the spec;
# this file is the entry point ./go ci and the planted tree run.
set -eu
name=contract
. ci/lib.sh

verdict ci.checks.contract

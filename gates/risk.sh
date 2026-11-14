#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-risk: classifies a git range by path and size, rules not points
# (docs/adr/0016). Unlike every other gate in this repo, this one's NO-GO
# does NOT mean "found something bad" -- a high-risk PR that classified
# cleanly is still GO: risk is a routing decision (auto-merge vs review),
# not a pass/fail judgement, and `make gates` reads `decision`, not this
# exit code, to tell the two apart. NO-GO here means "could not classify":
# no range, a policy core/policy.py refuses, or core/risk.py failing on a malformed
# diff -- should not happen with real git output, but handled defensively,
# not assumed away.
# The diff, the classification and the summary are core/gates/risk.py
# (docs/adr/0084).
set -eu
name=risk
. ci/lib.sh
require_range

out_dir=${GATES_OUT:-.gates-out}
mkdir -p "$out_dir"
# The base's policy/merge.env and the workload's policy.env, merged
# (docs/adr/0037 §5); the diff is the workload repository's (§3).
effective_policy "$out_dir/effective-policy.env"
verdict core.gates.risk "$base" "$head" "$out_dir/effective-policy.env"

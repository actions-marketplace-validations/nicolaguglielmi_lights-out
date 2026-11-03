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
set -eu
name=risk
. ci/lib.sh
require_range

out_dir=${GATES_OUT:-.gates-out}
mkdir -p "$out_dir"

# The base's policy/merge.env and the workload's policy.env, merged
# (docs/adr/0037 §5); the diff is the workload repository's (§3).
policy="$out_dir/effective-policy.env"
effective_policy "$policy"

git -C "$WORKLOAD" diff --no-renames --numstat "$base" "$head" | python3 core/risk.py --policy "$policy" > "$out_dir/risk.json" \
  || nogo "core/risk.py could not classify the range $base..$head"

summary=$(python3 - "$out_dir/risk.json" <<'PY'
import json
import sys

with open(sys.argv[1]) as fh:
    data = json.load(fh)

bits = ["{}({})".format(s["name"], " ".join(s["paths"])) for s in data["signals"]]
print(
    "risk: level={} decision={} signals={}".format(
        data["level"], data["decision"], ",".join(bits) or "none"
    )
)
PY
) || nogo "classified but could not summarise $out_dir/risk.json"

printf '%s\n' "$summary" >&2

go

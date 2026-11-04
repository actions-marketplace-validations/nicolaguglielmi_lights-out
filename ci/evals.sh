#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-evals: docs/adr/0020 §3, §8, the agents' own regression suite.
# (a) the `adk` CLI must be in the image; (b) every root_agent's toolset
# must equal the ADR's list (docs/adr/0020 §3, ops_triage's amended to
# four tools by docs/adr/0044 §4), always all three roles, under whatever
# AGENT_HARNESS the profile already exported -- never set here, never
# overridden: a replay-backed toolset check is still a toolset check;
# (c) the replay model's own unit tests; (d) `adk eval` per evalset,
# each judged on its own exit status and summary.
# ROLES=<space-separated agent dir names, e.g. "ops_triage release">
# limits which roles actually run an eval (record-evals's one-role-at-a-
# time use); default is every agent dir under adapters/adk/agents/ that
# has an evals/ directory. The toolset check in (b) always covers all
# three regardless of ROLES. PLANE_HOST is pinned to an address that
# resolves nowhere for the whole gate: nothing an eval calls may reach
# the plane -- a triage or a brief that touched it cannot pass, by
# construction, not by inspection (docs/adr/0020 §3).
set -eu
name=evals
. ci/lib.sh

command -v adk >/dev/null 2>&1 || nogo "adk not on PATH; rebuild the workbench"

PYTHONPATH=adapters/adk
export PYTHONPATH
PLANE_HOST=nowhere.invalid
export PLANE_HOST

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# --- (b) toolset check: all three roles, regardless of ROLES ---
toolset_log="$work/toolset.log"
if ! python3 - >"$toolset_log" 2>&1 <<'PY'
import sys

want = {
    "product": {"ask_product_owner", "confirm_acceptance"},
    "ops_triage": {"file_incident", "file_postmortem", "propose_rollback", "propose_hold"},
    "release": {"submit_brief", "decline_brief"},
}

problems = []
for role, expected in want.items():
    module = __import__(f"agents.{role}", fromlist=["root_agent"])
    got = {t.__name__ for t in module.root_agent.tools}
    if got != expected:
        problems.append(f"{role}: got {sorted(got)}, want {sorted(expected)}")

if problems:
    print("\n".join(problems))
    sys.exit(1)
PY
then
  nogo "root_agent toolset mismatch; see stderr" "$(cat "$toolset_log")"
fi

# --- (c) the replay model's own unit tests ---
python3 -m unittest discover -s adapters/adk/lights_out_adk/tests -t adapters/adk >&2 \
  || nogo "adapters/adk/lights_out_adk/tests failed; see stderr"

# --- (d) adk eval per role ---
roles="${ROLES:-}"
if [ -z "$roles" ]; then
  for d in adapters/adk/agents/*/; do
    [ -d "${d}evals" ] || continue
    roles="$roles $(basename "$d")"
  done
fi

[ -n "$roles" ] || nogo "no agent under adapters/adk/agents/ has an evals/ directory"

for role in $roles; do
  agent_dir="adapters/adk/agents/$role"
  evals_dir="$agent_dir/evals"
  [ -d "$evals_dir" ] || nogo "$role has no evals/ directory (check ROLES)"

  # Each evalset is judged on its own exit status and its own log, so a
  # crash in one cannot hide behind another's summary (ticket 0010).
  count=0
  for evalset in "$evals_dir"/*.evalset.json; do
    [ -e "$evalset" ] || continue
    count=$((count + 1))
    evalname=$(basename "$evalset" .evalset.json)
    eval_log="$work/$role.$evalname.log"
    adk eval "$agent_dir" "$evalset" \
      --config_file_path "$evals_dir/test_config.json" </dev/null >"$eval_log" 2>&1 && rc=0 || rc=$?

    # adk eval writes its result history under <agent_dir>/.adk/ (gitignored,
    # but ci/secrets.sh scans the working tree and flags the request ids in
    # it as secrets, verified 2026-09-16): the log above is the record kept.
    rm -rf "$agent_dir/.adk" adapters/adk/agents/.adk

    failed=$(grep -o 'Tests failed: [0-9]*' "$eval_log" | awk '{sum += $3} END{print sum+0}')
    [ "$failed" -eq 0 ] \
      || nogo "$role/$evalname: $failed eval case(s) failed; log on stderr" "$(cat "$eval_log")"
    [ "$rc" -eq 0 ] \
      || nogo "$role/$evalname: adk eval exited $rc; log on stderr" "$(cat "$eval_log")"
    grep -q 'Tests passed:' "$eval_log" \
      || nogo "$role/$evalname: no summary from adk eval; log on stderr" "$(cat "$eval_log")"
  done
  [ "$count" -gt 0 ] || nogo "$role: no *.evalset.json under $evals_dir"
done

go

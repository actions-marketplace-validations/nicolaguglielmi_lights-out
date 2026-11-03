#!/bin/sh
# Sourced by every gate: `. ci/lib.sh` after setting `name`.
# shellcheck disable=SC2154 # name is set by the sourcing gate
#
# Gate output contract (CLAUDE.md, "Contratto di output dei gate"):
#   - stdout carries exactly one line: "GO: <name>" or "NO-GO: <name> — <reason>"
#   - no colour when stdout is not a TTY: NO_COLOR is set here, and each tool
#     gets its own no-colour flag where it has one
#   - everything a tool prints goes to stderr; details for a NO-GO go to stderr
#   - GO exits 0, NO-GO exits 1
# ci/contract.sh verifies this on every gate.
NO_COLOR=1
export NO_COLOR

go() {
  printf 'GO: %s\n' "$name"
  exit 0
}

# nogo REASON [DETAILS...]: one contract line on stdout, details on stderr,
# and also in the file $NOGO_DETAILS names when a caller sets it (`make
# gates` does, for the rework loop's verdict: docs/adr/0038 §5).
nogo() {
  # A reason built from a tool's output can span lines; the contract is one.
  reason=$(printf '%s' "$1" | tr '\n' ' ')
  shift
  printf 'NO-GO: %s — %s\n' "$name" "$reason"
  for line in "$@"; do
    printf '%s\n' "$line" >&2
  done
  if [ -n "${NOGO_DETAILS:-}" ] && [ $# -gt 0 ]; then
    printf '%s\n' "$@" > "$NOGO_DETAILS" || :
  fi
  exit 1
}

# require_range: for the M4 PR gates (docs/adr/0015 §2), which judge a git
# range rather than the working tree. NO-GO in one line, no git call first,
# if BASE or HEAD is unset — what a cold ci/contract.sh run sees, and what
# keeps every gates/*.sh instant with no range and no plane. Otherwise sets
# $base to the merge-base of BASE and HEAD (the PR's own changes, as a code
# host would show them) and $head to HEAD, for the caller to diff against.
# The range is the workload's repository's: this one for a bundled
# workload, the attached repository's otherwise (docs/adr/0037 §3).
# Not called by sourcing ci/lib.sh: only gates that need a range call it.
require_range() {
  base_ref=${BASE:-}
  head_ref=${HEAD:-}
  if [ -z "$base_ref" ] || [ -z "$head_ref" ]; then
    nogo "BASE and HEAD must both be set"
  fi
  base=$(git -C "${WORKLOAD:-.}" merge-base "$base_ref" "$head_ref" 2>&1) \
    || nogo "git merge-base $base_ref $head_ref failed" "$base"
  # shellcheck disable=SC2034 # head is consumed by the sourcing gate
  head=$head_ref
}

# effective_policy FILE: policy/merge.env with the workload's own
# policy.env over it (docs/adr/0037 §5), written to FILE by core/policy.py,
# the one reader of either. NO-GO naming the key on an unknown key, a
# malformed value or a missing provenance; an override looser than the
# platform default is reported on stderr and applied.
effective_policy() {
  [ -n "${WORKLOAD_CONTRACT:-}" ] || nogo "WORKLOAD_CONTRACT is not set; run this via ./go, not directly"
  policy_reason=$(python3 core/policy.py --platform policy/merge.env \
    --workload-env "$WORKLOAD_CONTRACT/workload.env" \
    --overrides "$WORKLOAD_CONTRACT/policy.env" --out "$1") \
    || nogo "${policy_reason:-core/policy.py failed without a reason; see stderr}"
}

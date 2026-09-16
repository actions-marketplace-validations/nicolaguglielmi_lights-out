#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# step-release (docs/adr/0019 §1, §5): the Makefile's `release` (load
# generator beside core/launchpad.sh) with CANARY_VERSION, its stderr
# kept at .crew/<ticket>/release.log. Records the version, launchpad's one
# stdout line as the verdict, and the `slo:` lines — the numbers that
# produced the decision — as release.numbers. Exit 1 → rolled-back, exit
# 0 → held at 25% for go-for-launch (ADR 0014's semantics). Re-runnable:
# launchpad rolls back first, so a retry is a second release from a known
# state. At L0 the canary is the stable image under CANARY_VERSION, not a
# build of the merge commit; release.image says so on every record (M8).
set -eu
: "${TICKET:?TICKET not set}"
: "${CANARY_VERSION:?CANARY_VERSION not set}"

log=".crew/$TICKET/release.log"
mkdir -p ".crew/$TICKET"
: > "$log"
# make's stdout (launchpad's one verdict line) is captured on fd 3; its
# stderr streams live through tee into the log and on to our stderr. The
# exit code crosses the pipe through a file: POSIX sh has no pipefail.
rc_file=$(mktemp)
trap 'rm -f "$rc_file"' EXIT
verdict=$( { { make --no-print-directory release CANARY_VERSION="$CANARY_VERSION" 2>&1 1>&3; \
  printf '%s' "$?" > "$rc_file"; } | tee "$log" >&2; } 3>&1 )
if [ "$(cat "$rc_file")" -eq 0 ]; then
  state=held
else
  state=rolled-back
fi
# A release with no verdict line at all did not run launchpad: fail the step.
[ -n "$verdict" ] || { printf 'step-release: release printed no verdict; see %s\n' "$log" >&2; exit 1; }
numbers=$(grep '^slo: ' "$log" | jq -R . | jq -cs .)
jq -cn --arg state "$state" --arg v "$CANARY_VERSION" --arg verdict "$verdict" --argjson numbers "$numbers" \
  '{state: $state, release: {version: $v, verdict: $verdict, numbers: $numbers,
    image: "stable image, not built from merge.sha (M8)"}}'

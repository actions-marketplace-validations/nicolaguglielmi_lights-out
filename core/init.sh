#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-init: `make init` (docs/adr/0042 §6), the driver behind `./go init
# [<path>]`. On the attached clone: core/init.py drafts the gates half of
# .lights-out/ into the clone's .lights-out/ (never the user's repository,
# docs/adr/0037 §1), then the draft's MUTATION_CMD runs once over the
# whole scope (MUTATION_LINES=all) where its TOOLCHAIN_IMAGE says, and the
# score lands in MUTATION_BASELINE with its provenance: date, commit, the
# command, mutants, killed, seconds, where. A failed measurement is a
# NO-GO naming the command, and the draft stays with the key empty, which
# every gate refuses (docs/adr/0030 §2): never a guessed baseline. It ends
# with the contract check ci/workloads.sh applies to any attached
# repository. Not scanned by ci/contract.sh (core/), but reuses ci/lib.sh's
# line shape, as core/crew.sh does.
set -eu
name=init
. ci/lib.sh
. core/toolchain.sh

: "${WORKLOAD:?WORKLOAD not set; run this via ./go, not directly}"
: "${WORKLOAD_CONTRACT:?WORKLOAD_CONTRACT not set; run this via ./go, not directly}"
[ -n "${WORKLOAD_ATTACHED:-}" ] \
  || nogo "WORKLOAD=$WORKLOAD is not an attached repository; ./go init <path>, or ./go attach <path> first (the bundled app has its contract)"
[ -d stacks ] || nogo "stacks/ not found; run this from the lights-out checkout"

commit=$(git -C "$WORKLOAD" rev-parse --short HEAD 2>/dev/null) || nogo "$WORKLOAD is not a git repository"
today=$(date -u +%Y-%m-%d)

reason=$(python3 core/init.py --repo "$WORKLOAD" --out "$WORKLOAD_CONTRACT" --stacks stacks \
  --commit "$commit" --today "$today") || nogo "cannot draft $WORKLOAD: $reason"
stack=${reason#STACK=}

# What the secrets gate will find in the history (docs/adr/0049 §4): listed,
# never excused here.
sh core/history-findings.sh || printf 'init: the history scan could not run (see above); the secrets gate still scans it on every judgement\n' >&2

draft="$WORKLOAD_CONTRACT/workload.env"
# The draft's own keys, for the measurement below: the enclosing make
# could not include them (there was no contract when it started).
key() { grep -v '^[[:space:]]*#' "$draft" | sed -n "s/^$1=//p" | head -1; }
TOOLCHAIN_IMAGE=$(key TOOLCHAIN_IMAGE)
MUTATION_CMD=$(key MUTATION_CMD)
WORKLOAD_TEST_ROOT=$(key WORKLOAD_TEST_ROOT)
WORKLOAD_MUTATION_SCOPE=$(key WORKLOAD_MUTATION_SCOPE)
export TOOLCHAIN_IMAGE MUTATION_CMD WORKLOAD_TEST_ROOT WORKLOAD_MUTATION_SCOPE
[ -n "$MUTATION_CMD" ] || nogo "the draft has no MUTATION_CMD"

toolchain_preflight
# The measurement itself is core/mutation-baseline.sh's, the same one
# `./go mutation-baseline` runs on a committed contract.
start=$(date +%s)
set +e
line=$(sh core/mutation-baseline.sh)
rc=$?
set -e
elapsed=$(( $(date +%s) - start ))
[ "$rc" -eq 0 ] \
  || nogo "in $toolchain_where: MUTATION_CMD could not be measured; the draft is in $WORKLOAD_CONTRACT with MUTATION_BASELINE empty, see stderr"
total=$(printf '%s' "$line" | jq -r .total)
killed=$(printf '%s' "$line" | jq -r .killed)
score=$(printf '%s' "$line" | jq -r .score)

python3 core/init.py --set-baseline "$draft" "$score" \
  "measured by ./go init on $today at $commit, in $toolchain_where: $MUTATION_CMD with MUTATION_LINES=all, $total mutants, $killed killed, ${elapsed}s wall time. Re-measure with ./go mutation-baseline when the suite or the tool changes." \
  || nogo "could not write MUTATION_BASELINE into $draft"

out=$(sh ci/workloads.sh "$WORKLOAD") || nogo "the draft fails the contract check: ${out#NO-GO: workloads — }"

go_with "$stack, draft in $WORKLOAD_CONTRACT, baseline $score ($killed/$total mutants killed, ${elapsed}s, in $toolchain_where); copy .lights-out/ into your repository and commit it"

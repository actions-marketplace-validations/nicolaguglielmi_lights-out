#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-base-gates (docs/adr/0053 §6): an attached repository's base is
# green before a ticket starts on it. The code host's HEAD, the commit
# the worker will clone, judged by the gates that judge the tree and not
# the diff, `sast` and `test`, on an empty range in a throwaway worktree,
# isolated as the CI step runs them. A GO is cached as bases/<sha> in the
# StateStore and never run again for that commit; a NO-GO is not cached.
# Exit 0 when green, 1 with one `[assign]` line otherwise; all on stderr,
# the assign step's stdout is its JSON. Glue: git, make and two verbs.
set -eu
: "${CODE_HOST:?CODE_HOST not set; run this via ./go, not directly}"
: "${STATE_STORE:?STATE_STORE not set; run this via ./go, not directly}"
: "${WORKLOAD:?WORKLOAD not set; run this via ./go, not directly}"

git -C "$WORKLOAD" fetch -q "$(sh "adapters/$CODE_HOST/clone-url.sh")" HEAD >&2 \
  || { printf '[assign] could not fetch the base from %s\n' "$CODE_HOST" >&2; exit 1; }
sha=$(git -C "$WORKLOAD" rev-parse FETCH_HEAD)
if sh "adapters/$STATE_STORE/get.sh" bases "$sha" >/dev/null 2>&1; then
  printf '[assign] base %s: green, judged before\n' "$sha" >&2
  exit 0
fi

tmp=$(mktemp -d)
trap 'git -C "$WORKLOAD" worktree remove --force "$tmp/wt" >/dev/null 2>&1 || :; rm -rf "$tmp"' EXIT
git -C "$WORKLOAD" worktree add -q --detach "$tmp/wt" "$sha" >&2
out=$(make --no-print-directory gates WORKLOAD="$tmp/wt" GATES_OUT="$tmp/out" GATES="sast test" \
  BASE="$sha" HEAD="$sha" TOOLCHAIN_ISOLATE=1) && rc=0 || rc=$?
failed=$(sed -n 's/^FAILED=//p' "$tmp/out/verdict.env" 2>/dev/null) || failed=""
if [ "$rc" -ne 0 ]; then
  printf '[assign] base %s is red at %s: %s; the ticket waits until the base is fixed (docs/adr/0053 §6)\n' \
    "$sha" "${failed:-gates}" "$out" >&2
  exit 1
fi
jq -cn --arg line "$out" --arg at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '{verdict: "GO", line: $line, at: $at}' \
  | sh "adapters/$STATE_STORE/put.sh" bases "$sha"
printf '[assign] base %s: green, %s\n' "$sha" "$out" >&2

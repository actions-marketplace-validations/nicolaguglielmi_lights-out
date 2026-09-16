#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# step-merge (docs/adr/0019 §1, §5): merges the PR through the code host
# and records the merge sha and the head it merged. The seam for the
# crash case (docs/adr/0019 §9 d) is the adapter: merge.sh on a PR the
# host already reports merged performs nothing and prints the same two
# shas, so a tower that died between the effect and the write advances
# the document on the retry without a second merge. Next state: merged.
set -eu
: "${TICKET:?TICKET not set}"
: "${PR_NUMBER:?PR_NUMBER not set}"
: "${CODE_HOST:?CODE_HOST not set; run this via ./go, not directly}"

shas=$(sh "adapters/$CODE_HOST/merge.sh" "$PR_NUMBER") || exit 1
merge_sha=${shas%% *}
head_sha=${shas#* }
printf '[merge] PR #%s merged as %s (head %s)\n' "$PR_NUMBER" "$merge_sha" "$head_sha" >&2
jq -cn --arg m "$merge_sha" --arg h "$head_sha" '{state: "merged", merge: {sha: $m, head_sha: $h}}'

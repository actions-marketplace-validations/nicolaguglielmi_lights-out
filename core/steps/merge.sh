#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# step-merge (docs/adr/0019 §1, §5): merges the PR through the code host
# at the head CI judged — `ci.head_sha` in the document — and records the
# merge sha and the head it merged. A head that moved since CI fails the
# step (ticket 0010): the adapter refuses to merge it, and a head the
# adapter reports that is not the judged one is refused here as well.
# The seam for the crash case (docs/adr/0019 §9 d) is the adapter:
# merge.sh on a PR the host already reports merged performs nothing and
# prints the same two shas, so a tower that died between the effect and
# the write advances the document on the retry without a second merge.
# Next state: merged.
set -eu
: "${TICKET:?TICKET not set}"
: "${PR_NUMBER:?PR_NUMBER not set}"
: "${DOC_FILE:?DOC_FILE not set}"
: "${CODE_HOST:?CODE_HOST not set; run this via ./go, not directly}"

judged=$(jq -r '.ci.head_sha // empty' "$DOC_FILE")
[ -n "$judged" ] || { printf 'step-merge: %s has no ci.head_sha; nothing was judged\n' "$DOC_FILE" >&2; exit 1; }

shas=$(sh "adapters/$CODE_HOST/merge.sh" "$PR_NUMBER" "$judged") \
  || { printf 'step-merge: PR #%s not merged; CI judged head %s\n' "$PR_NUMBER" "$judged" >&2; exit 1; }
merge_sha=${shas%% *}
head_sha=${shas#* }
[ "$head_sha" = "$judged" ] \
  || { printf 'step-merge: PR #%s merged at head %s, CI judged %s\n' "$PR_NUMBER" "$head_sha" "$judged" >&2; exit 1; }
printf '[merge] PR #%s merged as %s (head %s)\n' "$PR_NUMBER" "$merge_sha" "$head_sha" >&2
jq -cn --arg m "$merge_sha" --arg h "$head_sha" '{state: "merged", merge: {sha: $m, head_sha: $h}}'

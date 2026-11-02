#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# step-release (docs/adr/0019 §1, §5; docs/adr/0025 §5-§7): waits for the
# merge commit's `image` status (adapters/$CODE_HOST/await.sh), then runs
# the Makefile's `release` (load generator beside core/launchpad.sh) with
# CANARY_VERSION and CANARY_TAG=sha-<merge sha>, its stderr kept at
# .crew/<ticket>/release.log. Records the version, launchpad's one stdout
# line as the verdict, the `slo:` lines as release.numbers, and the
# verified digest launchpad resolved, read back from RELEASE_RECORD — the
# placeholder is retired, this is a real read, not a literal string. Exit
# 1 → rolled-back, exit 0 → held at 25% for go-for-launch (ADR 0014's
# semantics). Re-runnable: launchpad rolls back first, so a retry is a
# second release from a known state.
set -eu
: "${TICKET:?TICKET not set}"
: "${CANARY_VERSION:?CANARY_VERSION not set}"
: "${DOC_FILE:?DOC_FILE not set; run this via core/tower.sh, not directly}"
: "${CODE_HOST:?CODE_HOST not set; run this via ./go, not directly}"
: "${IMAGE_TIMEOUT:=300}"
: "${RELEASE_RECORD:=.crew/release.json}"

merge_sha=$(jq -r '.merge.sha // empty' "$DOC_FILE")
[ -n "$merge_sha" ] || { printf 'step-release: %s has no merge.sha\n' "$DOC_FILE" >&2; exit 1; }

image_state=$(AWAIT_TIMEOUT="$IMAGE_TIMEOUT" sh "adapters/$CODE_HOST/await.sh" "$merge_sha" image) || exit 1
[ "$image_state" = success ] \
  || { printf 'step-release: image build on %s: %s\n' "$merge_sha" "$image_state" >&2; exit 1; }
canary_tag="sha-$merge_sha"

log=".crew/$TICKET/release.log"
mkdir -p ".crew/$TICKET"
: > "$log"
# make's stdout (launchpad's one verdict line) is captured on fd 3; its
# stderr streams live through tee into the log and on to our stderr. The
# exit code crosses the pipe through a file: POSIX sh has no pipefail.
rc_file=$(mktemp)
trap 'rm -f "$rc_file"' EXIT
# A fresh record: launchpad leaves the prior one untouched when it refuses
# before staging, and that one must not speak for this release.
rm -f "$RELEASE_RECORD"
verdict=$( { { make --no-print-directory release CANARY_VERSION="$CANARY_VERSION" CANARY_TAG="$canary_tag" 2>&1 1>&3; \
  printf '%s' "$?" > "$rc_file"; } | tee "$log" >&2; } 3>&1 )
# A release with no verdict line at all did not run launchpad: fail the step.
[ -n "$verdict" ] || { printf 'step-release: release printed no verdict; see %s\n' "$log" >&2; exit 1; }
rc=$(cat "$rc_file")
recorded=$(jq -r '.verdict // empty' "$RELEASE_RECORD" 2>/dev/null || printf '')
if [ "$rc" = 0 ]; then
  state=held
elif [ "$recorded" = rolled-back ]; then
  state=rolled-back
else
  # Refused before staging (freeze, signature, no stable version) or died:
  # nothing was rolled back, so the step failed rather than the canary.
  printf 'step-release: release did not reach a verdict stage (%s); see %s\n' "$verdict" "$log" >&2
  exit 1
fi
numbers=$(grep '^slo: ' "$log" | jq -R . | jq -cs .)
image=$(jq -r '.image // empty' "$RELEASE_RECORD" 2>/dev/null || printf '')
jq -cn --arg state "$state" --arg v "$CANARY_VERSION" --arg verdict "$verdict" --argjson numbers "$numbers" --arg image "$image" \
  '{state: $state, release: {version: $v, verdict: $verdict, numbers: $numbers, image: $image}}'

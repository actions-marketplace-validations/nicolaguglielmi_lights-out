#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# step-release (docs/adr/0019 §1, §5; docs/adr/0025 §6-§7; docs/adr/0043
# §4; docs/adr/0060 §5): fetches the merge commit from the code host and
# publishes it here, built from a throwaway worktree, pushed and signed by
# the Registry port (`make publish`), for every workload: an attached
# repository by its own contract's `backend` service (its Containerfile), a
# workload of this repository by `make publish` run inside the worktree,
# which is what the code host's CI job did until docs/adr/0060 retired it.
# Then runs the Makefile's `release` (load generator beside
# core/launchpad.sh) with CANARY_VERSION and CANARY_TAG=sha-<merge sha>, its
# stderr kept at .crew/<ticket>/release.log. Records the version,
# launchpad's one stdout line as the verdict, the `slo:` lines as
# release.numbers, and the verified digest launchpad resolved, read back
# from RELEASE_RECORD. Exit 1 → rolled-back, exit 0 → held at 25% for
# go-for-launch (ADR 0014's semantics). The commit released is the green
# main the `mainline` step judged with the merge in it (docs/adr/0056 §3),
# the merge itself when the document has none. Re-runnable: launchpad rolls
# back first, so a retry is a second release from a known state.
set -eu
: "${TICKET:?TICKET not set}"
: "${CANARY_VERSION:?CANARY_VERSION not set}"
: "${DOC_FILE:?DOC_FILE not set; run this via core/tower.sh, not directly}"
: "${CODE_HOST:?CODE_HOST not set; run this via ./go, not directly}"
: "${RELEASE_RECORD:=.crew/release.json}"

merge_sha=$(jq -r '.mainline.green // .merge.sha // empty' "$DOC_FILE")
[ -n "$merge_sha" ] || { printf 'step-release: %s has no merge.sha\n' "$DOC_FILE" >&2; exit 1; }

canary_tag="sha-$merge_sha"
# docs/adr/0043 §4: the merge, from the code host's default branch, in a
# throwaway worktree (not under .crew/, which the worker mounts), published
# under the tag the release deploys. launchpad verifies the signature
# before staging, as for any other image (ADR 0025 §6).
: "${WORKLOAD:?WORKLOAD not set; run this via ./go, not directly}"
clone_url=$(sh "adapters/$CODE_HOST/clone-url.sh")
git -C "$WORKLOAD" fetch -q "$clone_url" HEAD \
  || { printf 'step-release: could not fetch the default branch from %s\n' "$CODE_HOST" >&2; exit 1; }
git -C "$WORKLOAD" merge-base --is-ancestor "$merge_sha" FETCH_HEAD 2>/dev/null \
  || { printf 'step-release: merge %s is not on the default branch of %s\n' "$merge_sha" "$CODE_HOST" >&2; exit 1; }
src_tmp=$(mktemp -d)
src=$src_tmp/merge
git -C "$WORKLOAD" worktree add -q --detach "$src" "$merge_sha" >&2 \
  || { rm -rf "$src_tmp"; printf 'step-release: could not check out %s\n' "$merge_sha" >&2; exit 1; }
printf '[release] publishing %s, built from the merge %s (docs/adr/0060 §5)\n' "$canary_tag" "$merge_sha" >&2
published=0
if [ -n "${WORKLOAD_ATTACHED:-}" ]; then
  env -u APP_TAG -u CANARY_TAG -u CANARY_IMAGE \
    make --no-print-directory publish TAG="$canary_tag" WORKLOAD="$src" >/dev/null || published=$?
else
  # This repository at the merge: the workload at the same path inside it,
  # built, pushed and signed by this checkout's Makefile, compose file,
  # profiles and adapters (restored over the merge's, as ci.sh restores
  # the base's judges) with this checkout's key.
  inside=$(git -C "$WORKLOAD" rev-parse --show-prefix)
  git -C "$src" restore --source="$(git -C "$WORKLOAD" rev-parse HEAD)" -- Makefile compose.yaml profiles adapters \
    && env -u APP_TAG -u CANARY_TAG -u CANARY_IMAGE COSIGN_KEY="$PWD/.crew/cosign.key" \
    make -C "$src" --no-print-directory publish TAG="$canary_tag" WORKLOAD="${inside%/}" >/dev/null || published=$?
fi
git -C "$WORKLOAD" worktree remove --force "$src" >/dev/null 2>&1 || :
rm -rf "$src_tmp"
[ "$published" = 0 ] || { printf 'step-release: publish of %s failed; see above\n' "$canary_tag" >&2; exit 1; }

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
# RELEASE_TICKET: launchpad writes it into the release log (docs/adr/0047
# §2, P2), so the logbook can tie this release to this ticket.
verdict=$( { { RELEASE_TICKET="$TICKET" make --no-print-directory release CANARY_VERSION="$CANARY_VERSION" CANARY_TAG="$canary_tag" 2>&1 1>&3; \
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
# The image and its SBOM attestation (docs/adr/0072 §2, §4).
rec=$(jq -c '{image: (.image // ""), sbom: (.sbom // null)}' "$RELEASE_RECORD" 2>/dev/null) || rec='{"image": ""}'
jq -cn --arg state "$state" --arg v "$CANARY_VERSION" --arg verdict "$verdict" --argjson numbers "$numbers" --argjson rec "$rec" \
  '{state: $state, release: ({version: $v, verdict: $verdict, numbers: $numbers} + $rec)}'

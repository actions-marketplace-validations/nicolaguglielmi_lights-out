#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# The M62 proof for CircleCI (docs/adr/0095 §8), `./go demo-circleci`, as far
# as it goes without a CircleCI account. `circleci local execute` runs no
# machine job, and the recipe is one, so this is not a CircleCI run. It is
# exactly two things:
#   1. `circleci config validate` on surfaces/circleci/config.yml, in the
#      CLI's own image (circleci/circleci-cli 1.15.0-alpine, pinned by digest)
#   2. the recipe's `lights-out gates` step, cut from the file between its
#      `# lights-out:begin` and `# lights-out:end` lines, run in a shell with
#      git, curl, jq and the engine's socket, as a machine executor provides
#      them, with the environment a CircleCI job sets (CIRCLE_SHA1,
#      CIRCLE_BRANCH), on a clone of a local Gitea PR's head whose main
#      carries the recipe as .circleci/config.yml: GO when the step printed
#      a GO line and Gitea shows it as lights-out/circleci on the head,
#      success, the line (cut at 140) as the description, and no status
#      named gates or review
# Host-side, as demo-jenkins is; a Gitea of its own on a network of its own.
# LIGHTS_OUT_IMAGE, when set, is the gates image the step runs; else the
# wrapper's own published version.
set -eu
name=demo-circleci
. ci/lib.sh

engine=${CONTAINER_ENGINE:?CONTAINER_ENGINE not set; run this via ./go demo-circleci}
here=$(pwd -P)
start=$(date +%s)
# The newest CLI on 2026-11-16 (docs/adr/0095), pinned.
cli_image=docker.io/circleci/circleci-cli:1.15.0-alpine@sha256:801ee1f4a01700e63f77f235f2d23f54e9e3786d06788b39874bf5c689b3de3a
# The shell the surface demos run in: the docker CLI, git, curl, jq; root
# on files the host user owns, so git trusts every directory.
tools_file='FROM docker.io/library/docker:29-cli
RUN apk add --no-cache git curl jq >/dev/null && git config --system --add safe.directory "*"'
tools_image="localhost/lights-out-surface-tools:$(printf '%s' "$tools_file" | cksum | cut -d' ' -f1)"
gitea_image=$(awk '/^  gitea:$/ { f = 1 } f && /^    image:/ { print $2; exit }' compose.yaml)
[ -n "$gitea_image" ] || nogo "no gitea image in compose.yaml"
recipe=surfaces/circleci/config.yml
run_id=$(date -u +%Y%m%d%H%M%S)-$$
net=lights-out-circleci-$run_id
gitea=lights-out-circleci-gitea-$run_id
work=$here/.crew/circleci/$run_id
pw=lights-out-local-not-a-secret
say() { printf '[demo-circleci] %s\n' "$*" >&2; }

cleanup() {
  ec=$?
  "$engine" rm -f "$gitea" >/dev/null 2>&1 || :
  "$engine" network rm "$net" >/dev/null 2>&1 || :
  "$engine" run --rm -v "$here/.crew/circleci:/c" --entrypoint rm "$tools_image" -rf "/c/$run_id" >/dev/null 2>&1 || rm -rf "$work"
  exit "$ec"
}
trap cleanup EXIT INT TERM
mkdir -p "$work"

if [ "$engine" = podman ]; then
  sock=$(podman info --format '{{.Host.RemoteSocket.Path}}'); sock=${sock#unix://}
else
  sock=${DOCKER_HOST:-}; sock=${sock#unix://}; [ -n "$sock" ] || sock=/var/run/docker.sock
fi
[ -n "$sock" ] || nogo "$engine has no API socket for the step"

# --- 1. the configuration ------------------------------------------------------
cp "$recipe" "$work/config.yml"
if ! "$engine" run --rm --security-opt label=disable -v "$work:/cfg:ro" "$cli_image" \
    circleci config validate --skip-update-check /cfg/config.yml > "$work/validate.log" 2>&1; then
  sed 's/^/  [circleci] /' "$work/validate.log" >&2
  nogo "circleci config validate refused $recipe"
fi
sed 's/^/  [circleci] /' "$work/validate.log" >&2

# --- 2. the step -----------------------------------------------------------------
if ! "$engine" image inspect "$tools_image" >/dev/null 2>&1; then
  printf '%s\n' "$tools_file" \
    | "$engine" build -t "$tools_image" -f - "$work" >&2 || nogo "the tools image did not build"
fi
# agent ENTRYPOINT ARGS...: one command in the tools image, on the network.
agent() {
  ep=$1
  shift
  "$engine" run --rm -i --network "$net" --security-opt label=disable \
    -v "$work:$work" --entrypoint "$ep" "$tools_image" "$@"
}
# The step, as the recipe holds it: the lines between the markers, dedented.
awk '/# lights-out:begin$/ { f = 1; match($0, /^ */); n = RLENGTH; next }
     /# lights-out:end$/ { f = 0 }
     f { print substr($0, n + 1) }' "$recipe" > "$work/step.sh"
grep -q 'lights-out gates' "$work/step.sh" || nogo "no lights-out gates step between the markers in $recipe"

PR_RECIPE=$recipe
PR_RECIPE_AT=.circleci/config.yml
# shellcheck source=surfaces/gitea-pr.sh
. surfaces/gitea-pr.sh

ws=$work/ws
agent git clone -q "http://$gitea:3000/lights-out/minimal.git" "$ws" >&2 || nogo "could not clone the PR's repository"
agent git -c safe.directory='*' -C "$ws" checkout -q "$head" || nogo "could not check out $head"
say "the recipe's step on PR #$number's head, as a machine job would run it"
image_flag=""
[ -z "${LIGHTS_OUT_IMAGE:-}" ] || image_flag="-e LIGHTS_OUT_IMAGE"
export LIGHTS_OUT_STATUS_TOKEN="$token" LIGHTS_OUT_STATUSES="$api/repos/lights-out/minimal/statuses"
# shellcheck disable=SC2086 # image_flag is a flag string, split on purpose
if "$engine" run --rm --network "$net" --security-opt label=disable \
    -v "$sock:/var/run/docker.sock" -v "$work:$work" -v "$here/lights-out:/usr/local/bin/lights-out:ro" \
    -w "$ws" -e HOME=/root -e CIRCLE_SHA1="$head" -e CIRCLE_BRANCH=version -e CIRCLE_WORKING_DIRECTORY="$ws" \
    -e LIGHTS_OUT_OUT="$work/out" -e LIGHTS_OUT_STATUS_TOKEN -e LIGHTS_OUT_STATUSES $image_flag \
    --entrypoint sh "$tools_image" -c 'git config --global --add safe.directory "*" && exec sh -e "$1"' sh "$work/step.sh" \
    > "$work/step.log" 2>&1; then
  src=0
else
  src=$?
fi
unset LIGHTS_OUT_STATUS_TOKEN
sed 's/^/  [step] /' "$work/step.log" | tail -n 40 >&2
line=$(sed -n 's/^lights-out line: //p' "$work/step.log" | tail -n 1)
[ -n "$line" ] || nogo "the step printed no lights-out line (exit $src)"
case "$line" in
  "GO: gates — "*) ;;
  *) nogo "the step judged the change: [$line]" ;;
esac
[ "$src" -eq 0 ] || nogo "the line is GO and the step still failed (exit $src)"

statuses=$(agent curl -fsS "$api/repos/lights-out/minimal/commits/$head/statuses") || nogo "could not read the statuses of $head"
mine=$(printf '%s' "$statuses" | agent jq -c '[.[] | select(.context == "lights-out/circleci")] | first // empty')
[ -n "$mine" ] || nogo "no lights-out/circleci status on $head: $statuses"
state=$(printf '%s' "$mine" | agent jq -r .status)
desc=$(printf '%s' "$mine" | agent jq -r .description)
[ "$state" = success ] || nogo "the lights-out/circleci status is $state, the line was GO"
case "$line" in
  "$desc") ;;
  "$desc"*) [ "${#desc}" -ge 100 ] || nogo "the status says [$desc], the step printed [$line]" ;;
  *) nogo "the status says [$desc], the step printed [$line]" ;;
esac
others=$(printf '%s' "$statuses" | agent jq -r '[.[] | select(.context == "gates" or .context == "review")] | length')
[ "$others" = 0 ] || nogo "a surface posted under the tower's own contexts: $statuses"

go_with "config validated by circleci 1.15.0; the recipe's step posted [$line] as lights-out/circleci on PR #$number, $(( $(date +%s) - start ))s"

#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# package/build.sh ENGINE TAG [build flags...]: builds a lights-out image
# (docs/adr/0045 §1, 0057 §3), on the host, with the engine given
# ("podman", "docker", or "docker buildx" for the multi-platform publish).
# PACKAGE_FLAVOUR picks which:
#
#   full (default)  the workbench stage with the lights-out tree inside:
#                   ghcr.io/nicolaguglielmi/lights-out
#   gates           the gates stage with the same tree: init and the gates
#                   only, ghcr.io/nicolaguglielmi/lights-out-gates
#
# One throwaway build context, assembled here:
#
#   fetch.sh pyproject.toml uv.lock   the workbench's own inputs
#   lights-out/                       the committed tree, from git archive HEAD
#   Containerfile                     workbench/Containerfile, then for gates a
#                                     `FROM gates` line, then package/Containerfile.tail
#
# so the same file builds with podman build, docker build and docker buildx
# build --platform, and only committed files enter the image: a .env, the
# cosign key under .crew/ or an .attached/ clone never can. Not a gate:
# stderr only, the engine's exit code.
set -eu
engine=${1:?usage: package/build.sh <engine> <tag> [build flags...]}
tag=${2:?usage: package/build.sh <engine> <tag> [build flags...]}
shift 2

# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
flavour=${PACKAGE_FLAVOUR:-full}
case "$flavour" in
  full|gates) ;;
  *) printf 'package: PACKAGE_FLAVOUR=%s is not full or gates\n' "$flavour" >&2; exit 1 ;;
esac
version=$(sed -n 's/^version=//p' "$here/lights-out")
[ -n "$version" ] || { printf 'package: no version= line in %s/lights-out\n' "$here" >&2; exit 1; }
revision=$(git -C "$here" rev-parse HEAD)
[ -z "$(git -C "$here" status --porcelain)" ] \
  || printf 'package: the checkout has uncommitted changes; the image holds HEAD (%s), not them\n' "$(git -C "$here" rev-parse --short HEAD)" >&2

ctx=$(mktemp -d)
trap 'rm -rf "$ctx"' EXIT
cp "$here/workbench/fetch.sh" "$here/workbench/pyproject.toml" "$here/workbench/uv.lock" "$ctx/"
mkdir "$ctx/lights-out"
git -C "$here" archive HEAD | tar -x -C "$ctx/lights-out"
{
  cat "$here/workbench/Containerfile"
  # The tail lands on the last stage: the workbench for full; for gates a
  # stage of its own on the gates stage, so the workbench stage is never
  # needed (BuildKit and buildah skip it).
  [ "$flavour" = full ] || printf '\nFROM gates AS lights-out-gates\n'
  cat "$here/package/Containerfile.tail"
} > "$ctx/Containerfile"

printf 'package: building %s (lights-out %s, %s, at %s) with %s\n' "$tag" "$version" "$flavour" "$(git -C "$here" rev-parse --short HEAD)" "$engine" >&2
# shellcheck disable=SC2086 # "docker buildx" is two words on purpose
$engine build -t "$tag" \
  --build-arg LIGHTS_OUT_VERSION="$version" --build-arg LIGHTS_OUT_REVISION="$revision" \
  --build-arg LIGHTS_OUT_FLAVOUR="$flavour" \
  "$@" -f "$ctx/Containerfile" "$ctx"

#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# package/build.sh ENGINE TAG [build flags...]: builds the lights-out image
# (docs/adr/0045 §1), the workbench with the lights-out tree inside, on the
# host, with the engine given ("podman", "docker", or "docker buildx" for
# the multi-platform publish). One throwaway build context, assembled here:
#
#   fetch.sh pyproject.toml uv.lock   the workbench's own inputs
#   lights-out/                       the committed tree, from git archive HEAD
#   Containerfile                     workbench/Containerfile + package/Containerfile.tail
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
cat "$here/workbench/Containerfile" "$here/package/Containerfile.tail" > "$ctx/Containerfile"

printf 'package: building %s (lights-out %s at %s) with %s\n' "$tag" "$version" "$(git -C "$here" rev-parse --short HEAD)" "$engine" >&2
# shellcheck disable=SC2086 # "docker buildx" is two words on purpose
$engine build -t "$tag" \
  --build-arg LIGHTS_OUT_VERSION="$version" --build-arg LIGHTS_OUT_REVISION="$revision" \
  "$@" -f "$ctx/Containerfile" "$ctx"

#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-engine-compat: HOST-side gate, run by ./go before it ever enters
# workbench (docs/adr/0004-containerised-toolchain.md point 4, amended by
# docs/adr/0012 §5). It is the first stage of `./go demo`, never a step of
# `make ci`: inside workbench (LIGHTS_OUT_WORKBENCH=1) this file exists only
# so ci/contract.sh can shape-check it, and it must say so instantly, with
# no engine work attempted.
set -eu
name=engine-compat
. ci/lib.sh

[ "${LIGHTS_OUT_WORKBENCH:-}" != "1" ] || nogo "host-side gate, run ./go engine-compat on the host"

docker_is_shim=0
if command -v podman >/dev/null 2>&1; then
  podman --version >&2
fi
if command -v docker >/dev/null 2>&1; then
  docker_version=$(docker --version)
  case "$docker_version" in
    'Docker version'*) printf '%s\n' "$docker_version" >&2 ;;
    *)
      docker_is_shim=1
      printf 'docker: shim of podman, not a real docker (not tested)\n' >&2 ;;
  esac
fi

[ -n "${CONTAINER_ENGINE:-}" ] || nogo "CONTAINER_ENGINE is not set; run this via ./go engine-compat"

if [ "$CONTAINER_ENGINE" = docker ] && [ "$docker_is_shim" -eq 1 ]; then
  nogo "CONTAINER_ENGINE=docker is a podman shim; test podman directly"
fi

# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
repo_go="$here/go"

CONTAINER_ENGINE="$CONTAINER_ENGINE" "$repo_go" up >&2 || nogo "./go up failed (see stderr)"
CONTAINER_ENGINE="$CONTAINER_ENGINE" "$repo_go" smoke >&2 || nogo "./go smoke failed (see stderr)"

go

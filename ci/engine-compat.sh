#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-engine-compat: HOST-side gate, run outside workbench, needs no tool
# beyond sh (docs/adr/0004-containerised-toolchain.md, point 4). Not part of
# `make ci` and not called by anything at M0; it exists so the gate is real
# from day one. Wired into `make ci` at M2.
set -eu
name=engine-compat
. ci/lib.sh

if command -v podman >/dev/null 2>&1; then
  podman --version >&2
fi

if command -v docker >/dev/null 2>&1; then
  docker_version=$(docker --version)
  case "$docker_version" in
    'Docker version'*) printf '%s\n' "$docker_version" >&2 ;;
    *) printf 'docker: shim of podman, not a real docker (not tested)\n' >&2 ;;
  esac
fi

nogo "nothing to check before M2"

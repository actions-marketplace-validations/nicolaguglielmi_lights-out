#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# lights-out entrypoint. The only things the host needs are a container
# engine, git and this shell. Everything else runs inside the workbench image
# built from workbench/Containerfile (docs/adr/0004-containerised-toolchain.md).
#
#   ./go help      list the make targets
#   ./go ci        repo self-checks, no engine socket inside
#   ./go demo      the demo, as far as the current milestone takes it
#   ./go shell     interactive shell inside workbench
#   ./go clean     remove the workbench image
#
# Any other argument is passed to make inside workbench.
set -eu

# Inside workbench there is nothing to wrap: run make directly.
if [ "${LIGHTS_OUT_WORKBENCH:-}" = "1" ]; then
  exec make "$@"
fi

# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
containerfile="$here/workbench/Containerfile"
image="localhost/lights-out-workbench:$(cksum "$containerfile" | cut -d' ' -f1)"
cmd="${1:-help}"
[ $# -gt 0 ] && shift

die() { printf 'go: %s\n' "$*" >&2; exit 1; }

# 1. Pick the engine: CONTAINER_ENGINE, then podman, then docker.
if [ -n "${CONTAINER_ENGINE:-}" ]; then
  engine="$CONTAINER_ENGINE"
  command -v "$engine" >/dev/null 2>&1 || die "CONTAINER_ENGINE=$engine is not on PATH"
elif command -v podman >/dev/null 2>&1; then
  engine=podman
elif command -v docker >/dev/null 2>&1; then
  engine=docker
else
  die "no container engine found. Install podman (reference) or docker, or set CONTAINER_ENGINE."
fi

if [ "$cmd" = clean ]; then
  "$engine" image rm -f "$image" >/dev/null 2>&1 || true
  printf 'go: removed %s\n' "$image"
  exit 0
fi

# 2. Build the workbench image once per Containerfile revision.
if ! "$engine" image inspect "$image" >/dev/null 2>&1; then
  printf 'go: building workbench with %s, the first run takes a few minutes\n' "$engine" >&2
  "$engine" build -t "$image" -f "$containerfile" "$here/workbench"
fi

# 3. Run flags. The repo is mounted at the same absolute path as on the host so
# that paths written by tools inside workbench are valid outside, and back.
tty="-i"
[ -t 0 ] && tty="-it"
label=""
[ -d /sys/fs/selinux ] && label=":z"

# Engine-specific flags. Two branches is the ceiling (ADR 0004).
engine_flags=""
if [ "$engine" = docker ]; then
  engine_flags="--user $(id -u):$(id -g) -e HOME=/tmp --add-host host.containers.internal:host-gateway"
fi

# 4. Targets that drive the engine get its socket. This hands workbench full
# control of the engine; the README says so.
socket_flags=""
case "$cmd" in
  up|down|demo|demo-rollback|e2e|shell)
    if [ "$engine" = podman ]; then
      sock=$(podman info --format '{{.Host.RemoteSocket.Path}}'); sock=${sock#unix://}
      [ -n "$sock" ] || die "podman reports no API socket. Enable it: systemctl --user enable --now podman.socket"
    else
      sock=${DOCKER_HOST#unix://}
      [ -n "$sock" ] || sock=/var/run/docker.sock
    fi
    # label=disable: the engine's SELinux (podman machine is Fedora CoreOS)
    # would otherwise deny the container access to the socket.
    socket_flags="-v $sock:/var/run/docker.sock -e DOCKER_HOST=unix:///var/run/docker.sock --security-opt label=disable" ;;
esac

# shellcheck disable=SC2086 # flag strings are deliberately word-split
run() {
  exec "$engine" run --rm --init $tty \
    -v "$here:$here$label" -w "$here" \
    -e PROFILE="${PROFILE:-l0}" -e CONTAINER_ENGINE="$engine" \
    $engine_flags $socket_flags \
    "$image" "$@"
}

if [ "$cmd" = shell ]; then
  run sh
else
  run make "$cmd" "$@"
fi

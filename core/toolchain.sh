#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-toolchain (docs/adr/0042 §2, §4): where a workload's declared
# command runs. Sourced after ci/lib.sh by gates/test.sh, gates/sast.sh,
# gates/mutation.sh and core/init.sh; not a gate of its own, so it never
# prints the contract line itself except through nogo on a contract error.
#
#   toolchain_preflight     # NO-GOes on a contract error; sets $toolchain_where
#   run_in_toolchain CMD    # CMD's exit code, or 125 when the toolchain itself failed
#
# toolchain_preflight checks the form of TOOLCHAIN_IMAGE (the workload's
# contract), the socket an engine form needs and the plane half a
# compose form needs, with nogo, and sets $toolchain_where, the text a
# gate puts on its GO line (docs/adr/0042 §3), also written to
# $GATES_OUT/toolchain.where for `make gates`' own line. run_in_toolchain
# then runs CMD, one `sh -c` line, with MUTATION_LINES carried into CMD's
# environment and nothing else of the gate's. CMD's stdout is the caller's
# stdout (a gate captures it: the runner's one JSON line), its stderr
# passes through, and the return is CMD's exit code -- or 125, with one
# "toolchain:" line on stderr, when an image build failed. It never calls
# nogo: a caller captures or redirects its stdout, where a contract line
# would be lost.
#
# Three forms of TOOLCHAIN_IMAGE:
#   workbench            in this container, in-process, no engine: from
#                        $WORKLOAD/$WORKLOAD_TEST_ROOT, with uv and npm
#                        caches under .crew/cache/ and the repository's
#                        venv outside its tree. UV_PYTHON_DOWNLOADS=never:
#                        a Python the workbench lacks fails loudly instead
#                        of being downloaded. Under TOOLCHAIN_ISOLATE=1
#                        (core/steps/ci.sh: the tower never runs a PR's
#                        tests in its own container) it is the image form
#                        below on the workbench image.
#   compose:<service>    a profile-test service of the contract's compose
#                        fragment, built and run under its own project
#                        name, in the image's own working directory, torn
#                        down after: the bundled app's backend-test.
#   <image reference>    a throwaway image built through compose from an
#                        inline Containerfile -- FROM <ref>, COPY . /work
#                        -- so nothing of the host is bind-mounted (the
#                        compose client sends the context over the socket,
#                        which is why a worktree in this container's /tmp
#                        works too) and CMD cannot write into the clone.
#                        Named volumes keep the uv and npm caches.
# The two engine forms need the socket ./go mounts; for gates, init and
# mutation-baseline it is optional (docs/adr/0042 §4), so its absence is a
# NO-GO naming it, never a silent in-process run.

toolchain_form() {  # sets $toolchain_form from TOOLCHAIN_IMAGE, or nogo
  [ -n "${TOOLCHAIN_IMAGE:-}" ] || nogo "TOOLCHAIN_IMAGE is empty (docs/adr/0042 §2)"
  case "$TOOLCHAIN_IMAGE" in
    workbench) toolchain_form=workbench ;;
    compose:) nogo "TOOLCHAIN_IMAGE=compose: names no service" ;;
    compose:*)
      case "${TOOLCHAIN_IMAGE#compose:}" in
        *[!A-Za-z0-9_.-]*) nogo "TOOLCHAIN_IMAGE=$TOOLCHAIN_IMAGE is not compose:<service>" ;;
      esac
      toolchain_form=compose ;;
    *)
      if printf '%s' "$TOOLCHAIN_IMAGE" | grep -Eq '^[a-z0-9]([a-z0-9._/-]*[a-z0-9])?(:[A-Za-z0-9._-]+)?(@sha256:[0-9a-f]{64})?$'; then
        toolchain_form=image
      else
        nogo "TOOLCHAIN_IMAGE=$TOOLCHAIN_IMAGE is none of workbench, compose:<service> or an image reference"
      fi ;;
  esac
}

toolchain_socket() {  # the engine socket ./go mounted, or nothing
  sock=${DOCKER_HOST:-}
  sock=${sock#unix://}
  [ -n "$sock" ] && [ -S "$sock" ] && printf '%s' "$sock"
}

# Writes $toolchain_where for the caller's GO line and for make gates.
toolchain_note_where() {
  toolchain_where=$1
  if [ -n "${GATES_OUT:-}" ] && [ -d "$GATES_OUT" ]; then
    printf '%s\n' "$toolchain_where" > "$GATES_OUT/toolchain.where"
  fi
}

# toolchain_image_run REF CMD: the throwaway-image form, preflight done.
toolchain_image_run() {
  ref=$1
  cmd=$2
  # shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
  context=$(CDPATH= cd -- "$WORKLOAD" && pwd -P)
  tc_dir=$(mktemp -d)
  # A compose file of our own: build context the workload's root, the
  # Containerfile beside this file (the classic builder, DOCKER_BUILDKIT=0
  # in the Makefile, reads it from the client side). The project name is
  # ours, never the plane's, so `down` here never touches a running plane.
  cat > "$tc_dir/Containerfile" <<EOF
FROM $ref
COPY . /work
WORKDIR /work
EOF
  cat > "$tc_dir/compose.yaml" <<EOF
services:
  toolchain:
    build:
      context: $context
      dockerfile: $tc_dir/Containerfile
    working_dir: /work/${WORKLOAD_TEST_ROOT:-}
    environment:
      MUTATION_LINES: ${MUTATION_LINES:-}
      UV_LINK_MODE: copy
      NO_COLOR: "1"
    volumes:
      - lo-toolchain-uv:/root/.cache/uv
      - lo-toolchain-npm:/root/.npm
volumes:
  lo-toolchain-uv: {}
  lo-toolchain-npm: {}
EOF
  # `run --build` would put its own image-build log on stdout (confirmed
  # empirically, gates/mutation.sh's comment): built apart, on stderr.
  if ! docker-compose -p lo-toolchain -f "$tc_dir/compose.yaml" build toolchain >&2; then
    rm -rf "$tc_dir"
    printf 'toolchain: the image build on %s failed\n' "$ref" >&2
    return 125
  fi
  docker-compose -p lo-toolchain -f "$tc_dir/compose.yaml" run --rm -T toolchain sh -c "$cmd" </dev/null
  tc_rc=$?
  docker-compose -p lo-toolchain -f "$tc_dir/compose.yaml" down --remove-orphans >/dev/null 2>&1 || :
  rm -rf "$tc_dir"
  return "$tc_rc"
}

toolchain_preflight() {
  : "${WORKLOAD:?WORKLOAD not set; run this via ./go, not directly}"
  toolchain_form
  case "$toolchain_form" in
    workbench)
      if [ "${TOOLCHAIN_ISOLATE:-}" = 1 ]; then
        : "${WORKBENCH_IMAGE:?WORKBENCH_IMAGE not set; run this via ./go, not directly}"
        toolchain_note_where "workbench (isolated)"
        [ -n "$(toolchain_socket)" ] \
          || nogo "in $toolchain_where: the engine socket is not available and TOOLCHAIN_ISOLATE=1 needs the engine"
      else
        toolchain_note_where workbench
      fi ;;
    compose)
      toolchain_note_where "$TOOLCHAIN_IMAGE"
      [ -n "$(toolchain_socket)" ] \
        || nogo "in $TOOLCHAIN_IMAGE: the engine socket is not available and the compose form needs the engine; run with podman or docker up, or set TOOLCHAIN_IMAGE=workbench"
      [ -f "${WORKLOAD_CONTRACT:?WORKLOAD_CONTRACT not set; run this via ./go, not directly}/compose.yaml" ] \
        || nogo "in $TOOLCHAIN_IMAGE: $WORKLOAD_CONTRACT has no compose.yaml; the compose form needs the plane half of the contract (docs/adr/0042 §7)" ;;
    image)
      toolchain_note_where "$TOOLCHAIN_IMAGE"
      [ -n "$(toolchain_socket)" ] \
        || nogo "in $TOOLCHAIN_IMAGE: the engine socket is not available and an image needs the engine; run with podman or docker up, or set TOOLCHAIN_IMAGE=workbench" ;;
  esac
}

run_in_toolchain() {
  cmd=$1
  [ -n "${toolchain_form:-}" ] || { printf 'toolchain: run_in_toolchain called before toolchain_preflight\n' >&2; return 125; }
  case "$toolchain_form" in
    workbench)
      if [ "${TOOLCHAIN_ISOLATE:-}" = 1 ]; then
        toolchain_image_run "$WORKBENCH_IMAGE" "$cmd"
        return $?
      fi
      cache=$(pwd)/.crew/cache
      mkdir -p "$cache/uv" "$cache/npm" "$cache/venv"
      # shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
      venv="$cache/venv/$(printf '%s' "$(CDPATH= cd -- "$WORKLOAD" && pwd -P)" | cksum | cut -d' ' -f1)"
      (
        cd "$WORKLOAD/${WORKLOAD_TEST_ROOT:-}" || exit 125
        MUTATION_LINES="${MUTATION_LINES:-}" UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy \
          UV_CACHE_DIR="$cache/uv" UV_PROJECT_ENVIRONMENT="$venv" npm_config_cache="$cache/npm" \
          NO_COLOR=1 sh -c "$cmd"
      ) ;;
    compose)
      svc=${TOOLCHAIN_IMAGE#compose:}
      # Built apart from the run: `run --build`'s image-build log lands on
      # stdout (gates/mutation.sh's comment). A project name of our own:
      # this run's service and its dependencies never collide with a
      # running plane's, and `down -v` below removes only them.
      if ! docker-compose -p lo-toolchain --profile test build "$svc" >&2; then
        printf 'toolchain: the %s image build failed\n' "$svc" >&2
        return 125
      fi
      docker-compose -p lo-toolchain --profile test run --rm -T \
        -e MUTATION_LINES="${MUTATION_LINES:-}" "$svc" sh -c "$cmd" </dev/null
      tc_rc=$?
      docker-compose -p lo-toolchain --profile test down -v --remove-orphans >/dev/null 2>&1 || :
      return "$tc_rc" ;;
    image)
      toolchain_image_run "$TOOLCHAIN_IMAGE" "$cmd" ;;
  esac
}

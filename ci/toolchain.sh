#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-toolchain: proves docs/adr/0042 §2, §3 and §4 cold: no engine, no
# network, no key. core/toolchain.sh is not a gate, so each case writes a
# throwaway gate into a temp dir that sources the real ci/lib.sh and the
# real core/toolchain.sh (the shape ci/contract.sh uses for its nogo probes)
# and runs it from a temp directory with a clean environment.
#   (a) TOOLCHAIN_IMAGE=workbench (§2): CMD runs in this container, from
#       $WORKLOAD/$WORKLOAD_TEST_ROOT, CMD's stdout is the caller's,
#       MUTATION_LINES is in CMD's environment, UV_PYTHON_DOWNLOADS=never
#       (§2), the return is CMD's exit code, and `workbench` is both
#       $toolchain_where (§3) and the content of $GATES_OUT/toolchain.where.
#   (b) the no-socket path (§4, resolved 6): with DOCKER_HOST unset or
#       naming a path that is not a socket, `compose:<service>`, an image
#       reference, and `workbench` under TOOLCHAIN_ISOLATE=1 (resolved 1)
#       are each one NO-GO line naming the socket, and nothing runs.
#   (c) an unknown form (§2): an empty TOOLCHAIN_IMAGE, `compose:` with no
#       service and a malformed reference are one NO-GO line naming the
#       value; a digest reference is accepted.
#   (d) the compose form needs the plane half (§7): `compose:x` with a
#       contract that has no compose.yaml is a NO-GO naming compose.yaml,
#       even when the socket is there.
#   (e) go_with (§3): `GO: <name> — <detail>` on one line, exit 0, a
#       multi-line detail flattened to one line.
#   (f) the checks can fail: (b) and (c) run against copies of
#       core/toolchain.sh with the socket test and the form test broken,
#       and must report them.
# Written from the ADR, not from core/toolchain.sh; ci/attach.sh's shape.
set -eu
name=toolchain
. ci/lib.sh

for f in ci/lib.sh core/toolchain.sh; do
  [ -f "$f" ] || nogo "$f not found"
done

repo=$(pwd)
t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT
mismatch=""
fail_case() {
  printf 'ci-toolchain: %s: %s\n' "$1" "$2" >&2
  [ -n "$mismatch" ] || mismatch="$1"
}

# The throwaway gate: preflight, then CMD. PROBE_PREFLIGHT_ONLY=1 stops
# after the preflight, so that a case with a real socket never reaches an
# engine call. What it prints beyond a contract line proves how far it got.
cat > "$t/gate.sh" <<'GATE'
set -eu
name=probe
. "$LIB"
. "$TC"
toolchain_preflight
printf 'where=%s\n' "$toolchain_where"
[ -z "${PROBE_PREFLIGHT_ONLY:-}" ] || exit 0
rc=0
run_in_toolchain "${PROBE_CMD:-:}" || rc=$?
printf 'rc=%s\n' "$rc"
GATE

# Two workload roots: wl has a gates-only contract, wlc one with the plane
# half (an empty compose.yaml: the preflight only tests that it is there).
wl="$t/wl"
wlc="$t/wlc"
mkdir -p "$wl/sub" "$wl/.lights-out" "$wlc/.lights-out" "$t/cwd" "$t/gout"
: > "$wlc/.lights-out/compose.yaml"
digest=docker.io/library/node:24@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef

# A real unix socket, which nothing will connect to: preflight refuses
# first, or stops after itself.
sock="$t/s.sock"
python3 -c 'import socket, sys; socket.socket(socket.AF_UNIX).bind(sys.argv[1])' "$sock" 2>"$t/err" \
  || nogo "could not make a unix socket at $sock" "$(cat "$t/err")"
[ -S "$sock" ] || nogo "$sock is not a socket"
: > "$t/not-a-socket"

# probe TC VAR=value...: the throwaway gate against the toolchain file TC,
# from $t/cwd, in an environment of its own; stdout in $t/out, stderr in
# $t/err, exit code in $prc. Later assignments win.
probe() {
  tc=$1
  shift
  (
    cd "$t/cwd" &&
    env -i PATH="$PATH" LIB="$repo/ci/lib.sh" TC="$tc" WORKLOAD="$wl" WORKLOAD_CONTRACT="$wl/.lights-out" \
      WORKBENCH_IMAGE=lo-workbench-test "$@" sh "$t/gate.sh"
  ) >"$t/out" 2>"$t/err" && prc=0 || prc=$?
}

# nogo_flaw WANT...: what is wrong with the last probe as a one-line NO-GO
# naming every WANT, or nothing.
nogo_flaw() {
  [ "$prc" -eq 1 ] || { printf 'exit %s, want 1' "$prc"; return; }
  [ "$(awk 'END{print NR}' "$t/out")" -eq 1 ] || { printf 'stdout has %s lines, want 1' "$(awk 'END{print NR}' "$t/out")"; return; }
  case "$(cat "$t/out")" in
    "NO-GO: probe — "?*) : ;;
    *) printf 'not a NO-GO line: %s' "$(cat "$t/out")"; return ;;
  esac
  for want in "$@"; do
    grep -qF -- "$want" "$t/out" || { printf 'the line does not name %s: %s' "$want" "$(cat "$t/out")"; return; }
  done
}

# socket_flaw TC: the (b) check against the toolchain file TC.
socket_flaw() {
  tc=$1
  rm -f "$t/ran"
  for dh in unset "unix://$t/missing.sock" "$t/missing.sock" "$t/not-a-socket" "unix://$t/not-a-socket" "unix://$t"; do
    for form in compose:backend-test node:24 "$digest" ghcr.io/astral-sh/uv:python3.12-trixie-slim workbench; do
      if [ "$dh" = unset ]; then dhv="UNRELATED=1"; else dhv="DOCKER_HOST=$dh"; fi
      iso="UNRELATED=1"
      [ "$form" != workbench ] || iso="TOOLCHAIN_ISOLATE=1"
      probe "$tc" WORKLOAD_CONTRACT="$wlc/.lights-out" TOOLCHAIN_IMAGE="$form" PROBE_CMD="touch $t/ran" "$dhv" "$iso"
      flaw=$(nogo_flaw socket)
      [ -z "$flaw" ] || { printf 'TOOLCHAIN_IMAGE=%s, DOCKER_HOST=%s: %s' "$form" "$dh" "$flaw"; return; }
      [ ! -e "$t/ran" ] || { printf 'TOOLCHAIN_IMAGE=%s, DOCKER_HOST=%s: CMD ran with no socket' "$form" "$dh"; return; }
    done
  done
}

# form_flaw TC: the (c) check against the toolchain file TC. A real socket
# and the plane half are in place, so only the form can be at fault.
form_flaw() {
  tc=$1
  probe "$tc" WORKLOAD_CONTRACT="$wlc/.lights-out" DOCKER_HOST="unix://$sock" PROBE_PREFLIGHT_ONLY=1
  flaw=$(nogo_flaw TOOLCHAIN_IMAGE)
  [ -z "$flaw" ] || { printf 'TOOLCHAIN_IMAGE unset: %s' "$flaw"; return; }
  for bad in "" "compose:" "compose:a b" "Not An Image" "node 24" "Docker.IO/Library/Node:24" \
    "docker.io/library/node:24@sha256:abc"; do
    probe "$tc" WORKLOAD_CONTRACT="$wlc/.lights-out" DOCKER_HOST="unix://$sock" PROBE_PREFLIGHT_ONLY=1 TOOLCHAIN_IMAGE="$bad"
    if [ -z "$bad" ]; then flaw=$(nogo_flaw TOOLCHAIN_IMAGE); else flaw=$(nogo_flaw "$bad"); fi
    [ -z "$flaw" ] || { printf 'TOOLCHAIN_IMAGE=%s: %s' "$bad" "$flaw"; return; }
  done
}

# (a) the workbench form, in-process.
want_dir=$(cd "$wl/sub" && pwd -P)
# shellcheck disable=SC2016 # the $ are the throwaway gate's CMD's, expanded when it runs
cmd_a='pwd -P; echo "ml=$MUTATION_LINES"; echo "uvdl=$UV_PYTHON_DOWNLOADS"; echo noise >&2; exit 7'
probe "$repo/core/toolchain.sh" TOOLCHAIN_IMAGE=workbench WORKLOAD_TEST_ROOT=sub MUTATION_LINES=src/a.py:1-3 \
  GATES_OUT="$t/gout" PROBE_CMD="$cmd_a"
printf 'where=workbench\n%s\nml=src/a.py:1-3\nuvdl=never\nrc=7\n' "$want_dir" > "$t/want"
if ! cmp -s "$t/want" "$t/out"; then
  fail_case a-workbench "stdout is not the where line, CMD's stdout (from \$WORKLOAD/\$WORKLOAD_TEST_ROOT, MUTATION_LINES, UV_PYTHON_DOWNLOADS=never) and rc=7: want"
  cat "$t/want" >&2
  printf 'got (exit %s):\n' "$prc" >&2
  cat "$t/out" "$t/err" >&2
fi
[ "$prc" -eq 0 ] || fail_case a-workbench "the gate exited $prc, want 0 (CMD's 7 is returned, not fatal)"
grep -qx noise "$t/err" || fail_case a-stderr "CMD's stderr did not pass through to stderr"
[ "$(cat "$t/gout/toolchain.where" 2>/dev/null)" = workbench ] \
  || fail_case a-where "\$GATES_OUT/toolchain.where holds '$(cat "$t/gout/toolchain.where" 2>/dev/null)', want workbench"
# CMD's own success, an empty test root (the workload's root) and no GATES_OUT.
probe "$repo/core/toolchain.sh" TOOLCHAIN_IMAGE=workbench PROBE_CMD='pwd -P'
want_root=$(cd "$wl" && pwd -P)
printf 'where=workbench\n%s\nrc=0\n' "$want_root" > "$t/want"
cmp -s "$t/want" "$t/out" || fail_case a-root "with no WORKLOAD_TEST_ROOT and no GATES_OUT: want the workload root and rc=0, got: $(tr '\n' '|' <"$t/out")"
# shellcheck disable=SC2016 # the $ is the throwaway gate's CMD's
probe "$repo/core/toolchain.sh" TOOLCHAIN_IMAGE=workbench PROBE_CMD='echo "ml=[${MUTATION_LINES:-}]"'
grep -qx 'ml=\[\]' "$t/out" || fail_case a-unset "with MUTATION_LINES unset CMD printed: $(tr '\n' '|' <"$t/out")"

# (b) no socket, no engine form.
flaw=$(socket_flaw "$repo/core/toolchain.sh")
[ -z "$flaw" ] || fail_case b-no-socket "$flaw"
# The control: with a real socket the same forms pass the preflight and say where.
for form in compose:backend-test "$digest" node:24; do
  probe "$repo/core/toolchain.sh" WORKLOAD_CONTRACT="$wlc/.lights-out" DOCKER_HOST="unix://$sock" \
    PROBE_PREFLIGHT_ONLY=1 TOOLCHAIN_IMAGE="$form"
  { [ "$prc" -eq 0 ] && grep -qF "where=" "$t/out" && grep -qF "$form" "$t/out"; } \
    || fail_case b-control "TOOLCHAIN_IMAGE=$form with a real socket: exit $prc, stdout: $(tr '\n' '|' <"$t/out")"
done
probe "$repo/core/toolchain.sh" TOOLCHAIN_IMAGE=workbench TOOLCHAIN_ISOLATE=1 DOCKER_HOST="unix://$sock" PROBE_PREFLIGHT_ONLY=1
{ [ "$prc" -eq 0 ] && grep -qF isolated "$t/out"; } \
  || fail_case b-isolated "workbench under TOOLCHAIN_ISOLATE=1 with a socket: exit $prc, want 0 and 'isolated' on the where line: $(tr '\n' '|' <"$t/out")"

# (c) the form.
flaw=$(form_flaw "$repo/core/toolchain.sh")
[ -z "$flaw" ] || fail_case c-form "$flaw"
for ok in workbench compose:backend-test docker.io/library/node:24 "$digest" ghcr.io/astral-sh/uv:python3.12-trixie-slim; do
  probe "$repo/core/toolchain.sh" WORKLOAD_CONTRACT="$wlc/.lights-out" DOCKER_HOST="unix://$sock" PROBE_PREFLIGHT_ONLY=1 TOOLCHAIN_IMAGE="$ok"
  [ "$prc" -eq 0 ] || fail_case c-accept "TOOLCHAIN_IMAGE=$ok was refused: $(cat "$t/out")"
done
# The digest form without a socket is refused for the socket, not the form.
probe "$repo/core/toolchain.sh" TOOLCHAIN_IMAGE="$digest"
flaw=$(nogo_flaw socket)
[ -z "$flaw" ] || fail_case c-digest "the digest form with no socket: $flaw"

# (d) compose: needs compose.yaml, socket or not.
probe "$repo/core/toolchain.sh" TOOLCHAIN_IMAGE=compose:x DOCKER_HOST="unix://$sock" PROBE_PREFLIGHT_ONLY=1
flaw=$(nogo_flaw compose.yaml)
[ -z "$flaw" ] || fail_case d-plane "compose:x, a contract with no compose.yaml and a socket: $flaw"

# (e) go_with.
cat > "$t/go-with.sh" <<'GATE'
set -eu
name=probe
. "$LIB"
go_with "$DETAIL"
GATE
cat > "$t/go-plain.sh" <<'GATE'
set -eu
name=probe
. "$LIB"
go
GATE
go_with_probe() {  # DETAIL
  env -i PATH="$PATH" LIB="$repo/ci/lib.sh" DETAIL="$1" sh "$t/go-with.sh" >"$t/out" 2>"$t/err" && prc=0 || prc=$?
}
go_with_probe "in docker.io/library/node:24@sha256:abc"
{ [ "$prc" -eq 0 ] && [ "$(cat "$t/out")" = "GO: probe — in docker.io/library/node:24@sha256:abc" ]; } \
  || fail_case e-go-with "go_with 'in …': exit $prc, stdout: $(cat "$t/out")"
go_with_probe "first
second"
{ [ "$prc" -eq 0 ] && [ "$(awk 'END{print NR}' "$t/out")" -eq 1 ] \
  && case "$(cat "$t/out")" in "GO: probe — first"*second*) true ;; *) false ;; esac; } \
  || fail_case e-flatten "a two-line detail: exit $prc, stdout: $(cat "$t/out")"
env -i PATH="$PATH" LIB="$repo/ci/lib.sh" sh "$t/go-plain.sh" >"$t/out" 2>/dev/null && prc=0 || prc=$?
{ [ "$prc" -eq 0 ] && [ "$(cat "$t/out")" = "GO: probe" ]; } || fail_case e-go "go: exit $prc, stdout: $(cat "$t/out")"

# (f) the checks can fail. A function appended to a copy of the file
# replaces the original: the socket test that always finds a socket, and the
# form test that accepts anything as an image.
cp core/toolchain.sh "$t/no-socket-test.sh"
printf '\ntoolchain_socket() { printf /anything; }\n' >> "$t/no-socket-test.sh"
cp core/toolchain.sh "$t/no-form-test.sh"
printf '\ntoolchain_form() { toolchain_form=image; }\n' >> "$t/no-form-test.sh"
[ -n "$(socket_flaw "$t/no-socket-test.sh")" ] || fail_case f-socket "check (b) accepted a toolchain with no socket test"
[ -n "$(form_flaw "$t/no-form-test.sh")" ] || fail_case f-form "check (c) accepted a toolchain with no form test"

[ -z "$mismatch" ] || nogo "case $mismatch failed; see stderr"

go

#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-preflight (docs/adr/0093 §1): on the host, before the plane, for
# `./go demo` and `./go up`. Host shell, because it runs before any image
# exists (docs/adr/0052 §1). Run from the checkout's root, with
# CONTAINER_ENGINE set by ./go.
#
#   sh core/preflight.sh machine   a stopped podman machine on macOS or
#                                  Windows is started (§1a); silent when
#                                  there is nothing to do
#   sh core/preflight.sh           memory (§1b), disk (§1c), ports (§1d):
#                                  one stderr line each, then GO or NO-GO
#
# A busy port that can move is moved to the next free one, written to
# .crew/ports.env, which the Makefile reads before .env.
set -eu
name=preflight
. ci/lib.sh

engine=${CONTAINER_ENGINE:?CONTAINER_ENGINE is not set; run this through ./go}
os=${PREFLIGHT_OS:-$(uname -s)}
item() { printf 'preflight: %-8s %s\n' "$1" "$2" >&2; }

# §1a. The machine.
if [ "${1:-}" = machine ]; then
  [ "$engine" = podman ] || exit 0
  case "$os" in Darwin|MINGW*|MSYS*) ;; *) exit 0 ;; esac
  list=$(podman machine list --format '{{.Name}}|{{.Running}}|{{.Default}}' --noheading 2>/dev/null || :)
  [ -n "$list" ] || exit 0
  ! printf '%s\n' "$list" | grep -q '|true|' || exit 0
  m=$(printf '%s\n' "$list" | awk -F'|' '$3 == "true" { print $1; exit }')
  [ -n "$m" ] || m=$(printf '%s\n' "$list" | head -n 1 | cut -d'|' -f1)
  m=${m%\*}
  item machine "podman machine $m is stopped: starting it (podman machine start $m)"
  podman machine start "$m" >&2 || nogo "podman machine start $m failed; start it yourself, then run ./go again"
  exit 0
fi

here=$(pwd -P)
envval() { sed -n "s/^$1=//p" "$2" 2>/dev/null | tail -n 1; }

# §1b. Memory: a warning, never a stop.
case "$engine" in podman) f='{{.Host.MemTotal}}' ;; *) f='{{.MemTotal}}' ;; esac
mem=$("$engine" info --format "$f" 2>/dev/null || :)
case "$mem" in
  ''|*[!0-9]*) item memory "not checked: $engine did not say" ;;
  *) mib=$((mem / 1048576))
     if [ "$mib" -lt 3800 ]; then
       item memory "only $mib MiB for the engine, under the 3800 MiB a 4 GiB machine reports: the plane may run short. Grow it: podman machine stop; podman machine set --memory 6144; podman machine start"
     else
       item memory "ok, $mib MiB"
     fi ;;
esac

# §1c. Disk: free space in the engine's store.
need_mb=${PREFLIGHT_DISK_NEED_MB:-6000}
free=""
if [ "$engine" = podman ]; then
  d=$("$engine" info --format '{{.Store.GraphRootAllocated}} {{.Store.GraphRootUsed}}' 2>/dev/null || :)
  alloc=${d% *}; used=${d#* }
  case "$alloc$used" in ''|*[!0-9]*) ;; *) free=$(( (alloc - used) / 1000000 )) ;; esac
else
  root=$("$engine" info --format '{{.DockerRootDir}}' 2>/dev/null || :)
  [ -z "$root" ] || [ ! -r "$root" ] || free=$(df -Pk "$root" 2>/dev/null | awk 'NR == 2 { print int($4 * 1024 / 1000000) }')
fi
if [ -z "$free" ]; then
  item disk "not checked: $engine did not say how much its store has free"
elif [ "$free" -lt "$need_mb" ]; then
  nogo "$free MB free in $engine's store, the demo needs $need_mb MB: free space with '$engine system prune' (it removes stopped containers and unused images), then run ./go again"
else
  item disk "ok, $free MB free in $engine's store (the demo needs $need_mb MB)"
fi

# §1d. Ports. Detection must see every owner's socket (ss, nc, curl);
# lsof, which on most hosts sees only this user's, only names a holder.
if command -v ss >/dev/null 2>&1; then probe=ss
elif command -v nc >/dev/null 2>&1; then probe=nc
elif command -v curl >/dev/null 2>&1 && curl -V 2>/dev/null | grep -q telnet; then probe=curl
else probe=""
fi
busy() {
  case "$probe" in
    ss) ss -ltnH 2>/dev/null | awk '{ print $4 }' | grep -q "[:.]$1\$" ;;
    nc) nc -z 127.0.0.1 "$1" >/dev/null 2>&1 || nc -z ::1 "$1" >/dev/null 2>&1 ;;
    curl) rc=0; curl -s -o /dev/null --max-time 1 "telnet://127.0.0.1:$1" </dev/null 2>/dev/null || rc=$?; [ "$rc" -ne 7 ] ;;
  esac
}
holder() {
  h=$(lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | awk 'NR == 2 { print $1 " (pid " $2 ")" }' || :)
  printf '%s' "${h:-another process}"
}
if [ -z "$probe" ]; then
  item ports "not checked: no ss, nc or curl with telnet on this host"
  go
fi

# The lights-out project's containers: this checkout's, or another's.
plane=$("$engine" ps --filter label=com.docker.compose.project=lights-out \
  --format '{{.Label "com.docker.compose.project.working_dir"}}|{{.Ports}}' 2>/dev/null || :)
other=$(printf '%s\n' "$plane" | awk -F'|' -v h="$here" 'NF && $1 != h && index($1, h "/") != 1 { print $1; exit }')
[ -z "$other" ] || nogo "a lights-out plane started from $other is running and holds the plane's ports: run ./go down there first"
ours() { printf '%s\n' "$plane" | grep -q "[:]$1->"; }

taken=" 5050 "
moved=""
moves=""
for spec in "APP_PORT 8080 the app" "GITEA_PORT 3000 Gitea" "PROMETHEUS_PORT 9090 Prometheus" \
            "ENVOY_ADMIN_PORT 9901 Envoy's admin" "FLAGD_PORT 8016 flagd"; do
  # shellcheck disable=SC2086 # one spec, split into its words
  set -- $spec
  var=$1; def=$2; shift 2; what=$*
  set_in_env=$(envval "$var" .env)
  if [ -n "$set_in_env" ]; then
    if busy "$set_in_env" && ! ours "$set_in_env"; then
      nogo "port $set_in_env ($var in .env, $what) is held by $(holder "$set_in_env"): put another port in .env, or remove the line and ./go picks a free one"
    fi
    taken="$taken$set_in_env "
    continue
  fi
  p=$(envval "$var" .crew/ports.env); [ -n "$p" ] || p=$def
  if busy "$p" && ! ours "$p"; then
    was=$p; p=""; q=$((def + 1))
    while [ "$q" -le $((def + 99)) ]; do
      case "$taken" in *" $q "*) q=$((q + 1)); continue ;; esac
      if ! busy "$q"; then p=$q; break; fi
      q=$((q + 1))
    done
    [ -n "$p" ] || nogo "port $was ($what) is held by $(holder "$was") and no port from $((def + 1)) to $((def + 99)) is free: free one, or set $var in .env"
    moves="$moves
$was is held by $(holder "$was"): $what moves to $p ($var in .crew/ports.env)"
  fi
  taken="$taken$p "
  [ "$p" = "$def" ] || moved="$moved$var=$p
"
done

# 5050 cannot move: it is in every image's name (localhost:5050/…).
if busy 5050 && ! ours 5050; then
  nogo "port 5050 (the plane's registry, Zot) is held by $(holder 5050) and cannot move: images are named localhost:5050/…; stop it, then run ./go again"
fi
emu=""
case "$(envval EVENT_BUS .env)$(envval STATE_STORE .env)$(grep -E '^(EVENT_BUS|STATE_STORE)=' "profiles/${PROFILE:-l0}.env" 2>/dev/null || :)" in
  *-emulator*) emu="8085 8086" ;;
esac
for p in $emu; do
  if busy "$p" && ! ours "$p"; then
    nogo "port $p (an emulator of the profile) is held by $(holder "$p"); stop it, then run ./go again"
  fi
done

if [ -n "$moved" ]; then
  mkdir -p .crew
  { printf '# Written by ./go (docs/adr/0093 §1d): the plane ports moved off a busy default. A value in .env wins.\n'
    printf '%s' "$moved"; } > .crew/ports.env
  printf '%s\n' "$moves" | while IFS= read -r l; do [ -z "$l" ] || item ports "$l"; done
else
  rm -f .crew/ports.env
  item ports "ok, the plane's ports are free or held by this checkout's plane ($probe)"
fi
go

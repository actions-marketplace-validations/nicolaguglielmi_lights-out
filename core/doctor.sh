#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-doctor (docs/adr/0045 §4): `./go doctor`, on the host, before
# anything is built, because its first subject is the engine ./go needs.
# One stderr line per item: the engine (it answers; podman's machine and
# API socket), git, the workbench image, the plane's host ports (free, or
# held by the lights-out compose project itself), and the key the chosen
# profile needs (named, never shown). Then the one stdout line of the gate
# output contract: GO, or NO-GO naming the items that fail. Uses only what
# the host prerequisites guarantee (an engine, git, a POSIX shell); a port
# probe uses nc, lsof or ss when the host has one and says when it has none.
#
# --level <l0|l1|l2|l3> (docs/adr/0057 §8): what that level still lacks,
# read from profiles/<level>.env. The items above with PROFILE=<level>,
# then every adapter the profile names that has no adapters/<name>/
# (designed, not built), and for the cloud levels the cloud toolchain
# (docs/adr/0028). The last line counts what is missing.
set -eu
name=doctor
. ci/lib.sh

level=""
while [ $# -gt 0 ]; do
  case "$1" in
    --level) [ $# -ge 2 ] || nogo "--level needs one of l0 l1 l2 l3"; level=$2; shift 2 ;;
    --level=*) level=${1#--level=}; shift ;;
    *) nogo "'$1' is not an argument of doctor; --level <l0|l1|l2|l3>" ;;
  esac
done
if [ -n "$level" ]; then
  case "$level" in l0|l1|l2|l3) ;; *) nogo "--level $level is not one of l0 l1 l2 l3" ;; esac
  [ -f "profiles/$level.env" ] || nogo "--level $level has no profiles/$level.env"
  PROFILE=$level
fi

bad=""
nmiss=0
item() { printf 'doctor: %-9s %s\n' "$1" "$2" >&2; }
fail() { item "$1" "FAIL, $2"; bad="$bad $1"; nmiss=$((nmiss + 1)); }

# The engine, picked the way ./go picks it.
engine=""
if [ -n "${CONTAINER_ENGINE:-}" ]; then
  if command -v "$CONTAINER_ENGINE" >/dev/null 2>&1; then
    engine=$CONTAINER_ENGINE
  else
    fail engine "CONTAINER_ENGINE=$CONTAINER_ENGINE is not on PATH"
  fi
elif command -v podman >/dev/null 2>&1; then
  engine=podman
elif command -v docker >/dev/null 2>&1; then
  engine=docker
else
  fail engine "no podman or docker on PATH; install podman (reference) or docker"
fi
answers=""
if [ -n "$engine" ]; then
  v=$("$engine" version --format '{{.Client.Version}}' 2>/dev/null) || v="?"
  if "$engine" info >/dev/null 2>&1; then
    answers=1
    extra=""
    if [ "$engine" = podman ]; then
      if [ "$(podman info --format '{{.Host.RemoteSocket.Exists}}' 2>/dev/null)" = true ]; then
        extra=", API socket present"
      else
        extra=", no API socket (plane targets need it: systemctl --user enable --now podman.socket)"
      fi
    fi
    item engine "ok, $engine $v, answers$extra"
  else
    case "$engine:$(uname -s)" in
      podman:Darwin|podman:MINGW*|podman:MSYS*) fail engine "podman $v does not answer: podman machine start (or podman machine init first)" ;;
      *) fail engine "$engine $v does not answer ('$engine info' fails): start the $engine daemon or service" ;;
    esac
  fi
fi

if command -v git >/dev/null 2>&1; then
  item git "ok, $(git --version)"
else
  fail git "git is not on PATH"
fi

# The workbench image, tagged the way ./go tags it.
tag=$(cat workbench/Containerfile workbench/pyproject.toml workbench/uv.lock | cksum | cut -d' ' -f1)
if [ -n "$answers" ]; then
  if "$engine" image inspect "localhost/lights-out-workbench:$tag" >/dev/null 2>&1; then
    item workbench "ok, localhost/lights-out-workbench:$tag is built"
  else
    item workbench "ok, not built yet: the first ./go command builds it (3-6 minutes)"
  fi
fi

# The plane's host ports (README, "If something goes wrong").
envval() { sed -n "s/^$1=//p" .env 2>/dev/null | tail -1; }
app_port=$(envval APP_PORT); app_port=${app_port:-8080}
probe=""
if command -v nc >/dev/null 2>&1; then probe=nc
elif command -v lsof >/dev/null 2>&1; then probe=lsof
elif command -v ss >/dev/null 2>&1; then probe=ss
fi
plane_ports=""
if [ -n "$answers" ]; then
  plane_ports=$("$engine" ps --filter label=com.docker.compose.project=lights-out --format '{{.Ports}}' 2>/dev/null || true)
fi
if [ -z "$probe" ]; then
  item ports "not checked: no nc, lsof or ss on this host"
else
  taken=""
  # The emulators' ports only when the profile, or .env, names an emulator
  # adapter: at L0 and L1 the store and the bus are files (docs/adr/0060 §3).
  emu_ports=""
  case "$(envval EVENT_BUS)$(envval STATE_STORE)$(grep -E '^(EVENT_BUS|STATE_STORE)=' "profiles/${PROFILE:-l0}.env" 2>/dev/null)" in
    *-emulator*) emu_ports="8085 8086" ;;
  esac
  # shellcheck disable=SC2086 # emu_ports is two ports or nothing
  for p in 3000 5050 8016 $emu_ports 9090 9901 "$app_port"; do
    case "$probe" in
      nc) nc -z 127.0.0.1 "$p" >/dev/null 2>&1 || continue ;;
      lsof) lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1 || continue ;;
      ss) ss -ltnH 2>/dev/null | awk '{print $4}' | grep -q ":$p\$" || continue ;;
    esac
    case "$plane_ports" in *":$p->"*) continue ;; esac
    taken="$taken $p"
  done
  if [ -n "$taken" ]; then
    fail ports "in use by something other than the lights-out plane:$taken (APP_PORT in .env moves the app's)"
  else
    item ports "ok, 3000 5050 8016${emu_ports:+ $emu_ports} 9090 9901 $app_port free or held by the lights-out plane ($probe)"
  fi
fi

# The key. L0 replays and needs none; above it, the profile's provider and
# coding harness name theirs, .env overriding the profile as in the Makefile.
profile=${PROFILE:-l0}
if [ ! -f "profiles/$profile.env" ]; then
  fail key "PROFILE=$profile has no profiles/$profile.env"
else
  pval() { v=$(envval "$1"); [ -n "$v" ] || v=$(sed -n "s/^$1=//p" "profiles/$profile.env" | tail -1); printf '%s' "$v"; }
  harness=$(pval AGENT_HARNESS)
  provider=$(pval MODEL_PROVIDER)
  if [ "$harness" = replay ]; then
    item key "ok, none needed at $profile: the agents replay recordings"
  else
    # The variable's name is the adapter's (adapters/<harness>/conformance.env,
    # KEY_VAR where PROVIDER matches): core/ names no key (ci/model-free.sh).
    keyvar() { for f in adapters/*/conformance.env; do
        [ "$(sed -n 's/^PROVIDER=//p' "$f")" = "$1" ] && sed -n 's/^KEY_VAR=//p' "$f" && return 0
      done; return 0; }
    need=$(keyvar "$provider")
    [ ! -f "adapters/$harness/conformance.env" ] || need="$need $(sed -n 's/^KEY_VAR=//p' "adapters/$harness/conformance.env")"
    # shellcheck disable=SC2086 # a list of names, split on purpose
    need=$(printf '%s\n' $need | sort -u | tr '\n' ' ')
    need=${need% }
    missing=""
    for k in $need; do
      v=$(envval "$k")
      [ -n "$v" ] && [ "$v" != replace-me ] || missing="$missing $k"
    done
    if [ -n "$missing" ]; then
      fail key "$profile ($provider, $harness) needs$missing in .env, set to a real key"
    else
      item key "ok, $need set in .env for $profile ($provider, $harness)"
    fi
  fi
fi

[ -n "$level" ] || { [ -z "$bad" ] || nogo "${bad# }"; go; }

# --level: the adapters the profile names, each a directory under adapters/
# or designed and not built; .env overrides the profile, as in the Makefile.
for port in CODE_HOST TRACKER EVENT_BUS STATE_STORE ORCHESTRATOR DELIVERY METRICS FLAGS REGISTRY AGENT_HARNESS; do
  a=$(pval "$port")
  if [ -z "$a" ]; then
    fail "$port" "profiles/$level.env names no adapter"
  elif [ -d "adapters/$a" ]; then
    item "$port" "ok, $a (adapters/$a)"
  else
    fail "$port=$a" "designed, not built: there is no adapters/$a/"
  fi
done
# The cloud levels (docs/adr/0028, amended by 0057 §1): gcloud and terraform
# live in a cloud flavour of the workbench, written the day L2 is. An
# adapter's credentials are the adapter's to declare, never named here
# (ci/vendor-free.sh, docs/adr/0045 §4): a missing adapter is the item.
case "$level" in
  l2|l3)
    if [ -f workbench/cloud/Containerfile ]; then
      item toolchain "ok, workbench/cloud/Containerfile (gcloud, terraform)"
    else
      fail toolchain "no workbench/cloud/Containerfile: gcloud and terraform are not in the workbench (docs/adr/0028, 0057 §1)"
    fi ;;
esac

[ "$nmiss" -eq 0 ] || nogo "$level lacks $nmiss:$(printf '%s' "$bad" | sed 's/ /, /g; s/^, / /')"
go_with "$level has what its profile names"

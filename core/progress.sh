#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-progress (docs/adr/0093 §2): what a person sees of `./go demo`. Host
# shell: it reads the host's stages too, before any image exists (docs/adr/
# 0052 §1). Reads the run's merged output on stdin and:
#   - writes every line to <dir>/run.log;
#   - on `[step] <id>` ends the step before (its seconds) and prints
#     `[n/7] <what it does> (about <eta>) ...` on stderr;
#   - on `[say] <text>` prints the text on stderr;
#   - prints the demo's own verdict, `GO: demo[, …]` or `NO-GO: demo — …`,
#     on stdout, never a stage's (`GO: demo-rollback`);
#   - on `[exit] <rc>`, the run's exit code, written last by ./go: on 0,
#     rewrites <dir>/steps.tsv with each step's seconds, the next run's
#     estimates; otherwise prints the run's last NO-GO line on stdout if no
#     demo verdict came, then the log's last 40 lines and its path.
# Exits with the run's code. `date` runs only on a marker.
set -eu
dir=${1:?usage: progress.sh <dir>}
mkdir -p "$dir"
log="$dir/run.log"
: > "$log"
exec 3>>"$log"

steps="preflight toolchain plane rollback ticket checks console"
label() {
  case "$1" in
    preflight) printf 'the engine, memory, disk and ports' ;;
    toolchain) printf 'the toolchain image, built once per revision' ;;
    plane) printf 'the plane: code host, delivery, metrics, flags, registry and the app' ;;
    rollback) printf 'a canary with a failing feature takes 5%% of the traffic' ;;
    ticket) printf 'ticket 0001: request, spec, pull request, eight gates, merge, canary' ;;
    checks) printf "the repository's own checks, run beside the plane" ;;
    console) printf "this run's console, frozen into one page" ;;
    *) printf '%s' "$1" ;;
  esac
}
# The estimates: this machine's last run, else the stranger workflow's
# measured times after docs/adr/0093 (its "After" section).
eta() {
  v=$(awk -F'\t' -v s="$1" '$1 == s { print $2 }' "$dir/steps.tsv" 2>/dev/null | tail -n 1)
  if [ -z "$v" ]; then
    case "$1" in
      preflight) v=2 ;; toolchain) v=50 ;; plane) v=85 ;; rollback) v=65 ;;
      ticket) v=230 ;; checks) v=60 ;; console) v=10 ;; *) v=0 ;;
    esac
  fi
  printf '%s' "$v"
}
fmt() { if [ "$1" -lt 90 ]; then printf '%s s' "$1"; else printf '%s min %s s' $(($1 / 60)) $(($1 % 60)); fi; }

total=0
for s in $steps; do total=$((total + $(eta "$s"))); done
printf 'lights-out demo: a ticket goes from a request to a canary that rolls itself back, at L0, with no key. About %s on this machine.\n' "$(fmt "$total")" >&2

n=0; cur=""; t0=0; pending=""; times=""; verdict=""; last_nogo=""; rc=""
end_step() {
  [ -n "$cur" ] || return 0
  dt=$(( $(date +%s) - t0 ))
  if [ -n "$pending" ]; then printf ' %s\n' "$(fmt "$dt")" >&2; else printf '      done, %s\n' "$(fmt "$dt")" >&2; fi
  times="$times$cur	$dt
"
  cur=""; pending=""
}
while IFS= read -r line; do
  case "$line" in
    '[exit] '*) rc=${line#\[exit\] }; break ;;
  esac
  printf '%s\n' "$line" >&3
  case "$line" in
    '[step] '*)
      end_step
      cur=${line#\[step\] }
      n=0; i=0
      for s in $steps; do i=$((i + 1)); [ "$s" != "$cur" ] || n=$i; done
      t0=$(date +%s)
      printf '[%s/7] %s (about %s) ...' "$n" "$(label "$cur")" "$(fmt "$(eta "$cur")")" >&2
      pending=1 ;;
    '[say] '*)
      [ -z "$pending" ] || { printf '\n' >&2; pending=""; }
      printf '      %s\n' "${line#\[say\] }" >&2 ;;
    'GO: demo'|'GO: demo,'*|'GO: demo —'*|'NO-GO: demo —'*)
      [ -z "$pending" ] || { printf '\n' >&2; pending=""; }
      verdict=1
      printf '%s\n' "$line" ;;
    'NO-GO: '*) last_nogo=$line ;;
  esac
done
end_step
exec 3>&-
case "$rc" in ''|*[!0-9]*) rc=1; printf 'lights-out: the run ended without an exit code\n' >&2 ;; esac
if [ "$rc" -eq 0 ]; then
  printf '%s' "$times" > "$dir/steps.tsv"
else
  [ -n "$verdict" ] || printf '%s\n' "${last_nogo:-NO-GO: demo — the run failed with exit code $rc}"
  printf '\nThe last lines of the run:\n' >&2
  tail -n 40 "$log" | sed 's/^/  | /' >&2
  printf 'The whole run: %s (LIGHTS_OUT_VERBOSE=1 ./go demo prints it as it goes)\n' "$log" >&2
fi
exit "$rc"

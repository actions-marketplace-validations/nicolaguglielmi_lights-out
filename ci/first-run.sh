#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-first-run: the first run's host pieces as docs/adr/0093 says, written
# from its §1, §2 and §4 and its "Tests" section, not from the scripts. Cold:
# a temporary tree, a fake engine on PATH, real listening sockets inside
# this container's own network namespace, and a real HTTP server for the
# ready check. Each case is one that can fail.
#   §1 core/preflight.sh: free ports GO with no .crew/ports.env; a planted
#      listener on the app's and Gitea's ports moves both to the next free
#      port, written to .crew/ports.env and named; a second run keeps them;
#      a busy port .env sets is a NO-GO naming it and .env; a busy 5050 is
#      a NO-GO saying it cannot move; a port held by this checkout's plane
#      is fine; one held by a lights-out plane of another directory is a
#      NO-GO naming it; too little disk is a NO-GO with both numbers; too
#      little memory warns and stays GO; a stopped machine on macOS is
#      started once.
#   §1e adapters/gitea/ready.sh against a server answering 404: the
#      timeout line names the port and the status.
#   §2 core/progress.sh on scripted input: the terminal gets the header,
#      the step lines, the [say] lines, what the preflight changed or
#      warned about (never its "ok" lines) and the verdict; the log gets every
#      line; steps.tsv is written on GO only; a failure prints the log's
#      tail and its path, and the exit code is the run's.
#   §4 core/freeze.py --hash is proven in core/tests/test_freeze.py.
set -eu
name=first-run
. ci/lib.sh

for f in core/preflight.sh core/progress.sh adapters/gitea/ready.sh; do
  [ -f "$f" ] || nogo "$f not found"
done
tmp=$(mktemp -d)
pids=""
trap 'for p in $pids; do kill "$p" 2>/dev/null || :; done; rm -rf "$tmp"' EXIT

# A listener on 127.0.0.1:<port>, answering HTTP 404 to anything, until
# killed. Ready once the port accepts.
listen() {
  python3 - "$1" <<'PY' >/dev/null 2>&1 &
import http.server, sys
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404); self.end_headers(); self.wfile.write(b"not gitea")
    def log_message(self, *a): pass
http.server.HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
PY
  pids="$pids $!"
  i=0
  until curl -s -o /dev/null --max-time 1 "http://127.0.0.1:$1/" 2>/dev/null; do
    i=$((i + 1)); [ "$i" -lt 50 ] || nogo "could not start a listener on $1"
    sleep 0.1
  done
}
stop_listeners() { for p in $pids; do kill "$p" 2>/dev/null || :; done; pids=""; sleep 0.2; }

# The fake engine: answers what the preflight asks from files the case
# writes, and logs every call.
mkdir -p "$tmp/bin"
cat > "$tmp/bin/podman" <<'SH'
#!/bin/sh
printf '%s\n' "$*" >> "$FAKE/calls"
case "$*" in
  info*MemTotal*) cat "$FAKE/mem" ;;
  info*GraphRoot*) cat "$FAKE/disk" ;;
  info*) : ;;
  ps*) cat "$FAKE/ps" 2>/dev/null || : ;;
  "machine list"*) cat "$FAKE/machines" 2>/dev/null || : ;;
  "machine start"*) : ;;
esac
SH
chmod +x "$tmp/bin/podman"

# A checkout of its own for each case: the scripts it runs, nothing else.
fresh() {
  c="$tmp/c$1"; rm -rf "$c"; mkdir -p "$c/core" "$c/ci" "$c/.fake"
  cp core/preflight.sh "$c/core/"; cp ci/lib.sh "$c/ci/"
  printf '%s\n' 8589934592 > "$c/.fake/mem"
  printf '%s\n' "60000000000 10000000000" > "$c/.fake/disk"
  : > "$c/.fake/ps"; : > "$c/.fake/calls"
}
preflight() {
  (cd "$c" && env PATH="$tmp/bin:$PATH" FAKE="$c/.fake" CONTAINER_ENGINE=podman PREFLIGHT_OS=Linux \
    sh core/preflight.sh >"$c/.out" 2>"$c/.err")
}
want_go() { [ "$(cat "$c/.out")" = "GO: preflight" ] || nogo "§1 $1: want GO: preflight, got [$(cat "$c/.out")]" "$(cat "$c/.err")"; }
want_nogo() {
  { grep -q '^NO-GO: preflight — ' "$c/.out" && [ "$(wc -l < "$c/.out" | tr -d ' ')" = 1 ]; } \
    || nogo "§1 $1: want one NO-GO: preflight line, got [$(cat "$c/.out")]" "$(cat "$c/.err")"
}

# Free ports: GO, nothing written.
fresh free
preflight || :
want_go "free ports"
[ ! -e "$c/.crew/ports.env" ] || nogo "§1 free ports: .crew/ports.env written with nothing moved"

# The app's and Gitea's ports busy: both moved to the next free one.
fresh moved
listen 8080; listen 3000
preflight || nogo "§1 busy 8080 and 3000: exit $?, want 0" "$(cat "$c/.out")" "$(cat "$c/.err")"
want_go "busy 8080 and 3000"
grep -qx 'APP_PORT=8081' "$c/.crew/ports.env" 2>/dev/null || nogo "§1 busy 8080: .crew/ports.env has no APP_PORT=8081" "$(cat "$c/.crew/ports.env" 2>/dev/null)"
grep -qx 'CODE_HOST_PORT=3001' "$c/.crew/ports.env" || nogo "§1 busy 3000: .crew/ports.env has no CODE_HOST_PORT=3001" "$(cat "$c/.crew/ports.env")"
[ "$(grep -c '^[A-Z_]*=' "$c/.crew/ports.env")" = 2 ] || nogo "§1 busy 8080 and 3000: .crew/ports.env holds more than the two moved ports" "$(cat "$c/.crew/ports.env")"
grep '8080' "$c/.err" | grep -q '8081' || nogo "§1 busy 8080: no stderr line names 8080 and 8081" "$(cat "$c/.err")"
grep '3000' "$c/.err" | grep -q '3001' || nogo "§1 busy 3000: no stderr line names 3000 and 3001" "$(cat "$c/.err")"
# A second run keeps them, while they stay free.
preflight || nogo "§1 second run: exit $?" "$(cat "$c/.out")"
{ grep -qx 'APP_PORT=8081' "$c/.crew/ports.env" && grep -qx 'CODE_HOST_PORT=3001' "$c/.crew/ports.env"; } \
  || nogo "§1 second run: the moved ports changed" "$(cat "$c/.crew/ports.env")"
stop_listeners

# A busy port .env sets: NO-GO naming the port and .env, nothing moved.
fresh env
printf 'APP_PORT=9000\n' > "$c/.env"
listen 9000
preflight && nogo "§1 busy APP_PORT from .env: exit 0" "$(cat "$c/.out")"
want_nogo "busy APP_PORT from .env"
{ grep -q '9000' "$c/.out" && grep -q '\.env' "$c/.out"; } || nogo "§1 busy APP_PORT from .env: the line names neither 9000 nor .env" "$(cat "$c/.out")"
[ ! -e "$c/.crew/ports.env" ] || nogo "§1 busy APP_PORT from .env: a port .env sets was moved"
stop_listeners

# A busy 5050: cannot move.
fresh registry
listen 5050
preflight && nogo "§1 busy 5050: exit 0" "$(cat "$c/.out")"
want_nogo "busy 5050"
grep -q '5050' "$c/.out" || nogo "§1 busy 5050: the line does not name 5050" "$(cat "$c/.out")"
grep -q 'cannot move' "$c/.out" || nogo "§1 busy 5050: the line does not say it cannot move" "$(cat "$c/.out")"
stop_listeners

# Held by this checkout's own plane: fine, not moved. The fake engine says
# the lights-out project publishes 8080 from this checkout.
fresh ours
listen 8080
printf '%s|0.0.0.0:8080->8080/tcp\n' "$c" > "$c/.fake/ps"
preflight || nogo "§1 8080 held by this plane: exit $?" "$(cat "$c/.out")" "$(cat "$c/.err")"
want_go "8080 held by this plane"
[ ! -e "$c/.crew/ports.env" ] || nogo "§1 8080 held by this plane: moved anyway" "$(cat "$c/.crew/ports.env")"
grep -q 'com.docker.compose.project=lights-out' "$c/.fake/calls" || nogo "§1 the preflight never asked the engine for the lights-out project's containers"
stop_listeners

# Held by a lights-out plane of another directory: NO-GO naming it.
fresh other
listen 3000
printf '/home/someone/other-clone|0.0.0.0:3000->3000/tcp\n' > "$c/.fake/ps"
preflight && nogo "§1 a plane of another directory: exit 0" "$(cat "$c/.out")"
want_nogo "a plane of another directory"
grep -q '/home/someone/other-clone' "$c/.out" || nogo "§1 a plane of another directory: the line does not name it" "$(cat "$c/.out")"
stop_listeners

# Disk: under the need, a NO-GO with both numbers.
fresh disk
printf '%s\n' "60000000000 59500000000" > "$c/.fake/disk"
preflight && nogo "§1 500 MB free: exit 0" "$(cat "$c/.out")"
want_nogo "500 MB free"
grep -q 'prune' "$c/.out" || nogo "§1 500 MB free: the line gives no prune command" "$(cat "$c/.out")"
[ "$(grep -o '[0-9][0-9.,]* *[MG]B' "$c/.out" | wc -l | tr -d ' ')" -ge 2 ] || nogo "§1 500 MB free: the line does not give the free space and the need" "$(cat "$c/.out")"

# Memory: under 3,800 MiB warns, stays GO.
fresh mem
printf '%s\n' 3221225472 > "$c/.fake/mem"
preflight || nogo "§1 3 GiB of memory: exit $?, want a warning and GO" "$(cat "$c/.out")" "$(cat "$c/.err")"
want_go "3 GiB of memory"
grep -q 'memory' "$c/.err" || nogo "§1 3 GiB of memory: no warning line" "$(cat "$c/.err")"
fresh mem-ok
preflight || :; grep 'memory' "$c/.err" | grep -qiv 'ok' && nogo "§1 8 GiB of memory: warned" "$(cat "$c/.err")"

# A stopped machine on macOS: started, once.
fresh machine
printf 'podman-machine-default|false|true\n' > "$c/.fake/machines"
(cd "$c" && env PATH="$tmp/bin:$PATH" FAKE="$c/.fake" CONTAINER_ENGINE=podman PREFLIGHT_OS=Darwin \
  sh core/preflight.sh machine >"$c/.out" 2>"$c/.err") || nogo "§1 a stopped machine: exit $?" "$(cat "$c/.out")" "$(cat "$c/.err")"
[ "$(grep -c '^machine start' "$c/.fake/calls")" = 1 ] || nogo "§1 a stopped machine: machine start called $(grep -c '^machine start' "$c/.fake/calls") times, want 1" "$(cat "$c/.fake/calls")"
grep -q 'machine start podman-machine-default' "$c/.fake/calls" || nogo "§1 a stopped machine: not started by name" "$(cat "$c/.fake/calls")"
fresh machine-running
printf 'podman-machine-default|true|true\n' > "$c/.fake/machines"
(cd "$c" && env PATH="$tmp/bin:$PATH" FAKE="$c/.fake" CONTAINER_ENGINE=podman PREFLIGHT_OS=Darwin \
  sh core/preflight.sh machine >"$c/.out" 2>"$c/.err") || :
! grep -q '^machine start' "$c/.fake/calls" || nogo "§1 a running machine was started again"

# §1e: Gitea's ready check against something else on its port.
listen 3999
out=$(PLANE_HOST=127.0.0.1 CODE_HOST_PORT=3999 READY_TIMEOUT=2 sh adapters/gitea/ready.sh 2>&1) \
  && nogo "§1e gitea ready.sh: GO against a 404 server" "$out"
printf '%s' "$out" | grep -q '3999' || nogo "§1e gitea ready.sh: the timeout line does not name port 3999" "$out"
printf '%s' "$out" | grep -q '404' || nogo "§1e gitea ready.sh: the timeout line does not give the status 404" "$out"
stop_listeners

# §2: the filter, on a scripted run.
d="$tmp/progress"; mkdir -p "$d"
script() {
  cat <<'RUN'
[step] preflight
preflight: memory   ok, 8192 MiB
preflight: ports    8080 is held by node (pid 7): the app moves to 8081 (APP_PORT in .crew/ports.env)
[step] toolchain
STEP 1/8: FROM python
[step] plane
Container lights-out-gitea-1 Started
GO: engine-compat
[step] rollback
NO-GO: launchpad — 5%: error_rate canary=1.000 → rolled back
GO: demo-rollback
NO-GO: demo-gates — a stage's own line, not the demo's
[say] A canary at 5% failed its check and rolled back by itself
[step] ticket
[tower] 0001: release → rolled-back
[step] checks
GO: secrets
GO: ci
[step] console
[say] See why: file:///x/.crew/demo/console.html#ticket/0001
RUN
}
(script; printf 'GO: demo, milestone M9, 400s to rollback (budget 900s, plan §2)\n[exit] 0\n') \
  | sh core/progress.sh "$d" >"$d/term.out" 2>"$d/term.err" || nogo "§2 a GO run: the filter exited $?"
[ "$(cat "$d/term.out")" = "GO: demo, milestone M9, 400s to rollback (budget 900s, plan §2)" ] \
  || nogo "§2 a GO run: stdout is not exactly the demo's verdict" "$(cat "$d/term.out")"
grep -q 'the app moves to 8081' "$d/term.err" || nogo "§2 a GO run: a port the preflight moved is not on the terminal" "$(cat "$d/term.err")"
for noise in 'STEP 1/8' 'Container lights-out' 'GO: secrets' '\[tower\]' 'memory   ok'; do
  ! grep -q "$noise" "$d/term.err" || nogo "§2 a GO run: tool noise [$noise] reached the terminal" "$(cat "$d/term.err")"
done
[ "$(grep -c '^\[[1-7]/7\]' "$d/term.err")" -ge 7 ] || nogo "§2 a GO run: want a [n/7] line for each of the seven steps" "$(cat "$d/term.err")"
{ grep -q 'rolled back by itself' "$d/term.err" && grep -q 'console.html#ticket/0001' "$d/term.err"; } \
  || nogo "§2 a GO run: the [say] lines did not reach the terminal" "$(cat "$d/term.err")"
! grep -q '\[say\]\|\[step\]\|\[exit\]' "$d/term.err" || nogo "§2 a GO run: a raw marker reached the terminal" "$(cat "$d/term.err")"
for l in 'STEP 1/8: FROM python' 'GO: secrets' '[tower] 0001: release → rolled-back'; do
  grep -qF "$l" "$d/run.log" || nogo "§2 a GO run: [$l] is not in run.log"
done
[ -s "$d/steps.tsv" ] || nogo "§2 a GO run: no steps.tsv"
for s in preflight toolchain plane rollback ticket checks console; do
  grep -q "^$s	[0-9][0-9]*\$" "$d/steps.tsv" || nogo "§2 a GO run: steps.tsv has no seconds for $s" "$(cat "$d/steps.tsv")"
done
# The next run's header says how long, from that file.
(printf '[step] preflight\n[exit] 0\n') | sh core/progress.sh "$d" >/dev/null 2>"$d/term2.err" || :
grep -qi 'about' "$d/term2.err" || nogo "§2 the header gives no estimate" "$(cat "$d/term2.err")"

e="$tmp/progress-fail"; mkdir -p "$e"
i=0; lines=""; while [ "$i" -lt 60 ]; do lines="${lines}noise line $i
"; i=$((i + 1)); done
rc=0
(printf '[step] preflight\n[step] toolchain\n[step] plane\n%sNO-GO: engine-compat — ./go up failed (see stderr)\n[exit] 1\n' "$lines") \
  | sh core/progress.sh "$e" >"$e/term.out" 2>"$e/term.err" || rc=$?
[ "$rc" = 1 ] || nogo "§2 a failed run: the filter exited $rc, want the run's 1"
grep -q '^NO-GO: engine-compat' "$e/term.out" || nogo "§2 a failed run: the NO-GO line is not on stdout" "$(cat "$e/term.out")"
{ grep -q 'noise line 59' "$e/term.err" && ! grep -q 'noise line 5$' "$e/term.err"; } \
  || nogo "§2 a failed run: want the log's last lines, not all of them" "$(cat "$e/term.err")"
grep -q "$e/run.log" "$e/term.err" || nogo "§2 a failed run: the log's path is not printed" "$(cat "$e/term.err")"
[ ! -e "$e/steps.tsv" ] || nogo "§2 a failed run: steps.tsv written"

go

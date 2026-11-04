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
# Run by `make harness-conformance` before the suite judges any real harness
# (the judge is judged first, as ci/prompts.sh proves its checker on planted
# files before reading roles/). Not a ci/ check: it starts the stub and
# fake-cli about twenty times, a minute of `./go ci` that ci/contract.sh would
# spend twice, and it needs the suite's own files, not the repository's.
#
# It is not a conformance run of any real harness and says nothing of one:
# fake-cli proves the suite, never an adapter. What it cannot prove is the
# stub against the real CLIs' wire (the L0 suite of ADR 0041 does, once a
# harness exists) and the container side of run.sh.
set -eu
name=harness-conformance-proof
. ci/lib.sh

# `make harness-conformance` may carry the caller's choices; none of them is the proof's.
unset CONFORMANCE_HARNESS CONFORMANCE_PORT CONFORMANCE_TIMEOUT_S PROOF_COMPOSE_JSON FAKE_DEFECT

for tool in python3 jq git; do
  command -v "$tool" >/dev/null 2>&1 || nogo "$tool is not on PATH"
done

work=$(mktemp -d)
# shellcheck disable=SC2329 # invoked by name via `trap` below, not called directly
cleanup() {
  ec=$?
  rm -rf "$work"
  exit "$ec"
}
trap cleanup EXIT INT TERM

# --- the stand-in docker-compose ------------------------------------------------
mkdir -p "$work/bin"
cat > "$work/bin/docker-compose" <<'SHIM'
#!/bin/sh
# Answers the suite's compose calls from the proof's tree (cwd), stub.py on a local port.
args=" $* "
case "$args" in
  *" config "*)
    if [ -n "${PROOF_COMPOSE_JSON:-}" ]; then
      printf '%s\n' "$PROOF_COMPOSE_JSON"
    else
      printf '{"services":{"conformance-model":{},"fake-cli":{}}}\n'
    fi ;;
  *" up "*" conformance-model "*)
    STUB_WORK="$PWD/.crew/conformance/model" python3 -I gates/harness-conformance/stub.py "$CONFORMANCE_PORT" 2>"$PWD/.crew/conformance/stub.err" &
    echo $! > "$PWD/.crew/conformance/stub.pid" ;;
  *" rm "*)
    [ ! -f "$PWD/.crew/conformance/stub.pid" ] || kill "$(cat "$PWD/.crew/conformance/stub.pid")" 2>/dev/null || : ;;
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

effort=$(grep "^ANTHROPIC_$(printf '%s' "$THINKING" | tr '[:lower:]' '[:upper:]')=" "$here/thinking.env" | cut -d= -f2)
mkdir -p "$OUT"
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
base = env["MODEL_BASE_URL"].replace("conformance-model", "127.0.0.1")
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


def run_tool(name, tool_input):
    if name == "Bash":
        r = subprocess.run(["sh", "-c", tool_input["command"]], cwd=workspace, capture_output=True, text=True, timeout=60)
        return r.stdout + r.stderr
    if name == "Read":
        return open(host_path(tool_input["file_path"])).read()
    with open(host_path(tool_input["file_path"]), "w") as f:
        f.write(tool_input["content"])
    return "written"


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
        resp = json.load(urllib.request.urlopen(req))
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

# --- the tree the suite runs in ---------------------------------------------------
# build_tree DIR DEFECT: a copy of what the suite reads, plus fake-cli.
build_tree() {
  t=$1
  mkdir -p "$t/gates" "$t/ci" "$t/core" "$t/roles" "$t/adapters/fake-cli/hooks" "$t/.crew"
  cp gates/harness-conformance.sh "$t/gates/"
  cp -R gates/harness-conformance "$t/gates/harness-conformance"
  cp ci/lib.sh "$t/ci/"
  cp core/harness-check.sh "$t/core/"
  cp -R roles/dev-worker "$t/roles/dev-worker"
  cp "$fake/run.sh" "$fake/fake_cli.py" "$t/adapters/fake-cli/"
  cp "$fake/guard.sh" "$t/adapters/fake-cli/hooks/guard.sh"
  printf '{}\n' > "$t/adapters/fake-cli/package-lock.json"
  printf 'FROM scratch\n' > "$t/adapters/fake-cli/Containerfile"
  printf 'ANTHROPIC_LOW=low\nANTHROPIC_MEDIUM=medium\nANTHROPIC_HIGH=high\n' > "$t/adapters/fake-cli/thinking.env"
  printf 'PROVIDER=anthropic\nMODEL=fake-model-1\nKEY_VAR=FAKE_KEY_VALUE\nTHINKING_PATH=.output_config.effort\n' > "$t/adapters/fake-cli/conformance.env"
}

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
  port=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
  verdict=$(cd "$t" && PATH="$work/bin:$PATH" PROOF_INVOKED="$work/invoked" CONFORMANCE=1 CONFORMANCE_PORT="$port" \
    CONFORMANCE_TIMEOUT_S=2 PROOF_COMPOSE_JSON="${compose_json:-}" WORKBENCH_IMAGE=proof COMPOSE_FILE=compose.yaml WORKLOAD=w WORKLOAD_CONTRACT=w/c \
    FAKE_DEFECT="$2" sh gates/harness-conformance.sh 2> "$errfile") && rc=0 || rc=$?
  case "$3" in
    GO)
      case "$verdict" in
        "GO: harness-conformance — fake-cli, against a scripted model, "*) [ "$rc" -eq 0 ] || verdict="exit $rc" ;;
        *) rc=1 ;;
      esac
      [ "$rc" -eq 0 ] || nogo "the good fake-cli was refused ($1)" "got: $verdict" "$(tail -n 40 "$errfile")" ;;
    *)
      [ "$rc" -eq 1 ] || nogo "the suite accepted a harness that is wrong ($1): exit $rc" "$verdict"
      case "$verdict" in
        "NO-GO: harness-conformance — "*"$3"*) ;;
        *) nogo "the suite refused '$1' for another reason than expected" "wanted: $3" "got: $verdict" ;;
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
compose_json='{"services":{"conformance-model":{},"fake-cli":{"depends_on":{"postgres":{}}}}}'
prove "a worker whose service starts Postgres with it" "" "would also start postgres"
compose_json=""

go

#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-harness-conformance: every CLI harness's entry requirement (docs/adr/
# 0041 §8), written from the ADR and the adapter contract, never from an
# adapter. A CLI harness is an adapters/<name>/ with run.sh, Containerfile
# and package-lock.json: discovered, never listed. For each one, nine cases
# in a fixed order, the first disagreement a NO-GO naming the harness and
# the case:
#   0 pairing      1 valid PR          2 push denied        3 secrets read denied
#   4 the workspace cannot switch the guard off            5 MAX_TURNS
#   6 TOKEN_BUDGET 7 TIMEOUT_S         8 no key in artefacts
#
# What it runs: the real pinned CLI in its real image, driven by `sh
# adapters/<name>/run.sh` exactly as core/crew.sh does; only the far end of
# the wire is scripted (gates/harness-conformance/stub.py, compose service
# conformance-model). So it proves a harness's plumbing, never a model's
# ability and never the vendors' real wire: only an L1 recording does that.
#
# The adapter contract, each key read from adapters/<name>/conformance.env
# (PROVIDER, MODEL, KEY_VAR, THINKING_PATH) and thinking.env, never from a
# list here. Every harness's KEY_VAR is exported with a random canary before
# compose starts, because compose falls back to the project's .env for a
# variable missing from the environment, and on the owner's machine that file
# holds a real key.
#
# Provenance of the numbers (docs/adr/0041 §8, each a decision, not a
# measurement): MAX_TURNS=2 is the smallest limit that lets a run make more
# than one request; TOKEN_BUDGET=2500 can only be crossed by accumulating
# three responses of 1,000 tokens; TIMEOUT_S=30 is self-checking, because case
# 7 also requires that the stub saw the request it never answered, so a value
# shorter than a CLI's start fails the case instead of passing it; the stub's
# script calls a tool on every request and ends at step 20, which turns a
# budget that does not bind into a visible ordinary end, not a hang; "at most
# 3 requests" is the limit plus one, because each CLI counts a turn its own
# way. The port is a decision of this gate: 8089, inside the compose network
# only. CONFORMANCE_TIMEOUT_S moves case 7's 30 and is set by
# gates/harness-conformance/proof.sh alone, which cannot wait 30 s a harness.
#
# Lives in gates/, so ci/contract.sh cold-runs it inside `make ci` with no
# CONFORMANCE set and no engine: the guard below must be the first thing
# that runs. `make harness-conformance` is the only caller that sets
# CONFORMANCE=1; the acceptance command is `./go harness-conformance
# [CONFORMANCE_HARNESS=<name>]`, never a bare `sh gates/…` (CLAUDE.md).
# shellcheck disable=SC2016 # jq programs are single-quoted on purpose; their $m is jq's
set -eu
name=harness-conformance
. ci/lib.sh

# Instant NO-GO, before anything touches the engine (docs/adr/0026 §4).
if [ "${CONFORMANCE:-}" != "1" ]; then
  nogo "set CONFORMANCE=1: this suite builds each CLI harness's image and runs it against a scripted model (./go harness-conformance)"
fi

[ -n "${WORKBENCH_IMAGE:-}" ] || nogo "WORKBENCH_IMAGE is not set; run this via ./go harness-conformance"
for tool in docker-compose jq git sha256sum od tee; do
  command -v "$tool" >/dev/null 2>&1 || nogo "$tool is not on PATH; run this via ./go harness-conformance"
done

# --- the suite's view of compose (docs/adr/0041 §8, corrected) ----------------
# ADR 0041 §8 says COMPOSE_FILE=compose.yaml alone. It is not a project: its
# envoy and prometheus services depend on `backend`, which only a workload's
# fragment defines, and docker-compose refuses to load a file with an
# undefined dependency (`required: false` included; checked 2026-11-04). So
# `make harness-conformance` merges the smallest workload fragment that
# defines `backend` and names no harness service, with WORKLOAD and
# WORKLOAD_CONTRACT for interpolation. That is the Makefile's to say (this
# directory never names a workload, ci/app-free.sh). What this gate owns is
# the promise behind the ADR's sentence, checked below on the rendered
# project: running a harness's service starts nothing else, no Postgres.
# The worker image is built on the workbench.
[ -n "${COMPOSE_FILE:-}" ] || nogo "COMPOSE_FILE is not set; run this via ./go harness-conformance"
[ -n "${WORKLOAD:-}" ] || nogo "WORKLOAD is not set; run this via ./go harness-conformance"
[ -n "${WORKLOAD_CONTRACT:-}" ] || nogo "WORKLOAD_CONTRACT is not set; run this via ./go harness-conformance"
HARNESS_BASE_IMAGE=$WORKBENCH_IMAGE
CONFORMANCE_PORT=${CONFORMANCE_PORT:-8089}
: "${CREW_UID:=$(id -u)}"
: "${CREW_GID:=$(id -g)}"
export HARNESS_BASE_IMAGE CONFORMANCE_PORT CREW_UID CREW_GID

port=$CONFORMANCE_PORT
timeout_s=${CONFORMANCE_TIMEOUT_S:-30}
conf=.crew/conformance
model_url=http://conformance-model:$port
case_steps=20

# The dev-worker's own budgets, for every case that does not test one.
# shellcheck disable=SC1091 # a file of KEY=VALUE lines, as core/crew.sh sources it
. roles/dev-worker/role.env
role_thinking=$THINKING
role_max_turns=$MAX_TURNS
role_timeout_s=$TIMEOUT_S
role_token_budget=$TOKEN_BUDGET
prompt_line=$(grep -m1 -v '^[[:space:]]*$' roles/dev-worker/prompt.md) || nogo "roles/dev-worker/prompt.md has no first line"
ticket_line=$(grep -m1 -v '^[[:space:]]*$' gates/harness-conformance/ticket.md) || nogo "gates/harness-conformance/ticket.md has no first line"
final_title="Add conformance file"
final_body="Conformance body cf-7a1d: adds conformance.txt."

# --- the CLI harnesses, discovered -------------------------------------------
conf_get() {  # FILE KEY: the value of KEY= in FILE, one pair of quotes dropped
  grep "^$2=" "$1" 2>/dev/null | head -n1 | cut -d= -f2- | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/"
}
upper() { printf '%s' "$1" | tr '[:lower:]' '[:upper:]'; }

all=""
for d in adapters/*/; do
  h=$(basename "$d")
  if [ -f "adapters/$h/run.sh" ] && [ -f "adapters/$h/Containerfile" ] && [ -f "adapters/$h/package-lock.json" ]; then
    all="$all $h"
  fi
done
all=${all# }
[ -n "$all" ] || nogo "no CLI harness found: an adapters/<name>/ with run.sh, Containerfile and package-lock.json"

selected=$all
if [ -n "${CONFORMANCE_HARNESS:-}" ]; then
  case " $all " in
    *" $CONFORMANCE_HARNESS "*) selected=$CONFORMANCE_HARNESS ;;
    *) nogo "CONFORMANCE_HARNESS=$CONFORMANCE_HARNESS is not a CLI harness (run.sh, Containerfile and package-lock.json under adapters/<name>/); found: $all" ;;
  esac
fi

# Each selected harness's contract, read once and checked for shape (the
# engine-free half, ci/harness-shape.sh, checks it for everyone on every
# ./go ci; a harness that is run here must not be able to skip it).
for h in $selected; do
  cf=adapters/$h/conformance.env
  [ -f "$cf" ] || nogo "$h: $cf is missing (PROVIDER, MODEL, KEY_VAR, THINKING_PATH)"
  for k in PROVIDER MODEL KEY_VAR THINKING_PATH; do
    [ -n "$(conf_get "$cf" "$k")" ] || nogo "$h: $cf has no $k="
  done
  case "$(conf_get "$cf" KEY_VAR)" in
    ''|*[!A-Z0-9_]*|[0-9_]*) nogo "$h: $cf KEY_VAR is not a variable name" ;;
  esac
  [ -f "adapters/$h/thinking.env" ] || nogo "$h: adapters/$h/thinking.env is missing"
done

# --- the canaries -------------------------------------------------------------
# The key canary rides in the provider's auth header and must appear in no
# body and no artefact; the second one sits in the files case 3 asks the
# model to read and must appear in no body either.
rand() { od -An -N16 -tx1 /dev/urandom | tr -d ' \n'; }
canary="canary-$(rand)"
canary2="canary-$(rand)"
CONFORMANCE_CANARY=$canary
export CONFORMANCE_CANARY
for h in $all; do
  kv=$(conf_get "adapters/$h/conformance.env" KEY_VAR)
  case "$kv" in
    ''|*[!A-Z0-9_]*|[0-9_]*) continue ;;
  esac
  eval "$kv=\$canary"
  eval "export $kv"
done

# --- the scripted model's lifecycle --------------------------------------------
pass=0
started=0
# shellcheck disable=SC2329 # invoked by name via `trap` below, not called directly
cleanup() {
  ec=$?
  # Stops and removes this one service: `down` would take the plane with it
  # (the compose project is shared, docs/adr/0041 §8's COMPOSE_FILE note).
  if [ "$started" -eq 1 ]; then
    docker-compose --profile conformance rm -sf conformance-model >&2 2>&1 || :
  fi
  [ "$pass" -ne 1 ] || rm -rf "$conf"
  exit "$ec"
}
trap cleanup EXIT INT TERM

rm -rf "$conf" || nogo "could not remove $conf from an earlier run"
mkdir -p "$conf/model"
# The stub runs in a container, as the workbench image's user or CREW_UID:
# the directory it logs into must take a write from either.
chmod 777 "$conf/model"
t0=$(date +%s)

# The suite's compose view must load, hold a service named like each harness
# (run.sh runs it by that name), and start nothing with it: ADR 0041 §8's
# "no workload, no plane, no Postgres", checked on the rendered project.
#
# The rendered project holds every key variable's value, so it lives in a
# variable, never in a file under .crew/.
project=$(docker-compose --profile crew --profile conformance config --format json 2> "$conf/compose.err") \
  || nogo "docker-compose does not load the suite's project (COMPOSE_FILE=$COMPOSE_FILE)" "$(cat "$conf/compose.err")"
rm -f "$conf/compose.err"
printf '%s' "$project" | jq -e '.services["conformance-model"] != null' >/dev/null \
  || nogo "the suite's project has no service conformance-model (compose.yaml)"
for h in $selected; do
  printf '%s' "$project" | jq -e --arg h "$h" '.services[$h] != null' >/dev/null \
    || nogo "$h: the suite's project has no compose service named $h, and run.sh runs it by that name"
  deps=$(printf '%s' "$project" | jq -r --arg h "$h" '(.services[$h].depends_on // {}) | keys | join(",")')
  [ -z "$deps" ] || nogo "$h: running its service would also start $deps; the suite runs a harness with no workload service beside it (docs/adr/0041 §8)"
done
project=""

printf 'harness-conformance: the CLI under test is the real pinned binary in its real image; the model is scripted\n' >&2
printf 'harness-conformance: (gates/harness-conformance/stub.py). It proves plumbing, not a model and not the vendors'"'"' wire.\n' >&2
printf 'harness-conformance: harnesses: %s\n' "$selected" >&2

started=1
docker-compose --profile conformance up -d conformance-model >&2 \
  || nogo "could not start the scripted model (compose service conformance-model)"
waited=0
while [ ! -f "$conf/model/ready" ]; do
  waited=$((waited + 1))
  if [ "$waited" -gt 60 ]; then
    docker-compose --profile conformance logs --no-color conformance-model >&2 2>&1 || :
    nogo "the scripted model did not answer within 60 s (compose service conformance-model)"
  fi
  sleep 1
done
[ "$(cat "$conf/model/ready")" = "$port" ] \
  || nogo "the scripted model listens on $(cat "$conf/model/ready"), not on $port"

# --- helpers -------------------------------------------------------------------
# None of these may be called inside a $(...) capture: a nogo inside one would
# only exit the subshell the capture runs in (the delivery suite's note).

fail() {  # WHAT: NO-GO naming the running harness and case, with the evidence
  nogo "$h case $n: $1" \
    "--- run.sh's stderr, last 30 lines ($errf)" \
    "$(tail -n 30 "$errf" 2>/dev/null || true)" \
    "--- the scripted model's requests ($reqlog)" \
    "$(jq -c '{n, kind, auth, requested, tools, step, op, hooked, reported_tokens}' "$reqlog" 2>/dev/null | head -n 40 || true)"
}

set_case() {  # STEPS_JSON: the script the stub plays for the running case
  jq -n --arg case "$h/$n" --arg cwd "/crew/$ticket/workspace" --argjson steps "$1" \
    '{case: $case, cwd: $cwd, steps: $steps}' > "$conf/model/case.json.tmp" \
    || fail "could not build the stub's case file"
  mv "$conf/model/case.json.tmp" "$conf/model/case.json" || fail "could not write the stub's case file"
}

prepare() {  # H N: a fresh workspace, a bare origin and the ticket; sets the paths below
  h=$1
  n=$2
  ticket=conformance/$h/$n
  dir=$(pwd)/$conf/$h/$n
  ws=$dir/workspace
  out=$dir/out
  tfile=$dir/ticket.md
  errf=$dir/stderr.log
  reqdir=$conf/model/$h/$n
  reqlog=$reqdir/requests.jsonl
  mkdir -p "$ws" "$out" "$reqdir/bodies"
  : > "$reqlog"
  chmod 777 "$reqdir" "$reqdir/bodies"
  chmod 666 "$reqlog"
  : > "$errf"
  cp gates/harness-conformance/ticket.md "$tfile"
  git init -q -b main "$ws" || fail "git init failed"
  printf '# conformance workspace\n' > "$ws/README.md"
  case "$n" in
    3)
      # Committed in BASE, so the adapter's own commit and OUT/patch never hold them.
      printf 'CANARY=%s\n' "$canary2" > "$ws/.env"
      printf '%s\n' "$canary2" > "$ws/id_ed25519"
      printf '%s\n' "$canary2" > "$ws/signing.key"
      ;;
    4)
      # What a repository can ship to switch the guard off, one file per vendor.
      mkdir -p "$ws/.gemini" "$ws/.claude" "$ws/.codex"
      printf '{"hooksConfig":{"enabled":false,"disabled":["guard"]},"hooks":{"BeforeTool":[]}}\n' > "$ws/.gemini/settings.json"
      printf '{"disableAllHooks": true}\n' > "$ws/.claude/settings.json"
      printf '[features]\nhooks = false\n' > "$ws/.codex/config.toml"
      printf '{"hooks":{}}\n' > "$ws/.codex/hooks.json"
      ;;
  esac
  git -C "$ws" add -A
  git -C "$ws" -c user.name=lights-out-tests -c user.email=tests@lights-out.invalid commit -q -m base \
    || fail "could not commit the base"
  base=$(git -C "$ws" rev-parse HEAD)
  # A push the hook missed succeeds inside the container: origin.git is in the
  # same mount, and the remote is a path inside it.
  git init -q --bare "$dir/origin.git" || fail "git init --bare failed"
  git -C "$ws" remote add origin ../origin.git
  git -C "$ws" push -q origin HEAD:refs/heads/main || fail "could not populate origin.git"
}

invoke() {  # MAX_TURNS TOKEN_BUDGET TIMEOUT_S MODEL_PROVIDER: run.sh exactly as core/crew.sh runs it
  (
    ROLE=dev-worker
    TICKET=$ticket
    TICKET_FILE=$tfile
    WORKSPACE=$ws
    BASE=$base
    OUT=$out
    THINKING=$role_thinking
    MAX_TURNS=$1
    TOKEN_BUDGET=$2
    TIMEOUT_S=$3
    MODEL_PROVIDER=$4
    MODEL=$model
    MODEL_BASE_URL=$model_url
    ATTEMPT=1
    export ROLE TICKET TICKET_FILE WORKSPACE BASE OUT THINKING MAX_TURNS TOKEN_BUDGET TIMEOUT_S MODEL_PROVIDER MODEL MODEL_BASE_URL ATTEMPT
    # An image build is not counted by TIMEOUT_S (it runs inside the container),
    # so the ceiling is the longest budget plus the minutes a cold start can take.
    if command -v timeout >/dev/null 2>&1; then
      exec timeout "$(($3 + 600))" sh "adapters/$h/run.sh"
    fi
    exec sh "adapters/$h/run.sh"
  ) </dev/null
}

run_case() {  # MAX_TURNS TOKEN_BUDGET TIMEOUT_S [MODEL_PROVIDER]: sets rc; stderr streamed and kept in $errf
  rc_file=$dir/rc
  {
    rc=0
    invoke "$1" "$2" "$3" "${4:-$provider}" || rc=$?
    printf '%s' "$rc" > "$rc_file"
  } 2>&1 | tee "$errf" >&2
  rc=$(cat "$rc_file")
}

# One request per jq line; every query below is over requests.jsonl.
rq() { jq -rs "$@" "$reqlog"; }

check_auth() {
  bad=$(rq '[.[] | select((.kind == "generate" or .kind == "count") and .auth != "ok")] | length')
  [ "$bad" -eq 0 ] || fail "$bad request(s) did not carry the key canary: the key did not come from $key_var (case 8's invariant, caught here)"
}

loop_requests() {  # the requests that are the agent loop's, for $model
  rq --arg m "$model" '[.[] | select(.kind == "generate" and .tools == true and .requested == $m)] | length'
}

check_hooks_log() {
  [ -s "$out/hooks.log" ] || fail "OUT/hooks.log is missing or empty: no hook call was recorded"
  odd=$(grep -vE '^(ALLOW [^ ]+ -|DENY [^ ]+ .+)$' "$out/hooks.log" | head -n 1 || true)
  [ -z "$odd" ] || fail "hooks.log has a line that is not 'ALLOW <tool> -' or 'DENY <tool> <label>': $odd"
}

# Probes are the hooked calls the case wants refused: every hooked step but a write.
probe_count() {
  rq --arg m "$model" '[.[] | select(.kind == "generate" and .tools == true and .requested == $m and .hooked == true and .op != "write")] | length'
}

# A probe the CLI refuses by itself, before any hook runs, never reaches the
# guard, so it leaves no DENY line; found running gemini-cli 0.61.0-preview.0
# through this suite: its read_file refuses a workspace's .env as "Path not in
# workspace" (its own ignore rules) before BeforeTool fires. Such a probe is
# stopped all the same, and the canary checks below still hold it to that.
CLI_REFUSAL='Path not in workspace'

cli_refused_count() {  # hooked probes whose next tool result is the CLI's own refusal
  rq --arg m "$model" --arg refusal "$CLI_REFUSAL" '
    [.[] | select(.kind == "generate" and .tools == true and .requested == $m)] as $g
    | [$g[] | select(.hooked == true and .op != "write") | .step as $s
       | ($g | map(select(.step == ($s + 1))) | (.[0].last_result // "")) as $r
       | select(($r | test("denied"; "i") | not) and ($r | contains($refusal)))] | length'
}

check_denials_reached_the_model() {  # every probe's tool result, in the next request, says it was denied or refused
  silent=$(rq --arg m "$model" --arg refusal "$CLI_REFUSAL" '
    [.[] | select(.kind == "generate" and .tools == true and .requested == $m)] as $g
    | [$g[] | select(.hooked == true and .op != "write")] as $probes
    | [$probes[] | .step as $s
       | ($g | map(select(.step == ($s + 1))) | (.[0].last_result // "")) as $r
       | select((($r | test("denied"; "i")) or ($r | contains($refusal))) | not) | $s]
    | map(tostring) | join(",")')
  [ -z "$silent" ] || fail "the next request's tool result does not carry a denial for step(s) $silent"
}

check_valid_pr() {  # the artefact contract of ADR 0017 §1 and ADR 0041: cases 1 to 4 end the same way
  [ "$rc" -eq 0 ] || fail "run.sh exited $rc, want 0"
  check_auth
  sh core/harness-check.sh "$out" "$ws" "$base" 2> "$dir/harness-check.err" \
    || fail "core/harness-check.sh: $(cat "$dir/harness-check.err")"
  [ "$(git -C "$ws" rev-list --count "$base..HEAD")" = 1 ] || fail "the workspace is not exactly one commit over BASE"
  [ "$(git -C "$ws" log -1 --format=%an)" = lights-out-crew ] || fail "the commit over BASE was not made by the adapter under the crew identity (lights-out-crew)"
  changed=$(git -C "$ws" diff --name-only "$base" HEAD)
  [ "$changed" = conformance.txt ] || fail "the commit touches '$changed', want conformance.txt only"
  [ "$(grep '^diff --git' "$out/patch")" = "diff --git a/conformance.txt b/conformance.txt" ] \
    || fail "OUT/patch does not touch conformance.txt only"
  [ "$(jq -r '.title' "$out/pr.json")" = "$final_title" ] || fail "pr.json's title is '$(jq -r '.title' "$out/pr.json")', want '$final_title'"
  jq -e --arg b "$final_body" '.body | contains($b)' "$out/pr.json" >/dev/null || fail "pr.json's body lacks the final message's body"
  grep -qF -- "$final_title" "$out/final.md" || fail "final.md lacks the final message's title"
  grep -qF -- "$final_body" "$out/final.md" || fail "final.md lacks the final message's body"

  rj=$out/run.json
  jq -e . "$rj" >/dev/null 2>&1 || fail "OUT/run.json is missing or not JSON"
  want_tokens=$(rq '[.[] | .reported_tokens] | add // 0')
  field() {  # JQ_EXPR WANT: run.json's field, as text, equals WANT
    got=$(jq -r "$1 | if . == null then \"null\" else tostring end" "$rj")
    [ "$got" = "$2" ] || fail "run.json $1 is '$got', want '$2'"
  }
  field .harness "$h"
  field .provider "$provider"
  field .model "$model-conformance"
  field .thinking "$role_thinking"
  field .tokens.total "$want_tokens"
  field .input_sha256 "$(sha256sum "$tfile" | cut -d' ' -f1)"
  field .exit_code 0
  jq -e '(.turns | type) == "number" and .turns >= 1' "$rj" >/dev/null || fail "run.json .turns is not a number of at least 1"
  jq -e '(.tokens.input | type) == "number" and (.tokens.output | type) == "number"' "$rj" >/dev/null || fail "run.json .tokens.input and .tokens.output are not numbers"
  jq -e '(.duration_s | type) == "number"' "$rj" >/dev/null || fail "run.json .duration_s is not a number"
  jq -e --arg u "$model_url" '(.endpoint // "") | startswith($u)' "$rj" >/dev/null \
    || fail "run.json .endpoint is '$(jq -r '.endpoint // "absent"' "$rj")', want the MODEL_BASE_URL the run was given ($model_url)"
  check_hooks_log
}

check_stop() {  # PHRASE MAX_REQUESTS: ADR 0041 §5's stop contract, read from stderr
  [ "$rc" -eq 1 ] || fail "run.sh exited $rc, want 1"
  check_auth
  grep -qF -- "$1" "$errf" || fail "run.sh's stderr has no line containing '$1'"
  [ ! -e "$out/pr.json" ] || fail "an over-budget run left OUT/pr.json: it would be recorded"
  reqs=$(loop_requests)
  [ "$reqs" -le "$2" ] || fail "the stub saw $reqs requests for $model, at most $2 allowed: the budget did not stop the run"
  [ "$reqs" -ge 1 ] || fail "the stub saw no request for $model that carries tools"
}

valid_steps() {
  jq -n --arg t "$final_title

$final_body" '[{op: "write", path: "conformance.txt", content: "conformance\n"}, {op: "final", text: $t}]'
}

steps_after() {  # PROBES_JSON: the probes, then the valid run
  jq -n --argjson pre "$1" --argjson v "$(valid_steps)" '$pre + $v'
}

endless_steps() {  # a tool on every request, an ordinary end only at step 20
  jq -n --argjson k "$case_steps" --arg t "$final_title

$final_body" '[range($k) | {op: "shell", cmd: "echo turn"}] + [{op: "final", text: $t}]'
}

# --- the cases, one harness at a time ---------------------------------------------
for h in $selected; do
  cf=adapters/$h/conformance.env
  provider=$(conf_get "$cf" PROVIDER)
  model=$(conf_get "$cf" MODEL)
  key_var=$(conf_get "$cf" KEY_VAR)
  thinking_path=$(conf_get "$cf" THINKING_PATH)
  thinking_key="$(upper "$provider")_$(upper "$role_thinking")"
  want_thinking=$(conf_get "adapters/$h/thinking.env" "$thinking_key")
  [ -n "$want_thinking" ] || nogo "$h: adapters/$h/thinking.env has no $thinking_key= line"
  printf 'harness-conformance: %s (provider %s, model %s)\n' "$h" "$provider" "$model" >&2

  # The image first, so a build that fails is one NO-GO naming it, not eight cases
  # of an adapter that cannot start, and the cases' timings do not hold a build.
  docker-compose --profile crew build "$h" >&2 \
    || nogo "$h: its image did not build (docker-compose --profile crew build $h)"

  # Provider and harness pairing: the other provider offered to case 0, and the harness
  # whose name the refusal line must carry. A harness that exists names itself by
  # discovery; one that does not exist yet falls back to ADR 0041 §2's pairing.
  case "$provider" in
    gemini) other=anthropic ;;
    *) other=gemini ;;
  esac
  fitting=""
  for o in $all; do
    [ "$(conf_get "adapters/$o/conformance.env" PROVIDER)" = "$other" ] && fitting=$o
  done
  if [ -z "$fitting" ]; then
    case "$other" in
      anthropic) fitting=claude-code ;;
      openai) fitting=codex ;;
      *) fitting=gemini-cli ;;
    esac
  fi

  # ---- case 0: pairing -------------------------------------------------------
  prepare "$h" 0
  shim=$dir/shim
  mkdir -p "$shim"
  for tool in docker-compose docker podman; do
    printf '#!/bin/sh\necho "%s $*" >> "%s/invoked"\nexit 97\n' "$tool" "$shim" > "$shim/$tool"
    chmod +x "$shim/$tool"
  done
  set_case '[{"op":"final","text":"unused"}]'
  rc=0
  (
    PATH=$shim:$PATH
    ROLE=dev-worker TICKET=$ticket TICKET_FILE=$tfile WORKSPACE=$ws BASE=$base OUT=$out
    THINKING=$role_thinking MAX_TURNS=$role_max_turns TOKEN_BUDGET=$role_token_budget TIMEOUT_S=$role_timeout_s
    MODEL_PROVIDER=$other MODEL=$model MODEL_BASE_URL=$model_url ATTEMPT=1
    export PATH ROLE TICKET TICKET_FILE WORKSPACE BASE OUT THINKING MAX_TURNS TOKEN_BUDGET TIMEOUT_S MODEL_PROVIDER MODEL MODEL_BASE_URL ATTEMPT
    exec sh "adapters/$h/run.sh"
  ) </dev/null >"$dir/case0.out" 2>"$errf" || rc=$?
  [ "$rc" -eq 1 ] || fail "run.sh with MODEL_PROVIDER=$other exited $rc, want 1"
  [ ! -e "$shim/invoked" ] || fail "run.sh with MODEL_PROVIDER=$other started a container ($(cat "$shim/invoked")); it must refuse first"
  [ "$(awk 'END{print NR}' "$errf")" -eq 1 ] || fail "run.sh with MODEL_PROVIDER=$other wrote $(awk 'END{print NR}' "$errf") stderr lines, want exactly one"
  grep -qF -- "$fitting" "$errf" || fail "the refusal does not name the harness that fits $other ($fitting): $(cat "$errf")"

  # ---- case 1: a valid PR ----------------------------------------------------
  prepare "$h" 1
  set_case "$(steps_after '[]')"
  run_case "$role_max_turns" "$role_token_budget" "$role_timeout_s"
  check_valid_pr
  [ "$(rq '[.[] | select(.hooked == true)] | length')" -ge 1 ] || fail "the stub never had a hooked call executed"
  grep -q '^ALLOW ' "$out/hooks.log" || fail "hooks.log has no ALLOW line for the write"
  first=$(rq --arg m "$model" '[.[] | select(.kind == "generate" and .tools == true and .requested == $m)] | .[0].body // empty')
  [ -n "$first" ] || fail "the stub saw no request for $model that carries tools"
  jq -r '[.. | strings] | join("\n")' "$reqdir/$first" > "$dir/first-request.txt" 2>/dev/null \
    || fail "the first request's body is not JSON"
  grep -qF -- "$prompt_line" "$dir/first-request.txt" || fail "the first request does not carry the role prompt's first line ($prompt_line)"
  grep -qF -- "$ticket_line" "$dir/first-request.txt" || fail "the first request does not carry the ticket ($ticket_line)"
  got_thinking=$(jq -r "($thinking_path) // empty | tostring" "$reqdir/$first" 2>/dev/null || true)
  [ -n "$got_thinking" ] || fail "the first request carries nothing at $thinking_path (the value for THINKING=$role_thinking is '$want_thinking')"
  [ "$got_thinking" = "$want_thinking" ] || fail "the first request carries '$got_thinking' at $thinking_path, want '$want_thinking' (thinking.env's $thinking_key)"

  # ---- case 2: a push is denied ----------------------------------------------
  prepare "$h" 2
  set_case "$(steps_after '[{"op":"shell","cmd":"git push origin HEAD:refs/heads/conformance"}]')"
  run_case "$role_max_turns" "$role_token_budget" "$role_timeout_s"
  check_valid_pr
  grep -qE '^DENY [^ ]+ git push$' "$out/hooks.log" || fail "hooks.log has no 'DENY <tool> git push' line"
  if git -C "$dir/origin.git" show-ref --verify --quiet refs/heads/conformance; then
    fail "origin.git has refs/heads/conformance: the push got through the hook"
  fi
  [ "$(probe_count)" -ge 1 ] || fail "the stub never had the push executed"
  check_denials_reached_the_model

  # ---- case 3: secrets reads are denied --------------------------------------
  prepare "$h" 3
  # The probes: shell cat, the vendor's read, printenv, and on codex a code-mode
  # read that makes no nested tool call, so fires no hook (the stub renders it
  # as a plain read everywhere else). The last one is the open point ADR 0041 §3
  # closes here, by the second canary not reaching the wire.
  set_case "$(steps_after '[
    {"op":"shell","cmd":"cat .env"},
    {"op":"read","path":"id_ed25519"},
    {"op":"shell","cmd":"cat signing.key"},
    {"op":"read","path":"signing.key"},
    {"op":"shell","cmd":"printenv"},
    {"op":"jsread","path":".env"}]')"
  run_case "$role_max_turns" "$role_token_budget" "$role_timeout_s"
  check_valid_pr
  probes=$(probe_count)
  [ "$probes" -ge 5 ] || fail "the stub had only $probes hooked probes executed, want at least 5"
  denies=$(grep -c '^DENY ' "$out/hooks.log" || true)
  refused=$(cli_refused_count)
  [ "$denies" -ge "$((probes - refused))" ] || fail "hooks.log has $denies DENY lines for $probes hooked probe calls ($refused refused by the CLI before any hook): a read was not denied"
  check_denials_reached_the_model
  leaked=$(grep -rlF -e "$canary2" -e "$canary" "$reqdir/bodies" 2>/dev/null | head -n 1 || true)
  [ -z "$leaked" ] || fail "a canary reached the model: it is in $leaked (a read of .env, id_ed25519, signing.key or the environment was not stopped)"
  leaked=$(grep -rlF -e "$canary2" -e "$canary" "$out" 2>/dev/null | head -n 1 || true)
  [ -z "$leaked" ] || fail "a canary is in the artefacts: $leaked"

  # ---- case 4: the workspace cannot switch the guard off ---------------------
  prepare "$h" 4
  set_case "$(steps_after '[{"op":"shell","cmd":"git push origin HEAD:refs/heads/conformance"}]')"
  run_case "$role_max_turns" "$role_token_budget" "$role_timeout_s"
  check_valid_pr
  grep -qE '^DENY [^ ]+ git push$' "$out/hooks.log" || fail "hooks.log has no 'DENY <tool> git push' line: the workspace's own vendor settings switched the guard off, or the run never reached the push"
  if git -C "$dir/origin.git" show-ref --verify --quiet refs/heads/conformance; then
    fail "origin.git has refs/heads/conformance: with the workspace's own vendor settings committed, the push got through"
  fi
  [ "$(probe_count)" -ge 1 ] || fail "the stub never had the push executed"
  check_denials_reached_the_model

  # ---- case 5: MAX_TURNS -----------------------------------------------------
  prepare "$h" 5
  set_case "$(endless_steps)"
  run_case 2 "$role_token_budget" "$role_timeout_s"
  check_stop "over MAX_TURNS (2)" 3

  # ---- case 6: TOKEN_BUDGET --------------------------------------------------
  prepare "$h" 6
  set_case "$(endless_steps)"
  run_case "$role_max_turns" 2500 "$role_timeout_s"
  check_stop "over TOKEN_BUDGET (2500)" 3

  # ---- case 7: TIMEOUT_S -----------------------------------------------------
  prepare "$h" 7
  set_case '[{"op":"hang"}]'
  run_case "$role_max_turns" "$role_token_budget" "$timeout_s"
  [ "$rc" -eq 1 ] || fail "run.sh exited $rc, want 1"
  check_auth
  grep -qF -- "over TIMEOUT_S ($timeout_s s)" "$errf" || fail "run.sh's stderr has no line containing 'over TIMEOUT_S ($timeout_s s)'"
  [ ! -e "$out/pr.json" ] || fail "an over-budget run left OUT/pr.json: it would be recorded"
  [ "$(rq '[.[] | select(.op == "hang")] | length')" -ge 1 ] \
    || fail "the stub never saw the request it was to leave unanswered: TIMEOUT_S=$timeout_s is shorter than this CLI takes to start, or it never asked"

  # ---- case 8: no key in the artefacts, over every case ----------------------
  n=8
  for c in 1 2 3 4 5 6 7; do
    reqdir=$conf/model/$h/$c
    reqlog=$reqdir/requests.jsonl
    errf=$conf/$h/$c/stderr.log
    check_auth
    leaked=$(grep -rlF -- "$canary" "$reqdir/bodies" 2>/dev/null | head -n 1 || true)
    [ -z "$leaked" ] || fail "the key canary is in a request body ($leaked, case $c): the key left the auth header"
    leaked=$(grep -rlF -- "$canary" "$conf/$h/$c/out" 2>/dev/null | head -n 1 || true)
    [ -z "$leaked" ] || fail "the key canary is in the artefacts ($leaked, case $c)"
  done
  [ "$(jq -s '[.[] | select(.auth == "ok")] | length' "$conf/model/$h/1/requests.jsonl")" -ge 1 ] \
    || fail "no request carried the key canary at all: the key did not come from $key_var"
done

elapsed=$(($(date +%s) - t0))
pass=1
go_with "$selected, against a scripted model, ${elapsed} s"

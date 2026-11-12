#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# harness-codex: the `codex` AgentHarness (docs/adr/0041). Runs one
# headless `codex exec` in the `codex` compose service (no engine socket,
# no git credential, only this run's directory mounted; codex's own
# sandbox is off because it cannot start in rootless podman, so the
# container is the sandbox, §3), then does what the entrypoint does not,
# on gemini-cli's pattern: reads the stop reason from the budget hook's
# marker, the spend from the --json events, the served model from the
# entrypoint's served_model, commits what the model left under the crew
# identity (the adapter commits, not the model, docs/adr/0017 §1), writes
# the patch, pr.json, final.md and run.json, and refuses to record
# anything if the key leaked into the artefacts. Shapes read here were
# verified live on 0.166.0 (docs/adr/0041, "Verified"): `item.completed`
# events carry `agent_message` items with the text, `turn.completed`
# carries usage, `turn.failed` an error message.
# Adapter convention (docs/adr/0012 §6): not a gate, silent on success,
# one stderr line and exit 1 on failure.
set -eu
: "${ROLE:?ROLE not set}"
: "${TICKET:?TICKET not set}"
: "${WORKSPACE:?WORKSPACE not set}"
: "${BASE:?BASE not set}"
: "${OUT:?OUT not set}"
: "${TICKET_FILE:?TICKET_FILE not set}"
: "${THINKING:?THINKING not set}"
: "${MAX_TURNS:?MAX_TURNS not set}"
: "${TIMEOUT_S:?TIMEOUT_S not set}"
: "${TOKEN_BUDGET:?TOKEN_BUDGET not set}"

# One provider per harness (docs/adr/0041 §2); the model is the profile's
# (docs/adr/0040 §1, §4).
case "${MODEL_PROVIDER:-}" in
  openai) ;;
  gemini|anthropic)
    fits=gemini-cli; [ "$MODEL_PROVIDER" = anthropic ] && fits=claude-code
    printf 'harness-codex: MODEL_PROVIDER=%s runs on AGENT_HARNESS=%s (docs/adr/0041 §2); this harness runs openai only\n' "$MODEL_PROVIDER" "$fits" >&2
    exit 1
    ;;
  *)
    printf 'harness-codex: MODEL_PROVIDER=%s is not openai; this harness runs openai only (docs/adr/0041 §2)\n' "${MODEL_PROVIDER:-}" >&2
    exit 1
    ;;
esac
[ -n "${MODEL:-}" ] || { printf 'harness-codex: MODEL is empty; set the exact model id in the profile or .env (docs/adr/0040 §1)\n' >&2; exit 1; }
case "${OPENAI_API_KEY:-}" in
  ""|replace-me)
    printf 'harness-codex: MODEL_PROVIDER=openai needs a real OPENAI_API_KEY in .env (see .env.example)\n' >&2
    exit 1
    ;;
esac

# The role's THINKING mapped to model_reasoning_effort by this adapter's own map
# (docs/adr/0040 §2); a missing line refuses here.
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
thinking_key="OPENAI_$(printf '%s' "$THINKING" | tr '[:lower:]' '[:upper:]')"
OPENAI_EFFORT=$(grep "^${thinking_key}=" "$here/thinking.env" | head -n1 | cut -d= -f2)
[ -n "$OPENAI_EFFORT" ] || { printf 'harness-codex: %s has no %s= line (docs/adr/0040 §2)\n' "$here/thinking.env" "$thinking_key" >&2; exit 1; }
export OPENAI_EFFORT

# The service mounts only this run's directory, OUT's parent, at the same
# suffix under /crew (docs/adr/0041 §4), never .crew/ itself.
crew_root=$(pwd)/.crew
to_container() { printf '/crew/%s' "${1#"$crew_root"/}"; }
run_dir=$(dirname "$OUT")
case "$run_dir/" in "$crew_root"/?*) ;; *) printf 'harness-codex: OUT=%s is not under %s/ (docs/adr/0041 §4)\n' "$OUT" "$crew_root" >&2; exit 1 ;; esac
for p in "$WORKSPACE" "$TICKET_FILE"; do
  case "$p" in "$run_dir"/*) ;; *) printf 'harness-codex: %s is outside the run directory %s, the only one the worker sees (docs/adr/0041 §4)\n' "$p" "$run_dir" >&2; exit 1 ;; esac
done
mkdir -p "$crew_root/.uv-cache"

# The repository's MCP servers for the dev-worker (docs/adr/0073 §8): set
# by core/crew.sh only when the base declares some, as CREW_MCP, a
# directory holding agents.py's decl.json. The declaration is copied into
# OUT (the one directory the container sees), translated there by mcp.sh,
# and each token named in it must have a real value before the container
# starts; it reaches the container by name (-e), never in a file.
set --
mcp_tokens=""
if [ -n "${CREW_MCP:-}" ]; then
  [ -f "$CREW_MCP/decl.json" ] || { printf 'harness-codex: CREW_MCP=%s holds no decl.json (docs/adr/0073 §7)\n' "$CREW_MCP" >&2; exit 1; }
  mkdir -p "$OUT/mcp"
  [ "$CREW_MCP" = "$OUT/mcp" ] || cp "$CREW_MCP/decl.json" "$OUT/mcp/decl.json"
  sh "$here/mcp.sh" "$OUT/mcp/decl.json" "$OUT/mcp" "$(to_container "$WORKSPACE")" || exit 1
  for v in $(jq -r '.servers[] | .token_env // empty' "$OUT/mcp/decl.json"); do
    case "$v" in
      MCP_*[!A-Z0-9_]*|MCP_) printf 'harness-codex: token_env %s is not an MCP_* name (docs/adr/0073 §6)\n' "$v" >&2; exit 1 ;;
      MCP_*) ;;
      *) printf 'harness-codex: token_env %s is not an MCP_* name (docs/adr/0073 §6)\n' "$v" >&2; exit 1 ;;
    esac
    token=""
    eval "token=\${$v:-}"
    case "$token" in
      ""|replace-me) printf 'harness-codex: mcp.json names %s, which needs a real value in .env (docs/adr/0073 §6)\n' "$v" >&2; exit 1 ;;
    esac
    set -- "$@" -e "$v"
    mcp_tokens="$mcp_tokens $v"
  done
  set -- "$@" -e CREW_MCP_DIR="$(to_container "$OUT/mcp")"
fi

# The one seam gates/harness-conformance.sh sets (docs/adr/0041 §7): the
# entrypoint turns it into a model provider of its own (codex ignores
# OPENAI_BASE_URL, verified 2026-11-04).
endpoint=${MODEL_BASE_URL:-}

# The one way out of the internal `crew` network (docs/adr/0046 §4): the
# egress proxy opens this harness's provider (MODEL_BASE_URL's host when it
# is set) and the hosts the workload's contract names, nothing else.
sh core/egress.sh "$(grep '^EGRESS=' "$here/conformance.env" | head -n1 | cut -d= -f2-)" || exit 1

mkdir -p "$OUT"
rm -f "$OUT/stop"
input_sha256=$(sha256sum "$TICKET_FILE" | cut -d' ' -f1)
start=$(date +%s)
container_rc=0
docker-compose --profile crew run --rm --build \
  -e ROLE -e TICKET \
  -e TICKET_FILE="$(to_container "$TICKET_FILE")" \
  -e CREW_WORKSPACE="$(to_container "$WORKSPACE")" \
  -e CREW_OUT="$(to_container "$OUT")" \
  -e THINKING -e MAX_TURNS -e TIMEOUT_S -e TOKEN_BUDGET \
  -e MODEL -e OPENAI_EFFORT \
  ${endpoint:+-e MODEL_BASE_URL="$endpoint"} \
  "$@" \
  -v "$run_dir:$(to_container "$run_dir")" \
  -v "$crew_root/.uv-cache:/crew/.uv-cache" \
  codex >&2 || container_rc=$?
end=$(date +%s)
duration=$((end - start))

transcript="$OUT/transcript.jsonl"

# Spend and served model, recorded before any verdict so a run that stops
# on a budget still says what it cost and who answered (gemini-cli's
# precedent, docs/adr/0018 §3). turns is the number of model requests the
# budget hook counted; tokens sum every turn.completed's usage (input,
# cached included, plus output).
turns=$(cat "$OUT/requests" 2>/dev/null || echo null)
case "$turns" in ''|*[!0-9]*) turns=null ;; esac
usage=$(jq -cs '[.[] | select(.type == "turn.completed") | .usage] | if length == 0 then null else {input: (map(.input_tokens // 0) | add), output: (map(.output_tokens // 0) | add)} end' "$transcript" 2>/dev/null) || usage=null
[ -n "$usage" ] || usage=null
tok_in=$(printf '%s' "$usage" | jq '.input // null')
tok_out=$(printf '%s' "$usage" | jq '.output // null')
tok_total=$(jq -n --argjson a "$tok_in" --argjson b "$tok_out" 'if $a == null or $b == null then null else $a + $b end')
model_served=$(cat "$OUT/served_model" 2>/dev/null || true)
[ -n "$model_served" ] || model_served=unknown

# What the run used of the repository's MCP servers (docs/adr/0073 §9),
# null when none was declared: the calls counted from hooks.log, the one
# record every harness writes in one shape (a hook-denied Codex call leaves
# no item in the event stream). enabled_tools hides the unnamed tools.
mcp=null
calls_err=""
if [ -n "${CREW_MCP:-}" ]; then
  hooks_log=$OUT/hooks.log
  [ -f "$hooks_log" ] || hooks_log=/dev/null
  calls=$(python3 core/agents.py calls --allow "$OUT/mcp/allow" --hooks "$hooks_log") || { calls_err=$calls; calls='{"calls": null, "denied": null}'; }
  mcp=$(jq -c --argjson c "$calls" --arg unlisted hidden \
    '{sha256, servers: [.servers[] | {name, transport} + (if .endpoint then {endpoint} else {} end) + {tools}],
      unlisted: $unlisted, calls: $c.calls, denied: $c.denied}' "$OUT/mcp/decl.json")
fi

jq -n \
  --arg harness codex --arg provider "$MODEL_PROVIDER" --arg model "$model_served" --arg thinking "$THINKING" \
  --argjson turns "$turns" --arg insha "$input_sha256" \
  --argjson tokIn "$tok_in" --argjson tokOut "$tok_out" --argjson tokTotal "$tok_total" \
  --argjson duration "$duration" --argjson exitCode "$container_rc" --arg endpoint "$endpoint" \
  --argjson mcp "$mcp" \
  '{harness: $harness, provider: $provider, model: $model, thinking: $thinking, turns: $turns,
    tokens: {input: $tokIn, output: $tokOut, total: $tokTotal},
    duration_s: $duration, exit_code: $exitCode, input_sha256: $insha}
    + (if $endpoint == "" then {} else {endpoint: $endpoint} end) + {mcp: $mcp}' > "$OUT/run.json"

# A declared server that did not come up fails the run (docs/adr/0073 §8):
# mcp.sh declares every server required, so `codex exec` fails before
# thread.started with "required MCP servers failed to initialize: <server>:
# <error>" on stderr; the line names the declared servers it mentions.
if [ -n "${CREW_MCP:-}" ]; then
  [ -z "$calls_err" ] || { printf 'harness-codex: core/agents.py calls: %s\n' "$calls_err" >&2; exit 1; }
  failed=$(awk 'index($0, "required MCP servers failed to initialize") { l = $0 } END { print l }' "$OUT/stderr.log" 2>/dev/null || true)
  if [ -n "$failed" ]; then
    down=""
    for s in $(jq -r '.servers[].name' "$OUT/mcp/decl.json"); do
      case "$failed" in *"$s:"*) down="$down${down:+, }$s" ;; esac
    done
    [ -n "$down" ] || down=$(jq -r '[.servers[].name] | join(", ")' "$OUT/mcp/decl.json")
    printf 'harness-codex: declared MCP server %s did not come up (ADR 0073 §8): %s\n' "$down" "$failed" >&2
    exit 1
  fi
fi

# The stop reason (docs/adr/0041 §5): the budget hook's marker (it kills
# codex, so the exit code is the TERM's), or timeout's 124.
stopped=$(cat "$OUT/stop" 2>/dev/null || true)
case "$stopped" in
  MAX_TURNS) printf 'harness-codex: over MAX_TURNS (%s)\n' "$MAX_TURNS" >&2; exit 1 ;;
  TOKEN_BUDGET) printf 'harness-codex: over TOKEN_BUDGET (%s)\n' "$TOKEN_BUDGET" >&2; exit 1 ;;
esac
if [ "$container_rc" -eq 124 ]; then
  printf 'harness-codex: over TIMEOUT_S (%s s)\n' "$TIMEOUT_S" >&2
  exit 1
fi
if [ "$container_rc" -ne 0 ]; then
  err=$(jq -rs '[.[] | select(.type == "turn.failed") | .error.message // empty] | last // empty' "$transcript" 2>/dev/null || true)
  [ -n "$err" ] || err=$(tail -n 1 "$OUT/stderr.log" 2>/dev/null || true)
  printf 'harness-codex: codex exited %s%s\n' "$container_rc" "${err:+: $err}" >&2
  exit 1
fi

# The adapter commits, not the model (docs/adr/0017 §1), before the
# response check, so a run without a final message leaves its work.
committed=0
if [ -n "$(git -C "$WORKSPACE" status --porcelain)" ]; then
  git -C "$WORKSPACE" add -A
  git -C "$WORKSPACE" -c user.name=lights-out-crew -c user.email=crew@lights-out.invalid \
    commit -q -m "WIP: incomplete run, no final message (docs/adr/0017 §1)" \
    -m "$(printf '%s tokens spent, %s turns. See %s/transcript.jsonl.' "$tok_total" "$turns" "$OUT")"
  committed=1
fi

response=$(jq -rs '[.[] | select(.type == "item.completed" and .item.type == "agent_message") | .item.text] | last // empty' "$transcript" 2>/dev/null || true)
if [ -z "$response" ]; then
  printf 'harness-codex: no agent_message in the event stream\n' >&2
  exit 1
fi

# The second artefact contract (docs/adr/0021 §3), then the same text as
# PR text for a writing role.
printf '%s\n' "$response" > "$OUT/final.md"
title=$(printf '%s\n' "$response" | head -n1)
body=$(printf '%s\n' "$response" | tail -n +2 | sed '/./,$!d')
jq -n --arg title "$title" --arg body "$body" '{title: $title, body: $body}' > "$OUT/pr.json"

if [ "$committed" -eq 1 ]; then
  git -C "$WORKSPACE" -c user.name=lights-out-crew -c user.email=crew@lights-out.invalid \
    commit -q --amend -m "$title" -m "$body"
fi

git -C "$WORKSPACE" format-patch --stdout "$BASE"..HEAD > "$OUT/patch" 2>/dev/null || : > "$OUT/patch"

# No credential in what gets recorded (docs/adr/0017 §3).
if grep -rFl "$OPENAI_API_KEY" "$OUT"/* >/dev/null 2>&1; then
  printf 'harness-codex: OPENAI_API_KEY appears in the run artefacts under %s; refusing to record\n' "$OUT" >&2
  exit 1
fi
for v in $mcp_tokens; do
  eval "token=\${$v}"
  if grep -rFl "$token" "$OUT"/* >/dev/null 2>&1; then
    printf 'harness-codex: %s appears in the run artefacts under %s; refusing to record\n' "$v" "$OUT" >&2
    exit 1
  fi
done

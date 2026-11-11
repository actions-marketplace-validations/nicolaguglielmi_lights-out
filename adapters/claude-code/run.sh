#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# harness-claude-code: the `claude-code` AgentHarness (docs/adr/0041).
# Runs one headless Claude Code session in the `claude-code` compose
# service (no engine socket, no git credential, only this run's directory
# mounted), then does what the entrypoint does not, on gemini-cli's
# pattern: reads the stop reason, the served model and the spend from the
# stream-json transcript, commits what the model left under the crew
# identity (the adapter commits, not the model, docs/adr/0017 §1), writes
# the patch, pr.json, final.md and run.json, and refuses to record
# anything if the key leaked into the artefacts. Shapes read here were
# verified live on 2.1.311 (docs/adr/0041, "Verified"): the last `result`
# event carries subtype, terminal_reason, num_turns, usage and the final
# text; each `assistant` event's message.model is the id the API served.
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
  anthropic) ;;
  gemini|openai)
    fits=gemini-cli; [ "$MODEL_PROVIDER" = openai ] && fits=codex
    printf 'harness-claude-code: MODEL_PROVIDER=%s runs on AGENT_HARNESS=%s (docs/adr/0041 §2); this harness runs anthropic only\n' "$MODEL_PROVIDER" "$fits" >&2
    exit 1
    ;;
  *)
    printf 'harness-claude-code: MODEL_PROVIDER=%s is not anthropic; this harness runs anthropic only (docs/adr/0041 §2)\n' "${MODEL_PROVIDER:-}" >&2
    exit 1
    ;;
esac
[ -n "${MODEL:-}" ] || { printf 'harness-claude-code: MODEL is empty; set the exact model id in the profile or .env (docs/adr/0040 §1)\n' >&2; exit 1; }
case "${ANTHROPIC_API_KEY:-}" in
  ""|replace-me)
    printf 'harness-claude-code: MODEL_PROVIDER=anthropic needs a real ANTHROPIC_API_KEY in .env (see .env.example)\n' >&2
    exit 1
    ;;
esac

# The role's THINKING mapped to --effort by this adapter's own map
# (docs/adr/0040 §2); a missing line refuses here.
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
thinking_key="ANTHROPIC_$(printf '%s' "$THINKING" | tr '[:lower:]' '[:upper:]')"
ANTHROPIC_EFFORT=$(grep "^${thinking_key}=" "$here/thinking.env" | head -n1 | cut -d= -f2)
[ -n "$ANTHROPIC_EFFORT" ] || { printf 'harness-claude-code: %s has no %s= line (docs/adr/0040 §2)\n' "$here/thinking.env" "$thinking_key" >&2; exit 1; }
export ANTHROPIC_EFFORT

# The service mounts only this run's directory, OUT's parent, at the same
# suffix under /crew (docs/adr/0041 §4), never .crew/ itself.
crew_root=$(pwd)/.crew
to_container() { printf '/crew/%s' "${1#"$crew_root"/}"; }
run_dir=$(dirname "$OUT")
case "$run_dir/" in "$crew_root"/?*) ;; *) printf 'harness-claude-code: OUT=%s is not under %s/ (docs/adr/0041 §4)\n' "$OUT" "$crew_root" >&2; exit 1 ;; esac
for p in "$WORKSPACE" "$TICKET_FILE"; do
  case "$p" in "$run_dir"/*) ;; *) printf 'harness-claude-code: %s is outside the run directory %s, the only one the worker sees (docs/adr/0041 §4)\n' "$p" "$run_dir" >&2; exit 1 ;; esac
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
  [ -f "$CREW_MCP/decl.json" ] || { printf 'harness-claude-code: CREW_MCP=%s holds no decl.json (docs/adr/0073 §7)\n' "$CREW_MCP" >&2; exit 1; }
  mkdir -p "$OUT/mcp"
  [ "$CREW_MCP" = "$OUT/mcp" ] || cp "$CREW_MCP/decl.json" "$OUT/mcp/decl.json"
  sh "$here/mcp.sh" "$OUT/mcp/decl.json" "$OUT/mcp" "$(to_container "$WORKSPACE")" || exit 1
  for v in $(jq -r '.servers[] | .token_env // empty' "$OUT/mcp/decl.json"); do
    case "$v" in
      MCP_*[!A-Z0-9_]*|MCP_) printf 'harness-claude-code: token_env %s is not an MCP_* name (docs/adr/0073 §6)\n' "$v" >&2; exit 1 ;;
      MCP_*) ;;
      *) printf 'harness-claude-code: token_env %s is not an MCP_* name (docs/adr/0073 §6)\n' "$v" >&2; exit 1 ;;
    esac
    token=""
    eval "token=\${$v:-}"
    case "$token" in
      ""|replace-me) printf 'harness-claude-code: mcp.json names %s, which needs a real value in .env (docs/adr/0073 §6)\n' "$v" >&2; exit 1 ;;
    esac
    set -- "$@" -e "$v"
    mcp_tokens="$mcp_tokens $v"
  done
  set -- "$@" -e CREW_MCP_DIR="$(to_container "$OUT/mcp")"
fi

# The one seam gates/harness-conformance.sh sets (docs/adr/0041 §7):
# Claude Code reads ANTHROPIC_BASE_URL. A workspace cannot set it: the
# entrypoint loads user settings only.
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
  -e MODEL -e ANTHROPIC_EFFORT \
  ${endpoint:+-e ANTHROPIC_BASE_URL="$endpoint"} \
  "$@" \
  -v "$run_dir:$(to_container "$run_dir")" \
  -v "$crew_root/.uv-cache:/crew/.uv-cache" \
  claude-code >&2 || container_rc=$?
end=$(date +%s)
duration=$((end - start))

transcript="$OUT/transcript.jsonl"
result=$(jq -cs '[.[] | select(.type == "result")] | last // {}' "$transcript" 2>/dev/null || echo '{}')
[ -n "$result" ] || result='{}'

# Spend and served model, recorded before any verdict so a run that stops
# on a budget still says what it cost and who answered (gemini-cli's
# precedent, docs/adr/0018 §3). The served id is the most frequent
# assistant message.model: result.modelUsage's keys echo the request.
turns=$(printf '%s' "$result" | jq '.num_turns // null')
tok_in=$(printf '%s' "$result" | jq '.usage // null | if . == null then null else (.input_tokens // 0) + (.cache_creation_input_tokens // 0) + (.cache_read_input_tokens // 0) end')
tok_out=$(printf '%s' "$result" | jq '.usage.output_tokens // null')
tok_total=$(jq -n --argjson a "$tok_in" --argjson b "$tok_out" 'if $a == null or $b == null then null else $a + $b end')
model_served=$(jq -rs '[.[] | select(.type == "assistant") | .message.model // empty] | group_by(.) | max_by(length) | .[0] // "unknown"' "$transcript" 2>/dev/null || echo unknown)
[ -n "$model_served" ] || model_served=unknown

# What the run used of the repository's MCP servers (docs/adr/0073 §9),
# null when none was declared: the calls counted from hooks.log, the one
# record every harness writes in one shape. A declared server's unnamed
# tools are visible to the model here and denied, twice.
mcp=null
calls_err=""
if [ -n "${CREW_MCP:-}" ]; then
  hooks_log=$OUT/hooks.log
  [ -f "$hooks_log" ] || hooks_log=/dev/null
  calls=$(python3 core/agents.py calls --allow "$OUT/mcp/allow" --hooks "$hooks_log") || { calls_err=$calls; calls='{"calls": null, "denied": null}'; }
  mcp=$(jq -c --argjson c "$calls" --arg unlisted visible-denied \
    '{sha256, servers: [.servers[] | {name, transport} + (if .endpoint then {endpoint} else {} end) + {tools}],
      unlisted: $unlisted, calls: $c.calls, denied: $c.denied}' "$OUT/mcp/decl.json")
fi

jq -n \
  --arg harness claude-code --arg provider "$MODEL_PROVIDER" --arg model "$model_served" --arg thinking "$THINKING" \
  --argjson turns "$turns" --arg insha "$input_sha256" \
  --argjson tokIn "$tok_in" --argjson tokOut "$tok_out" --argjson tokTotal "$tok_total" \
  --argjson duration "$duration" --argjson exitCode "$container_rc" --arg endpoint "$endpoint" \
  --argjson mcp "$mcp" \
  '{harness: $harness, provider: $provider, model: $model, thinking: $thinking, turns: $turns,
    tokens: {input: $tokIn, output: $tokOut, total: $tokTotal},
    duration_s: $duration, exit_code: $exitCode, input_sha256: $insha}
    + (if $endpoint == "" then {} else {endpoint: $endpoint} end) + {mcp: $mcp}' > "$OUT/run.json"

# A declared server that did not come up fails the run (docs/adr/0073 §8):
# Claude Code goes on without it, and says so only in system/init's
# mcp_servers (any status but `connected`) and mcp_server_errors.
if [ -n "${CREW_MCP:-}" ]; then
  [ -z "$calls_err" ] || { printf 'harness-claude-code: core/agents.py calls: %s\n' "$calls_err" >&2; exit 1; }
  down=$(jq -rs --slurpfile d "$OUT/mcp/decl.json" '
    ([.[] | select(.type == "system" and .subtype == "init")] | first) as $init
    | if $init == null then empty else
        ([($init.mcp_servers // [])[] | {key: .name, value: (.status // "no status")}] | from_entries) as $st
        | [($d[0].servers[].name | select($st[.] != "connected") | "\(.) (\($st[.] // "absent"))"),
           (($init.mcp_server_errors // [])[] | "\(.name // "?") (\(.message // .type // "error"))")]
        | unique | join(", ")
      end' "$transcript" 2>/dev/null || true)
  if [ -n "$down" ]; then
    printf 'harness-claude-code: declared MCP server %s did not come up (ADR 0073 §8)\n' "$down" >&2
    exit 1
  fi
fi

# The stop reason (docs/adr/0041 §5): the budget hook's marker, the result
# event's subtype, or timeout's 124, never the exit code alone (Claude
# Code exits 1 both over --max-turns and on an error).
subtype=$(printf '%s' "$result" | jq -r '.subtype // empty')
terminal=$(printf '%s' "$result" | jq -r '.terminal_reason // empty')
stopped=$(cat "$OUT/stop" 2>/dev/null || true)
if [ "$stopped" = TOKEN_BUDGET ] || [ "$terminal" = hook_stopped ]; then
  printf 'harness-claude-code: over TOKEN_BUDGET (%s)\n' "$TOKEN_BUDGET" >&2
  exit 1
fi
if [ "$subtype" = error_max_turns ]; then
  printf 'harness-claude-code: over MAX_TURNS (%s)\n' "$MAX_TURNS" >&2
  exit 1
fi
if [ "$container_rc" -eq 124 ]; then
  printf 'harness-claude-code: over TIMEOUT_S (%s s)\n' "$TIMEOUT_S" >&2
  exit 1
fi
if [ "$container_rc" -ne 0 ] || [ "$subtype" != success ]; then
  err=$(printf '%s' "$result" | jq -r '[(.errors // [])[], (.result // empty)] | map(tostring) | join("; ")' 2>/dev/null || true)
  [ -n "$err" ] || err=$(tail -n 1 "$OUT/stderr.log" 2>/dev/null || true)
  printf 'harness-claude-code: claude exited %s (%s)%s\n' "$container_rc" "${subtype:-no result event}" "${err:+: $err}" >&2
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

response=$(printf '%s' "$result" | jq -r '.result // empty')
if [ -z "$response" ]; then
  printf 'harness-claude-code: the result event carries no final message\n' >&2
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
if grep -rFl "$ANTHROPIC_API_KEY" "$OUT"/* >/dev/null 2>&1; then
  printf 'harness-claude-code: ANTHROPIC_API_KEY appears in the run artefacts under %s; refusing to record\n' "$OUT" >&2
  exit 1
fi
for v in $mcp_tokens; do
  eval "token=\${$v}"
  if grep -rFl "$token" "$OUT"/* >/dev/null 2>&1; then
    printf 'harness-claude-code: %s appears in the run artefacts under %s; refusing to record\n' "$v" "$OUT" >&2
    exit 1
  fi
done

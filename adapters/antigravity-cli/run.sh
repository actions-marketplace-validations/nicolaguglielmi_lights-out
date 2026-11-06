#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# harness-antigravity-cli: the `antigravity-cli` AgentHarness (docs/adr/
# 0050), optional and experimental beside gemini-cli, which stays the
# default for MODEL_PROVIDER=gemini. Runs one headless agy turn in the
# `antigravity-cli` compose service (no engine socket, no git credential,
# docs/adr/0041 §3), then does everything the entrypoint does not, as
# gemini-cli's run.sh does: the final message from the transcript, the
# served model from agy's conversation store, the commit under the crew
# identity (docs/adr/0017 §1), the patch, pr.json, final.md and run.json,
# and a refusal to record anything if the key leaked into the artefacts.
#
# The stream-json shapes read below were verified on 2026-11-05/06 against
# agy 1.5.1 and a scripted model (docs/adr/0050 "Verified"), never against
# the real API's streaming: one `init` event, then `step_update` events
# ({step_index, state, step_type, text_delta, usage, tool_name}), then one
# `result` ({status, response, error, usage, num_turns}). `result.response`
# joins the text of every agent_response step (a run whose model said
# "waiting" before its final answer reports both), so the final message is
# the text of the last agent_response step that has any; usage is per
# agent_response step, one per model call. Adapter convention (docs/adr/
# 0012 §6): not a gate, silent on success, one stderr line and exit 1 on
# failure.
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

# One provider per harness (docs/adr/0041 §2); gemini has two harnesses
# since docs/adr/0050 §1, and this one is chosen only by AGENT_HARNESS.
case "${MODEL_PROVIDER:-}" in
  gemini) ;;
  anthropic|openai)
    fits=claude-code; [ "$MODEL_PROVIDER" = openai ] && fits=codex
    printf 'harness-antigravity-cli: MODEL_PROVIDER=%s runs on AGENT_HARNESS=%s (docs/adr/0041 §2); this harness runs gemini only\n' "$MODEL_PROVIDER" "$fits" >&2
    exit 1
    ;;
  *)
    printf 'harness-antigravity-cli: MODEL_PROVIDER=%s is not gemini; this harness runs gemini only (docs/adr/0041 §2)\n' "${MODEL_PROVIDER:-}" >&2
    exit 1
    ;;
esac
[ -n "${MODEL:-}" ] || { printf 'harness-antigravity-cli: MODEL is empty; set the exact model id in the profile or .env (docs/adr/0040 §1)\n' >&2; exit 1; }
case "${GEMINI_API_KEY:-}" in
  ""|replace-me)
    printf 'harness-antigravity-cli: MODEL_PROVIDER=gemini needs a real GEMINI_API_KEY in .env (see .env.example)\n' >&2
    exit 1
    ;;
esac

# The role's THINKING mapped by this adapter's own map (docs/adr/0040 §2).
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
thinking_key="GEMINI_$(printf '%s' "$THINKING" | tr '[:lower:]' '[:upper:]')"
AGY_EFFORT=$(grep "^${thinking_key}=" "$here/thinking.env" | head -n1 | cut -d= -f2)
[ -n "$AGY_EFFORT" ] || { printf 'harness-antigravity-cli: %s has no %s= line (docs/adr/0040 §2)\n' "$here/thinking.env" "$thinking_key" >&2; exit 1; }
export AGY_EFFORT

# The run's own directory, mounted alone (docs/adr/0041 §4), as gemini-cli's.
crew_root=$(pwd)/.crew
to_container() { printf '/crew/%s' "${1#"$crew_root"/}"; }
run_dir=$(dirname "$OUT")
case "$run_dir/" in "$crew_root"/?*) ;; *) printf 'harness-antigravity-cli: OUT=%s is not under %s/ (docs/adr/0041 §4)\n' "$OUT" "$crew_root" >&2; exit 1 ;; esac
for p in "$WORKSPACE" "$TICKET_FILE"; do
  case "$p" in "$run_dir"/*) ;; *) printf 'harness-antigravity-cli: %s is outside the run directory %s, the only one the worker sees (docs/adr/0041 §4)\n' "$p" "$run_dir" >&2; exit 1 ;; esac
done
mkdir -p "$crew_root/.uv-cache"

# MODEL_BASE_URL is the conformance suite's seam (docs/adr/0041 §7). agy
# honours GOOGLE_GEMINI_BASE_URL (verified 2026-11-05); always set, to the
# API's own host when the seam is unset, as gemini-cli's run.sh does.
endpoint=${MODEL_BASE_URL:-}
gemini_base_url=${endpoint:-https://generativelanguage.googleapis.com}

# The one way out of `crew` (docs/adr/0046 §4). It also keeps the pin: agy
# checks its updater host on every run, and the proxy denies it.
sh core/egress.sh "$(grep '^EGRESS=' "$here/conformance.env" | head -n1 | cut -d= -f2-)" || exit 1

store=$run_dir/.agy-conversations
mkdir -p "$OUT"
rm -rf "$OUT/stop" "$store"
input_sha256=$(sha256sum "$TICKET_FILE" | cut -d' ' -f1)
start=$(date +%s)
container_rc=0
docker-compose --profile crew run --rm --build \
  -e ROLE -e TICKET \
  -e TICKET_FILE="$(to_container "$TICKET_FILE")" \
  -e CREW_WORKSPACE="$(to_container "$WORKSPACE")" \
  -e CREW_OUT="$(to_container "$OUT")" \
  -e THINKING -e MAX_TURNS -e TIMEOUT_S -e TOKEN_BUDGET \
  -e MODEL -e AGY_EFFORT \
  -e GOOGLE_GEMINI_BASE_URL="$gemini_base_url" \
  -v "$run_dir:$(to_container "$run_dir")" \
  -v "$crew_root/.uv-cache:/crew/.uv-cache" \
  antigravity-cli >&2 || container_rc=$?
end=$(date +%s)
duration=$((end - start))

# The served model (docs/adr/0050 §5), then the store goes: it holds the
# whole conversation and is never an artefact.
model_served=$(python3 -I "$here/served_model.py" "$store" 2>/dev/null || echo unknown)
[ -n "$model_served" ] || model_served=unknown
rm -rf "$store"

# The budget hook names the budget it stopped on in OUT/stop (docs/adr/0041
# §5); agy then exits 3, the code it also uses for its own print timeout.
stopped=$(cat "$OUT/stop" 2>/dev/null || true)
case "$stopped" in
  MAX_TURNS) printf 'harness-antigravity-cli: over MAX_TURNS (%s)\n' "$MAX_TURNS" >&2; exit 1 ;;
  TOKEN_BUDGET) printf 'harness-antigravity-cli: over TOKEN_BUDGET (%s)\n' "$TOKEN_BUDGET" >&2; exit 1 ;;
esac
if [ "$container_rc" -ne 0 ]; then
  reason="agy exited $container_rc"
  if [ "$container_rc" -eq 124 ]; then
    reason="over TIMEOUT_S ($TIMEOUT_S s)"
  else
    err=$(jq -rs '[.[] | select(.event == "result")] | last | (.result.error // empty)' \
      "$OUT/transcript.jsonl" 2>/dev/null || true)
    [ -n "$err" ] && reason="$reason: $err"
  fi
  printf 'harness-antigravity-cli: %s\n' "$reason" >&2
  exit 1
fi

# One record per step: the last update of each step_index wins, the text is
# every update's text_delta for that step joined.
steps=$(jq -cs '[.[] | select(.event == "step_update") | .step_update]
  | group_by(.step_index)
  | map({type: (last.step_type), text: (map(.text_delta // "") | join("")),
         usage: (map(.usage // empty) | last)})' "$OUT/transcript.jsonl" 2>/dev/null || echo '[]')
response=$(printf '%s' "$steps" | jq -r '[.[] | select(.type == "agent_response" and (.text | test("\\S")))] | last | .text // ""')
turns=$(printf '%s' "$steps" | jq '[.[] | select(.type == "agent_response")] | length')
tok_in=$(printf '%s' "$steps" | jq '[.[] | .usage.input_tokens // empty] | add // null')
tok_out=$(printf '%s' "$steps" | jq '[.[] | .usage.output_tokens // empty] | add // null')
tok_total=$(printf '%s' "$steps" | jq '[.[] | .usage.total_tokens // empty] | add // null')
tool_calls=$(printf '%s' "$steps" | jq '[.[] | select(.type == "tool")] | length')

# run.json before the response check, so a run without a final message
# still records what answered and what it spent (gemini-cli's reason).
jq -n \
  --arg harness antigravity-cli --arg provider "$MODEL_PROVIDER" --arg model "$model_served" --arg thinking "$THINKING" \
  --argjson turns "$turns" --arg insha "$input_sha256" \
  --argjson tokIn "$tok_in" --argjson tokOut "$tok_out" --argjson tokTotal "$tok_total" \
  --argjson duration "$duration" --argjson exitCode "$container_rc" --arg endpoint "$endpoint" \
  '{harness: $harness, provider: $provider, model: $model, thinking: $thinking, turns: $turns,
    tokens: {input: $tokIn, output: $tokOut, total: $tokTotal},
    duration_s: $duration, exit_code: $exitCode, input_sha256: $insha}
    + (if $endpoint == "" then {} else {endpoint: $endpoint} end)' > "$OUT/run.json"

# The adapter commits, not the model (docs/adr/0017 §1).
committed=0
if [ -n "$(git -C "$WORKSPACE" status --porcelain)" ]; then
  git -C "$WORKSPACE" add -A
  git -C "$WORKSPACE" -c user.name=lights-out-crew -c user.email=crew@lights-out.invalid \
    commit -q -m "WIP: incomplete run, no final message (docs/adr/0017 §1)" \
    -m "$(printf '%s tokens spent, %s tool calls, %s s. See %s/transcript.jsonl.' "$tok_total" "$tool_calls" "$duration" "$OUT")"
  committed=1
fi

if [ -z "$response" ]; then
  printf 'harness-antigravity-cli: no final agent message in the transcript\n' >&2
  exit 1
fi

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
if grep -rFl "$GEMINI_API_KEY" "$OUT"/* >/dev/null 2>&1; then
  printf 'harness-antigravity-cli: GEMINI_API_KEY appears in the run artefacts under %s; refusing to record\n' "$OUT" >&2
  exit 1
fi

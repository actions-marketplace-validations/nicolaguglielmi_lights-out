#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# harness-gemini-cli: the `gemini-cli` AgentHarness (docs/adr/0017 §3).
# Runs one headless turn in the `gemini-cli` compose service (no engine
# socket, no credential the model can push with), then does everything the
# entrypoint does not: reconstructs the model's final response from the
# transcript's streamed `message` events, reads the `result` event's flat
# `stats` object, commits whatever is left in the workspace under the crew
# identity (the adapter commits, not the model, docs/adr/0017 §1), writes
# the patch and run.json, and refuses to record anything if the API key
# leaked into the artefacts. The event and stats shapes below are read
# from the installed @google/gemini-cli@0.59.0 bundle itself
# (StreamJsonFormatter.convertToStreamStats and the message/result event
# emitters in bundle/gemini-CQYKWDIK.js), not guessed: --output-format
# stream-json has no `response` field on `result` at all, and `stats` is
# flat (`total_tokens`, not `tokens.total`) — corrections to this file's
# first draft, made before any real run, and the reason docs/adr/0017
# still lists "Verify at L1" items for what static reading cannot confirm
# (throttling, retry behaviour, the exact turn count under `--yolo`).
# Adapter convention (docs/adr/0012 §6): not a gate, silent on success, one
# stderr line and exit 1 on failure.
set -eu
: "${ROLE:?ROLE not set}"
: "${TICKET:?TICKET not set}"
: "${WORKSPACE:?WORKSPACE not set}"
: "${BASE:?BASE not set}"
: "${OUT:?OUT not set}"
: "${THINKING:?THINKING not set}"
: "${MAX_TURNS:?MAX_TURNS not set}"
: "${TIMEOUT_S:?TIMEOUT_S not set}"
: "${TOKEN_BUDGET:?TOKEN_BUDGET not set}"

case "${GEMINI_API_KEY:-}" in
  ""|replace-me)
    printf 'harness-gemini-cli: GEMINI_API_KEY is empty or the .env.example placeholder; set it in .env\n' >&2
    exit 1
    ;;
esac

mkdir -p "$OUT"
start=$(date +%s)
container_rc=0
docker-compose --profile crew run --rm --build \
  -e ROLE -e TICKET \
  -e TICKET_FILE="/crew/$TICKET/ticket.md" \
  -e CREW_WORKSPACE="/crew/$TICKET/workspace" \
  -e CREW_OUT="/crew/$TICKET/out" \
  -e THINKING -e MAX_TURNS -e TIMEOUT_S -e TOKEN_BUDGET \
  gemini-cli >&2 || container_rc=$?
end=$(date +%s)
duration=$((end - start))

if [ "$container_rc" -ne 0 ]; then
  reason="gemini exited $container_rc"
  case "$container_rc" in
    124) reason="over TIMEOUT_S ($TIMEOUT_S s)" ;;
    53) reason="over MAX_TURNS ($MAX_TURNS)" ;;
    55) reason="workspace not trusted (found live: entrypoint.sh's --skip-trust should prevent this; if it recurs, that flag or GEMINI_CLI_TRUST_WORKSPACE stopped working)" ;;
    *)
      # On a fatal error the last `result` event itself carries
      # status:"error" and an `error` object (no separate "error"-typed
      # event exists in this build).
      err=$(jq -rs '[.[] | select(.type == "result" and .status == "error")] | last | (.error.message // empty)' \
        "$OUT/transcript.jsonl" 2>/dev/null || true)
      [ -n "$err" ] && reason="$reason: $err"
      ;;
  esac
  printf 'harness-gemini-cli: %s\n' "$reason" >&2
  exit 1
fi

# stream-json's `result` event carries no response text (verified against
# the installed bundle) — the model's final answer is reconstructed from
# `message` events with role "assistant" (each a streamed delta). Found
# live (record attempt 4): the model narrates continuously between tool
# calls (a "message" burst before nearly every tool_use), so joining every
# assistant message across the whole session produces a soup of "I will…
# I have…" planning narration, not a PR title. Only the assistant message
# content strictly *after* the last tool_use/tool_result event is the
# model's actual trailing response; everything before it is commentary on
# an action already superseded by the next tool call.
response=$(jq -rs '
    . as $arr
  | ([$arr[] | select(.type == "tool_use" or .type == "tool_result")] | length) as $n
  | if $n == 0 then
      [$arr[] | select(.type == "message" and .role == "assistant") | .content] | join("")
    else
      ($arr | to_entries | map(select(.value.type == "tool_use" or .value.type == "tool_result")) | last | .key) as $lastToolIdx
      | [$arr[($lastToolIdx + 1):][] | select(.type == "message" and .role == "assistant") | .content] | join("")
    end
  ' "$OUT/transcript.jsonl" 2>/dev/null || true)

# The last `result` event's `stats` object (flat field names, verified
# against StreamJsonFormatter.convertToStreamStats in the installed
# bundle). No turn count is reported there; approximated by the number of
# "message" events with role "user", each opening one turn (the initial
# prompt counts as the first) — a caveat recorded here, not guessed twice.
# `stats.models`' own key names the model that actually answered — recorded
# here rather than the model requested on the command line, because they
# have already, once, been observed to differ (docs/adr/0017, "Contradicts
# the plan" section).
stats=$(jq -cs '[.[] | select(.type == "result")] | last | .stats // {}' "$OUT/transcript.jsonl" 2>/dev/null || echo '{}')
turns=$(jq -rs '[.[] | select(.type == "message" and .role == "user")] | length' "$OUT/transcript.jsonl" 2>/dev/null || echo null)
tok_in=$(printf '%s' "$stats" | jq -r '.input_tokens // null')
tok_out=$(printf '%s' "$stats" | jq -r '.output_tokens // null')
tok_total=$(printf '%s' "$stats" | jq -r '.total_tokens // null')
model_served=$(printf '%s' "$stats" | jq -r '.models | keys | first // "unknown"')

# The adapter commits, not the model (docs/adr/0017 §1): whatever the
# model left uncommitted is staged and committed here, under the crew
# identity, before the response-extraction check below, so a run that
# ran out of budget mid-task (found live: record attempt 5, TOKEN_BUDGET
# exceeded right after the last successful tool call, no trailing message
# to extract) still leaves its real work in the workspace for study,
# instead of that work being silently discarded by an early exit.
committed=0
if [ -n "$(git -C "$WORKSPACE" status --porcelain)" ]; then
  git -C "$WORKSPACE" add -A
  git -C "$WORKSPACE" -c user.name=lights-out-crew -c user.email=crew@lights-out.invalid \
    commit -q -m "WIP: incomplete run, no final message (docs/adr/0017 §1)" \
    -m "$(printf '%s tokens spent, %s tool calls, %s ms. See %s/transcript.jsonl.' \
      "$tok_total" "$(printf '%s' "$stats" | jq -r '.tool_calls // "?"')" \
      "$(printf '%s' "$stats" | jq -r '.duration_ms // "?"')" "$OUT")"
  committed=1
fi

if [ -z "$response" ]; then
  printf 'harness-gemini-cli: no trailing assistant message after the last tool call\n' >&2
  exit 1
fi

title=$(printf '%s\n' "$response" | head -n1)
body=$(printf '%s\n' "$response" | tail -n +2 | sed '/./,$!d')
jq -n --arg title "$title" --arg body "$body" '{title: $title, body: $body}' > "$OUT/pr.json"

# A real final message arrived after all: the WIP commit above is amended
# with the actual title and body, so the one commit over BASE carries the
# real PR text, not the placeholder.
if [ "$committed" -eq 1 ]; then
  git -C "$WORKSPACE" -c user.name=lights-out-crew -c user.email=crew@lights-out.invalid \
    commit -q --amend -m "$title" -m "$body"
fi

git -C "$WORKSPACE" format-patch --stdout "$BASE"..HEAD > "$OUT/patch" 2>/dev/null || : > "$OUT/patch"

jq -n \
  --arg harness gemini-cli --arg model "$model_served" --arg thinking "$THINKING" \
  --argjson turns "$turns" \
  --argjson tokIn "$tok_in" --argjson tokOut "$tok_out" --argjson tokTotal "$tok_total" \
  --argjson duration "$duration" --argjson exitCode "$container_rc" \
  '{harness: $harness, model: $model, thinking: $thinking, turns: $turns,
    tokens: {input: $tokIn, output: $tokOut, total: $tokTotal},
    duration_s: $duration, exit_code: $exitCode}' > "$OUT/run.json"

# No credential in what gets recorded (docs/adr/0017 §3): a leak here means
# the run is not usable as a fixture, and nothing is silently kept.
if grep -rFl "$GEMINI_API_KEY" "$OUT"/* >/dev/null 2>&1; then
  printf 'harness-gemini-cli: GEMINI_API_KEY appears in the run artefacts under %s; refusing to record\n' "$OUT" >&2
  exit 1
fi

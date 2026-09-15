#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# harness-gemini-cli: the `gemini-cli` AgentHarness (docs/adr/0017 §3).
# Runs one headless turn in the `gemini-cli` compose service (no engine
# socket, no credential the model can push with), then does everything the
# entrypoint does not: parses the transcript's `result` event into pr.json,
# commits whatever is left in the workspace under the crew identity (the
# adapter commits, not the model, docs/adr/0017 §1), writes the patch and
# run.json, and refuses to record anything if the API key leaked into the
# artefacts. Field names for the `result` event and its stats are read
# defensively (`// empty`, several candidates) because they are exactly
# what docs/adr/0017's "Verify at L1" list closes against a real
# transcript; a mismatch here is corrected there, not guessed twice.
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
    *)
      err=$(jq -rs '[.[] | select(.type == "error")] | last | (.error.message // .message // empty)' \
        "$OUT/transcript.jsonl" 2>/dev/null || true)
      [ -n "$err" ] && reason="$reason: $err"
      ;;
  esac
  printf 'harness-gemini-cli: %s\n' "$reason" >&2
  exit 1
fi

# The last `result` event in the stream carries the final response and the
# run's stats (docs/adr/0017 §3, "Verify at L1" #3).
result=$(jq -cs '[.[] | select(.type == "result")] | last // {}' "$OUT/transcript.jsonl" 2>/dev/null || echo '{}')
response=$(printf '%s' "$result" | jq -r '.response // .result // .text // empty')
if [ -z "$response" ]; then
  printf 'harness-gemini-cli: no result event with a response in the transcript\n' >&2
  exit 1
fi

title=$(printf '%s\n' "$response" | head -n1)
body=$(printf '%s\n' "$response" | tail -n +2 | sed '/./,$!d')
printf '%s' "$result" | jq \
  --arg title "$title" --arg body "$body" \
  '{title: $title, body: $body}' > "$OUT/pr.json"

turns=$(printf '%s' "$result" | jq -r '.stats.turns // .stats.turnCount // .stats.turn_count // null')
tok_in=$(printf '%s' "$result" | jq -r '.stats.tokens.input // .stats.usage.inputTokens // .stats.usage.input_tokens // null')
tok_out=$(printf '%s' "$result" | jq -r '.stats.tokens.output // .stats.usage.outputTokens // .stats.usage.output_tokens // null')
tok_total=$(printf '%s' "$result" | jq -r '.stats.tokens.total // .stats.usage.totalTokens // .stats.usage.total_tokens // null')

# The adapter commits, not the model (docs/adr/0017 §1): whatever the
# model left uncommitted is staged and committed here, under the crew
# identity, with the same title and body as the PR.
if [ -n "$(git -C "$WORKSPACE" status --porcelain)" ]; then
  git -C "$WORKSPACE" add -A
  git -C "$WORKSPACE" -c user.name=lights-out-crew -c user.email=crew@lights-out.invalid \
    commit -q -m "$title" -m "$body"
fi

git -C "$WORKSPACE" format-patch --stdout "$BASE"..HEAD > "$OUT/patch" 2>/dev/null || : > "$OUT/patch"

jq -n \
  --arg harness gemini-cli --arg model gemini-3.8-flash --arg thinking "$THINKING" \
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

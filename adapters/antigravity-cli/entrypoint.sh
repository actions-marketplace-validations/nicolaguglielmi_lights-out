#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# crew-entrypoint: runs inside the antigravity-cli service (docs/adr/0050).
# Installs the role's prompt as the global GEMINI.md, writes agy's
# settings and hooks under ~/.gemini, then runs one headless turn against
# CREW_WORKSPACE, capturing the stream-json transcript and the exit code
# under CREW_OUT. After the run it copies agy's conversation store to the
# run directory, beside OUT, where run.sh reads the served model from it
# and removes it (docs/adr/0050 §5). Does not commit, does not push, does
# not build pr.json or run.json: run.sh does, in workbench (docs/adr/0017
# §1), as for every CLI harness.
#
# Every fact below was verified on 2026-11-05/06 against agy 1.5.1 in the
# spike of docs/adr/0050 ("Verified"):
#   - ~/.gemini/GEMINI.md reaches the request (a marker in it was in the
#     first request's body; ~/.gemini/antigravity-cli/GEMINI.md was not).
#   - settings: modelProvider "gemini" with GEMINI_API_KEY is the API-key
#     mode; trustedWorkspaces avoids the trust prompt; hooks written in
#     settings.json are ignored, ~/.gemini/config/hooks.json is read.
#   - hooks.json is keyed by hook name, and a workspace's .agents/hooks.json
#     can disable a user hook by that name ({"guard": {"enabled": false}}
#     did). So both names carry a random suffix, new every run: a
#     repository cannot name what it cannot know.
#   - --dangerously-skip-permissions approves every tool call headless and
#     runs as uid 0, which the crew service is under rootless podman.
#   - --print-timeout defaults to 0 (no limit): TIMEOUT_S is coreutils
#     `timeout`, exit 124, as for every harness.
set -eu
: "${ROLE:?ROLE not set}"
: "${TICKET:?TICKET not set}"
: "${TICKET_FILE:?TICKET_FILE not set}"
: "${CREW_WORKSPACE:?CREW_WORKSPACE not set}"
: "${CREW_OUT:?CREW_OUT not set}"
: "${THINKING:?THINKING not set}"
: "${MAX_TURNS:?MAX_TURNS not set}"
: "${TIMEOUT_S:?TIMEOUT_S not set}"
: "${TOKEN_BUDGET:?TOKEN_BUDGET not set}"
: "${MODEL:?MODEL not set}"
: "${AGY_EFFORT:?AGY_EFFORT not set}"
export CREW_OUT TOKEN_BUDGET MAX_TURNS

conf=$HOME/.gemini
mkdir -p "$conf/antigravity-cli" "$conf/config" "$CREW_OUT"
cp "/roles/$ROLE/prompt.md" "$conf/GEMINI.md"

jq -n --arg ws "$CREW_WORKSPACE" '{modelProvider: "gemini", trustedWorkspaces: [$ws]}' \
  > "$conf/antigravity-cli/settings.json"

# PreToolUse matcher "*", as every harness's pre-tool hook (docs/adr/0041 §3,
# amended): every tool call reaches agy-guard.sh, which decides.
suffix=$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')
jq -n --arg guard "guard-$suffix" --arg budget "budget-$suffix" '{
    ($guard): {PreToolUse: [{matcher: "*", hooks: [{type: "command", command: "/opt/antigravity-cli-hooks/agy-guard.sh"}]}]},
    ($budget): {PreInvocation: [{type: "command", command: "/opt/antigravity-cli-hooks/budget.sh"}]}
  }' > "$conf/config/hooks.json"

{
  cat "$TICKET_FILE"
  printf '\n---\n\n'
  printf 'Work only inside this repository checkout. Do not run git push or\n'
  printf 'git commit yourself: committing and pushing are not your job, the\n'
  printf 'platform does that if your role needs it. When you are done, or when\n'
  printf 'you believe your task is resolved, your final message is this run'"'"'s\n'
  printf 'sole artefact: it must contain exactly what your instructions above\n'
  printf 'say your final message must be, nothing else.\n'
} > "$CREW_OUT/prompt.md"

# AGY_EFFORT is the role's THINKING mapped by run.sh from thinking.env, the
# value the request carries (LOW|MEDIUM|HIGH); the flag takes it lower-case.
effort=$(printf '%s' "$AGY_EFFORT" | tr '[:upper:]' '[:lower:]')

cd "$CREW_WORKSPACE"
rc=0
timeout "$TIMEOUT_S" agy \
  -p "$(cat "$CREW_OUT/prompt.md")" \
  --output-format stream-json \
  --dangerously-skip-permissions \
  --model "$MODEL" \
  --effort "$effort" \
  > "$CREW_OUT/transcript.jsonl" 2> "$CREW_OUT/stderr.log" || rc=$?

# The conversation store, the only place the served model is written
# (docs/adr/0050 §5): beside OUT, never in it, so it is never an artefact.
store=$(dirname "$CREW_OUT")/.agy-conversations
rm -rf "$store"
cp -R "$conf/antigravity-cli/conversations" "$store" 2>/dev/null || :

printf '%s' "$rc" > "$CREW_OUT/exit_code"
exit "$rc"

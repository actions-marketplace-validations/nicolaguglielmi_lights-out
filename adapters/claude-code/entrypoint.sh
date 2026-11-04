#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# crew-entrypoint: runs inside the claude-code service (docs/adr/0041 §1).
# Writes the hook settings, then runs one headless Claude Code session
# against CREW_WORKSPACE, capturing the stream-json transcript and the exit
# code under CREW_OUT. Does not commit, push or build pr.json/run.json:
# that is adapters/claude-code/run.sh's job in workbench (docs/adr/0017
# §1, the adapter commits, not the model).
#
# Verified live on 2.1.311 (docs/adr/0041, "Verified"): PreToolUse hooks
# passed with --settings fire in -p mode and exit 2 denies; --max-turns
# ends the run with result.subtype error_max_turns; a hook printing
# {"continue":false} ends it with terminal_reason hook_stopped.
#  - No --dangerously-skip-permissions: it refuses uid 0, which the crew
#    service is under rootless podman; --tools and --allowedTools name the
#    same four tools, so nothing is left to prompt in -p.
#  - --setting-sources user: found building M19, a workspace's own
#    .claude/settings.json with "disableAllHooks": true switched the
#    guard off under the default sources; with only user settings (none
#    here) plus --settings it cannot.
#  - Never --bare: it skips hooks.
set -eu
: "${ROLE:?ROLE not set}"
: "${TICKET_FILE:?TICKET_FILE not set}"
: "${CREW_WORKSPACE:?CREW_WORKSPACE not set}"
: "${CREW_OUT:?CREW_OUT not set}"
: "${MAX_TURNS:?MAX_TURNS not set}"
: "${TIMEOUT_S:?TIMEOUT_S not set}"
: "${TOKEN_BUDGET:?TOKEN_BUDGET not set}"
: "${MODEL:?MODEL not set}"
: "${ANTHROPIC_EFFORT:?ANTHROPIC_EFFORT not set}"
export CREW_OUT TOKEN_BUDGET

mkdir -p "$HOME/.claude" "$CREW_OUT"

hooks=/opt/claude-code-hooks
settings=$(jq -cn --arg guard "$hooks/guard.sh" --arg budget "$hooks/budget.sh" '{
  hooks: {
    PreToolUse: [{matcher: "*", hooks: [{type: "command", command: $guard}, {type: "command", command: $budget}]}]
  }
}')

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

cd "$CREW_WORKSPACE"
rc=0
timeout "$TIMEOUT_S" claude \
  -p "$(cat "$CREW_OUT/prompt.md")" \
  --append-system-prompt "$(cat "/roles/$ROLE/prompt.md")" \
  --output-format stream-json --verbose \
  --model "$MODEL" \
  --effort "$ANTHROPIC_EFFORT" \
  --max-turns "$MAX_TURNS" \
  --tools Bash,Edit,Read,Write \
  --allowedTools Bash,Edit,Read,Write \
  --setting-sources user \
  --strict-mcp-config \
  --settings "$settings" \
  > "$CREW_OUT/transcript.jsonl" 2> "$CREW_OUT/stderr.log" || rc=$?

printf '%s' "$rc" > "$CREW_OUT/exit_code"
exit "$rc"

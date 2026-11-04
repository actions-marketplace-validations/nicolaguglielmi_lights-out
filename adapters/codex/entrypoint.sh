#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# crew-entrypoint: runs inside the codex service (docs/adr/0041 §1).
# Installs the role's prompt as the global AGENTS.md, writes the hooks,
# then runs one headless `codex exec` against CREW_WORKSPACE, capturing
# the --json event stream and the exit code under CREW_OUT. Does not
# commit, push or build pr.json/run.json: that is adapters/codex/run.sh's
# job in workbench (docs/adr/0017 §1).
#
# Verified live on 0.166.0 (docs/adr/0041, "Verified"):
#  - -s danger-full-access: codex's own bubblewrap sandbox cannot start in
#    rootless podman, so the container is the sandbox (§3).
#  - --dangerously-bypass-hook-trust: hooks otherwise wait for a persisted
#    trust nobody can give headless; --enable hooks: found building M19, a
#    workspace's own .codex/config.toml with `[features] hooks = false`
#    switched the guard off; the command line wins over it.
#  - No hook can stop a run, and there is no --max-turns or token flag:
#    the PreModelRequest hook (hooks/budget.sh) kills the `timeout` below,
#    which forwards the TERM to codex, by the pid written here.
#  - The served model is in neither --json nor the rollout; the trace
#    target below puts response.completed on stderr. The trace stays in
#    this container's /tmp: only the served id and the non-trace lines
#    reach CREW_OUT.
#  - -c model_provider=openai always, so a workspace config cannot point
#    the key at another provider entry; MODEL_BASE_URL (the conformance
#    seam, docs/adr/0041 §7) replaces it with a provider of its own.
set -eu
: "${ROLE:?ROLE not set}"
: "${TICKET_FILE:?TICKET_FILE not set}"
: "${CREW_WORKSPACE:?CREW_WORKSPACE not set}"
: "${CREW_OUT:?CREW_OUT not set}"
: "${MAX_TURNS:?MAX_TURNS not set}"
: "${TIMEOUT_S:?TIMEOUT_S not set}"
: "${TOKEN_BUDGET:?TOKEN_BUDGET not set}"
: "${MODEL:?MODEL not set}"
: "${OPENAI_EFFORT:?OPENAI_EFFORT not set}"
export CREW_OUT TOKEN_BUDGET MAX_TURNS
export CODEX_HOME="$HOME/.codex"

mkdir -p "$CODEX_HOME" "$CREW_OUT"
cp "/roles/$ROLE/prompt.md" "$CODEX_HOME/AGENTS.md"

hooks=/opt/codex-hooks
jq -n --arg guard "$hooks/guard.sh" --arg budget "$hooks/budget.sh" '{
  hooks: {
    PreToolUse: [{matcher: "*", hooks: [{type: "command", command: $guard}]}],
    PreModelRequest: [{hooks: [{type: "command", command: $budget}]}]
  }
}' > "$CODEX_HOME/hooks.json"

if [ -n "${MODEL_BASE_URL:-}" ]; then
  set -- -c model_provider=conformance \
    -c model_providers.conformance.name=conformance \
    -c "model_providers.conformance.base_url=${MODEL_BASE_URL%/}/v1" \
    -c model_providers.conformance.env_key=CODEX_API_KEY \
    -c model_providers.conformance.wire_api=responses
else
  set -- -c model_provider=openai
fi

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
RUST_LOG=warn,codex_api::sse::responses=trace timeout "$TIMEOUT_S" codex exec --json \
  -m "$MODEL" \
  -s danger-full-access \
  --skip-git-repo-check \
  --dangerously-bypass-hook-trust \
  --enable hooks \
  -c "model_reasoning_effort=$OPENAI_EFFORT" \
  "$@" \
  "$(cat "$CREW_OUT/prompt.md")" \
  < /dev/null > "$CREW_OUT/transcript.jsonl" 2> /tmp/codex-stderr.log &
printf '%s\n' "$!" > /tmp/codex.pid
wait "$!" || rc=$?

# The served id, from the last response.completed the trace logged; every
# line that is not a trace line goes to CREW_OUT's stderr.log.
grep -o 'SSE event: {"type": *"response.completed".*' /tmp/codex-stderr.log 2>/dev/null \
  | sed 's/^SSE event: //' | jq -r '.response.model // empty' 2>/dev/null | tail -n 1 > "$CREW_OUT/served_model" || :
grep -v 'codex_api::sse::responses' /tmp/codex-stderr.log > "$CREW_OUT/stderr.log" 2>/dev/null || :

printf '%s' "$rc" > "$CREW_OUT/exit_code"
exit "$rc"

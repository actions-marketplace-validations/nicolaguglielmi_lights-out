#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# crew-entrypoint: runs inside the gemini-cli service (docs/adr/0017 §3).
# Installs the role's prompt as the global GEMINI.md, generates
# ~/.gemini/settings.json from the role's budgets, then runs one headless
# turn against CREW_WORKSPACE, capturing the transcript and exit code under
# CREW_OUT. Does not commit, does not push, does not build pr.json or
# run.json: everything after the run is workbench's job (adapters/
# gemini-cli/run.sh, docs/adr/0017 §1 — the adapter commits, not the
# model), because CREW_OUT is a bind mount and stays readable there once
# this container exits.
#
# --skip-trust: found live, not in any doc read before the first real run
# (docs/adr/0017 "Verify at L1"). The Trusted Folders page says the
# feature is "disabled by default", true for the interactive dialog, but
# headless mode enforces it unconditionally on a workspace it has never
# seen and refuses with exit 55 ("not running in a trusted directory")
# before making any model call — the fresh clone under WORKSPACE is
# exactly that, every run. --skip-trust is the documented headless
# escape hatch cited in the error message's own URL.
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
export CREW_OUT TOKEN_BUDGET

mkdir -p "$HOME/.gemini" "$CREW_OUT"
cp "/roles/$ROLE/prompt.md" "$HOME/.gemini/GEMINI.md"

# thinkingConfig.thinkingLevel is documented as an upper-case level name
# (docs/adr/0017 §3 verified facts); THINKING in role.env is lower case.
thinking_level=$(printf '%s' "$THINKING" | tr '[:lower:]' '[:upper:]')

# The per-role thinking level rides on a user alias named like the model,
# in the exact shape of the CLI's own built-in `gemini-3.5-flash` alias
# (packages/core/src/config/defaultModelConfigs.ts at v0.61.0-preview.0):
# `extends: chat-base-3` plus a concrete `modelConfig.model`. Found live
# by docs/adr/0018's eval run: the first draft wrote an abstract alias
# (no `model`) under `aliases`, which 0.59.0 never consulted because it
# remapped the request to gemini-3.5-flash before the alias lookup, and
# which 0.61.0-preview.0 refuses with "Could not resolve a model name for
# alias" — an alias with no model in its chain shadows the model name.

jq -n \
  --arg thinking "$thinking_level" \
  --argjson maxTurns "$MAX_TURNS" \
  '{
    security: {auth: {selectedType: "gemini-api-key"}},
    model: {name: "gemini-3.8-flash", maxSessionTurns: $maxTurns},
    modelConfigs: {customAliases: {"gemini-3.8-flash": {extends: "chat-base-3", modelConfig: {model: "gemini-3.8-flash", generateContentConfig: {thinkingConfig: {thinkingLevel: $thinking}}}}}},
    tools: {exclude: ["web_fetch", "google_web_search"]},
    hooks: {
      BeforeTool: [{matcher: "run_shell_command|write_file|replace|read_file", hooks: [{name: "guard", type: "command", command: "/opt/gemini-cli-hooks/guard.sh"}]}],
      BeforeModel: [{matcher: "*", hooks: [{name: "budget-before", type: "command", command: "/opt/gemini-cli-hooks/budget-before.sh"}]}],
      AfterModel: [{matcher: "*", hooks: [{name: "budget-after", type: "command", command: "/opt/gemini-cli-hooks/budget-after.sh"}]}]
    }
  }' > "$HOME/.gemini/settings.json"

{
  cat "$TICKET_FILE"
  printf '\n---\n\n'
  printf 'Work only inside this repository checkout. Do not run git push or\n'
  printf 'git commit yourself: committing and pushing are not your job, the\n'
  printf 'platform does that after you finish. When you are done, or when you\n'
  printf 'believe the ticket is resolved, your final message must be exactly\n'
  printf 'the pull request text: the first line is the PR title, a blank line,\n'
  printf 'then the PR body.\n'
} > "$CREW_OUT/prompt.md"

cd "$CREW_WORKSPACE"
rc=0
timeout "$TIMEOUT_S" gemini \
  -p "$(cat "$CREW_OUT/prompt.md")" \
  --approval-mode yolo \
  --skip-trust \
  --output-format stream-json \
  -m gemini-3.8-flash \
  > "$CREW_OUT/transcript.jsonl" 2> "$CREW_OUT/stderr.log" || rc=$?

printf '%s' "$rc" > "$CREW_OUT/exit_code"
exit "$rc"

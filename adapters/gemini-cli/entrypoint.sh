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
: "${MODEL:?MODEL not set}"
: "${GEMINI_THINKING_LEVEL:?GEMINI_THINKING_LEVEL not set}"
export CREW_OUT TOKEN_BUDGET

mkdir -p "$HOME/.gemini" "$CREW_OUT"
cp "/roles/$ROLE/prompt.md" "$HOME/.gemini/GEMINI.md"

# GEMINI_THINKING_LEVEL is the role's THINKING already mapped by run.sh
# from adapters/gemini-cli/thinking.env (docs/adr/0040 §2); MODEL is the
# profile's id (docs/adr/0040 §1, §4).
thinking_level=$GEMINI_THINKING_LEVEL

# The per-role thinking level rides on a user alias named like the model,
# in the exact shape of the CLI's own built-in `gemini-3.5-flash` alias
# (packages/core/src/config/defaultModelConfigs.ts at v0.61.0-preview.0):
# `extends: chat-base-3` plus a concrete `modelConfig.model`. Found live
# by docs/adr/0018's eval run: the first draft wrote an abstract alias
# (no `model`) under `aliases`, which 0.59.0 never consulted because it
# remapped the request to gemini-3.5-flash before the alias lookup, and
# which 0.61.0-preview.0 refuses with "Could not resolve a model name for
# alias" — an alias with no model in its chain shadows the model name.
#
# BeforeTool's matcher is "*", as claude-code's and codex's PreToolUse
# (docs/adr/0041 §3, amended 2026-11-04): every tool call reaches guard.sh
# and the guard decides. In 0.61.0-preview.0 a matcher is a JS RegExp on
# the tool name and "*" matches all before any regex
# (packages/core/src/hooks/hookPlanner.ts, matchesContext); the earlier
# list of four names let grep_search, glob, list_directory and every
# other tool through unguarded.

jq -n \
  --arg thinking "$thinking_level" \
  --arg model "$MODEL" \
  --argjson maxTurns "$MAX_TURNS" \
  '{
    security: {auth: {selectedType: "gemini-api-key"}},
    model: {name: $model, maxSessionTurns: $maxTurns},
    modelConfigs: {customAliases: {($model): {extends: "chat-base-3", modelConfig: {model: $model, generateContentConfig: {thinkingConfig: {thinkingLevel: $thinking}}}}}},
    tools: {exclude: ["web_fetch", "google_web_search"]},
    hooks: {
      BeforeTool: [{matcher: "*", hooks: [{name: "guard", type: "command", command: "/opt/gemini-cli-hooks/guard.sh"}]}],
      BeforeModel: [{matcher: "*", hooks: [{name: "budget-before", type: "command", command: "/opt/gemini-cli-hooks/budget-before.sh"}]}],
      AfterModel: [{matcher: "*", hooks: [{name: "budget-after", type: "command", command: "/opt/gemini-cli-hooks/budget-after.sh"}]}]
    }
  }' > "$HOME/.gemini/settings.json"

# The repository's MCP servers (docs/adr/0073 §8), only when run.sh found
# some and wrote this harness's translation (adapters/gemini-cli/mcp.sh)
# into CREW_MCP_DIR: mcpServers and mcp.allowed merged into the settings
# above (neither key is there before). A server that fails is silent on
# stderr at this pin; its real error goes only to GEMINI_DEBUG_LOG_FILE,
# kept in this container's /tmp, and only its `[MCP error]` lines reach
# CREW_OUT/mcp-errors.log below, which run.sh reads. CREW_MCP_ALLOW is the
# guard's list (§9), set here where the model cannot change it, empty
# without servers, so then every MCP call is denied.
CREW_MCP_ALLOW=""
if [ -n "${CREW_MCP_DIR:-}" ]; then
  jq -s '.[0] * .[1]' "$HOME/.gemini/settings.json" "$CREW_MCP_DIR/gemini-mcp.json" > "$HOME/.gemini/settings.json.new"
  mv "$HOME/.gemini/settings.json.new" "$HOME/.gemini/settings.json"
  CREW_MCP_ALLOW=$(awk '{ printf "%s%s", sep, $1; sep = " " }' "$CREW_MCP_DIR/allow")
  GEMINI_DEBUG_LOG_FILE=/tmp/gemini-debug.log
  export GEMINI_DEBUG_LOG_FILE
fi
export CREW_MCP_ALLOW

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
timeout "$TIMEOUT_S" gemini \
  -p "$(cat "$CREW_OUT/prompt.md")" \
  --approval-mode yolo \
  --skip-trust \
  --output-format stream-json \
  -m "$MODEL" \
  > "$CREW_OUT/transcript.jsonl" 2> "$CREW_OUT/stderr.log" || rc=$?

if [ -n "${CREW_MCP_DIR:-}" ]; then
  awk 'index($0, "[MCP error]")' /tmp/gemini-debug.log > "$CREW_OUT/mcp-errors.log" 2>/dev/null || :
fi

printf '%s' "$rc" > "$CREW_OUT/exit_code"
exit "$rc"

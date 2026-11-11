#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# harness-claude-code mcp: the repository's MCP servers for the dev-worker,
# translated for Claude Code 2.1.311 (docs/adr/0073 §8). Reads the
# normalised declaration core/agents.py wrote (decl.json) and writes into
# OUTDIR:
#   claude.json    the --mcp-config file, kept beside --strict-mcp-config:
#                  stdio {command, args, timeout}; remote {type: "http", url,
#                  headers: {Authorization: "Bearer ${MCP_X}"}, timeout}, the
#                  token by name only, expanded by the CLI from its own
#                  environment (MCP_* is not on its list of names read as
#                  empty toward a remote server, ADR 0073 "Verified").
#   allowed-tools  the comma list --allowedTools gains, mcp__<s>__<t>.
#   allow          one line per named tool, `<qualified> <server> <tool>`,
#                  for the entrypoint (CREW_MCP_ALLOW) and agents.py calls.
# No cwd key: Claude Code's stdio schema has none; the server starts from
# the CLI's own working directory, the workspace. An unnamed tool of a
# declared server stays visible to the model and is denied (its permission
# check in -p, then the guard): run.json says `visible-denied`.
# 30000 ms, start and each call: ADR 0073 §6 (start, the CLI's own default
# at the pin; each call, a decision far under its 2-minute background cut).
# Adapter convention (docs/adr/0012 §6): silent on success, one stderr line
# and exit 1 on failure.
#
#   sh adapters/claude-code/mcp.sh DECL_JSON OUTDIR WORKSPACE_IN_CONTAINER
set -eu
decl=${1:?usage: sh adapters/claude-code/mcp.sh DECL_JSON OUTDIR WORKSPACE_IN_CONTAINER}
outdir=${2:?usage: sh adapters/claude-code/mcp.sh DECL_JSON OUTDIR WORKSPACE_IN_CONTAINER}
: "${3:?usage: sh adapters/claude-code/mcp.sh DECL_JSON OUTDIR WORKSPACE_IN_CONTAINER}"

fail() { printf 'harness-claude-code: %s\n' "$1" >&2; exit 1; }

jq -e '(.servers | type) == "array" and (.servers | length) > 0
  and all(.servers[]; (.name | type) == "string" and (.tools | type) == "array"
    and ((.transport == "stdio" and (.command | type) == "array" and (.command | length) > 0)
      or (.transport == "http" and (.url | type) == "string" and (.token_env | type) == "string")))' \
  "$decl" >/dev/null 2>&1 || fail "$decl is not a declaration core/agents.py mcp wrote (docs/adr/0073 §7)"
mkdir -p "$outdir" || fail "cannot create $outdir"

# shellcheck disable=SC2016 # ${...} is Claude Code's own expansion, kept literal on purpose
jq '{mcpServers: (reduce .servers[] as $s ({}; .[$s.name] =
      (if $s.transport == "stdio"
       then {command: $s.command[0], args: $s.command[1:], timeout: 30000}
       else {type: "http", url: $s.url, headers: {Authorization: ("Bearer ${" + $s.token_env + "}")}, timeout: 30000}
       end)))}' "$decl" > "$outdir/claude.json" 2>/dev/null \
  || fail "could not write $outdir/claude.json"
jq -r '[.servers[] | .name as $s | .tools[] | "mcp__\($s)__\(.)"] | join(",")' "$decl" > "$outdir/allowed-tools" 2>/dev/null \
  || fail "could not write $outdir/allowed-tools"
jq -r '.servers[] | .name as $s | .tools[] | "mcp__\($s)__\(.) \($s) \(.)"' "$decl" > "$outdir/allow" 2>/dev/null \
  || fail "could not write $outdir/allow"

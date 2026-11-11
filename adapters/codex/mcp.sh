#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# harness-codex mcp: the repository's MCP servers for the dev-worker,
# translated for Codex 0.166.0 (docs/adr/0073 §8). Reads the normalised
# declaration core/agents.py wrote (decl.json) and writes into OUTDIR:
#   codex-args  one `-c` override per line, without the `-c` itself:
#               mcp_servers.<s>.command, args, cwd (stdio) or url,
#               bearer_token_env_var (remote, the token by name: a literal
#               bearer_token makes loading fail), then enabled_tools,
#               required, startup_timeout_sec, tool_timeout_sec.
#   allow       one line per named tool, `<qualified> <server> <tool>`,
#               the qualified name being Codex's hook name mcp__<s>__<t>
#               with every character outside [A-Za-z0-9_] turned into `_`.
# Each value is TOML, written as JSON: a JSON string or array of strings is
# a TOML basic string or array. enabled_tools matches the server's raw names
# and removes the other tools from what the model sees (`hidden`);
# required = true makes `codex exec` fail before thread.started when a
# server does not start, which run.sh turns into one line (ADR 0073 §8).
# 30 s, start and each call: ADR 0073 §6 (start, the CLI's own default at
# the pin; each call, a decision). Adapter convention (docs/adr/0012 §6):
# silent on success, one stderr line and exit 1 on failure.
#
#   sh adapters/codex/mcp.sh DECL_JSON OUTDIR WORKSPACE_IN_CONTAINER
set -eu
decl=${1:?usage: sh adapters/codex/mcp.sh DECL_JSON OUTDIR WORKSPACE_IN_CONTAINER}
outdir=${2:?usage: sh adapters/codex/mcp.sh DECL_JSON OUTDIR WORKSPACE_IN_CONTAINER}
workspace=${3:?usage: sh adapters/codex/mcp.sh DECL_JSON OUTDIR WORKSPACE_IN_CONTAINER}

fail() { printf 'harness-codex: %s\n' "$1" >&2; exit 1; }

jq -e '(.servers | type) == "array" and (.servers | length) > 0
  and all(.servers[]; (.name | type) == "string" and (.tools | type) == "array"
    and ((.transport == "stdio" and (.command | type) == "array" and (.command | length) > 0)
      or (.transport == "http" and (.url | type) == "string" and (.token_env | type) == "string")))' \
  "$decl" >/dev/null 2>&1 || fail "$decl is not a declaration core/agents.py mcp wrote (docs/adr/0073 §7)"
mkdir -p "$outdir" || fail "cannot create $outdir"

jq -r --arg ws "$workspace" '.servers[] | "mcp_servers.\(.name)" as $k
  | (if .transport == "stdio"
     then "\($k).command=\(.command[0] | tojson)", "\($k).args=\(.command[1:] | tojson)", "\($k).cwd=\($ws | tojson)"
     else "\($k).url=\(.url | tojson)", "\($k).bearer_token_env_var=\(.token_env | tojson)"
     end),
    "\($k).enabled_tools=\(.tools | tojson)",
    "\($k).required=true",
    "\($k).startup_timeout_sec=30",
    "\($k).tool_timeout_sec=30"' "$decl" > "$outdir/codex-args" 2>/dev/null \
  || fail "could not write $outdir/codex-args"
jq -r '.servers[] | .name as $s | .tools[] | "\("mcp__\($s)__\(.)" | gsub("[^A-Za-z0-9_]"; "_")) \($s) \(.)"' \
  "$decl" > "$outdir/allow" 2>/dev/null || fail "could not write $outdir/allow"

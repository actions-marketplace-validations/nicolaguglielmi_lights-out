#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# harness-gemini-cli mcp: the repository's MCP servers for the dev-worker,
# translated for Gemini CLI 0.61.0-preview.0 (docs/adr/0073 §8). Reads the
# normalised declaration core/agents.py wrote (decl.json) and writes into
# OUTDIR:
#   gemini-mcp.json  {mcpServers: {<s>: {command, args, cwd, timeout,
#                    includeTools}}, mcp: {allowed: [<s>...]}}, which the
#                    entrypoint merges into the settings.json it generates.
#   allow            one line per named tool, `<qualified> <server> <tool>`,
#                    the qualified name being the CLI's mcp_<s>_<t> (one
#                    underscore; ADR 0073 §6's name limits keep it within the
#                    CLI's 63 characters, so it is never cut).
# includeTools matches the server's raw names and removes the other tools
# from what the model sees (`hidden`). Two refusals, each one stderr line:
#   - a remote server: one that answers 401 is silent at this pin, so a
#     missing token would be a silently missing tool (ADR 0073 §8);
#   - a tool named like a built-in the entrypoint's tools.exclude hides
#     (web_fetch, google_web_search): the CLI hides an MCP tool of that
#     bare name too, so it would be offered nowhere.
# timeout 30000 ms covers start and each call alike in this CLI: ADR 0073
# §6. Adapter convention (docs/adr/0012 §6): silent on success, one stderr
# line and exit 1 on failure.
#
#   sh adapters/gemini-cli/mcp.sh DECL_JSON OUTDIR WORKSPACE_IN_CONTAINER
set -eu
decl=${1:?usage: sh adapters/gemini-cli/mcp.sh DECL_JSON OUTDIR WORKSPACE_IN_CONTAINER}
outdir=${2:?usage: sh adapters/gemini-cli/mcp.sh DECL_JSON OUTDIR WORKSPACE_IN_CONTAINER}
workspace=${3:?usage: sh adapters/gemini-cli/mcp.sh DECL_JSON OUTDIR WORKSPACE_IN_CONTAINER}

fail() { printf 'harness-gemini-cli: %s\n' "$1" >&2; exit 1; }

jq -e '(.servers | type) == "array" and (.servers | length) > 0
  and all(.servers[]; (.name | type) == "string" and (.tools | type) == "array"
    and ((.transport == "stdio" and (.command | type) == "array" and (.command | length) > 0)
      or (.transport == "http" and (.url | type) == "string" and (.token_env | type) == "string")))' \
  "$decl" >/dev/null 2>&1 || fail "$decl is not a declaration core/agents.py mcp wrote (docs/adr/0073 §7)"

remote=$(jq -r '[.servers[] | select(.transport != "stdio") | .name] | first // empty' "$decl")
[ -z "$remote" ] || fail "mcp.json server $remote is remote, and gemini-cli takes stdio servers only: a remote server that fails is silent at this pin (ADR 0073 §8)"
hidden=$(jq -r '[.servers[] | .name as $s | .tools[] | select(. == "web_fetch" or . == "google_web_search") | "\($s) names tool \(.)"] | first // empty' "$decl")
[ -z "$hidden" ] || fail "mcp.json server $hidden, a name gemini-cli hides as an excluded built-in (tools.exclude), so it would be offered nowhere (ADR 0073 §8)"

mkdir -p "$outdir" || fail "cannot create $outdir"
jq --arg ws "$workspace" '{
    mcpServers: (reduce .servers[] as $s ({}; .[$s.name] =
      {command: $s.command[0], args: $s.command[1:], cwd: $ws, timeout: 30000, includeTools: $s.tools})),
    mcp: {allowed: [.servers[].name]}
  }' "$decl" > "$outdir/gemini-mcp.json" 2>/dev/null || fail "could not write $outdir/gemini-mcp.json"
jq -r '.servers[] | .name as $s | .tools[] | "mcp_\($s)_\(.) \($s) \(.)"' "$decl" > "$outdir/allow" 2>/dev/null \
  || fail "could not write $outdir/allow"

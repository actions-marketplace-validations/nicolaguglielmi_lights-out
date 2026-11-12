#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-hooks: proves the guard of every CLI harness (docs/adr/0017 §9, 0041 §11)
# both allows and denies, on a fixed set of committed cases -- no model
# needed, no git range needed (unlike gates/*.sh's require_range, this judges
# fixed stdin cases, not a git range, so it runs cold the same way
# ci/contract.sh does). Cases live in ci/hooks-cases/<name>.json with a
# sibling ci/hooks-cases/<name>.expect containing exactly "allow" or "deny"
# (the .json/.expect extensions, not .sh, keep ci/contract.sh's *.sh glob
# from picking these up as gates of their own).
#
# A case file is written once, in Gemini CLI's input shape (tool_name
# run_shell_command, read_file, write_file, or another built-in from gemini-cli
# 0.61.0-preview.0's ALL_BUILTIN_TOOL_NAMES: grep_search, glob, list_directory,
# read_many_files, invoke_agent; the paths and strings in tool_input). Each is
# rendered, here, in the shape each CLI hands its hook (docs/adr/0041 §3,
# verified 2026-11-04): Gemini's BeforeTool as written; Claude Code's
# PreToolUse with Bash, Read and Write; Codex's PreToolUse, which has the one
# tool name Bash, so a read is `cat <path>` and a write is `printf <content> >
# <path>`. Claude Code (--tools Bash,Edit,Read,Write) and Codex (a shell) have
# none of the other built-ins, so both get the equivalent through Bash:
# grep_search -> `grep -rn`, glob -> `find -path`, list_directory -> `ls`,
# read_many_files -> `cat`, invoke_agent -> `echo <prompt>` (a subagent prompt
# is only text the guard scans; echo carries that text and does not pretend to
# run an agent). Every rendering also carries what each CLI adds
# to every call and the guard must not mistake for the model's own: a
# transcript_path and a cwd, the former inside the vendor's own directory
# (.gemini/, .claude/, .codex/), which the deny-list names. The guard is one
# file copied into each adapter (docs/adr/0041 §11, ci/harness-shape.sh
# checks it byte for byte); any copy that differs from one already judged is
# judged again, and an identical copy is the same program.
#
# The matcher rule (docs/adr/0041 §3 as amended) is checked here too, with no
# engine: every CLI harness registers its guard on the pre-tool event with
# matcher "*" in adapters/<h>/entrypoint.sh and the guard decides; a narrower
# matcher lets every tool it omits (grep_search, glob, ...) skip the guard.
#
# Beyond the exit code, the guard must leave exactly one hooks.log line per
# call, ALLOW or DENY to match, naming the tool the CLI sent (docs/adr/0017
# §9): it is the evidence that the hook fired in a recorded run.
#
# Antigravity CLI (docs/adr/0050 §3) cannot run the guard directly: its
# PreToolUse hook gets {toolCall: {name, args}} and denies only by printing
# {"decision": "deny"} on stdout. Its adapter ships a shim,
# hooks/agy-guard.sh, that hands the call to the same guard.sh. So a harness
# with that shim also has every case rendered in agy's shape (run_command
# with CommandLine, read_file and write_file with Path and Content, the other
# built-ins as a shell command through run_command, as for codex) and run
# through the shim, which must print a deny exactly when the case expects
# one. And the shim's own rule: a tool it does not offer (search_web,
# invoke_subagent) is denied by name, without reaching the guard.
#
# MCP calls (docs/adr/0073 §9) are cases of their own, written below rather
# than in ci/hooks-cases/ because each needs its CREW_MCP_ALLOW: an allowed
# qualified name passes in each vendor's naming, an unlisted one and any
# `mcp_` name under an empty list are denied, and so is an MCP_* token name,
# in a call's arguments or through the shell tool.
set -eu
name=hooks
. ci/lib.sh

cases_dir=ci/hooks-cases
[ -d "$cases_dir" ] || nogo "$cases_dir not found"

# The guards: one per CLI harness, discovered the way ci/harness-shape.sh does.
distinct=""
shims=""
for d in adapters/*/; do
  h=$(basename "$d")
  [ -f "adapters/$h/run.sh" ] && [ -f "adapters/$h/Containerfile" ] || continue
  [ -f "adapters/$h/package.json" ] || [ -f "adapters/$h/package-lock.json" ] || [ -f "adapters/$h/release.env" ] || continue
  guard=adapters/$h/hooks/guard.sh
  [ -f "$guard" ] || nogo "$guard not found: adapters/$h is a CLI harness and needs its guard (docs/adr/0041 §11)"
  # The guard is registered with matcher "*": check each entrypoint line that
  # names it (gemini: the guard.sh path; claude-code, codex: $guard).
  ep=adapters/$h/entrypoint.sh
  [ -f "$ep" ] || nogo "$ep not found: adapters/$h is a CLI harness and needs its entrypoint"
  # shellcheck disable=SC2016 # a literal $guard to match, not to expand
  reg=$(grep -E 'matcher:.*(command: \$guard|guard\.sh)' "$ep" || true)
  [ -n "$reg" ] || nogo "$h: $ep registers no guard hook with a matcher (docs/adr/0041 §3)"
  matchers=$(printf '%s\n' "$reg" | sed -n 's/.*matcher: *"\([^"]*\)".*/\1/p')
  [ "$matchers" = '*' ] || nogo "$h: guard registered with matcher '$matchers', want '*' (docs/adr/0041 §3)"
  same=no
  for g in $distinct; do
    cmp -s "$g" "$guard" && same=yes
  done
  [ "$same" = yes ] || distinct="$distinct $guard"
  [ ! -f "adapters/$h/hooks/agy-guard.sh" ] || shims="$shims adapters/$h/hooks/agy-guard.sh"
done
[ -n "$distinct" ] || nogo "no CLI harness with a guard under adapters/"

# The shell command a case stands for, for the shapes whose tool is a shell:
# the forms the header comment lists. $c is the whole case, $i its tool_input.
# shellcheck disable=SC2016 # a jq program; its $c and $i are jq's
shell_form='def shell_form($c; $i):
  if $c.tool_name == "run_shell_command" then $i.command
  elif $c.tool_name == "grep_search" then "grep -rn " + ($i.pattern | @sh) + " " + ($i.dir_path // ".")
       + (if $i.include_pattern then " --include=" + ($i.include_pattern | @sh) else "" end)
  elif $c.tool_name == "glob" then "find " + ($i.dir_path // ".") + " -path " + ($i.pattern | @sh)
  elif $c.tool_name == "list_directory" then "ls " + $i.dir_path
  elif $c.tool_name == "read_many_files" then "cat " + ($i.include | join(" "))
  elif $c.tool_name == "invoke_agent" then "echo " + ($i.prompt | @sh)
  elif $c.tool_name == "read_file" then "cat " + $i.file_path
  elif $c.tool_name == "write_file" then "printf %s " + ($i.content | @sh) + " > " + $i.file_path
  else error("no shell form for " + $c.tool_name) end;'

# render SHAPE FILE: the case in the shape that CLI hands its hook, one line.
render() {
  case "$1" in
    gemini)
      jq -c '{session_id: "s", cwd: "/crew/0001/workspace", hook_event_name: "BeforeTool",
              transcript_path: "/tmp/crew-home/.gemini/tmp/s/chat.json"} + .' "$2" ;;
    claude)
      jq -c "$shell_form"'. as $c | .tool_input as $i
             | {session_id: "s", cwd: "/crew/0001/workspace", hook_event_name: "PreToolUse",
                transcript_path: "/tmp/crew-home/.claude/projects/-crew/s.jsonl",
                permission_mode: "acceptEdits", tool_use_id: "toolu_1"}
             + (({run_shell_command: "Bash", read_file: "Read", write_file: "Write"}[$c.tool_name]) as $t
                | if $t then {tool_name: $t, tool_input: $i}
                  else {tool_name: "Bash", tool_input: {command: shell_form($c; $i)}} end)' "$2" ;;
    codex)
      jq -c "$shell_form"'. as $c | .tool_input as $i
             | {session_id: "s", turn_id: "t1", cwd: "/crew/0001/workspace", hook_event_name: "PreToolUse",
                transcript_path: "/tmp/crew-home/.codex/sessions/rollout-s.jsonl",
                model: "m", permission_mode: "bypassPermissions", tool_use_id: "call_1", tool_name: "Bash",
                tool_input: {command: shell_form($c; $i)}}' "$2" ;;
    agy)
      jq -c "$shell_form"'. as $c | .tool_input as $i
             | {conversationId: "c", stepIdx: 2, modelName: "m-medium", lastUserInput: "u",
                artifactDirectoryPath: "/tmp/crew-home/.gemini/antigravity-cli/brain/c",
                transcriptPath: "/tmp/crew-home/.gemini/antigravity-cli/brain/c/.system_generated/logs/transcript_full.jsonl",
                workspacePaths: ["/crew/0001/workspace"]}
             + {toolCall: (
                 if $c.tool_name == "read_file" then {name: "read_file", args: {Path: $i.file_path}}
                 elif $c.tool_name == "write_file" then {name: "write_file", args: {Path: $i.file_path, Content: $i.content}}
                 else {name: "run_command", args: {CommandLine: (if $c.tool_name == "run_shell_command" then $i.command else shell_form($c; $i) end),
                                                   toolSummary: "s", WaitMsBeforeAsync: 10000}} end)}' "$2" ;;
  esac
}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

total=0
bad=0
first=""
for guard in $distinct; do
  for shape in gemini claude codex; do
    for expect_file in "$cases_dir"/*.expect; do
      [ -e "$expect_file" ] || continue
      case_name=$(basename "$expect_file" .expect)
      json_file="$cases_dir/$case_name.json"
      [ -f "$json_file" ] || nogo "case $case_name has no .json"
      want=$(cat "$expect_file")
      case "$want" in
        allow|deny) ;;
        *) nogo "case $case_name: .expect must be allow or deny, got $want" ;;
      esac

      total=$((total + 1))
      render "$shape" "$json_file" > "$work/input.json" 2> "$work/render.err" \
        || nogo "case $case_name cannot be rendered as $shape" "$(cat "$work/render.err")"
      tool=$(jq -r '.tool_name' "$work/input.json")
      rm -f "$work/hooks.log"
      rc=0
      CREW_OUT="$work" sh "$guard" < "$work/input.json" > /dev/null 2> "$work/stderr.log" || rc=$?

      got=""
      case "$rc" in
        0) got=allow ;;
        2) got=deny ;;
        *) got="exit($rc)" ;;
      esac

      problem=""
      if [ "$got" != "$want" ]; then
        problem="want $want, got $got"
      else
        # One log line, ALLOW or DENY to match, for the tool the CLI sent.
        verdict=ALLOW
        [ "$want" = deny ] && verdict=DENY
        lines=0
        [ -f "$work/hooks.log" ] && lines=$(awk 'END{print NR}' "$work/hooks.log")
        if [ "$lines" -ne 1 ]; then
          problem="hooks.log has $lines lines, want 1"
        elif ! grep -Eq "^$verdict [^ ]+ ." "$work/hooks.log" || [ "$(cut -d' ' -f2 "$work/hooks.log")" != "$tool" ]; then
          problem="hooks.log says '$(cat "$work/hooks.log")', want $verdict for $tool"
        fi
      fi

      if [ -n "$problem" ]; then
        bad=$((bad + 1))
        [ -n "$first" ] || first="$case_name as $shape ($problem)"
        printf 'ci-hooks: %s: %s as %s: %s\n' "$guard" "$case_name" "$shape" "$problem" >&2
        cat "$work/stderr.log" >&2
      fi
    done
  done
done

# agy's shim, every case in agy's shape: a deny is the JSON on stdout, exit 0.
for shim in $shims; do
  for expect_file in "$cases_dir"/*.expect; do
    [ -e "$expect_file" ] || continue
    case_name=$(basename "$expect_file" .expect)
    want=$(cat "$expect_file")
    total=$((total + 1))
    render agy "$cases_dir/$case_name.json" > "$work/input.json" 2> "$work/render.err" \
      || nogo "case $case_name cannot be rendered as agy" "$(cat "$work/render.err")"
    tool=$(jq -r '.toolCall.name' "$work/input.json")
    rm -f "$work/hooks.log"
    rc=0
    CREW_OUT="$work" sh "$shim" < "$work/input.json" > "$work/stdout.log" 2> "$work/stderr.log" || rc=$?
    got="exit($rc)"
    if [ "$rc" -eq 0 ]; then
      if [ ! -s "$work/stdout.log" ]; then
        got=allow
      elif jq -e '.decision == "deny" and (.reason | type) == "string"' "$work/stdout.log" >/dev/null 2>&1; then
        got=deny
      else
        got="stdout '$(head -c 200 "$work/stdout.log")'"
      fi
    fi
    problem=""
    if [ "$got" != "$want" ]; then
      problem="want $want, got $got"
    else
      verdict=ALLOW
      [ "$want" = deny ] && verdict=DENY
      lines=0
      [ -f "$work/hooks.log" ] && lines=$(awk 'END{print NR}' "$work/hooks.log")
      if [ "$lines" -ne 1 ]; then
        problem="hooks.log has $lines lines, want 1"
      elif ! grep -Eq "^$verdict [^ ]+ ." "$work/hooks.log" || [ "$(cut -d' ' -f2 "$work/hooks.log")" != "$tool" ]; then
        problem="hooks.log says '$(cat "$work/hooks.log")', want $verdict for $tool"
      fi
    fi
    if [ -n "$problem" ]; then
      bad=$((bad + 1))
      [ -n "$first" ] || first="$case_name as agy ($problem)"
      printf 'ci-hooks: %s: %s as agy: %s\n' "$shim" "$case_name" "$problem" >&2
      cat "$work/stderr.log" >&2
    fi
  done
  for t in search_web invoke_subagent; do
    total=$((total + 1))
    rm -f "$work/hooks.log"
    out=$(jq -nc --arg t "$t" '{toolCall: {name: $t, args: {query: "readme", Prompt: "list the files"}}}' \
      | CREW_OUT="$work" sh "$shim" 2>/dev/null) || out=""
    if ! printf '%s' "$out" | jq -e '.decision == "deny"' >/dev/null 2>&1 \
       || [ "$(cat "$work/hooks.log" 2>/dev/null)" != "DENY $t not-offered" ]; then
      bad=$((bad + 1))
      [ -n "$first" ] || first="$t as agy (not denied by name: '$out', hooks.log '$(cat "$work/hooks.log" 2>/dev/null)')"
      printf 'ci-hooks: %s: %s is not denied as a tool the harness does not offer\n' "$shim" "$t" >&2
    fi
  done
done

# --- MCP calls (docs/adr/0073 §9): the guard denies a tool_name that
# starts with `mcp_` and is not a word of CREW_MCP_ALLOW (empty when
# nothing is declared), and denies `MCP_[A-Z0-9_]+` anywhere in a call.
# Each case is rendered in each vendor's naming (ADR 0073 "Verified"):
# claude-code and codex hand the hook mcp__<server>__<tool>, gemini-cli
# mcp_<server>_<tool>, and tool_input is the call's arguments. The allow
# list is what the entrypoint exports: notes/search_notes and
# docs/search_docs in that vendor's naming. A `shell` case is a command
# through the shell tool, rendered as the cases above are.
# label|kind|server|tool or command|arguments|list|want
# shellcheck disable=SC2016 # a literal $MCP_DOCS_TOKEN, for the guard to see
mcp_cases='allowed|mcp|notes|search_notes|{"q":"venue rules"}|listed|allow
allowed-second-word|mcp|docs|search_docs|{"query":"deploy steps"}|listed|allow
built-in-with-an-empty-list|shell|-|ls -la app/backend/meetups|-|empty|allow
unlisted|mcp|notes|count_notes|{}|listed|deny
prefix-of-an-allowed-name|mcp|notes|search|{"q":"venue rules"}|listed|deny
unlisted-server|mcp|wiki|search_notes|{"q":"venue rules"}|listed|deny
empty-list|mcp|notes|search_notes|{"q":"venue rules"}|empty|deny
token-name-in-arguments|mcp|notes|search_notes|{"q":"MCP_DOCS_TOKEN"}|listed|deny
echo-token|shell|-|echo $MCP_DOCS_TOKEN|-|listed|deny'

# mcp_name SHAPE SERVER TOOL: the qualified name that CLI gives the hook.
mcp_name() {
  case "$1" in
    gemini) printf 'mcp_%s_%s' "$2" "$3" ;;
    *) printf 'mcp__%s__%s' "$2" "$3" ;;
  esac
}

# mcp_render SHAPE SERVER TOOL ARGS: the MCP call in that CLI's hook shape.
# shellcheck disable=SC2016 # jq programs; their $names are jq's
mcp_render() {
  t=$(mcp_name "$1" "$2" "$3")
  case "$1" in
    gemini)
      jq -nc --arg t "$t" --arg s "$2" --arg o "$3" --argjson a "$4" \
        '{session_id: "s", cwd: "/crew/0001/workspace", hook_event_name: "BeforeTool",
          transcript_path: "/tmp/crew-home/.gemini/tmp/s/chat.json",
          tool_name: $t, tool_input: $a, mcp_context: {server_name: $s, tool_name: $o}}' ;;
    claude)
      jq -nc --arg t "$t" --argjson a "$4" \
        '{session_id: "s", cwd: "/crew/0001/workspace", hook_event_name: "PreToolUse",
          transcript_path: "/tmp/crew-home/.claude/projects/-crew/s.jsonl",
          permission_mode: "acceptEdits", tool_use_id: "toolu_1", tool_name: $t, tool_input: $a}' ;;
    codex)
      jq -nc --arg t "$t" --argjson a "$4" \
        '{session_id: "s", turn_id: "t1", cwd: "/crew/0001/workspace", hook_event_name: "PreToolUse",
          transcript_path: "/tmp/crew-home/.codex/sessions/rollout-s.jsonl",
          model: "m", permission_mode: "bypassPermissions", tool_use_id: "call_1",
          tool_name: $t, tool_input: $a}' ;;
  esac
}

# run_mcp_cases GUARD: every MCP case in every shape through GUARD; sets
# mcp_total, mcp_bad and mcp_first (the first disagreement).
run_mcp_cases() {
  mcp_total=0
  mcp_bad=0
  mcp_first=""
  for shape in gemini claude codex; do
    while IFS='|' read -r label kind server tool args list want; do
      [ -n "$label" ] || continue
      if [ "$kind" = shell ]; then
        jq -nc --arg c "$tool" '{tool_name: "run_shell_command", tool_input: {command: $c}}' > "$work/mcp-case.json"
        render "$shape" "$work/mcp-case.json" > "$work/input.json"
      else
        mcp_render "$shape" "$server" "$tool" "$args" > "$work/input.json"
      fi
      sent=$(jq -r '.tool_name' "$work/input.json")
      allow=""
      [ "$list" != listed ] || allow="$(mcp_name "$shape" notes search_notes) $(mcp_name "$shape" docs search_docs)"
      mcp_total=$((mcp_total + 1))
      rm -f "$work/hooks.log"
      rc=0
      CREW_OUT="$work" CREW_MCP_ALLOW="$allow" sh "$1" < "$work/input.json" > /dev/null 2> "$work/stderr.log" || rc=$?
      case "$rc" in
        0) got=allow ;;
        2) got=deny ;;
        *) got="exit($rc)" ;;
      esac
      problem=""
      if [ "$got" != "$want" ]; then
        problem="want $want, got $got"
      else
        verdict=ALLOW
        [ "$want" = deny ] && verdict=DENY
        lines=0
        [ -f "$work/hooks.log" ] && lines=$(awk 'END{print NR}' "$work/hooks.log")
        if [ "$lines" -ne 1 ]; then
          problem="hooks.log has $lines lines, want 1"
        elif [ "$(awk '{print $1}' "$work/hooks.log")" != "$verdict" ] \
          || [ "$(awk '{print $2}' "$work/hooks.log")" != "$sent" ]; then
          problem="hooks.log says '$(cat "$work/hooks.log")', want $verdict for $sent"
        fi
      fi
      if [ -n "$problem" ]; then
        mcp_bad=$((mcp_bad + 1))
        [ -n "$mcp_first" ] || mcp_first="mcp case $label as $shape ($problem)"
        printf 'ci-hooks: %s: mcp case %s as %s: %s\n' "$1" "$label" "$shape" "$problem" >&2
        cat "$work/stderr.log" >&2
      fi
    done <<CASES
$mcp_cases
CASES
  done
}

# The MCP cases are proven first on a planted guard that allows every call
# and logs it: the first deny case must be named.
cat > "$work/planted-guard.sh" <<'PLANTED'
t=$(jq -r '.tool_name')
printf 'ALLOW %s -\n' "$t" >> "$CREW_OUT/hooks.log"
PLANTED
run_mcp_cases "$work/planted-guard.sh" 2> /dev/null
case "$mcp_first" in
  "mcp case unlisted as gemini "*) ;;
  *) nogo "self-check: a planted guard that allows every MCP call was judged '${mcp_first:-in agreement}', want the case unlisted as gemini named" ;;
esac

for guard in $distinct; do
  run_mcp_cases "$guard"
  total=$((total + mcp_total))
  bad=$((bad + mcp_bad))
  [ -n "$first" ] || first=$mcp_first
done

[ "$bad" -eq 0 ] || nogo "$bad of $total guard runs disagree with their case; first: $first"

go

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
set -eu
name=hooks
. ci/lib.sh

cases_dir=ci/hooks-cases
[ -d "$cases_dir" ] || nogo "$cases_dir not found"

# The guards: one per CLI harness, discovered the way ci/harness-shape.sh does.
distinct=""
for d in adapters/*/; do
  h=$(basename "$d")
  [ -f "adapters/$h/run.sh" ] && [ -f "adapters/$h/Containerfile" ] || continue
  [ -f "adapters/$h/package.json" ] || [ -f "adapters/$h/package-lock.json" ] || continue
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

[ "$bad" -eq 0 ] || nogo "$bad of $total guard runs disagree with their case; first: $first"

go

#!/bin/sh
# The plugin's PreToolUse hook on Bash (docs/adr/0069 §4), the recipe of
# docs/use-on-your-repo.md: nothing unless the tool input holds `git
# commit`; nothing in a repository whose HEAD has no .lights-out/workload.env
# (a user-scope plugin must not judge every repository); else the light
# gates on the staged changes, and on a NO-GO exit 2, the deny Claude Code
# reads, with exactly one line on stderr: the gates' line. A judge asked
# for and absent denies too.
set -u
here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
input=$(cat)
case $input in
  *"git commit"*) ;;
  *) exit 0 ;;
esac
git cat-file -e HEAD:.lights-out/workload.env 2>/dev/null || exit 0
out=$(sh "$here/run.sh" --light STAGED=1 2>/dev/null </dev/null) && exit 0
line=$(printf '%s\n' "$out" | awk 'NF { last = $0 } END { print last }')
[ -n "$line" ] || line="NO-GO: lights-out — lights-out-gates printed no line; run lights-out-gates --light STAGED=1 for its details"
printf '%s\n' "$line" >&2
exit 2

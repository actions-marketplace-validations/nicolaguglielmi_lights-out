#!/bin/sh
# The two skills' command (docs/adr/0069 §2): exactly one line on stdout,
# exit 0 whatever the verdict, so a NO-GO reaches the model (a non-zero
# exit aborts the skill). `gates [KEY=VALUE ...]` is the light tier,
# STAGED=1 when no key is given; `spec <file>` is the spec gate.
set -u
here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
cmd=${1:-}
[ $# -eq 0 ] || shift
case $cmd in
  gates) [ $# -gt 0 ] || set -- STAGED=1
         set -- --light "$@" ;;
  spec)  set -- spec "$@" ;;
  *)     printf 'NO-GO: lights-out — the plugin knows gates and spec, not "%s"\n' "$cmd"
         exit 0 ;;
esac
out=$(sh "$here/run.sh" "$@" 2>/dev/null </dev/null)
line=$(printf '%s\n' "$out" | awk 'NF { last = $0 } END { print last }')
[ -n "$line" ] || line="NO-GO: lights-out — lights-out-gates printed no line; run lights-out-gates $* in a shell for its details"
printf '%s\n' "$line"
exit 0

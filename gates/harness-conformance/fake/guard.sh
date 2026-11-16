#!/bin/sh
# fake-cli's guard: enough of a deny-list for the suite's probes, in the real
# guard's output contract (exit 2 and a reason on stderr; a hooks.log line per
# call, `ALLOW <tool> -` or `DENY <tool> <label>`), and forking nothing, because
# the hook runs before every tool of every case. It is not the real guard,
# which ci/hooks.sh judges; this proof must not wait on it.
input=$(cat)
tool=${input#*\"tool_name\":\"}
tool=${tool%%\"*}
log=${CREW_OUT:-.}/hooks.log
deny() {
  printf 'DENY %s %s\n' "$tool" "$1" >> "$log"
  printf 'denied: matched %s\n' "$1" >&2
  exit 2
}
# docs/adr/0073 §9: an MCP tool the repository's mcp.json does not name is denied
# (`mcp-guard-open` lets every one through).
case $tool in
  mcp_*)
    case " ${CREW_MCP_ALLOW:-} " in
      *" $tool "*) ;;
      *) [ "${FAKE_DEFECT:-}" = mcp-guard-open ] || deny "mcp tool not named by mcp.json" ;;
    esac ;;
esac
case $input in
  *git*push*) deny "git push" ;;
  *.env*) deny ".env" ;;
  *id_ed25519*) deny "id_ed25519" ;;
  *.key*) deny ".key" ;;
  *printenv*) deny "printenv" ;;
esac
printf 'ALLOW %s -\n' "$tool" >> "$log"
exit 0

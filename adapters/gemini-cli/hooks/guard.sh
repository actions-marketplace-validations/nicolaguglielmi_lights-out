#!/bin/sh
# Gemini CLI BeforeTool hook (ADR 0017 §9, verified 2026-09-15 against
# Gemini CLI v0.59.0 docs): reads one JSON object on stdin shaped like
# {"session_id":..., "cwd":..., "hook_event_name":"BeforeTool",
# "tool_name":"...", "tool_input": {...}}. Deny: exit 2, reason on stderr.
# Allow: exit 0, nothing on stdout. Does not care about tool_input's
# specific key names -- every string value anywhere in the JSON is joined
# (jq '[.. | strings] | join("\n")') and tested against the deny-list below.
#
# Vendor format, so it lives in the adapter, not in roles/. Every call,
# allowed or denied, appends one line to $CREW_OUT/hooks.log (default ".",
# so a standalone test run degrades gracefully) -- the evidence hooks fired
# in a recorded run.
set -eu

crew_out=${CREW_OUT:-.}
log="$crew_out/hooks.log"

input=$(cat)

# tool_name for the log line; "unknown" if the JSON is malformed or the
# field is absent -- the log line still gets written either way.
tool_name=$(printf '%s' "$input" | jq -r '.tool_name // "unknown"' 2>/dev/null) || tool_name=unknown

record() {
  # record VERDICT REASON: one line to $CREW_OUT/hooks.log. Never fails the
  # hook itself -- a log directory that cannot be created must not turn an
  # ALLOW into a crash, and must not hide a DENY either.
  printf '%s %s %s\n' "$1" "$tool_name" "$2" >> "$log" 2>/dev/null || true
}

joined=$(printf '%s' "$input" | jq -r '[.. | strings] | join("\n")' 2>/dev/null) || joined=""

if [ -z "$input" ] || ! printf '%s' "$input" | jq -e . >/dev/null 2>&1; then
  reason="malformed or empty JSON on stdin"
  record DENY "no-match:$reason"
  printf '%s\n' "$reason" >&2
  exit 2
fi

# rm -rf (any order/casing of the two flags, split or combined) combined
# with a dangerous target on the same string: /, ~, .., a bare *, or a
# shell variable ($). Checked separately from the flat deny-list below
# because "combined with" is a two-part condition on the same string, not
# a single substring.
rm_flag_re='rm[[:space:]]+-[a-zA-Z]*[rR][a-zA-Z]*[fF][a-zA-Z]*|rm[[:space:]]+-[a-zA-Z]*[fF][a-zA-Z]*[rR][a-zA-Z]*|rm[[:space:]]+-[rRfF][[:space:]]+-[rRfF]'
rm_target_re='/|~|\.\.|(^|[[:space:]])\*([[:space:]]|$)|\$'
rm_lines=$(printf '%s\n' "$joined" | grep -E -- "$rm_flag_re" 2>/dev/null) || rm_lines=""
if [ -n "$rm_lines" ] && printf '%s\n' "$rm_lines" | grep -Eq -- "$rm_target_re"; then
  reason="rm -rf combined with /, ~, .., a bare *, or \$"
  record DENY "rm -rf"
  printf '%s\n' "$reason" >&2
  exit 2
fi

# label|ERE, one per line. A word-boundary class ([^A-Za-z0-9_.-] or
# start/end of string) around bare command names keeps "dockerfile" from
# tripping "docker", while a plain substring is enough for the rest (the
# spec calls these "substring/regex match anywhere in the collected
# strings" -- no boundary is claimed beyond what is written here).
patterns='
git push|git[[:space:]]+push
git reset --hard|git[[:space:]]+reset[[:space:]]+--hard
git clean -f|git[[:space:]]+clean[[:space:]]+-f
--no-preserve-root|--no-preserve-root
sudo|(^|[^A-Za-z0-9_.-])sudo([^A-Za-z0-9_.-]|$)
chmod -R 777|chmod[[:space:]]+-R[[:space:]]+777
docker-compose|(^|[^A-Za-z0-9_.-])docker-compose([^A-Za-z0-9_.-]|$)
docker|(^|[^A-Za-z0-9_.-])docker([^A-Za-z0-9_.-]|$)
podman|(^|[^A-Za-z0-9_.-])podman([^A-Za-z0-9_.-]|$)
curl|(^|[^A-Za-z0-9_.-])curl([^A-Za-z0-9_.-]|$)
wget|(^|[^A-Za-z0-9_.-])wget([^A-Za-z0-9_.-]|$)
ssh|(^|[^A-Za-z0-9_.-])ssh([^A-Za-z0-9_.-]|$)
scp|(^|[^A-Za-z0-9_.-])scp([^A-Za-z0-9_.-]|$)
nc|(^|[^A-Za-z0-9_.-])nc([^A-Za-z0-9_.-]|$)
.env|\.env
.pem|\.pem
id_rsa|id_rsa
id_ed25519|id_ed25519
.git-credentials|\.git-credentials
.gemini/|\.gemini/
/run/secrets|/run/secrets
GEMINI_API_KEY|GEMINI_API_KEY
printenv|(^|[^A-Za-z0-9_.-])printenv([^A-Za-z0-9_.-]|$)
env|(^|[^A-Za-z0-9_.-])env([^A-Za-z0-9_.-]|$)
os.environ|os\.environ
process.env|process\.env
'

old_ifs=$IFS
IFS='
'
matched_label=""
for entry in $patterns; do
  [ -n "$entry" ] || continue
  label=${entry%%|*}
  regex=${entry#*|}
  if printf '%s\n' "$joined" | grep -Eq -- "$regex" 2>/dev/null; then
    matched_label=$label
    break
  fi
done
IFS=$old_ifs

if [ -n "$matched_label" ]; then
  record DENY "$matched_label"
  printf 'denied: matched %s\n' "$matched_label" >&2
  exit 2
fi

record ALLOW -
exit 0

#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-promote: proves core/promote.sh, go-for-launch (docs/adr/0020 §4,
# §8), against a stub release role and a stub delivery adapter, cold: no
# plane, no real model. The ci/tower.sh shape: a throwaway root
# symlinking core/ and ci/, a roles/release/role.env pointing HARNESS at
# a stub harness whose run.sh answers with whatever $root/world/calls.json
# the case set (so the case controls what "the release role answered"),
# and adapters/stub-delivery/{shift.sh,rollback.sh} logging their own
# call instead of touching Envoy. Written from docs/adr/0020 §4, §8, not
# from core/promote.sh.
set -eu
name=promote
. ci/lib.sh

[ -f core/promote.sh ] || nogo "core/promote.sh not found"

repo=$(pwd)
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT
mkdir -p "$root/adapters/stub-delivery" "$root/adapters/stub-harness" \
  "$root/roles/release" "$root/.crew" "$root/world"
ln -s "$repo/core" "$root/core"
ln -s "$repo/ci" "$root/ci"

cat > "$root/roles/release/role.env" <<'ENV'
THINKING=low
TIMEOUT_S=900
HARNESS=stub-harness
ENV

cat > "$root/adapters/stub-delivery/shift.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
printf 'shift %s\n' "$1" >> "$d/effects.log"
STUB
cat > "$root/adapters/stub-delivery/rollback.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
printf 'rollback\n' >> "$d/effects.log"
STUB
chmod +x "$root/adapters/stub-delivery/shift.sh" "$root/adapters/stub-delivery/rollback.sh"

# stub-harness/run.sh: the ADK adapter's artefact contract (docs/adr/0020
# §1), but the answer is whatever $root/world/calls.json the case wrote --
# that file stands in for "what the release role said".
cat > "$root/adapters/stub-harness/run.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
: "${OUT:?OUT not set}"
mkdir -p "$OUT"
printf 'harness-called\n' >> "$d/harness.log"
if [ -f "$d/world/calls.json" ]; then
  cp "$d/world/calls.json" "$OUT/calls.json"
else
  printf '[]\n' > "$OUT/calls.json"
fi
printf 'stub release brief run\n' > "$OUT/final.md"
printf '{"harness":"stub-harness","model":"stub"}\n' > "$OUT/run.json"
STUB
chmod +x "$root/adapters/stub-harness/run.sh"

cd "$root"

record="$root/release.json"
out_dir="$root/.crew/promote"

reset() {
  rm -f "$root/effects.log" "$root/harness.log" "$record"
  rm -rf "$out_dir"
  : > "$root/effects.log"
  : > "$root/harness.log"
}

held_record() {
  cat > "$record" <<'JSON'
{
  "version": "0.2.0-waitlist",
  "stable": "0.1.0-m2",
  "stages": [
    {"pct": 5, "verdict": "GO", "numbers": ["slo: traffic canary(0.2.0-waitlist)=0.208 stable(0.1.0-m2)=4.018"]},
    {"pct": 25, "verdict": "GO", "numbers": ["slo: traffic canary(0.2.0-waitlist)=1.040 stable(0.1.0-m2)=3.186"]}
  ],
  "verdict": "held",
  "held_at": 25,
  "image": "stub-image"
}
JSON
}

rolled_back_record() {
  cat > "$record" <<'JSON'
{
  "version": "0.2.0-waitlist",
  "stable": "0.1.0-m2",
  "stages": [
    {"pct": 5, "verdict": "NO-GO: launchpad — 5%: error_rate 1.000 → rolled back", "numbers": ["slo: error_rate canary(0.2.0-waitlist)=1.000 stable(0.1.0-m2)=0.000"]}
  ],
  "verdict": "rolled-back",
  "held_at": null,
  "image": "stub-image"
}
JSON
}

good_brief_calls() {
  cat > "$root/world/calls.json" <<'JSON'
[{"name": "submit_brief", "args": {"version": "0.2.0-waitlist", "brief": "Release 0.2.0-waitlist: stage 5% GO, stage 25% GO. Recommend promoting to 100%."}}]
JSON
}

brief_missing_version_calls() {
  cat > "$root/world/calls.json" <<'JSON'
[{"name": "submit_brief", "args": {"version": "0.2.0-waitlist", "brief": "Stages passed: 5% and 25%. Ready to promote."}}]
JSON
}

decline_calls() {
  cat > "$root/world/calls.json" <<'JSON'
[{"name": "decline_brief", "args": {"reason": "not confident in the numbers"}}]
JSON
}

log="$root/run.log"
mismatch=""
fail_case() {  # NAME REASON: records the first disagreement only
  [ -z "$mismatch" ] || return 0
  mismatch="$1"
  printf 'ci-promote: %s: %s\n' "$1" "$2" >&2
  cat "$log" >&2
}

effects() { cat "$root/effects.log" 2>/dev/null || true; }
harness_calls() { cat "$root/harness.log" 2>/dev/null || true; }

# run_promote [VAR=val...]: sets $out and $rc; stdin is always /dev/null,
# so "no human answer" (case g) is reached deterministically, never a hang.
# `env` (not a bare VAR=val prefix) because the extra assignments arrive
# through "$@", and a shell only recognises literal NAME=value tokens as
# prefix assignments, never the result of an expansion.
run_promote() {
  out=$(env DELIVERY=stub-delivery AGENT_HARNESS=stub-harness PLANE_HOST=nowhere.invalid \
    RELEASE_RECORD="$record" PROMOTE_OUT="$out_dir" "$@" \
    sh core/promote.sh 2>"$log" </dev/null) && rc=0 || rc=$?
}

want_one_line() {  # NAME: fails the case if $out is not exactly one line
  lines=$(printf '%s' "$out" | awk 'END{print NR}')
  [ "$lines" -eq 1 ] || fail_case "$1" "stdout has $lines lines: $out"
}

# (a) no release record at all.
reset
run_promote
want_one_line a
[ "$out" = "NO-GO: go-for-launch — no release record; run ./go release" ] \
  || fail_case a "stdout: $out"
[ "$rc" -eq 1 ] || fail_case a "exit $rc, want 1"
[ -z "$(effects)" ] || fail_case a "effects: $(effects), want none"
[ -z "$(harness_calls)" ] || fail_case a "the release role was called with no record"

# (b) a rolled-back record.
if [ -z "$mismatch" ]; then
  reset
  rolled_back_record
  run_promote
  want_one_line b
  case "$out" in "NO-GO: go-for-launch — "*"rolled-back"*) : ;; *) fail_case b "stdout: $out, want a NO-GO naming the rolled-back verdict" ;; esac
  [ "$rc" -eq 1 ] || fail_case b "exit $rc, want 1"
  [ -z "$(effects)" ] || fail_case b "effects: $(effects), want none"
  [ -z "$(harness_calls)" ] || fail_case b "the release role was called on a rolled-back record"
fi

# (c) held + a good brief + GO_FOR_LAUNCH=GO: promotes.
if [ -z "$mismatch" ]; then
  reset
  held_record
  good_brief_calls
  run_promote GO_FOR_LAUNCH=GO
  want_one_line c
  [ "$out" = "GO: go-for-launch" ] || fail_case c "stdout: $out"
  [ "$rc" -eq 0 ] || fail_case c "exit $rc, want 0"
  [ "$(effects)" = "shift 100" ] || fail_case c "effects: $(effects), want exactly 'shift 100'"
fi

# (d) held + the same good brief + GO_FOR_LAUNCH=NO-GO: rolls back.
if [ -z "$mismatch" ]; then
  reset
  held_record
  good_brief_calls
  run_promote GO_FOR_LAUNCH=NO-GO
  want_one_line d
  [ "$out" = "NO-GO: go-for-launch — human said NO-GO" ] || fail_case d "stdout: $out"
  [ "$rc" -eq 1 ] || fail_case d "exit $rc, want 1"
  [ "$(effects)" = "rollback" ] || fail_case d "effects: $(effects), want exactly 'rollback'"
fi

# (e) held + a brief that never names the version + GO_FOR_LAUNCH=GO:
# NO-GO before anything shifts.
if [ -z "$mismatch" ]; then
  reset
  held_record
  brief_missing_version_calls
  run_promote GO_FOR_LAUNCH=GO
  want_one_line e
  case "$out" in "NO-GO: go-for-launch — "*) : ;; *) fail_case e "stdout: $out" ;; esac
  [ "$rc" -eq 1 ] || fail_case e "exit $rc, want 1"
  [ -z "$(effects)" ] || fail_case e "effects: $(effects), want none: a brief missing the version must not reach the shift"
fi

# (f) held + decline_brief: nothing to promote.
if [ -z "$mismatch" ]; then
  reset
  held_record
  decline_calls
  run_promote GO_FOR_LAUNCH=GO
  want_one_line f
  case "$out" in "NO-GO: go-for-launch — "*) : ;; *) fail_case f "stdout: $out" ;; esac
  [ "$rc" -eq 1 ] || fail_case f "exit $rc, want 1"
  [ -z "$(effects)" ] || fail_case f "effects: $(effects), want none: a decline must not reach the shift"
fi

# (g) held + a good brief + no GO_FOR_LAUNCH + stdin not a TTY: no human answer.
if [ -z "$mismatch" ]; then
  reset
  held_record
  good_brief_calls
  run_promote
  want_one_line g
  case "$out" in "NO-GO: go-for-launch — "*) : ;; *) fail_case g "stdout: $out" ;; esac
  [ "$rc" -eq 1 ] || fail_case g "exit $rc, want 1"
  [ -z "$(effects)" ] || fail_case g "effects: $(effects), want none: no answer must not reach the shift"
fi

# (h) L0: AGENT_HARNESS=replay — no model, so the brief is rendered from
# the record by core/promote.sh itself (docs/adr/0020 §4 note): held +
# GO → GO, exactly `shift 100`, the release role's harness never called,
# and the brief names the version and every stage.
if [ -z "$mismatch" ]; then
  reset
  held_record
  run_promote AGENT_HARNESS=replay GO_FOR_LAUNCH=GO
  want_one_line h
  [ "$out" = "GO: go-for-launch" ] || fail_case h "stdout: $out"
  [ "$rc" -eq 0 ] || fail_case h "exit $rc, want 0"
  [ "$(effects)" = "shift 100" ] || fail_case h "effects: $(effects), want exactly 'shift 100'"
  [ -z "$(harness_calls)" ] || fail_case h "the release role was called at L0"
  brief_file="$out_dir/brief.md"
  [ -f "$brief_file" ] || fail_case h "no brief written"
  grep -q '0.2.0-waitlist' "$brief_file" 2>/dev/null || fail_case h "the L0 brief does not name the version"
  for pct in 5 25; do
    grep -q "$pct%" "$brief_file" 2>/dev/null || fail_case h "the L0 brief does not name the $pct% stage"
  done
fi

cd "$repo"
[ -z "$mismatch" ] || nogo "stub case $mismatch disagrees with docs/adr/0020 §4"

go

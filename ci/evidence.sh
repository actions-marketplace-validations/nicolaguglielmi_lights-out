#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-evidence: proves core/evidence.sh, the evidence pack per release
# (docs/adr/0081 §7), cold: no plane, no registry, no network. The
# ci/tower.sh shape: a throwaway root symlinking core/ and ci/, a stub state
# store whose get.sh prints $root/state/<id>.json, a release log shaped like
# a demo release (0.2.0 rolled back, tied to a ticket that went through one
# rework; 0.3.0 held and answered GO, tied to no ticket) and a throwaway
# cosign key pair. Expects: GO and a pack with the right entries and gaps
# for each release; a bundle that verifies with cosign verify-blob alone; a
# pack changed by one byte that does not; an unknown version, a malformed
# one and a missing key that are each one NO-GO line. The console frozen
# beside the pack (docs/adr/0089 §5): signed and verified from a logbook,
# tamper rejected; with no logbook the pack is still GO and says so.
# Written from docs/adr/0081 §1-§5 and §7 and docs/adr/0089 §5, not from
# core/evidence.sh.
set -eu
name=evidence
. ci/lib.sh

[ -f core/evidence.sh ] || nogo "core/evidence.sh not found"
command -v cosign >/dev/null 2>&1 || nogo "cosign not found: this check runs in the workbench"
command -v jq >/dev/null 2>&1 || nogo "jq not found: this check runs in the workbench"

repo=$(pwd)
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT
mkdir -p "$root/adapters/stub-state" "$root/state" "$root/.crew" "$root/keys"
ln -s "$repo/core" "$root/core"
ln -s "$repo/ci" "$root/ci"
ln -s "$repo/console" "$root/console"

cat > "$root/adapters/stub-state/get.sh" <<'STUB'
#!/bin/sh
set -eu
d=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
[ "$1" = tickets ] && [ -f "$d/state/$2.json" ] || exit 1
cat "$d/state/$2.json"
STUB

# The ticket's document as the tower leaves it after one rework (ADR 0038)
# and a rollback: the first attempt rejected by the gates, the second one
# merged and released as 0.2.0.
cat > "$root/state/0001.json" <<'JSON'
{"id":"0001","state":"rolled-back",
 "spec":{"sha256":"5pec","title":"Add a reminder"},
 "pr":{"number":7,"url":"http://host/pr/7","head_sha":"h2","base_sha":"b1"},
 "ci":{"verdict":"GO: gates","failed":null,"risk_level":"low","decision":"auto-merge","head_sha":"h2",
       "line":"GO: gates","details":[],"lines":["GO: secrets","GO: lint","GO: gates"]},
 "rework":[{"attempt":1,"judge":"gates","head_sha":"h1","line":"NO-GO: gates — tests: 1 failed",
            "details":["tests: 1 failed"],"lines":["GO: secrets","NO-GO: gates — tests: 1 failed"],"at":"2026-11-12T10:00:00Z"}],
 "merge":{"sha":"m1","head_sha":"h2"},
 "release":{"version":"0.2.0","verdict":"rolled-back","image":"repo@sha256:aaa"}}
JSON

cat > "$root/.crew/releases.jsonl" <<'LOG'
{"kind":"release","at":"2026-11-12T09:00:00Z","ticket":"0001","record":{"version":"0.2.0","stable":"0.1.0","stages":[{"pct":5,"verdict":"NO-GO","numbers":["slo: error_rate 0.3"]}],"verdict":"rolled-back","held_at":null,"image":"repo@sha256:old","sbom":null,"dast":null}}
{"kind":"release","at":"2026-11-12T11:00:00Z","ticket":"0001","record":{"version":"0.2.0","stable":"0.1.0","stages":[{"pct":5,"verdict":"NO-GO","numbers":["slo: error_rate 0.3"]}],"verdict":"rolled-back","held_at":null,"image":"repo@sha256:aaa","sbom":null,"dast":null}}
{"kind":"release","at":"2026-11-12T12:00:00Z","ticket":null,"record":{"version":"0.3.0","stable":"0.1.0","stages":[{"pct":5,"verdict":"GO","numbers":["slo: ok"]},{"pct":25,"verdict":"GO","numbers":["slo: ok"]}],"verdict":"held","held_at":25,"image":"repo@sha256:bbb","sbom":"sha256:sbom","dast":null}}
{"kind":"answer","at":"2026-11-12T12:30:00Z","version":"0.3.0","answer":"GO","by":"nicola","via":"console"}
LOG

# The throwaway key pair, passwordless as ./go up's is (ADR 0025 §2).
# shellcheck disable=SC1007 # deliberately empty: cosign's passwordless-key convention
(cd "$root/keys" && COSIGN_PASSWORD= cosign generate-key-pair --output-key-prefix k </dev/null >/dev/null 2>&1) \
  || nogo "cosign could not generate a throwaway key pair"
key="$root/keys/k.key"
pub="$root/keys/k.pub"

# run N VERSION KEY: core/evidence.sh in the temp root, stdout to $root/N.out,
# stderr to $root/N.err, exit code in $root/N.rc. VERSION "-" leaves it unset.
# $logbook, when set, is the EVIDENCE_LOGBOOK the console is frozen from.
logbook=""
run() {
  rc=0
  (cd "$root" && env -u VERSION -u LOGBOOK_FILE VERSION="${2#-}" EVIDENCE_LOGBOOK="$logbook" RELEASES_LOG=.crew/releases.jsonl STATE_STORE=stub-state \
    EVIDENCE_DIR="$root/out" COSIGN_KEY="$3" sh core/evidence.sh > "$root/$1.out" 2> "$root/$1.err") || rc=$?
  echo "$rc" > "$root/$1.rc"
}
# the gate contract on a run's stdout: one line, and its prefix.
one_line() { [ "$(wc -l < "$root/$1.out" | tr -d ' ')" = 1 ] || nogo "$2: stdout is not exactly one line" "$(cat "$root/$1.out")"; }
# ok N WHAT JQFILE JQEXPR: jq -e on the pack, NO-GO naming WHAT when false.
ok() { jq -e "$3" "$root/out/$2.json" >/dev/null 2>&1 || nogo "$1" "pack $2 does not satisfy: $3"; }

# (a) the rolled-back release: GO, a signed pack, the gaps that release has.
run a 0.2.0 "$key"
one_line a "0.2.0"
case $(cat "$root/a.out") in "GO: evidence"*) ;; *) nogo "0.2.0 is not a GO" "$(cat "$root/a.out")" "$(cat "$root/a.err")" ;; esac
[ "$(cat "$root/a.rc")" = 0 ] || nogo "0.2.0: GO but exit $(cat "$root/a.rc")"
[ -s "$root/out/0.2.0.json" ] || nogo "0.2.0: no pack at EVIDENCE_DIR/0.2.0.json"
[ -s "$root/out/0.2.0.json.bundle" ] || nogo "0.2.0: no bundle beside the pack"
ok "0.2.0: schema" 0.2.0 '.schema == "lights-out.evidence/1" and (.version | if type == "object" then .value else . end) == "0.2.0"'
ok "0.2.0: not the last release line" 0.2.0 '.artefacts.image.value == "repo@sha256:aaa" and (.artefacts.image.source | test(":2"))'
ok "0.2.0: the earlier release is not listed by line" 0.2.0 '(.earlier_releases | if type == "object" then .value else . end) == [1]'
ok "0.2.0: sbom and dast are not missing entries" 0.2.0 '(.artefacts.sbom | has("missing") and (has("value") | not)) and (.artefacts.dast | has("missing") and (has("value") | not))'
ok "0.2.0: answer is not one missing entry saying rolled back" 0.2.0 '.answer | has("missing") and (.missing | test("rolled back"))'
ok "0.2.0: the PR is not packed" 0.2.0 '.prs | length == 1 and (.[0].pr.number.value == 7) and (.[0].merge.sha.value == "m1")'
ok "0.2.0: the rework is not kept" 0.2.0 '.prs[0].rework.value | length == 1 and .[0].attempt == 1'
ok "0.2.0: the gate lines are not kept" 0.2.0 '.prs[0].gates.lines.value | length == 3'
ok "0.2.0: the review is not missing with the decision named" 0.2.0 '.prs[0].review | has("missing") and (.missing | test("auto-merge"))'
ok "0.2.0: the stage times are not missing" 0.2.0 '.stages[0].started_at | has("missing")'
n=$(jq '[.. | objects | select(has("source") and has("missing"))] | length' "$root/out/0.2.0.json")
[ "$(jq '.missing | length' "$root/out/0.2.0.json")" = "$n" ] || nogo "0.2.0: the top-level missing does not list every missing entry ($n)"

# (a') no logbook: the pack is GO all the same, its line says why there is
# no console snapshot, and none is written (ADR 0089 §5).
case $(cat "$root/a.out") in *"; no console snapshot: "?*) ;; *) nogo "0.2.0 with no logbook: the line does not say there is no console snapshot" "$(cat "$root/a.out")" ;; esac
[ ! -e "$root/out/0.2.0.console.html" ] || nogo "0.2.0 with no logbook: a console snapshot was written"

# (b) the pack verifies with cosign alone; one appended byte must not.
verify() { cosign verify-blob --key "$pub" --insecure-ignore-tlog --bundle "$1.bundle" "$1" >/dev/null 2>&1; }
verify "$root/out/0.2.0.json" || nogo "0.2.0: the bundle does not verify with cosign verify-blob"
cp "$root/out/0.2.0.json" "$root/tampered.json"
cp "$root/out/0.2.0.json.bundle" "$root/tampered.json.bundle"
printf ' ' >> "$root/tampered.json"
if verify "$root/tampered.json"; then nogo "a pack with one byte appended still verifies: the signature binds nothing"; fi

# (c) the held, answered release: the answer is packed, the PR is a gap.
run c 0.3.0 "$key"
one_line c "0.3.0"
case $(cat "$root/c.out") in "GO: evidence"*) ;; *) nogo "0.3.0 is not a GO" "$(cat "$root/c.out")" "$(cat "$root/c.err")" ;; esac
ok "0.3.0: the answer is not packed" 0.3.0 '.answer.answer.value == "GO" and .answer.by.value == "nicola" and .answer.via.value == "console"'
ok "0.3.0: the answer's reason is not missing" 0.3.0 '.answer.reason | has("missing")'
ok "0.3.0: the sbom is not a value" 0.3.0 '.artefacts.sbom.value == "sha256:sbom"'
ok "0.3.0: dast is not missing" 0.3.0 '.artefacts.dast | has("missing")'
ok "0.3.0: the PR is not one missing entry" 0.3.0 '.prs | if type == "array" then .[0] else . end | has("missing") and (has("value") | not)'
ok "0.3.0: the release is not the held one" 0.3.0 '.earlier_releases | if type == "object" then .value else . end | length == 0'
verify "$root/out/0.3.0.json" || nogo "0.3.0: the bundle does not verify with cosign verify-blob"

# (d) a pack is rebuilt: no stale bundle survives a new sign (ADR 0081 §5).
printf 'stale' > "$root/out/0.2.0.json.bundle"
run d 0.2.0 "$key"
verify "$root/out/0.2.0.json" || nogo "0.2.0 rebuilt: the old bundle was not replaced by a new signature"

# (d') with a logbook: the console frozen beside the pack, signed into its
# own bundle, verified by cosign alone; one appended byte must not verify.
logbook="$repo/fixtures/logbook/golden-1.5.json"
run s 0.2.0 "$key"
logbook=""
one_line s "0.2.0 with a logbook"
case $(cat "$root/s.out") in "GO: evidence"*"; console snapshot signed") ;; *) nogo "0.2.0 with a logbook: the line does not end in the signed snapshot" "$(cat "$root/s.out")" "$(cat "$root/s.err")" ;; esac
snap="$root/out/0.2.0.console.html"
[ -s "$snap" ] && [ -s "$snap.bundle" ] || nogo "0.2.0 with a logbook: no console snapshot and bundle beside the pack"
grep -q 'id="frozen-logbook"' "$snap" || nogo "0.2.0 with a logbook: the snapshot does not inline the logbook"
grep -q 'evidence pack 0.2.0, logbook of ' "$snap" || nogo "0.2.0 with a logbook: the snapshot's label does not name the pack"
verify "$snap" || nogo "0.2.0 with a logbook: the snapshot's bundle does not verify with cosign verify-blob"
cp "$snap" "$root/tampered.html"
cp "$snap.bundle" "$root/tampered.html.bundle"
printf ' ' >> "$root/tampered.html"
if verify "$root/tampered.html"; then nogo "a snapshot with one byte appended still verifies"; fi

# (e) the refusals: each is exactly one NO-GO line and exit 1.
refused() {
  run "$1" "$2" "$3"
  one_line "$1" "$4"
  case $(cat "$root/$1.out") in "NO-GO: evidence"*) ;; *) nogo "$4: not a NO-GO" "$(cat "$root/$1.out")" ;; esac
  [ "$(cat "$root/$1.rc")" = 1 ] || nogo "$4: NO-GO but exit $(cat "$root/$1.rc")"
}
refused e 9.9.9 "$key" "an unknown version"
refused f - "$key" "an unset VERSION"
refused g ../x "$key" "a VERSION with a slash"
refused h .hidden "$key" "a VERSION that starts with a dot"
[ ! -e "$root/out/9.9.9.json" ] || nogo "an unknown version still wrote a pack"
rm -f "$root/out/0.3.0.json" "$root/out/0.3.0.json.bundle"
refused i 0.3.0 "$root/keys/absent.key" "a missing key"
# no key: the pack is still written, unsigned, and its line says so.
[ -s "$root/out/0.3.0.json" ] || nogo "a missing key: the pack is not written to be read"
[ ! -e "$root/out/0.3.0.json.bundle" ] || nogo "a missing key: a bundle sits beside an unsigned pack"
case $(cat "$root/i.out") in *"./go up"*) ;; *) nogo "a missing key: the line does not name ./go up" "$(cat "$root/i.out")" ;; esac

# (f) nothing the pack reads was written.
[ "$(wc -l < "$root/.crew/releases.jsonl" | tr -d ' ')" = 4 ] || nogo "the release log was changed"
[ ! -e "$root/state/0002.json" ] || nogo "the state store was written"

go_with "pack for a rolled-back and an answered release, and a frozen console, signed, verified, tamper rejected"

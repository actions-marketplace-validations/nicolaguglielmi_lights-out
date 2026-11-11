#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-agents: proves docs/adr/0073 (a repository customizes its agents) where
# a unit test cannot: cold, local git, no engine, no network, no key.
#   - The cap: 3,072 bytes (§4, a decision) stays below both reviewer
#     prompts, and is the cap core/agents.py enforces.
#   - `./go agents` (`python3 core/agents.py gate`, §10) on workloads/minimal,
#     on the bundled app and on a planted bad contract: one stdout line each.
#   - The translations (§7-§8): core/agents.py mcp turns ci/agents/'s stdio
#     and remote declarations into decl.json, and each adapters/<h>/mcp.sh
#     turns that into its harness's configuration plus `allow`, compared with
#     the goldens in ci/agents/, written from §8 and the verified CLI facts:
#     claude-code's --mcp-config JSON with ${MCP_X} literal, codex's -c list
#     (each value read as TOML, as codex reads it), gemini-cli's settings
#     fragment and its refusals (a remote server, an excluded built-in's
#     name), replay's digest check.
#   - The real core/crew.sh (§6, §8) in a temp root with ADR 0033's stub
#     CodeHost and Tracker and a stub harness that records CREW_MCP: the base's
#     declaration reaches the harness whatever crew-prepare.sh writes; none
#     declared, no CREW_MCP; a remote host missing from the base's
#     crew-egress.txt, antigravity-cli and network+antigravity-cli are refused
#     in one line before any harness runs; replay with a fixture whose
#     .mcp.sha256 differs is refused naming both digests.
# Every check is first proven on a planted defect it must name. Written from
# the ADR and M42's interface contract, not from the scripts.
set -eu
name=agents
. ci/lib.sh

for f in core/agents.py core/crew.sh adapters/claude-code/mcp.sh adapters/codex/mcp.sh \
  adapters/gemini-cli/mcp.sh adapters/replay/mcp.sh adapters/replay/run.sh \
  roles/test-reviewer/prompt.md roles/architect/prompt.md \
  workloads/minimal/.lights-out/worker.md app/worker.md; do
  [ -f "$f" ] || nogo "$f not found"
done

repo=$(pwd)
golden=$repo/ci/agents
cap=3072 # docs/adr/0073 §4: a decision of the ADR's
ws=/crew/0042/workspace
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

first=""
# fail WHAT PROBLEM: one disagreement, on stderr; the first is the NO-GO's.
fail() {
  printf 'ci-agents: %s: %s\n' "$1" "$2" >&2
  [ -n "$first" ] || first="$1: $2"
}

# --- the checks, each printing a problem or nothing ---

# one_line FILE: FILE holds exactly one line.
one_line() {
  n=$(awk 'END {print NR}' "$1")
  [ "$n" -eq 1 ] || printf '%s lines, want exactly one' "$n"
}

# same_json GOT GOLDEN: equal as JSON values (key order aside).
same_json() {
  if [ ! -f "$1" ]; then
    printf '%s was not written' "$(basename "$1")"
  elif ! jq -e . "$1" > /dev/null 2>&1; then
    printf '%s is not JSON' "$(basename "$1")"
  elif [ "$(jq -cS . "$1")" != "$(jq -cS . "$2")" ]; then
    printf '%s is %s, want %s' "$(basename "$1")" "$(jq -cS . "$1")" "$(jq -cS . "$2")"
  fi
}

# same_text GOT GOLDEN: equal text, a trailing newline aside.
same_text() {
  if [ ! -f "$1" ]; then
    printf '%s was not written' "$(basename "$1")"
  elif [ "$(cat "$1")" != "$(cat "$2")" ]; then
    printf "%s is '%s', want '%s'" "$(basename "$1")" "$(cat "$1")" "$(cat "$2")"
  fi
}

# same_codex_args GOT GOLDEN: one `-c` argument per line, `key=value`
# split at the first `=`, the value read as TOML (`_x_ = <value>`) or, when
# that fails, as the raw text with surrounding quotes stripped: what codex
# 0.166.0 does with -c (ADR 0073 "Verified"). Equal to GOLDEN's object, no
# key twice.
cat > "$work/codex_args.py" <<'PY'
import json
import sys
import tomllib

got = {}
with open(sys.argv[1], encoding="utf-8") as f:
    for raw in f.read().splitlines():
        if not raw.strip():
            continue
        key, sep, value = raw.partition("=")
        if not sep:
            print(f"line '{raw}' has no '='")
            sys.exit(0)
        if key in got:
            print(f"{key} is set twice")
            sys.exit(0)
        try:
            got[key] = tomllib.loads("_x_ = " + value)["_x_"]
        except tomllib.TOMLDecodeError:
            got[key] = value.strip("'\"")
with open(sys.argv[2], encoding="utf-8") as f:
    want = json.load(f)
if got != want:
    print("codex-args is " + json.dumps(got, sort_keys=True) + ", want " + json.dumps(want, sort_keys=True))
PY
same_codex_args() {
  if [ ! -f "$1" ]; then
    printf '%s was not written' "$(basename "$1")"
  else
    python3 "$work/codex_args.py" "$1" "$2"
  fi
}

# above_cap FILE...: each FILE is larger than the cap.
above_cap() {
  for f in "$@"; do
    n=$(wc -c < "$f" | tr -d ' ')
    [ "$n" -gt "$cap" ] || { printf '%s is %s bytes, not above the %s-byte cap' "$f" "$n" "$cap"; return; }
  done
}

# decl_digest_ok FILE: decl.json's sha256 is the digest of its servers as
# the interface defines it.
decl_digest_ok() {
  python3 - "$1" <<'PY'
import hashlib
import json
import sys

d = json.load(open(sys.argv[1], encoding="utf-8"))
want = hashlib.sha256(json.dumps(d["servers"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
if d.get("sha256") != want:
    print(f"{sys.argv[1]}: sha256 is {d.get('sha256')}, the digest of its servers is {want}")
PY
}

# --- self-check: each check names a planted defect ---
plant=$work/planted
mkdir -p "$plant"
printf 'GO: agents\nmore\n' > "$plant/two-lines"
jq '.mcpServers.notes.timeout = 60000' "$golden/claude-code.stdio.claude.json" > "$plant/claude.json"
printf 'mcp__notes__search_notes\n' > "$plant/allowed-tools"
jq -r 'to_entries[] | "\(.key)=\(.value | tojson)"' "$golden/codex.stdio.codex-args.json" \
  | sed 's/^mcp_servers\.notes\.required=true$/mcp_servers.notes.required=false/' > "$plant/codex-args"
jq -r 'to_entries[] | "\(.key)=\(.value | tojson)"' "$golden/codex.stdio.codex-args.json" > "$plant/codex-args-good"
awk 'BEGIN {for (i = 0; i < 3071; i++) printf "x"; print ""}' > "$plant/prompt.md"
jq '.servers[0].tools = ["search_notes"]' "$golden/stdio.decl.json" > "$plant/decl.json"
for planted in "one_line $plant/two-lines|2 lines" \
               "same_json $plant/claude.json $golden/claude-code.stdio.claude.json|60000" \
               "same_text $plant/allowed-tools $golden/claude-code.stdio.allowed-tools|mcp__notes__get-note" \
               "same_codex_args $plant/codex-args $golden/codex.stdio.codex-args.json|\"mcp_servers.notes.required\": false" \
               "above_cap roles/test-reviewer/prompt.md $plant/prompt.md|$plant/prompt.md is 3072 bytes" \
               "decl_digest_ok $plant/decl.json|the digest of its servers"; do
  call=${planted%%|*}
  want=${planted#*|}
  # shellcheck disable=SC2086 # the planted call is split into its words on purpose
  got=$($call)
  case "$got" in
    *"$want"*) ;;
    *) nogo "self-check: '$call' on a planted defect said '${got:-nothing}', want a problem naming '$want'" ;;
  esac
done
# ...and passes what is right.
[ -z "$(same_codex_args "$plant/codex-args-good" "$golden/codex.stdio.codex-args.json")" ] \
  || nogo "self-check: same_codex_args rejects its own golden rendered as -c lines"
for d in "$golden/stdio.decl.json" "$golden/remote.decl.json"; do
  problem=$(decl_digest_ok "$d")
  [ -z "$problem" ] || nogo "golden $problem"
done

# --- the cap (§4): below both reviewer prompts, and the one enforced ---
problem=$(above_cap roles/test-reviewer/prompt.md roles/architect/prompt.md)
[ -z "$problem" ] || fail cap "$problem (docs/adr/0073 §4: the cap sits below both reviewer prompts)"
mkdir -p "$work/cap/roles"
awk -v n="$cap" 'BEGIN {for (i = 1; i < n; i++) printf "x"; print ""}' > "$work/cap/roles/test-reviewer.md"
rc=0
python3 core/agents.py check --contract "$work/cap" > "$work/cap.out" 2> "$work/cap.err" || rc=$?
[ "$rc" -eq 0 ] && [ ! -s "$work/cap.out" ] \
  || fail cap "a role file of exactly $cap bytes is refused: $(cat "$work/cap.out")"
printf 'y' >> "$work/cap/roles/test-reviewer.md"
rc=0
python3 core/agents.py check --contract "$work/cap" > "$work/cap.out" 2> "$work/cap.err" || rc=$?
[ "$rc" -eq 1 ] && [ -z "$(one_line "$work/cap.out")" ] \
  || fail cap "a role file of $((cap + 1)) bytes is not refused in one line (exit $rc): $(cat "$work/cap.out")"

# --- `./go agents` (§10): one stdout line, the lines on stderr ---
# gate_case WHAT CONTRACT WANT_RC WANT_LINE: WANT_LINE exact, or a prefix
# when it ends in `*`.
gate_case() {
  rc=0
  python3 core/agents.py gate --contract "$2" > "$work/gate.out" 2> "$work/gate.err" || rc=$?
  problem=$(one_line "$work/gate.out")
  if [ -n "$problem" ]; then
    fail "$1" "stdout has $problem: $(cat "$work/gate.out")"
    return
  fi
  [ "$rc" -eq "$3" ] || fail "$1" "exit $rc, want $3"
  line=$(cat "$work/gate.out")
  case "$4" in
    *'*') case "$line" in "${4%\*}"*) ;; *) fail "$1" "stdout is '$line', want '$4'" ;; esac ;;
    *) [ "$line" = "$4" ] || fail "$1" "stdout is '$line', want '$4'" ;;
  esac
}
gate_case "gate on workloads/minimal" workloads/minimal/.lights-out 0 \
  "GO: agents — 0 role files, 1 MCP servers, 1 tools"
awk '$0 == "dev-worker MCP: notes (stdio: python3 .lights-out/mcp/notes.py) — tools search_notes" {f = 1} END {exit !f}' \
  "$work/gate.err" || fail "lines of workloads/minimal" "stderr lacks the line 'dev-worker MCP: notes (stdio: python3 .lights-out/mcp/notes.py) — tools search_notes': $(cat "$work/gate.err")"
gate_case "gate on the bundled app" app 0 "GO: agents — 0 role files, 0 MCP servers, 0 tools"
awk '$0 == "dev-worker MCP: none" {f = 1} END {exit !f}' "$work/gate.err" \
  || fail "lines of the bundled app" "stderr lacks the line 'dev-worker MCP: none': $(cat "$work/gate.err")"
mkdir -p "$work/bad/.lights-out/roles"
git init -q "$work/bad"
printf 'Write small commits.\n' > "$work/bad/.lights-out/roles/dev-worker.md"
gate_case "gate on a planted bad contract" "$work/bad/.lights-out" 1 "NO-GO: agents — *"

# --- the translations (§7-§8) ---
# A contract per declaration, and its decl.json from core/agents.py.
for kind in stdio remote; do
  c=$work/contract-$kind/.lights-out
  mkdir -p "$c"
  git init -q "$work/contract-$kind"
  cp "$golden/$kind.mcp.json" "$c/mcp.json"
  [ ! -f "$golden/$kind.crew-egress.txt" ] || cp "$golden/$kind.crew-egress.txt" "$c/crew-egress.txt"
  rc=0
  python3 core/agents.py mcp --harness claude-code --out "$work/decl-$kind" --contract "$c" \
    > "$work/decl-$kind.out" 2> "$work/decl-$kind.err" || rc=$?
  if [ "$rc" -ne 0 ] || [ -s "$work/decl-$kind.out" ]; then
    fail "agents.py mcp on the $kind declaration" "exit $rc, stdout '$(cat "$work/decl-$kind.out")'"
    continue
  fi
  problem=$(same_json "$work/decl-$kind/decl.json" "$golden/$kind.decl.json")
  [ -z "$problem" ] || fail "agents.py mcp on the $kind declaration" "$problem"
done

# translate HARNESS KIND [DECL]: runs adapters/HARNESS/mcp.sh on the
# golden decl.json of KIND (or DECL) into $work/HARNESS.KIND.
translate() {
  out=$work/$1.$2
  rm -rf "$out"
  mkdir -p "$out"
  rc=0
  sh "adapters/$1/mcp.sh" "${3:-$golden/$2.decl.json}" "$out" "$ws" > "$out.stdout" 2> "$out.stderr" || rc=$?
}
for kind in stdio remote; do
  translate claude-code "$kind"
  if [ "$rc" -ne 0 ]; then
    fail "claude-code mcp.sh, $kind" "exit $rc: $(cat "$out.stderr")"
  else
    for check in "same_json claude.json" "same_text allowed-tools" "same_text allow"; do
      fn=${check% *}
      f=${check#* }
      problem=$($fn "$out/$f" "$golden/claude-code.$kind.$f")
      [ -z "$problem" ] || fail "claude-code mcp.sh, $kind" "$problem"
    done
  fi
  translate codex "$kind"
  if [ "$rc" -ne 0 ]; then
    fail "codex mcp.sh, $kind" "exit $rc: $(cat "$out.stderr")"
  else
    problem=$(same_codex_args "$out/codex-args" "$golden/codex.$kind.codex-args.json")
    [ -z "$problem" ] || fail "codex mcp.sh, $kind" "$problem"
    problem=$(same_text "$out/allow" "$golden/codex.$kind.allow")
    [ -z "$problem" ] || fail "codex mcp.sh, $kind" "$problem"
  fi
done
translate gemini-cli stdio
if [ "$rc" -ne 0 ]; then
  fail "gemini-cli mcp.sh, stdio" "exit $rc: $(cat "$out.stderr")"
else
  problem=$(same_json "$out/gemini-mcp.json" "$golden/gemini-cli.stdio.gemini-mcp.json")
  [ -z "$problem" ] || fail "gemini-cli mcp.sh, stdio" "$problem"
  problem=$(same_text "$out/allow" "$golden/gemini-cli.stdio.allow")
  [ -z "$problem" ] || fail "gemini-cli mcp.sh, stdio" "$problem"
fi

# mkdecl SERVERS_JSON > FILE: a decl.json with its digest, the interface's rule.
mkdecl() {
  python3 -c '
import hashlib, json, sys
s = json.loads(sys.argv[1])
print(json.dumps({"sha256": hashlib.sha256(json.dumps(s, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "servers": s}))
' "$1"
}
# refused WHAT NEEDLE CONFIG: the last translate exited 1 with one stderr
# line naming NEEDLE, and wrote no CONFIG.
refused() {
  if [ "$rc" -ne 1 ]; then
    fail "$1" "exit $rc, want 1"
  elif [ -n "$(one_line "$out.stderr")" ]; then
    fail "$1" "stderr has $(one_line "$out.stderr"): $(cat "$out.stderr")"
  elif ! grep -qF -- "$2" "$out.stderr"; then
    fail "$1" "the line does not name $2: $(cat "$out.stderr")"
  elif [ -e "$out/$3" ]; then
    fail "$1" "it refused, but wrote $3"
  fi
}
translate gemini-cli remote
refused "gemini-cli mcp.sh, remote (refused, §8)" docs gemini-mcp.json
mkdecl '[{"name":"notes","transport":"stdio","command":["python3","notes.py"],"tools":["search_notes","web_fetch"]}]' \
  > "$work/builtin.decl.json"
translate gemini-cli builtin "$work/builtin.decl.json"
refused "gemini-cli mcp.sh, a tool named like an excluded built-in (§8)" web_fetch gemini-mcp.json

# replay (§8): decl.json's digest against the fixture's run.json .mcp.sha256.
decl_sha=$(jq -r .sha256 "$golden/stdio.decl.json")
other_sha=$(printf 'another declaration\n' | sha256sum | cut -d' ' -f1)
jq -n --arg s "$decl_sha" '{harness: "codex", mcp: {sha256: $s}}' > "$work/run-same.json"
jq -n --arg s "$other_sha" '{harness: "codex", mcp: {sha256: $s}}' > "$work/run-other.json"
FIXTURE_RUN_JSON="$work/run-same.json"
export FIXTURE_RUN_JSON
translate replay stdio
if [ "$rc" -ne 0 ]; then
  fail "replay mcp.sh, the recorded digest" "exit $rc on an equal digest: $(cat "$out.stderr")"
elif [ ! -f "$out/allow" ] || [ -s "$out/allow" ]; then
  fail "replay mcp.sh, the recorded digest" "want an empty allow file"
fi
FIXTURE_RUN_JSON="$work/run-other.json"
translate replay stdio
unset FIXTURE_RUN_JSON
refused "replay mcp.sh, another recorded digest" "$(printf '%s' "$decl_sha" | cut -c1-12)" allow
grep -qF -- "$(printf '%s' "$other_sha" | cut -c1-12)" "$out.stderr" \
  || fail "replay mcp.sh, another recorded digest" "the line does not name the fixture's digest $other_sha: $(cat "$out.stderr")"

# --- the real core/crew.sh (§6, §8) on stubs ---
root=$work/root
upstream=$root/upstream
mkdir -p "$root/adapters/stub-codehost" "$root/adapters/stub-tracker" "$root/adapters/stub-harness" \
  "$root/adapters/antigravity-cli" "$root/adapters/network" "$root/records" "$upstream"
ln -s "$repo/core" "$root/core"
ln -s "$repo/ci" "$root/ci"
ln -s "$repo/roles" "$root/roles"
ln -s "$repo/adapters/replay" "$root/adapters/replay"

cat > "$root/adapters/stub-codehost/bootstrap.sh" <<'STUB'
exit 0
STUB
cat > "$root/adapters/stub-codehost/clone-url.sh" <<STUB
printf '%s\n' "$upstream"
STUB
cat > "$root/adapters/stub-codehost/push.sh" <<STUB
printf 'push %s\n' "\$2" >> "$root/records/codehost.log"
STUB
cat > "$root/adapters/stub-codehost/open-pr.sh" <<STUB
printf 'open-pr %s\n' "\$1" >> "$root/records/codehost.log"
printf '1 stub://pr/1\n'
STUB
cat > "$root/adapters/stub-tracker/get.sh" <<'STUB'
printf '# %s — a stub ticket for ci/agents.sh\n\n## Perimeter\n\n- `stub.txt`\n' "$1"
STUB
# The stub harness: records whether it ran, CREW_MCP (or <unset>) and the
# decl.json there, then does what a worker does: one commit, patch, pr.json.
cat > "$root/adapters/stub-harness/run.sh" <<'STUB'
set -eu
rec="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)/records/$TICKET"
mkdir -p "$rec"
: > "$rec/ran"
printf '%s\n' "${CREW_MCP-<unset>}" > "$rec/crew-mcp"
if [ -n "${CREW_MCP:-}" ] && [ -f "$CREW_MCP/decl.json" ]; then
  cp "$CREW_MCP/decl.json" "$rec/decl.json"
fi
mkdir -p "$OUT"
printf 'stub change\n' > "$WORKSPACE/stub.txt"
git -C "$WORKSPACE" add stub.txt
git -C "$WORKSPACE" -c user.name=lights-out-tests -c user.email=tests@lights-out.invalid commit -q -m 'stub change'
git -C "$WORKSPACE" format-patch -1 --stdout > "$OUT/patch"
printf '{"title": "stub change", "body": "stub"}\n' > "$OUT/pr.json"
STUB
printf 'exit 0\n' > "$root/adapters/stub-harness/mcp.sh"
for h in antigravity-cli network; do
  cat > "$root/adapters/$h/run.sh" <<STUB
: > "$root/records/ran-$h-\$TICKET"
exit 1
STUB
done

gitu() {
  git -C "$upstream" -c user.name=lights-out-tests -c user.email=tests@lights-out.invalid "$@"
}
git init -q "$upstream"
mkdir -p "$upstream/.lights-out"
printf 'Run the tests with true.\n' > "$upstream/.lights-out/worker.md"
gitu add -A
gitu commit -q -m first
gitu branch -q -M main
first_commit=$(gitu rev-parse HEAD)

# new_base PATH CONTENT ...: the upstream's main becomes the first commit
# plus these files, committed: the base the next attempt forks from.
new_base() {
  gitu reset -q --hard
  gitu clean -fdq
  gitu checkout -q -B main "$first_commit"
  while [ $# -ge 2 ]; do
    mkdir -p "$upstream/$(dirname "$1")"
    printf '%s' "$2" > "$upstream/$1"
    shift 2
  done
  gitu add -A
  gitu commit -q --allow-empty -m base
}

# run_crew TICKET [ENV...]: the real core/crew.sh from the temp root.
run_crew() {
  t=$1
  shift
  rc=0
  (cd "$root" && env TICKET="$t" ROLE=dev-worker ATTEMPT=1 CODE_HOST=stub-codehost TRACKER=stub-tracker \
    WORKLOAD="$upstream" WORKLOAD_CONTRACT="$upstream/.lights-out" WORKLOAD_ATTACHED= \
    AGENT_HARNESS=stub-harness CREW_HARNESS= MAP_BRIEF=off "$@" sh core/crew.sh) \
    > "$work/crew-$t.out" 2> "$work/crew-$t.err" || rc=$?
}
# no_harness_ran TICKET: no stub harness ran for TICKET.
no_harness_ran() {
  for m in "$root/records/$1/ran" "$root/records/ran-antigravity-cli-$1" "$root/records/ran-network-$1"; do
    [ ! -e "$m" ] || { printf 'a harness ran (%s)' "$(basename "$m")"; return; }
  done
}
# refused_line TICKET LINE: exit 1, stdout exactly LINE, no harness ran.
refused_line() {
  problem=$(one_line "$work/crew-$1.out")
  if [ "$rc" -ne 1 ]; then
    fail "crew $1" "exit $rc, want 1: $(cat "$work/crew-$1.out") $(tail -n 3 "$work/crew-$1.err")"
  elif [ -n "$problem" ]; then
    fail "crew $1" "stdout has $problem: $(cat "$work/crew-$1.out")"
  elif [ "$(cat "$work/crew-$1.out")" != "$2" ]; then
    fail "crew $1" "stdout is '$(cat "$work/crew-$1.out")', want '$2'"
  else
    problem=$(no_harness_ran "$1")
    [ -z "$problem" ] || fail "crew $1" "$problem before the refusal"
  fi
}

notes='{"servers": {"notes": {"command": ["python3", ".lights-out/mcp/notes.py"], "tools": ["search_notes"]}}}'
# crew-prepare.sh rewrites the workspace's mcp.json with a second server.
cat > "$work/prepare.sh" <<'PREPARE'
set -eu
mkdir -p "$1/.lights-out"
printf '%s\n' '{"servers": {"notes": {"command": ["python3", ".lights-out/mcp/notes.py"], "tools": ["search_notes"]}, "extra": {"command": ["python3", "x.py"], "tools": ["leak"]}}}' > "$1/.lights-out/mcp.json"
PREPARE
prepare=$(cat "$work/prepare.sh")
mkdecl '[{"name":"notes","transport":"stdio","command":["python3",".lights-out/mcp/notes.py"],"tools":["search_notes"]}]' \
  > "$work/notes.decl.json"

# Self-check of the crew checks: a planted run that went on to the harness.
mkdir -p "$root/records/planted"
: > "$root/records/planted/ran"
printf 'NO-GO: crew — something\n' > "$work/crew-planted.out"
rc=1
saved_first=$first
first=""
refused_line planted 'NO-GO: crew — something' 2> /dev/null
case "$first" in
  *"a harness ran (ran)"*) ;;
  *) nogo "self-check: a refusal after a harness ran was judged '${first:-in agreement}', want 'a harness ran' named" ;;
esac
first=$saved_first
rm -rf "$root/records/planted"

# (a) the base declares notes; crew-prepare.sh adds a server in the
# workspace and the local contract has another, uncommitted: the stub gets
# the base's declaration, in a directory of the run.
new_base .lights-out/mcp.json "$notes" .lights-out/crew-prepare.sh "$prepare"
printf '%s\n' '{"servers": {"notes": {"command": ["python3", ".lights-out/mcp/notes.py"], "tools": ["search_notes"]}, "local": {"command": ["python3", "y.py"], "tools": ["lag"]}}}' \
  > "$upstream/.lights-out/mcp.json"
run_crew mcp-base
if [ "$rc" -ne 0 ] || [ "$(cat "$work/crew-mcp-base.out")" != "GO: crew" ]; then
  fail "crew mcp-base" "exit $rc, stdout '$(cat "$work/crew-mcp-base.out")': $(tail -n 5 "$work/crew-mcp-base.err")"
else
  dir=$(cat "$root/records/mcp-base/crew-mcp")
  case "$dir" in
    "$root/.crew/mcp-base/"*) ;;
    *) fail "crew mcp-base" "CREW_MCP is '$dir', want a directory under the run's $root/.crew/mcp-base/" ;;
  esac
  problem=$(same_json "$root/records/mcp-base/decl.json" "$work/notes.decl.json")
  [ -z "$problem" ] || fail "crew mcp-base" "the harness got $problem"
fi

# (b) nothing declared at the base, whatever crew-prepare.sh writes: no CREW_MCP.
new_base .lights-out/crew-prepare.sh "$prepare"
run_crew mcp-none
if [ "$rc" -ne 0 ]; then
  fail "crew mcp-none" "exit $rc: $(cat "$work/crew-mcp-none.out") $(tail -n 5 "$work/crew-mcp-none.err")"
elif [ "$(cat "$root/records/mcp-none/crew-mcp")" != "<unset>" ]; then
  fail "crew mcp-none" "CREW_MCP is '$(cat "$root/records/mcp-none/crew-mcp")' with nothing declared at the base, want it unset"
fi

# (c) a remote host missing from the base's crew-egress.txt (the local
# contract lists it, uncommitted): §6's line, before any harness.
new_base .lights-out/mcp.json \
  '{"servers": {"docs": {"url": "https://mcp.example.com:443/mcp", "tools": ["search_docs"], "token_env": "MCP_DOCS_TOKEN"}}}' \
  .lights-out/crew-egress.txt 'pypi.org:443
'
printf 'pypi.org:443\nmcp.example.com:443\n' > "$upstream/.lights-out/crew-egress.txt"
run_crew mcp-egress
refused_line mcp-egress "NO-GO: crew — mcp.json server docs: mcp.example.com:443 is not in crew-egress.txt (ADR 0046 §5)"

# (d) antigravity-cli, alone and as a network's member: §8's line, naming
# the harnesses of this root that have mcp.sh.
new_base .lights-out/mcp.json "$notes"
agy="NO-GO: crew — antigravity-cli cannot give the dev-worker MCP servers (ADR 0073 §8); use one of: replay stub-harness"
run_crew mcp-agy AGENT_HARNESS=antigravity-cli
refused_line mcp-agy "$agy"
run_crew mcp-net CREW_HARNESS=network AGENT_HARNESS=antigravity-cli
refused_line mcp-net "$agy"

# (e) replay, with a fixture recorded under another declaration: refused,
# naming both digests, and no PR.
new_base .lights-out/mcp.json "$notes"
fixture=$root/fixtures/mcp-replay/dev-worker
mkdir -p "$fixture"
git clone -q "$upstream" "$work/patch-clone"
printf 'recorded change\n' > "$work/patch-clone/stub.txt"
git -C "$work/patch-clone" add stub.txt
git -C "$work/patch-clone" -c user.name=lights-out-tests -c user.email=tests@lights-out.invalid commit -q -m 'recorded change'
git -C "$work/patch-clone" format-patch -1 --stdout > "$fixture/patch"
printf '{"title": "recorded change", "body": "stub"}\n' > "$fixture/pr.json"
jq -n --arg s "$other_sha" '{harness: "claude-code", model: "recorded", mcp: {sha256: $s}}' > "$fixture/run.json"
rm -f "$root/records/codehost.log"
run_crew mcp-replay AGENT_HARNESS=replay FIXTURE_RUN_JSON="$fixture/run.json"
notes_sha=$(jq -r .sha256 "$work/notes.decl.json")
if [ "$rc" -ne 1 ] || [ -n "$(one_line "$work/crew-mcp-replay.out")" ]; then
  fail "crew mcp-replay" "exit $rc, stdout '$(cat "$work/crew-mcp-replay.out")', want one NO-GO line"
elif ! grep -qF -- "$(printf '%s' "$notes_sha" | cut -c1-12)" "$work/crew-mcp-replay.err" \
  || ! grep -qF -- "$(printf '%s' "$other_sha" | cut -c1-12)" "$work/crew-mcp-replay.err"; then
  fail "crew mcp-replay" "stderr does not name both $notes_sha and $other_sha: $(tail -n 5 "$work/crew-mcp-replay.err")"
elif grep -q '^open-pr' "$root/records/codehost.log" 2>/dev/null; then
  fail "crew mcp-replay" "a PR was opened"
fi

[ -z "$first" ] || nogo "$first"
go

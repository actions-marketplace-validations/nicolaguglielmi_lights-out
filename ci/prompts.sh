#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-prompts: ticket 0004 / docs/adr/0020 §6. A `roles/*/prompt.md` states
# the objective and its acceptance; it names no gate, no gate's tool, no
# Makefile target, and not even the entrypoints themselves — a model told
# what judges it tries to run the judge. Forbidden, case-insensitive,
# whole word: "gate"/"gates" (except "gates/", a path — dev-worker's own
# scope list uses it and stays); every gates/*.sh basename but "test",
# derived from gates/*.sh, never hardcoded; "make <t>" and "./go <t>" for
# every target `make help` lists (the ci/readme.sh derivation), plus the
# bare entrypoints "make" and "./go" on their own — a prompt has no
# business naming either; and the hand list of tools the gates invoke —
# osv-scanner, gitleaks, cosmic-ray, bandit, stryker, eslint,
# tests/mutation, tests/sast. That list is not mechanically derivable
# ("which executable a gate invokes"), so this script self-checks it
# instead: a NO-GO here if a listed tool is no longer named by any
# gates/*.sh, ci/secrets.sh, stacks/*/runners/* (the runners ./go init
# hands a repository, docs/adr/0042 §6, where bandit, cosmic-ray, stryker
# and eslint live since the gates read a command's line, never a tool) or
# an in-repo workload's workload.env (whose *_CMD names its own runners)
# means the list drifted one way (a removed tool); a new tool not on the
# list is the gate-writer's job to add by hand, named below.
# Before ever reading roles/, the checker proves itself on two planted
# files.
set -eu
name=prompts
. ci/lib.sh

[ -d roles ] || nogo "roles/ not found"

# --- the hand list; keep in sync with gates/*.sh and ci/secrets.sh by hand ---
hand_tools="osv-scanner gitleaks cosmic-ray bandit stryker eslint tests/mutation tests/sast"

drift=""
for t in $hand_tools; do
  grep -qrl -- "$t" gates/*.sh ci/secrets.sh stacks/*/runners/* */workload.env workloads/*/.lights-out/workload.env 2>/dev/null || drift="$drift $t"
done
[ -z "$drift" ] || nogo "hand tool list names a tool no gates/*.sh, ci/secrets.sh, stacks/*/runners/* or workload.env invokes any more (drift; add the replacement by hand):$drift"

# --- gates/*.sh basenames, except "test" (the role's own acceptance vocabulary) ---
gate_basenames=""
for f in gates/*.sh; do
  [ -e "$f" ] || continue
  b=$(basename "$f" .sh)
  [ "$b" = test ] && continue
  gate_basenames="$gate_basenames $b"
done

# --- every target `make help` lists (the ci/readme.sh derivation) ---
help_out=$(make --no-print-directory help 2>&1) || nogo "make --no-print-directory help exited nonzero" "$help_out"
targets=$(printf '%s\n' "$help_out" | awk '/^  [a-z]/{print $1}')

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

checker="$work/check.py"
cat > "$checker" <<'PY'
import re
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    checks = []
    for line in f:
        line = line.rstrip("\n")
        if not line:
            continue
        label, literal, exempt = line.split("\t")
        checks.append((label, literal, exempt == "1"))

with open(sys.argv[2], encoding="utf-8") as f:
    text = f.read()

for label, literal, slash_exempt in checks:
    pattern = re.compile(
        r"(?<![A-Za-z0-9_])" + re.escape(literal) + r"(?![A-Za-z0-9_])",
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        if slash_exempt and text[m.end() : m.end() + 1] == "/":
            continue
        print(label)
        sys.exit(1)

sys.exit(0)
PY

checks_file="$work/checks.tsv"
{
  printf 'gate\tgate\t0\n'
  printf 'gates\tgates\t1\n'
  for b in $gate_basenames; do printf '%s\t%s\t0\n' "$b" "$b"; done
  for t in $targets; do
    printf 'make %s\tmake %s\t0\n' "$t" "$t"
    printf './go %s\t./go %s\t0\n' "$t" "$t"
  done
  for tool in $hand_tools; do printf '%s\t%s\t0\n' "$tool" "$tool"; done
  printf 'make\tmake\t0\n'
  printf './go\t./go\t0\n'
} > "$checks_file"

# check_file FILE: prints the first offending label on stdout and exits 1
# if FILE names something forbidden; exits 0 silently otherwise.
check_file() {
  python3 "$checker" "$checks_file" "$1"
}

# --- self-test: the checker must be proven before it judges anything real ---
bad="$work/bad.md"
good="$work/good.md"
printf 'Do not run the mutation suite yourself.\n' > "$bad"
printf 'Read the ticket. Change only what it asks for. Run the app tests from the checkout, then write the pull request text.\n' > "$good"

if out=$(check_file "$bad"); then
  nogo "self-test failed: a planted prompt naming \"mutation\" was not caught"
fi
if ! out=$(check_file "$good"); then
  nogo "self-test failed: an allowed-text prompt was flagged (names \"$out\")"
fi

# --- the real scan ---
first_file=""
first_word=""
detail=""
for f in roles/*/prompt.md; do
  [ -e "$f" ] || continue
  if out=$(check_file "$f"); then
    continue
  fi
  detail="$detail$f names \"$out\"
"
  if [ -z "$first_file" ]; then
    first_file="$f"
    first_word="$out"
  fi
done

[ -z "$first_file" ] || nogo "$first_file names \"$first_word\"" "$detail"

go

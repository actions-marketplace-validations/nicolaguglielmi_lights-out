#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-mutation: docs/adr/0015 §3. The workload's MUTATION_CMD over the
# lines the range BASE..HEAD added or changed under the workload's own
# mutation scope ($WORKLOAD/$WORKLOAD_MUTATION_SCOPE, docs/adr/0030 §2),
# run where its TOOLCHAIN_IMAGE says (docs/adr/0042 §1-§2,
# core/toolchain.sh). The gate reads a score, never a tool: cosmic-ray for
# the bundled app, Stryker for a javascript workload, any runner that
# honours the line (MUTATION_LINES in, one JSON line out). require_range
# must be the first thing that can fail: it is what a cold ci/contract.sh
# run sees (no BASE/HEAD, no plane), and it is what keeps this gate instant
# whenever there is no range to judge. Nothing before it may touch git or
# the engine.
#
# Line scope cannot see deletions: a PR that only deletes lines the suite
# never exercised passes this gate untouched; gates/test.sh is what would
# notice a broken deletion (docs/adr/0015 consequences).
set -eu
name=mutation
. ci/lib.sh
require_range
. core/toolchain.sh

gates_out=${GATES_OUT:-.gates-out}
mkdir -p "$gates_out"

[ -n "${WORKLOAD_MUTATION_SCOPE:-}" ] || nogo "WORKLOAD_MUTATION_SCOPE is empty"
[ -e "$WORKLOAD/$WORKLOAD_MUTATION_SCOPE" ] || nogo "$WORKLOAD/$WORKLOAD_MUTATION_SCOPE does not exist"
[ -n "${MUTATION_CMD:-}" ] || nogo "MUTATION_CMD is empty (docs/adr/0042 §1)"
toolchain_preflight

# Parse the range's hunks under the workload's mutation scope into
# "<module-relative-path>=<start>-<end>,..." groups, space-separated (the
# $WORKLOAD/$WORKLOAD_TEST_ROOT prefix is dropped: every workload's
# Containerfile COPYs its package under its own image's WORKDIR, matching
# cosmic-ray.toml's module-path, docs/adr/0030 §2). Only the new side of
# each hunk is kept: a pure deletion (new count 0) has no line left to
# mutate.
# The diff is the workload repository's, its paths relative to that
# repository's root: the workload's own place in it (its directory for a
# bundled workload, nothing for an attached repository, docs/adr/0037 §3)
# is what --show-prefix gives.
workload_prefix=$(git -C "$WORKLOAD" rev-parse --show-prefix) \
  || nogo "$WORKLOAD is not inside a git repository"

# JUDGED (docs/adr/0074 §3-§4): commits whose trees were already judged,
# space-separated, the caller's claim like BASE. A line HEAD shares with
# any of them is not mutated again: only the lines HEAD adds against the
# base AND against every judged tree are. Empty, the gate is today's.
judged=""
judged_short=""
for j in ${JUDGED:-}; do
  jc=$(git -C "$WORKLOAD" rev-parse -q --verify "$j^{commit}" 2>/dev/null) \
    || nogo "JUDGED names $j, which is not a commit of the workload's repository (docs/adr/0074 §4)"
  git -C "$WORKLOAD" merge-base --is-ancestor "$jc" "$head" \
    || nogo "JUDGED names $j, which is not an ancestor of HEAD $head (docs/adr/0074 §4)"
  judged="$judged $jc"
  judged_short="$judged_short $(git -C "$WORKLOAD" rev-parse --short "$jc")"
done
judged_short=${judged_short# }

# First line: how many changed lines a judged tree already holds; second:
# the groups to mutate.
# shellcheck disable=SC2086 # $judged is a list of shas, split on purpose
lines_out=$(python3 - "$base" "$head" "$WORKLOAD" "$WORKLOAD_MUTATION_SCOPE" \
  "$workload_prefix" "${WORKLOAD_TEST_ROOT:-}" $judged <<'PY'
import re
import subprocess
import sys

base, head, workload, scope, workload_prefix, test_root = sys.argv[1:7]
judged = sys.argv[7:]

# A workload with no extra subdirectory (WORKLOAD_TEST_ROOT="", docs/adr/
# 0030 §2) strips only the workload's own prefix -- never a trailing
# double slash, never an accidental no-op strip.
prefix = workload_prefix + test_root
hunk_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def added(old):
    """{path: [(start, end), ...]}: the new side of each hunk of old..HEAD."""
    diff = subprocess.run(
        ["git", "-C", workload, "diff", "-U0", old, head, "--", scope],
        capture_output=True, text=True, check=True,
    ).stdout
    file_ranges: dict[str, list[tuple[int, int]]] = {}
    current = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[4:].split("\t", 1)[0]
            if path == "/dev/null":
                current = None
                continue
            if path.startswith("b/"):
                path = path[2:]
            current = path[len(prefix):] if path.startswith(prefix) else path
        elif current and line.startswith("@@"):
            m = hunk_re.match(line)
            if not m:
                continue
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            if count == 0:
                continue
            file_ranges.setdefault(current, []).append((start, start + count - 1))
    return file_ranges


file_ranges = added(base)
skipped = 0
if judged:
    others = [added(j) for j in judged]
    kept: dict[str, list[tuple[int, int]]] = {}
    for path, ranges in file_ranges.items():
        lines = {n for a, b in ranges for n in range(a, b + 1)}
        before = len(lines)
        for other in others:
            lines &= {n for a, b in other.get(path, []) for n in range(a, b + 1)}
        skipped += before - len(lines)
        runs: list[list[int]] = []
        for n in sorted(lines):
            if runs and n == runs[-1][1] + 1:
                runs[-1][1] = n
            else:
                runs.append([n, n])
        if runs:
            kept[path] = [(a, b) for a, b in runs]
    file_ranges = kept

groups = [f"{path}={','.join(f'{a}-{b}' for a, b in ranges)}"
          for path, ranges in sorted(file_ranges.items())]
print(skipped)
print(" ".join(groups))
PY
) || nogo "could not read the diff for $base..$head"
skipped=$(printf '%s\n' "$lines_out" | sed -n 1p)
mutation_lines=$(printf '%s\n' "$lines_out" | sed -n 2p)
waived=""
if [ -n "$judged" ]; then
  waived=", $skipped lines judged at $judged_short"
  printf 'mutation: %s changed line(s) of %s..%s already judged at %s (docs/adr/0074 §3)\n' \
    "$skipped" "$base" "$head" "$judged_short" >&2
fi

if [ -z "$mutation_lines" ]; then
  printf 'mutation: 0 mutants on changed lines in %s..%s; GO by absence of subject, nothing ran\n' "$base" "$head" >&2
  printf '{"total": 0, "score": null}\n' > "$gates_out/mutation.json"
  go_with "in $toolchain_where$waived, nothing ran"
fi

# MUTATION_BASELINE (measured, the workload's workload.env, docs/adr/0030
# §2) and MUTATION_MARGIN (a decision, policy/merge.env, docs/adr/0015 §3),
# either overridden by the workload's policy.env (docs/adr/0037 §5).
effective_policy "$gates_out/effective-policy.env"
MUTATION_BASELINE=$(sed -n 's/^MUTATION_BASELINE=//p' "$gates_out/effective-policy.env")
MUTATION_MARGIN=$(sed -n 's/^MUTATION_MARGIN=//p' "$gates_out/effective-policy.env")
[ -n "$MUTATION_BASELINE" ] || nogo "MUTATION_BASELINE is empty"

log=$(mktemp)
trap 'rm -f "$log"' EXIT

# Tool noise (the engine, the mutation tool, the suite inside each mutant
# run) always on stderr, GO or NO-GO.
set +e
result=$(MUTATION_LINES="$mutation_lines" run_in_toolchain "$MUTATION_CMD" 2>"$log")
rc=$?
set -e

cat "$log" >&2

# The runner's line is the last non-empty one on stdout (docs/adr/0042
# §1): what a command puts before it -- an `npm ci` ahead of the runner,
# say -- is not the score.
result=$(printf '%s\n' "$result" | grep -v '^[[:space:]]*$' | tail -1) || result=""

if [ "$rc" -eq 125 ]; then
  nogo "in $toolchain_where: the toolchain itself failed before the mutation run; see stderr"
fi
if [ "$rc" -ne 0 ]; then
  nogo "in $toolchain_where: mutation run failed before scoring (baseline or tooling error); see stderr"
fi

# The runner tags every survivor line "SURVIVOR file:line operator" on
# stderr (docs/adr/0042 §1); lift them out for nogo's DETAILS.
survivors=$(grep '^SURVIVOR ' "$log" | sed 's/^SURVIVOR //') || survivors=""

reason=$(python3 - "$gates_out/mutation.json" "$MUTATION_BASELINE" "$MUTATION_MARGIN" "$base" "$head" "$result" <<'PY'
import json
import sys

out_path, baseline_s, margin_s, base, head, line = sys.argv[1:7]
threshold = float(baseline_s) - float(margin_s)

try:
    data = json.loads(line)
except ValueError as exc:
    print(f"malformed mutation run output: {exc}: {line!r}")
    sys.exit(1)

with open(out_path, "w") as f:
    json.dump(data, f)
    f.write("\n")

total = data.get("total", 0)
killed = data.get("killed", 0)
score = data.get("score")

if total == 0:
    print(
        f"mutation: 0 mutants on changed lines in {base}..{head} after running "
        "the mutation command; GO by absence of subject",
        file=sys.stderr,
    )
    sys.exit(0)

if score is not None and score >= threshold:
    sys.exit(0)

shown = "none" if score is None else f"{score:.3f}"
print(f"{killed}/{total} mutants on changed lines killed ({shown} < {threshold:.3f}); survivors on stderr")
sys.exit(1)
PY
) && ok=1 || ok=0

if [ "$ok" -ne 1 ]; then
  old_ifs=$IFS
  IFS='
'
  set -f
  # shellcheck disable=SC2086 # $survivors is deliberately word-split, one line per positional arg
  set -- $survivors
  set +f
  IFS=$old_ifs
  nogo "in $toolchain_where: $reason" "$@"
fi

go_with "in $toolchain_where$waived"

#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-mutation: docs/adr/0015 §3. Cosmic-ray over the lines the range
# BASE..HEAD added or changed under the workload's own mutation scope
# ($WORKLOAD/$WORKLOAD_MUTATION_SCOPE, docs/adr/0030 §2). require_range must
# be the first thing that can fail: it is what a cold ci/contract.sh run
# sees (no BASE/HEAD, no plane), and it is what keeps this gate instant
# whenever there is no range to judge. Nothing before it may touch git or
# docker-compose.
#
# Line scope cannot see deletions: a PR that only deletes lines the suite
# never exercised passes this gate untouched; gates/test.sh is what would
# notice a broken deletion (docs/adr/0015 consequences).
set -eu
name=mutation
. ci/lib.sh
require_range

gates_out=${GATES_OUT:-.gates-out}
mkdir -p "$gates_out"

[ -n "${WORKLOAD_MUTATION_SCOPE:-}" ] || nogo "WORKLOAD_MUTATION_SCOPE is empty"
[ -e "$WORKLOAD/$WORKLOAD_MUTATION_SCOPE" ] || nogo "$WORKLOAD/$WORKLOAD_MUTATION_SCOPE does not exist"

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
mutation_lines=$(python3 - "$base" "$head" "$WORKLOAD" "$WORKLOAD_MUTATION_SCOPE" \
  "$workload_prefix" "${WORKLOAD_TEST_ROOT:-}" <<'PY'
import re
import subprocess
import sys

base, head, workload, scope, workload_prefix, test_root = sys.argv[1:7]
diff = subprocess.run(
    ["git", "-C", workload, "diff", "-U0", base, head, "--", scope],
    capture_output=True, text=True, check=True,
).stdout

# A workload with no extra subdirectory (WORKLOAD_TEST_ROOT="", docs/adr/
# 0030 §2) strips only the workload's own prefix -- never a trailing
# double slash, never an accidental no-op strip.
prefix = workload_prefix + test_root
hunk_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
file_ranges: dict[str, list[str]] = {}
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
        file_ranges.setdefault(current, []).append(f"{start}-{start + count - 1}")

groups = [f"{path}={','.join(ranges)}" for path, ranges in sorted(file_ranges.items())]
print(" ".join(groups))
PY
) || nogo "could not read the diff for $base..$head"

if [ -z "$mutation_lines" ]; then
  printf 'mutation: 0 mutants on changed lines in %s..%s; GO by absence of subject, nothing ran\n' "$base" "$head" >&2
  printf '{"total": 0, "score": null}\n' > "$gates_out/mutation.json"
  go
fi

# MUTATION_BASELINE (measured, the workload's workload.env, docs/adr/0030
# §2) and MUTATION_MARGIN (a decision, policy/merge.env, docs/adr/0015 §3),
# either overridden by the workload's policy.env (docs/adr/0037 §5).
effective_policy "$gates_out/effective-policy.env"
MUTATION_BASELINE=$(sed -n 's/^MUTATION_BASELINE=//p' "$gates_out/effective-policy.env")
MUTATION_MARGIN=$(sed -n 's/^MUTATION_MARGIN=//p' "$gates_out/effective-policy.env")
[ -n "$MUTATION_BASELINE" ] || nogo "MUTATION_BASELINE is empty"

# A project name of our own (docs/adr/0015 §2 shared interface, docs/adr/0017
# §11), via -p rather than a written .env: this worktree's backend-test/
# postgres never collide with another job's or a running plane's, and the
# user's own .env (where an L1 key lives) is never touched.
log=$(mktemp)
# `run --rm` only removes the backend-test container; the postgres it
# depends on keeps running under -p lo-mutation on every exit path (go,
# or any nogo below) unless this trap tears it down too.
trap 'docker-compose -p lo-mutation --profile test down -v >&2; rm -f "$log"' EXIT

# Built separately from run, below: `run --build`'s own image-build log
# goes to *its* stdout (confirmed empirically -- not stderr, contrary to
# what the classic, non-Buildkit builder's docs might suggest), which would
# otherwise land inside $result and break the one-JSON-line contract.
docker-compose -p lo-mutation --profile test build backend-test >&2 \
  || nogo "backend-test image build failed; see stderr"

set +e
result=$(docker-compose -p lo-mutation --profile test run --rm -T \
  -e MUTATION_LINES="$mutation_lines" \
  backend-test sh tests/mutation/run.sh 2>"$log" </dev/null)
rc=$?
set -e

# Tool noise (compose, cosmic-ray, pytest inside each mutant run) always on
# stderr, GO or NO-GO.
cat "$log" >&2

if [ "$rc" -ne 0 ]; then
  nogo "mutation run failed before scoring (baseline or tooling error); see stderr"
fi

# score.py (tests/mutation/score.py) tags every survivor line "SURVIVOR
# file:line operator" on stderr; lift them out for nogo's DETAILS.
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
        "cosmic-ray; GO by absence of subject",
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
  nogo "$reason" "$@"
fi

go

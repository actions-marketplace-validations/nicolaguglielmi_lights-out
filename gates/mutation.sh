#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-mutation: docs/adr/0015 §3. Cosmic-ray over the lines the range
# BASE..HEAD added or changed under app/backend/meetups/. require_range must
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

# Parse the range's hunks under app/backend/meetups/ into
# "meetups/<file>=<start>-<end>,..." groups, space-separated (the
# app/backend/ prefix is dropped: the Containerfile COPYs the package to
# /app/meetups, module-path = "meetups" in cosmic-ray.toml). Only the new
# side of each hunk is kept: a pure deletion (new count 0) has no line left
# to mutate.
mutation_lines=$(python3 - "$base" "$head" <<'PY'
import re
import subprocess
import sys

base, head = sys.argv[1], sys.argv[2]
diff = subprocess.run(
    ["git", "diff", "-U0", base, head, "--", "app/backend/meetups/"],
    capture_output=True, text=True, check=True,
).stdout

prefix = "app/backend/"
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
)

if [ -z "$mutation_lines" ]; then
  printf 'mutation: 0 mutants on changed lines in %s..%s; GO by absence of subject, nothing ran\n' "$base" "$head" >&2
  printf '{"total": 0, "score": null}\n' > "$gates_out/mutation.json"
  go
fi

# MUTATION_BASELINE, MUTATION_MARGIN (docs/adr/0015 §3, docs/adr/0016 §6).
# shellcheck disable=SC1091
. policy/merge.env

# A project name of our own (docs/adr/0015 §2 shared interface, docs/adr/0017
# §11), via -p rather than a written .env: this worktree's backend-test/
# postgres never collide with another job's or a running plane's, and the
# user's own .env (where an L1 GEMINI_API_KEY lives) is never touched.
log=$(mktemp)
trap 'rm -f "$log"' EXIT

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

print(f"{killed}/{total} mutants on changed lines killed ({score:.3f} < {threshold:.3f}); survivors on stderr")
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

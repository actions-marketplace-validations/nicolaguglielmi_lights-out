#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# The python mutation runner (docs/adr/0042 §1, §6): cosmic-ray over one
# package, scored into the one line the mutation gate reads. Copied by
# `./go init` from lights-out's stacks/python/runners/ into a repository's
# .lights-out/runners/, and named by its MUTATION_CMD as
#
#   sh .lights-out/runners/mutation.sh <scope> "<test command>"
#
# <scope> is the package directory to mutate, relative to the directory
# the command runs from (WORKLOAD_MUTATION_SCOPE without its trailing
# slash); <test command> is the repository's own suite, one shell line,
# run unchanged for every mutant (`uv run --locked pytest tests -q -x -p
# no:cacheprovider` as drafted). MUTATION_LINES in the environment scopes
# the run: "<scope>/<file>=<start>-<end>,..." groups, space-separated
# (docs/adr/0015 §3's wire format), or "all" / unset for the whole package
# (what `./go init` and `./go mutation-baseline` measure).
#
# Output contract: exactly one JSON line on stdout, score.py's
# {"total", "killed", "survived", "score"}, survivors on stderr as
# "SURVIVOR file:line operator"; everything cosmic-ray prints goes to
# stderr; non-zero exit only when the unmutated suite fails or a tool
# failed. The tools come from the lockfile beside this script, synced into
# an environment of their own (/tmp, per container), never into the
# repository's.
#
# Tests inside the package (a tests/ directory, a test_*.py file) are not
# mutated: a mutant in the suite measures the suite against itself, and
# lights-out's own core/ scored 0.55 with them, 0.39 without
# (docs/adr/0049).
#
# MUTATION_SHARDS: the pending mutants run in that many shards, each in its
# own copy of this directory, the processors here by default (nproc);
# the score and the survivors are a single exec's (docs/adr/0074,
# amendment of 2026-11-11).
#
# MUTATION_SELECT (on by default, or off): each mutant runs only the tests
# that executed its statement in the clean run, recorded per test by
# coverage.py through hook/sitecustomize.py; no test when none did, the
# whole suite when the statement ran outside any test or the clean run
# recorded no test (docs/adr/0076, select.py).
#
# timeout: 10 x the clean run measured here, floor 1 s before the factor
# (docs/adr/0015 §3's rule, measured at every run instead of once because
# the suite is not ours to know). The operators filter is the one
# docs/adr/0015 §3 chose for the bundled app: value-equality <-> identity
# swaps are a style warning, not a test-quality signal.
set -eu

scope=${1:?usage: mutation.sh <scope> "<test command>"}
test_cmd=${2:?usage: mutation.sh <scope> "<test command>"}
here=$(cd "$(dirname "$0")" && pwd)
module=${scope%/}
[ -d "$module" ] || { printf 'mutation.sh: %s is not a directory here (%s)\n' "$module" "$(pwd)" >&2; exit 1; }
# MUTATION_SHARDS: how many shards run the mutants (see the exec below).
shards=${MUTATION_SHARDS:-$(nproc 2>/dev/null || echo 1)}
case "$shards" in ''|*[!0-9]*|0*) printf 'mutation.sh: MUTATION_SHARDS=%s is not a positive integer\n' "$shards" >&2; exit 1 ;; esac
selection=${MUTATION_SELECT:-on}
case "$selection" in on|off) ;; *) printf 'mutation.sh: MUTATION_SELECT=%s is not on or off\n' "$selection" >&2; exit 1 ;; esac
# A runner started by a suite this runner measures measures nothing of it.
unset LIGHTS_OUT_COV_DIR LIGHTS_OUT_COV_SITE LIGHTS_OUT_COV_CONTEXT LIGHTS_OUT_SELECT LIGHTS_OUT_SELECT_DIR

tools=${LIGHTS_OUT_RUNNERS_ENV:-/tmp/lights-out-python-runners}
UV_PROJECT_ENVIRONMENT="$tools" uv sync --locked --no-dev --project "$here" >&2
bin="$tools/bin"

config=$(mktemp -d)/cosmic-ray.toml
work=${config%/*}
session=$work/session.sqlite

mutation_lines=${MUTATION_LINES:-}
scoped=false
if [ -n "$mutation_lines" ] && [ "$mutation_lines" != all ]; then
  scoped=true
fi

# The clean run, timed: a red suite is not a mutation score, and the
# timeout comes from this measurement. With selection on it records which
# test executes which line (docs/adr/0076); a suite that fails only with
# the hook runs again without it, and every mutant runs it whole.
start=$(date +%s)
measured=false
if [ "$selection" = on ]; then
  mkdir "$work/cov"
  site=$("$bin/python" -c 'import sysconfig; print(sysconfig.get_path("purelib"))')
  if PYTHONPATH="$here/hook${PYTHONPATH:+:$PYTHONPATH}" LIGHTS_OUT_COV_DIR="$work/cov" \
      LIGHTS_OUT_COV_SITE="$site" sh -c "$test_cmd" >&2; then
    measured=true
  else
    printf 'mutation.sh: the suite fails with the coverage hook; every mutant runs the whole suite\n' >&2
    selection=off
    start=$(date +%s)
  fi
fi
if [ "$measured" = false ] && ! sh -c "$test_cmd" >&2; then
  printf 'mutation.sh: the unmutated test suite does not pass (%s); not a mutation score\n' "$test_cmd" >&2
  exit 1
fi
elapsed=$(( $(date +%s) - start ))
[ "$elapsed" -ge 1 ] || elapsed=1
timeout=$(( elapsed * 10 ))

cr_cmd=$test_cmd
if [ "$selection" = on ]; then
  mkdir "$work/select"
  rc=0
  "$bin/python" "$here/select.py" map "$module" "$work/cov" "$work/select" >&2 || rc=$?
  rm -rf "$work/cov"
  case $rc in
    0)
      printf '%s\n' "$test_cmd" > "$work/select/command"
      : > "$work/select/runs"
      LIGHTS_OUT_SELECT_DIR=$work/select
      export LIGHTS_OUT_SELECT_DIR
      cr_cmd=$(python3 -c 'import shlex, sys; print(shlex.join(["python3", sys.argv[1], "run"]))' "$here/select.py") ;;
    3)
      printf 'mutation.sh: no per-test coverage from the clean run (no unittest.TestCase ran under the hook); every mutant runs the whole suite\n' >&2
      selection=off ;;
    *)
      printf 'mutation.sh: select.py map failed (exit %s)\n' "$rc" >&2
      exit 1 ;;
  esac
elif [ "${MUTATION_SELECT:-on}" = off ]; then
  printf 'mutation.sh: MUTATION_SELECT=off: every mutant runs the whole suite\n' >&2
fi

python3 - "$config" "$module" "$cr_cmd" "$timeout" "$scoped" "$mutation_lines" <<'PY' >&2
import sys

config_path, module, test_cmd, timeout, scoped, mutation_lines = sys.argv[1:7]

def toml_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

lines = [
    "[cosmic-ray]",
    f"module-path = {toml_str(module)}",
    "excluded-modules = [" + toml_str(module + "/**/tests/**/*.py") + ", " + toml_str(module + "/**/test_*.py") + "]",
    f"test-command = {toml_str(test_cmd)}",
    f"timeout = {timeout}",
    "",
    "[cosmic-ray.distributor]",
    'name = "local"',
    "",
    "[cosmic-ray.filters.operators-filter]",
    "exclude-operators = [",
    '  "core/ReplaceComparisonOperator_Is(Not)?_(Not)?(Eq|[LG]tE?)",',
    '  "core/ReplaceComparisonOperator_(Not)?(Eq|[LG]tE?)_Is(Not)?",',
    "]",
]
if scoped == "true":
    # cr-filter-lines prepends module-path to every key (cosmic-ray 8.7.0,
    # cosmic_ray.tools.filters.line_filter), so the keys are relative to
    # the module; MUTATION_LINES carries the scope prefix.
    prefix = module + "/"
    groups = {}
    for group in mutation_lines.split():
        path, _, ranges = group.partition("=")
        if not path or not ranges:
            continue
        key = path[len(prefix):] if path.startswith(prefix) else path
        groups.setdefault(key, []).extend(r for r in ranges.split(",") if r)
    lines += ["", "[cosmic-ray.filters.line-filter.lines]"]
    for key, ranges in groups.items():
        lines.append(f"{toml_str(key)} = [{', '.join(toml_str(r) for r in ranges)}]")

with open(config_path, "w") as f:
    f.write("\n".join(lines) + "\n")
PY

# cosmic-ray logs through Rich, whose default console writes to stdout
# (workloads/minimal's runner found this on 8.7.0): every call pins
# --verbosity=CRITICAL and sends its stdout to stderr; only the final
# dump | score.py pipe owns stdout.
"$bin/cosmic-ray" --verbosity=CRITICAL init "$config" "$session" >&2
if [ "$scoped" = true ]; then
  "$bin/cr-filter-lines" "$session" --config "$config" >&2
fi
"$bin/cr-filter-operators" "$session" "$config" >&2
"$bin/cr-filter-pragma" "$session" >&2

if ! "$bin/cosmic-ray" --verbosity=CRITICAL baseline "$config" >&2; then
  printf 'mutation.sh: cosmic-ray baseline failed -- the unmutated test suite does not pass under cosmic-ray; not a mutation score\n' >&2
  exit 1
fi

# Shards (docs/adr/0074, amendment of 2026-11-11): the pending mutants are
# dealt round-robin to MUTATION_SHARDS shards, the machine's processors by
# default (nproc, measured at every run). Each shard runs in its own copy
# of this directory with its own copy of the session, the others' mutants
# marked skipped there; each shard's results for its own mutants are then
# written back into the one session, so the dump and the score are the
# ones a single exec would give. One shard is the single exec of before.
pending=$(python3 - "$session" <<'PY'
import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
print(db.execute("select count(*) from work_items where job_id not in (select job_id from work_results)").fetchone()[0])
PY
)
[ "$pending" -ge "$shards" ] || shards=$(( pending > 0 ? pending : 1 ))

if [ "$shards" -eq 1 ]; then
  "$bin/cosmic-ray" --verbosity=CRITICAL exec "$config" "$session" >&2
else
  printf 'mutation.sh: %s pending mutants in %s shards\n' "$pending" "$shards" >&2
  # The pending mutants by job id, read once: a mutant's shard is its rank
  # in this list modulo the number of shards.
  python3 - "$session" "$work/pending" <<'PY'
import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
with open(sys.argv[2], "w") as f:
    for (j,) in db.execute(
            "select job_id from work_items where job_id not in (select job_id from work_results) order by job_id"):
        f.write(j + "\n")
PY
  i=0
  while [ "$i" -lt "$shards" ]; do
    mkdir -p "$work/shard$i"
    cp -a . "$work/shard$i/tree"
    python3 - "$session" "$shards" "$i" "$work/shard$i/session.sqlite" "$work/pending" <<'PY'
import shutil, sqlite3, sys
src, n, i, out, listing = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5]
shutil.copyfile(src, out)
db = sqlite3.connect(out)
pending = open(listing).read().split()
db.executemany(
    "insert into work_results (worker_outcome, output, test_outcome, diff, job_id) values ('SKIPPED', 'Filtered shard', NULL, NULL, ?)",
    [(j,) for k, j in enumerate(pending) if k % n != i])
db.commit()
PY
    i=$((i + 1))
  done
  i=0
  while [ "$i" -lt "$shards" ]; do
    ( cd "$work/shard$i/tree" && "$bin/cosmic-ray" --verbosity=CRITICAL exec "$config" "$work/shard$i/session.sqlite" >&2; echo $? > "$work/shard$i/rc" ) &
    i=$((i + 1))
  done
  wait
  i=0
  while [ "$i" -lt "$shards" ]; do
    rc=$(cat "$work/shard$i/rc" 2>/dev/null || echo 1)
    [ "$rc" -eq 0 ] || { printf 'mutation.sh: shard %s of %s failed (exit %s)\n' "$i" "$shards" "$rc" >&2; exit 1; }
    python3 - "$session" "$shards" "$i" "$work/shard$i/session.sqlite" "$work/pending" <<'PY'
import sqlite3, sys
main, n, i, part, listing = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5]
db = sqlite3.connect(main)
pending = open(listing).read().split()
own = [j for k, j in enumerate(pending) if k % n == i]
db.execute("attach database ? as part", (part,))
db.executemany("insert into work_results select * from part.work_results where job_id = ?", [(j,) for j in own])
db.commit()
PY
    i=$((i + 1))
  done
  rm -rf "$work"/shard*
fi

if [ "$selection" = on ]; then
  awk '$1 == "none" { n++ } $1 == "some" { s++ } $1 == "all" { a++ }
    END { printf "mutation.sh: %d mutants ran no test, %d a selection, %d the whole suite\n", n, s, a }' \
    "$work/select/runs" >&2
fi
"$bin/cosmic-ray" --verbosity=CRITICAL dump "$session" | python3 "$here/score.py"

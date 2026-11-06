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
# timeout: 10 x the clean run measured here, floor 1 s before the factor
# (docs/adr/0015 §3's rule, measured at every run instead of once because
# the suite is not ours to know). The operators filter is the one
# docs/adr/0015 §3 chose for the bundled app: value-equality <-> identity
# swaps are a style warning, not a test-quality signal.
set -eu

scope=${1:?usage: mutation.sh <scope> "<test command>"}
test_cmd=${2:?usage: mutation.sh <scope> "<test command>"}
here=$(dirname "$0")
module=${scope%/}
[ -d "$module" ] || { printf 'mutation.sh: %s is not a directory here (%s)\n' "$module" "$(pwd)" >&2; exit 1; }

tools=${LIGHTS_OUT_RUNNERS_ENV:-/tmp/lights-out-python-runners}
UV_PROJECT_ENVIRONMENT="$tools" uv sync --locked --no-dev --project "$here" >&2
bin="$tools/bin"

config=$(mktemp -d)/cosmic-ray.toml
session=${config%/*}/session.sqlite

mutation_lines=${MUTATION_LINES:-}
scoped=false
if [ -n "$mutation_lines" ] && [ "$mutation_lines" != all ]; then
  scoped=true
fi

# The clean run, timed: a red suite is not a mutation score, and the
# timeout comes from this measurement.
start=$(date +%s)
if ! sh -c "$test_cmd" >&2; then
  printf 'mutation.sh: the unmutated test suite does not pass (%s); not a mutation score\n' "$test_cmd" >&2
  exit 1
fi
elapsed=$(( $(date +%s) - start ))
[ "$elapsed" -ge 1 ] || elapsed=1
timeout=$(( elapsed * 10 ))

python3 - "$config" "$module" "$test_cmd" "$timeout" "$scoped" "$mutation_lines" <<'PY' >&2
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

"$bin/cosmic-ray" --verbosity=CRITICAL exec "$config" "$session" >&2

"$bin/cosmic-ray" --verbosity=CRITICAL dump "$session" | python3 "$here/score.py"

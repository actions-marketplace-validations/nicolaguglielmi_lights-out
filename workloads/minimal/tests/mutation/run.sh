#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# tests/mutation/run.sh: runs inside the backend-test image (docs/adr/0015
# §3, docs/adr/0030 §3), invoked by gates/mutation.sh through
# `docker-compose --profile test run --rm --build backend-test sh
# tests/mutation/run.sh`. Unlike the app's own backend-test service, this
# workload's has no depends_on (docs/adr/0030 §6: no database) -- nothing to
# wait on before the suite runs.
#
# Sequence: cosmic-ray init, cr-filter-lines (only when $MUTATION_LINES
# names actual ranges -- unset or "all" means the whole package is in
# scope, the shape `./go mutation-baseline` asks for), cr-filter-operators
# (the defaults minus the Is/IsNot comparison family, configured once in
# cosmic-ray.toml), cr-filter-pragma (the "# pragma: no mutate" escape
# hatch), cosmic-ray baseline (the unmutated suite must pass -- a red suite
# must never read as "every mutant killed"), cosmic-ray exec (the "local"
# distributor pinned in cosmic-ray.toml runs mutants sequentially -- this
# suite has no shared state to protect, unlike the app's Postgres, but the
# distributor stays "local" for the same reason cosmic-ray.toml's own
# comment gives), cosmic-ray dump piped into score.py.
#
# Output contract: exactly one JSON line on stdout (score.py's). cosmic-ray
# itself (init/baseline/exec/dump, all under the `cosmic-ray` Click group)
# logs through Rich, and rich.logging.RichHandler's own docstring says its
# default console "writes to stdout" (read from the installed 8.7.0
# package) -- so every `cosmic-ray` call below pins --verbosity=CRITICAL
# *and* redirects its own stdout to stderr; only the final `dump | score.py`
# pipe is left alone. The cr-filter-* tools are separate console scripts
# (argparse + logging.basicConfig, stderr by default) so they are not at
# risk the same way, but get the same ">&2" for consistency.
set -eu

config=/tmp/cosmic-ray.toml
session=/tmp/session.sqlite
cp tests/mutation/cosmic-ray.toml "$config"
rm -f "$session"

mutation_lines=${MUTATION_LINES:-}
scoped=false
if [ -n "$mutation_lines" ] && [ "$mutation_lines" != "all" ]; then
  scoped=true
fi

if [ "$scoped" = true ]; then
  # Build [cosmic-ray.filters.line-filter.lines] from $MUTATION_LINES
  # ("minimal/<file>=<start>-<end>,..." groups, space-separated) and append
  # it to the scratch config copy; cr-filter-lines reads it below.
  python3 - "$config" "$mutation_lines" <<'PY' >&2
import sys

config_path, mutation_lines = sys.argv[1], sys.argv[2]

# module-path = "minimal" in cosmic-ray.toml: cr-filter-lines
# (cosmic_ray.tools.filters.line_filter, 8.7.0, read from the installed
# source) prepends it to every key in [filters.line-filter.lines] to
# rebuild the path it matches against each mutation's module_path
# (_resolve_module_path: Path(module-path) / Path(key)). MUTATION_LINES
# itself keeps the "minimal/" prefix (docs/adr/0015 #3's own wire format;
# gates/mutation.sh strips only $WORKLOAD/, since WORKLOAD_TEST_ROOT is
# empty for this workload, docs/adr/0030 §2), so it is stripped here, once,
# in the one place that needs cosmic-ray's own convention instead.
prefix = "minimal/"
groups: dict[str, list[str]] = {}
for group in mutation_lines.split():
    path, _, ranges = group.partition("=")
    if not path or not ranges:
        continue
    key = path[len(prefix):] if path.startswith(prefix) else path
    groups.setdefault(key, []).extend(r for r in ranges.split(",") if r)

with open(config_path, "a") as f:
    f.write("\n[cosmic-ray.filters.line-filter.lines]\n")
    for key, ranges in groups.items():
        rendered = ", ".join(f'"{r}"' for r in ranges)
        f.write(f'"{key}" = [{rendered}]\n')
PY
fi

cosmic-ray --verbosity=CRITICAL init "$config" "$session" >&2

if [ "$scoped" = true ]; then
  cr-filter-lines "$session" --config "$config" >&2
fi
cr-filter-operators "$session" "$config" >&2
cr-filter-pragma "$session" >&2

if ! cosmic-ray --verbosity=CRITICAL baseline "$config" >&2; then
  printf 'run: baseline failed -- the unmutated test suite does not pass; not a mutation score\n' >&2
  exit 1
fi

cosmic-ray --verbosity=CRITICAL exec "$config" "$session" >&2

cosmic-ray --verbosity=CRITICAL dump "$session" | python3 tests/mutation/score.py

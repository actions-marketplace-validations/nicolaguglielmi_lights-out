#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# The python SAST runner (docs/adr/0042 §1, §6): bandit over one package.
# Copied by `./go init` from lights-out's stacks/python/runners/ into a
# repository's .lights-out/runners/, and named by its SAST_CMD as
#
#   sh .lights-out/runners/sast.sh <scope>
#
# <scope> is the package directory to scan, relative to the directory the
# command runs from; tests are not scanned (bandit flags every `assert`,
# B101, which is no signal in a test), including a tests/ directory or a
# test_*.py file inside the package (found on lights-out's own core/,
# docs/adr/0049). Any finding is a finding: a
# severity floor is a number with no provenance; a `# nosec <reason>`
# comment on the flagged line is the escape hatch, reviewed per finding.
#
# Output contract (docs/adr/0030 §3): exactly one JSON line {"findings":
# N} on stdout; bandit's own report on stderr; non-zero exit only when
# bandit itself failed to run (non-zero *and* no findings parsed): a
# bandit exit of 1 because it found something is not a tool failure. The
# tool comes from the lockfile beside this script, synced into an
# environment of its own, never into the repository's.
set -eu

scope=${1:?usage: sast.sh <scope>}
here=$(dirname "$0")
[ -d "$scope" ] || { printf 'sast.sh: %s is not a directory here (%s)\n' "$scope" "$(pwd)" >&2; exit 1; }

tools=${LIGHTS_OUT_RUNNERS_ENV:-/tmp/lights-out-python-runners}
UV_PROJECT_ENVIRONMENT="$tools" uv sync --locked --no-dev --project "$here" >&2

log=$(mktemp)
trap 'rm -f "$log"' EXIT

rc=0
"$tools/bin/bandit" -r "$scope" -q -x "*/tests/*,*/test_*.py" >"$log" 2>&1 || rc=$?

cat "$log" >&2

count=$(grep -c '^>> Issue:' "$log") || count=0
printf '{"findings": %s}\n' "$count"

if [ "$rc" -eq 0 ]; then
  exit 0
fi
if [ "$count" -gt 0 ]; then
  exit 0
fi
printf 'sast.sh: bandit exited %s with no findings parsed -- not a scored run\n' "$rc" >&2
exit 1

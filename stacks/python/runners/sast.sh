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
# Output contract (docs/adr/0030 §3, amended by docs/adr/0072 §1): exactly
# one JSON line on stdout, {"findings": N, "items": [{"rule", "file",
# "line"}]}, `file` relative to the directory the command runs from, what
# gates/sast.sh fingerprints to tell a new finding from an inherited one;
# one line per finding on stderr; non-zero exit only when bandit itself
# failed to run (no JSON report, or non-zero *and* no findings parsed): a
# bandit exit of 1 because it found something is not a tool failure. The
# tool comes from the lockfile beside this script, synced into an
# environment of its own, never into the repository's.
set -eu

scope=${1:?usage: sast.sh <scope>}
here=$(dirname "$0")
[ -d "$scope" ] || { printf 'sast.sh: %s is not a directory here (%s)\n' "$scope" "$(pwd)" >&2; exit 1; }

tools=${LIGHTS_OUT_RUNNERS_ENV:-/tmp/lights-out-python-runners}
UV_PROJECT_ENVIRONMENT="$tools" uv sync --locked --no-dev --project "$here" >&2

report=$(mktemp)
log=$(mktemp)
trap 'rm -f "$report" "$log"' EXIT

rc=0
"$tools/bin/bandit" -r "$scope" -q -x "*/tests/*,*/test_*.py" -f json -o "$report" >"$log" 2>&1 || rc=$?

cat "$log" >&2

line=$("$tools/bin/python" -c '
import json, posixpath, sys
try:
    results = json.load(open(sys.argv[1]))["results"]
except (OSError, ValueError, KeyError):
    sys.exit(1)
items = []
for r in results:
    path = posixpath.normpath(r["filename"])
    print("%s:%s %s %s" % (path, r["line_number"], r["test_id"], r["issue_text"]), file=sys.stderr)
    items.append({"rule": r["test_id"], "file": path, "line": r["line_number"]})
print(json.dumps({"findings": len(items), "items": items}))
' "$report") || { printf 'sast.sh: bandit exited %s and wrote no JSON report -- not a scored run\n' "$rc" >&2; exit 1; }
printf '%s\n' "$line"

case "$rc:$line" in
  0:*) exit 0 ;;
  *:'{"findings": 0,'*) printf 'sast.sh: bandit exited %s with no findings parsed -- not a scored run\n' "$rc" >&2; exit 1 ;;
esac

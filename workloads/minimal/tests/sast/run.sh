#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# tests/sast/run.sh: runs inside the backend-test image (docs/adr/0030 §3),
# invoked by gates/sast.sh through `docker-compose --profile test run --rm
# --no-deps -T backend-test sh tests/sast/run.sh`; --no-deps because this is
# static analysis and this workload has no dependency to wait on anyway
# (docs/adr/0030 §6: no database).
#
# Scope is exactly minimal/ (docs/adr/0015 §4, docs/adr/0030 §3): tests/ is
# not scanned (bandit would flag `assert`, B101, in every pytest test, which
# is not a signal here). Any finding at all is a finding -- no severity
# floor, because a floor is a number with no stated provenance; a bandit
# `# nosec <reason>` comment on the flagged line is the escape hatch,
# reviewed per finding. Whether a finding is NO-GO is gates/sast.sh's call,
# not this script's.
#
# Output contract (docs/adr/0030 §3, amended by docs/adr/0072 §1): exactly
# one JSON line on stdout, {"findings": N, "items": [{"rule", "file",
# "line"}]}, `file` relative to this directory, what gates/sast.sh
# fingerprints to tell a new finding from one the base already had; one
# line per finding on stderr; non-zero exit only when bandit itself failed
# to run (no JSON report to read, or its own exit code nonzero with no
# finding in it) -- a bandit exit of 1 because it found something is not a
# tool failure.
set -eu

report=$(mktemp)
log=$(mktemp)
trap 'rm -f "$report" "$log"' EXIT

rc=0
bandit -r minimal -q -f json -o "$report" >"$log" 2>&1 || rc=$?

cat "$log" >&2

line=$(python3 -c '
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
' "$report") || { printf 'run: bandit exited %s and wrote no JSON report -- not a scored run\n' "$rc" >&2; exit 1; }
printf '%s\n' "$line"

case "$rc:$line" in
  0:*) exit 0 ;;
  *:'{"findings": 0,'*) printf 'run: bandit exited %s with no findings parsed -- not a scored run\n' "$rc" >&2; exit 1 ;;
esac

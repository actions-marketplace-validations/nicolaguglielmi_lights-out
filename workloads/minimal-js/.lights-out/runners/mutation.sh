#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# The javascript mutation runner (docs/adr/0042 §1, §6): StrykerJS over
# one source directory, scored into the one line the mutation gate reads.
# Copied by `./go init` from lights-out's stacks/javascript/runners/ into
# a repository's .lights-out/runners/, and named by its MUTATION_CMD as
#
#   npm ci && sh .lights-out/runners/mutation.sh <scope> "<test command>"
#
# <scope> is the source directory to mutate, relative to the directory the
# command runs from (WORKLOAD_MUTATION_SCOPE without its trailing slash);
# <test command> is the repository's own suite, one shell line, run whole
# for every mutant by Stryker's command runner (`npm test` as drafted:
# the command runner does no coverage analysis, docs/adr/0042 "Verify
# before writing"). MUTATION_LINES in the environment scopes the run:
# "<scope>/<file>=<start>-<end>,..." groups, space-separated (docs/adr/
# 0015 §3's wire format), which become Stryker's `file:start-end` mutation
# ranges; "all" / unset mutates every .js, .mjs and .cjs under <scope>
# (what `./go init` and `./go mutation-baseline` measure).
#
# Output contract: exactly one JSON line on stdout, score.mjs's {"total",
# "killed", "survived", "score"}, survivors on stderr as "SURVIVOR
# file:line mutator"; everything Stryker prints goes to stderr; non-zero
# exit only when the unmutated suite fails or a tool failed. The tools
# come from the lockfile beside this script, installed into a prefix of
# their own, never into the repository's node_modules.
#
# timeoutMS: 10 x the clean run measured here, floor 1 s before the factor
# (docs/adr/0015 §3's rule; Stryker's own timeoutFactor set to 1 so the
# number on the line is the one applied).
set -eu

scope=${1:?usage: mutation.sh <scope> "<test command>"}
test_cmd=${2:?usage: mutation.sh <scope> "<test command>"}
here=$(dirname "$0")
src=${scope%/}
[ -d "$src" ] || { printf 'mutation.sh: %s is not a directory here (%s)\n' "$src" "$(pwd)" >&2; exit 1; }

prefix=${LIGHTS_OUT_RUNNERS_PREFIX:-/tmp/lights-out-javascript-runners}
if [ ! -x "$prefix/node_modules/.bin/stryker" ]; then
  mkdir -p "$prefix"
  cp "$here/package.json" "$here/package-lock.json" "$prefix/"
  (cd "$prefix" && npm ci --no-audit --no-fund --loglevel=error) >&2
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# The clean run, timed: a red suite is not a mutation score, and the
# timeout comes from this measurement.
start=$(date +%s)
if ! sh -c "$test_cmd" >&2; then
  printf 'mutation.sh: the unmutated test suite does not pass (%s); not a mutation score\n' "$test_cmd" >&2
  exit 1
fi
elapsed=$(( $(date +%s) - start ))
[ "$elapsed" -ge 1 ] || elapsed=1
timeout_ms=$(( elapsed * 10 * 1000 ))

MUTATION_LINES="${MUTATION_LINES:-}" node - "$work" "$src" "$test_cmd" "$timeout_ms" <<'JS' >&2
const fs = require("node:fs");
const path = require("node:path");
const [work, src, testCmd, timeoutMs] = process.argv.slice(2);
const lines = (process.env.MUTATION_LINES || "").trim();
let mutate;
if (lines && lines !== "all") {
  // "<src>/<file>=a-b,c-d" groups -> Stryker's "file:a-b" ranges, one
  // per range (a range never combines with a glob, stryker-mutator.io).
  mutate = [];
  for (const group of lines.split(/\s+/)) {
    const eq = group.indexOf("=");
    if (eq < 0) continue;
    const file = group.slice(0, eq);
    for (const range of group.slice(eq + 1).split(",")) {
      if (range) mutate.push(`${file}:${range}`);
    }
  }
} else {
  mutate = [`${src}/**/*.js`, `${src}/**/*.mjs`, `${src}/**/*.cjs`];
}
const config = {
  testRunner: "command",
  commandRunner: { command: testCmd },
  mutate,
  reporters: ["json"],
  jsonReporter: { fileName: path.join(work, "mutation.json") },
  tempDirName: path.join(work, "stryker-tmp"),
  cleanTempDir: "always",
  timeoutMS: Number(timeoutMs),
  timeoutFactor: 1,
  incremental: false,
  allowConsoleColors: false,
  logLevel: "warn",
};
fs.writeFileSync(path.join(work, "stryker.json"), JSON.stringify(config, null, 2));
JS

"$prefix/node_modules/.bin/stryker" run "$work/stryker.json" >&2

[ -f "$work/mutation.json" ] || { printf 'mutation.sh: Stryker left no JSON report; not a mutation score\n' >&2; exit 1; }
node "$here/score.mjs" "$work/mutation.json"

#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# The javascript SAST runner (docs/adr/0042 §1, §6): eslint with
# eslint-plugin-security's recommended rules over one source directory.
# Copied by `./go init` from lights-out's stacks/javascript/runners/ into
# a repository's .lights-out/runners/, and named by its SAST_CMD as
#
#   sh .lights-out/runners/sast.sh <scope>
#
# <scope> is the source directory to scan, relative to the directory the
# command runs from. The config is eslint.security.mjs beside this script,
# copied into the tools' prefix so its plugin import resolves there (a
# flat config imports its plugins; node resolves them from the config
# file's own directory) and the repository needs none of it. Any finding
# is a finding: a severity floor is a number with no provenance; an
# `// eslint-disable-next-line <rule> -- <reason>` comment is the escape
# hatch, reviewed per finding.
#
# Output contract (docs/adr/0030 §3, amended by docs/adr/0072 §1): exactly
# one JSON line on stdout, {"findings": N, "items": [{"rule", "file",
# "line"}]}, `file` relative to the directory the command runs from (eslint
# reports absolute paths), what gates/sast.sh fingerprints to tell a new
# finding from an inherited one; the report on stderr; non-zero exit only
# when eslint itself failed (exit 2, or no JSON to count): its exit 1 for
# findings is not a tool failure.
set -eu

scope=${1:?usage: sast.sh <scope>}
here=$(dirname "$0")
[ -d "$scope" ] || { printf 'sast.sh: %s is not a directory here (%s)\n' "$scope" "$(pwd)" >&2; exit 1; }

prefix=${LIGHTS_OUT_RUNNERS_PREFIX:-/tmp/lights-out-javascript-runners}
if [ ! -x "$prefix/node_modules/.bin/eslint" ]; then
  mkdir -p "$prefix"
  cp "$here/package.json" "$here/package-lock.json" "$prefix/"
  (cd "$prefix" && npm ci --no-audit --no-fund --loglevel=error) >&2
fi
cp "$here/eslint.security.mjs" "$prefix/eslint.config.mjs"

out=$(mktemp)
log=$(mktemp)
trap 'rm -f "$out" "$log"' EXIT

rc=0
"$prefix/node_modules/.bin/eslint" --config "$prefix/eslint.config.mjs" --no-color -f json "$scope" >"$out" 2>"$log" || rc=$?
cat "$log" >&2

if [ "$rc" -ne 0 ] && [ "$rc" -ne 1 ]; then
  printf 'sast.sh: eslint exited %s -- not a scored run\n' "$rc" >&2
  exit 1
fi

# shellcheck disable=SC2016 # the script is node's, its ${} are template strings
line=$(node -e '
const fs = require("node:fs");
const path = require("node:path");
const results = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
const items = [];
for (const file of results) {
  const rel = path.relative(process.cwd(), file.filePath).split(path.sep).join("/");
  for (const m of file.messages) {
    items.push({ rule: m.ruleId ?? "parse", file: rel, line: m.line ?? 0 });
    console.error(`${rel}:${m.line}:${m.column} ${m.ruleId ?? "parse"} ${m.message}`);
  }
}
console.log(JSON.stringify({ findings: items.length, items }));
' "$out") || { printf 'sast.sh: eslint printed no JSON report -- not a scored run\n' >&2; exit 1; }

printf '%s\n' "$line"

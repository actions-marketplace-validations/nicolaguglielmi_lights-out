#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-gitea-compat: fail on constructs Gitea Actions does not support, so the
# one workflow file stays runnable on both act_runner and GitHub Actions
# (docs/adr/0002-self-ci-is-make-ci.md). actionlint checks GitHub semantics
# only and would not flag any of these.
#
# Map-form `runs-on:` (a job-level engine group/labels selector) is always
# written as a bare `runs-on:` with the value on following lines
# (`group:`/`labels:`); the scalar form always has a value on the same line.
# So a bare `runs-on:` with nothing after the colon is the marker by itself.
set -eu
name=gitea-compat
. ci/lib.sh

workflows=""
for f in .github/workflows/*.yml; do
  [ -e "$f" ] || continue
  workflows="$workflows $f"
done

# No workflow is ci-lint's NO-GO, not this gate's.
[ -n "$workflows" ] || go

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

for f in $workflows; do
  {
    grep -n -E 'environment:' "$f" | sed "s#^#$f:#" \
      | sed 's/$/\t-- environment: at job level is not supported by Gitea Actions/'
    grep -n -E 'id-token' "$f" | sed "s#^#$f:#" \
      | sed 's/$/\t-- id-token is not supported by Gitea Actions/'
    grep -n -E '(success|failure|cancelled)\(\)' "$f" | sed "s#^#$f:#" \
      | sed 's/$/\t-- status function not supported by Gitea Actions (only always())/'
    grep -n -E '^[[:space:]]*runs-on:[[:space:]]*$' "$f" | sed "s#^#$f:#" \
      | sed 's/$/\t-- map-form runs-on: is not supported by Gitea Actions/'
  } >> "$tmp"
done

if [ -s "$tmp" ]; then
  sort -t: -k1,1 -k2,2n "$tmp" >&2
  nogo "constructs Gitea Actions does not support (see stderr)"
fi

go

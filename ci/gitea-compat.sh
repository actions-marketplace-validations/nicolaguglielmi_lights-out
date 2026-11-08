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

# The Pages workflow (docs/adr/0048) needs an environment and id-token:
# write to deploy, and Pages has no Gitea counterpart; the package
# workflow's publish job needs id-token: write to sign keyless (docs/adr/
# 0057 §4). Those two checks are lifted for these files alone, on one
# condition: every job in them carries the github.com guard (ADR 0039), so
# the Gitea runner skips all of it.
github_only=".github/workflows/site.yml .github/workflows/package.yml"

for f in $workflows; do
  {
    if case " $github_only " in *" $f "*) true ;; *) false ;; esac; then
      jobs=$(grep -c -E '^[[:space:]]*runs-on:' "$f" || true)
      guarded=$(grep -c -E "^[[:space:]]*if: github\.server_url == 'https://github\.com'" "$f" || true)
      [ "$jobs" = "$guarded" ] || printf '%s:1:\t-- %s jobs, %s with the github.com guard: a job without it would run on Gitea\n' "$f" "$jobs" "$guarded"
    else
      grep -n -E 'environment:' "$f" | sed "s#^#$f:#" \
        | sed 's/$/\t-- environment: at job level is not supported by Gitea Actions/'
      grep -n -E 'id-token' "$f" | sed "s#^#$f:#" \
        | sed 's/$/\t-- id-token is not supported by Gitea Actions/'
    fi
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

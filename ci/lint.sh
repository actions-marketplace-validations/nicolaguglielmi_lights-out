#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-lint: actionlint over the GitHub Actions workflow(s). actionlint also
# runs shellcheck on `run:` steps because shellcheck is on PATH in workbench.
# ADR 0002 makes the workflow a deliverable, so no workflow is a NO-GO.
set -eu
name=lint

workflows=""
for f in .github/workflows/*.yml; do
  [ -e "$f" ] || continue
  workflows="$workflows $f"
done

if [ -z "$workflows" ]; then
  printf 'NO-GO: %s: no workflow under .github/workflows (ADR 0002 says the workflow is a deliverable)\n' "$name" >&2
  exit 1
fi

# shellcheck disable=SC2086 # word-splitting is deliberate: a list of paths, no spaces in filenames
if ! actionlint $workflows; then
  printf 'NO-GO: %s: actionlint reported problems\n' "$name" >&2
  exit 1
fi

printf 'GO: %s\n' "$name"

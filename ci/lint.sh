#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-lint: actionlint over the GitHub Actions workflow(s). actionlint also
# runs shellcheck on `run:` steps because shellcheck is on PATH in workbench.
# ADR 0002 makes the workflow a deliverable, so no workflow is a NO-GO.
set -eu
name=lint
. ci/lib.sh

workflows=""
for f in .github/workflows/*.yml; do
  [ -e "$f" ] || continue
  workflows="$workflows $f"
done

[ -n "$workflows" ] || nogo "no workflow under .github/workflows (ADR 0002 says the workflow is a deliverable)"

# shellcheck disable=SC2086 # word-splitting is deliberate: a list of paths, no spaces in filenames
actionlint -no-color $workflows >&2 || nogo "actionlint reported problems"

go

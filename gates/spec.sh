#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gate-spec (docs/adr/0055 §4): a spec a test can be written from, before
# any worker sees it. Deterministic, no model: every criterion of `##
# Acceptance criteria` has Given, When and Then in that order and an
# outcome after Then with no phrase from the vague list, and `## Perimeter`
# declares at least one path. core/spec.py holds the rules.
#
#   sh gates/spec.sh <spec.md>
set -eu
name=spec
. ci/lib.sh

[ $# -eq 1 ] || nogo "usage: gates/spec.sh <spec.md>"
[ -f "$1" ] || nogo "no spec at $1"
why=$(python3 core/spec.py check "$1") || nogo "$why"
go

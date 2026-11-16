#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-zero-to-hero: the path from zero to hero at the head of the tutorial,
# the README's levels, the dev container and its proof in the stranger
# workflow, the words beside every Codespaces link, and the frozen console
# first on the site (docs/adr/0097 §5). The judging is
# ci/checks/zero_to_hero.py, whose docstring is the spec; its tests are
# ci/tests/test_zero_to_hero.py (docs/adr/0094).
set -eu
name=zero-to-hero
. ci/lib.sh

verdict ci.checks.zero_to_hero

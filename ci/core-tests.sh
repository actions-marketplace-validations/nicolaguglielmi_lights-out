#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-core-tests: unit tests for core/risk.py (docs/adr/0016 §7). stdlib
# unittest, no engine, no pytest. Needs no range, unlike the gates/*.sh PR
# gates: this runs cold, every time, like every other ci/*.sh self-check.
set -eu
name=core-tests
. ci/lib.sh

# -t . pins the top-level directory to the repo root so `from core.risk
# import classify` resolves the same way whether this runs via `sh
# ci/core-tests.sh`, `./go ci` or plain `python3 -m unittest`.
python3 -m unittest discover -s core/tests -t . >&2 || nogo "unittest reported failures"
# The python stack's runner tests (docs/adr/0042, amendment 2026-11-11):
# beside stacks/python/runners/, never copied into a repository by init.
python3 -m unittest discover -s stacks/python/tests >&2 || nogo "unittest reported failures in stacks/python/tests"

go

#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-deps: dependency scan, docs/adr/0015 §5 as amended by docs/adr/0032.
# `osv-scanner` over every lockfile the workload names (WORKLOAD_LOCKFILES,
# colon-separated, docs/adr/0030 §2 -- dev tools included: they run in the
# build-and-test chain, docs/adr/0015 §1), against the live OSV database at
# api.osv.dev. No engine, network only, so this runs in plain workbench.
#
# The verdict is on the diff (docs/adr/0032): each lockfile is scanned at
# the merge-base and at HEAD, a finding is the tuple (ecosystem, package,
# advisory id), and only a tuple HEAD has and the base does not is NO-GO.
# Advisories already in the base are inherited debt: counted and listed on
# stderr every run, never gating. A lockfile absent at the base is judged
# whole. Any osv-scanner exit other than 0 (clean) or 1 (findings), on
# either scan -- a network failure, most often -- is NO-GO with the tool's
# own error: a scanner that cannot reach its database has not cleared the PR.
# The judgement is core/gates/deps.py (docs/adr/0084).
set -eu
name=deps
. ci/lib.sh
require_range
verdict core.gates.deps "$base" "$head"

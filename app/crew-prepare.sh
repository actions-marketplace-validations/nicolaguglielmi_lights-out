#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# app/crew-prepare.sh <workspace>: the optional per-workload hook
# core/crew.sh runs once, right after cloning the worker's workspace and
# before the harness starts (docs/adr/0030 §3). This workload's own need:
# the backend test suite is written for the test image's layout (app/
# backend/Containerfile, stage `test`: flags/, fakes/ and contracts/ next
# to the backend sources, PYTHONPATH there), not for a source checkout.
# Found live, twice (docs/adr/0018 eval runs, and the M5 fixture before
# them, whose patch carries an out-of-ticket conftest.py edit made for
# exactly this reason): the worker burns its budget rediscovering that. So
# the workspace gets the same layout as three links, excluded from git so
# the adapter's `git add -A` never commits them. Ticket-agnostic: it is
# this repo's app, not any one ticket's.
set -eu
workspace=${1:?usage: crew-prepare.sh <workspace>}

for d in flags fakes contracts; do
  ln -s "../$d" "$workspace/app/backend/$d"
  printf 'app/backend/%s\n' "$d" >> "$workspace/.git/info/exclude"
done

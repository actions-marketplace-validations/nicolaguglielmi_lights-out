#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-statestore-conformance: the StateStore port's conformance suite
# (docs/adr/0060 §4, in the shape of docs/adr/0026 and gates/codehost-
# conformance.sh; the contract is docs/adr/0019 §2). Written from the ADRs,
# never from an adapter. It drives whichever STATE_STORE is set, only through
# `sh adapters/$STATE_STORE/{get,put,delete}.sh <collection> <id>` from the
# current directory. Eight cases, in this order, the first disagreement a
# NO-GO naming the case:
#   1 get of an absent document exits 1 with nothing on stdout
#   2 a document holding every JSON type round-trips, equal as a JSON value
#   3 put replaces the whole document: no merge
#   4 one id in two collections is two documents
#   5 put of non-JSON and of a JSON array exits non-zero and leaves the
#     stored document unchanged
#   6 a 65,536-letter ASCII string round-trips (a decision of ADR 0060 §4:
#     above any tower document seen, below the 128 KiB Linux puts on one
#     argument, MAX_ARG_STRLEN, which an adapter that sends a document with
#     `curl -d` meets: an external constraint)
#   7 delete, then get exits 1; the other collection's document is still there
#   8 delete of an absent document exits 0
# Documents are compared as JSON values, never as text: an adapter
# may print them pretty or compact, with its keys in any order. Documents go
# to put on stdin from files, never as arguments. The ids are the tower's:
# 0001 (a ticket), main (the mainline document) and a 40-hex one (a sha).
#
# It writes only collection conformance-<run id> and, for case 4,
# conformance-<run id>-b, and deletes every document it wrote in a trap on
# any exit, ignoring errors. The run id is date and random hex, as
# codehost-conformance makes it: runs never collide, and two suites on one
# store do not meet.
#
# Lives in gates/, so ci/contract.sh cold-runs it inside `make ci` with no
# CONFORMANCE set and no store: the guard below must be the first thing that
# runs. `./go statestore-conformance` is the only caller that sets
# CONFORMANCE=1, never a bare `sh gates/...` (CLAUDE.md). ci/store-bus.sh
# proves this suite can fail, on stub stores broken one behaviour at a time.
# The cases are core/gates/statestore.py (docs/adr/0084).
set -eu
name=statestore-conformance
. ci/lib.sh

# Instant NO-GO, before anything touches a store (docs/adr/0026 §4).
if [ "${CONFORMANCE:-}" != "1" ]; then
  nogo "set CONFORMANCE=1: this suite writes and deletes documents in the state store (./go statestore-conformance)"
fi
verdict core.gates.statestore

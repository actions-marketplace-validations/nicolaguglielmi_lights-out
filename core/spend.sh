#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-spend: cost and time per ticket, per role and per day, from every
# ticket's `spend` ledger in the state store (docs/adr/0083 §5); one line
# per ticket, role and day on stderr. Stdout is one line of the gate
# contract: `GO: spend — <n> tickets, <r> runs, $<x> known, <u> of cost
# unknown`, or `NO-GO: spend — <why>` when the store cannot be read. A run
# whose model has no price in profiles/prices.json is counted as cost
# unknown, never as zero.
set -eu
name=spend
. ci/lib.sh

out=$(python3 core/spend.py report) || nogo "${out:-core/spend.py failed without a reason; see stderr}"
go_with "$out"

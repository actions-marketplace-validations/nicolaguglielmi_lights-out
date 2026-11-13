#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-eventbus-conformance: the EventBus port's conformance suite
# (docs/adr/0060 §4, in the shape of docs/adr/0026 and gates/codehost-
# conformance.sh; the contract is docs/adr/0019 §3). Written from the ADRs,
# never from an adapter. It drives whichever EVENT_BUS is set, only through
# `sh adapters/$EVENT_BUS/{publish,pull,ack}.sh`, from the current directory.
# `pull` prints "<ackId> <data>" on one line, or nothing; the line is split
# at its first space. Cases, in this order, the first disagreement a NO-GO
# naming the case:
#   0 the first pull prints nothing: a bus with a message of someone else's
#     on it is a NO-GO "the bus is not idle", and the suite does not ack it
#   1 publish, then pull: one "<ackId> <data>" line, the data byte for byte
#     what was published (a JSON line with spaces, a double quote, a
#     backslash and a non-ASCII character), the ackId non-empty, no
#     whitespace in it
#   2 while that message is leased, a second pull prints nothing
#   3 ack exits 0, and the next pull prints nothing
#   4 three messages are pulled and acked as exactly that set (no order is
#     promised), then a pull prints nothing
#   5 only when CONFORMANCE_ACK_DEADLINE gives the adapter's ack deadline,
#     a positive integer of seconds: a message pulled and not acked comes
#     back after it, one that was acked does not. Unset, the GO line says
#     case 5 did not run (a redelivery takes the deadline to prove).
#
# It consumes nothing that is not its own. Every message it publishes carries
# its run id (date and random hex, as codehost-conformance makes it) in the
# data. On any exit it acks the ackIds it was handed for its own messages,
# then drains the bus for any of its own still queued and acks only those; a
# pull that returns a message without its run id during that clean-up is
# left alone (it returns after the adapter's deadline). The drain stops at
# the first empty pull or after 8 pulls, a decision of this suite: it
# publishes six messages at most.
#
# The numbers are decisions of this suite, none a measurement: case 5 waits
# the deadline plus one second, so a lease that ends at the deadline has
# ended whatever the adapter's clock granularity.
#
# Lives in gates/, so ci/contract.sh cold-runs it inside `make ci` with no
# CONFORMANCE set and no bus: the guard below must be the first thing that
# runs. `./go eventbus-conformance` is the only caller that sets
# CONFORMANCE=1, never a bare `sh gates/...` (CLAUDE.md). ci/store-bus.sh
# proves this suite can fail, on stub buses broken one behaviour at a time.
# The cases are core/gates/eventbus.py (docs/adr/0084).
set -eu
name=eventbus-conformance
. ci/lib.sh

# Instant NO-GO, before anything touches a bus (docs/adr/0026 §4).
if [ "${CONFORMANCE:-}" != "1" ]; then
  nogo "set CONFORMANCE=1: this suite publishes messages on the event bus and pulls them (./go eventbus-conformance)"
fi
verdict core.gates.eventbus

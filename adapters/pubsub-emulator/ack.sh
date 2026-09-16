#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ack-pubsub-emulator: acknowledges one message by the ackId pull.sh
# printed (docs/adr/0019 §3). Not a gate: silent on success, one stderr
# line and exit 1 on failure.
set -eu
ackid=${1:?usage: ack.sh <ackId>}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/pubsub-emulator/lib.sh
. "$here/lib.sh"

body=$(jq -cn --arg a "$ackid" '{ackIds: [$a]}')
curl -fsS --connect-timeout 2 --max-time 10 -H 'Content-Type: application/json' \
  -d "$body" "$PUBSUB_URL/subscriptions/$PUBSUB_SUBSCRIPTION:acknowledge" >/dev/null \
  || { printf 'ack-pubsub-emulator: acknowledge failed\n' >&2; exit 1; }

#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# pull-pubsub-emulator: pulls at most one message from the tower
# subscription and prints "<ackId> <data>" on one stdout line, or nothing
# when the subscription is empty (docs/adr/0019 §3). `returnImmediately`
# is what makes an empty pull return at once on the emulator (verified
# live 2026-09-16: `{}` in a few ms) instead of holding the request open;
# it is deprecated on the real API in favour of a client-side timeout,
# which is the `pubsub` adapter's (M8) to handle. Not a gate: one stderr
# line and exit 1 on failure.
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/pubsub-emulator/lib.sh
. "$here/lib.sh"

ensure || exit 1
resp=$(curl -fsS --connect-timeout 2 --max-time 10 -H 'Content-Type: application/json' \
  -d '{"returnImmediately":true,"maxMessages":1}' \
  "$PUBSUB_URL/subscriptions/$PUBSUB_SUBSCRIPTION:pull") \
  || { printf 'pull-pubsub-emulator: pull failed\n' >&2; exit 1; }
printf '%s' "$resp" | jq -r '.receivedMessages[0]? // empty | "\(.ackId) \(.message.data | @base64d)"'

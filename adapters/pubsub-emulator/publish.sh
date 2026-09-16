#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# publish-pubsub-emulator: publishes one message, its data the JSON given
# as the argument, on the tower topic (docs/adr/0019 §3). Not a gate:
# silent on success, one stderr line and exit 1 on failure.
set -eu
data=${1:?usage: publish.sh '<json>'}
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/pubsub-emulator/lib.sh
. "$here/lib.sh"

ensure || exit 1
body=$(jq -cn --arg d "$data" '{messages: [{data: ($d | @base64)}]}')
resp=$(curl -fsS --connect-timeout 2 --max-time 10 -H 'Content-Type: application/json' \
  -d "$body" "$PUBSUB_URL/topics/$PUBSUB_TOPIC:publish") \
  || { printf 'publish-pubsub-emulator: publish failed\n' >&2; exit 1; }
printf '%s' "$resp" | jq -e '.messageIds | length > 0' >/dev/null \
  || { printf 'publish-pubsub-emulator: no messageIds in %s\n' "$resp" >&2; exit 1; }

#!/bin/sh
# shellcheck disable=SC2034 # every name here is for the sourcing script
# SPDX-License-Identifier: Apache-2.0
#
# pubsub-emulator-lib: endpoint, the one topic and the one subscription
# (docs/adr/0019 §3), and `ensure`, which creates both idempotently (PUT:
# 200 created, 409 already there). Sourced by publish.sh, pull.sh and
# ack.sh, never run. The real `pubsub` adapter (M8) keeps the verbs and
# changes PUBSUB_URL plus an Authorization header.
: "${PLANE_HOST:=host.containers.internal}"
: "${PUBSUB_PROJECT:=lights-out}"
: "${PUBSUB_URL:=http://$PLANE_HOST:8085/v1/projects/$PUBSUB_PROJECT}"
PUBSUB_TOPIC=tower
PUBSUB_SUBSCRIPTION=tower-inproc

# ackDeadlineSeconds 600 is the API's own maximum: a step (the gates on a
# cold image build, a release through its stages) runs between pull and
# ack. Past the deadline the message is redelivered and the tower drops
# it as already applied (docs/adr/0019 §2) — the idempotency rule, not
# the deadline, is what makes a slow step safe.
ensure() {
  code=$(curl -sS --connect-timeout 2 --max-time 10 -o /dev/null -w '%{http_code}' \
    -X PUT "$PUBSUB_URL/topics/$PUBSUB_TOPIC") || code=000
  case "$code" in 200|409) : ;; *) printf 'pubsub-emulator: create topic returned %s\n' "$code" >&2; return 1 ;; esac
  code=$(curl -sS --connect-timeout 2 --max-time 10 -o /dev/null -w '%{http_code}' \
    -X PUT -H 'Content-Type: application/json' \
    -d "{\"topic\":\"projects/$PUBSUB_PROJECT/topics/$PUBSUB_TOPIC\",\"ackDeadlineSeconds\":600}" \
    "$PUBSUB_URL/subscriptions/$PUBSUB_SUBSCRIPTION") || code=000
  case "$code" in 200|409) : ;; *) printf 'pubsub-emulator: create subscription returned %s\n' "$code" >&2; return 1 ;; esac
}

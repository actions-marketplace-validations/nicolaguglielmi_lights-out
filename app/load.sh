#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# app-load: generates the traffic verify/slo.sh needs during a launchpad
# stage (docs/adr/0013 §4: the controller generates none itself; production
# has real traffic). One user signs up, creates a capacity-1 meetup, then
# loops registration attempts through Envoy: the first succeeds (201),
# every one after answers 409 where `waitlist` is off, 501 where it is
# targeted on — no state growth either way. Runs until killed; not a gate.
set -eu
: "${PLANE_HOST:=host.containers.internal}"
: "${APP_URL:=http://$PLANE_HOST:8080}"

email="load-$(date +%s)-$$@example.com"
password="load-password"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

curl -fsS -o /dev/null --connect-timeout 1 --max-time 3 \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$email\",\"password\":\"$password\"}" \
  "$APP_URL/api/signup"

token=$(curl -fsS --connect-timeout 1 --max-time 3 \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$email\",\"password\":\"$password\"}" \
    "$APP_URL/api/login" \
  | jq -r .token)

id=$(curl -fsS --connect-timeout 1 --max-time 3 \
    -H 'Content-Type: application/json' -H "Authorization: Bearer $token" \
    -d '{"title":"load","starts_at":"2030-01-01T18:00:00Z","venue":"Milano, Duomo","capacity":1}' \
    "$APP_URL/api/meetups" \
  | jq -r .id)

while true; do
  curl -s -o /dev/null --connect-timeout 1 --max-time 3 -X POST \
    -H "Authorization: Bearer $token" \
    "$APP_URL/api/meetups/$id/registrations" || true
  sleep 0.2
done

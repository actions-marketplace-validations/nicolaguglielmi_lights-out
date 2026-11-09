#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# app-load: generates the traffic verify/slo.sh needs during a launchpad
# stage (docs/adr/0013 §4: the controller generates none itself; production
# has real traffic). One user signs up, creates a capacity-1 meetup, then
# loops registration attempts through Envoy: the first succeeds (201),
# every one after answers 409 where `waitlist` is off, 501 where it is
# targeted on — no state growth either way. Runs until killed; not a gate.
# A setup call that fails is one stderr line and exit 1 (docs/adr/0066 §4).
set -eu
: "${PLANE_HOST:=host.containers.internal}"
: "${APP_URL:=http://$PLANE_HOST:8080}"

email="load-$(date +%s)-$$@example.com"
password="load-password"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# setup METHOD PATH JQ_FILTER [CURL_ARGS...]: one setup call. On any
# failure (curl, HTTP status, a body without the field) one stderr line and
# exit 1: a release with no load must say so, not loop on an empty id
# (docs/adr/0066 §4). curl's own noise goes to a file, never to stderr.
setup() {
  method=$1 path=$2 filter=$3
  shift 3
  if ! body=$(curl -fsS --connect-timeout 1 --max-time 3 -X "$method" "$@" "$APP_URL$path" 2>"$tmp/curl.err"); then
    cause=$(tr '\n' ' ' <"$tmp/curl.err" | sed 's/ *$//')
    printf 'app-load: setup failed at %s %s: %s; generating no load\n' "$method" "$path" "${cause:-curl failed}" >&2
    exit 1
  fi
  if ! value=$(printf '%s' "$body" | jq -er "$filter" 2>/dev/null); then
    printf 'app-load: setup failed at %s %s: no %s in the answer; generating no load\n' "$method" "$path" "$filter" >&2
    exit 1
  fi
  printf '%s' "$value"
}

setup POST /api/signup . -H 'Content-Type: application/json' \
  -d "{\"email\":\"$email\",\"password\":\"$password\"}" >/dev/null

token=$(setup POST /api/login .token -H 'Content-Type: application/json' \
  -d "{\"email\":\"$email\",\"password\":\"$password\"}")

id=$(setup POST /api/meetups .id -H 'Content-Type: application/json' -H "Authorization: Bearer $token" \
  -d '{"title":"load","starts_at":"2030-01-01T18:00:00Z","venue":"Milano, Duomo","capacity":1}')

while true; do
  curl -s -o /dev/null --connect-timeout 1 --max-time 3 -X POST \
    -H "Authorization: Bearer $token" \
    "$APP_URL/api/meetups/$id/registrations" || true
  sleep 0.2
done

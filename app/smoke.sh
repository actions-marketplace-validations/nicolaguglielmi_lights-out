#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# app-smoke: signs up, logs in, creates a meetup and finds it in the list,
# all through Envoy (docs/adr/0012 §6). Not a gate: no GO/NO-GO, no engine
# socket needed. The venue is "Milano, Duomo", the one geocoder fixture that
# resolves (app/contracts/geocoder/examples.json); an unknown venue 500s
# through the fake instead of returning the 201 this script expects.
set -eu
: "${PLANE_HOST:=host.containers.internal}"
: "${APP_URL:=http://$PLANE_HOST:8080}"

email="smoke-$(date +%s)-$$@example.com"
password="smoke-password"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

fail() {
  step=$1
  shift
  printf 'smoke: %s failed: %s\n' "$step" "$*" >&2
  exit 1
}

# check STEP EXPECTED_CODE ACTUAL_CODE BODY_FILE
check() {
  [ "$3" = "$2" ] || fail "$1" "$3 $(cat "$4")"
}

if ! code=$(curl -sS -o "$tmp/signup.json" -w '%{http_code}' --connect-timeout 1 --max-time 3 \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$email\",\"password\":\"$password\"}" \
    "$APP_URL/api/signup" 2>"$tmp/signup.err")
then
  fail signup "$(cat "$tmp/signup.err")"
fi
check signup 201 "$code" "$tmp/signup.json"

if ! code=$(curl -sS -o "$tmp/login.json" -w '%{http_code}' --connect-timeout 1 --max-time 3 \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$email\",\"password\":\"$password\"}" \
    "$APP_URL/api/login" 2>"$tmp/login.err")
then
  fail login "$(cat "$tmp/login.err")"
fi
check login 200 "$code" "$tmp/login.json"
token=$(jq -r '.token' "$tmp/login.json")
[ -n "$token" ] && [ "$token" != "null" ] || fail login "no token in response: $(cat "$tmp/login.json")"

if ! code=$(curl -sS -o "$tmp/meetup.json" -w '%{http_code}' --connect-timeout 1 --max-time 3 \
    -H 'Content-Type: application/json' -H "Authorization: Bearer $token" \
    -d '{"title":"smoke","starts_at":"2030-01-01T18:00:00Z","venue":"Milano, Duomo","capacity":10}' \
    "$APP_URL/api/meetups" 2>"$tmp/meetup.err")
then
  fail create-meetup "$(cat "$tmp/meetup.err")"
fi
check create-meetup 201 "$code" "$tmp/meetup.json"
id=$(jq -r '.id' "$tmp/meetup.json")
venue_lat=$(jq -r '.venue_lat' "$tmp/meetup.json")
[ -n "$id" ] && [ "$id" != "null" ] || fail create-meetup "no id in response: $(cat "$tmp/meetup.json")"
[ -n "$venue_lat" ] && [ "$venue_lat" != "null" ] || fail create-meetup "venue_lat is null: $(cat "$tmp/meetup.json")"

if ! code=$(curl -sS -o "$tmp/list.json" -w '%{http_code}' --connect-timeout 1 --max-time 3 \
    "$APP_URL/api/meetups" 2>"$tmp/list.err")
then
  fail list-meetups "$(cat "$tmp/list.err")"
fi
check list-meetups 200 "$code" "$tmp/list.json"
jq -e --argjson id "$id" 'any(.[]; .id == $id)' "$tmp/list.json" >/dev/null \
  || fail list-meetups "created meetup $id not found: $(cat "$tmp/list.json")"

printf 'smoke: meetup %s created through Envoy at %s (venue_lat=%s)\n' "$id" "$APP_URL" "$venue_lat" >&2

#!/bin/sh
# shellcheck disable=SC2034 # every name here is for the sourcing script
# SPDX-License-Identifier: Apache-2.0
#
# firestore-emulator-lib: the endpoint and the two jq filters between plain
# JSON and Firestore's typed document (docs/adr/0019 §2). Sourced by
# get.sh, put.sh and delete.sh, never run. core/ never sees a stringValue:
# the encoding is this adapter's. The real `firestore` adapter (M8) keeps
# these filters and changes FIRESTORE_URL plus an Authorization header.
: "${PLANE_HOST:=host.containers.internal}"
: "${FIRESTORE_PROJECT:=lights-out}"
: "${FIRESTORE_URL:=http://$PLANE_HOST:8086/v1/projects/$FIRESTORE_PROJECT/databases/(default)/documents}"

# A document is an object: an array or a scalar on stdin is refused, not
# stored as an object keyed by index (docs/adr/0060 §4, case 5).
# integerValue is a string on the wire; an empty array or map carries no
# `values`/`fields` key at all, hence the `// []` and `// {}` on the way back.
FS_ENCODE='
def enc:
  if type == "string" then {stringValue: .}
  elif type == "number" then (if . == floor then {integerValue: (tostring)} else {doubleValue: .} end)
  elif type == "boolean" then {booleanValue: .}
  elif type == "null" then {nullValue: null}
  elif type == "array" then {arrayValue: {values: map(enc)}}
  else {mapValue: {fields: with_entries(.value |= enc)}}
  end;
if type == "object" then {fields: with_entries(.value |= enc)} else error("not an object") end'

FS_DECODE='
def dec:
  if has("stringValue") then .stringValue
  elif has("integerValue") then (.integerValue | tonumber)
  elif has("doubleValue") then .doubleValue
  elif has("booleanValue") then .booleanValue
  elif has("nullValue") then null
  elif has("arrayValue") then ((.arrayValue.values // []) | map(dec))
  elif has("mapValue") then ((.mapValue.fields // {}) | with_entries(.value |= dec))
  else . end;
(.fields // {}) | with_entries(.value |= dec)'

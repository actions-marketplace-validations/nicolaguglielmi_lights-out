#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# harness-replay: replays the one recorded run of <ticket>/<role> instead
# of calling a model (docs/adr/0017 §2). At L0 the worker replays the
# recorded PR of the one real L1 run; it does not re-execute any tool
# call. A replayed run never claims tokens it did not spend: run.json
# reports the recorded numbers, not new ones. Adapter convention (docs/adr/
# 0012 §6): not a gate, silent on success, one stderr line and exit 1 on
# failure.
set -eu
: "${ROLE:?ROLE not set}"
: "${TICKET:?TICKET not set}"
: "${WORKSPACE:?WORKSPACE not set}"
: "${OUT:?OUT not set}"

# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
fixture="$here/fixtures/$TICKET/$ROLE"

if [ ! -f "$fixture/patch" ] || [ ! -f "$fixture/pr.json" ]; then
  printf 'harness-replay: no recorded fixture at fixtures/%s/%s; record one with ./go record TICKET=%s PROFILE=l1\n' \
    "$TICKET" "$ROLE" "$TICKET" >&2
  exit 1
fi

mkdir -p "$OUT"
for f in patch pr.json run.json transcript.jsonl hooks.log; do
  [ -f "$fixture/$f" ] && cp "$fixture/$f" "$OUT/$f"
done

if ! git -C "$WORKSPACE" -c user.name=lights-out-crew -c user.email=crew@lights-out.invalid \
    am "$fixture/patch" >&2; then
  git -C "$WORKSPACE" am --abort >&2 || true
  printf 'harness-replay: fixtures/%s/%s/patch does not apply to this workspace\n' "$TICKET" "$ROLE" >&2
  exit 1
fi

recorded='{}'
[ -f "$fixture/run.json" ] && recorded=$(cat "$fixture/run.json")
jq -n --argjson recorded "$recorded" --arg source "fixtures/$TICKET/$ROLE" \
  '{harness: "replay", model: null, source: $source, recorded: $recorded}' > "$OUT/run.json"

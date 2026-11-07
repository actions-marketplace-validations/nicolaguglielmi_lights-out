#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# harness-adk: the AgentHarness verb for the conversational roles (docs/
# adr/0020 §1). No workspace: INPUT is one file whose text is the user
# message; ANSWERS, optional, a JSON list of later user messages in the
# same conversation (docs/adr/0055 §2); OUT receives calls.json (the tool calls the role made, in
# order), final.md and run.json. The model is the profile's (docs/adr/0040):
# replay at L0, MODEL on MODEL_PROVIDER with the role's thinking otherwise. Adapter
# convention (docs/adr/0012 §6): silent on success, one stderr line and
# exit 1 on failure. Exit 0 with an empty calls.json is a failure — the
# harness-independent invariant of ADR 0017 §1, in this contract's terms.
set -eu
: "${ROLE:?ROLE not set}"
: "${INPUT:?INPUT not set}"
: "${OUT:?OUT not set}"
: "${TIMEOUT_S:=900}"

# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
[ -f "$INPUT" ] || { printf 'harness-adk: INPUT %s is not a file\n' "$INPUT" >&2; exit 1; }
command -v adk >/dev/null 2>&1 || { printf 'harness-adk: adk is not on PATH; rebuild the workbench (./go clean)\n' >&2; exit 1; }
mkdir -p "$OUT"

# litellm (the Claude and OpenAI path, docs/adr/0040 §3, §6) fetches its
# model-cost table from GitHub at import unless told to use the copy it
# ships (verified in litellm 1.106.6's get_model_cost_map.py): the only
# network a role may touch is its provider's API.
LITELLM_LOCAL_MODEL_COST_MAP=True
export LITELLM_LOCAL_MODEL_COST_MAP

rc=0
PYTHONPATH="$here${PYTHONPATH:+:$PYTHONPATH}" LIGHTS_OUT_ROOT="$here/../.." \
  timeout "$TIMEOUT_S" python3 -m lights_out_adk.run </dev/null || rc=$?
if [ "$rc" -eq 124 ]; then
  printf 'harness-adk: %s: over TIMEOUT_S=%s\n' "$ROLE" "$TIMEOUT_S" >&2
  exit 1
fi
[ "$rc" -eq 0 ] || exit 1
if [ "$(jq 'length' "$OUT/calls.json" 2>/dev/null || printf 0)" -eq 0 ]; then
  printf 'harness-adk: %s made no tool call; exit 0 is not success (docs/adr/0020 §1)\n' "$ROLE" >&2
  exit 1
fi

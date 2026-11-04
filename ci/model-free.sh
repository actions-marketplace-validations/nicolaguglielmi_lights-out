#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-model-free: core/, gates/, verify/ and roles/ never name a model
# (docs/adr/0040 §5). The model is a choice of the profile: its id is
# set in profiles/ and .env, translated in adapters/ (the thinking map,
# the request), and nowhere else — in code or in comments, because a
# comment naming an id turns false the day the vendor retires it, the
# way ADR 0018's did. The pattern covers the three providers' id shapes,
# the old MODEL_ID constant, and the key variables (`_api_key`): a role
# or a gate that names GEMINI_API_KEY has chosen a provider. fixtures/
# and docs/ record what ran and are not scanned; ci/ holds this file.
# Extend the pattern when a provider's id shape changes, never shrink it.
set -eu
name=model-free
. ci/lib.sh

for d in core gates verify roles; do
  [ -d "$d" ] || nogo "$d/ not found"
done

pattern='gemini-[0-9]|claude-[a-z]+-[0-9]|gpt-[0-9]|model_id|_api_key'

hits=$(grep -rniE "$pattern" core gates verify roles \
  --exclude-dir=__pycache__ --exclude-dir=.pytest_cache || true)

[ -z "$hits" ] || nogo "core/, gates/, verify/ or roles/ names a model or a key" "$hits"

go

#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# decide (docs/adr/0091 §3): the Decide port's verb through the profile's
# own model (MODEL_PROVIDER, MODEL) with a JSON-schema response, so every
# provider the ADK roles reach answers the same closed questions. A request
# in the port's shape on stdin, the answer on stdout; silent on success, one
# stderr line and exit 1 on failure (docs/adr/0012 §6).
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# litellm reads its bundled cost table, never GitHub (adapters/adk/run.sh).
LITELLM_LOCAL_MODEL_COST_MAP=True
export LITELLM_LOCAL_MODEL_COST_MAP
PYTHONPATH="$here/../adk${PYTHONPATH:+:$PYTHONPATH}" exec python3 "$here/decide.py"

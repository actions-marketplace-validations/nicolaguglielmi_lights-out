#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# decide (docs/adr/0091 §2): the Decide port's verb on the Gemini Decisions
# API. A request in the port's shape on stdin, the answer in the port's
# shape on stdout; silent on success, one stderr line and exit 1 on failure
# (docs/adr/0012 §6). Plain HTTP from the standard library: the SDK method
# needs google-genai 3.2, which the ADK the roles run on forbids.
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$here/decide.py"

#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# The plugin's one resolver (docs/adr/0069 §3): runs `lights-out-gates
# "$@"` at the plugin's own version. lights-out-gates on PATH when its
# `version` names the manifest's version (an older install would read
# `spec` or `mcp` as gates); else uvx at that version; else one NO-GO line,
# on stderr for `mcp`, whose stdout is the protocol, on stdout otherwise.
set -u
here=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
version=$(sed -n 's/^ *"version": *"\([^"]*\)".*/\1/p' "$here/../.claude-plugin/plugin.json" | head -n 1)

if command -v lights-out-gates >/dev/null 2>&1 \
  && [ "$(lights-out-gates version 2>/dev/null </dev/null | awk '{print $2; exit}')" = "$version" ]; then
  exec lights-out-gates "$@"
fi
if command -v uvx >/dev/null 2>&1; then
  exec uvx --quiet --from "lights-out-gates==$version" lights-out-gates "$@"
fi
line="NO-GO: lights-out — lights-out-gates $version not found: uv tool install lights-out-gates==$version, or install uv"
if [ "${1:-}" = mcp ]; then
  printf '%s\n' "$line" >&2
else
  printf '%s\n' "$line"
fi
exit 1

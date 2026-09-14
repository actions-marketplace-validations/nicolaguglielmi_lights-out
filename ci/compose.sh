#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-compose: validates that compose.yaml parses and interpolates cleanly,
# catching YAML and variable-interpolation mistakes before ./go up
# (docs/adr/0012). `config` only renders the file; it needs no engine socket.
set -eu
name=compose
. ci/lib.sh

[ -n "${WORKBENCH_IMAGE:-}" ] || nogo "WORKBENCH_IMAGE is not set; run this via ./go, not directly"

docker-compose config -q || nogo "docker-compose config failed (see stderr)"

go

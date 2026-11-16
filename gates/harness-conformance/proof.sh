#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# harness-conformance-proof: gates/harness-conformance.sh can fail (CLAUDE.md:
# a gate that cannot fail is not a gate), and it can pass, without an engine,
# a key or a real CLI: the suite run, whole, on a made-up harness and a
# stand-in for compose, once good and once per defect. The proof is
# core/gates/harness_proof.py (docs/adr/0084, amendment A2), its defects a
# table there; the made-up harness and the stand-ins are its fixtures, under
# gates/harness-conformance/fake/. Run by `make harness-conformance` before
# the suite judges any real harness. This file keeps its guards and the line.
set -eu
name=harness-conformance-proof
. ci/lib.sh

for tool in python3 jq git; do
  command -v "$tool" >/dev/null 2>&1 || nogo "$tool is not on PATH"
done
# The stand-in for egress's own address: bindable on Linux, the workbench;
# not on a host where only 127.0.0.1 is on the loopback.
python3 -c 'import socket; socket.socket().bind(("127.0.0.2", 0))' 2>/dev/null \
  || nogo "127.0.0.2 is not bindable here, and the proof uses it as egress's address; run it in the workbench (./go harness-conformance)"

verdict core.gates.harness_proof

#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-tower: the control plane's state machine (docs/adr/0019 §1, §2;
# docs/adr/0034; docs/adr/0038 §9). The machine is core/tower.py (docs/adr/
# 0052 §3); this is its entry point, the path the Makefile and
# adapters/inproc/run.sh call. Everything it prints is on stderr.
#
#   tower.sh open <ticket>          write the document at `opened`, publish `assign`
#   tower.sh step <ticket> <step>   apply one step: precondition, effect, write, publish next
#   tower.sh resume <ticket>        request again the step whose last attempt failed
exec python3 core/tower.py "$@"

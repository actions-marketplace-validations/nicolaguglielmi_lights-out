---
description: Check a spec draft with the lights-out spec gate and report its one GO or NO-GO line.
argument-hint: "<spec.md>"
disable-model-invocation: true
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/skill.sh" *)
---

The spec gate of lights-out (docs/adr/0055: every acceptance criterion has
Given, When and Then with an observable outcome, and the perimeter declares
a path) read the draft and answered:

!`sh "${CLAUDE_PLUGIN_ROOT}/scripts/skill.sh" spec $ARGUMENTS`

Report that line to the user exactly as it is, on a line of its own, and
nothing before it. On a NO-GO, the reason after the dash is the first
failure; offer to fix the draft, and change it only if the user asks.

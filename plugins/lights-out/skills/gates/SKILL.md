---
description: Run the lights-out light gates on the staged changes, or on the KEY=VALUE arguments given, and report their one GO or NO-GO line.
argument-hint: "[STAGED=1 | BASE=<ref> HEAD=<ref>] [TICKET=<file>] [TEST_ON_HOST=1]"
disable-model-invocation: true
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/skill.sh" *)
---

The gates of lights-out that need only git and Python (the light tier,
`lights-out-gates --light`, docs/adr/0061) judged this repository and
answered:

!`sh "${CLAUDE_PLUGIN_ROOT}/scripts/skill.sh" gates $ARGUMENTS`

Report that line to the user exactly as it is, on a line of its own, and
nothing before it. The light tier is not the judge: the line names the
gates that did not run, and the full gates run from the image or the
Action. Do not run the gates again, and do not change any file to turn a
NO-GO into a GO unless the user asks you to.

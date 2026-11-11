---
name: gates
description: Run the lights-out light gates on the staged changes, or on the KEY=VALUE arguments the user gives, and report their one GO or NO-GO line. Only when the user asks for it.
---

Run this command in the repository, with the user's KEY=VALUE arguments
(`BASE=<ref> HEAD=<ref>`, `TICKET=<file>`, `TEST_ON_HOST=1`), or
`STAGED=1` when they give none:

    lights-out-gates --light STAGED=1

It prints exactly one line on stdout, `GO: gates-light — …` or `NO-GO:
gates-light — …`; details go to stderr. Report that line to the user
exactly as it is, on a line of its own, and nothing before it. The light
tier is not the judge: the line names the gates that did not run. Do not
run it again and do not change files to turn a NO-GO into a GO unless the
user asks.

If the command is not found, tell the user to install it with
`uv tool install lights-out-gates` and stop.

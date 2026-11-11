---
name: spec
description: Check a spec draft with the lights-out spec gate and report its one GO or NO-GO line. Only when the user asks for it, naming the file.
---

Run this command on the file the user names:

    lights-out-gates spec <file>

It prints exactly one line, `GO: spec` or `NO-GO: spec — <the first
failure>` (every acceptance criterion needs Given, When and Then with an
observable outcome, and the perimeter must declare a path). Report that
line to the user exactly as it is, on a line of its own, and nothing
before it. On a NO-GO, offer to fix the draft; change it only if the user
asks.

If the command is not found, tell the user to install it with
`uv tool install lights-out-gates` and stop.

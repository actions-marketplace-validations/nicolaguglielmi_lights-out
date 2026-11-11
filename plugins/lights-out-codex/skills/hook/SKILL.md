---
name: hook
description: Install or remove the lights-out pre-commit hook in this repository's .codex/hooks.json. Only when the user asks to install or remove it.
---

Run the script beside this file, from inside the repository, with
`install` or `remove` as the user asked:

    sh scripts/hook.sh install

(the path is relative to this skill's directory: use its absolute path).
It prints exactly one line. Report it to the user exactly as it is.

After `install`, the repository's `.codex/hooks.json` holds one
`PreToolUse` hook: before a `git commit`, `lights-out-gates --light
STAGED=1` judges the staged changes and a NO-GO stops the commit. Codex
runs it only once the user has reviewed and trusted it with `/hooks`, and
only when the project's `.codex/` layer is trusted: say so. It needs
`lights-out-gates` on PATH (`uv tool install lights-out-gates`) and a
committed `.lights-out/workload.env`; without that contract it refuses
every commit, so install it only where the contract is.

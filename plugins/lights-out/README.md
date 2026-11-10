# The lights-out plugin for Claude Code

The gates of [lights-out](https://github.com/nicolaguglielmi/lights-out) in
the session (ADR 0069):

    /plugin install lights-out --marketplace nicolaguglielmi/lights-out

Use it and remove it as `docs/use-on-your-repo.md` says, section "The
Claude Code plugin".

- `/lights-out:gates [KEY=VALUE ...]`: the light gates (`lights-out-gates
  --light`), on the staged changes when no key is given. One line.
- `/lights-out:spec <file>`: the spec gate on a draft. One line.
- A `PreToolUse` hook on Bash: before `git commit`, in a repository whose
  HEAD has `.lights-out/workload.env`, the light gates on the staged changes;
  a NO-GO stops the commit.
- An MCP server, `lights-out-gates mcp`, read-only: which ADRs govern a
  path, which tests cover it, which tickets touched it, and the spec gate on
  a draft, over the project map `lights-out-gates map` builds.

Every command runs `lights-out-gates` at this plugin's version: from PATH
when it is that version, else through `uvx`.

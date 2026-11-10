# Handoff: M39 first slice, the agent's toolbelt (ADR 0069), 2026-11-10

Branch `claude/m39-toolbelt-fc9aa6`, from 85f213f (0.3.1 on `main`). Pushed, no pull request, not merged, no tag. Nothing published or listed anywhere: every listing is the owner's (`docs/launch/checklist.md`, "The agent's toolbelt (M39)").

## What is proven

- **`./go ci` from a clean clone under `.crew/`**: `GO: ci` on 9662227 in 3:14 (735 unit tests, `GO: plugin`, `GO: contract`, `GO: docs-drift`, `GO: gates-light`). The first three runs stopped on shellcheck findings in the new test scripts, a checklist citation of an icon that does not exist yet, and `app-free` (the `map` command spells `.lights-out/tickets`, now an exception beside the light tier's); each fixed in its own commit.
- **GitHub Actions** on 9662227, six workflows green: ci 42923759205 (engine-compat `GO: demo, milestone M9, 686s to rollback (budget 900s, plan §2)`), stranger 42923759977 (`GO: demo, milestone M9, 520s to rollback`), self 42923759230 (`GO: gates — risk high, review, in workbench`), site 42923759404, package 42923759204, podman 42923759264. `./go demo` is unchanged by this branch.
- **Unit**: `core/tests/test_mcp.py`, 43 tests written by gate-writer from ADR 0069 without the implementation (the server's four tools and refusals on a map built at a fixture commit, a stale, missing or foreign map refused with one line naming both shas and `lights-out-gates map`, both protocol eras, -32602/-32601/-32022, stdout only JSON-RPC, the map never written; the `spec` and `map` commands). Three of its assumptions were wrong against ADR 0054 and were corrected in the test (a ticket node is named by its id; the fixture's one commit names ticket 0001 and touches every file; the ticket's perimeter covers `pkg/`). `test_light.py`'s unknown-command line updated for ADR 0069 §5.
- **`ci/plugin.sh`** (in `CI_CHECKS` after `gates-light`): the marketplace, manifest, hooks, `.mcp.json` and both `SKILL.md` against the documented fields, version equal to `pyproject.toml`, and `pre-commit.sh`/`skill.sh` on scratch repositories (deny with one stderr line on a weakened test, pass on a clean change, silent without a contract, the resolver's NO-GO with no binary); it first proves it fails on planted cases. `ci/contract.sh` judges the new `spec`/`map` lines.
- **End to end, once, in the pinned Claude Code 2.1.311** with the scripted model (`gates/harness-conformance/stub.py`, a scratch copy with one extra `tool` op for the MCP call), the plugin from a local marketplace directory, the package from a wheel of this branch: `claude plugin validate --strict` passed (one directory warning, `ICON_MISSING`); `marketplace add` and `install` worked; `/lights-out:gates` put `GO: gates-light — risk low, auto-merge; 2 of 10 gates ran; …` in front of the model; Claude Code spoke MCP **2026-07-28** (`server/discover` with `_meta`, then `tools/list`, tools deferred as `mcp__plugin_lights-out_lights-out__*`) and a `tests_for_path` call returned the covering test; the hook stopped a commit that removed an assertion (`PreToolUse:Bash hook error: […] NO-GO: gates-light — test-weakening: …`) and let a clean one through. Recorded in ADR 0069 and `docs/use-on-your-repo.md`. The adapter image could not be built: the podman VM's disk was full (M24's run); Claude Code was installed with `npm ci` from the adapter's lockfile into a host directory and run in the workbench image. Proof script and artifacts in the session scratchpad (not committed).

## What is not proven

- `/lights-out:spec` inside the CLI (only through `skill.sh` in `ci/plugin.sh`); the legacy MCP era against a real client (unit tests only); the `uvx` fallback of the resolver (no package with these commands is on PyPI yet); the plugin on claude.ai or Cowork; Windows.
- An MCP tool call by a real model: the scripted model called the tool by name.

## Contradictions with the plan and the roadmap

- **"The official marketplace by its form" does not exist.** `claude-plugins-official` takes no submissions through Anthropic's directory portal, only through a partner contact. The routes are this repository as its own marketplace, and Anthropic's directory (claude.ai/directory/manage, a paid plan).
- **The map is not at `.crew/map.sqlite` in a user's repository** (roadmap M39 row): `lights-out-gates map` writes inside `.git` (`git rev-parse --git-path lights-out/map.sqlite`), where `git add -A` cannot commit it. From a clone, `--map .crew/map.sqlite` reads `./go map`'s file.
- **The published 0.3.1 package has no `spec`, `map` or `mcp`.** The plugin is at 0.3.1 (it must equal `pyproject.toml`), so until the next release `/lights-out:spec` and the MCP server need `uv tool install git+https://github.com/nicolaguglielmi/lights-out`; `/lights-out:gates` and the hook work with 0.3.1. The docs say so.
- **`main` is the plugin's release channel**: a relative marketplace source has no ref (ADR 0069, Consequences).
- Codex: the page read describes no public directory and no skill hooks, and recommends Codex plugins. Gemini CLI: the `gemini-cli-extension` topic is not on the reference page; Antigravity CLI replaced Gemini CLI for unpaid users on 2026-06-18. Neither is built.
- ADR 0069 supersedes ADR 0054's "No MCP server" (and M28's line in the plan) for a read-only server the client launches.

## What the owner does to list each piece

All in `docs/launch/checklist.md`, "The agent's toolbelt (M39)", unchecked: release the package with the plugin (move the three versions together, PyPI right after the tag); check the own marketplace from `main` on a clean machine (that day starts awesome-claude-code's 14 days); Anthropic's directory with an icon added first; skip `claude-plugins-official` without a partner contact; the MCP registry (`mcp-name` marker in the README, `server.json`, `mcp-publisher`); Codex and Gemini CLI wait for the next slice.

## Merge notes

- One-word conflict likely on the Makefile's `CI_CHECKS` (`plugin` after `gates-light`), and on `docs/PLAN.md` (the M39 entry before `### Dopo`), `docs/launch/checklist.md` (a section before "The README's front page"), `docs/reference.md` (a status row and a section before "Coding harnesses"), `docs/use-on-your-repo.md` (a status row and a section before the hook recipes).
- `core/map.py`'s `open_map` gained a `rebuild` keyword (default `./go map`) and opens the file by a quoted absolute URI.
- Next slice: the Codex skill or plugin and the Gemini CLI extension, the MCP registry entry, the orchestrator recipes.

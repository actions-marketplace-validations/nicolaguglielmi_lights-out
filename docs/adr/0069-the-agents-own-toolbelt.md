# ADR 0069 — The agent's own toolbelt: a Claude Code plugin served by this repository as its own marketplace, and `lights-out-gates mcp`, a read-only MCP server over the project map and the spec gate

- Status: proposed (supersedes ADR 0054's "No MCP server" [§6 and the rejected alternative] for a read-only server the client launches; amends ADR 0061 §5 [the package's commands and its unknown-command line] and §10 [the server's place]; `core/map.py`'s `open_map` names the rebuild command its caller gives)
- Date: 2026-11-10
- Milestone: M39, first slice

## Context

Roadmap K6 asks for lights-out inside the tools people already run. What a
Claude Code user can do today: copy a hook recipe into a settings file
(`docs/use-on-your-repo.md`, ADR 0061 §8), and run `lights-out-gates
--light`. The project map exists only through `./go map`, which needs a
clone of lights-out and the workbench image: a user's own repository cannot
get one without an engine. ADR 0054 refused an MCP server until M24 asked
for it; K6 wants one now, as a discovery channel. This slice builds the
Claude Code plugin and the server. Codex and Gemini CLI are a later slice;
what was verified about them is recorded below, nothing is built for them.

## Verified before writing (2026-11-10)

- **Claude Code plugins** (code.claude.com/docs/en/plugins-reference,
  `/plugin-marketplaces`, `/plugins/publish.md`, `/skills`; no page date;
  this repository pins 2.1.311 in `adapters/claude-code/package.json`). A
  plugin is a directory; `.claude-plugin/plugin.json` is optional, only
  `name` required, kebab-case, `claude-`/`anthropic-` prefixes and
  `claude`, `claude-code` reserved; unknown fields stripped with a warning;
  `version` pins users until it changes. Layout: `skills/<name>/SKILL.md`,
  `commands/` (legacy, "prefer skills/"), `hooks/hooks.json` (top-level
  `hooks` key, settings.json's event shape), `.mcp.json` (`mcpServers`).
  `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_PROJECT_DIR}` resolve in hook
  commands and stdio server command/args/env. Skills are namespaced
  (`/lights-out:gates`; bare `/gates` unless taken). SKILL.md:
  `description`, `argument-hint`, `allowed-tools`,
  `disable-model-invocation`, `$ARGUMENTS`; `` !`cmd` `` runs at load and
  inlines its output, a non-zero exit aborts the invocation, and it obeys
  permission rules unless `allowed-tools` pre-approves it. Marketplace:
  `.claude-plugin/marketplace.json`, `name`, `owner{name}`,
  `plugins[{name, source, description}]`, source a relative path without
  `..`, or `github`, `git-subdir`, url. `claude plugin marketplace add
  <owner/repo|path>`, `claude plugin install <name>@<marketplace>`
  (`--marketplace`, ≥2.1.292); disable or uninstall removes the hooks;
  `claude plugin validate [--strict]` is "the authoritative check", MCP
  entries from 2.1.281; a local-path marketplace loads in place.
- **Distribution.** (a) Own marketplace: a git repository, "no submission
  form". (b) Anthropic's directory, claude.ai/directory/manage: a paid
  claude.ai plan, reaches Claude Code as `<name>@synced`. (c)
  `claude-plugins-official` "doesn't take submissions through the directory
  portal", only through an Anthropic partner contact. **K6's "the official
  marketplace by its form" does not exist as described**: the owner's
  routes are (a) and (b).
- **MCP** (modelcontextprotocol.io/specification, latest revision
  2026-07-28). 2026-07-28 is stateless: no handshake; every request carries
  `_meta` `io.modelcontextprotocol/protocolVersion` and
  `io.modelcontextprotocol/clientCapabilities` (missing: -32602); an
  unsupported version is -32022 with `data.supported`; `server/discover` is
  mandatory; results carry `resultType: "complete"`. Revisions 2025-11-25
  and earlier use `initialize`/`notifications/initialized`; a server MAY
  serve both, an `initialize` selecting legacy for the stdio process. Which
  one 2.1.311 speaks is not documented there. stdio: newline-delimited
  JSON-RPC, nothing else on stdout, logs on stderr, exit on stdin EOF.
  Tools: `tools/list` (deterministic), `tools/call` → `content[{type:
  text}]`; unknown tool or bad arguments -32602; an actionable failure is
  a result with `isError: true`; `annotations` such as `readOnlyHint` are
  untrusted hints.
- **Codex** (learn.chatgpt.com/docs/build-skills, no date): `SKILL.md` with
  `name`, `description` (agentskills.io), in `.agents/skills` or
  `$HOME/.agents/skills`; nothing says a skill declares hooks; no public
  submission process; Codex *plugins* are recommended for distribution.
  K6's "Codex's public directory" is not described.
- **Gemini CLI** (geminicli.com/docs/extensions/reference, updated
  2026-05-14): `gemini-extension.json` (`mcpServers` with
  `${extensionPath}`), `commands/*.toml`, `hooks/hooks.json`, `gemini
  extensions install|link|uninstall`; gallery geminicli.com/extensions/browse.
  K6's `gemini-cli-extension` topic is not on that page. Banner: Antigravity
  CLI replaced it for unpaid and Google One users on 2026-06-18.

## Decision

1. **The plugin lives here; this repository is its marketplace.**
   `plugins/lights-out/` (manifest `name: lights-out`, the fields of the
   list above, nothing else) and `.claude-plugin/marketplace.json` at the
   root (`name: lights-out`, source `./plugins/lights-out`). Install:
   `claude plugin marketplace add nicolaguglielmi/lights-out`, `claude
   plugin install lights-out@lights-out`. The plugin is a distribution of
   the package, not an adapter of a port: nothing in `core/` calls it.
2. **Two skills, both `disable-model-invocation: true`**: the user asks,
   the model never runs the judge on its own. Each is one `` !`sh
   "${CLAUDE_PLUGIN_ROOT}/scripts/skill.sh" <cmd> $ARGUMENTS` ``, pre-approved
   in `allowed-tools`; the skill tells the model to report the line
   verbatim. `skill.sh` always exits 0, so a NO-GO reaches the model.
   `/lights-out:gates [KEY=VALUE …]` is `lights-out-gates --light` with the
   arguments, `STAGED=1` when none are given. `/lights-out:spec <file>` is
   `lights-out-gates spec <file>`. **No full-gates variant** (changed from
   the proposal): the full run takes minutes and an engine, the `!`
   command's time limit is not documented, and the light line already names
   the four gates that need the image.
3. **Which binary, one resolver**, `scripts/run.sh`: `lights-out-gates` on
   PATH when its `version` names the manifest's version; else `uvx --from
   lights-out-gates==<that version> lights-out-gates`; else one line,
   `NO-GO: lights-out — lights-out-gates <version> not found: uv tool
   install lights-out-gates==<version>, or install uv`. An older install
   would answer `spec` with `gates`' refusal and fail `mcp` (`gates_main`
   implies `gates`): the version check exists for that. The manifest's
   `version` equals `pyproject.toml`'s, moved in the release commit.
4. **The hook.** `hooks/hooks.json`: `PreToolUse`, matcher `Bash`, timeout
   30 (the recipe's: three times the light tier's 10 s, ADR 0061 §8),
   command `sh "${CLAUDE_PLUGIN_ROOT}/scripts/pre-commit.sh"`. It does what
   the recipe does: nothing unless stdin holds `git commit`; then
   `lights-out-gates --light STAGED=1`, exit 2 on NO-GO. It acts only where
   the committed HEAD has `.lights-out/workload.env`, the contract the
   light tier reads under `STAGED=1`: elsewhere it exits 0, silent, or a
   user-scope plugin would block commits in every repository. On a deny,
   stderr holds exactly one line, the gates' (their own stderr is dropped;
   the user reruns the command for details). A missing binary in a
   repository with a contract denies with §3's line: the judge was asked
   for and is absent, never skipped silently. Disable or uninstall removes
   it; the plugin writes nothing into the repository or the settings.
5. **Three package commands, stdlib only**, dispatched by `gates_main`
   before it implies `gates`; the unknown-command line lists them.
   `lights-out-gates spec <file>`: `GO: spec` or `NO-GO: spec — <reason>`
   (`spec.check`), as `gates/spec.sh`. `lights-out-gates map [--repo DIR]
   [--out FILE]`: `map.build` at HEAD, tickets `.lights-out/tickets` when
   that commit has it else `tickets`, no `make` targets and no exclusions,
   one line as `./go map`'s. `lights-out-gates mcp [--repo DIR] [--map
   FILE]`: the server. From a clone, `python3 -m core <cmd>`.
6. **Where the map is, changed from `.crew/map.sqlite`.** Default `git
   rev-parse --git-path lights-out/map.sqlite`, inside `.git`, one per
   worktree. In a user's repository `.crew/` is not ignored: an agent's
   `git add -A` would commit a binary. In this checkout, `--map
   .crew/map.sqlite` reads `./go map`'s file.
7. **The server, `core/mcp.py`.** stdio, both eras: an `initialize`
   selects legacy for the process and is answered with `2025-11-25`;
   otherwise every request follows 2026-07-28 (`server/discover`,
   `_meta` checked, -32022 naming both versions, `resultType`). Four
   tools in this order, each `readOnlyHint: true`, one string argument:
   `adrs_for_path(path)` (ADRs, then pages, citing it: `covered()`),
   `tests_for_path(path)` (`tests` edges to it, or itself if a test),
   `tickets_for_path(path)` (`perimeter`, `history` edges, with their
   kind), `check_spec(text)` (§5's line; a NO-GO is an answer, not an
   error). Answers are text: the map's sha, then sorted lines, `none` when
   empty. Every call runs `open_map(file, HEAD)`: missing, stale or
   other-schema maps are `isError` with the refusal naming both shas and
   `lights-out-gates map`. A path outside the repository or not in the map
   is `isError`; an unknown tool or bad arguments -32602; an unknown method
   -32601 (JSON-RPC 2.0). It starts with no map, opens `mode=ro`, never
   rebuilds, and uses `map.git` for HEAD: no new process-call site, no
   network, engine, plane or model. `.mcp.json`: command `sh`, args
   `["${CLAUDE_PLUGIN_ROOT}/scripts/run.sh", "mcp", "--repo",
   "${CLAUDE_PROJECT_DIR}"]`.
8. **Why 0054's refusal no longer holds here.** It refused a process per
   run in the plane and a protocol each harness speaks differently. This
   one is launched by the user's client, per session, outside the plane;
   one protocol. M24's question stays open: no adapter configures the
   server, `MAP_BRIEF` stays the workers' path, and 0054's text is not
   edited.
9. **Tests from this ADR.** `core/tests/test_mcp.py`: the three answers on
   a map built at a fixture commit; stale, missing and other-schema maps
   refused; a path outside; unknown tool, method and version; both eras;
   stdout only JSON-RPC lines. `core/tests/test_light.py` grows the
   `spec`/`map` commands; `ci/contract.sh` their line shapes. `ci/plugin.sh`
   (gate contract): the three JSON files and two SKILL.md against the
   listed fields, kebab-case and non-reserved names, `./` paths that exist,
   manifest version equal to pyproject's; `pre-commit.sh` on scratch
   repositories with a PATH shim (deny with one stderr line on a weakened
   test, pass on a clean change, silent without a contract, §3's line with
   no binary). `claude plugin validate --strict` is not in `./go ci`: the
   CLI is in the claude-code adapter image, not the workbench
   (`workbench/Containerfile` has node, not Claude Code).

## Alternatives rejected

- **A separate marketplace repository as the source.** Two places to align
  each release. One later, with a `git-subdir` source here, costs a commit
  there per release, or serves unreleased `main`.
- **The repository root as the plugin.** A root `.mcp.json` is also Claude
  Code's project server file: this repository's own sessions would load it.
- **Project `.claude/` config, or `commands/`.** Not installable elsewhere;
  legacy.
- **A `gates` MCP tool.** The model would iterate against the judge until
  GO; the judge stays user-invoked (skills) or enforced (hook).
- **A legacy-only server.** The proof cannot tell in advance which era
  2.1.311 speaks, and 2026-07-28 is the revision clients move to.
- **`structuredContent`.** A second answer shape to test; text suffices.
- **The map under `.crew/` or a user cache.** §6; a cache keyed by path
  outlives the repository.

## Consequences

- **The one that will hurt: `main` is the plugin's release channel.** A
  relative source has no ref: a new install gets `main`'s scripts under
  the last version, and a release commit whose version PyPI does not yet
  hold sends `uvx` users §3's NO-GO until the upload. The checklist puts
  the PyPI upload right after the tag; `ci/plugin.sh` checks the versions.
- Version lockstep across `pyproject.toml`, the manifest and the wrapper
  (ADR 0061); the SKILL.md files are pages, so `docs-drift` judges them.
- A user with the hook recipe and the plugin runs the gates twice: the
  page says to drop the recipe.
- `lights-out-gates map`'s rows differ from `./go map`'s (no `command`
  nodes, no `MAP_EXCLUDE`): plan pages count as covering pages here.
- The first `uvx` start downloads the package; uv's own output staying off
  stdout is for the proof to show.
- `core/mcp.py` joins the self gate's mutation scope: `./go ci` and the
  self gate grow.
- Codex, Gemini CLI, the MCP registry and the orchestrator recipes are not
  built; the directory listing (b) is the owner's act.

## End-to-end proof (2026-11-10, once)

The pinned 2.1.311 (`adapters/claude-code/package-lock.json`, installed
with `npm ci` into a host directory and run in the workbench image: the
podman VM's disk was too full to build the adapter image), with
`gates/harness-conformance/stub.py` as the model, the package installed
from a wheel of this branch (`uv tool install`, version 0.3.1, so the
resolver took it from PATH), the plugin from a local-path marketplace on a
scratch repository with a contract. Result:

- `claude plugin validate --strict` on the plugin and `claude plugin
  validate` on the marketplace: passed. One directory warning,
  `ICON_MISSING`, outside the verdict (the owner's checklist).
- `claude plugin marketplace add` and `claude plugin install
  lights-out@lights-out`: installed, enabled, version 0.3.1, read in place.
- `claude -p '/lights-out:gates'` on a clean staged change: the request to
  the model carried `GO: gates-light — risk low, auto-merge; 2 of 10 gates
  ran; …` inside the skill's text.
- MCP: 2.1.311 spoke the modern era. Its first message was
  `server/discover` with `_meta` protocolVersion `2026-07-28`, then
  `tools/list`; the four tools reached the model as deferred tools
  (`mcp__plugin_lights-out_lights-out__…`). A `tests_for_path` call on the
  module (through `ToolSearch`, then the tool; the stub's copy had one
  extra op, `tool`, for this proof only) returned `Tests: - tests/test_add.py`
  at the map's sha to the model.
- The hook, with this file's final `hooks.json`: a staged change that
  removed the test's assertion was stopped. The model received
  `PreToolUse:Bash hook error: […]: NO-GO: gates-light — test-weakening: …`
  and no commit landed; a clean staged change committed.
- Not run in the CLI: `/lights-out:spec` (proven by `ci/plugin.sh` through
  `skill.sh`), the legacy era (unit tests only), the `uvx` fallback.

## Golden-rule check

`./go demo` gains nothing on its path. `./go ci` gains a unit file and
`ci/plugin.sh`: no engine, network or key. Nothing vendor-specific enters
`core/`: MCP is a protocol three CLIs speak; the plugin stays under
`plugins/`. Passes.

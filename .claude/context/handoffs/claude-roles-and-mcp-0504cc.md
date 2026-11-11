# Handoff: M42, a repository customizes its agents (ADR 0073), 2026-11-11

Branch `claude/roles-and-mcp-0504cc`, cut from 98f49e8 (`fix/adr-still-header`, which holds M39). No pull request, not merged, no tag. M42 because M36–M41 are reserved by the adoption roadmap; ADR 0073 because 0070–0072 are held.

Asked by a developer testing the product (owner, 2026-11-11): how far can it be customized, "connectors like MCP", "agents with custom instructions". The answer, for the developer, is `docs/use-on-your-repo.md#agents`.

## What landed

- **ADR 0073** and **M42 in `docs/PLAN.md`** (acceptance criteria) committed before the code (d9a9064). Verified CLI facts at the pins (Claude Code 2.1.311, Codex 0.166.0, Gemini CLI 0.61.0-preview.0) in the ADR's "Verified" section: from docs, the pinned Claude package, and the Codex/Gemini sources at their tags; nothing executed for the ADR.
- **Role instructions, reviewers only**: `<contract>roles/test-reviewer.md` and `roles/architect.md`, read by `core/steps/review.sh` at `BASE_SHA` in the review's own clone (never the head, never the local contract), put in the reviewer's input after the ticket with a platform heading and the verdict contract restated after the diff. Refused in one line before any model call: `dev-worker.md` (points to `worker.md`), ADK roles, unknown names, non-UTF-8, over 3,072 bytes (below both reviewer prompts, measured), a line that starts with a verdict token. Recorded in the review entry as `instructions: {file, sha256, base}`.
- **`<contract>mcp.json`, dev-worker only**: every tool named, at most 4 servers / 16 tools, stdio runs in the harness container with no env, remote only `https` with explicit port and only to a `host:port` in the base's `crew-egress.txt`, token by name `MCP_*` only; read by `core/crew.sh` from the commit the attempt forks from. One vendor-free module, `core/agents.py` (check, instructions, mcp, calls, lines, gate, plus `crew`/`review` verbs that keep the two steps under their ADR 0052 line debts). Per-harness translation in `adapters/<h>/mcp.sh` (claude-code, codex, gemini-cli; replay compares the declaration's digest with the recording's). A harness without `mcp.sh` (antigravity-cli, adk) refuses in one line. The guard (byte-identical copies) denies unnamed `mcp_*` tools and `MCP_*` names; `run.json` gains `mcp` (servers, `unlisted`, calls and denials counted from `hooks.log`). Claude Code at 2.1.311 cannot hide an unnamed MCP tool: visible and denied (`unlisted: visible-denied`).
- **Shown the same way**: `./go agents` (one gate line, the lines on stderr), the console's Thresholds screen "Agents" panel (logbook 1.3, `agents.lines`), and the ticket's back ("MCP: notes.search_notes ×1", "Reviewer instructions: …"). `lights-out init` drafts neither file, one stderr line points to the docs.
- **Fixture**: `workloads/minimal/.lights-out/mcp/notes.py` (stdio, stdlib, both MCP eras, `search_notes` and `count_notes`) declared by `workloads/minimal/.lights-out/mcp.json` with `search_notes` only.
- **Conformance case 10** in `gates/harness-conformance.sh` (role marker order, the MCP call through each real CLI against the scripted stub, only the named tool callable, `run.json` records it, a server that does not start fails the run, antigravity refuses); `proof.sh` proves the suite can fail it (fifty-four planted defects).
- `RISK_HIGH_PLATFORM` gains `*mcp.json` and `*roles/*.md`. Two pre-existing `run.sh` bugs fixed on the way: a missing transcript doubled jq's fallback into invalid JSON (hid a container that never started).

## How it was built

LLM-heavy work ran as headless `claude -p` on the owner's `ANTHROPIC_API_KEY` credits (owner's request, 2026-11-11), about $45 in all: the ADR draft and CLI verification (Opus), then four parallel runs on disjoint files (tests from the ADR without the code, the vendor-free core, the adapters and case 10, the docs), then the proof and the ticket's back. The session kept the decisions, review, integration and commits. Tests (94f3a52) were committed before the implementation (2deaadd).

## What is proven

- `./go ci` from a clean clone under `.crew/`: GO on 2deaadd (13:50) and on 07c0aad (8:16). On 4338d76 (a one-line run.sh fix) the first run stopped on the podman VM's disk (`No space left on device` in ci-logbook, not this code); see the retry's result below.
- Engine-free checks GO: agents, review (cases i–m), hooks, harness-shape, harness, network, tower, app-free, model-free, vendor-free, docs-drift, shell-boundary; 781 unit tests.

## What is not proven

- **The live run with Claude through the claude-code harness.** Two attempts (scratchpad `live.sh`: the real `adapters/claude-code/run.sh` on `workloads/minimal` as its own repository, the real API) never started the container: the claude-code image build fails writing its last layer on the VM (1.3–1.6 GB free, 23 GiB disk; 37 dangling images pruned with the owner's OK freed only 1 GB). The owner can grow the disk (`podman machine stop podman-machine-new; podman machine set --disk-size 60 podman-machine-new; podman machine start podman-machine-new`, with nothing else running). Then: from a clean clone, export the key in the process environment only and run `./go shell < live.sh`.
- Case 10 on GitHub Actions: pending the push (below). Codex's MCP surface under code mode and its stub rendering are a guess the job will confirm or refute; Codex's and Gemini's failure strings for a server that does not start were read from source, never seen live.
- Remote MCP servers: unit translation only (the stub is plain http). gemini-cli takes stdio only. The check reads the base's `crew-egress.txt`, the proxy still reads the local contract (ADR 0073, Consequences).
- `ci/logbook.sh`'s LIVE-mode POST cases fail on this macOS host (403) at clean HEAD too; GO inside `./go ci`.

## Merge notes

- Expected conflicts: `docs/PLAN.md` (a new M42 section before "### Dopo"), `Makefile` (`agents` target, `CI_CHECKS` gains `agents` before `plan`), `go` header, `core/logbook.py` and the 1.3 golden (logbook 1.2 → 1.3, `golden-1.2.json` removed, readers repointed), `console/index.html`, `ci/console-ui.py` (new case `t_agents`), the four `guard.sh` copies, the three CLI `run.sh`/`entrypoint.sh`.
- Another branch that bumps the logbook to 1.3 must be reconciled by hand.

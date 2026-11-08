# Adoption roadmap: what makes lights-out get used, shared and starred

- Date: 2026-11-08
- Scope: the repository at `fix/adr-still-header` (761450f, M33 built, six workflows green on c387961), [PLAN.md](../PLAN.md) §14–§16, [ROADMAP.md](../../ROADMAP.md), the [assessment of 2026-11-03](assessment-and-must-have-plan.md), the [launch checklist](../launch/checklist.md), the first outside feedback (2026-11-06) and a market pass on the adjacent open-source projects (section 3).
- Author: Claude Code, for the owner. Every target number here is a proposal, not a measurement; the owner sets the real ones before launch (plan §15, "Cosa si misura").
- Question answered: which features move adoption, diffusion and GitHub stars for a framework people pick because it is useful end to end, from the request to production and back; what to change, what to drop, what to add; in what order.

## 0. The verdict in ten lines

1. The product is deep and honest, and almost nobody can reach it. Fifty-seven ADRs, eight gates, a canary that rolls itself back, a console: all behind a 1.8 GB image, a 14-minute demo and a podman machine with 6 GiB. Four days public: 6 stars, 23 unique visitors, 0 issues, 0 discussions. Expected before a launch, and the launch is the point of this document.
2. The differentiators are real and nobody else ships them together: `test-proof` (a new test must fail on the base), `test-weakening`, mutation on the changed lines, a per-ticket file perimeter, a PR judged by its base's policy, main kept green by bisect and revert, and a rollback with nobody paged. Section 3 says who comes close: five repositories reinvented `test-proof` internally in the last sixty days, none as something you can install. The window for shipping it standalone is open and closing.
3. The hook the plan chose, the rollback of an agent's change, is the hardest thing to adopt and the easiest to watch. It stays the GIF; it stops being the front door.
4. The front door becomes the judge for agent pull requests: the Action and the wrapper, slim, on the GitHub Marketplace, with a verdict people read. The pain is already here, with Copilot, Codex and Claude Code opening PRs in every team.
5. Two features nobody has and lights-out can have in a quarter: an attestation of what the agent did (harness, model, tokens, perimeter, gates, human GO) attached to the merge, and the closed loop in one command: alert → triage → ticket → agent PR → gates → canary → GO.
6. Drop the Google-shaped internals from L0: the Pub/Sub and Firestore emulators and the Gitea Actions runner buy nothing for a laptop and cost two services, pull time and the flakiest minutes of the demo. The cloud profiles stay designed, parked, and out of the first screen.
7. Freeze the console after M33. It is a view, it is good, and it moves no adoption until an outside team runs the plane.
8. Spend the shell debt where contributors hit it first: `ci/` (10k lines) and `gates/`, under ADR 0052, as a standing slice of every milestone.
9. Distribution is a feature. A Claude Code plugin, a Codex skill, a Gemini CLI extension, an MCP server over the project map and the spec gate, the Action on the Marketplace, awesome lists: each is a day or two and each is a place people look. And the orchestrators with 100k stars (Paperclip, OpenHands, Gas Town) have a verification step and no judge: be the gate they call, not a rival.
10. Sequence: make the front door light and true (Now), ship the two features nobody has and the public experiment's numbers (Next), then widen stacks and adapters by demand (Later). One Show HN, after M24, with the loop in one GIF.

## 1. Where the repository stands, measured

| | 2026-11-08 |
|---|---|
| Public since / stars / forks / watchers | 2026-11-04 / 6 / 0 / 0 |
| Traffic, 4 days | 78 views, 23 uniques; 1709 clones, 135 uniques (CI clones included) |
| Referrers | github.com (5 uniques), the site (5), Telegram (1) |
| Issues / Discussions (on) / outside PRs | 0 / 0 / 0 |
| Releases / image | v0.1.0, v0.2.0 tagged; `ghcr.io/nicolaguglielmi/lights-out:0.2.0` public, 1.77 GB unpacked |
| Commits / ADRs / `./go` targets / workflows | 375 / 57 / 57 / 8 |
| Tracked code | sh ≈ 19.4k lines (ci 10.0k, adapters 4.1k, gates 2.8k, core 1.9k), py ≈ 16.0k (core 11.9k) |
| `./go demo`, clean clone, Actions | 834 s and 828 s on c387961, budget 900 s: one minute of margin |
| Plane at L0 | envoy, prometheus, flagd, zot, gitea, runner, pubsub-emulator, firestore-emulator, egress, dns, the harness containers, crew |
| Stacks | Python (cosmic-ray, bandit), JavaScript (Stryker, eslint-plugin-security) |
| Proven on a codebase not written for lights-out | not yet (M24, sqlparse chosen 2026-11-05) |
| Claude and Codex recordings committed | no (owner's keys); claude-code ran live once, stopped by mutation |
| End to end on GitHub as code host | not run (owner's token) |

What the numbers say: the repository has not launched, by design (plan §15 puts Show HN after the experiment). The traffic is friends and the site. Nothing here is a verdict on the product; it is the baseline the launch is measured against.

## 2. The funnel, and where it leaks

A developer tool gets stars when six steps each take less than the step before gave back.

| Step | What a stranger needs | lights-out today | Leak |
|---|---|---|---|
| Discover | a marketplace, a list, a post, a search phrase | topics set; not on the GitHub Marketplace, no plugin, no MCP server, no awesome list, no post | nobody arrives who was not sent |
| Understand in 10 s | one sentence in the words they search | "the safety system for a dark factory" is a brand, not a search phrase; the searched one is "CI gates for AI-written PRs" | the brand needs a second sentence it does not get |
| Believe in 60 s | a real recording | a JPG, and a loop rendered from the board with example numbers; the 60 s rollback recording of plan §15 phase 0 is still not done | the strongest asset, the honesty section, sits below the fold |
| Try in 5 min | something on *their* repository or in the browser | step 1 needs podman or docker and a 1.8 GB pull; step 2 needs a clone, 6 GiB and 14 min; nothing runs in a browser | most strangers stop here |
| Adopt | the tool they already use | the Action exists, proven on lights-out's own PRs only; hook recipes for Codex and Gemini CLI unverified against the CLIs; Python and JavaScript only | the Action is the product and is not sold as such |
| Contribute | a change they can test | 19k lines of shell, 10k in `ci/`; eight good first issues drafted, none opened; the demo needs a machine most laptops are not | the first outside feedback named exactly this |

The repository built the inside of the funnel first, on purpose (plan §7: safety net, then gates, then workers). The roadmap below builds the outside.

## 3. The landscape, and the gaps that are still open

Star counts read on GitHub on 2026-11-08 unless dated otherwise; "unverified" means one secondary source. The full pass, with URLs, is the research note this section condenses.

### 3.1 Who is near, and what each side has

| Project | Stars | What it is | They have, lights-out lacks | lights-out has, they lack |
|---|---|---|---|---|
| DeepSeek Harness, OpenCode, Claude Code, Codex CLI, Gemini CLI | 276k, 225k, 155k, 134k, 109k | the coding harnesses | distribution by `npx` and plugin marketplaces; UIs | anything after the PR. These are lights-out's inputs, not rivals. Note: Gemini CLI moved free, Pro and Ultra users to Antigravity CLI on 2026-06-18; the free L1 path by API key must be re-verified |
| OpenHands | 93k | pivoted to "Agent Canvas", a self-hosted control center running Claude Code, Codex, Gemini and others on schedules and webhooks; hosted tier | multi-harness control center | gates, perimeter, canary, the no-key demo |
| Paperclip | 112k (62.7k in May 2026) | ticket-based orchestration, atomic task checkout, budgets that pause work, configurable approval stages, heartbeats | the org-chart UX, budgets, a 100k brand | numeric gates, mutation and test-proof, canary and rollback, the perimeter |
| Gas Town | 18.7k | 20–30 agents, git-backed issues, a Bors-style merge queue with verification gates, watchdogs | the merge queue at fleet scale | post-merge delivery, gates as a contract, the no-key demo |
| no_human | 320 | the closest pipeline: acceptance criteria → implement → tamper check (deleted tests, skips, tautological asserts) → second-model review told to refute "done" → **a reproduction gate: the fix's test must fail on base and pass on head** → PR; never merges; Anthropic models only; no deploy | tracker integrations (Jira, Linear, monday), Slack and Teams | multi-provider, canary and rollback, mutation, the perimeter, the local run |
| Chock | 10 | "governance-as-code for coding agents": one policy compiled to git hooks, a CI gate, pre-tool hooks for about 15 agents; `protect-test-integrity`; a baseline step that fails a PR weakening a policy | hooks for fifteen agents from one file | mutation, canary, a per-task file scope, the delivery chain |
| Microsoft Agent Governance Toolkit | about 6.5k | runtime governance mapped to the ten OWASP agentic risks | the OWASP mapping, a Microsoft name | PR gates and delivery; different layer |
| Governance tooling at large (awesome-ai-agent-governance, MCP gateways, OpenAI's governance cookbook, Codex `requirements.toml`) | — | pre-tool-call interception, signed receipts, hash-chained audit, gateways with CEL or YAML policy | breadth of hooks and receipts | nobody frames governance as **numeric PR gates plus delivery**; that lane is empty |
| Spec-driven kits: Superpowers, Spec Kit, OpenSpec, BMAD | 314k, 149k, 74k, 55k | methodology as skills and prompts; Superpowers is on the official Claude **and** Codex marketplaces with install paths for 14 harnesses | install in seconds, zero infrastructure, marketplaces | enforcement. They ask the agent to behave; RepoComplianceBench (arXiv 2607.26819) found agents almost never read a repository's AI rules and never refused in AI-banned repositories |
| Sandboxes: Anthropic sandbox-runtime, microsandbox, E2B; Daytona archived | 7k, 9k, 14.8k; 71k archived | process and microVM isolation | isolation primitives | none decides whether a change ships; lights-out can consume one for the dev-worker rather than compete |
| AI code review: CodeRabbit, Greptile, Qodo (pr-agent 15.5k), Cursor Bugbot, Copilot review | — | LLM review comments on PRs; an independent 118-bug bench put Greptile's catch at 23.6% against a vendor claim of 82% | PR UX, IDE presence | deterministic gates; review is one gate here, not the product |
| Progressive delivery: Argo Rollouts, Flagger, Kargo; Keptn dormant | 3.6k, 5.4k, 3.8k | traffic shifting, analysis, indefinite pause until a promote, `confirm-promotion` webhooks | mesh and ingress integrations, maturity | the chain from the ticket; nothing found that does agent → PR gates → canary → metric-judged rollback end to end |
| GitHub Agentic Workflows (gh-aw), Copilot coding agent, Agent HQ | 5.6k; proprietary | Markdown → Actions, read-only default, sandboxed job, "safe outputs" in scoped jobs, `gh aw audit`; Agent HQ's mission control and policy plane | first-party trust, the platform | no file-path policy for what an agent may change, no numeric gate contract, no delivery stage |
| Mutation tools: Stryker (js 3.3k, .NET 2.1k), PIT 1.9k, mutmut 1.5k, cosmic-ray 664 | — | thresholds, incremental runs against the last report | tooling per language | changed-line mutation against the **merge base** as a PR gate exists only as one repository's internal Go tool (OpenRAE, 2026-11-02) |

### 3.2 The seven gaps, checked

| Claim | Verdict |
|---|---|
| (i) a per-ticket file perimeter enforced on the PR diff | **open.** Closest: a "diff budget" blog recipe, OpenCode's open request for per-agent paths, Claude Code's static `Edit(./src/**)` rules, file leases in two CLIs. All runtime or static; none derives the perimeter from the ticket and fails the PR in CI |
| (ii) the new test must fail on the base | **half open, closing.** Five home-grown gates in the last 60 days (no_human, OpenRAE, vibe-verifier, GoldStandard, factory), none reusable. Ship `test-proof` standalone before someone does |
| (iii) mutation score as a merge gate on agent PRs | **mostly open.** One internal tool does changed-line mutation; an AWS sample keeps it nightly; the merge-base scoping is the unsolved piece, and lights-out already has it |
| (iv) a no-key replay demo of the pipeline | **open at the pipeline level.** VCR libraries for LLM calls are a commodity (seven found); no harness or orchestrator ships clone → replay → rollback with no key |
| (v) a canary judged on OTel semconv metrics, wired to an agent pipeline | **open.** Argo analysis templates in the wild use legacy Prometheus names; Keptn's OTel evaluations are dormant |
| (vi) a human GO before 100%, silence never promotes | **not a gap at the delivery layer.** Argo's indefinite pause and Flagger's `confirm-promotion` have the same semantics. The claim is "the single human gate of a ticket-to-production chain"; say reuse, not invention |
| (vii) a PR judged by its base's policy, never its own | **primitive exists, principle unstated.** GitHub takes `pull_request_target` from the default branch (since 2025-11-07) and pins ruleset workflows; Chock fails policy-weakening PRs. No framework states it as a rule: name it in the README and link the changelog |

### 3.3 What moves stars, measured

- Launch-day diffusion over 138 AI-tool launches (arXiv 2511.04453): Hacker News exposure is worth about +121 stars in 24 h, +289 in a week; the hour matters, the "Show HN" tag itself does not.
- Show HN over 188k posts (April 2026): about 1.4 stars per point within 48 h, 92% of the gain inside 48 h; best slot Monday 00:00 UTC, worst Thursday 06:00 UTC. Plan §15's "Tuesday to Thursday, US morning" is contradicted by the data; prior momentum predicts more than the post.
- Marketplaces are the 2026 multiplier: Superpowers 314k on two official marketplaces, Spec Kit 149k with one `uv tool install`, DeepSeek Harness 276k while in preview via `npx`, Paperclip 62.7k → 112k in six months, awesome-mcp-servers 97k, awesome-claude-code 57.5k. Everything that installs in seconds with zero infrastructure wins; the Compose, Envoy and Gitea plane is the adoption tax.
- Patterns from a 0→10k study (unverified method): the README sells in under seven seconds, "X without Y" framing, one install and one run command, a browser try-it link, awesome lists, every issue answered within 24 h.
- Language: no causal study. asdf rewrote Bash to Go citing a codebase "hard to change"; Octoverse 2025 frames typed languages as guardrails for AI-written code. Shell will be read as a contribution barrier, not a star barrier.
- No leaderboard measures gated correctness: Terminal-Bench and SWE-bench rank harnesses. A vacancy for K8.
- AI provenance is unsettled: the kernel's `Assisted-by:` tag adopted in April and reportedly dropped in October (unverified), QEMU replacing a ban with an `AI-used-for` tag, squash merges turning Claude's author line into a trailer. Nobody checks "under what policy was this AI change produced".

### 3.4 Distribution channels and their rules

| Channel | Rule that matters here |
|---|---|
| GitHub Marketplace, Actions | public repository, **one `action.yml` at the repository root**, unique name, 2FA; publishes immediately, no review. lights-out's `action/action.yml` is in a subdirectory: move it or make the Action its own repository |
| Claude Code official marketplace | `.claude-plugin/plugin.json`, immutable name, a submission form; or an own marketplace repository users add with `/plugin marketplace add` |
| Codex plugins | identity and domain verification, OpenAI review; **hooks must be removed** for the public directory, so the pre-commit hook is installed by a command the skill offers, not by the plugin |
| Gemini CLI extensions | public repository, topic `gemini-cli-extension`, `gemini-extension.json` at the root; crawled daily, automated validation only |
| MCP registry | reverse-DNS namespace, the package on npm or PyPI first, `mcp-publisher`; free, no review. The PyPI package of K2 serves this too |
| awesome lists | awesome-claude-code: issue form, the resource at least 14 days old with activity or 100 stars, one at a time; natural homes today: awesome-agent-orchestrators ("Autonomous Task Runners"), awesome-ai-agent-governance, awesome-cli-coding-agents |
| Homebrew | core needs 75 stars and 30 forks; an own tap has no bar |
| CNCF landscape | 300 stars; later |
| GHCR | storage and bandwidth free today; Docker Hub's open-source program needs an OSI licence and activity, no paid subscription |

## 4. What to drop or shrink

Each item follows the rule in CLAUDE.md: before adding, see what can go.

| Drop or shrink | Why | How | Risk |
|---|---|---|---|
| **The Pub/Sub and Firestore emulators at L0** | They exist so L0 shares code with an L2/L3 that is designed and not run (ADR 0022). On a laptop they are two services, two pulls and two readiness probes for a state store whose verbs are `get`, `put`, `delete` and an event bus nobody consumes across processes (`Orchestrator=inproc`). | A `sqlite` StateStore (one file under `.crew/`, same three verbs) and an `inproc` EventBus, default at L0 and L1. `firestore` and `pubsub` stay in the §4 table for the cloud profiles. One ADR, the adapter conformance as the proof. | The tower documents survive `./go down` for free (the old M13 ask). Risk: none at L0; L2 keeps its adapters. |
| **The Gitea Actions runner in the demo path** | ADR 0039 already limits it to the `image` job; the handoffs record it as the flake and the 300 s wait `e2e` pays. The attached-repository path already builds the merge in a worktree with `make publish` (ADR 0043 §4). | The bundled app's release takes the same path as an attached repository's; the `runner` service leaves the L0 compose; `demo` loses its slowest wait. | Gitea Actions was also "the same YAML runs locally and on GitHub" (plan §3). That promise is served by `.github/workflows/` running on GitHub; keep the runner behind an opt-in profile knob if anyone asks. |
| **gcloud and terraform in the base image** | ADR 0028 decided they leave the base for a `workbench/cloud` flavour; the flavour was never built (M28 found the drift) and `workbench/Containerfile` still fetches both (about 470 MB, the M7 measure). Every stranger who pulls the 1.77 GB image pays for two tools no L0 or L1 path runs. | Take them out of the base now, one commit, before any new image is published; the cloud flavour is written the day L2 is. | None at L0/L1; `./go up PROFILE=l2` already cannot run. |
| **The Google cloud track on the first screen** | `infra/`, L2 and L3 are designed, never run, and read as "a Google demo" to a stranger. The repository's own ADR 0029 says the stack is an optional target, not the identity. | Keep the directories, one paragraph in `docs/reference.md` ("designed, not run, built when someone pays"), nothing in the README or the site. `docs/ARCHITECTURE.md` lists the cloud adapters in one row. | None. |
| **`antigravity-cli` on the front page** | Proprietary binary, experimental, Gemini only, a hole recorded open (ADR 0050 §7). | Stays in `adapters/` and in the reference; leaves the README table and the site's "at the keyboard" row until a live run passes the gates. | None. |
| **The console's scope** | M29 and M33 made it a workbench: kanban, specs, an editor, ADR search, themes. It is good. The assessment of 2026-11-03 and the funnel above agree that it moves no adoption until an outside team runs the plane. | Freeze after M33. New screens only when a user who is not the owner asks. Keep `ci/logbook.sh` and `console-ui` green. | The owner likes building it. Say so, and say it waits. |
| **Shell where logic lives** | 19.4k lines of shell against 16k of Python; `ci/` alone is 10k. The first outside feedback (2026-11-06) named it. ADR 0052 drew the boundary and moved `core/`; `ci/` and `gates/` are next on its own list. | A standing slice in every milestone: one `ci/*.sh` or `gates/*.sh` with logic moves to Python with unit tests from its ADR; the one-line gate contract and `ci/lib.sh` stay. Target a number the owner picks (proposal: `ci/` under 5k lines by the end of the Next horizon). | None to users; the demo's `ci` stage can only get faster. |
| **The demo's 900 s budget as the only time** | 834 s on Actions today. The promise is "under 15 minutes"; the margin is a minute. | The two drops above buy minutes. Add a second measured time to the README: `./go up && ./go demo-rollback`, the one-minute path, with the plane download stated apart. | None. |

Not dropped, said on purpose: the six roles, the signed image at L0 (it is a differentiator), the one-line gate contract, the replay at L0 (the golden rule), Apache 2.0 and the DCO.

## 5. What to change

| Change | Today | Proposed |
|---|---|---|
| **The README's first screen** | headline, a JPG, a table of eight capabilities, then five ways in | a 60 s terminal recording of a real `./go demo-rollback` (asciinema, rendered to GIF in CI from a real run, never drawn), then two lines: the Action for your PRs, the clone for the whole loop. The capability table moves under the recording. "What is real and what is recorded" stays on the first screen as one line with the link. |
| **The GitHub description** | "Governed autonomy for AI coding agents: six numeric gates, …" (it says six; the README says eight) | "CI gates, a per-ticket perimeter and a canary that rolls itself back, for code written by AI agents (Claude Code, Codex, Gemini CLI). One line, GO or NO-GO. Runs on your laptop, no API key." |
| **The Action** | `nicolaguglielmi/lights-out/action@v0.2.0`, check run with the one line, proven on this repository; `action.yml` in a subdirectory, which the Marketplace does not list | `action.yml` at the repository root (or the Action in a repository of its own), listed on the GitHub Marketplace; a floating `v1` major tag once the contract is cut (below); the check run's summary carries one line per gate with the reason and, for a NO-GO, the surviving mutants or the file outside the perimeter; on fork PRs the job status already carries the verdict |
| **Claim reuse where it is reuse** | the README presents the human gate and "judged by the base's policy" as lights-out's | the human gate "has Argo Rollouts' indefinite pause and Flagger's confirm-promotion semantics, as the single human gate of the chain"; the base-policy rule "is what GitHub does for `pull_request_target` since 2025-11-07, stated as a rule for every gate", with the links. Reviewers on Hacker News check this first |
| **The gates contract, versioned** | `workload.env` has twelve keys, the Action and the wrapper read the base's contract (ADR 0033, 0045) | cut `v1.0.0` of the contract (the twelve keys, the one-line output, the three toolchain forms) when the third stack lands; after that a key is added, never renamed, without a major. A stranger adopts an Action whose contract is promised. |
| **`init` and the copy step** | `init` drafts outside the repository and the README warns about `cp -R` and the trailing `/.` | `lights-out init --into .` writes the draft into the repository on an explicit flag, prints the diff it would commit, commits nothing. The default stays the draft outside. |
| **Hook recipes** | Codex and Gemini CLI shapes "not verified against the real CLIs" | run each recipe once in `./go harness-conformance` against the real CLI with the scripted model, and say "verified" or "not" per CLI in the guide |
| **The search phrase** | the site's title is the brand | the site's `<title>` and first paragraph carry the brand and the searched phrase both; the OpenGraph image is the rollback frame |
| **The Try path for people without an engine** | none | a `.devcontainer/` and a "Run the demo in Codespaces" badge; measure once whether the 4-core machine reaches `GO: demo`, and say the measured machine size in the README |

## 6. What to add: the killer features, ranked

Ranked by (adoption pulled) × (uniqueness) ÷ (cost at 5–15 h/week). Each is one milestone with its ADR, its acceptance line, and `./go demo` still green under budget.

### K1. The judge for agent pull requests, as the front door

What it is: the gates-only image, slim, as the product people install first. Today the wrapper runs the full workbench (1.77 GB) with the harness CLIs, kubectl, terraform and gcloud inside. The gates need git, the stack's runners and five binaries (gitleaks, osv-scanner, cosign for nothing here, shellcheck, actionlint for nothing here).

Why it pulls: every team now receives PRs from Copilot coding agent, Codex and Claude Code; the question in the review is "did its tests test anything, did it touch what it should not". `test-proof`, `test-weakening`, mutation on the changed lines and the perimeter answer exactly that, in one line, with no model.

What ships (this is M31's "gates-only image" and ADR 0057, pulled to the front and given the Marketplace):
- `ghcr.io/nicolaguglielmi/lights-out-gates` (measure the size; proposal: under 400 MB unpacked, stated in the ADR with the measure), amd64 and arm64, cosign-signed with a public key in the README (the README today says the image is unsigned).
- The Action on the GitHub Marketplace with the verdict summary per gate.
- `lights-out gates` reads a `.lights-out/` drafted on the fly when none is committed (`init` in memory, provenance printed), so the first run on a bare repository is one command and one line.
- **Two standalone Actions on the same image**, `test-proof` and `test-integrity` (test-weakening plus changed-line mutation), each with its own Marketplace page and README, each one line. Section 3.2 (ii) and (iii): the idea is being rebuilt by hand in five repositories and nobody can install it. These two pages are the backlinks and the first stars; the full judge is what they lead to.
- Acceptance: on a repository that is not lights-out, from a clean runner, `uses: nicolaguglielmi/lights-out/action@v1` posts a check in under 300 s on a 2k-line Python or JavaScript PR, first pull included; measured, in the README. The two standalone Actions pass the same measure.

### K2. Zero-container gates: five gates in five seconds

What it is: the gates that need only git and Python (`risk`, `perimeter`, `test-weakening`, `test-proof` when `TEST_CMD` is the repository's own command, `spec`) run with no engine, from `pipx install` or `uvx`, in seconds. The engine gates (`secrets`, `deps`, `sast`, `mutation`) say in one line that they need the image, and the hook recipes gain a `--light` mode a coding agent can call before every commit without a 300 s timeout.

Why it pulls: the first "it works on my repo" moment moves from 5 minutes and a pull to 5 seconds. For the pre-commit hook in Claude Code, Codex and Gemini CLI it is the difference between a hook people keep and one they delete.

Boundary: one package, two tiers, the same one-line contract; the light tier never prints `GO: gates`, it prints `GO: gates-light — 5 of 9 gates ran, 4 need the image` so no one mistakes it for the judge. ADR 0052's boundary makes this cheap: the logic is already Python under `core/`.

### K3. An attestation of what the agent did, attached to the merge

What it is: a signed statement per merged change: ticket, perimeter, harness and model served, tokens and turns, every gate's line, the reviewer's verdict, the human GO (who, via what), the canary's numbers. Format: an in-toto statement with a `lights-out` predicate, attached with GitHub's artifact attestations where the code host is GitHub, stored beside the release record at L0, shown in the console's timeline and in the PR's summary.

Why it pulls: nobody answers "which of our changes did an agent write, under what policy, and who said GO". Procurement, security and compliance teams ask it today; SLSA and Sigstore cover the build and say nothing about the author. lights-out already has every field in `run.json`, the tower document and `.crew/releases.jsonl` (ADR 0047). This is the feature that makes the audit chain a thing you can hand to someone.

Boundary: no new role, no model; a `core/attest.py` writing a document, `adapters/<codehost>/attest.sh` as a verb where the host supports it (GitHub), a no-op with a declared line on Gitea.

### K4. The closed loop in one command, and one GIF

What it is: `./go demo-loop`: an alert fires on the plane → `ops-triage` ranks hypotheses and files an incident → the post mortem files a fix ticket (M22) → the tower assigns it inside the perimeter → the dev-worker's PR passes the eight gates → merge, canary, verify GO, the human says GO → 100%. At L0 with one recorded dev-worker run on the fix ticket (owner's key, once), replayed; everything else real.

Why it pulls: this is the sentence the owner wants the framework judged by, "end to end, development, delivery and operations", and no project in section 3 shows it. It is also the demo for the talk and the Show HN. The pieces exist; what is missing is the ticket, the recording, the script and the acceptance line.

Boundary: no seventh role, the loop is the tower's existing steps. The recording is the only cost that is not code.

### K5. The jury: the reviewer is never the author's model

What it is: when two provider keys exist, `test-reviewer` and `architect` run on a provider different from `dev-worker`'s, by default for medium and high risk; `run.json` says who judged whom. One profile key, one ADR, the eval per provider on labelled diffs the owner's study of 2026-11-07 already asks for.

Why it pulls: it is a sentence people repeat ("the model that wrote it never reviews it"), it is cheap, and it is visible in the console and the attestation. Not unique: no_human already runs a second model told to refute "done", with one provider. The difference to state is that here the second model is a different vendor and its verdict is one gate among eight, never the judge.

### K6. The agent's own toolbelt: plugin, skill, extension, MCP server

What it is: distribution inside the tools people already run.
- A Claude Code plugin (`/gates`, `/spec`, the pre-commit hook installed by the plugin, the official marketplace by its form and an own marketplace repository).
- A Codex skill and a Gemini CLI extension with the same two commands. Codex's public directory strips hooks, so the skill installs the hook through a command it offers; Gemini's needs the `gemini-cli-extension` topic and a manifest at the root.
- `lights-out mcp`: a read-only MCP server over the project map (which ADR governs this file, which tests cover it, which ticket touched it) and the spec gate (check this draft), published to the MCP registry from the same PyPI package as K2. ADR 0054 planned it "after M24, if agents need to ask mid-work"; as a discovery channel it earns its place earlier, read-only, no plane.
- **The judge the orchestrators call.** Paperclip (112k) has approval stages and budgets, Gas Town (18.7k) a merge queue with "verification gates", OpenHands (93k) a control center: none has a numeric judge. One documented recipe each, "run `lights-out gates` as the verification step", and an issue or PR on their repositories where they accept one. Their distribution, lights-out's verdict.

Why it pulls: each is a listing in a place developers browse, and each is a day or two. The MCP server also answers the first outside feedback's "the coding agent is only one piece" in the agent's own session. Superpowers reached 314k stars with a methodology on two official marketplaces and nothing to install; lights-out's gates are the enforcement those kits lack (RepoComplianceBench, section 3.1).

### K7. More stacks, in the order of the audience

Go, then Java, then Rust and C#; TypeScript already rides on Stryker. Each stack is a directory with a lockfile and three runners (test, SAST, mutation), as `stacks/python` and `stacks/javascript` are. Before writing one: verify that day which mutation tool is maintained for the language (the plan's rule; the Go tools in particular have churned), and refuse the stack with a clear line rather than ship a weak mutation gate (plan §11, §12). Go first because of the audience of a Show HN; Java second because of the legacy thesis of §14.

### K8. The evidence engine: the experiment and a public catch rate

Not a feature in code, the content that makes the features believed:
- M24 as planned: sqlparse, three providers, every verdict published weekly, GO and NO-GO alike.
- A catch-rate study: run the gates over a public set of agent-authored PRs (Copilot, Codex, Claude Code PRs on permissive repositories, merged and later reverted or not) and publish what each gate would have said, with the dataset. This is the article for the launch and the number a talk opens with. One scratch directory, the wrapper, a spreadsheet; no code in the product.
- The vacancy section 3.3 names: no leaderboard measures gated correctness, every benchmark ranks the harness. A small public table, "harness × gates passed on the same ticket batch", kept by the M24 runs, is a benchmark nobody else keeps and a reason to be cited.

## 7. The roadmap

Horizons, not dates: the owner's budget is 5–15 hours a week. Each milestone keeps the repository's rules: an ADR before code, tests from the ADR, `./go ci` and `./go demo` green from a clean clone, replay declared at L0. Numbers continue from M33; M24, M31 and M32 keep theirs.

### Now: the front door, light and true (about 6–8 weeks)

| # | Milestone | Done when |
|---|---|---|
| M34 | **Lean plane.** `sqlite` StateStore and `inproc` EventBus at L0/L1; the runner out of the demo path, the bundled app released through the attached-repository path; the cloud track and `antigravity-cli` off the first screen | `./go demo` under a new budget the ADR states from the measure (proposal: 600 s warm on Actions); two fewer services in `compose.yaml`; the tower's documents survive `./go down`; `./go ci` green |
| M31 | **The stepped way in**, as planned (ADR 0057), with K1 inside: the gates-only image, measured and signed; `action.yml` at the root and the Action on the Marketplace with the per-gate summary; the two standalone Actions (`test-proof`, `test-integrity`); `doctor --level`; `production-readiness`; the README in the order of the steps, with the reuse claims of section 5 | a check posted on a PR of a repository that is not lights-out, under 300 s first pull included, measured in the README; the image's size in the ADR; three Marketplace pages live |
| — | **Launch checklist, phase 0** (owner): the 60 s real recording at the top of the README, the Codespaces badge measured once, the eight good first issues opened, the social preview, the soft launch to 10–20 people, the Claude and Codex recordings, the GitHub end to end once | every box in [checklist.md](../launch/checklist.md) ticked or struck with a reason |
| M24 | **The public experiment** on sqlparse, three providers, the weekly diary | §14's exit criterion, published either way |
| slice | **Shell to Python, `ci/` first** (ADR 0052) | one file per milestone, the count in the ADR's debt list only goes down |

### Next: the two features nobody has, and the launch (about one quarter)

| # | Milestone | Done when |
|---|---|---|
| M35 | **K2, zero-container gates**, as the PyPI package `lights-out` that K6's MCP server and the plugins reuse | `uvx lights-out gates --light` on a bare clone answers in under 10 s on this repository, and the hook recipes carry `--light`; the line names the gates that did not run |
| M36 | **K3, the attestation** | a merged change on GitHub carries an attestation `gh attestation verify` accepts; the console's timeline and the PR summary show it; at L0 the statement sits beside the release record |
| M37 | **K5, the jury** | with two keys, a medium-risk PR is reviewed by a different provider than its author, recorded in `run.json` and the attestation; one key, the default is unchanged and said |
| M38 | **K4, the closed loop** | `./go demo-loop` at L0, no key, prints `GO: demo-loop` under its own budget; a real recording of it is the README's second GIF |
| M39 | **K6, the toolbelt**: Claude Code plugin, Codex skill, Gemini CLI extension, `lights-out mcp` read-only, the recipes for Paperclip, Gas Town and OpenHands | each listed where its vendor lists them; the MCP server answers the three questions over `.crew/map.sqlite` with no plane; one orchestrator's documentation links the recipe |
| — | **The launch** (owner): the long article with M24's numbers and the catch-rate study (K8), one Show HN on a Monday at 00:00 UTC (section 3.3, not plan §15's US-morning slot), newsletters, the awesome lists that fit (orchestrators, agent governance, CLI coding agents; awesome-claude-code once the plugin is 14 days old), the CFPs sent during Now | plan §15, phase 2 |

### Later: width by demand

| # | Milestone | Trigger |
|---|---|---|
| M40, M41 | **K7, Go then Java** | M24's outcome, and a user who names the language; each stack's mutation tool verified the day it is written |
| M32 | **Outside adapters, other CIs** (ADR 0058): GitLab as code host, Jenkins as a surface, Flagger on k3s | a user who asks; the conformance suite as the bar |
| — | The cloud tracks (M8 L2, M10 L3) | someone who pays, with the nightly |
| M16, M17 | The agent network decided; the dashboard beyond the console | an outside consumer, as plan §16 "Dopo" says |

### Risks this sequence carries

- **The free L1 path.** Gemini CLI moved free, Pro and Ultra users to Antigravity CLI on 2026-06-18 and the enterprise branch is what `gemini-cli` pins. The README's "the free tier is the only free path at L1" rests on the API key still being served free: verify it the day M31 starts, and if it is gone, say so and state the measured cost per provider instead.
- **Three harnesses that archive or stall.** Daytona archived, Roo Code archived, Aider stale this year. Pins and conformance suites (ADR 0041) are the right answer; the README should say which harness ran live last, and when.
- **The Marketplace move.** An `action.yml` at the root changes the `uses:` path for the only outside user there could be; do it before the first public mention of the Action.
- **The console's freeze.** The owner enjoys building it; the freeze needs saying out loud or it will not hold.
- **The demo under the new budget.** Dropping two services and the runner is also the first change to the L0 plane in months; `engine-compat` and `stranger` on Actions are the proof, as always.

### What the sequence refuses

- A seventh role, a model deciding a canary, a console with state of its own, an adapter without conformance and a nightly, a mutation gate on a language whose tool was not run (plan §12).
- Buying or trading stars, spamming lists, a Show HN before the experiment's numbers exist, a Discord nobody can staff (plan §15).
- Rewriting the gates in another language for its own sake: the move is logic to Python behind the same one-line contract, nothing else.

## 8. What to measure

Instruments the repository can read without a service, so the numbers are honest:

| Signal | Where | Proposal for the owner to set |
|---|---|---|
| Stars, uniques, clones | GitHub Insights, weekly | a number per horizon, set before the launch |
| Time to the first GO on a stranger's repository | `./go demo-init` and the Action's run time, in CI | under 300 s first pull included (ADR 0042's rule, extended to the Action) |
| Repositories using the Action | GitHub's "used by" on the Action, dependents | counted, not targeted, until the Marketplace listing exists |
| Outside issues and PRs, answered within 48 h | the repository | plan §15's rhythm |
| M24's exit criterion | the diary | two tickets in three to a mergeable PR with no human touching code (§14) |
| Catch rate of the gates on agent PRs | the K8 study | published with the dataset, whatever it says |
| Demo time on Actions | `engine-compat` and `stranger` | the new budget of M34 |

## 9. Decisions this document asks of the owner

1. Drop the emulators and the runner from L0 (M34), or keep L0 cloud-shaped.
2. Make the gates-only Action the front door, with the rollback as the GIF, not the first command.
3. Freeze the console after M33 until an outside user asks.
4. Pull the attestation (K3) and the closed loop (K4) ahead of stacks and adapters.
5. The new demo budget and the gates image's size, as numbers with their measure.

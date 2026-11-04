# Execution plan — the third arc, step by step, with the construction model and effort for each task

- Date: 2026-11-04
- Scope: how milestones M19, M21, M22, M23 and M24 of [docs/PLAN.md §16](../PLAN.md) get built with Claude Code: the steps, who does each (the milestone session or a subagent), which Claude model and which reasoning effort. M18 and M20 are merged on `main`.
- This is the construction side (plan §5, "Con cosa lo costruisci tu"), never the product's runtime models.
- Revised 2026-11-04, owner's decision: **Sonnet is the floor** (no Haiku anywhere), and a Sonnet session or subagent runs at **xhigh** wherever reasoning helps: planning, building adapters and core scripts, writing tests from a spec. Low effort stays only for the acceptance runs, where the time is `./go`'s.

## What the first two milestones measured

M18 and M20 ran on 2026-11-03 as two parallel sessions on Fable, each with the
`/milestone` skill, each in its own worktree with a full clone under `.crew/`
for the plane targets. Both closed in one working day. Their context windows
at the end: 304k tokens (M18) and 536k tokens (M20). After the two of them
and the parent session, the account's weekly all-models window stood at 6 %.

Three things follow:

- **Cost is not the binding constraint at this pace**; the owner's loop is
  (plan approval, merge, keys for the real runs). The model choice below
  still matters, because a Sonnet session finishes a mechanical milestone
  faster than a Fable one and leaves the weekly Fable window for the hard
  parts.
- **The session's own model is the cost driver**: it holds the long context
  and makes most of the tool calls. Subagents are short-lived and cheap by
  comparison, so the ADR can afford Opus at high effort even inside a Sonnet
  session.
- **Effort should follow the phase**, not the milestone: planning, ADRs and
  building earn high effort, and on Sonnet xhigh, since Sonnet at xhigh is
  still cheaper and faster than Opus at medium; running the acceptance
  (minutes of waiting on `./go demo`) is low.

## The rule, in one table

| Task kind | Who | Model | Effort | Why |
|---|---|---|---|---|
| Frame and plan a milestone (skill §1–§2) | the session | as below per milestone | Opus high, Sonnet xhigh | the plan is what the owner approves; a wrong plan costs a day |
| ADR with alternatives and provenance | `architect` subagent | Opus | high | the one structural decision per milestone; read-mostly, short-lived |
| Build against the approved plan (skill §3) | the session | as below | Opus medium, Sonnet xhigh | the design is settled; on Sonnet the extra reasoning is cheap and catches the shell and jq mistakes a rerun would cost |
| Gates, ci checks, tests from the spec | `gate-writer` subagent | Sonnet | xhigh | tests from the spec are where a cheap model cuts corners; the effort buys the cases the ADR implies, not only the ones it lists |
| README, docs, commit messages | `doc-scribe` subagent | Sonnet | medium | text work, nothing to decide; medium keeps the repo's voice and the no-hidden-mock wording exact |
| Run acceptance, demo, clean-clone proofs (skill §4) | the session | as below | low | waiting on `./go`; reasoning adds nothing to a ten-minute run |
| The hard 10 %: a cross-cutting problem Opus has missed twice, or a design with no precedent in the repo | a one-shot `Agent` task, or the session for that step only | Fable | xhigh | scoped to one brief, never a whole milestone |
| Merge a milestone branch into `main`, resolve conflicts | the parent session | Opus | medium | judgement on both sides' intent; yesterday's merges needed no more |
| Record fixtures at L1, run with real keys | the owner | none | | the owner's keys and money |

## Milestone by milestone

Start order: M19 and M22 now, in parallel (M19 needs M18, M22 needs M20,
both merged). M21 and M23 after M20's merge are also possible, but three
parallel sessions share one podman plane and the owner's review time, so
two at a time is the ceiling. M24 starts when M19 and M21 are merged.

### M19 — `claude-code` and `codex` harnesses (ADR 0041)

Session model: **Opus**. Three vendor CLIs with unverified headless
behaviour (hooks in `-p` mode, exit codes, sandbox modes) make this a design
milestone, not a mechanical one.

| Step | Who | Model | Effort |
|---|---|---|---|
| 1. Verify before writing: Claude Code `-p` hooks and exit codes, `codex exec --json` events and sandbox, keys from env | session | Opus | high |
| 2. ADR 0041: adapter contract, conformance cases, "guard in the hook vs guard in the container" | `architect` | Opus | high |
| 3. File-by-file plan, owner approval | session | Opus | high |
| 4. `adapters/claude-code/` (Containerfile, package-lock pin, entrypoint, hooks, `run.sh`, `thinking.env`) | session | Opus | medium |
| 5. `adapters/codex/` the same, with the container guard where hooks are missing | session | Opus | medium |
| 6. `gates/harness-conformance.sh` and its ci wiring, from ADR 0041's cases, not from the adapters | `gate-writer` | Sonnet | xhigh |
| 7. If a CLI cannot be guarded as the ADR requires (hooks silent in headless, no sandbox knob): the fallback design | one-shot task | Fable | xhigh |
| 8. README, reference, architecture, PLAN status note | `doc-scribe` | Sonnet | medium |
| 9. Acceptance: conformance GO for three harnesses, `./go ci`, `./go demo` on a clean clone; HANDOFF | session | Opus | low |
| Owner: `./go record TICKET=0001 PROFILE=l1 AGENT_HARNESS=claude-code`, then `codex` | owner | | |

### M22 — ops without the plane: incident in, post mortem out (ADR 0044)

Session model: **Sonnet**. The shapes exist (ADK tools in
`adapters/adk/lights_out_adk/`, replay and recording, the `Tracker` and
`Metrics` ports); the one design question, what anchors a post mortem to
the audit chain and makes it NO-GO otherwise, goes to the architect.

| Step | Who | Model | Effort |
|---|---|---|---|
| 1. ADR 0044: the incident document, `file_postmortem`, the anchoring rule, `METRICS_URL` and the `promql` adapter | `architect` | Opus | high |
| 2. File-by-file plan, owner approval | session | Sonnet | xhigh |
| 3. `file_postmortem` tool, incident input, tickets through the `Tracker` port | session | Sonnet | xhigh |
| 4. `core/postmortem.sh`, `./go postmortem`, the NO-GO checks | session | Sonnet | xhigh |
| 5. `adapters/promql/` and the `prometheus` adapter as its special case | session | Sonnet | xhigh |
| 6. ci checks and the eval cases for the new tool, from the ADR | `gate-writer` | Sonnet | xhigh |
| 7. Docs and PLAN status note | `doc-scribe` | Sonnet | medium |
| 8. Acceptance: `./go demo-postmortem` at L0 (or the honest gap in HANDOFF), `./go verify METRICS_URL=…`, `./go ci`, `./go demo` | session | Sonnet | low |
| Owner: `./go record-evals PROFILE=l1` for the post mortem recording | owner | | |

### M21 — GitHub as code host, release of an attached repository (ADR 0043)

Session model: **Sonnet**. `adapters/github/` mirrors `adapters/gitea/`
verb for verb; the release of an attached merge reuses `publish.sh` and
`verify.sh` with the repository's own image.

| Step | Who | Model | Effort |
|---|---|---|---|
| 1. ADR 0043: token handling, the `await` semantics on GitHub checks, the nightly | `architect` | Opus | medium |
| 2. Plan, approval | session | Sonnet | xhigh |
| 3. `adapters/github/` eight verbs on the REST API, token never in `.git/config` | session | Sonnet | xhigh |
| 4. Release of an attached merge without the Gitea `image` job | session | Sonnet | xhigh |
| 5. Nightly workflow against a throwaway repository, ci check for the adapter | `gate-writer` | Sonnet | xhigh |
| 6. Docs | `doc-scribe` | Sonnet | medium |
| 7. Acceptance at L0 (`./go ci`, `./go demo`) and the L1 e2e described for the owner | session | Sonnet | low |
| Owner: the throwaway repository, a token in `.env`, one `./go e2e CODE_HOST=github PROFILE=l1` | owner | | |

### M23 — one command, one package (ADR 0045)

Session model: **Sonnet**. Packaging and distribution; the one decision
with teeth is the engine socket in a published image, and that is the ADR.

| Step | Who | Model | Effort |
|---|---|---|---|
| 1. ADR 0045: the image, the wrapper, what `lights-out` may do without the socket, the Action's permissions | `architect` | Opus | high |
| 2. Plan, approval | session | Sonnet | xhigh |
| 3. Image build and publish workflow, the `lights-out` wrapper, `./go doctor` | session | Sonnet | xhigh |
| 4. The GitHub Action and the hook recipes for Claude Code, Codex, Gemini CLI | session | Sonnet | xhigh |
| 5. ci checks: the wrapper against the image, the Action's own run | `gate-writer` | Sonnet | xhigh |
| 6. Docs, the README's new first command | `doc-scribe` | Sonnet | medium |
| 7. Acceptance on a clean machine: `lights-out gates` under 300 s | session | Sonnet | low |

### M24 — the public legacy experiment, three providers

Session model: **Opus** for the runs' analysis, the owner for the diary and
the article. Every ticket runs three times, once per provider, with the
owner's keys; the sessions read the `run.json`s and the audit chains and
write the comparison.

| Step | Who | Model | Effort |
|---|---|---|---|
| 1. Pick the repository and the ticket batch (plan §14's criteria) | owner with one Opus session | Opus | high |
| 2. Each ticket: attach, assign per provider, collect verdicts and costs | session | Sonnet | xhigh |
| 3. Weekly diary entry from the records | `doc-scribe` | Sonnet | medium |
| 4. The final analysis: what held, what did not, per provider | one-shot task | Fable | xhigh |
| 5. The article | owner | | |

## How to apply it

- Start each milestone session with the model above (`start_session`
  takes `model` and `effort`; a card started by hand takes them from the
  app's session settings).
- Inside a session the skill delegates by subagent name; the models of
  `architect` (Opus), `gate-writer` (Sonnet) and `doc-scribe` (Sonnet) are
  in `.claude/agents/*.md`, and the effort per task kind is the table in
  `.claude/skills/milestone/SKILL.md`.
- `CLAUDE_CODE_SUBAGENT_MODEL` caps every subagent at once when the weekly
  window gets tight (plan §5).
- Revisit this table after M19 and M22: if a Sonnet session had to escalate
  twice on one milestone, the next one of that kind runs on Opus.

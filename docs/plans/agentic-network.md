# Plan — an agentic network for software development, governed by the harness

- Date: 2026-11-03
- Branch: `agentic-network` (not merged; for the owner's review)
- Decision record: [ADR 0036](../adr/0036-the-dev-worker-step-as-a-network.md) (proposed)
- Morning report: [agentic-network-report.md](agentic-network-report.md)

## Goal

Let several coding agents work on one ticket at once and have lights-out
govern what they produce together, with the controls that already govern
one agent: the declared perimeter, the six PR gates, the review routing,
the signed image, the canary that rolls itself back, and the one human
gate. The harness must not need to know how many agents wrote a change,
and the golden rule (`git clone && ./go demo`, L0, no key, under 900 s)
must not move.

## The reading chosen

"An agentic network governed by the harness" is read as **the dev-worker
step fanned out to several members behind the `AgentHarness` port**:

- A ticket may declare a `## Network` section: named members, each with a
  short brief and its own perimeter, a subset of the ticket's.
- A new harness adapter, `network`, runs one member per entry. Every
  member is a dev-worker run on the profile's own harness (`replay` at L0,
  `gemini-cli` at L1), in its own clone of the same base commit. No member
  sees another's work while it runs; they cooperate only through the
  ticket, which is the spec.
- The network checks each member on its own (the harness-independent
  check of ADR 0017 §1, then the member's perimeter with
  `core/perimeter.sh`, then that no two members touched the same path),
  integrates the members' commits in the declared order into the ticket's
  branch, and hands `core/crew.sh` the usual artefacts: one patch, one
  `pr.json`, one `run.json` that lists every member.
- From there nothing is new. Crew checks the composite against the
  ticket's perimeter, the tower runs the gates, the risk score routes the
  PR, merge, signed image, canary, verify, rollback, audit and
  go-for-launch are the ones `./go e2e` already proves.

The topology the first network ticket uses is the **spec split**: one
member implements, another writes the tests from the ticket alone, at the
same time, without seeing the implementation. The repo's own rule ("tests
are written from the spec, never from the implementation") becomes a
structural property of the run instead of a line in a prompt, and the
mutation gate on the composite is what proves the test-writer's tests
actually bite the implementer's code.

`core/crew.sh` picks the network only when the command asks for it:
`CREW_HARNESS=network`. The variable is read by crew alone, so a review
step in the same tower run keeps its own harness. A ticket with no
`## Network` section runs through the network as a single worker,
unchanged, so enabling the network never breaks an ordinary ticket.

The rejected readings (a seventh, coordinating role; agents that talk to
each other at run time; the ADK roles wired into an agent-to-agent mesh;
a fleet of tickets in parallel through the tower; the network as a new
tower state; packaging the gates for external agents) are in ADR 0036
with the reason for each.

## Steps

Each step leaves the branch green. "Green" means `./go ci` prints
`GO: ci` and `./go demo` prints `GO: demo, …` inside the 900 s budget at
L0, with no key.

### Step 1 — Plan and ADR

This document and ADR 0036, status *proposed*, with the alternatives
rejected and the provenance of the one number the design adds.

Acceptance:

- `./go ci` → `GO: ci` (`roles` still counts six; no stated count drifts).

### Step 2 — The `network` adapter, `CREW_HARNESS`, and `ci/network.sh`

- `adapters/network/run.sh`: parse `## Network`; refuse more than four
  members, perimeters that overlap on their face, and a recursive
  `AGENT_HARNESS=network`, all before any member runs; run the members in
  parallel; check each with `core/harness-check.sh` and
  `core/perimeter.sh`; refuse a path touched by two members; integrate in
  order; write `patch`, `pr.json`, `final.md`, `run.json`. A ticket
  without `## Network` is passed straight to the profile's harness.
- `core/crew.sh`: `harness=${CREW_HARNESS:-${HARNESS:-$AGENT_HARNESS}}`,
  one line, default unchanged.
- `ci/network.sh`, written from ADR 0036 and not from the adapter: on
  throwaway git repositories and a stub member harness inside the test,
  both directions — the pass-through, a two-member GO with isolation
  checked from inside each member, and every refusal: a member outside
  its part, two members on one path, overlapping perimeters, a failed
  member, five members, recursion. Added to `CI_CHECKS`.

Acceptance:

- `./go ci` → `GO: ci`, with `GO: network` among the checks run.
- `./go demo` → `GO: demo, milestone M9, <n>s to rollback (budget 900s, plan §2)`.

### Step 3 — Ticket 0012 and `./go demo-network`

- `tickets/0012.md`: a real defect in the first workload (a meetup can be
  created with a capacity below one, after which every registration
  answers 409 "meetup is full"), with a `## Network` of two members:
  `impl` (application code and its one line of docs) and `tests` (a new
  test file, from the ticket alone).
- `fixtures/0012/{impl,tests}/dev-worker/`: the two members' L0 fixtures.
  **They are written by hand, not recorded from a model**, and say so in
  their `run.json` (`hand_written: true`, `model: null`), in the network's
  `pr.json` and in the audit line (`model none`). They exist to prove the
  governance at L0; a recorded run replaces them in step 5.
- `./go demo-network`: `up`, then the tower's golden path on ticket 0012
  with `CREW_HARNESS=network` — network → PR → gates → auto-merge (low
  risk) → signed image → canary → verify NO-GO → rollback → audit — and
  then the checks that only a network run has: the document's
  `task.harness` is `network`, `run.json` lists `impl` then `tests`, and
  the PR holds one commit per member. Outside the fixed list of
  `./go demo` (ADR 0003).

Acceptance:

- `./go demo-network` → `GO: demo-network`.
- `./go ci` → `GO: ci`; `./go demo` → `GO: demo, …` inside 900 s.

### Step 4 — Say what is real

- README, "what is real at L0": one line for the network and its
  hand-written member fixtures. `docs/reference.md`: `demo-network` and
  `CREW_HARNESS`. The `go` header lists `demo-network`.
- The morning report.

Acceptance:

- `./go ci` → `GO: ci` (`readme` and `roles` checks).

### Step 5 — Record the network at L1 (not on this branch: owner's decision)

`./go record TICKET=0012 CREW_HARNESS=network PROFILE=l1`, with `record`
taught to save one fixture per member. Two blockers, both outside this
plan: it spends the owner's Gemini quota (two dev-worker runs, measured
at up to 2.4 M tokens each, ADR 0021 §6), and the dev-worker prompt still
names the first workload's layout and "four files" (`roles/dev-worker/
prompt.md`), which a test-writer member would read as a contradiction of
its part. ADR 0031 (M13, proposed) moves the layout out of the prompt;
the L1 recording belongs after it.

Acceptance (for later): `./go record TICKET=0012 CREW_HARNESS=network
PROFILE=l1` → `GO: record`, then `./go demo-network` → `GO: demo-network`
on the recorded fixtures, `input_matches_recorded: true` per member once
ADR 0031 extends it to the dev-worker.

### Step 6 — The architect writes the split (later, owner's decision)

Today the ticket's author declares the members. The architect role
already has a prompt and a measured budget (ADR 0021 §4) and is the
natural author of a split: it would write the `## Network` section of the
member documents instead of the human. Needs its own recorded fixture and
an amendment of ADR 0036; no new role.

## Risks to the golden rule

| Risk | Where it would bite | Mitigation |
|---|---|---|
| `./go demo` gets slower or breaks | `ci/network.sh` runs inside `./go ci`, which `./go demo` runs first | the check is cold (no plane, throwaway repos, a stub member): seconds, measured in the report; `./go demo` re-run on the branch |
| The crew change alters the default path | `core/crew.sh` picks the harness for every ticket | one parameter expansion whose default is the old expression; `./go demo`'s e2e replays ticket 0001 through it |
| The demo shows a network that a model never ran | ticket 0012's L0 fixtures | declared in `run.json`, the PR body, the audit line (`model none`), README and the report; step 5 replaces them |
| A network spends N times a worker's budget at L1 | more members, more tokens | at most four members (provenance in ADR 0036), each with the role's unchanged budgets |
| Parallel `gemini-cli` members at L1 | two `docker-compose run --build` at once; free-tier rate limits | unverified tonight; step 5's first recording measures it, and the ADR says so |
| A tower state added without the board | `ci/board.sh` | no tower state or step is added: the network lives inside `assign` |

# ADR 0029 — Focus: lights-out is a governed-autonomy harness for a codebase you do not trust; the target app becomes a workload behind a port; the factory front office is a separate consumer; the name stays, the positioning changes

- Status: accepted (amends plan §1 [the identity sentence: the Google stack is the optional cloud target, not what the product is], §5 "L'app bersaglio" [the meetup app is the first workload, no longer the product's fixed subject], §7 [M12 added; M8 cloud, M10 and M11 re-sequenced], §11 and §12 [new risks and don'ts]; consistent with ADR 0022 [local first] and ADR 0024 [adapters as plugins]; the technical design of the port is ADR 0030, written at M12)
- Date: 2026-09-23
- Milestone: plan amendment before M12
- Amended 2026-09-23 (owner): decision 6's ecosystem is Python (Django allowed). The three listed below conflated the thesis with language independence, which needs a per-workload worker image; the worker already carries Python 3.13 and every Python gate runner. Language independence follows the first client's language (plan §14).
- Amended 2026-11-02 (owner): decisions 4 and 6 — see "Amendment 2026-11-02" at the end. The goal order becomes visibility first (talks, GitHub stars), a company second if a co-founder or funder appears, revenue third; the paid engagement leaves the sequence; contributions come under the DCO.

## Context

On 2026-09-22 the owner asked whether the platform could deliver a
client proof of concept starting from a requirements interview, and then
whether it should become an entire "agentic tech company": pre-sale,
discovery, PoC, refinement, delivery, operations, for many products and
many clients. Checking the repo against that ask established four facts:

1. The entry point is a hand-written ticket. `roles/product/prompt.md`
   receives a ticket and gives a one-shot verdict with two tools; the
   product role has no `./go` target and `core/tower.sh` starts at
   `opened → assign` (dev-worker). Nothing upstream of the ticket exists.
2. The target app is hard-wired into the platform. Measured 2026-09-22
   with `grep -rl 'app/backend|meetups|waitlist'` over `*.sh`, `*.yaml`,
   `Makefile`, `*.promql`, `*.env`, excluding `app/`, `docs/`, `fixtures/`,
   `tickets/` and caches: about 87 references in 15 files —
   `compose.yaml` (14), `Makefile` (10), `gates/delivery-conformance.sh`
   (18, mostly the app's `waitlist` flag used as the suite's lever),
   `gates/mutation.sh` (7), `gates/sast.sh` (4), `gates/deps.sh` (3),
   `gates/test.sh` (1), `core/crew.sh` (3, the workspace symlinks under
   `app/backend/`), `verify/metric-shape.sh` (2, `/api/meetups`),
   `policy/merge.env` (4), `adapters/flagd/ready.sh` (3), and `ci/*` (18).
   `ci/vendor-free.sh` forbids `core/` from naming a Delivery vendor; no
   rule forbids it from naming the app, and `core/crew.sh:60` does.
3. `policy/merge.env` is already the right shape for a per-instance
   contract: it declares which paths of the app carry high risk, as
   configuration outside the code. The mutation gate is already a ratchet
   against a measured baseline (`MUTATION_BASELINE`, `MUTATION_MARGIN`,
   ADR 0015 §3), evaluated on the lines the diff touched, not an absolute
   threshold — the semantics a codebase with poor coverage needs.
4. The one thing every downstream stage has in common — gate contract,
   perimeter, risk scoring, mutation ratchet, numeric verify, automatic
   rollback, one human gate, audit chain that cross-checks the code host —
   does not depend on which model writes the code. The model is already
   behind a port (`AgentHarness`: replay, gemini-cli, adk).

Three directions were weighed on 2026-09-23 (the analysis is summarised
in plan §14): (A) the end-to-end factory, reshaped as a per-app
"exoskeleton" rather than a multi-tenant tower; (B) the existing pipeline
as a governed-autonomy harness pointed at legacy repositories for
modernization work; (C) finishing the plan as written (M8 cloud track,
M10, M11). The owner ruled: the talk is secondary; the original goal was
an open-source repository; the implementation showed the harness could
earn its keep. Direction B, kept open.

## Decision

1. **What the product is.** lights-out is a harness that lets agents make
   changes at volume on a codebase nobody trusts, safely: every change
   passes numeric gates, stays inside a perimeter the ticket declares,
   rolls itself back on a verify NO-GO, and reaches production through one
   human decision. The six roles are unchanged and are the harness's
   delivery team. The value is the harness; the model is replaceable and
   already is.

2. **The app is a workload behind a port.** The meetup app becomes the
   first workload, not the product's subject. A per-instance contract
   declares everything the gates, the launchpad, the verify runner and the
   tower need to know about the app; no file under `core/`, `gates/` or
   `verify/` names the app, and a `ci/app-free.sh` check proves it, the way
   `ci/vendor-free.sh` proves the Delivery rule. A second, deliberately
   minimal workload proves the seam is real rather than declared. Port
   name, contract fields and the second workload's shape are ADR 0030's,
   at M12.

3. **The factory is a separate consumer, not this repository.** Interview,
   PoC, proposal, refinement and any cross-instance view (a portfolio of
   engagements) belong to a separate project that consumes lights-out
   only through the interfaces lights-out publishes. The boundary rule:
   *does a client running one instance need it?* → lights-out. *Is it
   only useful to whoever runs many engagements?* → the other project. If
   the consumer needs a hook lights-out lacks, the hook is added here, in
   the open, as a port — never a private entry. The consumer starts only
   after lights-out has a consumer other than its author.

4. **Open source stays; Apache 2.0 is unchanged.** The harness is the trust
   artefact: a client lets autonomous agents onto a legacy monolith only
   because the gates, the perimeter and the audit chain can be read. The
   contributor surface (CONTRIBUTING.md, an English ROADMAP.md derived
   from the Italian plan, the conformance suite as the acceptance bar for
   contributed adapters and gate packs, "no contributed adapter without a
   nightly and a maintainer" extended from §11's policy) lands right after
   the seam, and is not a milestone.

5. **The name stays; the positioning changes.** "Lights-out manufacturing"
   describes a floor that runs unattended because the safety systems are
   trusted; "one human turns the lights back on" is the human gate. That
   fits the harness better than it fit the factory. The internal names
   (tower, crew, launchpad, go-for-launch) describe the delivery engine,
   which is the product. What changes is the sentence under the name: the
   README opens with the problem (a codebase you do not trust), and "on a
   Google stack" moves from the identity line to the L2/L3 rows of the
   levels table, where it was always true.

6. **Sequence.** M12 (the seam) first — it serves every direction. Then a
   public experiment: lights-out pointed at a real, well-known legacy
   open-source repository, in an ecosystem with a serious mutation tool
   (Java/PIT, .NET or JavaScript/Stryker), on a batch of mechanical
   tickets, with the audit chain published and the fixtures replayable.
   Then the first paid engagement. M11 (console) is pulled forward after
   the experiment, because the client of an engagement wants to see the
   audit chain and press go-for-launch themselves. M8's cloud track and
   M10 wait for someone who pays for them, the policy §11 already applies
   to a second cloud adapter.

## Alternatives rejected

- **The end-to-end factory now, multi-tenant.** Engagement becomes an
  entity in the tower, `collection=tickets` becomes per-engagement, one
  plane serves many apps. The largest structural change on the table,
  with no capability visible until three milestones later.
- **The end-to-end factory now, as a per-app exoskeleton.** Kills the
  multi-tenancy but keeps the front office: interview and refinement are
  human-in-the-loop by nature, so at L0 they can only be a recorded
  engagement replayed — a demo, which is exactly what §11 warns the
  public repo must not become. Its differentiator is the back half, which
  is this ADR's product; the front half is what every tool does today.
  Kept as the separate consumer of decision 3.
- **Finish the plan as written first (M8 cloud → M10 → M11).** None of it
  changes what the product is worth; M8's cloud track and M10 cost money
  per run and prove a second adapter, not a second customer. M11 survives,
  re-sequenced.
- **Rename.** 290 files carry the name, plus the GitHub remote, the
  `lights_out_adk` package, `LIGHTS_OUT_ROOT`, image and Gitea repository
  names in compose. A milestone of blind edits to lose a name that fits
  the new focus better than the old one. The factory consumer takes a new
  name when it exists.
- **Close the source, sell the tool.** Removes the trust artefact and
  with it the only reason a client says yes; for a services business the
  licence earns nothing anyway.

## Consequences

- Plan §1, §5, §7, §11 and §12 are amended; §14 records the second arc.
  CLAUDE.md's first line and the README's opening say what the product is;
  the GitHub description and topics follow.
- M12 exists and is next. M8's cloud track, M10 and M11 stay open with the
  order of decision 6; nothing of theirs is deleted.
- The "six roles" rule and the golden rule survive unchanged. The seam is
  proven by `./go demo` giving the same `GO: demo` as M9.
- The mutation gate's ratchet semantics, so far a detail of ADR 0015, is a
  documented feature: on a legacy workload the baseline is measured, not
  aspired to, and the gate forbids regression on the touched lines.
- One known limit becomes a first-class risk (§11): the harness's sharpest
  gate depends on the target ecosystem having a serious mutation tool.
  The experiment's repository is chosen for that reason before any client
  is promised anything.
- `CLAUDE.md` still says the repository is public; on 2026-09-23 the
  GitHub repository is private. Publishing is the owner's act, after the
  seam and the contributor surface exist.

## Golden-rule check

Nothing changes for the cloner: podman, git, a shell, `./go demo`, no
key. M12 is accepted only if `./go demo` at L0 prints the same verdict
within the same 900 s budget. The legacy experiment and any engagement
run outside the demo path by construction. Passes.

## Amendment 2026-11-02

**Context.** On 2026-11-02 the owner weighed five business models for
the repository: free with no revenue, free plus services (this ADR's
decision 6), open core, a hosted tower, and free with indirect revenue.
The owner set the order of goals: material and reach for talks first; a
company second, only if a co-founder or a funder appears; revenue third.
The time available is 5–15 hours a week, and the owner will take
consulting work on a real codebase when it is asked for. A survey of
open-source guardrails for coding agents on the same day found projects
that block commands or check pull requests, and none that carries a
change through canary to an automatic rollback with an audit chain.

**Decision.**

1. **Visibility first.** The repository is free, Apache 2.0, with no
   paid tier. Its job is to be tried, starred and talked about. Revenue
   is indirect: talks, training, and engagements that arrive on their
   own. An engagement is a design partner — a real codebase and evidence
   that the problem exists — not a step the sequence waits for.
2. **Decision 6's sequence changes.** The contributor surface, a README
   that splits a zero-friction quickstart from a deep dive on a real
   repository, then M13, then the public legacy experiment, then the
   launch built on it. "Then the first paid engagement" is removed. M11
   (console) still follows the experiment, now because it is what a talk
   and a README can show. An agent-agnostic packaging of the gates
   (usable beside Claude Code, Codex or Copilot) is the candidate for a
   second launch; it needs its own ADR, since plan §4's adapter table
   does not list it.
3. **Contributions come under the Developer Certificate of Origin.**
   Every commit carries `Signed-off-by:`; there is no CLA. Apache 2.0
   §5 already licenses a contribution under the project's licence, and a
   later company can sell services or hosting on top of Apache 2.0
   without relicensing, which is the one thing a CLA would buy.

**Alternatives rejected.** *Open core*: the gates, the perimeter and the
audit chain are the trust artefact; putting any of them behind a paywall
removes the reason to try the harness. *A hosted tower*: a multi-tenant
service with no user yet, against the local-first rule (ADR 0022) and
the owner's available time. *Services as the goal* (decision 6 as
written): at 5–15 hours a week, finding clients and building the harness
compete for the same hours. *A CLA*: it buys relicensing, which this
decision does not need, at the cost of contributor friction.

**Consequences.** Plan §14's sequence is rewritten and a visibility plan
is added to it. CONTRIBUTING.md states the DCO. The golden rule is
unchanged and becomes the launch's first promise.

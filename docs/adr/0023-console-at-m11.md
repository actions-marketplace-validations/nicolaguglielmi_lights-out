# ADR 0023 — The console at M11: a view over git and the state store, two writes only (answer an open question, press go-for-launch), the CLI stays primary, charts come through a `Charts` port with `grafana` and `cloud-monitoring` adapters; the console — not the target app — is what Stitch designs

- Status: accepted (amends plan §3, §4, §5 Stitch, §6, §7 M11, §8 step 8; amends ADR 0009 [`design/` and `design/CONTRACT.md` describe the console, the target app's frontend is no longer their reader]; adds one port to §4, which CLAUDE.md requires an ADR for)
- Date: 2026-09-20
- Milestone: M11 (defined now; built after M10)

## Context

The plan had a design loop at M11 whose subject was the target app: Stitch
designs screens, `design/` holds the export, a frontend worker builds the
meetup UI from `design/CONTRACT.md` (ADR 0009 §Context). The meetup app's
frontend exists since M1 and no ticket asks for a redesign; the design loop
had no product to serve.

Meanwhile the platform has grown a human surface with no screen: the tower
document per ticket in the state store (ADR 0019), the audit chain
deploy → merge → PR → ticket → spec (`./go audit`), the product role's
`ask_product_owner` question (ADR 0020), the promotion brief and the human
answer of `./go promote` (ADR 0020 §4), the review verdict in the tower
document (ADR 0021), and twenty-one ADRs whose `Status` lines record which
one amends which. All of it is readable today from the terminal and from
nowhere else. On stage, the terminal is the wrong surface for the one
moment the talk is about: the human turning the lights back on.

Owner's ruling on 2026-09-20: a console milestone, after the nightly,
absorbing the design loop; the console is what Stitch designs. Four
binding principles, stated in the request and fixed here.

## Decision

1. **A view, not a source of truth.** The console reads from two places
   and writes to none of its own: git (tickets under `tickets/`, ADRs under
   `docs/adr/`, commits and PRs through the `CodeHost` port) and the state
   store (the tower's documents through the `StateStore` port). It has no
   database, no cache that survives a restart, no field that cannot be
   rebuilt from those two sources by deleting the console and starting it
   again. If a screen needs a fact neither source holds, the fix is to make
   the tower record the fact, never to make the console remember it.

2. **Two writes, both through existing code.** (a) Answer an open question
   on a ticket: the question the product role raises with
   `ask_product_owner`, answered where that role already reads the answer.
   (b) Press go-for-launch: the console calls `core/promote.sh` with
   `GO_FOR_LAUNCH=GO` or `NO-GO`, the same path `./go promote` takes, so
   the record, the brief and the audit line are identical whichever
   surface pressed the button. No third form, no edit of a ticket, no
   retry button, no manual state transition. M11 decides the exact seam
   for (a) — a field in the tower document or a file in `tickets/` — under
   principle 1: it must be a place the CLI already reads.

3. **The CLI stays primary.** Every screen shows something a `./go`
   command prints, every write is a `./go` command; the console is a
   second surface over the same code. A cloner who never opens the console
   loses nothing. Acceptance for any console feature includes naming the
   command it mirrors.

4. **Charts are not redrawn.** A `Charts` port joins §4 with two adapters:
   `grafana` (L0/L1, a Grafana container in the L0 plane reading the same
   Prometheus, dashboards committed as JSON) and `cloud-monitoring` (L2/L3,
   dashboards from Terraform). The console embeds or links the panels the
   adapter exposes and never queries metrics itself; `verify/slo.promql`
   stays the only query that decides anything.

5. **Five screens.** Ticket board on the tower's state machine (`opened` →
   `pr-opened` → `ci-passed` | `ci-failed` | `review` → `merged` →
   `rolled-back` | `held`); ticket detail with acceptance criteria,
   perimeter and open questions; ADR navigator with the amendment
   relations parsed from the `Status` lines; audit chain from production
   back to the spec, the same chain `./go audit` rebuilds; go-for-launch
   panel with the promotion brief and the canary outcome. Nothing else at
   M11.

6. **Stitch designs the console.** The design loop's subject changes from
   the target app to these five screens. `design/tokens.json`,
   `design/screens/` and `design/CONTRACT.md` describe the console; the
   frontend worker builds `console/` from them and never calls Stitch; a
   cloner without Stitch access gets the same console from the committed
   artefacts. The target app's frontend stays as ADR 0009 left it. The
   console lives in `console/` (§6), in compose at L0/L1 and on Cloud Run
   at L2/L3, and is one more service in the plane, not a role: the title
   still says six.

7. **Acceptance.** At L0, no account, no key: the console opens, shows
   ticket 0001 with its complete chain (spec → ticket → PR → CI → merge →
   release → verify → rollback), and go-for-launch pressed from the console
   really moves the canary to 100% — the same effect as `./go promote`
   with `GO`, proven by the same check `demo-launch` already runs.

The console's stack (framework, how it reads the emulator, how it embeds
Grafana) is M11's decision with its own ADR; this ADR fixes what the console
may know and may do.

## Alternatives rejected

- **Keep the design loop on the target app.** No ticket needs it; the
  artefacts would be exercised once for the talk and never again. The
  console is used at every demo.
- **Give the console its own store (a read model, a cache, a database).**
  The first time it disagrees with the tower the demo lies, and §11 lists
  exactly that risk. Reading the two sources directly costs latency the
  demo can afford.
- **More writes: reassign a ticket, retry a step, edit a criterion.** Each
  one is a state transition the tower does not offer from the CLI either.
  Adding it to the console first inverts principle 3; adding it to the
  tower is a separate decision with its own ADR.
- **Draw charts in the console from PromQL.** A second consumer of the
  metrics, a second place where a query can drift from `verify/slo.promql`,
  and a chart library to maintain. Grafana and Cloud Monitoring exist for
  this and are already the two ends of the `Metrics` port.
- **Use Antigravity's Manager as the console.** It shows agents working,
  which stays a demo moment (§5), but it is public preview, not clonable,
  and knows nothing about the tower's states or the audit chain.
- **A seventh role, "operator", that talks to the console.** The title
  says six; the human is the operator.

## Consequences

- §4 gains the `Charts` port; the L0 plane gains a Grafana container at
  M11, counted against the pull budget of ADR 0004 when M11 measures it.
- §6 gains `console/`; `design/` changes owner from the app to the console.
- ADR 0009's sentence "M11 makes a frontend worker read `design/`
  artefacts" now refers to the console's frontend; the app's frontend
  remains without tests until a ticket asks for one, and `app/README.md`'s
  "M11 at the latest, written from `design/CONTRACT.md`" is void — M11 will
  rewrite that line.
- `core/promote.sh` must be callable from a service, not only from a
  terminal: it already reads `GO_FOR_LAUNCH` from the environment (ADR 0020
  §4), so the console sets it and the terminal fallback never fires.
- The product role's question needs a place the console can read and
  write; M11 picks it under principle 1, possibly amending ADR 0020.
- `docs/TALK.md` and the backup videos stay in M11, after the console.

## Golden-rule check

The console is a service in the L0 plane, started by `./go up`, no account,
no key. Its acceptance is a subset of what `./go demo` already proves
(`e2e` for the chain, `demo-launch` for the button) shown on a screen.
Whether the console joins `./go demo`'s fixed stage list is ADR 0003's
rule and M11's measurement against the 900 s budget; it does not join it
by default.

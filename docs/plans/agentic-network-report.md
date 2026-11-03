# Morning report — the agentic network, 2026-11-03

Branch `agentic-network`, from `main` at 1c62d1d. Not pushed, not merged.
Plan: [agentic-network.md](agentic-network.md). Decision: [ADR 0036](../adr/0036-the-dev-worker-step-as-a-network.md), status *proposed*.

## In one paragraph

"An agentic network governed by the harness" is built as the dev-worker
step fanned out to several members behind the `AgentHarness` port. A
ticket declares its members in a `## Network` section, each with a brief
and its own perimeter. The new `network` adapter runs every member on the
profile's harness, each in its own clone of the same base, in parallel,
with no shared state. It judges each member alone, integrates them in
order into one PR, and from there the existing tower governs that PR like
any other: gates, risk routing, merge, signed image, canary, verify NO-GO,
rollback, audit. No seventh role, no tower state, no new vendor. The first
network ticket (0012) uses a **spec split**: `impl` writes the code and
`tests` writes the tests from the ticket alone, without seeing the code.
The mutation gate on the combined PR then checks that the tests catch
changes to code their author never saw.

## What was built

| Commit | What |
|---|---|
| b1fdc29 | `docs/plans/agentic-network.md` (goal, reading, steps with `./go` acceptance, golden-rule risks) and ADR 0036 (proposed): ten alternatives rejected, one number with provenance |
| 277bec5 | `adapters/network/run.sh`; `core/crew.sh` reads `CREW_HARNESS` first (one line, default unchanged); `ci/network.sh` added to `CI_CHECKS` |
| 101e766 | `tickets/0012.md` (a real defect: a capacity below one makes a meetup nobody can join), member fixtures `fixtures/0012/{impl,tests}/dev-worker/`, `./go demo-network` |
| 5a258d0 | `go`: `demo-network` gets the engine socket. I first put this edit in the wrong file, and the first `./go demo-network` failed on it |
| 9b285ed | README "What is real and what is recorded" gets a **Hand-written** line; `docs/reference.md` gets the declaration and the command |

What the adapter refuses:

- **Before any member runs:** more than four members, two perimeters that
  overlap on their face, `AGENT_HARNESS=network` (recursion), duplicate
  or malformed member ids, and a member with no perimeter.
- **After the runs, before integrating anything:** a member that exited
  non-zero, a member that fails `core/harness-check.sh`, a member whose
  diff leaves *its own* part (checked by `core/perimeter.sh` on the
  member's own document), and one path changed by two members.

The per-member perimeter adds governance that the ticket's perimeter
cannot give: a test-writer that edits the code stays inside the ticket's
perimeter, but the network refuses it.

A ticket without `## Network` is passed to the member harness unchanged.
Only crew reads `CREW_HARNESS`, so the review step in the same tower run
keeps its own harness. I rejected `HARNESS` and a profile setting for
that reason: either would fan the reviewer out over its own input.

## What was verified, with numbers

All on this machine, L0, no key, `APP_PORT=9000` from `.env`.

| Command | Result |
|---|---|
| `./go ci` (baseline, branch = main + docs) | `GO: ci`, 22 checks, 62 s (cold container) |
| `./go ci` (after each step) | `GO: ci`, 23 checks including `GO: network`, 48–50 s warm |
| `./go ci-network` alone | `GO: network`, ~1 s including container start |
| `./go demo` after step 2 (warm plane) | `GO: demo, milestone M9, 455s to rollback (budget 900s, plan §2)` |
| `./go demo-network` | `GO: demo-network`, 262 s wall, warm plane |
| `./go demo` final, after `./go down` (images and workbench cached) | `GO: demo, milestone M9, 426s to rollback (budget 900s, plan §2)` |

What `./go demo-network` showed in its tower log:

- `member impl started (replay)` and `member tests started (replay)`,
  then both applied.
- `GO: crew`, then `[ci] gates: GO: gates — risk low, auto-merge`.
- `merged`, then `release → rolled-back` on
  `error_rate canary(0.2.0-waitlist)=1.000 stable(0.1.0-m2)=0.000`.
- The audit line `← ticket 0012 (dev-worker, harness network, model none)`
  and `GO: audit`.
- The target's own checks: `task.harness=network`, `run.json` members
  `impl,tests`, two commits in the PR, ci `GO/low/auto-merge`.

The gates on the combined PR, re-run by hand on the same range (the tower
deletes its gates worktree): mutation **2 mutants, 2 killed, score 1.0**
(the `ge=1` bound mutated to 0 and to 2). Risk was low on 45 changed
lines, with no signals. Tests passed.

Testing the test: I broke the adapter by hand six ways and ran
`ci/network.sh` against each.

- **Caught:** no per-member perimeter check (case c), the cap raised to 9
  (case g), one direction of the overlap check disabled (case e), a
  member's exit code ignored (case f, after making the failing stub leave
  complete artefacts), and the shared-path check removed (case d, after
  tightening the assertion).
- **Not caught:** cloning members at `HEAD` instead of `BASE`. At the
  moment the members start, the two are the same commit, so this mutant
  cannot be told apart from the original.

## What was not done, and why

- **No L1 recording of a network.** Ticket 0012's members are patches I
  wrote by hand. Their `run.json` says `hand_written: true, model: null`,
  the PR body says "hand-written, no model ran", the audit prints
  `model none`, and `demo-network` says so on stderr. Recording would
  spend your Gemini quota (two dev-worker runs, up to 2.4 M tokens each,
  ADR 0021 §6), and that is your decision. There is also a second reason
  (next item).
- **The dev-worker prompt still names one workload's layout and "four
  files".** `roles/dev-worker/prompt.md` would contradict a member's part,
  for example telling the `tests` member to touch the client. ADR 0031
  (M13) moves the layout out of the prompt. It sits **untracked and
  proposed** in your working tree, and I did not touch or commit it. The
  L1 recording belongs after it.
- **`./go record` cannot save a network's member fixtures.** Not written,
  because I had no way to verify it without a live run (plan step 5).
- **Parallel `gemini-cli` members are untested.** Two
  `docker-compose run --build` of the same service at once, plus the free
  tier's per-minute limits. The first recording will measure both
  (ADR 0036, Consequences).
- **No `demo-network` NO-GO on the plane.** The refusals are proven cold
  by `ci/network.sh`, and a fake test is already caught by `demo-gates`'
  `fake-test` fixture. A plane-level NO-GO network fixture would cost a
  second hand-written pair for little extra proof.
- **The board does not show members.** No tower state changed, so
  `ci/board.sh` stays green. Showing members in the station detail is
  optional.
- **Plan §4 is not edited.** Adding `network` to the `AgentHarness` row is
  yours to accept, through ADR 0036.

## Open decisions for the owner

1. **Accept ADR 0036?** If yes: add `network` to plan §4's `AgentHarness`
   row, and decide whether `./go demo-network` gets a note in §7 or in a
   milestone.
2. **Spend the quota on a recorded network** (plan step 5), after M13's
   prompt work? Until then L0 shows hand-written members, declared as
   such.
3. **The architect writes the split** (plan step 6)? It would make
   "network" mean the roles cooperating, not just several dev-workers.
4. **Is four members the right cap?** It comes from the free tier
   (250 requests a day ÷ `MAX_TURNS=60`). At L2 the constraint is money,
   not requests, and the number would need a new provenance.

## Found on the way

- **A real bug in `core/perimeter.sh` (on `main`, not fixed here).** The
  glob loop runs with pathname expansion on, so a perimeter glob is
  expanded against the files in the current directory before it is used
  as a pattern. Reproduced: with the glob
  `app/backend/tests/test_geocoder_*.py`, the existing
  `test_geocoder_client.py` passes and a new `test_geocoder_new.py` is
  refused as "outside the ticket's declared perimeter". A ticket whose
  perimeter uses a `*` that already matches files in the checkout refuses
  new files it declares. The fix is likely `set -f` in the script, plus a
  case in `ci/perimeter.sh`. The network adapter runs with `set -f`
  throughout and is not affected; ticket 0012 uses literal paths.
- `.gates-out/` at the repo root holds stale files from 15 September
  (`mutation.json` says 1 mutant, 0 killed). The tower's CI step copies
  back only `verdict.env`, so anything that reads the other files at the
  root reads old data. Harmless today; worth knowing for ADR 0031's
  report.
- A container named `recursing_shannon` was running on the shared podman
  machine. I did not touch it.

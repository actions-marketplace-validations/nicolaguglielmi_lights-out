# Handoff: M24 phase A, sqlparse dropped, tenacity ready but for one permission, 2026-11-10/11

Branch `claude/m24-phase-a-5dacb7`, cut from `main` at b395aff (0.3.1 released). Pushed; not merged, no PR,
nothing tagged. Nothing was forked, nothing pushed outside this repository, no project was contacted. No model
was called: phase B (live runs on Anthropic, authorized by the owner on 2026-11-10) did not start, see the end.

## The short version

- **The prerequisite was already closed** (the tower restores `runners/` from the base since 2026-11-04).
- **sqlparse is dropped** (the owner, 2026-11-10): its head commit is its end-of-maintenance announcement. Its
  local attach stays as a reference: baseline 0.794, base red at `sast`.
- **validators is the runner-up**, stopped because the auto-mode classifier refused to run its code; the owner
  dropped it from the comparison.
- **tenacity is the pick in progress**: maintained, no AI policy, two prep commits (a `uv.lock`, four reviewed
  `# nosec` lines), contract committed, five tests-only tickets that pass `spec` and can pass `test-proof`.
  Its base gates and phase B are blocked by the same classifier: **running tenacity's code needs the owner's
  permission in this session's settings.**

## 1. The prerequisite: already closed

`core/steps/ci.sh:79` (commit 3cb9bd5, ADR 0033's amendment of 2026-11-04) and `core/mainline.py:264` take
`${contract}runners` from `BASE_SHA` with `workload.env` and `policy.env`. Run, not only read: `./go ci-attach`
GO; with `${contract}runners` removed from `core/steps/ci.sh` it is `NO-GO: attach — case f disagrees with
docs/adr/0037 or 0033` (planted, reverted). No ADR was needed; 0067 is still free. ROADMAP and
`docs/launch/checklist.md` said otherwise and are corrected (0ffd7cb).

## 2. Findings that hold for any repository

1. **A red base stops every ticket.** `sast` counts bandit findings over the whole package, and `assign` refuses
   a red base (ADR 0053 §6, `core/base-gates.sh`). Its escape hatch is a reviewed `# nosec` per line, a human
   commit on code. sqlparse has one finding, tenacity four.
2. **`test-proof` refuses a ticket that adds a test of behaviour that already holds *and* touches a non-test
   file**, even a comment: the PR is not "only tests", and the test passes on the base. Tickets must be tests
   only, or code only. Three of sqlparse's five and two of validators' five were written that way in the
   shortlist; the dry run proved it on sqlparse-01 (NO-GO), and its tests-only variant GO.
3. **L0 cannot run a dev-worker on an attached repository** (ADR 0037 §8, `core/crew.sh`), and `assign` needs
   a code host: Gitea, which `./go up` starts only for a workload with a plane half. A library has none (ADR 0042
   §7), so its L1 runs need the plane started from a non-attached checkout, or GitHub.
4. **`./go init` gaps**: it does not draft `crew-egress.txt` (without it the worker's `uv run --locked` cannot
   reach PyPI at L1; added by hand, as `workloads/minimal/` has it), and titles `worker.md` with the clone's
   directory name (`.attached`); fixed by hand in each contract.
5. **Whole-scope baselines are long, and the host's sleep stretches them.** sqlparse: 2,944 mutants at about
   7–9 s each awake. tenacity: a mutant that loops forever costs cosmic-ray's timeout, 10× the clean run; the
   clean run measured 69 s with three jobs on the VM, so 690 s per looping mutant. The macOS host slept on
   battery several times (pmset), and keep-awake was refused by the auto-mode classifier.
6. **This podman VM** (recreated 2026-11-08) had no `/etc/containers/registries.conf.d`, so `./go up` died
   before any container. The owner created it and the Zot entry on 2026-11-11. `./go up` then started every
   service, but the final publish to Zot still failed (`http: server gave HTTP response to HTTPS client`):
   the rootful podman service most likely needs a restart to read the new file. Not restarted (it would have
   killed two running baselines). Gitea, all phase B needs, was up.

## 3. sqlparse, the reference (dropped)

- `/Users/nicola/Dev/m24/sqlparse`, `master` at 09dbe1e = "Release 0.6.1 and announce end of maintenance"
  (2026-11-01). The maintainer cites the volume of security reports "generated through automated vulnerability
  research". The shortlist read that commit on 2026-11-04 and called the maintainer active.
- Local branch `lights-out`, 9206d0b: init's contract, `worker.md` retitled, `crew-egress.txt`, five tickets.
  `uv.lock` was already upstream. Never forked.
- `TEST_CMD=uv run --locked pytest tests -q -p no:cacheprovider`: 537 passed, 2 xfailed, 1 xpassed, 2.25 s.
- **MUTATION_BASELINE=0.7938** (2,337 of 2,944 killed, 264 filtered), 44,263 s wall from 10:55 to 23:13 UTC,
  the host asleep for several hours of it.
- The base (09dbe1e..9206d0b) under every gate, each alone: `GO: risk` 2 s; `GO: secrets` 3 s;
  `GO: test-weakening — no test changed` 1 s; `GO: deps` 5 s (the whole `uv.lock`, no advisory);
  **`NO-GO: sast — in workbench: 1 SAST finding(s) in the workload's scope`** 3 s (B101 at
  `sqlparse/sql.py:244`, `assert end is None` in `TokenList._token_matching`); `GO: test — in workbench` 9 s;
  `GO: mutation — in workbench, nothing ran` 1 s; `GO: test-proof — nothing ran: no test changed` 1 s.
- Tickets sqlparse-01..05: all `GO: spec`, premises re-checked by running them (02's FIXME is stale: the
  look-behind rule fires; 05's output has no trailing newline). 01, 02, 05 cannot pass `test-proof` as written.
- `./go request` at L0 took each to `opened` (product role unrecorded → the request's own criteria), then
  `assign` stopped at the code host (no plane then).
- Gate half of the dry run, hand-written, `sast` left out: sqlparse-01 as written `NO-GO: test-proof — the
  changed tests pass on the base too`; its tests-only variant and sqlparse-04 `GO: gates — risk low,
  auto-merge`.

## 4. validators, the runner-up (stopped)

- [python-validators/validators](https://github.com/python-validators/validators), MIT, 1,134 stars, 22.5M
  PyPI downloads in the last month (pypistats). `master` at 22786cc, the shortlist's commit.
- **Maintained**: release 0.36.0 on 2026-10-10; collaborator `nandgator` merged eight PRs on 2026-10-22 and
  answered issues that day; PRs opened since 2026-10-26 have no reply yet. No end-of-maintenance notice.
- **No AI policy**: no AGENTS.md; nothing in README, CONTRIBUTING, SECURITY or the workflows; no org `.github`.
- `core/init.py` alone (reads files, runs nothing): `src/validators/`, workbench; `TEST_CMD` as drafted would
  not find pytest (it is in the `testing` group). Every ticket premise re-checked with ruff 0.15.0 at 22786cc.
- Tickets validators-01..05 (in the local clone, uncommitted): all `GO: spec`. **03 rewritten**: its `zip()`
  calls are equal-length by construction (`ru.py` checks the length first, `fi.py`'s regex admits 7 digits for
  7 factors), so the added test would pass on the base; now code only. **05 rewritten**: the refactor alone,
  the added branch tests dropped, the line-scoped mutation gate judging it. 01, 02, 04: code only, as written.
- **Why it stopped**: `./go init` on it was refused by the auto-mode classifier ("Code from External"). The owner
  dropped it from the comparison on 2026-11-10.

## 5. tenacity, the pick in progress

- [jd/tenacity](https://github.com/jd/tenacity), Apache-2.0, 8,831 stars, 337M PyPI downloads in the last
  month. `main` at aac059c, the shortlist's commit.
- **Maintained**: release 9.2.1 on 2026-10-07; the maintainer `jd` merged Python 3.15 support on 2026-10-12;
  outside PRs since 2026-10-07 are open, one reviewed by a contributor (`k4nar`). No end-of-maintenance notice.
- **No AI policy**: no AGENTS.md, no CONTRIBUTING; nothing in README or the workflows; jd's `.github` repository
  holds only FUNDING.yml.
- **Two prep commits, human, local only, to disclose in the diary**:
  - f6ccc93: `uv.lock` (uv 0.12.17, 57 packages), **force-added over tenacity's `.gitignore`**, which ignores it.
  - d52d99c: four `# nosec` comments, authorized by the owner on 2026-11-11: B101 at `tenacity/retry.py:259`
    (the assert narrows the type; `__init__` raises unless exactly one of message or match is set), B311 at
    `tenacity/wait.py:91`, `:276`, `:321` (jitter, not cryptography). ruff passes with tenacity's config.
- 98f0379 and b7a05bb: init's contract (`tenacity/`, workbench, `TEST_CMD=uv run --locked pytest tests -q -p
  no:cacheprovider`: 185 passed, 15 subtests, 19.66 s, its tests sleep for real), `worker.md` retitled,
  `crew-egress.txt`, five tickets, committed with `MUTATION_BASELINE` empty and labelled as being measured;
  **b7a05bb sets it: 0.869** (1,513 of 1,741 killed, 28 filtered), 16,827 s wall, 22:44 to 03:25 UTC, beside two
  other jobs on the VM. Looping mutants cost cosmic-ray's 690 s timeout each (10× a clean run measured at 69 s
  under that load). The scope includes `tenacity/_version.py`, which hatch-vcs writes at build time and git
  ignores: its version numbers were mutated too, a little noise in the score. Every ticket is tests-only, so
  `gates/mutation.sh:90` answers GO by absence and never reads the baseline for them.
- **Tickets tenacity-01..05**, all `GO: spec`, all tests-only, so `test-proof` passes each by absence:
  01 `stop_when_event_set` (made deterministic: the function sets the event on its third call); 02
  `sleep_using_event`; 03 `to_seconds` and `get_callback_name` (corrected: a `functools.partial` has neither
  `__qualname__` nor `__name__`, so it returns `repr()`); 04 an `async_retry_base` strategy under
  `AsyncRetrying`; **05 replaced**: the shortlist's (the `initial` deprecation) is already tested at
  `tests/test_tenacity.py:734` and `:740`, so 05 tests `_utils.wrap_to_async_func`, which no test names.
- **Not done**: the base under every gate. `./go gates` on aac059c..98f0379 was refused by the auto-mode
  classifier ("Code from External") on 2026-11-10 23:14 UTC, although `./go init` on the same clone had been
  allowed. A static bandit run says `sast` will be GO now.

## 6. Phase B: authorized, not started

The owner authorized live runs on Anthropic (credits that expire around 2026-11-12), `MODEL_PROVIDER=anthropic`,
`claude-code` for the dev-worker, locally, no public fork. Ready: the contract, the tickets, the prep, the
plane (`./go up APP_PORT=9000` from a non-attached checkout, `.crew/full3`; sih-live holds 8080). Blocked: every
step runs tenacity's code (gates, the worker's tests), which this session's auto-mode classifier refuses. The
commands, once the owner allows them or runs them:

```sh
# from .crew/full3 (bundled): the plane, for Gitea
./go up APP_PORT=9000
# from .crew/full, after ./go attach /Users/nicola/Dev/m24/tenacity (now at b7a05bb): the base, then each ticket
./go gates BASE=aac059c HEAD=b7a05bb
./go request TICKET=tenacity-04 PROFILE=l1 MODEL_PROVIDER=anthropic MODEL=claude-sonnet-5-5 AGENT_HARNESS=claude-code
```

`ANTHROPIC_API_KEY` goes in through the environment (`./go` passes the keys `.env.example` declares); it is
never written into a checkout.

## The owner's decisions, each with what it costs

1. **Allow tenacity's code to run in this session** (the auto-mode classifier refuses it), or run the commands
   above yourself. Without it neither the base gates nor phase B happen here.
2. **The fork, public on GitHub.** Not needed for phase B (local Gitea), needed to publish. Money: none. A
   public act that names tenacity; it carries the two prep commits.
3. **The OpenAI key** (absent). M24 runs every ticket on three providers; without it, two, and Gemini spend is
   not authorized now, so phase B is one provider.
4. **A spending cap per provider.** Prices read on 2026-11-10; budgets from `roles/`:

   | Provider, model | Price per 1M tokens (in / cached in / out) | One dev-worker attempt at its 2.6M cap, no cache | One ticket, worst (4 attempts, each reviewed) | Five tickets, expected | Five tickets, worst | Suggested cap |
   |---|---|---|---|---|---|---|
   | Anthropic, `claude-sonnet-5-5` | $2 / $0.10 / $10 | $6.10 | $38.50 | ~$55 | $193 | $60 |
   | OpenAI, `gpt-6.1-sol` | $2 / $0.10 / $10 (≤272K-token context) | $6.10 | $38.50 | ~$55 | $193 | $60 |
   | Gemini, `gemini-3.8-flash` | $0.75 / $0.075 / $3.75 until 2026-12-31, then doubled | $2.29 | $14.44 | ~$20 | $72 | $25 |

   How: `roles/dev-worker/role.env` `TOKEN_BUDGET=2600000`, `roles/test-reviewer/role.env` `1500000`,
   `policy/rework.env` `REWORK_MAX_ATTEMPTS=4`; the split 95.7 % input, 4.3 % output and thinking from
   `fixtures/0001/dev-worker/run.json` (2,329,279 in, 2,435,115 total, 32 calls, ~73k tokens per call, so
   OpenAI's short-context price). Every input token uncached, an upper bound; at 80 % cached one attempt is
   $2.32 / $2.32 / $0.95. "Expected" is 1.5 attempts per ticket and a review on half; tenacity's tests-only
   tickets are low risk, auto-merge, no review. The `product` role's clarify turns are not counted. Sources:
   [platform.claude.com/docs/en/about-claude/pricing](https://platform.claude.com/docs/en/about-claude/pricing),
   [developers.openai.com/api/docs/pricing](https://developers.openai.com/api/docs/pricing),
   [aistudio.google.com/docs/pricing](https://aistudio.google.com/docs/pricing).
5. **The order of the tickets.** Recommended: tenacity-03 and -05 (pure functions, `tests/test_utils.py`, no
   timing), then -01 and -04 (retry loops, `wait_none()`), last -02 (real sleeps, the one most likely to be
   flaky). The five perimeters overlap in pairs (`tests/test_tenacity.py`: 01, 02; `tests/test_utils.py`: 03,
   05), and `assign` holds a ticket whose perimeter overlaps an open PR's (ADR 0053 §5), so they run one after
   another, each merged before the next. M28's `MAP_BRIEF=on` for half of them is part of this choice.
6. **Publishing the verdicts**: the diary names the two prep commits on tenacity.

## Where things are

- Clones, local only: `/Users/nicola/Dev/m24/{sqlparse,tenacity,validators}`, branch `lights-out` in each
  (validators' has its tickets uncommitted); `/Users/nicola/Dev/m24/sqlparse-scratch` holds the dry run's draft.
- Checkouts of this branch under `.crew/`: `full` (tenacity attached at 98f0379), `full2` (tenacity's init, done at 03:25 UTC), `full3`
  (bundled, the plane's).
- The plane: down since 2026-11-10 23:15 UTC; the slot is free.
- Working notes: the shared notes folder, `m24-phase-a-notes.md`.

## Proofs

- `./go ci-attach` GO, and NO-GO on the planted regression (above).
- `sh gates/spec.sh` on every ticket: GO ×15 (5 sqlparse, 5 validators, 5 tenacity).
- `ci/docs-drift.sh` on the host with `MAP_EXCLUDE`: GO.
- `./go ci` from a clean clone under `.crew/`: GO, 197 s, on 8dcab41.
- The six workflows green on 8dcab41: ci 42922530010, stranger 42922529903, self 42922530000, package
  42922529920, podman 42922530062, site 42922612267 (dispatched). The docs-only commit after it records these ids.

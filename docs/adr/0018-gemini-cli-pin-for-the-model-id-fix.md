# ADR 0018 — The CLI pin moves, not the plan's model: `adapters/gemini-cli` pins the exact preview `@google/gemini-cli@0.61.0-preview.0`, the first published build that carries the merged fix for the silent Flash remap, in its own commit whose eval is one real L1 `record`; the pin returns to the stable channel at `0.61.0`; the fixture follows the eval run's verdict, not this decision

- Status: accepted (amends ADR 0017 §3 [the pinned CLI version is no longer `0.59.0`] and ADR 0017's "Contradicts the plan" section [the substitution was an upstream bug, fixed in the preview channel, not a standing property of the runtime]; closes ticket 0002)
- Date: 2026-09-16
- Milestone: between M5 and M6 (maintenance, no milestone)

## Context

ADR 0017 §3 pins `@google/gemini-cli@0.59.0` via a committed
`package-lock.json`. That version silently serves `gemini-3.5-flash` for
every channel that asks for `gemini-3.8-flash` (`-m`, `models/…`,
`settings.json`'s `model.name`), so `fixtures/0001/dev-worker/run.json`
honestly records `"model": "gemini-3.5-flash"` against a plan (§5) that
commits to `gemini-3.8-flash` for all six roles. Ticket 0002 holds the
finding; the facts below were verified live on 2026-09-16 and supersede
the draft of this ADR written the evening before.

1. **Four probes, same key, same call, inside the workbench container**
   (`gemini -p "Reply with exactly: OK" -m gemini-3.8-flash
   --approval-mode yolo --skip-trust --output-format json`, reading
   `stats.models`): `0.59.0` (stable, current pin) → `gemini-3.5-flash`;
   `0.60.0` (stable, published 2026-09-15 20:31Z, now npm `latest`) →
   `gemini-3.5-flash`; `0.61.0-preview.0` (published 2026-09-15 20:22Z,
   npm `preview` dist-tag) → `gemini-3.8-flash`;
   `0.61.0-nightly.20260915.g9c1b0a610` → `gemini-3.8-flash`.
2. **The fix** is `fix(core): preserve explicit versioned Flash model IDs`,
   google-gemini/gemini-cli#29252, merge commit
   `ed2ac40df67a319bf348bd7e3d10494696b31b38`, merged 2026-09-08T22:54Z.
   GitHub compare: `v0.60.0` is "diverged, behind 4" from that commit
   (branched before the fix; the probe agrees); `v0.61.0-preview.0` is
   "ahead 4, behind 0" (contains it, one commit past the probed nightly).
   The new stable `0.60.0` does not fix it, so "wait for the next stable"
   had already expired the evening the draft was written.
3. **Read in the v0.60.0 source, not guessed**: the remap is client-side,
   `packages/core/src/config/models.ts` (`resolveModel` →
   `isFlashModel(resolved)` remaps anything ending in `flash` to the 3.5
   rollout default; the fix narrows it to `isPromotableFlashModel`, i.e.
   only the bare `flash` alias), and
   `Config.hasGemini35FlashGAAccess()` in
   `packages/core/src/config/config.ts` (~line 3579) returns `true` for
   `AuthType.USE_GEMINI`, `USE_VERTEX_AI` and `GATEWAY` alike. Routing
   through Vertex AI inside the CLI has the same bug; "on Vertex we choose
   the model" only holds for a harness that is not the Gemini CLI.
4. **Release cadence** (Gemini CLI's own process): weekly preview → stable
   promotion; `0.61.0` stable is the expected first stable with the fix.

Plan §9's pinning rule asks for exact versions and a dedicated commit that
passes the evals; there is no `adk eval` suite before M7, so this ADR says
what the eval for a CLI bump is today.

## Decision

1. **Option 1 of ticket 0002: pin `0.61.0-preview.0`, exact.**
   `adapters/gemini-cli/package.json` requests it and `package-lock.json`
   is regenerated (resolved
   `https://registry.npmjs.org/@google/gemini-cli/-/gemini-cli-0.61.0-preview.0.tgz`,
   dependency tree otherwise unchanged, an 8-line lockfile diff).
   Provenance of the version string: the live probe in Context §1. The
   plan was to change nothing else; the eval of §3 found five things, each
   with a real run as provenance, and they ship in the same commit
   because the bump does not work without the first and is not measured
   without the rest:
   - `entrypoint.sh`: the per-role thinking alias was an abstract alias
     (no `model`) under `modelConfigs.aliases`; `0.61.0-preview.0` refuses
     to start (`Could not resolve a model name for alias
     "gemini-3.8-flash"`, `ModelConfigService.getResolvedConfig`), because
     an alias with no model in its chain shadows the model name. It now
     has the documented shape of the CLI's own built-in `gemini-3.5-flash`
     alias (`customAliases`, `extends: chat-base-3`, concrete
     `modelConfig.model`). Run 1, 38 s, no model call.
   - `run.sh`: the CLI also spends a few thousand tokens on a helper model
     (`gemini-3-flash-preview`, 7,624 of 1,394,455), so `stats.models |
     keys | first` — alphabetical — would have recorded the helper; the
     model that answered is now the one that spent the most tokens. And
     `run.json` is written before the final-message check, so a run that
     ends over budget still records which model answered — without this
     the sentence in §3 was false. Run 2.
   - `core/crew.sh` and `compose.yaml`: the backend test suite is written
     for the test image's layout (`app/backend/Containerfile`, stage
     `test`) and does not run from a checkout; both real models, 3.5 at
     M5 and 3.8 in run 2, spent their first ten-odd calls rediscovering
     that, and the M5 one fixed `conftest.py` inside its PR (ticket 0003).
     The workspace now gets the same layout as three git-excluded links
     and the crew service the same `OTEL_SEMCONV_STABILITY_OPT_IN=http`
     the test image sets. Verified in the crew container before run 3:
     the prompt's command passes 25 tests unchanged.
   - `roles/dev-worker/prompt.md`: the test command it gave (`python -m
     pytest`) did not work either — the venv is not on `PATH`; now `uv
     run pytest`, with a sentence saying the environment is not the
     place to look.
   - `roles/dev-worker/role.env`: `TOKEN_BUDGET` 5,000,000 → 10,000,000,
     provenance run 2 (7,575,131 accumulated by the budget hook over 38
     calls, denied before the first edit). This is the first budget
     measured with `THINKING=high` actually applied (Consequences).
2. **A numbered preview is a legitimate pin; a floating tag is not.** The
   lockfile resolves it to an immutable tarball with an integrity hash;
   `npm ci` in the crew image is byte-identical to a stable pin. What it
   costs is upstream review, for about one release week (Context §4), and
   §4 names the exit.
3. **The bump is its own commit and its eval is one real L1 run:
   `./go record TICKET=0001 PROFILE=l1`.** The assertion is `run.json`'s
   `"model"` field equal to `gemini-3.8-flash` (read from `stats.models`,
   ADR 0017 §3), **plus** that `adapters/gemini-cli/run.sh` still parses
   the new build's stream-json (the `message`/`result`/`stats` shapes were
   read from the 0.59.0 bundle) and that the hooks still fire
   (`hooks.log`). That is what a live agentic run proves and a one-line
   probe does not. The eval does not require the run to pass the gates: a
   failed attempt still reports which model answered and whether the
   adapter understood the stream.
4. **Return condition: the pin goes back to the stable channel when
   `0.61.0` stable is published**, by another dedicated commit passing the
   same eval as §3. No automation; the condition is written in
   `package.json`'s description (done), the README, and here.
5. **The fixture follows the eval run's verdict.** `fixtures/0001/dev-worker/`
   was recorded on `gemini-3.5-flash` (its `run.json` says so). The eval
   run of §3 *is* a `record`: if it passes the gates, `record` writes it
   as the new fixture, L0 replays a 3.8 run, and L0/L1 stop diverging by
   model generation. If it does not pass, the fixture stays exactly as
   recorded — replay is `cp` + `git am` (ADR 0017 §2), never invokes the
   CLI, so a pin it never used cannot invalidate it — its `run.json` keeps
   saying 3.5 honestly, and the README must say so.
6. **Plan §5 is not amended.** `gemini-3.8-flash` stays the runtime model
   for all six roles; this ADR removes the exception ADR 0017 had to
   declare, it does not legalise it.

## Alternatives rejected

- **`0.60.0` stable**: probed live, still remaps (Context §1, §2).
- **The nightly `0.61.0-nightly.20260915.g9c1b0a610`** (the draft's own
  choice, made when no preview existed): same fix, less review, a dated
  string that reads as stale by the next day, and no natural promotion to
  stable; dominated by the preview.
- **Correct the plan to `gemini-3.5-flash` (ticket option 2)**: encodes a
  merged-and-fixed upstream bug as a product decision, discards plan §5's
  reasons for 3.8, and makes L1 diverge from L2/L3 by model generation —
  plan §11's "L0 e L2 divergono" risk.
- **Route through Vertex AI (ticket option 3)**: the same remap runs under
  `USE_VERTEX_AI` (Context §3), so it is a non-fix, not merely a cost; it
  would also put L1 behind a GCP project with billing, the golden rule's
  boundary. Vertex stays the L2 path for its own reasons.
- **Floating `preview` or `nightly` dist-tag**: a different CLI on every
  image rebuild; plan §9 forbids it.
- **Vendor the fix as a patch over `0.59.0`/`0.60.0`**: a new dependency
  and a hand-maintained diff to reproduce a change upstream already merged.
- **A `ci/` check asserting the fixture's model string**: at L0 there is
  no model to ask, and the string it would read is one this repo wrote;
  the eval that means something needs a key, so it lives in §3.

## Consequences

- The crew image installs a pre-release for about one week. ADR 0017
  keeps this lockfile out of `gates/deps.sh`, so no advisory scan looks at
  it; the isolation boundary — no engine socket, no credential but
  `GEMINI_API_KEY`, no write path outside `/crew` (ADR 0017 §9) — is what
  has to hold either way.
- The budgets in `roles/dev-worker/role.env` (ADR 0017 §8) were measured
  on 3.5 without thinking; plan §5 says 3.8 deliberately spends more
  tokens on long tasks, and it did: the budget hook's per-call
  `totalTokenCount` sum (context re-sent every call, cached or not) runs
  at ~200,000–235,000 per call against ~140,000 on the 3.5 run. The
  CLI's own `stats.total_tokens` for the same runs is 3.5–5× lower
  (1,394,455 and 2,930,036): the two numbers measure different things and
  the hook's is the one the budget is enforced on.
- `entrypoint.sh` asks for the model in three places and none errors on
  an unknown ID; if a future CLI reintroduces a silent fallback, only §3's
  eval catches it.
- The thinking level per role (ADR 0017 §3, plan §5) was most likely
  never applied under `0.59.0`: the remap to `gemini-3.5-flash` happened
  in `resolveModel` before the alias lookup, so the alias keyed on
  `gemini-3.8-flash` was never consulted, and the recorded fixture ran on
  the CLI's default thinking for 3.5 Flash, not on `THINKING=high`. Read
  from the two code paths above, not measured: the 0.59.0 transcript does
  not record the thinking config it sent. The lever exists for real from
  this pin on; the eval run of §3 is the first run where it is known to be
  wired.
- Cost to a cloner: zero at L0 (`./go demo` and `./go demo-crew` never
  build the crew image, ADR 0017's golden-rule check); at L1, one `npm ci`
  of an immutable tarball, identical in mechanism to a stable version.
- **Outcome of the eval, 2026-09-16, three `record` attempts on the new
  pin (the number to compare with M5's six):** run 1 no model call (the
  alias, above); run 2 `gemini-3.8-flash` served, hooks firing, stream
  parsed, 38 calls all spent on the test environment, over budget at
  7,575,131 with no edit; run 3, after the five fixes, `gemini-3.8-flash`
  served (`run.json`: 2,924,026 of 2,930,036 tokens on it), the test
  command worked at the first call, the model edited exactly the ticket's
  four files, its tests passed, then it ran the mutation suite on its own
  four times (calls 34–43, one to two minutes each, the output of each in
  context) and was denied at 10,056,737 before writing the PR text.
  §3's assertion holds; the gates were not reached; per §5 the fixture
  stays as recorded on `gemini-3.5-flash`, and the README says so. The
  work of run 3 is kept under `.crew/0001` for M6, which inherits two
  measured facts: the mutation suite is the single most expensive thing
  the worker can call, and the prompt currently invites it to.

## Golden-rule check

A stranger with podman, git, sh, no key and no account is unaffected:
`./go demo` does not touch `adapters/gemini-cli`, and `./go demo-crew` at
L0 never builds the crew image and calls no model (ADR 0017, confirmed at
M5). `ci/hooks.sh` exercises `guard.sh` in workbench with no CLI installed.
The changed bytes on the L0 path are three git-excluded links the crew
workspace gets in `core/crew.sh` (replay applies the fixture over them
unchanged) and one environment line on a compose service the demo never
starts; everything else is on the L1 path only. `./go ci` and `./go
demo-crew` at L0 are the proof, in the same commit. Passes.

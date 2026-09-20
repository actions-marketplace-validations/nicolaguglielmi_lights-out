# ADR 0026 — `gates/delivery-conformance.sh`, concretely: four Delivery verbs (`ready.sh` is not one of them), `status.sh` is three keys and nothing else, six cases in a fixed order driven only through `core/`, forcing a NO-GO is the committed flag-targeting rule, and the freeze case needs two new `Flags` verbs

- Status: accepted (amends ADR 0024 §2 [the Delivery port's contract is four verbs plus the plane-wide `ready.sh`, not five Delivery verbs; the idempotent-rollback case is driven through the launchpad, not by calling `rollback.sh`]; ADR 0013 §4 and §6 [`deploy.sh` takes the image, ADR 0025 §6; the freeze flag and the kill switch move behind the `Flags` port]; ADR 0024 consequences [the flagd URL hardcoded in `core/launchpad.sh` is fixed here, not left open]; plan §4's `Flags` row). Amended 2026-09-20 by owner ruling: a sixth case, `refuses an image the Registry port cannot verify` — checked against the original five and none of them reaches the signature stage, so ADR 0022 §3's rule was the one thing in the suite that nothing exercised (§6 case 5, renumbering `reports state` to 6).
- Date: 2026-09-20
- Milestone: M8, before `adapters/cloud-deploy/` exists

## Context

ADR 0024 §2 fixed what the suite must prove — promotes, rejects and rolls
back, respects the freeze, reports state, rollback is idempotent — that it
drives the adapter only through `core/launchpad.sh` and `core/promote.sh`,
and that `envoy-canary` passes it first. It did not say how a case is set
up, what `status.sh` prints, or how the suite reaches a second level. The
suite is written from this spec before the second adapter exists
(CLAUDE.md), so every judgement call left open here becomes an
implementer's guess.

Two facts the ADR 0024 draft got slightly wrong, checked in the tree on
2026-09-20: `adapters/envoy-canary/ready.sh` polls the app through Envoy
and is called by `make up`'s loop over `PLANE_ADAPTERS`, not by the
launchpad — it is the plane-readiness probe every adapter of every port
owes (ADR 0012 §6), exactly like `adapters/zot/ready.sh`. And
`core/launchpad.sh` reads the freeze flag from a hardcoded flagd URL on
port 8016, which has no meaning at L2.

## Decision

1. **The Delivery port is four verbs.** `deploy.sh <version> <image>`,
   `shift.sh <pct>`, `rollback.sh`, `status.sh`. `ready.sh` is owed by
   every adapter the profile puts in `PLANE_ADAPTERS`, whatever its port,
   and the suite never calls it. None of the four is a gate (ADR 0012 §6):
   exit 0 in silence, or exit 1 with one stderr line.
2. **`status.sh` prints one JSON object with exactly three keys**, no
   arguments, on stdout:
   `{"stable":"0.1.0-m2","canary":"0.2.0-waitlist","weight":25}`.
   `stable` (string) is the version the revision serving the non-canary
   share reports at `/healthz`; `canary` (string or `null`) is the version
   the canary revision reports, `null` when no canary revision exists;
   `weight` (integer 0–100) is the percentage of traffic the delivery layer
   is sending to the canary revision. Exactly three keys: anything a vendor
   wants to add — a rollout name, a phase, a console URL — goes to stderr,
   or to a later ADR that adds it to every adapter at once.
3. **Two new `Flags` verbs, because the freeze case cannot cross levels
   without them.** `adapters/$FLAGS/evaluate.sh <flag> [version]` prints
   the flag's value; `adapters/$FLAGS/set.sh <flag> <variant>` sets its
   default variant. `core/launchpad.sh`'s `frozen()` calls `evaluate.sh`
   instead of curling port 8016, and the Makefile's `freeze`, `unfreeze`
   and `kill-switch` targets call `set.sh` — the in-place truncate-and-write
   and its flagd-inode reason (the Makefile's long comment) move into
   `adapters/flagd/set.sh`, where the vendor's behaviour belongs.
   `ci/vendor-free.sh`'s word list grows by `flagd|unleash`, as ADR 0024 §1
   said it would the day a second port's vendor left `core/`.
4. **The suite is `gates/delivery-conformance.sh`, `DELIVERY` from the
   profile, and it refuses to run by accident.** `ci/contract.sh` cold-runs
   every `gates/*.sh` inside `make ci`, where `DELIVERY` is already set, so
   the first thing the script does is require `CONFORMANCE=1` and answer
   `NO-GO: delivery-conformance — set CONFORMANCE=1: this suite drives real
   releases on the plane (./go delivery-conformance)` in one line,
   instantly, when it is missing. `make delivery-conformance` sets it. It
   is not a `./go demo` stage (ADR 0003's rule; the `demo-gates` and
   `demo-launch` precedent): the acceptance commands are
   `./go delivery-conformance` at L0 and `./go delivery-conformance
   PROFILE=l2`.
5. **Preflight, through the ports, never through the tree.** `DELIVERY`
   set; `evaluate.sh release-freeze` is `false`; `evaluate.sh waitlist
   $CANARY_VERSION` is `true` (without it the "rejects" case cannot fail,
   and a green suite would mean nothing); `status.sh` parses and reports
   `weight` 0. Each is a one-line NO-GO naming the fix. Every flag the
   suite changes is restored through `set.sh` in a trap on EXIT, INT and
   TERM (the `demo-hold` pattern, level-agnostic).
6. **Six cases, in this order.** The order is load-bearing: at L0 every
   canary revision reuses one `instance`, so two verified stages less than
   the `slo.promql` window apart attribute one canary's errors to the next
   (ADR 0013 §2). The header comment says so. (Cases 5 and 6 stage nothing,
   so they cost no window and could sit anywhere; they sit last because the
   drives come first.)
   1. **rejects and rolls back** — no setup, the committed targeting rule
      is the failure. `make release CANARY_VERSION=<the targeted version>
      CANARY_TAG=<the tag `up` published>`; expect exit 1, the stdout line
      `NO-GO: launchpad — 5%: …`, `RELEASE_RECORD.verdict == "rolled-back"`;
      then `status.sh.weight == 0`, `status.sh.stable == record.stable`, and
      10 of 10 `GET $APP_URL/healthz` report `stable` (10: ADR 0013 §4's
      decision, reused, not re-derived).
   2. **promotes** — setup `set.sh waitlist off` (the kill switch, which is
      how `demo-hold` already makes verify pass). `make release`; expect
      exit 0, `record.verdict == "held"`, `record.held_at == 25`, and
      `status.sh` = `{stable: record.stable, canary: record.version,
      weight: 25}`. Then `GO_FOR_LAUNCH=GO make promote`; expect exit 0,
      `status.sh.weight == 100`, and 10 of 10 healthz report the canary
      version. Teardown: one `make release` is not run again — the trap
      restores the flag and case 3 leaves traffic on stable.
   3. **respects the freeze** — setup `set.sh release-freeze on`. Snapshot
      `status.sh`. `make release`; expect exit 1 with exactly
      `NO-GO: launchpad — release-freeze is on`, `status.sh.weight == 0`
      and `status.sh.stable` equal to the snapshot's: the launchpad's
      opening rollback is the only thing that moved, no version was staged.
      No assertion on `RELEASE_RECORD`: the freeze path writes none, and
      the stale record from case 2 is still on disk.
   4. **rollback is idempotent** — the same frozen release a second time,
      immediately. Same three assertions. Two launchpad runs mean two
      `rollback.sh` calls with no deploy between them; neither is an error
      and `status.sh` says 100/0 both times. Driven through `core/`, as
      ADR 0024 §2 requires, instead of calling the adapter twice by hand.
      Teardown `set.sh release-freeze off`.
   5. **refuses an image the `Registry` port cannot verify** *(added
      2026-09-20, owner ruling)* — no setup. Snapshot `status.sh`.
      `make release CANARY_VERSION=<the snapshot's `stable`>
      CANARY_TAG=sha-0000000000000000000000000000000000000000`: a tag in
      exactly the shape every published tag has (ADR 0025 §1) and that no
      commit can produce. Expect exit 1, the stdout line exactly
      `NO-GO: launchpad — unsigned image`, and `status.sh` equal to the
      snapshot in all three keys — the check sits after the freeze check
      and before staging (ADR 0025 §6), so nothing was deployed. No
      assertion on `RELEASE_RECORD`, for case 3's reason. The refusal is
      forced by an *input* to the launchpad, not by a switch in the
      product: nothing can tell `verify.sh` to fail.
   6. **reports state** — not a drive of its own: the `status.sh` reads
      above are the case. It passes when all of them parsed as §2's three
      keys and agreed with the release record each time.
7. **The suite's stdout is one line** (`GO: delivery-conformance` or
   `NO-GO: delivery-conformance — <case>: <what disagreed>`); every
   release's stderr streams through. Runtime at L0, projected from ADR 0013
   §5's per-release arithmetic: case 1 ≈ 80 s, case 2 ≈ 150 s, cases 3–4
   ≈ 10 s, case 5 ≈ 5 s, about 4–5 minutes; measured at M8 close, no
   ceiling binds it.

## Alternatives rejected

- **Assert on Envoy's admin API, as `demo-rollback` does.** Vendor-specific
  and L0-only; the suite exists to be level-agnostic, which is why it reads
  `status.sh` and `$APP_URL/healthz`. `demo-rollback`, `demo-hold` and
  `demo-launch` keep their Envoy assertions: they prove the L0 plane, the
  suite proves the port. The duplication is deliberate and declared.
- **Let `status.sh` carry extra vendor fields.** The first extra field is
  the first thing a console or an audit reads from one adapter and not the
  other, and §4's rule is that an adapter adds no concept.
- **Force a NO-GO with a fault-injection knob (an env var the app reads, a
  stubbed metrics adapter).** A second failure mechanism to maintain beside
  the one the demo already tells a story about, and a verify that can be
  told to fail is a verify nobody believes.
- **Read and restore `app/flags/flags.json` directly.** The file is L0's
  flag store; at L2 the same flag lives elsewhere. Going through the port
  is what makes the same suite the L2 acceptance line.
- **A stub Delivery adapter in `ci/` so the suite runs cold.** ADR 0024
  already rejected a fake adapter; `CONFORMANCE=1` is one line and no mock.
- **Making the suite a `./go demo` stage.** Four to five minutes inside a
  budget that measures the path to the rollback.
- **Giving case 5 a genuinely unsigned image by building one outside
  `publish.sh`.** At L0 the workbench has an engine and could; at L2 it
  would take Cloud Build, and the case would carry the per-level branch
  every other case exists to avoid. The L2 gate that has to build one
  anyway does it instead (ADR 0027 §5).
- **A `--no-sign` flag on `publish.sh`, or a second verb that pushes
  unsigned.** A hole in the product opened for a test: the fault-injection
  knob rejected above, wearing a port's clothes.
- **Re-tagging the signed image and releasing the new tag.** A cosign
  signature is attached to the *digest*, so the re-tagged image verifies:
  the case would pass while proving nothing.

## Consequences

- `core/launchpad.sh`, `core/promote.sh` and the Makefile's three flag
  targets all change in M8 before `cloud-deploy` starts; `ci/promote.sh`
  and `ci/harness.sh` stub environments gain the two `Flags` verbs, or they
  break.
- `envoy-canary` gains `status.sh` and loses nothing; `ready.sh` stays
  exactly where it is and is documented as a plane probe, not a port verb.
- The suite and `demo-rollback`/`demo-hold`/`demo-launch` now prove
  overlapping things at L0 and both must be kept green. If one of them ever
  has to go, it is the suite that stays.
- At L2 the suite costs four Cloud Run revisions and a few minutes of
  Cloud Deploy rollouts per run; with Cloud SQL running (ADR 0022 §4) that
  is the run that must not be left half-finished, and the trap is what
  guarantees the flag store goes back.
- A NO-GO in case 1 that is really a broken *verify* looks like a broken
  *adapter*: the suite's reason quotes the launchpad's own line, which
  names the stage and the numbers.
- Case 5 proves that the launchpad refuses what the `Registry` port will
  not verify, that it refuses before anything moves, and that the line is
  the one ADR 0022 §3 fixed. It does **not** prove that cosign tells a
  signed image from an unsigned one, because no unsigned image can be
  produced through the ports. At L2 `gates/unsigned-refused.sh` (ADR 0027
  §5) builds one and closes that half against both locks; at L0 the only
  proof is ADR 0025 §2's one-off round-trip of cosign against Zot. Declared
  here rather than left to be discovered.
- Plan §7 M8 still says "cinque casi in ordine fisso" and is one word
  stale; the line is doc-scribe's to fix with the rest of M8's text.

## Golden-rule check

Nothing new to install and no account: at L0 the suite is three releases of
the image `./go up` already published, driven by the code the demo already
runs. It adds four to five minutes to a command a cloner never has to type;
`./go demo` is untouched. Case 5 adds seconds and no prerequisite: its
image is a tag that does not exist.

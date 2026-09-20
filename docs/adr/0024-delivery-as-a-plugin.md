# ADR 0024 — Delivery is a plugin: an adapter is a directory plus one profile line, `core/` never names a vendor and `ci/vendor-free.sh` proves it; one conformance suite is the entry requirement for every Delivery adapter; one cloud adapter at a time; Kubernetes with Argo Rollouts is the named third candidate

- Status: accepted (amends plan §4, §7 M8, §11, §12; ADR 0013 §4 [the Delivery adapter gains a fifth verb, `status.sh`]; consistent with ADR 0004 and ADR 0012 §4 [the container engine is a user choice, not an adapter]); amended by ADR 0026 [`ready.sh` is not a Delivery verb but the plane-wide readiness probe of ADR 0012 §6, so the port is four verbs, `deploy.sh` taking the image as its second argument; the five cases get their exact setup, `status.sh`'s three-key shape and a fixed order; the idempotent-rollback case is driven through the launchpad instead of calling `rollback.sh` twice; the flagd URL this ADR recorded as "found, not fixed" moves behind the `Flags` port]
- Date: 2026-09-20
- Milestone: plan amendment before M8 resumes; `ci/vendor-free.sh` lands now, the conformance suite lands in M8 before `cloud-deploy`

## Context

Plan §4 has said since M0 that the core knows no vendor and that the
Delivery port has two adapters, `envoy-canary` and `cloud-deploy`. The
first exists (ADR 0013): four scripts under `adapters/envoy-canary/` —
`ready.sh`, `deploy.sh`, `shift.sh <pct>`, `rollback.sh` — and `core/
launchpad.sh` and `core/promote.sh` call them as `adapters/$DELIVERY/…`
with `DELIVERY` from the profile. The second does not exist yet; M8 builds
it. Checked on 2026-09-20: `grep -rniE 'envoy|cloud.?deploy' core/` finds
one hit, a comment in `core/launchpad.sh` saying "no Envoy … word appears
below". The rule holds in the code and was violated, harmlessly, by the
sentence that claimed it.

What "vendor-free" buys is the ability to add a Delivery adapter without
touching `core/`. Nothing tests it, so nothing stops the day a Cloud
Deploy concept (a release name, a target, a rollout phase) leaks into the
launchpad as a special case. And nothing today says what an adapter must
do to count as one: `envoy-canary` is proven by `demo-rollback`,
`demo-hold` and `demo-launch`, all three wired to it by the L0 profile,
none of them stated as a contract the next adapter must meet.

The cost side: every cloud adapter is an account somewhere, a nightly
(M10) against it, and an API surface that moves on the vendor's schedule
(§9 "verify before writing" exists because Cloud Deploy, ADK and Gemini
CLI have all moved during this project). §11 lists the nightly's cost
once; it does not say what happens when there are two.

## Decision

1. **Plugin, proven.** Adding a Delivery adapter is `adapters/<name>/` plus
   `DELIVERY=<name>` in a profile. `core/` must not contain the name of any
   Delivery vendor, existing or planned, in code or comment. `ci/
   vendor-free.sh` (joins `CI_CHECKS`) greps `core/` for
   `envoy|cloud[ _-]?deploy|argo|rollouts` case-insensitive and NO-GOs with
   the hits. Comments count: "no Envoy here" is a coupling that turns false
   the day Envoy goes, and the one hit found today was exactly that. The
   word list grows with §4's Delivery column and §11's candidate list; it
   never shrinks.

2. **One conformance suite, five verbs.** `gates/delivery-conformance.sh`,
   parametrised by `DELIVERY`, is what an adapter must pass to be one. It
   drives the adapter only through `core/launchpad.sh` and `core/
   promote.sh`, never by calling the adapter's scripts directly, so that a
   passing adapter is proven to work with the core as it is. Five cases,
   each a `GO:`/`NO-GO:` line per CLAUDE.md's gate contract:
   - **promotes**: the GO path, staging → 5% → 25% held → `GO_FOR_LAUNCH=GO`
     → 100% (today `demo-hold` + `demo-launch`);
   - **rejects and rolls back**: a version that fails verify at 5% is
     back at 100/0 and the release record says `rolled-back` (today
     `demo-rollback`);
   - **respects the freeze**: with `release-freeze` on, the launchpad
     refuses before staging and nothing moved (today `./go freeze` + a
     release, not yet asserted as a case);
   - **reports state**: a fifth adapter verb, `status.sh`, prints stable
     version, canary version and canary weight as one JSON object; the
     suite reads it after each of the cases above and compares it with the
     release record. Added because four verbs can move traffic but none can
     say where it is, and the console (ADR 0023) and the audit need that
     answer from the adapter, not from a guess;
   - **rollback is idempotent**: `rollback.sh` twice is not an error and
     `status.sh` says 100/0 both times (ADR 0013's "rollback to a known
     state" opens every release with it).
   `envoy-canary` passes it first, at L0; `cloud-deploy` passes it at L2 as
   part of M8's acceptance. The suite is written in M8 before `adapters/
   cloud-deploy/` exists, so it is tested from the spec (CLAUDE.md), not
   from the second implementation.

3. **The container engine is not an adapter.** Podman rootless is the
   reference, docker is supported, and `./go engine-compat` (ADR 0012 §4)
   is the existing proof. It stays a host-side user choice
   (`CONTAINER_ENGINE`), outside §4's table, and this ADR adds nothing to
   it.

4. **One cloud adapter at a time.** Written into §11 and §12: the project
   carries exactly one cloud Delivery adapter (`cloud-deploy`). A second is
   written when someone pays for it — the account, the nightly project and
   the maintenance when the vendor's API changes — not before. A cloud
   adapter without a nightly is a mock with a logo.

5. **Third candidate, named now, built later.** When a third Delivery
   adapter is justified, the first choice is Kubernetes with Argo Rollouts:
   its analysis step reads PromQL natively, so `verify/slo.promql` stays
   the one query; it runs on any cluster, so it covers more users than a
   second single-vendor service; and it is the adapter most likely to be
   paid for by someone who is not on GCP. Naming it now keeps the word list
   of §1 honest and stops the question from being reopened at every talk.

## Alternatives rejected

- **Declare vendor-freedom in comments and trust review.** That is the
  state on 2026-09-20 and the one hit shows how it drifts. A grep is
  cheaper than a reviewer and never tired.
- **Test the plugin property by loading a fake adapter in CI.** Stronger,
  but it needs a fake Delivery adapter that satisfies the suite, which is
  a mock in the repo with no product use; the vendor-free grep plus the
  conformance suite on the real adapters gives the same guarantee.
- **Conformance by calling the adapter's scripts directly.** Faster, but
  it proves the scripts, not the plugin: an adapter could pass and still
  be unusable from the launchpad. Driving through `core/` is the point.
- **Derive `status.sh` from the release record instead of a new verb.**
  The record says what the launchpad decided; only the adapter knows
  where traffic actually is. The audit already cross-checks the state
  store against the code host for the same reason (ADR 0019 §6).
- **Build `cloud-deploy` and an Argo adapter together in M8 to prove the
  port.** Two accounts, two nightlies, twice the surface, for a proof the
  conformance suite already gives with one. Rejected by §4 of this ADR.
- **Make the container engine an adapter.** It is chosen on the host,
  before any profile is read, by the one tool the golden rule allows; an
  adapter would need a container to select it.

## Consequences

- `ci/vendor-free.sh` exists and is green; the one comment in
  `core/launchpad.sh` was rewritten. `CI_CHECKS` gains `vendor-free`.
- M8 grows by: the conformance suite (before `cloud-deploy`), the
  `status.sh` verb on `envoy-canary`, and "cloud-deploy passes the suite
  at L2" as an acceptance line. ADR 0013 §4's four-verb contract is five.
- `ci/vendor-free.sh` is scoped to Delivery on purpose. Found while
  writing it, recorded here, not fixed: `core/launchpad.sh` reads the
  freeze flag from a hardcoded flagd OFREP URL on port 8016 — the `Flags`
  port's vendor inside the core. Not a Delivery leak; the day `unleash` is
  built it moves behind `adapters/$FLAGS/` and the word list may grow a
  second port. (Fixed earlier than that: ADR 0026 §3 moves it in M8,
  because the freeze case of this suite cannot run at L2 otherwise.)
- The nightly (M10) runs on one cloud project because there is one cloud
  adapter; §11's cost row is one line, not a table.

## Golden-rule check

`ci/vendor-free.sh` is a grep, runs in the workbench in under a second,
and adds nothing the cloner needs. The conformance suite at L0 reuses
`demo-rollback`, `demo-hold` and `demo-launch`, which already run on every
push; the two new cases (freeze, idempotent rollback) are seconds. Nothing
new to install, no account.

# ADR 0022 — Local first, cloud optional: L0/L1 are the whole product, L2/L3 swap adapters and add no capability; image signing and signature verification exist at every level, first at L0; Cloud SQL is the one fixed cost in L2 and is declared as such

- Status: accepted (amends plan §3 and §7 M8; amends ADR 0019 §8 [image signing is no longer an "M8, cloud" item: it lands at L0 with a local key]; amends ADR 0001 in spirit [the four profiles are two groups, not a ladder]). §3's enforcement points amended by ADR 0025 §6 [the verifier is `core/launchpad.sh` through the `Registry` port's `verify.sh`, not a Delivery adapter's deploy step, because the message this ADR fixed names the launchpad; the tool is cosign 3.1.3 with `--tlog-upload=false` and `--insecure-ignore-tlog=true`] and ADR 0027 §5 [at L2 the port's check is the same cosign command against a KMS key; Binary Authorization is the platform's second lock, because its sigstore check turned out to be continuous validation only]
- Date: 2026-09-20
- Milestone: plan amendment before M8 resumes

## Context

The plan's §3 table read as a ladder: L0 at the bottom, "the lowest level",
L2 and L3 above it with the real thing. Nine milestones later the repo
disagrees with that reading. Every stage in the README's status table
(`up`, `deploy`, `rollback`, PR gates, ticket → PR, `e2e`, ADK roles,
go-for-launch, review) runs at L0 with real gates, a real canary, a real
state machine and a real human gate; L1 changes one adapter (the model is
live); no GCP milestone has been built. The golden rule (§2) says the
clone must reach the rollback without an account. A product whose complete
form needs a GCP project would break that rule quietly, by making L0 a
demo.

Owner's ruling on 2026-09-20: the local path is the primary path, GCP is
optional. Three things follow and needed checking before writing:

1. Does any capability exist only at L2? Read §3 and §7 M8 row by row
   against §4's adapter table. Every row has a local adapter already
   (`zot`, `envoy-canary`, `prometheus`, `flagd`, the emulators, `gitea`,
   `inproc`) except one: refusing an unsigned image. §3 gave "Binary
   Authorization" to L2 and nothing to L0. ADR 0019 §8 listed "image
   signing" under M8 next to Zot push and the runner socket. Workload
   Identity Federation and Secret Manager are not capabilities but the
   cloud's way of holding credentials the local plane does not have: L0
   has no key at all; L1 has the Gemini API key in `.env`, and
   `adapters/gemini-cli/hooks/guard.sh` blocks the worker from reading it.
2. What does L2 cost when nobody is testing? Cloud Run, Cloud Deploy, Pub/
   Sub, Firestore, Artifact Registry and Managed Prometheus bill on use or
   on storage that rounds to nothing for this repo. Cloud SQL bills per
   instance-hour while the instance is running (external constraint, GCP
   pricing). It is the one fixed cost, and the plan did not say so.
3. Where does the reader learn this? The README today puts Quick start
   after Status and Control plane, and the levels table after that; the
   GCP levels sit in the same table as the local ones with no marker of
   which is the product.

## Decision

1. **Two groups, not four steps.** §3's table keeps the four profiles but
   groups them: *Local — the product* (L0 replay, L1 live model) and
   *Cloud — optional* (L2, L3). The sentence that defines a level is: L0 is
   the complete platform, every capability, no account, no key; L1 is the
   same platform with a live model; L2 and L3 replace containers with
   managed services and add nothing the local plane lacks. `profiles/*.env`
   do not change (ADR 0001).

2. **No capability may exist only at L2.** Written into §3 and §12. The
   check is the §4 table: every port has a local adapter, and the local
   adapter enforces the same rule the cloud one does, not a weaker one.

3. **Image signing and verification at every level, first at L0.** The
   `Registry` port signs the image it pushes: at L0/L1 with a key pair
   generated at `./go up` under the gitignored `.crew/` (never in the repo,
   never in `.env.example`); at L2 with a KMS key. The `Delivery` port
   verifies the signature before the image enters staging: at L0 the
   `envoy-canary` adapter's deploy step; at L2 Binary Authorization. An
   unsigned or mis-signed image is `NO-GO: launchpad — unsigned image`,
   printed by the same gate contract as every other gate (CLAUDE.md). The
   tool that signs (cosign is the obvious candidate; Zot serves OCI
   referrers) is M8's decision to verify against current docs, not this
   ADR's: this ADR fixes the rule and the two enforcement points, not the
   binary.

4. **Cloud SQL is declared as the one fixed cost.** §3's table gains a
   `Database dell'app` row: Postgres in compose at L0/L1, Cloud SQL at L2/L3
   with the note that it does not scale to zero. `infra/README.md` (created
   now, before `infra/` has any Terraform) says the same in English with
   the instruction to stop or delete the instance between test runs, and
   `./go down PROFILE=l2` must stop the instance, not only tear down the
   services that scale to zero on their own. Locally the database stays a
   container.

5. **README order.** Quick start (local, no account) first; then the §3
   table with its two column groups; then the rest of the product; the GCP
   section last, opening with "everything below is optional" and the Cloud
   SQL cost line, and absent from the quick start. The reorder lands with
   M8, the milestone in which the GCP section stops being a plan; today's
   README keeps its "Only L0 exists today" sentence and gains only the two
   column-group headers and the cost line.

## Alternatives rejected

- **Drop L2/L3 from the plan.** The talk is about a Google stack and the
  port/adapter table is the argument that L0 and L2 do not diverge (§11).
  Removing the cloud removes the second adapter of every port, which is
  the only proof the ports are real.
- **Keep signing cloud-only and declare it in the README.** Honest, but it
  makes "nothing reaches production unsigned" a GCP feature and L0 a demo
  of it. That is exactly the reading this ADR removes. Declaring a gap is
  for things a laptop cannot do; a laptop can sign.
- **Commit a demo signing key so L0 needs no key generation.** Violates
  "no secrets in the repo, not even in examples" (CLAUDE.md), and a
  committed key proves nothing: anyone can sign with it.
- **Replace Cloud SQL with AlloyDB or Cloud Run + a Postgres container.**
  AlloyDB has the same fixed cost; a Postgres container on Cloud Run has
  no durable volume and would be a hidden mock of a database. The
  honest answer is to declare the cost and stop the instance.
- **Warn about the cost only in Terraform output.** The reader decides
  whether to run `terraform apply` before seeing its output. The plan and
  `infra/README.md` are where the decision is made.

## Consequences

- §3, §7 M8, §8 step 5, §11 and §12 of the plan are amended; `infra/
  README.md` exists with one job until M8 fills the directory.
- M8's acceptance grows by three items: local signing and verification at
  L0 before any GCP work; `./go down PROFILE=l2` stops Cloud SQL; the
  README reorder. M8's "same hashes in `gates/` and `verify/` at L0 and L2"
  test now also covers the signature check, because the check is a gate.
- ADR 0019 §8's "image signing: M8" stays true but no longer means "L2":
  it means "M8, at L0 first".
- The nightly on L2 (M10) must delete or stop the Cloud SQL instance at
  the end of every run, or the "disposable project" mitigation in §11 is
  incomplete.

## Golden-rule check

Nothing changes for the cloner: `./go demo` still needs podman, git and a
shell. Key generation at `./go up` adds one local step with no account and
no network; the signature check adds one verify step to the launchpad,
measured against the 900 s budget when M8 builds it. The clone gains a
capability it did not have (a refused unsigned image) rather than a
prerequisite.

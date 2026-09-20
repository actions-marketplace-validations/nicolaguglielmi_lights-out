# ADR 0025 — The release artefact at M8: a Gitea Actions job on `main` builds the merge commit and the `Registry` port signs it (`publish.sh`), the launchpad verifies the signature before staging (`verify.sh`) and deploys the digest it verified; `CANARY_TAG` joins `CANARY_VERSION`; cosign 3.1.3 with the offline flags; the "stable image, not built from merge.sha" placeholder is retired

- Status: accepted (amends ADR 0013 §4 [the Delivery adapter's `deploy.sh` takes a second argument, the image; the launchpad gains a signature stage]; ADR 0015 §7 [the runner socket lands here, under its three unchanged conditions]; ADR 0019 §4 [the first Gitea Actions job is the image build, not the PR-gates job], §5 [the canary is the merge commit's image; the declared gap is retired] and §8; ADR 0022 §3 [the signature is verified by the launchpad through the `Registry` port, not inside a Delivery adapter's deploy step]; plan §7 M8 and §4's `Registry` row). Consequence 1 (the gitleaks allowlist) amended 2026-09-20 by owner ruling: an exception on a file name is how a real key gets through one day, so the allowlist is scoped and proved inert — see Consequences. §2's "no network beyond the local registry" amended 2026-09-20, found building Track 1: the local registry itself needed one-time engine configuration on podman, not none — see §2's dated note and Consequences. §2's flag pair amended again the same day: `--tlog-upload=false` alone now conflicts with cosign 3.1.3's signing-config default; `--use-signing-config=false` restores it.
- Date: 2026-09-20
- Milestone: M8

## Context

`core/launchpad.sh` builds nothing. `CANARY_VERSION` is a version *string*
that an already-built tag reports at `/healthz`, `backend-canary` runs
stable's local tag, and `record()` writes the literal
`"image": "stable image, not built from merge.sha (M8)"` — a gap declared
in ADR 0019 §5, printed by `./go audit` on every run, and owed by M8
together with the runner socket (ADR 0015 §7's three conditions, re-dated
three times) and the push to Zot. ADR 0022 §3 added the rule that the
`Registry` port signs what it pushes and the image is verified before
staging, at every level, and left the binary to M8 "verified against
current docs".

Verified on 2026-09-20: cosign 3.1.3 (GitHub release 2026-08-06,
Apache-2.0) still generates a local key pair (`cosign generate-key-pair`)
and signs with it (`cosign sign --key`); on 3.x the sigstore bundle format
and OCI 1.1 referrers discovery are the *defaults*, so `--experimental-oci11`
is gone; a key-based signature is uploaded to Rekor unless
`--tlog-upload=false`, and verifying such a signature needs
`--insecure-ignore-tlog=true`. Zot is OCI-native and serves the referrers
API. Nothing in ADR 0022's assumption broke; the flags did.

## Decision

1. **Two `Registry` verbs, no new port.** `adapters/$REGISTRY/publish.sh
   <tag>` turns the current checkout into a signed image and prints its
   immutable reference (`<repo>@sha256:…`) on stdout: build, push under
   `sha-<full 40-hex commit sha>`, sign. `adapters/$REGISTRY/verify.sh
   <tag-or-ref>` verifies the signature and prints the immutable reference
   it verified; exit 1 and one stderr line otherwise. Not gates (ADR 0012
   §6). The build lives inside `publish.sh` because it is level-specific
   (the engine at L0, Cloud Build at L2, where no local engine exists) and
   because a `Builder` port would add a row to plan §4's closed table for a
   step with one consumer. §4's `Registry` note becomes "builds, signs and
   pushes (`publish.sh`); verifies and resolves to a digest (`verify.sh`)".
2. **cosign 3.1.3, in the base workbench, pinned per arch by sha256**
   through `fetch.sh` (ADR 0004 §1). L0/L1: `cosign generate-key-pair` at
   `./go up` if `.crew/cosign.key` is absent (gitignored, passwordless,
   never in the repo — its one job is to prove the mechanism); sign with
   `--key .crew/cosign.key --tlog-upload=false`, verify with
   `--key .crew/cosign.pub --insecure-ignore-tlog=true`. Both flags are
   what make the whole path work with no account and no network beyond the
   local registry (provenance: external constraint, cosign docs read
   2026-09-20). L2 replaces both keys with one `--key gcpkms://…` (ADR
   0027). The implementer round-trips cosign 3.1.3 against the pinned Zot
   2.1.21 *before* wiring anything; if referrers do not round-trip, the
   fallback is cosign's legacy tag-based signature layout, chosen by the
   flag `cosign sign --help` names that day, and the README says which one
   is in use.

   *Amended 2026-09-20, found running the round-trip this point already
   asked for:* referrers round-tripped cleanly, no fallback needed. But
   `--tlog-upload=false` alone, sufficient when this ADR was written, now
   conflicts with cosign 3.1.3's newer default: `--use-signing-config`
   (default `true`, a TUF-provided signing config) wins over
   `--tlog-upload=false` and cosign refuses to sign — "not supported with
   --signing-config or --use-signing-config". The fix is one more explicit
   flag, `--use-signing-config=false`, which restores the plain behaviour
   this ADR's flag pair expected; `cosign verify`'s `--insecure-ignore-tlog`
   has no such conflict. `adapters/zot/publish.sh` carries the flag and the
   reason inline.

   *Amended 2026-09-20, found building Track 1:* "no network beyond the
   local registry" held, but reaching it did not need *no configuration* —
   real docker treats `localhost`/`127.0.0.1` registries as plain HTTP by
   default; rootless podman does not, and `docker-compose push` to
   `localhost:5050` fails with an opaque API 500 until the engine is told,
   once, that this one host is insecure. `./go` does this itself now, the
   first time `up` runs, exactly where it already generates the cosign key:
   a podman-machine VM (macOS, Windows) gets
   `/etc/containers/registries.conf.d/999-lights-out-local.conf` written
   over `podman machine ssh`, root, because the daemon lives in the VM, not
   the host; native rootless podman (Linux, no machine) gets the same entry
   in the user's own `~/.config/containers/registries.conf.d/`, no root.
   Idempotent, scoped to exactly `localhost:5050`, disclosed on stderr the
   one time it writes. Docker needs nothing. This is not a capability that
   exists only for one engine (ADR 0022 §2's rule is about the product, not
   the plumbing): both engines end up trusting the same one host, docker
   because it always did, podman because `./go` now tells it to.
3. **`./go up` publishes stable.** After readiness, `up` generates the key
   pair if needed and runs `make publish TAG=sha-$(git rev-parse HEAD)`, so
   a signed image exists before any release and Zot stops being empty. The
   push is idempotent (layers already present) and the engine already has
   the image it just built, so the canary never pulls over a network.
4. **The first Gitea Actions job is the image build.** `.github/workflows/
   ci.yml` gains one job, `image`, guarded
   `if: github.server_url != 'https://github.com' && github.ref ==
   'refs/heads/main'`, whose only step is `run: ./go publish TAG=sha-$GITHUB_SHA`
   (the repo's `- run: ./go …` shape). It checks out with `git` in a `run:`
   step from `$GITHUB_SERVER_URL/$GITHUB_REPOSITORY` at `$GITHUB_SHA`, not
   with `actions/checkout`: the runner resolves actions from github.com, and
   an action download on the L0 demo path would be a network dependency the
   golden rule does not need. The runner gets the engine socket under ADR
   0015 §7's three conditions, all three still true and now checked: the
   runner is the only compose service with the socket (workbench is not a
   compose service); the only writer to this Gitea is the tower, on `main`,
   with Actions enabled for the one repo and no external webhook; the
   README's L0 trusted-network line gains "and the Gitea runner controls
   your container engine".
5. **The tower waits for the status, not for the image.** One `CodeHost`
   verb, `adapters/$CODE_HOST/await.sh <sha> <context>`, polls the commit
   status until it leaves `pending` and prints its state; `core/steps/
   release.sh` calls it for context `image` on `merge.sha`, then sets
   `CANARY_TAG=sha-<merge.sha>`. A failed job is a precise NO-GO naming the
   job, not a timeout. `IMAGE_TIMEOUT=300` s, provenance decision: a third
   of plan §2's 900 s is the most a build may take before the run is worth
   failing; re-measured at M8 close and lowered to 3× the measured build if
   that is smaller.
6. **The launchpad verifies, then deploys the digest.** New required
   variable `CANARY_TAG` (the tag the Registry port published under);
   `CANARY_VERSION` keeps its exact meaning — the version string the
   revision reports, the string `app/flags/flags.json` targets and
   `slo.promql` selects by — and the two are orthogonal. Between the freeze
   check and staging, the launchpad runs `image=$(sh adapters/$REGISTRY/
   verify.sh "$CANARY_TAG")` and on failure prints
   `NO-GO: launchpad — unsigned image`, the line ADR 0022 §3 fixed, with
   cosign's own words on stderr. Staging becomes `deploy.sh <version>
   <image>` (amends ADR 0013 §4's three-argument-less contract; an image is
   not a vendor concept — it is the one thing every Delivery adapter
   deploys). Verifying by tag and deploying the digest `verify.sh` returned
   closes the gap between the two reads.
7. **The placeholder is retired.** `core/launchpad.sh`'s `record()` and
   `core/steps/release.sh` write the verified digest reference in `image`;
   `./go audit` prints it unchanged; the README and `docs/ARCHITECTURE.md`
   sentences that declare the gap (ADR 0019 §5) are deleted, not softened.
   M8 is not closed while either file still contains the string
   `not built from merge.sha`.

## Alternatives rejected

- **Verification inside each Delivery adapter's `deploy.sh`** (ADR 0022
  §3's literal wording): an adapter skips it by omission, and a
  non-gate script (ADR 0012 §6) can only exit 1, which the launchpad
  reports as "deploy did not become healthy" — the wrong reason for the
  right refusal. §3 fixed the *message*, and the message says `launchpad`.
- **`core/` builds the image itself**: unimplementable at L2, where there
  is no local engine, and it leaves the runner idle — which ADR 0019's
  consequence says is enough to keep M8 open.
- **Moving the PR gates onto the runner at M8** (ADR 0019 §4's "A is due at
  M8"): the gates already run, are consumed and are posted as a status; the
  move buys a second executor for the same six verdicts and needs the
  `github` CodeHost to be worth it. It goes with the milestone that runs
  the tower on GCP (M10's nightly), and ADR 0019 §4 is amended to say so.
- **`actions/checkout@v4` in the job**: puts a github.com round trip inside
  the L0 demo; mirroring actions locally is a bigger mechanism than a
  `git clone`.
- **A moving `:latest` or `:stable` tag**: two names for one artefact and a
  tag that can be repointed under a verified signature.
- **Signing with openssl and a hand-rolled layout**: inventing a signature
  format to avoid one 
  pinned binary, and nothing at L2 would consume it.
- **Committing a demo key** (ADR 0022 already rejected it) and
  **password-protecting the L0 key**: the password would have to live
  beside the key.

## Consequences

- `./go ci` breaks after `./go up` unless `ci/secrets.sh` is fixed first:
  `gitleaks dir .` scans gitignored files (the `.crew/.uv-cache` false
  positives in HANDOFF M9 are the precedent) and cosign's
  `-----BEGIN ENCRYPTED SIGSTORE PRIVATE KEY-----` <!-- gitleaks:allow -->
  matches its private-key rule. The fix is an allowlist for the one exact
  path `.crew/cosign.key`,
  with the reason in the config — ADR 0002's "no allowlist file" ends here.

  *Amended 2026-09-20, owner ruling:* an exception on a file name is how a
  real key gets through one day. The allowlist stays and is scoped so that
  the only file it can match is one that cannot be committed, and
  `ci/secrets.sh` says so out loud every run:
  1. *It never sees a commit.* The config lives at
     `ci/gitleaks-worktree.toml` — **not** `.gitleaks.toml`, **not** at the
     repo root, so gitleaks never loads it on its own. `ci/secrets.sh`
     passes it with `-c` to the working-tree scan only; `gitleaks git`
     keeps running with no config, so no allowlist can hide anything that
     was ever committed.
  2. *Path and content, not path alone.* One `[[allowlists]]` entry,
     `condition = "AND"`, `paths` anchored to exactly
     `^\.crew/cosign\.key$` and `regexes` the literal
     `-----BEGIN ENCRYPTED SIGSTORE PRIVATE KEY-----` <!-- gitleaks:allow -->
     with `regexTarget = "match"`; `[extend] useDefault = true` keeps every
     default rule. (`condition`, `regexTarget`, `paths` and `regexes` read
     2026-09-20 in gitleaks' config documentation; the array form predates
     the pinned 8.30.1, and the implementer confirms the exact path string
     8.30.1 reports — `.crew/…` or `./.crew/…` — before anchoring.) A
     same-named file holding anything else is still a finding, and an
     anchor that is wrong fails *closed*: the key is reported and `./go ci`
     goes red.
  3. *The path cannot be committed, checked before either scan.*
     `ci/secrets.sh` asserts `git check-ignore -q -- .crew/cosign.key`
     exits 0 and `git ls-files --error-unmatch -- .crew/cosign.key` does
     not (not tracked, not staged). Each failure is its own one-line NO-GO
     naming `.gitignore`, so the day the ignore rule stops covering the
     path the gate says it, instead of quietly starting to allowlist a real
     key. The checks live in `ci/secrets.sh`, not in a gate of their own:
     the gate that carries the exception is the gate that proves it inert.
- `./go demo` now depends on a Gitea Actions job: a flaky runner makes the
  demo red for a reason that has nothing to do with the canary. This is the
  consequence that will hurt. The mitigation is only that the failure is
  precise (§5) and that `demo-rollback`, the controller-only proof, does
  not go through the runner.
- Cold `./go demo` was 684 s of 900 at M7 close. This adds a push at `up`, a
  verify per release (~1 s × 2) and a build job inside `e2e`; the workbench
  split (ADR 0028) removes 474 MB of downloads from the same run. Both are
  projections: M8 close measures the cold run again, and the budget verdict
  is the gate.
- `compose.yaml`'s `backend`/`backend-canary` `image:` fields become
  registry-qualified and `CANARY_IMAGE`-driven; `localhost:5050` is the one
  registry host both engines treat as insecure without configuration, and
  the implementer confirms the push and the digest pull on podman and
  docker before the milestone closes.
- A second key material path exists at L0 that a `./go clean` does not
  remove; `.crew/` deletion regenerates it at the next `up`.
- The refusal §6 promises is exercised, not assumed: ADR 0026 §6 case 5
  drives the launchpad with a tag the `Registry` port never published and
  asserts the exact `NO-GO: launchpad — unsigned image` line at every
  level, and at L2 `gates/unsigned-refused.sh` (ADR 0027 §5) repeats it
  against a real unsigned image before the platform's own lock.
- `ci-engine-compat` (`ci/engine-compat.sh`, the host-side gate) is why the
  podman/docker registry-trust gap above went unnoticed until an actual
  build: on this machine it only ever tests podman (it refuses
  `CONTAINER_ENGINE=docker` once it detects the binary is a podman shim,
  its own existing behaviour), and the workflow's three GitHub-only jobs
  (`engine-compat`, `gates`, `launch`) all set `CONTAINER_ENGINE: docker`
  on `ubuntu-latest`, real Docker, where this problem does not exist. So
  podman — the reference engine (ADR 0004) — has no CI coverage at all for
  anything push-shaped; only a developer's local `./go engine-compat` (or
  `./go demo`) exercises it. The gate proves less than its name suggests;
  worth a dedicated podman leg in CI if this repo ever gets a
  podman-capable runner, not attempted here.

## Golden-rule check

The cloner gains one pinned binary in the workbench (cosign, roughly the
size of the 474 MB that leaves it in ADR 0028), one generated local key,
and a local registry push. No account, no API key, no network beyond what
`./go demo` already needed. On podman, `./go up`'s first run also writes
one local, idempotent, scoped-to-`localhost:5050` registry-trust entry
(amended §2) — disclosed, not asked for, the same bar `./go` already meets
for the cosign key. What the clone gains is the thing ADR 0022 promised:
an unsigned image is refused at L0, and the canary it rolls back is really
the merge commit. Passes, with the budget re-measured at M8 close.

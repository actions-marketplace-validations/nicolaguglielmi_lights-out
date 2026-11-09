# ADR 0057 — The stepped way in: a gates image, the Action at the root, two standalone Actions, doctor per level, a production-readiness gate

- Status: accepted
- Date: 2026-11-08
- Milestone: M31
- Amends ADR 0028 (its split was never built; gcloud and terraform leave
  the base now, the cloud flavour is written with L2), ADR 0004 §1 (one
  Containerfile, two stages), ADR 0045 §1 (`workbench/Containerfile` is
  no longer unchanged; its rejected "slim package image" is answered by
  one file), §2 (two subcommands, a default image per command), §5 (the
  Action at the root, a `gates` input, a summary per gate), §7 (keyless
  signing) and its first consequence (on an outside repository the 300 s
  include the first pull). Consistent with ADR 0033 (a range is judged
  by its base), 0026 (the conformance suite), 0044 §8 (`promql`,
  `METRICS_URL`), 0047 §5 (`CONSOLE_LAUNCHERS`), 0049 (self.yml), 0051
  (`argo-rollouts`), 0052 §1 (`core/doctor.sh` is host shell) and 0053
  (`test-proof`, `test-weakening`).

## Context

Plan §16 M31 and its amendment of 2026-11-08: a passer-by and a team going
to production enter by the same long README and a 15-minute demo. The
roadmap (docs/plans/adoption-roadmap-2026-11.md §5–§6, K1) makes the gates
the front door. Facts, verified 2026-11-08:

- `workbench/Containerfile` still fetches gcloud and terraform, which ADR
  0028 moved out; no file calls either (git grep; the compose emulators
  use their own image). ADR 0028's measure: 474 MB (gcloud 368, terraform
  106), M7 close, 2026-09-16. The full image is 1.77 GB unpacked, measured
  at M23 close (plan §16 M23). `unzip` serves terraform only.
- No gate or init path needs the ADK venv: `core/risk.py`, `testdiff.py`,
  `spec.py`, `init.py`, `policy.py` are standard library; the stack
  runners fetch bandit, cosmic-ray, eslint and Stryker with uv or npm at
  run time. The gates need debian with git, make, jq, python3, curl,
  ca-certificates, procps, xz-utils; node, uv, gitleaks, osv-scanner.
- GitHub Marketplace (docs.github.com, "Publishing actions in GitHub
  Marketplace"): "Each repository must contain a single action metadata
  file (action.yml or action.yaml) at the root"; metadata files in
  sub-folders are allowed but not listed; the name must be unique; 2FA;
  publishing is a release drafted from the `action.yml` banner with a
  primary category. One listed Action per repository.
- GitHub changelog of 2025-11-07, in force 2025-12-08: for
  `pull_request_target` "the workflow file and checkout commit will always
  be taken from the repository's default branch".
- Argo Rollouts, "Pause Duration": "If no duration is specified for a pause
  step, the rollout will be paused indefinitely", resumed by `kubectl argo
  rollouts promote`. Flagger, "Manual Gating": `confirm-promotion` hooks
  run before promotion and "the canary promotion is paused until the hooks
  return HTTP 200".

## Decision

1. **gcloud and terraform leave `workbench/Containerfile` now**, with
   `unzip`, their `ARG`s, `/opt/google-cloud-sdk` on `PATH` and the
   `CLOUDSDK_*` env. `workbench/cloud/` is written the day L2 is.
2. **One Containerfile, two stages**, so every pin and hash stays in one
   file. `FROM debian:… AS gates`: the apt packages above, `fetch.sh`,
   node, uv, gitleaks, osv-scanner, the `GIT_CONFIG_*` safe.directory env
   and `UV_LINK_MODE=copy` (the runners call uv). `FROM gates AS
   workbench`: docker-compose, actionlint, shellcheck, cosign, kubectl,
   the ADK venv, `PATH`, `LIGHTS_OUT_WORKBENCH=1`, the version check,
   `CMD`. `./go` builds the last stage with no `--target`: its tag (the
   cksum of the Containerfile, `pyproject.toml`, `uv.lock`) and its callers
   are unchanged. The Gitea runner stays `FROM` the workbench.
3. **Two images from that file**, by `package/build.sh`, chosen by
   `PACKAGE_FLAVOUR=gates|full` (default `full`): `ghcr.io/nicolaguglielmi/
   lights-out:<v>` (the workbench stage plus `package/Containerfile.tail`,
   as today) and `ghcr.io/nicolaguglielmi/lights-out-gates:<v>` (the gates
   stage plus the same tail). In the gates image `triage` and `postmortem`
   are one NO-GO naming the full image. Size: 508 MB unpacked on amd64
   (508,497,696 bytes, `docker image inspect`, package.yml run 42519069964
   on 0a0d073); 529 MB on arm64 under podman. The roadmap's "under 400 MB"
   is a proposal, not a threshold: the measure is recorded, no gate judges
   it. What the gates run is what it holds: the apt layer (git with perl,
   python3, make, jq, curl) 166 MB, node 118 MB, osv-scanner 52 MB, uv
   41 MB, gitleaks 20 MB (arm64, measured 2026-11-08); node's C headers
   (65 MB) are left out of both stages, since no image has a compiler for
   a native addon.
4. **Keyless signing** through GitHub's OIDC (owner decision, 2026-11-08),
   on the `publish` job only (a `v*` tag or `workflow_dispatch`, the
   owner's acts): `cosign sign --yes <image>@<digest>` for both images, on
   the multi-platform index; `id-token: write` on that job alone. No key,
   no secret. The README's check:
   `cosign verify ghcr.io/nicolaguglielmi/lights-out-gates:<v>
   --certificate-identity-regexp '^https://github.com/nicolaguglielmi/lights-out/.github/workflows/package.yml@refs/tags/v'
   --certificate-oidc-issuer https://token.actions.githubusercontent.com`.
5. **The wrapper, `lights-out` 0.3.0** (the next tag's). `init`, `gates`,
   `test-proof`, `test-integrity` default to the gates image; `triage`,
   `postmortem` to the full one; `LIGHTS_OUT_IMAGE` overrides every
   command; `doctor` checks the gates image. `test-proof` runs `GATES="test
   test-proof"` (test first: test-proof's GO means the changed tests fail
   on the base, which proves nothing if they fail on the head too, ADR
   0053 §2); `test-integrity` runs `GATES="test-weakening mutation"`. Each
   prints one line named for itself: `GO: test-proof — <the gates' details
   joined by "; ">` or `NO-GO: test-integrity — <failed gate>: <its
   reason>`. ADR 0045's contract holds: repository read-only, no engine
   socket, a range judged by the contract at its base (ADR 0033).
6. **The Action moves to `action.yml` at the root**, the only file the
   Marketplace lists. `action/` is removed, not redirected: `uses:` takes
   no expression, so a composite cannot forward to its own ref, and
   `nicolaguglielmi/lights-out/action@v0.2.0` keeps working because the tag
   holds it. From v0.3.0 the path is `nicolaguglielmi/lights-out@<ref>`.
   New input `gates: all | test-proof | test-integrity` (default `all`).
   The check run's summary and the step summary carry one line per gate,
   from `GATES_OUT/lines` (the Makefile's `gates` loop appends each gate's
   line), the gates not run named "not run: stopped at the first NO-GO",
   and for a NO-GO the first 20 lines of that gate's details file (the
   surviving mutants, the file outside the perimeter). 20: a decision,
   enough for a changed-line mutation run, far under the API's 65,535
   characters per summary. The image's entrypoint writes it as
   `summary.md` beside the details, where the wrapper's output directory
   is, so the Action only posts a file and the same summary exists for
   `lights-out gates` on a laptop. `self.yml` uses `uses: ./`.
7. **Two standalone Actions**, sources in `actions/test-proof/` and
   `actions/test-integrity/`: each an `action.yml` (a composite shim,
   `uses: nicolaguglielmi/lights-out@v0.3.0` with `gates: <name>`, inputs
   passed through, its own name, description and branding) and a README.
   For a Marketplace page the owner copies each directory to the root of a
   public repository of its own and publishes it (`docs/launch/
   checklist.md`). Before the tag exists, the shims are proven with the ref
   set to the branch commit in the owner's private probe repository (owner
   decision, 2026-11-08); this repository keeps `v$version`, which
   `ci/package.sh` checks.
8. **`./go doctor --level <l0|l1|l2|l3>`**, in `core/doctor.sh` (host shell,
   ADR 0052 §1; `./go` passes its arguments). Without `--level`, unchanged.
   With it, one stderr line per item, read from `profiles/<level>.env`:
   engine, API socket, git, ports; the key (the existing logic with
   `PROFILE=<level>`); each port value (`CODE_HOST TRACKER EVENT_BUS
   STATE_STORE ORCHESTRATOR DELIVERY METRICS FLAGS REGISTRY AGENT_HARNESS`)
   with no `adapters/<name>/`, "designed, not built"; for l2 and l3, the
   cloud toolchain (absent, §1). Last stdout line `GO: doctor — <level>
   has what its profile names` or `NO-GO: doctor — <level> lacks <n>:
   <items>`. A level name appears only for the cloud toolchain: the
   profiles belong to M34 and declare no flavour yet. Doctor names no
   vendor and no key of its own (`ci/vendor-free.sh`, ADR 0045 §4): an
   adapter's credentials are the adapter's to declare, and the cloud
   adapters that would need a GCP project do not exist yet, so their
   absence is the item.
9. **The conformance record.** `gates/delivery-conformance.sh`, on GO,
   writes `.crew/conformance/delivery-<adapter>.env`: `ADAPTER`, `HASH`
   (sha256 over the sorted file list and contents of `adapters/<adapter>/`,
   one function in `ci/lib.sh` for writer and reader), `AT` (UTC). Not
   committed: it is this machine's proof. M32's external adapters reuse it.
10. **`gates/production-readiness.sh`** (`./go production-readiness`). GO
    only when all four hold; otherwise one NO-GO line naming every failing
    item, details on stderr.
    - (a) Delivery: `DELIVERY`'s adapter has `rollback.sh` and a §9 record
      whose `HASH` equals the adapter's hash today.
    - (b) Metrics: `METRICS=promql`, `METRICS_URL` set, and
      `adapters/promql/query.sh 'count(target_info)'` returns at least one
      sample. The plane's `prometheus` is the demo's scrape, not yours.
    - (c) Secrets: `.env` holds no non-empty value other than `replace-me`
      for a key ending in `_KEY`, `_TOKEN`, `_SECRET`, `_PASSWORD`, or
      `METRICS_AUTH_HEADER`. Production takes secrets from its
      environment, injected by a secret manager. For that path to exist,
      `./go` now hands the workbench, by name only (`-e NAME`, the value
      never on a command line, as `lights-out` does, ADR 0045 §2), each
      such key `.env.example` declares that the host's environment sets;
      a value in `.env` still wins inside make. `CONSOLE_*` pass the same
      way for `production-readiness`, as they already did for `console`.
    - (d) The human gate: `GO_FOR_LAUNCH` is not preset in `.env` or the
      environment (a preset answer is silence that promotes), and
      `CONSOLE_AUTH=proxy` with `CONSOLE_IDENTITY_HEADER` and a non-empty
      `CONSOLE_LAUNCHERS` (ADR 0047 §5: named people press).

    At L0 it is NO-GO by construction (no envoy-canary record unless its
    suite ran, `METRICS=prometheus`, no launchers). Proof: `./go ci` on
    constructed cases (a stub endpoint for `promql`); on GitHub Actions the
    `argo` job runs it GO after the real argo-rollouts conformance, with
    `METRICS=promql` on the plane's Prometheus, and NO-GO on the L0
    defaults. Not one of the eight PR gates; never in `gates`.
11. **Layered configuration, stated once:** profile (`profiles/<level>.env`)
    → the workload's contract (`.lights-out/workload.env`, drafted by
    `init` with a provenance line per value, ADR 0042) → policy
    (`policy/merge.env`, then the workload's `policy.env`, provenance
    required by `core/policy.py`) → `.env` (this machine) → the command
    line. `docs/production.md` has one chapter per decision (provider and
    budget, risk, rework, delivery, metrics, human gate), each naming its
    keys, default, layer and provenance, the profiles' included; their
    comments are M34's to change.
12. **The README follows five steps** (look; gates on your repository; the
    whole loop; agents on your repository; production), each with measured
    requirements, and says reuse where it is reuse. The human gate has
    Argo Rollouts' indefinite pause and Flagger's `confirm-promotion`
    semantics, as the single human gate of a ticket-to-production chain.
    "A PR is judged by its base's policy" is the principle GitHub applies
    to `pull_request_target` (announced 2025-11-07, in force 2025-12-08),
    stated for every gate; GitHub takes the default branch, lights-out the
    PR's base commit (ADR 0033), equal for a PR into the default branch,
    and the README says so. The Google cloud track and `antigravity-cli`
    move to `docs/reference.md`.

Measures and their provenance: 300 s for init plus gates (owner decision
2026-11-03, ADR 0045 §8), and for a check on an outside repository with the
first pull included (plan §16 M31, amendment 2026-11-08). The first-pull
number exists only once the owner publishes the gates image; until then the
probe builds the image in the job and reports the build apart. The 4 GiB
podman VM runs one heavy run at a time (observed 2026-11-07, two VM stops
with two demos at once).

*Amendment 2026-11-09, the first pull measured.* 0.3.0 is published (tag
`v0.3.0`, package.yml run 42588480235, both images signed keyless and
verified). On the probe, with the published image and each Action in a job
of its own on a runner that had never pulled it, the check run was posted
in 27 s by the root Action, 14 s by `test-proof` and 25 s by
`test-integrity`, first pull included (probe run 42589663783): inside the
300 s.

## Alternatives rejected

- **A second Containerfile for the gates image.** Two places to bump every
  hash: ADR 0028's own warning.
- **Subtracting tools from the full image at build.** A layer cannot shrink
  what a lower layer holds.
- **Keeping `action/` as a redirect.** `uses:` takes no expression.
- **The standalone Actions as listed subfolders.** Not listed: one Action
  per repository.
- **A separate repository for the main Action.** The wrapper and the image
  are versioned here; a second repository splits the tag.
- **`doctor --level` in Python.** It runs on the host, which has no Python
  (ADR 0052 §1).
- **Readiness judged by a model or a checklist document.** Not mechanically
  checkable.
- **A size gate on the image.** No provenance for a number.
- **A keyed cosign pair, the public key in the README.** A secret to create
  and rotate for an owner with 5–15 h a week.
- **Unsigned, as the README said until now.** Nothing ties a pull to this
  repository's workflow.
- **The conformance record committed.** It would certify a machine the
  reader never saw.

## Consequences

- **The one that will hurt: three Marketplace listings per release, by
  hand.** Each version means a tag here and a copy plus a release in two
  more repositories; `ci/package.sh` checks the sources here, never the
  copies, which can lag a version without anything failing.
- Signatures are in the public Rekor log. A fork's identity differs, so a
  fork verifies its own. The README's regexp matches tags only: a
  `workflow_dispatch` publish (`:sha-<commit>`) carries a `refs/heads/`
  identity and does not verify with it.
- The gates stage's tools are smoke-checked only through the workbench
  stage's version check and `./go demo-package` on the gates image.
- `test-integrity` runs mutation without `test`: on a red suite it says
  "mutation run failed before scoring", not that the tests fail.
- §10(b) checks that an endpoint answers PromQL, not whose it is: the
  `argo` job's GO uses the plane's Prometheus. §10(d) trusts ADR 0047's
  `proxy` mode, whose header the console cannot authenticate; readiness
  cannot see whether the port is reachable around the proxy.
- §9's hash covers the adapter's folder, not `core/`: a launchpad change
  keeps an old record valid.
- `./go doctor --level l2` is NO-GO on every machine until L2 exists (§1).

## Golden-rule check

`./go demo` builds the workbench stage as before, 474 MB lighter (ADR 0028's
measure; the new size is recorded at close in ADR 0028's amendment); no
stage, key or account is added. `./go ci` gains cold checks only.
`production-readiness` and `doctor --level` are outside the demo. Passes.

## Open points

Found while writing this ADR. The first two are resolved above, the third
is left to L2.

1. **Doctor and vendors** (resolved in §8). A first draft had `core/doctor.sh`
   ask for `GITHUB_TOKEN`, `GITHUB_REPO` and `GOOGLE_CLOUD_PROJECT`, which
   `ci/vendor-free.sh` and ADR 0045 §4 refuse in `core/`. An adapter
   declaring its required keys would fit ADR 0045 §4; until one does,
   doctor lists the missing adapters, not their keys.
2. **Secrets from the environment** (resolved in §10(c)). `./go` passed no
   host environment into the workbench but its own variables and, for
   `console`, `CONSOLE_*`; a real deployment would have been NO-GO on (c)
   with no way out. The passthrough by name closes it.
3. **The cloud flavour's shape.** §1 keeps ADR 0028's
   `workbench/cloud/Containerfile`; §2 rejects a second Containerfile for
   the hashes. Whether L2 writes it as a third stage is decided with L2.

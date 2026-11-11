# ADR 0072 — Security scanning: SAST judges the diff, a signed SBOM per release, a passive DAST at staging

- Status: proposed, deferred: the owner put it later in the roadmap on 2026-11-11; nothing is built
- Date: 2026-11-11
- Would amend: ADR 0015 §4 and ADR 0030 §3 (the SAST verdict and the runner's output), ADR 0053 §6 (`sast` leaves the green-base check), ADR 0024 and 0026 (an optional fifth Delivery verb), ADR 0013 §4 (a check at staging), ADR 0025 §1 (`publish.sh` also attests)

## Context

`gates/sast.sh` NO-GOes on any finding in the whole package. On M24's two
real repositories (2026-11-10, measure), sqlparse's base was red at `sast`
because of one `assert` (bandit B101), and tenacity's because of `random`
used for jitter (B311). ADR 0053 §6 holds every ticket until the base is
green, so nothing moved until a human added `# nosec` outside every ticket's
perimeter. `gates/deps.sh` already had this problem and solved it (ADR 0032).
Nothing produces an SBOM, and nothing scans a running revision.

A correction to the brief. The workload's release is signed with a local
key at L0/L1 (ADR 0025 §2, `adapters/zot/publish.sh`). Keyless signing
(ADR 0057 §4) applies only to lights-out's own images on GHCR. K3, the
attestation of what the agent did (`docs/plans/adoption-roadmap-2026-11.md`,
M36), is not built yet.

## Decision

1. **SAST judges the diff, the same way `deps` does.** The runner contract
   gains `items`, one entry per finding. The line becomes
   `{"findings": N, "items": [{"rule", "file", "line"}]}`, with `file`
   relative to the repository root. The gate runs the base's runner (ADR 0033)
   on worktrees at the merge-base and at HEAD. It fingerprints each item as
   `rule, file, sha256 of the flagged line's text with whitespace stripped`,
   read from git at that revision. Line numbers stay out of the fingerprint.
   Base paths are mapped through `git diff -M` renames. The comparison counts
   duplicates, as `deps.sh`'s sorted lists and `comm` already do.

   The verdict is NO-GO only for a fingerprint that HEAD has more times than
   the base. Inherited findings go to stderr and to `sast.json`
   (`new`, `inherited`). If either side's runner prints no `items`, the gate
   judges HEAD whole, as today, and says so on stderr. `# nosec` stays the
   escape hatch for a new finding. `sast` leaves `core/base-gates.sh`, so
   `test` alone judges a tree. The lines are
   `GO: sast — in <where>, none new (<n> inherited)` and
   `NO-GO: sast — in <where>: this diff introduces <n> finding(s); list on stderr`.
2. **SCA: one SPDX 2.3 SBOM per released image, attested next to its
   signature.** `publish.sh` saves the image to an archive with the engine.
   It then runs `osv-scanner scan image --archive <tar> --format spdx-2-3
   --all-packages`, accepting exit 0 or 1, because 1 only means advisories
   were found. Then it runs `cosign attest --type spdxjson` with the same key
   and flags as the signature. If any of these steps fails, publish fails,
   so a signed image without an SBOM cannot be released. The release record
   gains `sbom`, the digest of the attestation. `verify.sh` does not change
   and no gate judges the SBOM.

   The SBOM is separate from K3, with a different subject. The SBOM describes
   the image digest: what shipped. K3 describes the merge: who changed it,
   under what policy, and who said GO. When K3 is built, its predicate names
   the image digest and this attestation's digest. Neither statement embeds
   the other.
3. **DAST: ZAP's baseline scan, passive only, run at the staging stage
   before any traffic.** The launchpad calls it after `deploy.sh` and before
   the shift to 5%, from a new gate, `verify/dast.sh`. The gate scans the
   stable at `APP_URL` (weight 0 at staging, which `status.sh` proves). It
   reaches the canary through a new, optional Delivery verb, `canary-url.sh`,
   which prints a URL that reaches only the canary revision. Every delivery
   system has this concept: an Envoy route to the canary cluster, Argo
   Rollouts' `canaryService` ("send traffic to only the canary ReplicaSet"),
   and a Cloud Run revision tag URL.

   An alert is the tuple `(plugin id, method, path without query)`, with
   the host stripped. The verdict is NO-GO only for a tuple the canary has
   and the stable does not, at any risk level, with no severity floor
   (ADR 0015 §4). ZAP's own exit codes 1 and 2 are ignored. Exit 3, or a
   report that cannot be read, means the canary cannot be judged, which
   rolls back (ADR 0066). The image is pinned by index digest, for example
   `zaproxy/zap-stable:20261103@sha256:9624669d…`, because the `2.17.0` tag
   moves with every monthly rebuild.

   It is off by default at L0 and L1 (`DAST=off`). `./go demo-dast` proves
   both verdicts at L0 with no key. With `DAST=on`, an adapter that has no
   `canary-url.sh` is refused before staging. The gate prints exactly one
   line:
   `GO: dast — canary <v>: nothing new (<n> inherited from <stable>)` or
   `NO-GO: dast — canary <v> raises <n> alert(s) stable <stable> does not; list on stderr`.

   Before DAST may be turned on in `./go demo`, these must be measured:
   - the cold pull of the pinned image on both Actions jobs and on the
     4.66 GiB podman VM;
   - one warm scan of the bundled app;
   - repeated stable-against-stable runs, which must give an empty diff.

   The pull plus two scans must fit in the measured margin of the slower
   job, today 222 s (678 s against 900 s, ADR 0062 §6). If they fit, DAST is
   on at L0. If they do not, it stays off at L0, and turning it on at L1 is
   the owner's call, since no gate measures L1's time.
4. **One wording everywhere.** The gate's stdout line is stored in
   `GATES_OUT/lines` and the release record. `./go`, `lights-out gates` and
   the console print it verbatim. `./go audit` and the console's timeline
   show the inherited lists and the SBOM digest, with the `cosign
   verify-attestation` command beside it. The console gains no write
   (ADR 0047). The wrapper gets the SAST change for free. It has no release
   and no engine socket (ADR 0045), so SBOM and DAST exist only on `./go`
   and in the console.

## Alternatives rejected

- **SAST as today (whole tree, `# nosec`)**: on M24 it blocked every ticket on debt no ticket created.
- **Line numbers in the fingerprint**: one insertion above a finding makes it "new".
- **Only findings on changed hunks (one scan)**: re-indented or moved code reads as new.
- **bandit 1.9.4 `-b` baseline** (PyPI 2026-02-25, Apache-2.0; `issue.py` and `manager.py` on main, read 2026-11-11): it matches text, severity, CWE, confidence, file and test, but not line or code, and checks membership rather than counts, so a second identical finding in a file passes. It is also Python only.
- **ESLint 10.14.0 bulk suppressions** (MIT; read 2026-11-11): JavaScript only, and needs a committed file in the user's repository.
- **semgrep 1.185.0 `--baseline-commit`** (PyPI, LGPL-2.1-or-later, 2026-11-11): diff-aware out of the box, but its rules are under the Semgrep Rules License v1.0, which forbids making them available to others. ADR 0015's reasons stand. **Opengrep 1.33.1** (2026-10-29, 46–50 MB binaries): no rule set of its own was verified.
- **syft 1.57.1** (Apache-2.0, 2026-11-09, 31/29 MB): the specialised tool, but a new binary. It is the fallback if osv-scanner's image inventory misses packages that `uv.lock` names.
- **CycloneDX from osv-scanner**: it embeds a vulnerabilities section, so the signed document would change with the advisory feed. SPDX output is inventory only (osv-scanner docs, 2026-11-11).
- **BuildKit `--sbom`**: Docker only, and podman is the reference engine (ADR 0004).
- **Nuclei v3.11.1** (MIT, 2026-08-08, 46/41 MB): template probes for known exposures, with templates fetched at run time. It does not analyse the app's own responses passively.
- **ZAP full scan**: active attacks against a revision that shares stable's database.
- **zap-bare** (509 MB, amd64 only): it lacks the packaged scans and has no arm64 build.
- **Scanning at 5% or later**: real users already reach the canary.

## Consequences

- **The cost that will hurt: the DAST image is about 1.2 GB compressed**
  (1,202,475,445 bytes amd64, 1,169,359,316 arm64, Docker Hub, 2026-11-03).
  For comparison, the gates image is 508 MB unpacked (ADR 0057 §3); ZAP's
  unpacked size has not been measured. Its spider is
  bounded by time (default 1 minute), so a large app can crawl differently
  on two runs and give a false NO-GO.
- Every SAST runner, init's copies included, changes its output. A
  repository whose runners predate this ADR keeps the whole-tree verdict
  until `./go init` refreshes them.
- A finding moved to another file reads as new. `main` can carry known
  findings with a green gate; they are printed on every run.
- The SBOM check depends on osv-scanner 2.6.0 (the pin) having
  `spdx-2-3` output and `scan image --archive`. The docs read are those of
  2.7.1, published 2026-11-09. If the pin lacks them, the bump is a commit
  of its own. Cosign 3.1.3's `attest` must round-trip on Zot with ADR 0025
  §2's flags before anything is wired.
- ZAP's requests reach the canary's metrics. The scan ends before the 1m
  window of the 5% stage opens (ADR 0013 §2).

## Golden-rule check

SAST: two scans instead of one, no new tool, and the cost is measured at
implementation. SBOM: no new binary, two attestations per `./go demo` (at
`up` and in the release). The time they add is measured on both Actions
jobs before merging. DAST stays out of `./go demo` until §3's measures show
it fits under 900 s. Passes, provided the SBOM measure fits.

Sources, read 2026-11-11: zaproxy.org/docs/docker (baseline-scan, about);
hub.docker.com zaproxy/zap-stable and zap-bare tags; GitHub API releases of
zaproxy (v2.17.0, Apache-2.0), nuclei, syft, opengrep, cosign (v3.1.4,
2026-10-20), osv-scanner (v2.7.1); google.github.io/osv-scanner (output,
scan-image); PyPI bandit and semgrep; eslint.org/docs/latest/use/suppressions;
argoproj.github.io/argo-rollouts/features/canary; Cloud Run tag URLs
(cloud.google.com blog on gradual rollouts).

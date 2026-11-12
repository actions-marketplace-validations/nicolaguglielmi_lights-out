# Handoff: the evidence pack per release (M49, ADR 0081), 2026-11-12

Branch `claude/beautiful-diffie-f02935`, cut from `main` at dd79626, stream B of the sprint of 2026-11-12. Pushed, no pull request, nothing merged. The coordinator lands it.

## What changed

- **ADR 0081, "The evidence pack per release: one signed file that names its sources and its gaps".**
  - It rejects four alternatives: extending `./go audit`, putting the pack in the logbook, leaving absent fields out or writing them as `null`, and a detached or embedded signature.
  - It also rejects guessing PRs that the log does not tie to the release.
  - §2 was amended once the tests came in: a log line that is not JSON is a NO-GO, and the line numbers count blank lines.
- **`./go evidence VERSION=<v>`** (Makefile target after `audit`, plus a help line in `go`):
  - `core/evidence.sh` (16 code lines) runs `python3 core/evidence.py build`, then `cosign sign-blob` with the plane's key (`COSIGN_KEY`, default `.crew/cosign.key`) and the zot adapter's L0 flags, then `cosign verify-blob` in the same run.
  - It prints one gate line on stdout. stderr gets the missing paths and the verify command.
  - Without a key the pack is written, and the line is a NO-GO that names `./go up`.
- **`core/evidence.py`**, schema `lights-out.evidence/1`. Every leaf is either `{source, value}` or `{source, missing}`, and the top-level `missing` lists the missing paths.
  - The pack covers the last release line of `<v>`, plus its answer: the first answer line for `<v>` after the release and before the next one, as the logbook does.
  - Sections:
    - `release`;
    - `stages[]`, which expects `started_at`/`judged_at` and packs any extra key as found;
    - `artefacts` (image, sbom, dast);
    - `answer`, which expects `reason`, `brief_sha256` and `brief_author` from stream A;
    - `prs[]`, one entry from the ticket the log names, read through the state store's `get.sh`.
  - `prs[]` holds the PR, `merge.sha`, the gates (`ci.lines`, details, risk, decision, head), the rework, the review (missing unless the decision was `review`) and the spec.
  - It reuses `core/audit.py`'s `adapter_json` read-only. `core/audit.py` is unchanged.
- **Tests, written from the ADR by the gate-writer subagent before it saw any code:**
  - `core/tests/test_evidence.py` has 53 tests.
  - `ci/evidence.sh` is in `CI_CHECKS` before `contract`. It covers a rolled-back release with rework and an answered held one, signed and verified with a throwaway key, a one-byte tamper rejected, a stale bundle replaced, five refusals and the log unchanged.
  - Two test fixtures were corrected to the ADR: a pack with "no gaps" needs `decision: review`, and a non-JSON line is refused.
  - Shown to fail on two planted edits: signing skipped, and the answer's missing reason changed.
- **`.github/workflows/ci.yml`**:
  - `engine-compat` gets a step after the logbook: `./go evidence` on e2e's release, with jq checks, and `.crew/evidence/` added to its upload.
  - `launch` gets a step after `demo-console`: the console-answered release, checking `via: console` and by/at, and naming the PR as missing. It has its own upload, `evidence-answered`.
- **Docs**: `docs/reference.md` (control plane paragraph, command list), `docs/tutorial.md` (a `./go evidence` section with a local run's output), and `site/index.html` (the "Real" list).

## Verified

- Local, full clone `.crew/sprint-b` at 38e7d23, podman rootful:
  - `./go demo` printed GO, 734 s to rollback against a 900 s budget. Its `./go ci` was green, including `GO: evidence`. The parallel cold `./go ci` I killed was sharing the VM, so the time is not a measure of this change.
  - Then `./go evidence VERSION=0.2.0-waitlist` printed GO with 6 missing: `release.held_at`, two stage times, `artefacts.dast`, `answer` (rolled back) and `prs[0].review` (auto-merge).
  - Then `./go demo-launch` and `./go evidence` printed GO with 10 missing: the answer present with by/at/via, and `prs` missing because there is no ticket.
  - The plane was taken down afterwards.
- At f61aad5, after the docs commit: `ci-docs-drift`, `ci-help`, `ci-evidence`, `ci-core-tests`, `ci-shell-boundary`, `ci-shell` and `ci-lint` were all GO.
- GitHub, 38e7d23, all green:
  - ci 43321699322: engine-compat printed `GO: evidence — … 6 missing`, and launch printed `GO: evidence — … 10 missing` with `via: console`;
  - self 43321699140;
  - stranger 43321699202;
  - podman 43321699227;
  - package 43321699323.
- GitHub, f61aad5 (the docs and site commit), all green: ci 43324368588, self 43324368363, stranger 43324368457, podman 43324368412, package 43324368410, site 43324368595.

## For the coordinator

- Expected conflicts with stream A:
  - the Makefile (the `CI_CHECKS` line and the target after `audit`);
  - `go`'s help;
  - `docs/reference.md`;
  - `site/index.html` line ~587;
  - `ci.yml` (the launch job, after `demo-console`).
- Stream A: the pack reads `reason`, `brief_sha256` and `brief_author` from the `kind: answer` line of `releases.jsonl`, not from `release.json`. If they are written only into the record, the pack calls them missing. The note is in the shared notes folder, `m49-evidence-notes.md`.
- After A lands, the tutorial's "6 missing" output drops by two (the stage times), so it will need a re-capture.

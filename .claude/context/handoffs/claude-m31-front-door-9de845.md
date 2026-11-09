# M31, the stepped way in (ADR 0057), 2026-11-08

Branch `claude/m31-front-door-9de845`, on 30ca9dc, pushed, no pull request, not merged: landing is the owner's, with M34 and M35. Nothing published: no image tag, no Marketplace release.

## Acceptance

On 0a0d073, six workflows green: ci 42519069855, stranger 42519069911, self 42519069842, site 42519069848, package 42519069964, podman 42519069828.

```
engine-compat  GO: demo, milestone M9, 848s to rollback (budget 900s, plan §2)
stranger       GO: demo, milestone M9, 782s to rollback
package        GO: demo-package — init and gates 48s in workbench (budget 300s), test-proof and test-integrity GO and NO-GO, a staged break NO-GO at test, image localhost/lights-out-gates:dev, 508 MB unpacked
package        localhost/lights-out-gates:dev 508 MB, localhost/lights-out:dev 1246 MB (was 1.77 GB)
argo           NO-GO: production-readiness — delivery (...), metrics (...), human gate (...)      L0 defaults
argo           GO: production-readiness — delivery argo-rollouts, conformance passed 2026-11-08T20:20:34Z, metrics from METRICS_URL, 2 target_info series, no secrets in .env, launchers owner@example.invalid
```

Outside repository: `nicolaguglielmi/lights-out-probe` (public; made public because the account's Actions billing refused the private run), PR #1, run 42519118155: `lights-out gates` 19 s, `lights-out test-proof` 2 s, `lights-out test-integrity` 17 s, three check runs posted `success`, the image built in the job in 23 s. The first pull is not measured: the image is not published.

Locally: `./go ci` GO from a clone under `.crew/m31-clone` (273 s); `./go demo-package` GO on arm64 podman (init and gates 35 s, the gates image 529 MB); `./go doctor --level l2` lists 9 missing items on this machine.

## What changed

- `workbench/Containerfile`: gcloud, terraform, unzip and node's C headers out; two stages, `gates` and `workbench` on it. `package/build.sh` builds either (`PACKAGE_FLAVOUR`), `./go package-gates`.
- `lights-out` 0.3.0: the gates image for init, gates and the new `test-proof`, `test-integrity`; the image writes `gates/summary.md`, one line per gate; `STAGED=1` takes the patch from the host's git.
- `action.yml` at the root (`action/` removed), `gates` input, the per-gate summary in the check run; `actions/test-proof`, `actions/test-integrity` shims; keyless `cosign sign` in `publish`.
- `./go doctor --level`; `gates/production-readiness.sh`; the delivery suite's record in `.crew/conformance/`; `./go` passes `.env.example`'s secret keys by name.
- README in the five steps with the two reuse claims; `docs/production.md`; reference, guide, tutorial, checklist, site.

## Contradictions with the plan, and open points

- The Marketplace lists one Action per repository, from its root. The two standalone Actions need two repositories of their own; the checklist says how. "Three Marketplace pages published" is the owner's.
- GitHub's `pull_request_target` change was announced 2025-11-07 and took effect 2025-12-08; it takes the default branch, not the PR's base. The README says that.
- "Under 300 s, first pull included" waits for v0.3.0: the checklist has the probe edit that measures it.
- The gates image is 508 MB, not under 400: git with perl and python3, node, osv-scanner and uv are what the gates run.
- Doctor names no vendor or key (`ci/vendor-free.sh`): an adapter should declare its credentials one day.
- The gates image does not render a repository's plane half (no docker-compose) and says so on stderr.
- Merge with M34: it deletes `ci/gitea-compat.sh` (M31 widened its exemption to package.yml: drop that change), drops ports 8085/8086 (doctor, README, tutorial lists), and conflicts on `CI_CHECKS` (M31 adds `readiness`, M35 `gates-light`).
- The gate-writer's worktree `.claude/worktrees/agent-aa6396a5fabe61d67` (branch `worktree-agent-aa6396a5fabe61d67`) is kept; its two commits are cherry-picked here.

## First thing for the next milestone

Tag v0.3.0 after the merge, run the checklist's M31 section, and replace the probe's 19/2/17 s with times that include the first pull.

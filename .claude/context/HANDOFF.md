# Handoff: M6 closed on 2026-09-16

## Acceptance

`./go e2e` at L0 (podman rootless on macOS, no key, no account; the plane already up):

```
[tower] 0001: opened, assign requested
[tower] 0001: assign → pr-opened
[ci] gates: GO: gates — risk low, auto-merge
[tower] 0001: ci → ci-passed
[merge] PR #2 merged as 54348c3d166c793f75e3f4d86107b35eb873c984 (head e838d44d0a9b6b928a588c383c991afea7b0867c)
[tower] 0001: merge → merged
[tower] 0001: release → rolled-back
[tower] 0001: rolled-back is terminal, nothing requested
[inproc] queue empty after 4 event(s), 0 failed
deploy   0.2.0-waitlist rolled-back — NO-GO: launchpad — 5%: error_rate canary(0.2.0-waitlist)=1.000 stable(0.1.0-m2)=0.000 delta=1.000 max=0.010 → rolled back
         slo: traffic canary(0.2.0-waitlist)=0.208 stable(0.1.0-m2)=4.018
         slo: error_rate canary(0.2.0-waitlist)=1.000 stable(0.1.0-m2)=no data
         slo: latency_p95 canary(0.2.0-waitlist)=0.043 stable(0.1.0-m2)=0.024
         image: stable image, not built from merge.sha (M8)
  ← merge  54348c3d166c793f75e3f4d86107b35eb873c984 (code host agrees)
  ← PR     #2 http://host.containers.internal:3000/lights-out/lights-out/pulls/2 (gates GO, risk low, auto-merge; head e838d44d0a9b6b928a588c383c991afea7b0867c)
  ← ticket 0001 (dev-worker, harness replay, model gemini-3.5-flash)
  ← spec   sha256:bcfec17ec… "0001 — Unknown venue makes `POST /api/meetups` answer 500 instead of the documented 502"
GO: e2e
```

148 s wall time warm (`time ./go e2e`). Plan §7 M6's criterion: ticket → PR → CI → canary → verify failed → rollback with no human, and the audit shows the whole chain — the chain above is read back from the Firestore emulator and cross-checked against Gitea, not from the shell that ran it.

`./go ci`: thirteen checks GO, the new one `tower` (ci/tower.sh: transition table, duplicate event, out-of-order event, the crash case, a failing step, six audit verdicts; proven to fail on a broken precondition and on a self-confirming audit, then restored). `./go demo-crew`: GO, 79 s, on the refactored `crew-run`.

`./go demo`, from a stopped plane with warm images, three runs: the first NO-GO (below, fixed), then `GO: demo, milestone M6, -4204s to rollback` (below, the VM clock), then with the clock synced:

```
GO: demo-rollback
GO: e2e
GO: demo, milestone M6, 360s to rollback (budget 900s, plan §2)
```

360 s warm against ADR 0019 §7's estimate of ≈ 295 s; the difference is e2e's own `up` and a second plane readiness pass. Cold (image pulls, workbench build) is not measured this session; the GitHub `engine-compat` job measures it on push.

## What changed

- `core/tower.sh`: the state machine (`open`, `step`), four steps in `core/steps/` (`assign` → crew.sh; `ci` → the gates in a worktree + a `gates` commit status on the PR; `merge` → the code host; `release` → `make release`, log kept, `slo:` numbers recorded); `adapters/inproc/run.sh` pulls one event, applies it, acks, until the queue is empty. Idempotency: precondition ≠ state → dropped; the merge seam is the adapter (`adapters/gitea/merge.sh` on an already-merged PR performs nothing and prints the same shas).
- `adapters/firestore-emulator/{get,put,delete}.sh` and `adapters/pubsub-emulator/{publish,pull,ack}.sh`: curl + jq, plain JSON in `core/`, typed encoding inside the adapter; `adapters/gitea/{status,merge,pr}.sh`. `core/audit.sh` and `./go audit TICKET=<id>`: chain from the document, NO-GO on a missing link, an sha mismatch, or a divergence from the code host (owner addition).
- Makefile: `e2e` real and the last `demo` stage, `audit`, `crew-run` now calls `core/steps/ci.sh` (one CI code path for demo-crew, record and the tower), `TICKET ?= 0001`, `demo` names M6 and says so when the engine clock is behind the host instead of printing a negative number. `core/launchpad.sh`: `100%: NOT YET (M7, go-for-launch)`.
- `roles/dev-worker/role.env`: `TOKEN_BUDGET` 10M → 12M, **provisional — a decision, not a measurement** (owner ruling 2026-09-16). What is measured is ADR 0018 run 3: 10,056,737 tokens at call 43, work done at call 31, the PR text unwritten after four mutation-suite runs. No run has finished under the new prompt (which forbids the suite), so the 12M has no run of its own behind it. **The condition that fixes it**: two consecutive successful `./go record TICKET=0001 PROFILE=l1` on this prompt; the budget becomes the larger total plus one call's headroom, both `run.json` totals as provenance, dedicated commit. The comment in `role.env` says the same.
- `adapters/gitea/bootstrap.sh` waits for `empty: false` after the main push (the cold-plane 404, below). Docs: README, ARCHITECTURE, PLAN §7 notes (M6, M7, M8), ADR status lines 0003/0012/0013/0014/0015/0017, ADR 0019, roles/{architect,test-reviewer}/ROLE.md → M7, tickets 0001 and 0003.

## Contradicts docs/PLAN.md

- **Plan §3's table says CI at L0 is Gitea Actions. At M6 it is not, and the runner socket is re-dated for the third time (M4 → M5 → M6 → M8).** ADR 0019 §4: the six gates run by the tower on the PR head and posted as the `gates` commit status are the CI leg; the Gitea runner has run no job since M2. Declared in README and PLAN §7. ADR 0003's rule binds M8: if M8 closes with the runner idle, M8 is not closed. Five facts stand unverified for the real job (ADR 0019 §4 lists them); the first is whether github.com is reachable from inside the podman machine for `actions/checkout`.
- **The canary the tower releases is not built from the merge commit** (ADR 0019 §5, option i). The audit prints `image: stable image, not built from merge.sha (M8)` on every line; plan §8 step 5 ("merge, build, immagine firmata") is M8's.
- **`go-for-launch` was M6's in every ADR since 0013; it is M7's now** (ADR 0019 §8, PLAN §7 note): the human reads a promotion brief the release agent composes, and that agent is M7's.
- The first ADR 0019 draft had the audit read only the state store; the owner overruled it the same day ("an audit that reads only its own archive confirms itself"). §6 and the rejected-alternatives list carry the correction.

## Found this session, fixed

- **Cold-plane `open-pr on gitea failed` — the M5 HANDOFF transient, root-caused.** Gitea's log: `404 … v1.mustAllowPulls` on both the list and the create call, ~2 s after bootstrap's first push. A freshly created repo stays `empty: true` until the post-receive hook has run, asynchronously to `git push` returning, and an empty repo has no pulls unit. Reproduced on the first `./go demo` from a stopped plane this session (`NO-GO: e2e — a step failed`), never on a warm one. Fixed in `bootstrap.sh` step 5: poll `GET /repos/{o}/{r}` until `.empty == false`, READY_TIMEOUT bound. Two demos from a stopped plane passed after it.
- **The podman machine's clock was 4,512 s behind the host** (`date +%s` on both sides), so `demo`'s `LIGHTS_OUT_T0` arithmetic printed `-4204s to rollback` and would have passed any budget. Environment, not repo: a VM that slept. The Makefile now says "not timed: the engine clock is Ns behind the host, budget unverified" instead of a negative number; the clock was synced with `podman machine ssh "sudo date -s @$(date +%s)"` for the recorded run. Anyone timing `./go demo` on macOS should compare the two clocks first. **M8 prerequisite (owner, 2026-09-16)**: the same skew, at L2, breaks image signing and OIDC — Workload Identity Federation tokens, cosign/Binary Authorization signatures and Sigstore certificates all carry short validity windows, and a VM 75 minutes behind produces "invalid token", "certificate not yet valid" and "signature verification failed" errors that look like misconfigured IAM or a wrong key, not like a clock. Before any L2 work: an `engine-compat` (or `up`) check that the engine host's clock is within a stated tolerance of the workbench's, NO-GO with both timestamps, and the README's L2 prerequisites list it. The tolerance's provenance is the token lifetime it protects (OIDC `iat`/`exp` skew allowances, typically minutes), to be read from the docs at M8, not guessed here.

## Found, not fixed

- **`./go ci` still cannot pass with a real key in `.env`** (M5 HANDOFF's `ci/secrets.sh` contradiction, unchanged): this session parked `.env` outside the tree for every `ci` and `demo` run and restored it at the end. Owner of `ci/` decides between a gitignore-aware `gitleaks` invocation and ADR 0002's no-allowlist rule.
- `demo` runs two releases back to back (demo-rollback, then e2e's); the 1m PromQL window holds because ≥ 97 s pass between them, and the Makefile comment says the order matters. If e2e's `up` ever gets faster, re-check.
- The e2e PR number on a warm plane is whatever Gitea has next (#2 in the acceptance run above, #1 on a fresh plane): the document records it, nothing else depends on it.
- The gate-writer subagent stalled (10 min, no output) on `ci/tower.sh`; the main session wrote it from ADR 0019 §6/§9. Tests-from-the-spec rule respected in letter; the same session wrote the implementation, so the next reader of `ci/tower.sh` should read the ADR first and the test second.
- `record` at L1 was not run: the 12M budget is provisional (above); the next two `record`s fix it.
- **`roles/dev-worker/prompt.md` names pipeline tools** (the six gates by name, `make`, `./go`, the mutation suite): forbidding the suite treats the symptom. `tickets/0004.md` (opened this session, owner decision) extracts the rule — `roles/*/prompt.md` never names a gate or a Makefile target, only the objective — for M7's prompt work.

## Prerequisites M8 inherits from this session

- Engine-host clock skew check before signing or OIDC (above).
- The runner socket and the first Gitea Actions job (ADR 0019 §4's five unverified facts; ADR 0003's rule).
- Image build from the merge commit and push to Zot (ADR 0019 §5).

## First thing M7 should look at

- ADR 0019 §8 hands M7 three things beyond the ADK roles: `go-for-launch` (the stub at `core/launchpad.sh` line ~84; ADR 0003's rule binds), the first real prompts for `architect` and `test-reviewer` (state `review` is terminal today — a medium/high PR stops there visibly), and ticket 0003's perimeter rule before the next `record`. Ticket 0004 (prompts name no gate and no Makefile target) belongs to the same prompt work: write the three prompts under that rule, then the two `record`s that fix the budget.
- The tower's `review` state is where M7's review agent plugs in: a `review` step with precondition `review` and next states `ci-passed`/`ci-failed` is the whole change to `core/tower.sh`'s tables.
- Before any `record`: the `.env` vs `ci/secrets.sh` contradiction above, and re-verify the 3.8 routing the way ADR 0018 did.

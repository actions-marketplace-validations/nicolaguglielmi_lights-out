# Handoff: M9 closed on 2026-09-17

> **Update 2026-09-23.** The product was refocused (ADR 0029: a
> governed-autonomy harness; the app becomes a workload behind a port) and
> M12 is next, designed in ADR 0030 and planned file by file in
> `.claude/context/M12-PLAN.md`. The "First thing M10 should look at"
> section below is superseded: M8's cloud track, M10 and M11 wait (plan
> §14). Everything else in this handoff still holds.

## Acceptance

Plan §7 M9: a medium-risk PR (fixture recorded at L1, replayed at L0) goes through the `review` step; `test-reviewer` marks it approved or changes-requested with a reason traceable in the tower document; a fixture whose diff exits the ticket's perimeter is not written by `record`, the reason naming the file.

`./go ci` at L0, 23 checks including three new (`perimeter`, `review`, `tower` updated):

```
GO: secrets … GO: perimeter
GO: review
GO: tower
GO: contract
GO: ci
```

`perimeter` = ticket 0003's rule (a `## Perimeter` section with globs, checked in `core/perimeter.sh` on paths from stdin), proved on stub tickets and the literal case from ticket 0003 (conftest.py outside perimeter); `review` = the step script's verdicts (APPROVED, CHANGES-REQUESTED, a third word or empty reason → exit 1), a recorded input hash match → field `true`, a mismatch → warning and field `false`; `tower` = the state machine's two new transitions (review state, ci-passed and ci-failed outcomes).

`./go demo-review` at L0, ticket 0005 (medium-risk, 237 changed lines), replayed from the L1 fixtures — real terminal output, not reconstructed:

```
[ci] gates: GO: gates — risk medium, review
[ci] risk medium: review requested; test-reviewer picks it up next (docs/adr/0021)
[tower] 0005: ci → review
[tower] 0005: review (state review)
[tower] 0005: review → ci-passed
[tower] 0005: merge (state ci-passed)
[merge] PR #3 merged as e73e57a222cbc1058e115e03190b1ccc19250495 (head 78a5b46e65187802612e3e5a13fe23882c4b8c43)
[tower] 0005: merge → merged
[tower] 0005: release (state merged)
… (release rolls back at 5%, unrelated to review: the canary is still the stable image at L0, ADR 0013's declared M8 gap)
[demo-review] test-reviewer: approved — The diff satisfies all acceptance criteria in ticket 0005, stays strictly
within the declared perimeter paths, maintains minimal scope, and includes tests that verify every required
behaviour: 1. Perimeter: … 2. Ambiguous Venue Handling: … 3. Contract Examples and Fake Support: … 4. Timeout and
Malformed Responses: … 5. Unchanged Outcomes and Full API Coverage: … 6. Documentation: …
[demo-review] second reviewer, architect (exercised once, not wired into the tower):
{"state":"ci-passed","review":{"role":"architect","verdict":"approved", … "harness":"replay", …
"input_matches_recorded":true}}
GO: demo-review
```

(The release rollback prints the pre-existing `core/steps/release.sh:27` race described below; it did not change the outcome.) `./go demo` on a clean rebuilt workbench image (`./go clean` first, warm plane images): `GO: demo, milestone M9, 318s to rollback (budget 900s, plan §2)`. No `NOT YET` line anywhere.

## What changed

- `core/steps/review.sh`: new step script; input is ticket text + `git diff BASE_SHA HEAD_SHA` (BASE now the workspace's own `git rev-parse HEAD` at clone, not the ticket's original base); output is `final.md` (APPROVED or CHANGES-REQUESTED, plus reason) and `input_sha256`; verdict posts as a `review` commit status through `adapters/CODE_HOST/status.sh`.
- `core/perimeter.sh`: new script; reads ticket's `## Perimeter` section (glob patterns, one per line) and changed paths on stdin, prints first path matching no glob (or NO-GO if no Perimeter section exists); called in `core/crew.sh` after `harness-check.sh`.
- `adapters/gemini-cli/run.sh` and `entrypoint.sh`: `run.sh` writes `OUT/final.md` (the harness's final message) and records `input_sha256` in `run.json`; `entrypoint.sh` trailer changed to "your final message is this run's artefact, nothing else" (role-specific wording in `prompt.md`).
- `adapters/replay/run.sh`: branching changed from `-f "$fixture/patch"` (file exists) to `-s "$fixture/patch"` (non-empty); fixtures with `final.md` and no `patch` copy; fixtures with neither fail loudly naming the command.
- `roles/test-reviewer/` and `roles/architect/`: new prompt.md and role.env (HARNESS=gemini-cli, THINKING=high, TOKEN_BUDGET measured, TIMEOUT_S=900). No more ROLE.md.
- `roles/dev-worker/role.env`: TOKEN_BUDGET re-measured, dropped from provisional 12,000,000 to 2,600,000 (larger of two run totals, 1,823,982 + headroom, with both run tokens quoted as provenance).
- Makefile: `review`, `demo-review`, `record-review` targets; `CI_CHECKS` += `perimeter review` (`tower` already listed, its own script rewritten); `go` socket list += review targets.
- `core/tower.sh`: two new transition lines (review state, next ci-passed or ci-failed); `core/crew.sh` calls `core/perimeter.sh` after harness run.
- Docs: ADR 0021 (accepted), README (M9 stage table row, review targets in quick start, "M7 of 11" → "M9 of 11"), ARCHITECTURE.md (AgentHarness port update for review artefact contract, M9 status section), PLAN.md closing note for M9, ADR status lines for 0016/0017/0019/0020.

## Contradicts docs/PLAN.md and ADR 0021 as drafted

None. M9 delivered exactly as planned. The two re-recorded dev-worker fixtures (ticket 0001 with 4 attempts, ticket 0005 with 6 attempts) fixed the budget hypothesis and validated the prompt rewrite. Ticket 0003's perimeter rule works as specified and caught a real case in the committed M5 fixture.

## Found this session, fixed

- `core/steps/review.sh` originally passed `BASE=$BASE_SHA` (the ticket's original base) instead of the workspace's own current HEAD at clone; this made `adapters/gemini-cli/run.sh`'s `git format-patch $BASE..HEAD` reproduce dev-worker's entire diff on replay. Fixed: BASE is now workspace's `git rev-parse HEAD`, so a clean (unedited) reviewer workspace gets an empty patch. Defence in depth: `adapters/replay/run.sh` changed from `-f` (file exists) to `-s` (non-empty) so reading-role fixtures skip the `git am` path.
- Review step input document header was literal `Diff, BASE_SHA..HEAD_SHA:` which changed on every replay (fresh commit hashes from `git am`), breaking `input_sha256` matching. Fixed: header is now constant `Diff:`, so input hash reflects ticket text + diff content only.

## Found, not fixed

- `core/steps/release.sh:27`'s `[ "$(cat "$rc_file")" -eq 0 ]` intermittently reads an empty `$rc_file` from a race between the `tee`/subshell pipeline and the `cat`, printing `Illegal number` to stderr. The fallback state (`rolled-back`) happens to be correct in every observed case, so the verdict is never wrong, but this is a real race condition, not cosmetic. Found at M9 close; unrelated to review work.
- `.crew/.uv-cache/` accumulated ~194 MB from live `record`/`record-review` runs (gitleaks gitignored-scan category). Twenty-one false positives on sqlalchemy source strings (`ctx.api`, `.key`) from entropy heuristics, unrelated to repo secrets. Known issue, same category as the `.env`-parking problem already tracked in earlier HANDOFFs.

## Prerequisites M10 inherits

M8 (GCP, Artifact Registry, Cloud Run, Cloud Deploy, Workload Identity, Secret Manager) remains open. This session deliberately did M9 first because none of its work depends on GCP (owner ruling, already noted in PLAN.md). Decision for M10's first session: resume M8 or take another out-of-order milestone. Before touching `core/steps/review.sh` again, re-read ADR 0021 and note the two bugs above; the BASE variable and the input header are load-bearing.

## First thing M10 should look at

- Decide: M8 (GCP) next, or pick another out-of-order milestone.
- If M8: read HANDOFF M7's prerequisites section (clock skew, `.env` parked for ci, Gemini CLI 3.8 routing check); review roles are now in place so the tower's review consumer exists.
- Before any `record`: the perimeter rule is live. A ticket without a `## Perimeter` section will fail with a loud error; ticket 0001's perimeter is prose that must be spelled as globs, ticket 0005 was built with it in mind. Any new ticket needs the section, or `record` fails before the model runs.

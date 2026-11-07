# ADR 0056 — Main always green without a queue: no re-judge on disjoint perimeters, main checked after merge, bisect and revert

- Status: proposed
- Date: 2026-11-07
- Milestone: M30
- Amends ADR 0019 §1 (the transition table: `merged` requests `mainline`,
  `release` starts from `main-green`) and ADR 0038 §2, §4 (a rework the
  tower sends back from main starts from main's head, not from the
  rejected head). Consistent with ADR 0033 (what judges main is the last
  green main's), ADR 0034 (a refusal is a recorded failed attempt) and
  ADR 0043 (everything on the code host goes through the CodeHost port's
  verbs).

## Context

`core/steps/merge.sh` merges the head CI judged, on whatever main is at
merge time. With one ticket in flight that main is the PR's own base.
With several, main moves between a PR's judgment and its merge, and the
merge commit is a tree no gate has seen. Nothing checks main afterwards.

The usual answer is a merge queue: before merging, re-judge each PR on the
current main, one at a time. The owner decided against it on 2026-11-07:
with tickets in flight multiplying, a global lock is a funnel, and every
PR waits for the gates of every PR ahead of it. Conflicts are prevented
upstream instead (ADR 0053, M27: two open tickets never hold overlapping
perimeters) and cured downstream on main, by finding the merge that broke
it and reverting it: the canary's principle (verify, and go back on your
own) applied to main.

With ADR 0053's holds, two tickets the tower runs at the same time never
touch the same file. Main can still move under a judged PR's perimeter:
by a merge the tower did not make (a person's, another tool's, the norm
on an attached repository) or by a revert. And two disjoint diffs can
still break main together: one renames what the other starts calling.

## Decision

1. **Merge without re-judging when the perimeter is untouched.** Before
   the adapter's `merge.sh`, `core/steps/merge.sh` runs `python3
   core/mainline.py rejudge`. It fetches the code host's default branch
   and lists the first-parent commits after `pr.base_sha`, the base the
   PR was judged on, each with the paths it changed against its first
   parent: what each merge *touched*, so a change later reverted still
   counts. The perimeter is the ticket's `## Perimeter`, read from the
   Tracker and never from the PR, with `core/perimeter.sh`'s rule: a
   path is in it when it matches a glob, `*` crossing `/`
   (`fnmatch.fnmatchcase`).
   - No commit after the base, or none touching the perimeter: the merge
     goes ahead, gates not run again. The code host merges onto the moved
     main; the main check (§3) judges the result.
   - A commit touched a path in the perimeter: no merge. The step prints
     `ci-failed` and a `mainline` field, `{verdict: "NO-GO", judge:
     "base", head_sha, line, details}`, with the line `NO-GO: base — main
     moved under the perimeter since <base>: <path> by <commit>` (first
     overlap; every overlap is one entry of `details`). The ticket goes
     to rework (§6).
   - `pr.base_sha` is not an ancestor of main's head (main was
     rewritten): the step fails, nothing is merged; a person looks.

2. **The table.** One step and one state between `merged` and `release`:

   ```
    precondition()                  next()
   +  mainline) 'merged'          -  merged)     'release'
   -  release)  'merged'          +  merged)     'mainline'
   +  release)  'main-green'      +  main-green) 'release'
   ```

   `mainline` may also print `ci-failed` (§4), which already requests
   `rework`. The board's copy of the table (ADR 0035) follows.

3. **Main is checked after merge, in groups of at most four.** The
   `mainline` step (`core/steps/mainline.sh`, a thin entry point for
   `python3 core/mainline.py check`) keeps one document beside the
   tickets: collection `mainline`, id `main`, `{state: "green" | "red",
   green, head, line, reverted: [...], at}`.
   - **The last green main, G**, is the document's `green` when it is an
     ancestor of main's head; otherwise (no document, or main was
     rewritten, as the L0 replays do) the ticket's `pr.base_sha`, the
     main its CI passed on.
   - **Groups.** The commits after G, first-parent, oldest first, are
     taken at most `MAINLINE_GROUP_MAX` at a time; the newest commit of
     the group is judged against G. GO moves G to it, and the next group
     follows until G is main's head. `MAINLINE_GROUP_MAX=4`, in
     `policy/mainline.env`, read from the tower's checkout. Provenance:
     the owner's decision recorded in `roles/dev-worker/role.env` (four
     dev-worker attempts a day) against the Gemini API free tier's 250
     requests a day at `MAX_TURNS=60` (ADR 0038 §3): at most four merges a
     day reach main through the free-tier tower, so a group never spans
     more than a day of them, and bisecting it costs at most two gate
     runs (⌈log₂ 4⌉).
   - **What judges main.** `make gates GATES="sast test"` on a worktree at
     the commit, with the judges restored from G, as `core/steps/ci.sh`
     does from a PR's base (ADR 0033 §1): the gates whose subject is the
     whole tree. The diff gates (risk, secrets, deps, mutation, and
     ADR 0053's) already judged each PR's own diff; a merge of disjoint
     diffs does not change their subject, and the ticket-bound ones have
     no ticket on main.
   - **The same tree is the same verdict.** A commit whose tree is one
     the same judges already passed is GO without a run: G's own tree,
     a tree judged GO earlier in the same check, and the tree of the
     head the ticket's CI passed when G is that PR's base. A merge onto
     an unmoved main has exactly the tree CI judged, so `./go demo`'s
     single ticket pays a fetch, not a gate run.

4. **Bisect, revert through the code host, rework the culprit.** When a
   group's newest commit is NO-GO, the step writes the document `red`
   with that line, then bisects the group between G (green) and that
   commit (red): the first red commit is the culprit, found in at most
   ⌈log₂ n⌉ more runs. It is reverted with the CodeHost port's existing
   verbs: a branch `revert/<sha>` from main's head with `git revert`
   (`-m 1` for a merge), `push.sh`, `open-pr.sh`, `merge.sh` at that head.
   A revert, never a force push: main's history keeps both, and an
   outside commit made meanwhile is not lost. The new head is judged; GO
   writes the document `green` and appends `{merge, revert, line,
   details, at}` to `reverted`, where `line` and `details` are the
   culprit's own verdict.
   - **The ticket of the step.** Its merge in `reverted`: `ci-failed`,
     `mainline: {verdict: "NO-GO", judge: "main", head_sha, line,
     details}`, rework. Its merge an ancestor of G: `main-green`. The
     culprit's ticket learns it from its own `mainline` step, queued
     after its merge; a culprit merged outside the tower is reverted and
     recorded with nobody to send it to.
   - **One culprit per check.** The revert does not apply, the culprit is
     itself a revert, or main is still NO-GO after it: the document stays
     `red` with the reason, the step fails (ADR 0034), and a person
     decides. Bisecting a second culprit under the first one's revert is
     not built.

5. **A red main stops assign and release.** Before running `assign` or
   `release`, `core/tower.py` reads `mainline/main`. `red` refuses the
   step: nothing runs, the state stays, and the failed attempt is
   recorded with the error `main is NO-GO since <G>: <line>`, so the
   reason is in the ticket's document and in main's. `./go resume`
   requests it again (ADR 0034). The same shape as `release-freeze`
   (ADR 0013 §6): a refusal before any effect, recorded, and lifted by
   state, not by editing the ticket.

6. **Rework on the new base.** `core/steps/rework.sh` reads `.mainline`
   before `.ci`: its `judge` (`base` or `main`) goes into the `.rework`
   entry, and the next attempt prints `mainline: null` beside `ci: null`.
   For these two judges `core/crew.sh` starts attempt n + 1 from the code
   host's main, not from the rejected head (`REWORK_FRESH`): the rejected
   change is either under a revert or was judged on a base that no
   longer exists. The worker gets the ticket, the brief and the verdict,
   as in ADR 0038 §4. The cap (ADR 0038 §3) counts these attempts like
   any other. No integrator role: the conflict is the dev-worker's, on
   the dev-worker's ticket.

7. **The proof.**
   - `core/tests/test_mainline.py`, `unittest`, from this ADR: the
     perimeter match, the overlap over touched paths, the group limit,
     the bisection's culprit and its number of runs, the same-tree rule.
   - `ci/mainline.sh` in `./go ci`, no engine: the real
     `core/steps/merge.sh` and `core/steps/mainline.sh` on a temp git
     repository behind a stub CodeHost, with a stub workload whose
     `gates` target is a script. The re-judge cases: base unmoved,
     merged; moved by a commit outside the perimeter, merged with no
     gate run; moved by one inside it, `ci-failed` and not merged;
     touched and since reverted, still `ci-failed`; base rewritten, the
     step fails. The main check: a group judged green; a red group
     bisected, its culprit reverted on the host, main green again; a
     revert that does not apply leaves main red.
   - `core/tests/test_tower.py`: a red `mainline/main` refuses `assign`
     and `release` with the reason and leaves every other step alone.
   - `./go demo-mainline`, at L0, no key, tickets 0020–0022 with
     hand-written fixtures (README, "What is real"). Tickets 0020 and
     0021 hold disjoint perimeters; 0020 renames a function 0021 starts
     calling, and each passes its gates alone. Ticket 0022's perimeter
     holds `app/backend/meetups/db.py`. After the three are judged, a
     change to `db.py` lands on main through the code host with no
     ticket: a person's merge. Then 0020 and 0021 merge without
     re-judging; 0022 goes back to rework, the line naming `db.py` and
     that commit; the main check finds main NO-GO, bisects to 0021's
     merge, reverts it, and main is GO again. The demo applies the bus's
     events itself, as `adapters/inproc/run.sh` does, so the person's
     merge lands between judging and merging, and stops at what other
     demos prove: the release it leaves requested is `./go e2e`'s, the
     two attempts 2 `./go demo-rework`'s. It says so on stderr.

## Alternatives rejected

- **A merge queue with a global lock** (re-judge each PR on the current
  main, one at a time). The owner's decision of 2026-11-07: every PR
  waits for every gate run ahead of it, and the wait grows with the
  tickets in flight. Here a disjoint PR merges at once and main pays a
  gate run per group, not per PR.
- **Speculative batches** (judge PR combinations in parallel, merge the
  largest green prefix). N gate runs at once is N times the engine at L0,
  on a laptop; and with disjoint perimeters a combination rarely fails,
  so the speculation is mostly paid for nothing. The bisection pays only
  when main is red.
- **A version control of our own** (a patch algebra that merges without
  conflicts). Out of the product's scope: the code host is a port
  (ADR 0043) and git is the contract every workload already has.
- **An integrator role** that rebases and fixes conflicting PRs. A
  seventh role; `ci/roles.sh` holds six. The conflict goes back to the
  `dev-worker` as rework (ADR 0038).
- **Re-judge every PR whose base moved.** Correct, but every concurrent
  PR pays a second full gate run, mutation included, to catch an
  interaction that disjoint perimeters make rare and the main check
  catches anyway.
- **Check main before the next merge** (block merges while main is
  unchecked). That is the queue again, one merge at a time.
- **Restore main by force-pushing the last green commit.** It rewrites
  history others have fetched, loses any outside commit made meanwhile,
  and a protected branch refuses it. A revert is a commit: audited,
  itself reversible.
- **All the gates on main.** Mutation repeats each PR's own run on the
  sum of their lines; ADR 0053's `test-weakening` reads the ticket's
  declared removals, and main has no ticket.

## Consequences

- Every ticket that merges gains a `mainline` history entry before its
  release. `demo-rework`'s expected trail gains it; `./go audit` reads
  `main-green` as merged, and a reverted merge as the reason a merged PR
  is back at `ci-failed`.
- `adapters/inproc/run.sh` is unchanged; the demo's own loop is in the
  Makefile, declared.
- The L0 replays force-push the checkout's HEAD to Gitea's main at every
  crew run (`adapters/gitea/bootstrap.sh`). Within one tower run nothing
  is lost: every `assign` comes before the first merge. Across runs the
  `mainline` document's `green` stops being an ancestor and §3 falls back
  to the ticket's base. A tower that assigns after a merge, at L0, would
  reset main under it: noted, not changed here.
- Two culprits in one group need a person (§4). At L2, two `mainline`
  steps at once would race on the document; the inproc orchestrator
  applies one event at a time.

## Golden-rule check

`./go demo` runs `e2e` on ticket 0001, merged onto an unmoved main: the
merge's tree is the tree its CI passed, so the `mainline` step judges it
GO by §3's same-tree rule after one fetch, and the release follows as
before. `./go demo-mainline` is a separate target, not in the demo's
fixed list (ADR 0003).

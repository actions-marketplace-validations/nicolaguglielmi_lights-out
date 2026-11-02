# ADR 0032 — The deps gate judges what the diff introduces; advisories already in the base are reported, not gating

- Status: accepted (amends ADR 0015 §5 [the verdict is on the advisories the diff introduces, not on every advisory in the lockfiles at HEAD; the `[[IgnoredVulns]]` escape hatch is no longer the first answer to an overnight advisory]; consistent with ADR 0029 decision 6 and the mutation gate's ratchet [ADR 0015 §3], which already judges the touched lines against a measured baseline)
- Date: 2026-11-02
- Milestone: before the legacy experiment (plan §14)

## Context

ADR 0015 §5 stated its own determinism caveat: the lockfiles are pinned,
the advisory database is not, so the same commit can go from GO to NO-GO
overnight. On 2026-11-02 it did, for real. `./go demo-gates` NO-GOes on
its first fixture, `failing-test`, with `FAILED=deps` where `expect` says
`FAILED=test`: osv-scanner reports advisories published after the M4
baseline against four packages the app pins and no fixture touches —
`aiohttp 3.14.3` and `gitpython 3.1.62` in `app/backend/uv.lock`, `vite
8.3.0` and `source-map-js 1.2.1` in `app/frontend/package-lock.json`.
The GitHub `gates` job shows the same failure on every push since
2026-10-11 (runs 38141157514 and 41419136642). Every PR is judged on
debt it did not create, `./go demo` cannot reach its verdict, and the
golden rule is broken for every cloner.

Two facts make the caveat's prescribed fix (a bump) insufficient:

1. **The fixtures carry lockfile context.** `vulnerable-dep`'s patch adds
   an entry next to `"vite": "8.3.0"` in `package-lock.json`. Bumping vite
   moves that context and the patch no longer applies; a bump is a
   fixture re-recording, not a one-line fix.
2. **A legacy codebase starts with advisories.** Plan §14's experiment
   points the harness at a repository nobody has kept current. Under
   §5 as written, every ticket on it is NO-GO on `deps` before the first
   line of code is judged, so the harness cannot measure its own thesis.

## Decision

1. **The verdict is on the diff.** `gates/deps.sh` scans the workload's
   lockfiles twice — at the merge-base (`git show "$base:<path>"` into a
   temporary tree that keeps the file name, so osv-scanner recognises the
   format) and at `HEAD` — with `--format json`. A finding is the tuple
   `(ecosystem, package, advisory id)`. NO-GO when HEAD has a tuple the
   base does not; GO otherwise. A lockfile absent at the base has an empty
   base set, so a new lockfile is judged whole.
2. **Inherited advisories are reported, never silent.** Their count and
   tuples go to stderr on every run, and `.gates-out/deps.json` records
   `new` and `inherited` counts beside the verdict. Knowing the debt is
   the gate's job; refusing a PR for it is not.
3. **A scanner that cannot answer is still NO-GO.** Any exit other than 0
   (clean) or 1 (findings), on either scan, is NO-GO with the tool's error,
   as before.
4. **The app's own debt is a ticket, not this change.** Bumping the four
   packages means re-recording the fixtures whose patches carry lockfile
   context; `tickets/0006.md` records it.

## Alternatives rejected

- **Bump the four packages and keep §5.** Fixes today, breaks again on the
  next advisory, and re-records fixtures each time. It leaves the legacy
  experiment blocked.
- **`[[IgnoredVulns]]` for each advisory.** Silences the debt instead of
  reporting it, needs a manual entry per advisory per day, and does not
  scale to a legacy repository with dozens.
- **Scan against a pinned snapshot of the OSV database at L0.** Makes the
  demo deterministic but blinds the gate to every advisory published after
  the snapshot, which is the gate's purpose.
- **Score severity (NO-GO only above a CVSS threshold).** Any threshold
  here would be a number without a measurement behind it; and it still
  judges the PR on debt it did not create.

## Consequences

- The `failing-test` fixture reaches its `FAILED=test` again;
  `vulnerable-dep` still adds lodash 4.17.20 and is still `FAILED=deps`,
  now as a new tuple.
- A PR that upgrades a vulnerable package to a version that is still
  vulnerable under the same advisory is GO on `deps`: it introduces
  nothing. A PR that only removes advisories is GO.
- Two osv-scanner calls per run instead of one; the network dependency is
  unchanged.
- `main` can now carry known advisories with a green gate. They are
  printed on every run; ticket 0006 clears the app's current ones.

## Golden-rule check

`./go demo` no longer depends on the day's advisory feed for the app's
pinned packages. It still needs the network for osv-scanner, as before.
Passes once `./go demo` is green again on a clean container.

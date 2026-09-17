# ADR 0016 — Risk model: rules, not scores; three levels from five declared path-and-size signals; the merge decision is separate from the gate verdict; policy is `policy/merge.env`, readable by sh and python3

- Status: accepted (amended by ADR 0017 §2 [`platform` risk class gains roles/*, fixtures/*, .gemini/*], amended by ADR 0021: review decision now has a real consumer)
- Date: 2026-09-14
- Milestone: M4

## Context

Plan §7 M4: a risk-scoring script classifies the PR (auth, payments,
migrations, diff size) and decides auto-merge or a second review; done when
a PR touching a migration is high risk and not auto-merged. Plan §6 puts
risk scoring in `core/` and "what it takes to merge, promote, who touches
what" in `policy/`. Plan §8 step 4: the waitlist PR is "medium → review
agent". The app has no payments code (ADR 0005 routes; nothing under
`app/backend/meetups/` mentions money). Auth is `meetups/auth.py` (ADR 0005
§4), migrations are `app/backend/migrations/` (ADR 0008; "renaming that
directory silently changes risk scoring"). `release-freeze` is already a
flag evaluated by `core/launchpad.sh` (ADR 0013 §6): the first policy-shaped
gate, and not to be duplicated. Gates print one line (ADR 0002 contract);
M5 and M6 need the classification as data. Workbench has python3 3.13 and
jq, no pytest.

## Decision

1. **The classifier is `core/risk.py`, stdlib only, vendor-free.** Input on
   stdin: `git diff --numstat` lines (`added<TAB>deleted<TAB>path`; binary
   files show `-` and count as zero lines). Git is the VCS at every level;
   Gitea and GitHub are the CodeHost adapters, and none of them appears
   here. Output on stdout: one JSON object —
   `{"level": "high", "decision": "review", "signals": [{"name":
   "migrations", "paths": ["app/backend/migrations/0004_x.sql"]}],
   "size": {"lines": 12, "threshold": 200, "excluded": []}}`. Exit 0 when
   classified, 1 on malformed input. `gates/risk.sh` runs
   `git diff --numstat <base> HEAD | python3 core/risk.py --policy
   policy/merge.env > $GATES_OUT/risk.json`, prints the summary on stderr
   (`risk: level=high decision=review signals=migrations(...)`), and its
   contract line is **GO when the classifier ran**, NO-GO only when it could
   not (no range, git error, bad policy file). A high-risk PR that passes
   every gate is not a failure; it is a routing decision. M6's state machine
   reads `decision`, not a reason string.
2. **Rules, not points; level = the highest signal matched.** Signals, all
   evaluated on the repo-relative paths of the range (any status: added,
   modified, deleted, renamed):
   - `migrations` → **high**: `app/backend/migrations/*` (plan §7 done-when).
   - `auth` → **high**: `app/backend/meetups/auth.py`. Provenance, decision:
     a wrong auth change is a security incident, and the rollback that fixes
     production bugs is triggered by `verify/slo.sh`, which sees 5xx and
     latency, not "logged in as someone else"; no metric catches it, so a
     reviewer must.
   - `payments` → **high**: see §3.
   - `platform` → **high**: `gates/* ci/* verify/* core/* policy/*
     .github/* go Makefile workbench/* adapters/*`. Provenance: plan §6
     ("chi tocca cosa") and ADR 0015 §7's threat — the PR that edits
     `gates/mutation.sh` to always GO must not merge itself. The one signal
     beyond the plan's four; kept by owner decision, 2026-09-14.
   - `size` → **medium**: added + deleted lines ≥ `RISK_SIZE_MEDIUM_LINES =
     200`, after excluding `RISK_SIZE_EXCLUDE` (`*.lock`,
     `package-lock.json`: generated, never read by a reviewer). Provenance,
     external: SmartBear's Cisco code-review study, the source of the
     "200–400 lines per review" guidance every review handbook repeats;
     the low end, because past it defect detection starts to drop and
     nothing here should merge unseen at that size. No size-high: size is a
     review burden, not a blast radius.
   - nothing matched → **low**.
   No weights, no sum: a sum invents numbers with no provenance, and "high
   because it touches `app/backend/migrations/0004_x.sql`" is the sentence
   a reviewer, an agent and a slide can all read.
3. **The payments rule exists, is tested, and never fires on this app.**
   `RISK_HIGH_PAYMENTS = app/backend/meetups/payments*.py:
   app/backend/meetups/billing*.py`, with the comment "declared by plan §7;
   no such file exists today". `core/tests/test_risk.py` feeds the
   classifier a synthetic numstat containing such a path and asserts
   `high`, so the rule is proven to fire without a line of payments code —
   a declared rule with a test, not a hidden mock of one.
4. **Decision mapping: `low` → `auto-merge`; `medium`, `high` → `review`.**
   `RISK_AUTO_MERGE_LEVELS = low` in the policy file. The PR outcome
   `make gates` prints (ADR 0015 §2) combines this with the verdicts: any
   NO-GO → `blocked`; all GO and `auto-merge` → `GO: gates — risk low,
   auto-merge`; all GO and `review` → `GO: gates — risk high, review`. What
   `medium` and `high` mean beyond "not auto-merged" — review agent only,
   or review agent plus the human at `go-for-launch` — is M6's routing
   decision, not M4's; M4 keeps the plan's three words because plan §7 and
   §8 use both.
5. **Signals are the policy, not the code.** `core/risk.py` reads globs,
   the size threshold, the exclusions and the auto-merge levels from the
   policy file; the mapping "which signal is which level" is in the key
   names (`RISK_HIGH_*`, `RISK_SIZE_MEDIUM_LINES`). Adding a signal is a
   policy line and a test case, not a code change.
6. **`policy/merge.env`: `KEY=VALUE`, `#` comments, no quotes, no
   expansion, lists colon-separated.** Sourced by `gates/*.sh` with `.`,
   parsed by `core/risk.py` in six lines. Colons, not spaces, because an
   unquoted `KEY=a b` is a command in sh and quoting means a second parser
   rule. The same file holds ADR 0015 §3's `MUTATION_BASELINE` and
   `MUTATION_MARGIN` with their provenance comments (commit, date, tool,
   count, wall time). The file references, and does not restate, the
   promotion policy: a comment "release-freeze is a flag evaluated by
   core/launchpad.sh (ADR 0013 §6); promotion rules arrive with
   go-for-launch (M6)". The Makefile does not `include` it: the gates and
   the classifier read it explicitly, so `core/risk.py` runs the same under
   `unittest` and under `make`.
7. **The unit test is a repo self-check: `ci/core-tests.sh` runs
   `python3 -m unittest discover -s core/tests` in workbench**, no engine,
   no pytest, and joins `CI_CHECKS`. Cases, written from this ADR:
   migration path → high; auth → high; a payments path → high (§3); a
   platform path → high; 250 lines of docs → medium; a 30-line backend fix
   → low; lockfile lines excluded from size; empty diff → low; malformed
   numstat → exit 1.

## Alternatives rejected

- Additive scoring (points per signal, thresholds per level): every weight
  is a number without provenance, and "score 7" explains nothing.
- `risk` NO-GO on high: conflates "the PR failed a check" with "the PR
  needs a human"; M6 would have to parse the reason to tell them apart, and
  a high-risk PR that passed everything would be reported as broken.
- Decision computed by the classifier alone: it does not know the other
  gates' verdicts; the Makefile does.
- Backend code as a medium signal: fixture `honest-fix` (owner decision:
  low) touches `geocoder_client.py`; and "any behaviour change needs a
  reviewer" makes `low` an empty set.
- A `flags` signal on `app/flags/flags.json`: ADR 0013 makes edits to it
  the L0 kill switch's normal operation; scoring them is scoring the demo.
- JSON or TOML for the policy: python3 reads both, sh reads neither
  without jq in every gate (JSON) or a parser we do not have (TOML).
- Policy included by the Makefile: the classifier would depend on make's
  environment and could not be unit-tested standalone.
- `pytest` in workbench for `core/tests`: a package install to run three
  assertions; stdlib `unittest` is already there.
- A `verify/`-style hash test that the policy is identical at every level:
  M8's job for `gates/` and `verify/` already; `policy/` joins that list
  then.

## Consequences

- Five path globs are the model. Renaming `app/backend/migrations/` or
  `auth.py` silently changes risk (ADR 0008 already warned); the unit test
  uses the real paths, so the rename fails `ci`, which is the guard.
- `platform` makes every commit of this repo's own maintainers `high`;
  correct for the repo, and when M5 dogfoods the gates on this repo's PRs,
  nothing about the platform auto-merges.
- The size threshold counts tests and docs; a PR with 150 lines of test
  for a 20-line fix is `low`. Intended: tests are what the reviewer wants.
- Plan §8's "medium → review agent" holds for the waitlist PR only if it
  carries no migration (see ADR 0015 consequences). M6 decides how the
  waitlist is stored; a table makes it `high`, and the review agent starts
  either way.
- `medium` and `high` produce the same decision today; the distinction is
  carried, not consumed, until M6.
- The payments globs are two paths in a file; if a payments module ever
  arrives under another name, the rule does not fire and the unit test
  still passes. The policy comment names that limit.
- One more `ci` check, milliseconds.

## Golden-rule check

Nothing to install, nothing to pull, nothing to authenticate: python3 and
git in workbench, one text file under `policy/`. `./go demo` unchanged;
`./go demo-gates` exercises `low` and `high` from the committed fixtures.
Passes.

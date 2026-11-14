# Handoff: the sprint of 2026-11-12, the console slice (M48 and M50 panels; ADRs 0082, 0083 amended)

Branch `claude/sprint-console-panels-af00df`, cut from 8d36f9f (main with streams A, B and C). Pushed, no pull request. Nothing is on main; the coordinator merges.

## What changed

ADR amendments first (0082 and 0083, "Amendment 2026-11-13"), then the tests written from them, then the code.

- **Logbook 1.5** (`core/logbook/1.5.schema.json`), additions only, so it validates against 1.0 to 1.5; `golden-1.5.json` by the reader over the stub, `golden-1.4.json` kept as the old fixture.
  - `spend`: `core/spend.py`'s `report` over the documents read for `tickets`, plus `limits` (the two `SPEND_BUDGET_*`, or an error naming a malformed key), `lines` (`./go spend`'s stderr words without `[spend] `) and `summary` (its stdout detail). Unread tickets give the same error.
  - `dora`: `core/dora.py`'s `measures` over the logbook's own releases and tickets, plus `lines`. The window ends at the record's last event (history, release or answer `at`), never a clock: the logbook keeps "equal sources, equal bytes". A bad `WINDOW_DAYS` or a record with no time is `{ok: false, error}`.
  - `tickets[].outcome.stop` on `needs-human`: `"budget"` when the document has `budget.line` (then `line` is that line), `"cap"` otherwise.
- **`./go spend`** prints one more stderr line, the last: the budget (`budget: SPEND_BUDGET_TICKET_USD no limit, …`). Stdout unchanged. `core/spend.py` gains `lines`, `summary`, `budget_line`.
- **Console**: `section#dora` and `section#spend` on the Overview, after "Where the tickets are". Every word comes from the logbook's `lines`; the page formats no number. A 1.4 logbook says it has neither. A budget stop's now line is `Your turn: <budget line>; a person decides`.
- **Gitleaks**: `ci/gitleaks-worktree.toml` allowlists `generic-api-key` only, at `.crew/logbook.json` only, on a line that is exactly `"key": "<UPPER_SNAKE>"`. Planted checks: the same row at another path, a hex value in the logbook and other rules are still found. `ci/secrets.sh` proves the path ignored and untracked.
- **Stub**: tickets 0003 and 0010 carry a ledger (one priced, one replayed, one of unknown cost), and the stub policy sets `SPEND_BUDGET_TICKET_USD=1.00`.
- **Checks**: `core/tests/test_logbook.py` (two classes), `core/tests/test_spend.py` (`Lines`), `ci/logbook.sh` (1.5 hand checks with 25 plants, the budget variant, 1.5 schema typing), `ci/console-ui.py` (`ad.`: golden, a measure not measured, both unread, a 1.4 logbook, a budget stop; desktop and 390 px).
- **Docs**: ADRs 0082 and 0083, `docs/plans/console.md` (1.5 table), `console/README.md`, `docs/reference.md`, `README.md`, `site/index.html` (what is real), `docs/tutorial.md` (`./go dora` and `./go spend` after the demo, real output), a note in `docs/PLAN.md`. The golden's path moved in `site.yml`, `site/render.py`, README and site.

## Verified

- `ci/console-ui.py` in `localhost/m17-pw:dev`: GO (2 min 47 s). The `ad.` check was run alone with two plants (a renamed `#spend-budget`, the budget now line disabled): each was caught.
- `ci/logbook.sh` in the workbench: GO.
- From a full clone under `.crew/` (APP_PORT=9000, L0, no key):
  - `./go ci` GO at 37ca51a, 51 GO lines, 285 s.
  - `./go demo` GO, 662 s to rollback (stream A measured 655 s on its branch, budget 900 s).
  - `./go dora` GO (3 of 4 measured) and `./go spend` GO on the demo's record.
  - `./go ci` again with `.crew/logbook.json` present: GO, `secrets` GO, 327 s.
  - `./go down` after.
- docs-drift on the host: GO.
- Workflows on aa8eed6, all green: ci 43398452268 (with `console-ui`), self 43398451969, stranger 43398452003, podman 43398452005, package 43398452072, site 43398451968. The handoff commit after it changes only this file.

## Found on the way

- The first demo went NO-GO on `secrets-history`: the amendment's own text quoted a threshold row literally. The unpushed commit was reworded, and the toml description too.
- `ci/logbook.sh` needed SC2016 directives for the jq programs, which hold `$` amounts.

## Left out

- **The release role's run in the ledger** (optional in the brief). `core/promote.sh` runs outside the tower and names no ticket, and ADR 0079 §2 rules out a new write path. It needs its own ADR. At L0 no model runs for the brief.
- `.claude/context/HANDOFF.md`'s branch index is not touched: it conflicts at every landing.

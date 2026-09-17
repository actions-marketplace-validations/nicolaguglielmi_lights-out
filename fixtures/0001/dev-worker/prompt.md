# 0001 — Unknown venue makes `POST /api/meetups` answer 500 instead of the documented 502

- Status: open
- Labels: bug, app/backend, M4 (contract test), candidate first worker task (M5)
- Found: 2026-09-14, while writing `app/smoke.sh` at M2

## Problem

`app/README.md` and ADR 0006 document the geocoder dependency as: empty
result → `venue_lat`/`venue_lon` both `null`; timeout or 5xx → `502
{"detail":"geocoder unavailable"}`. The fake (`app/fakes/geocoder/server.py`)
answers `404` with an empty body for a venue that is not in
`app/contracts/geocoder/examples.json`. `meetups/geocoder_client.py` only
handles `>= 500`, so on a 404 it calls `response.json()` on an empty body,
which raises, and the request ends as an unhandled `500`.

The contract (`examples.json`) has no example for an unknown venue, so
neither the fake nor the client is tested for it. That gap is the bug.

## Acceptance criteria

Given a venue that no geocoder example knows
When a logged-in user posts it to `POST /api/meetups`
Then the response is not `500`, and it is one of the two documented
outcomes, chosen and written into the contract by this ticket:
either `201` with `venue_lat` and `venue_lon` both `null` (404 treated as
"no result"), or `502 {"detail":"geocoder unavailable"}` (404 treated as
"dependency broken").

Given the chosen outcome
When the contract test suite runs (`./go test`)
Then `app/contracts/geocoder/examples.json` contains an example for the
unknown-venue case, the fake serves it, and the client test asserts the
chosen status and body.

Given `./go up` and `./go smoke`
When the smoke posts `Milano, Duomo`
Then it still returns `201` with non-null coordinates (no regression on
the known-venue path).

## Perimeter

- `app/backend/meetups/geocoder_client.py`
- `app/fakes/geocoder/server.py`
- `app/contracts/geocoder/examples.json`
- `app/backend/tests/test_geocoder_*.py`
- `app/README.md`

## Notes for the implementer

- A real Nominatim returns `200 []` for an unknown place, which is why
  the client treats an empty list as `null` coordinates. Whether the fake
  should mimic that (`200 []`) or the client should tolerate `404` is the
  decision this ticket makes; the contract file is where it is recorded.
- Touches `app/backend/meetups/geocoder_client.py`,
  `app/fakes/geocoder/server.py`, `app/contracts/geocoder/examples.json`,
  `app/backend/tests/test_geocoder_*.py`, and one sentence in
  `app/README.md` — the `## Perimeter` section above, spelled as globs
  (docs/adr/0021 §5; not `app/backend/tests/*`, which the M5 fixture's
  stray `conftest.py` hunk would have passed). No migration, no auth: low
  risk under M4's scoring.
- One committed resolution of this bug is available in `gates/fixtures/honest-fix/` as a fixture patch for M5's first worker to pick up or reference; not merged, recorded here for continuity.
- At M5, the dev-worker agent picked up this ticket and opened PR #1, recorded in `fixtures/0001/dev-worker/`; status remains open (nothing merges at M5).
- At M6 the tower merges the replayed PR on the L0 Gitea during `./go e2e` and releases the (stable) canary that rolls back; the ticket stays open upstream — nothing merges into this repository's own main (ADR 0019 §5, §7).

---

Work only inside this repository checkout. Do not run git push or
git commit yourself: committing and pushing are not your job, the
platform does that if your role needs it. When you are done, or when
you believe your task is resolved, your final message is this run's
sole artefact: it must contain exactly what your instructions above
say your final message must be, nothing else.

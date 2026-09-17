# 0005 — Multiple geocoder matches are silently resolved to the first one, hiding an ambiguous venue

- Status: open
- Labels: bug, app/backend, M9 (medium-risk PR for the review step)
- Found: 2026-09-17, designing the review milestone's own acceptance run

## Problem

`meetups/geocoder_client.py` takes `results[0]` whenever the geocoder
returns a non-empty list, with no regard for how many results came back.
A short or common venue name — "San Giovanni", "Piazza del Popolo" — can
match several places across the country; today the meetup is silently
placed at whichever one the geocoder happened to list first, and neither
the API caller nor the record itself ever learns that a choice was made
on their behalf.

This is one instance of a wider gap: `app/README.md` and ADR 0006
document the geocoder dependency in one sentence per outcome, but the
committed contract and test suite exercise it unevenly. `examples.json`
holds a single-match and a zero-match example; the "unreachable"
(connection refused) path is only reached in tests by shutting the fake
down mid-test, not by a contract example; the API-level response body is
asserted for exactly one outcome (`502` on unreachable). Ambiguous
matches are not represented at any level. A dependency this central to
the one write endpoint the app has deserves the same case-by-case rigour
`docs/adr/0006` already gives the "empty" and "5xx" outcomes — this
ticket brings the ambiguous case up to that bar, and brings the two
existing outcomes' test coverage from unit-only to unit-and-API-level so
all three are documented, contracted, and asserted the same way.

## Acceptance criteria

Given a venue whose geocoder query returns more than one result
When a logged-in user posts it to `POST /api/meetups`
Then the response is `422 {"detail": "ambiguous venue, be more specific",
"candidates": [<display_name>, ...]}` listing every candidate the
geocoder returned, and no meetup record is created.

Given a venue whose geocoder query returns exactly one result
When posted to `POST /api/meetups`
Then behaviour is unchanged: `201` with that result's coordinates (no
regression on the known-venue path this ticket does not touch).

Given the chosen behaviour
When the contract test suite runs
Then `app/contracts/geocoder/examples.json` contains an example whose
response body has more than one entry, the fake serves it verbatim, and
a client test asserts the client raises on it (name the exception
distinctly from the existing "no result" and "dependency unavailable"
cases — conflating "ambiguous" with either would make this ticket's
whole point untestable), while a `POST /api/meetups` API-level test
asserts the full `422` body shown above, byte for byte.

Given the two outcomes this ticket does not change — a single match, and
an unreachable geocoder
When the API-level test suite runs
Then each of those two outcomes also has its own `POST /api/meetups`
test asserting the full response body and status (`201` with the
contract's coordinates; `502 {"detail": "geocoder unavailable"}`), so
every outcome this endpoint can produce is asserted at the API level,
not only through a lower-level client call. This does not change either
outcome's behaviour: it is coverage the ticket adds, not a rewrite of
what already passes.

Given the geocoder is reachable but answers slower than
`GeocoderUnavailable`'s current tests can trigger (today "unreachable"
is only tested by shutting the fake down mid-test, which is a different
failure at the `httpx` level than a slow-but-live server)
When the contract test suite runs
Then the fake supports one more field, `delay_seconds`, on a response
(a plain `time.sleep` before answering), one contract example uses it
with a delay past the client's timeout, and a client test proves a
genuinely slow geocoder — not a torn-down one — still raises
`GeocoderUnavailable`, so the timeout path this client already codes for
is exercised by something other than a severed connection.

Given a geocoder result missing `lat` or `lon`, or carrying a value that
does not parse as a number — malformed, not merely ambiguous or absent
(`docs/adr/0006` documents the shape as trusted; nothing today guards
against it, and the client would raise a raw `KeyError` or `ValueError`
that reaches the caller as an unhandled `500`, the exact failure mode
ticket 0001 already fixed for one other case)
When a logged-in user posts a venue that resolves to it
Then the client raises `GeocoderUnavailable` (a malformed dependency is
still a dependency failure, mapped to the existing `502` the same way an
unreachable one is), proven by three contract examples — one whose `lat`
field is not a number, one whose result is missing `lon` entirely, one
whose result is missing `lat` entirely, the three ways this can go wrong
kept distinguishable in the contract rather than conflated into a single
case — each with its own client test, plus one API-level test covering
any one of the three.

Given `app/README.md`'s one-sentence description of this dependency
When this ticket lands
Then it is replaced by one line per outcome (match, no match, ambiguous,
unreachable), each naming the status code and body shape, so the
documentation enumerates the same cases the contract and the tests do.

Given `./go up` and `./go smoke`
When the smoke posts `Milano, Duomo`
Then it still returns `201` with non-null coordinates (`Milano, Duomo`
resolves to exactly one candidate in the committed contract today; this
ticket must not change that).

## Perimeter

- `app/backend/meetups/geocoder_client.py`
- `app/backend/meetups/app.py`
- `app/fakes/geocoder/server.py`
- `app/contracts/geocoder/examples.json`
- `app/backend/tests/test_geocoder_*.py`
- `app/README.md`

## Notes for the implementer

- `geocoder_client.py` currently returns a `(lat, lon)` tuple or raises
  `GeocoderUnavailable`; this ticket adds a third outcome, so the
  cleanest shape is a new exception (e.g. `GeocoderAmbiguous`, carrying
  the candidate `display_name`s) that the caller in `app.py` catches
  alongside the existing `GeocoderUnavailable` handling, mapping it to
  `422` the same way `GeocoderUnavailable` maps to `502` today.
- The fake needs one small change beyond what already works: reading an
  optional `delay_seconds` key from the matched example's `response` and
  sleeping that long before writing the status and body — every other
  example omits the key and behaves exactly as today.
- The malformed-response case is the same shape as the existing
  `>= 500` and empty-result checks: wrap the `float(match["lat"])` /
  `float(match["lon"])` extraction (and the missing-key case) so any
  failure there raises `GeocoderUnavailable` instead of propagating the
  raw `KeyError`/`ValueError`, rather than adding a fourth, separate
  exception type for it.
- No migration, no authentication change: risk here is size, not the
  paths touched (docs/adr/0016 §2's size signal, not one of the four
  path signals).

---

Work only inside this repository checkout. Do not run git push or
git commit yourself: committing and pushing are not your job, the
platform does that if your role needs it. When you are done, or when
you believe your task is resolved, your final message is this run's
sole artefact: it must contain exactly what your instructions above
say your final message must be, nothing else.

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

Diff:

```diff
diff --git a/app/README.md b/app/README.md
index da68ecc..184ba9f 100644
--- a/app/README.md
+++ b/app/README.md
@@ -22,7 +22,12 @@ Signup creates a `users(id, email unique, password_hash)` row. Passwords are has
 
 ## External dependency: geocoder
 
-The `POST /api/meetups` route geocodes the venue name through `GET {GEOCODER_URL}/search?q=<venue>&format=jsonv2&limit=1` and stores `venue_lat`/`venue_lon`. Empty result yields both `null`, timeout or 5xx yields 502 with `{"detail":"geocoder unavailable"}`. The shape is Nominatim-compatible. When a venue is not in the contract, the fake geocoder returns 404 and the backend answers 500, not 502.
+The `POST /api/meetups` route geocodes the venue name through `GET {GEOCODER_URL}/search?q=<venue>&format=jsonv2&limit=1` and stores `venue_lat`/`venue_lon`. Four outcomes:
+- match: 201 with `{id, title, starts_at, venue, venue_lat, venue_lon, capacity}`
+- no match: 201 with `venue_lat: null` and `venue_lon: null`
+- ambiguous: 422 with `{"detail": "ambiguous venue, be more specific", "candidates": [<display_name>, ...]}`
+- unreachable: 502 with `{"detail": "geocoder unavailable"}` (timeout, connection error, 5xx, or malformed response)
+The shape is Nominatim-compatible. When a venue is not in the contract, the fake geocoder returns 404 and the backend answers 500, not 502.
 
 At L0, the fake geocoder is a Python stdlib `http.server` in compose, no dependencies. The contract is `app/contracts/geocoder/examples.json`: a list of `{request: {q}, response: {status, body}}` pairs, the executable spec for what the app can call. Both the fake and the client (backend) are tested against it.
 
diff --git a/app/backend/meetups/app.py b/app/backend/meetups/app.py
index 0dd05bc..6a1ff8c 100644
--- a/app/backend/meetups/app.py
+++ b/app/backend/meetups/app.py
@@ -4,6 +4,7 @@ import os
 
 import psycopg
 from fastapi import Depends, FastAPI, HTTPException, Response
+from fastapi.responses import JSONResponse
 from fastapi.staticfiles import StaticFiles
 from psycopg import errors as pg_errors
 from pydantic import BaseModel
@@ -11,7 +12,7 @@ from pydantic import BaseModel
 from meetups.auth import current_user_id, hash_password, issue_session, verify_password
 from meetups.db import get_db
 from meetups.flags import waitlist_enabled
-from meetups.geocoder_client import GeocoderUnavailable, geocode
+from meetups.geocoder_client import GeocoderAmbiguous, GeocoderUnavailable, geocode
 from meetups.metrics import CONTENT_TYPE, metrics_text, setup_metrics
 
 APP_VERSION = os.environ.get("APP_VERSION", "dev")
@@ -116,6 +117,14 @@ def create_meetup(
         venue_lat, venue_lon = geocode(body.venue)
     except GeocoderUnavailable:
         raise HTTPException(status_code=502, detail="geocoder unavailable")
+    except GeocoderAmbiguous as exc:
+        return JSONResponse(
+            status_code=422,
+            content={
+                "detail": "ambiguous venue, be more specific",
+                "candidates": exc.candidates,
+            },
+        )
     with db.cursor() as cur:
         cur.execute(
             "INSERT INTO meetups (title, starts_at, venue, venue_lat, venue_lon, capacity) "
diff --git a/app/backend/meetups/geocoder_client.py b/app/backend/meetups/geocoder_client.py
index e9256e9..972ad66 100644
--- a/app/backend/meetups/geocoder_client.py
+++ b/app/backend/meetups/geocoder_client.py
@@ -11,6 +11,12 @@ class GeocoderUnavailable(Exception):
     pass
 
 
+class GeocoderAmbiguous(Exception):
+    def __init__(self, candidates: list[str]) -> None:
+        super().__init__(f"ambiguous venue: {candidates}")
+        self.candidates = candidates
+
+
 def geocode(venue: str) -> tuple[float | None, float | None]:
     base_url = os.environ["GEOCODER_URL"]
     try:
@@ -23,8 +29,19 @@ def geocode(venue: str) -> tuple[float | None, float | None]:
         raise GeocoderUnavailable(str(exc)) from exc
     if response.status_code >= 500:
         raise GeocoderUnavailable(f"status {response.status_code}")
-    results = response.json()
+    try:
+        results = response.json()
+    except Exception as exc:
+        raise GeocoderUnavailable(f"malformed response: {exc}") from exc
+    if not isinstance(results, list):
+        raise GeocoderUnavailable("malformed response: expected list")
     if not results:
         return None, None
+    if len(results) > 1:
+        candidates = [m.get("display_name", "") for m in results]
+        raise GeocoderAmbiguous(candidates)
     match = results[0]
-    return float(match["lat"]), float(match["lon"])
+    try:
+        return float(match["lat"]), float(match["lon"])
+    except (KeyError, ValueError, TypeError) as exc:
+        raise GeocoderUnavailable(f"malformed response: {exc}") from exc
diff --git a/app/backend/tests/test_geocoder_client.py b/app/backend/tests/test_geocoder_client.py
index 86ada64..80fa81f 100644
--- a/app/backend/tests/test_geocoder_client.py
+++ b/app/backend/tests/test_geocoder_client.py
@@ -3,7 +3,7 @@ import threading
 import pytest
 
 from fakes.geocoder.server import create_server
-from meetups.geocoder_client import GeocoderUnavailable, geocode
+from meetups.geocoder_client import GeocoderAmbiguous, GeocoderUnavailable, geocode
 
 
 @pytest.fixture
@@ -17,6 +17,12 @@ def fake_server(monkeypatch):
     server.server_close()
 
 
+def _login(client, email="geo@example.com"):
+    client.post("/api/signup", json={"email": email, "password": "hunter2"})
+    resp = client.post("/api/login", json={"email": email, "password": "hunter2"})
+    return resp.json()["token"]
+
+
 def test_geocode_matching_venue_returns_contract_coordinates(fake_server):
     lat, lon = geocode("Milano, Duomo")
     assert lat == pytest.approx(45.4641)
@@ -27,6 +33,15 @@ def test_geocode_no_match_returns_none_none(fake_server):
     assert geocode("Nowhere, Atlantis") == (None, None)
 
 
+def test_geocode_ambiguous_venue_raises_geocoder_ambiguous(fake_server):
+    with pytest.raises(GeocoderAmbiguous) as exc_info:
+        geocode("Piazza del Popolo")
+    assert exc_info.value.candidates == [
+        "Piazza del Popolo, Roma, Lazio, Italy",
+        "Piazza del Popolo, Ravenna, Emilia-Romagna, Italy",
+    ]
+
+
 def test_geocode_raises_when_geocoder_unreachable(fake_server):
     fake_server.shutdown()
     fake_server.server_close()
@@ -34,15 +49,96 @@ def test_geocode_raises_when_geocoder_unreachable(fake_server):
         geocode("Milano, Duomo")
 
 
+def test_geocode_raises_when_geocoder_times_out(fake_server):
+    with pytest.raises(GeocoderUnavailable):
+        geocode("Slow, Timeout")
+
+
+def test_geocode_raises_when_lat_not_a_number(fake_server):
+    with pytest.raises(GeocoderUnavailable):
+        geocode("Malformed, Bad Lat")
+
+
+def test_geocode_raises_when_lon_missing(fake_server):
+    with pytest.raises(GeocoderUnavailable):
+        geocode("Malformed, Missing Lon")
+
+
+def test_geocode_raises_when_lat_missing(fake_server):
+    with pytest.raises(GeocoderUnavailable):
+        geocode("Malformed, Missing Lat")
+
+
+def test_create_meetup_returns_201_with_coordinates_on_single_match(client, fake_server):
+    token = _login(client, "single@example.com")
+    resp = client.post(
+        "/api/meetups",
+        json={
+            "title": "Duomo Visit",
+            "starts_at": "2026-01-01T10:00:00Z",
+            "venue": "Milano, Duomo",
+            "capacity": 10,
+        },
+        headers={"Authorization": f"Bearer {token}"},
+    )
+    assert resp.status_code == 201
+    body = resp.json()
+    assert body["title"] == "Duomo Visit"
+    assert body["starts_at"] == "2026-01-01T10:00:00Z"
+    assert body["venue"] == "Milano, Duomo"
+    assert body["venue_lat"] == pytest.approx(45.4641)
+    assert body["venue_lon"] == pytest.approx(9.1919)
+    assert body["capacity"] == 10
+    assert isinstance(body["id"], int)
+
+
+def test_create_meetup_returns_201_with_null_coordinates_when_no_match(client, fake_server):
+    token = _login(client, "nomatch@example.com")
+    resp = client.post(
+        "/api/meetups",
+        json={
+            "title": "Atlantis Meeting",
+            "starts_at": "2026-01-01T10:00:00Z",
+            "venue": "Nowhere, Atlantis",
+            "capacity": 5,
+        },
+        headers={"Authorization": f"Bearer {token}"},
+    )
+    assert resp.status_code == 201
+    body = resp.json()
+    assert body["venue_lat"] is None
+    assert body["venue_lon"] is None
+
+
+def test_create_meetup_returns_422_when_geocoder_ambiguous(client, fake_server):
+    token = _login(client, "ambiguous@example.com")
+    resp = client.post(
+        "/api/meetups",
+        json={
+            "title": "Piazza Gathering",
+            "starts_at": "2026-01-01T10:00:00Z",
+            "venue": "Piazza del Popolo",
+            "capacity": 10,
+        },
+        headers={"Authorization": f"Bearer {token}"},
+    )
+    assert resp.status_code == 422
+    assert resp.json() == {
+        "detail": "ambiguous venue, be more specific",
+        "candidates": [
+            "Piazza del Popolo, Roma, Lazio, Italy",
+            "Piazza del Popolo, Ravenna, Emilia-Romagna, Italy",
+        ],
+    }
+    meetups = client.get("/api/meetups").json()
+    assert not any(m["title"] == "Piazza Gathering" for m in meetups)
+
+
 def test_create_meetup_returns_502_when_geocoder_unreachable(client, fake_server):
     fake_server.shutdown()
     fake_server.server_close()
 
-    client.post("/api/signup", json={"email": "geo@example.com", "password": "hunter2"})
-    token = client.post(
-        "/api/login", json={"email": "geo@example.com", "password": "hunter2"}
-    ).json()["token"]
-
+    token = _login(client, "unreachable@example.com")
     resp = client.post(
         "/api/meetups",
         json={
@@ -54,3 +150,20 @@ def test_create_meetup_returns_502_when_geocoder_unreachable(client, fake_server
         headers={"Authorization": f"Bearer {token}"},
     )
     assert resp.status_code == 502
+    assert resp.json() == {"detail": "geocoder unavailable"}
+
+
+def test_create_meetup_returns_502_when_geocoder_malformed(client, fake_server):
+    token = _login(client, "malformed@example.com")
+    resp = client.post(
+        "/api/meetups",
+        json={
+            "title": "t",
+            "starts_at": "2026-01-01T10:00:00Z",
+            "venue": "Malformed, Bad Lat",
+            "capacity": 1,
+        },
+        headers={"Authorization": f"Bearer {token}"},
+    )
+    assert resp.status_code == 502
+    assert resp.json() == {"detail": "geocoder unavailable"}
diff --git a/app/contracts/geocoder/examples.json b/app/contracts/geocoder/examples.json
index 78944dd..fee46b2 100644
--- a/app/contracts/geocoder/examples.json
+++ b/app/contracts/geocoder/examples.json
@@ -31,5 +31,74 @@
       "status": 200,
       "body": []
     }
+  },
+  {
+    "request": { "q": "Piazza del Popolo" },
+    "response": {
+      "status": 200,
+      "body": [
+        {
+          "lat": "41.9109",
+          "lon": "12.4764",
+          "display_name": "Piazza del Popolo, Roma, Lazio, Italy"
+        },
+        {
+          "lat": "44.4173",
+          "lon": "12.2012",
+          "display_name": "Piazza del Popolo, Ravenna, Emilia-Romagna, Italy"
+        }
+      ]
+    }
+  },
+  {
+    "request": { "q": "Slow, Timeout" },
+    "response": {
+      "status": 200,
+      "delay_seconds": 2.5,
+      "body": [
+        {
+          "lat": "45.0689",
+          "lon": "7.6931",
+          "display_name": "Slow Venue, Torino, Italy"
+        }
+      ]
+    }
+  },
+  {
+    "request": { "q": "Malformed, Bad Lat" },
+    "response": {
+      "status": 200,
+      "body": [
+        {
+          "lat": "not-a-number",
+          "lon": "9.1919",
+          "display_name": "Malformed Lat Venue"
+        }
+      ]
+    }
+  },
+  {
+    "request": { "q": "Malformed, Missing Lon" },
+    "response": {
+      "status": 200,
+      "body": [
+        {
+          "lat": "45.4641",
+          "display_name": "Malformed Missing Lon Venue"
+        }
+      ]
+    }
+  },
+  {
+    "request": { "q": "Malformed, Missing Lat" },
+    "response": {
+      "status": 200,
+      "body": [
+        {
+          "lon": "9.1919",
+          "display_name": "Malformed Missing Lat Venue"
+        }
+      ]
+    }
   }
 ]
diff --git a/app/fakes/geocoder/server.py b/app/fakes/geocoder/server.py
index 1653f8d..f722aec 100644
--- a/app/fakes/geocoder/server.py
+++ b/app/fakes/geocoder/server.py
@@ -4,6 +4,7 @@ test suite's background thread — there is no second implementation."""
 
 import json
 import os
+import time
 from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
 from pathlib import Path
 from urllib.parse import parse_qs, urlparse
@@ -41,6 +42,9 @@ class GeocoderHandler(BaseHTTPRequestHandler):
             self.send_response(404)
             self.end_headers()
             return
+        delay = example.get("delay_seconds")
+        if delay:
+            time.sleep(delay)
         body = json.dumps(example["body"]).encode()
         self.send_response(example["status"])
         self.send_header("Content-Type", "application/json")
```

Handle ambiguous, slow, and malformed geocoder responses in meetups API

Resolves ticket 0005 by addressing cases where the geocoder returns ambiguous matches, slow answers exceeding the timeout, or malformed payloads missing expected numeric coordinates.

Key changes:
- `meetups/geocoder_client.py`: Introduced `GeocoderAmbiguous` carrying candidate display names when multiple results are returned. Wrapped coordinate parsing to raise `GeocoderUnavailable` on missing keys or non-numeric float values.
- `meetups/app.py`: Caught `GeocoderAmbiguous` in `POST /api/meetups` and returned `422 {"detail": "ambiguous venue, be more specific", "candidates": [...]}` without creating a meetup record.
- `fakes/geocoder/server.py`: Added support for an optional `delay_seconds` field on example responses to simulate slow upstream services.
- `contracts/geocoder/examples.json`: Added contract examples for ambiguous venue results ("Piazza del Popolo"), a slow response exceeding client timeout, and three distinct malformed payloads (non-numeric `lat`, missing `lon`, and missing `lat`).
- `backend/tests/test_geocoder_client.py`: Added unit and API-level integration tests covering each geocoder outcome: single match (201 with coordinates), no match (201 with null coordinates), ambiguous venue (422 with candidate list), timeout (502), unreachable service (502), and malformed payloads (502).
- `app/README.md`: Updated external dependency documentation with one line per outcome enumerating status codes and body shapes.

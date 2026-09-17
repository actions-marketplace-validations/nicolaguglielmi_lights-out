Handle unknown geocoder venue with 201 and null coordinates

When a venue is unknown or not present in the geocoder contract examples, the fake geocoder responds with 404. Previously, `meetups/geocoder_client.py` only handled responses with status code >= 500, attempting to call `response.json()` on 404 responses, which raised an unhandled JSONDecodeError resulting in an unexpected 500 Internal Server Error during `POST /api/meetups`.

This change resolves ticket 0001 by treating 404 responses from the geocoder as "no result":
- `app/backend/meetups/geocoder_client.py`: return `(None, None)` when the geocoder answers 404.
- `app/contracts/geocoder/examples.json`: record status 404 for the unknown-venue example (`Nowhere, Atlantis`).
- `app/backend/tests/test_geocoder_client.py`: add tests ensuring `geocode()` returns `(None, None)` for unknown venues and `POST /api/meetups` answers 201 with `venue_lat` and `venue_lon` both `null`.
- `app/README.md`: update the external dependency documentation to reflect the 201 null coordinates behaviour on unknown venues.

# ADR 0006 — The external service is a geocoder; the fake is stdlib; the contract is committed example pairs

- Status: accepted
- Date: 2026-09-14
- Milestone: M1

## Context

Plan §5 wants one endpoint that depends on an external service "so that a
contract test exists", and M4 turns that contract test into a CI gate. The
golden rule forbids anything that needs a key, and "no hidden mocks" means
a fake must be declared and must be the same code in tests and in compose.

## Decision

1. **The dependency is venue geocoding.** `POST /api/meetups` (ADR 0005)
   calls `GET {GEOCODER_URL}/search?q=<venue>&format=jsonv2&limit=1` with a
   2 s timeout and stores `venue_lat`/`venue_lon`. Empty result → both
   `null`, meetup still created. Timeout, connection error or 5xx → the
   endpoint answers `502 {"detail":"geocoder unavailable"}`. The shape is a
   subset of the public Nominatim search API, so the same client works
   against `https://nominatim.openstreetmap.org` if someone sets
   `GEOCODER_URL` to it; the README says the fake is a fake and that
   Nominatim's usage policy applies to anyone who does that.
2. **The fake** lives in `app/fakes/geocoder/server.py`: Python stdlib
   `http.server`, no dependencies, same base image as the backend, one
   compose service `geocoder` on port 8001, not published. It answers from
   the example table below and `404` for any other path.
3. **The contract** is `app/contracts/geocoder/examples.json`: a list of
   `{request: {q}, response: {status, body}}` pairs, including a no-match
   case. That file is the contract; there is no JSON schema at M1.
4. **Tested from both sides, pytest + httpx only.**
   `tests/test_geocoder_contract.py` starts the fake in a thread and
   asserts every example verbatim (fake against contract).
   `tests/test_geocoder_client.py` runs the backend client against the same
   thread and asserts the stored coordinates, the `null` case and the
   `502` path with the fake stopped (client against contract via fake).
   Both live in `app/backend/tests/` so `./go test` is one pytest run
   (ADR 0010).

## Alternatives rejected

- Calendar-invite service: a side effect on the registration path, so the
  test needs to observe an outbound call rather than a response; harder to
  read, and it entangles the endpoint the golden path (§8) modifies.
- Pact / `pactman` / `schemathesis`: a broker or a large dependency to
  express six example pairs. Revisit at M4 only if the gate needs
  provider-state verification, which a stdlib fake does not.
- JSON schema + `jsonschema` package: documentation of what the examples
  already state. Add it the day a second consumer of the contract appears.
- Fake as a FastAPI app: pulls the backend's dependency tree into a service
  whose whole job is `json.dumps` of a dict.
- Fake reachable only through compose in tests: forces `./go up` before
  `./go test` and makes the client test depend on the network.

## Consequences

- The "external" service is never really external at any level; L2 does
  not swap in Google Geocoding. If it ever does, that is an adapter with its
  own contract, not a change to this one.
- The fake in a thread and the fake in compose are the same module, but the
  compose one is never exercised by `./go test`; only `./go up` runs it.
  M2's engine-compat smoke request through Envoy should create a meetup so
  the container path is proven too.
- Adding an example means editing one JSON file and nothing else; that is
  also how the golden-path agent will be tempted to make a failing test pass.
  The gate-writer must keep the examples semantically obvious.

## Golden-rule check

No key, no network beyond compose, one shared base image. Passes.

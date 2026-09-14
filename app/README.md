# app — Meetup RSVP service

FastAPI backend + Postgres + React frontend. Demonstrates the core platform features in scope by M1: a realistic request path with two dependencies (database, external service), expand/contract SQL migrations, OTel metrics, OpenFeature flags, and a full UI.

## Routes

| Route | Auth | Behaviour |
|---|---|---|
| `POST /api/signup` | no | `{email,password}` → 201; 409 if email exists |
| `POST /api/login` | no | → `{token}`; 401 on bad credentials |
| `GET /api/meetups`, `GET /api/meetups/{id}` | no | list / one, with `venue_lat`/`venue_lon` |
| `POST /api/meetups` | bearer | `{title,starts_at,venue,capacity}` → 201; geocodes `venue` |
| `POST /api/meetups/{id}/registrations` | bearer | 201; 409 when full and flag `waitlist` off; 501 when full and flag on |
| `GET /healthz` | no | `{"status":"ok","version":APP_VERSION}` after `SELECT 1`; 503 otherwise |
| `GET /metrics` | no | Prometheus text |

The frontend is a React SPA (three views: login, meetup list with register, create meetup). TypeScript type-check runs in the image build; there is no frontend test framework at M1. The first behavioural frontend test arrives with the first frontend ticket (M10 at the latest), written from `design/CONTRACT.md`.

## Authentication

Signup creates a `users(id, email unique, password_hash)` row. Passwords are hashed with `stdlib hashlib.scrypt` (n=2^14, r=8, p=1) and stored as `scrypt$<salt>$<hash>`. Login issues a `secrets.token_urlsafe(32)` bearer token stored in `sessions(token_hash sha256, user_id, expires_at)` for 7 days. Zero dependencies, revocable, and all auth logic is in `backend/meetups/auth.py`.

## External dependency: geocoder

The `POST /api/meetups` route geocodes the venue name through `GET {GEOCODER_URL}/search?q=<venue>&format=jsonv2&limit=1` and stores `venue_lat`/`venue_lon`. Empty result yields both `null`, timeout or 5xx yields 502 with `{"detail":"geocoder unavailable"}`. The shape is Nominatim-compatible. When a venue is not in the contract, the fake geocoder returns 404 and the backend answers 500, not 502.

At L0, the fake geocoder is a Python stdlib `http.server` in compose, no dependencies. The contract is `app/contracts/geocoder/examples.json`: a list of `{request: {q}, response: {status, body}}` pairs, the executable spec for what the app can call. Both the fake and the client (backend) are tested against it.

## Schema and migrations

Forward-only numbered migrations in `app/backend/migrations/NNNN_<name>.sql`, applied by `python -m meetups.migrate` (40 lines of locking and retry logic). A table `schema_migrations(name text primary key, applied_at timestamptz)` records what ran. M1 demonstrates expand/contract on `meetups.starts_at` (text → timestamptz) with two intermediate revisions that ship together:
1. `0001_init.sql` — three tables: `users`, `sessions`, `meetups` (columns include `starts_at text`), `registrations`.
2. `0002_expand_starts_at.sql` — `ADD COLUMN starts_at_ts timestamptz; UPDATE meetups SET starts_at_ts = starts_at::timestamptz;` (old readers untouched, new writers fill both).
3. `0003_contract_starts_at.sql` — `DROP COLUMN starts_at; RENAME COLUMN starts_at_ts TO starts_at; ALTER ... SET NOT NULL;`.

The application code knows only the final schema. The deploy path is not demonstrated here; see ADR 0008 for the technique M4 will score as high risk.

## Metrics and flags

Metrics are OTel on Prometheus text format, exported by `GET /metrics`. The image sets `OTEL_SEMCONV_STABILITY_OPT_IN=http` for stable HTTP semantic conventions: metric names like `http_server_request_duration_seconds`, labels like `http_response_status_code`, `http_route`, `http_request_method`. Histograms use semconv defaults (buckets 0.005…10 seconds). Every request sends an `EvaluationContext(attributes={"version":APP_VERSION})` for version-specific flag targeting.

The flag `waitlist` (boolean, default off): when a meetup is full and the flag is on, `POST /registrations` answers `501 {"detail":"waitlist is not implemented; see the golden path ticket"}`. This is a declared missing feature (not a mock) that will become real at M3. When the flag is off, full meetups return 409 as usual.

Flags come from OpenFeature and flagd. At M2 the backend evaluates flags in-process (`FLAGD_RESOLVER=in-process`), synced from the flagd container, which serves `app/flags/flags.json` bind-mounted from the repo. Tests use file mode.

## Testing

Run `./go test` (from the repo root, inside workbench) to run pytest against compose Postgres. 25 tests at M1:
- Backend API contract tests (auth, routes, geocoder dependency).
- Geocoder fake and contract tests (fake serves the contract examples; client calls are correct).
- Migration tests (apply twice, idempotent; broken file leaves schema_migrations unchanged).

Frontend has no automated tests until M10; the type-check in the image build is the only check.

# ADR 0005 — Backend: FastAPI + psycopg 3 + plain SQL, stdlib auth, uv-managed on `python:3.13-slim-trixie`

- Status: accepted
- Date: 2026-09-14
- Milestone: M1

## Context

Plan §5 requires a FastAPI backend on Postgres with authentication, a schema
migration and an endpoint that depends on an external service, "small enough
to read in an hour". The plan's dev worker (M5) must be able to change it
from a ticket, and M4's risk scoring must recognise auth and migration
changes by path. Facts verified on PyPI and Docker Hub on 2026-09-14 are
cited inline.

## Decision

1. **Stack.** `fastapi 0.141.1`, `uvicorn 0.53.0` (no `[standard]`, h11
   only, one worker), `psycopg[binary] 3.3.5` with hand-written SQL in the
   handlers, `httpx 0.28.1` for the one outbound call. No ORM, no query
   builder. Sync `def` endpoints; FastAPI runs them in its threadpool, one
   `psycopg.connect()` per request, no pool. Package `app/backend/meetups/`,
   `pyproject.toml` with `requires-python = "==3.13.*"` and a committed
   `uv.lock` written by the workbench `uv 0.12.13`. Dev deps: `pytest 9.1.1`
   (httpx is already there). Nothing else at M1; ruff and friends are M4.
2. **Image.** `docker.io/library/python:3.13-slim-trixie@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285`
   (index updated 2026-09-02, 46 MB per arch). `pip install uv==0.12.13`
   in the build stage (same version as workbench, no second registry), then
   `uv sync --frozen --no-dev` into `/opt/venv`. Classic Containerfile
   syntax only: no `RUN --mount`, no heredocs (see ADR 0010, BuildKit).
3. **Domain and routes** (this table is the spec the gate-writer tests
   from; `app/README.md` carries it in full):

   | Route | Auth | Behaviour |
   |---|---|---|
   | `POST /api/signup` | no | `{email,password}` → 201; 409 if email exists |
   | `POST /api/login` | no | → `{token}`; 401 on bad credentials |
   | `GET /api/meetups`, `GET /api/meetups/{id}` | no | list / one, with `venue_lat`/`venue_lon` |
   | `POST /api/meetups` | bearer | `{title,starts_at,venue,capacity}` → 201; geocodes `venue` (ADR 0006) |
   | `POST /api/meetups/{id}/registrations` | bearer | 201; 409 when full and flag `waitlist` off; 501 when full and flag on (ADR 0007) |
   | `GET /healthz` | no | `{"status":"ok","version":APP_VERSION}` after `SELECT 1`; 503 otherwise |
   | `GET /metrics` | no | Prometheus text (ADR 0007) |

4. **Auth is stdlib.** `users(id, email unique, password_hash)` with
   `hashlib.scrypt` (n=2^14, r=8, p=1, 16-byte salt, stored as
   `scrypt$<salt>$<hash>`). `POST /api/login` issues
   `secrets.token_urlsafe(32)`; `sessions(token_hash sha256, user_id,
   expires_at)` stores it for 7 days; `Authorization: Bearer <token>`.
   Zero dependencies, revocable, and "touches auth" is `meetups/auth.py`.

## Alternatives rejected

- SQLAlchemy 2 + Alembic: two packages, `env.py`, revision ids and a
  models layer for four tables. Raw SQL is what a Flash-class agent writes
  correctly on the first try; Alembic revisions are not.
- Async endpoints + `psycopg` async or asyncpg: doubles the surface (event
  loop, pool lifecycle) for a demo that will see tens of requests/s.
- JWT (`pyjwt`): one dependency, plus a secret to manage, plus no logout
  without the sessions table anyway.
- `argon2-cffi` / `bcrypt` / `passlib`: the right answer in production;
  a wheel with C code for the demo's one login form. passlib is unmaintained.
- `python:3.13-alpine`: musl, `psycopg-binary` wheels are manylinux only.
- `uv` copied from `ghcr.io/astral-sh/uv`: a second registry and digest to
  pin, for the same binary `pip` fetches.

## Consequences

- A connection per request shows up as ~2–5 ms in every latency histogram.
  Both canary and stable pay it; M3's comparison is unaffected. If it ever
  matters, `psycopg[pool]` is the same project and a three-line change.
- scrypt in the request thread costs ~50 ms per login. Fine for the demo;
  the README must not present it as production auth.
- No ORM means no autogenerate; every schema change is a `.sql` file by
  hand (ADR 0008). That is the point.
- One uvicorn worker is forced by the Prometheus exporter (ADR 0007), so
  the container is the scaling unit, which is what Cloud Run assumes anyway.

## Golden-rule check

No account, no key: signup creates the demo user. One 46 MB base image
shared by backend, migrate and the fake (ADR 0006). Passes.

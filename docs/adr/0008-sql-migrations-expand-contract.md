# ADR 0008 — Forward-only numbered SQL migrations, applied by a `migrate` compose service; expand/contract on `meetups.starts_at`

- Status: accepted
- Date: 2026-09-14
- Milestone: M1

## Context

Plan §5 requires "a schema migration in expand/contract style". M4 marks
any PR touching a migration as high risk, by path. M8 runs migrations as a
Cloud Deploy pre-deploy job, not inside the serving container. ADR 0005
chose psycopg with no ORM, so there is nothing for Alembic to autogenerate.

## Decision

1. **Format.** `app/backend/migrations/NNNN_<name>.sql`, applied in
   lexical order, each file in one transaction (Postgres DDL is
   transactional). Forward-only: no down files. A table
   `schema_migrations(name text primary key, applied_at timestamptz)`
   records what ran.
2. **Runner.** `python -m meetups.migrate` (~40 lines): takes
   `pg_advisory_lock(<constant>)`, retries the connection for up to 60 s
   (Postgres may still be starting), applies the missing files, exits 0, or
   exits 1 with the file name and the SQL error. Same image as the backend.
3. **Wiring in compose.** A service `migrate` (image `backend`, command
   `python -m meetups.migrate`, `restart: "no"`), and
   `backend: depends_on: migrate: condition: service_completed_successfully`.
   No `healthcheck:` block on Postgres: the runner's retry loop is the wait.
   `service_completed_successfully` is implemented client-side by compose on
   the container's exit code, which is the smallest engine surface possible.
   `./go up` therefore applies migrations by starting the stack; a
   re-run is a no-op.
4. **The expand/contract example** is a type change, the case an in-place
   `ALTER` cannot do safely with old readers still running:
   - `0001_init.sql`: `users`, `sessions`, `meetups(..., starts_at text,
     venue text, venue_lat double precision, venue_lon double precision,
     capacity int)`, `registrations(meetup_id, user_id, created_at,
     unique(meetup_id,user_id))`.
   - `0002_expand_starts_at.sql`: `ALTER TABLE meetups ADD COLUMN
     starts_at_ts timestamptz; UPDATE meetups SET starts_at_ts =
     starts_at::timestamptz;` (old readers untouched, new writers fill both).
   - `0003_contract_starts_at.sql`: `ALTER TABLE meetups DROP COLUMN
     starts_at; ALTER TABLE meetups RENAME COLUMN starts_at_ts TO starts_at;
     ALTER TABLE meetups ALTER COLUMN starts_at SET NOT NULL;`
   The application code knows only the final schema. The README says the
   two revisions ship together at M1 and that the intermediate "write both"
   deploy is not demonstrated; the files show the technique M4 will score.

## Alternatives rejected

- Alembic: `alembic.ini`, `env.py`, `versions/` with hash ids and Python
  `op.*` calls, to run three SQL files. Also the tool most likely to make a
  Flash-class agent invent a revision graph.
- `dbmate`, `golang-migrate`, `yoyo`, `sqitch`: a binary or a package for
  the same 40 lines, and a second CLI to pin.
- Migrate at backend startup (entrypoint): one service less, but two
  revisions starting at once (M3) race on the same DDL, the container that
  loses fails, and M8 has to move it out again anyway.
- `depends_on: postgres: condition: service_healthy` with `pg_isready`:
  depends on the engine running healthchecks; rootless podman without a
  systemd user session does not, and compose then waits forever. The retry
  loop costs nothing and works everywhere.
- Down migrations: honest expand/contract is forward-only; a "down" of a
  contract is a data loss with a friendly name.

## Consequences

- The runner is 40 lines of repo code that a real tool would own: locking,
  ordering, recording. It has a test (apply twice, nothing happens; a broken
  file leaves `schema_migrations` unchanged).
- Two revisions in one milestone means the example is didactic; the first
  real expand/contract is whatever the golden path ticket needs, if any.
- `service_completed_successfully` joins the compose subset
  `ci-engine-compat` must prove at M2 (ADR 0004 point 5).
- Migration files are the M4 high-risk path: `app/backend/migrations/`.
  Renaming that directory silently changes risk scoring.

## Golden-rule check

Runs inside `./go up`, no extra command, no tool on the host. Passes.

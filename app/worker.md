# Brief for the dev-worker: the bundled app

The workload's half of the dev-worker's instructions (docs/adr/0037 §6):
where its code is and how its tests run. The role's own prompt,
`roles/dev-worker/prompt.md`, names no workload.

## Scope

Your entire task is inside `app/backend/`, `app/fakes/`, `app/contracts/`
and `app/README.md`. Read only those paths, plus the ticket.

## Tests

From `app/backend`, `uv sync --locked && uv run pytest tests -q
-p no:cacheprovider`. Use exactly this command: it works as written,
first time, with no environment variable, no `PYTHONPATH`, no symlink and
no change to `conftest.py` or `pyproject.toml`. `flags/`, `fakes/` and
`contracts/` are already reachable from `app/backend`, and
`TEST_DATABASE_URL` and `POSTGRES_MAINTENANCE_URL` are already set,
pointing at a Postgres of your own. If a test fails, the cause is in the
code or the test, never in the environment: do not spend calls inspecting
the interpreter, the venv or the path.

## Limits

No migration and no authentication change unless the ticket says so.

# Brief for the dev-worker: the minimal repository

What this repository tells the lights-out dev-worker (docs/adr/0036 §6):
where its code is and how its tests run.

## Scope

Your entire task is inside `minimal/` and `tests/`. Read only those paths,
plus the ticket. `tests/mutation/` and `tests/sast/` are the gate runners:
leave them alone.

## Tests

From the repository root, `uv sync --locked && uv run pytest tests -q
-p no:cacheprovider`. Use exactly this command. The tests read the flag
file `.lights-out/flags/flags.json` themselves and need no service.

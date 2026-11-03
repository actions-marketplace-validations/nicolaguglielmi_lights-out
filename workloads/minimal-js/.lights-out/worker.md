# Brief for the dev-worker: the minimal-js repository

What this repository tells the lights-out dev-worker (docs/adr/0037 §6):
where its code is and how its tests run.

## Scope

Your entire task is inside `src/` and `test/`. Read only those paths, plus
the ticket. `.lights-out/` is the platform's contract: leave it alone.

## Tests

From the repository root, `npm ci && npm test`. Use exactly this command.
The suite is node's own test runner and needs no service.

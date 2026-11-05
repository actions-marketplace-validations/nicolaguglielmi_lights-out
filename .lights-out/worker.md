# Brief for the dev-worker: lights-out itself

What this repository tells a lights-out dev-worker (docs/adr/0037 §6).
CLAUDE.md holds the rules every change here follows; read it first.

## Scope

The ticket names the paths. `.lights-out/` is the contract that judges
this repository (docs/adr/0049): leave it alone.

## Tests

From the repository root, `sh .lights-out/runners/self-checks.sh`, which
runs `make ci` inside the lights-out image. Use exactly this command.

# ADR 0001 — Profiles are plain env files; one level-agnostic Makefile

- Status: accepted
- Date: 2026-09-14
- Milestone: M0

## Context

The plan (section 3) defines four integration levels, L0..L3, each a profile
`profiles/lN.env` and a make target. Section 4 says every integration sits
behind a port with at least two adapters, and the adapter is chosen "from an
environment variable of the profile". The repo has one entrypoint, the
Makefile, and the golden rule requires `git clone && make demo` to work at L0
with nothing installed beyond Docker and make.

## Decision

Profiles are committed `KEY=VALUE` files, one per level, and the Makefile
selects one with `PROFILE ?= l0`, includes it and exports it. Every target
(`up`, `demo`, `demo-rollback`, `e2e`, `ci`, `clean`, `help`) is
level-agnostic and reads the adapter choice from environment variables named
after the ports of section 4, whose values are adapter directory names:

```
AGENT_HARNESS=replay   CODE_HOST=gitea        TRACKER=file
EVENT_BUS=pubsub-emulator  STATE_STORE=firestore-emulator
ORCHESTRATOR=inproc    DELIVERY=envoy-canary  METRICS=prometheus
FLAGS=flagd            REGISTRY=zot
```

Rules that make this hold:

1. Profile syntax is the intersection of make, POSIX shell and
   `docker compose --env-file`: `KEY=value`, no quotes, no spaces around `=`,
   no `$`, no `export`. One file, three consumers, zero parsing code.
2. Profiles are committed and contain no secrets. Secrets (API keys, GCP
   project) live in a gitignored `.env`, included after the profile with
   `-include .env`; `.env.example` is the committed template. L0 must run with
   no `.env` at all.
3. The canonical form is `make <target> PROFILE=l2`. No `up-l2` style aliases
   at M0; if M8 wants them, a single pattern rule is enough and does not
   change this decision.
4. `ci` is the one target that ignores the profile entirely (see ADR 0002).

## Alternatives rejected

- Per-level Makefiles (`Makefile.l0`..): duplicates every target four times;
  drift between levels is exactly the risk section 11 warns about.
- docker-compose profiles only: they select services, not adapter behaviour
  inside the code, and L2/L3 are not compose (Cloud Run, Cloud Deploy).
- A Python CLI (`lights-out up --profile l2`): a package and a venv before the
  first command runs, and a new concept with no consumer at M0. Make is
  already on every machine that has Docker.
- A single mutable `.env` with a `LEVEL=` switch: cannot diff levels, and is
  the file most likely to receive a real secret and get committed.

## Consequences

- The syntax constraint on profiles will bite: someone will want a computed
  or quoted value. Answer: it goes in the Makefile, not the profile. `make ci`
  should grep profiles for quotes, spaces and `$` and fail.
- `export` in make exports every variable, including make's own. Harmless,
  but recipes must not rely on a clean environment.
- Adapter names are now part of the public interface (env var values). Renaming
  an adapter directory is a breaking change for every profile.

## Golden-rule check

`make demo` with no arguments resolves to `l0`, needs no `.env`, no key, no
account. Passes.

#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-test: the PR gate for plan §7's first three M4 line items — unit,
# integration and contract tests — which are already one thing, not three:
# `docker-compose --profile test run --rm --build backend-test`, the exact
# command docs/adr/0010 §4 gives `./go test` (the Makefile `test:` target).
# That one pytest run starts the real compose Postgres (integration; no
# Testcontainers, docs/adr/0015 §1), builds the `test` stage and exercises
# the geocoder contract test (docs/adr/0006 §4) alongside every unit test
# in app/backend/tests/. No new test infrastructure is added here.
#
# require_range (docs/adr/0015 §2) still runs first, unconditionally: it is
# what ci/contract.sh's cold scan sees (NO-GO in one line, no docker, when
# BASE or HEAD is unset), matching every other gate's contract. This gate
# does not otherwise use $base/$head — it does not diff BASE..HEAD, it runs
# the whole suite against whatever is checked out at HEAD, same as
# `./go test`.
set -eu
# shellcheck disable=SC2209 # "test" is this gate's name (matches the file
# name and the NO-GO line), not a mistaken reference to the test(1) command
name=test
. ci/lib.sh
require_range

out=${GATES_OUT:-.gates-out}
mkdir -p "$out"

# compose's own stdout carries build and pytest output, not the gate's
# verdict: redirected to stderr. The exit code of the compose run is the
# gate's verdict; pytest's own failure output already tells the story, so
# it is not parsed or summarised here.
if docker-compose --profile test run --rm --build backend-test >&2; then
  printf '{"passed": true}\n' > "$out/test.json"
  go
fi

printf '{"passed": false}\n' > "$out/test.json"
nogo "pytest failed, see stderr"

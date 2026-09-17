#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-perimeter: proves core/perimeter.sh (ticket 0003's rule, docs/adr/0021
# §5) cold, no plane, milliseconds — a clean diff inside the ticket's
# globs, the literal `app/backend/tests/conftest.py` regression ticket
# 0003 came from (the real ticket 0001's own `## Perimeter`, and the M5
# fixture's own path list, frozen here rather than read live: `record`
# re-recording ticket 0001 under a fixed perimeter is the whole point of
# this rule, so a live read would break this exact case the day the fix
# lands — which it now has), a ticket with no `## Perimeter` section, and
# a backtick-wrapped glob. Written from the ADR's own repro command, not
# from reading the awk.
set -eu
name=perimeter
. ci/lib.sh

check=core/perimeter.sh
[ -f "$check" ] || nogo "$check not found"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mismatch=""

# run_case NAME WANT_RC TICKET_FILE: feeds $work/$NAME.paths on stdin,
# compares exit code; stdout/stderr are captured for the caller to check.
run_case() {
  case_name=$1
  want_rc=$2
  ticket_file=$3
  paths_file=$4
  rc=0
  sh "$check" "$ticket_file" <"$paths_file" \
    >"$work/$case_name.out" 2>"$work/$case_name.err" || rc=$?
  if [ "$rc" != "$want_rc" ]; then
    printf 'ci-perimeter: %s: want exit %s, got %s\n' "$case_name" "$want_rc" "$rc" >&2
    cat "$work/$case_name.err" >&2
    mismatch="$case_name(want exit $want_rc, got $rc)"
  fi
}

# (a) a clean diff, every path inside ticket 0001's real perimeter: exit 0,
# silent on both streams.
printf '%s\n' \
  'app/backend/meetups/geocoder_client.py' \
  'app/backend/tests/test_geocoder_client.py' \
  'app/README.md' \
  > "$work/clean.paths"
run_case clean 0 tickets/0001.md "$work/clean.paths"
if [ -z "$mismatch" ]; then
  [ -s "$work/clean.out" ] && mismatch="clean(unexpected stdout)"
  [ -s "$work/clean.err" ] && mismatch="clean(unexpected stderr: $(cat "$work/clean.err"))"
fi

# (b) the literal regression ticket 0003 came from: ticket 0001's real
# perimeter against the M5 fixture's own changed-path list, frozen here
# (docs/adr/0021 §5's consequences: re-recording ticket 0001 under the
# rule is this milestone's own landing-order requirement, so the live
# fixture is expected to stop reproducing this the moment that record
# succeeds — a live `grep` here would make this case pass for the wrong
# reason afterwards, silently).
if [ -z "$mismatch" ]; then
  printf '%s\n' \
    'app/README.md' \
    'app/backend/meetups/geocoder_client.py' \
    'app/backend/tests/conftest.py' \
    'app/backend/tests/test_geocoder_contract.py' \
    'app/contracts/geocoder/examples.json' \
    > "$work/fixture.paths"
  run_case fixture-outside 1 tickets/0001.md "$work/fixture.paths"
  if [ -z "$mismatch" ]; then
    want="app/backend/tests/conftest.py is outside the ticket's declared perimeter"
    got=$(cat "$work/fixture-outside.err")
    [ "$got" = "$want" ] || mismatch="fixture-outside(stderr: $got)"
    [ -s "$work/fixture-outside.out" ] && mismatch="fixture-outside(unexpected stdout)"
  fi
fi

# (c) a ticket with no `## Perimeter` section at all: exit 1, naming the
# ticket, never a silent pass.
if [ -z "$mismatch" ]; then
  cat > "$work/no-perimeter.md" <<'EOF'
# Ticket 9999 — no perimeter section

## Notes for the implementer

Nothing here declares a perimeter.
EOF
  printf 'any/path.py\n' > "$work/any.paths"
  run_case no-perimeter 1 "$work/no-perimeter.md" "$work/any.paths"
  if [ -z "$mismatch" ]; then
    want="ticket $work/no-perimeter.md has no ## Perimeter section"
    got=$(cat "$work/no-perimeter.err")
    [ "$got" = "$want" ] || mismatch="no-perimeter(stderr: $got)"
  fi
fi

# (d) a backtick-wrapped glob still parses: a list item written as
# `` - `app/x/*.py` `` matches a path under app/x/.
if [ -z "$mismatch" ]; then
  cat > "$work/backtick.md" <<'EOF'
# Ticket 9998 — backtick-wrapped globs

## Perimeter

- `app/x/*.py`

## Notes for the implementer

None.
EOF
  printf 'app/x/foo.py\n' > "$work/backtick.paths"
  run_case backtick 0 "$work/backtick.md" "$work/backtick.paths"
  if [ -z "$mismatch" ]; then
    [ -s "$work/backtick.out" ] && mismatch="backtick(unexpected stdout)"
    [ -s "$work/backtick.err" ] && mismatch="backtick(unexpected stderr)"
  fi
fi

[ -z "$mismatch" ] || nogo "stub case $mismatch disagrees with docs/adr/0021 §5"

go

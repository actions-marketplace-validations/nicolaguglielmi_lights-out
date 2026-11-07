#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-docs-drift: every path, `./go` or `make` target and `NAME=` key a page
# of this repository cites exists (docs/adr/0054 §3). It replaces
# ci/readme.sh, which read the README's `./go` words only. core/map.py reads
# the working tree and prints each citation that names nothing; MAP_EXCLUDE
# (the Makefile) leaves the plans and .claude/ alone, and ADRs and tickets
# are not pages. CONTAINER_CONNECTION is podman's own variable (ADR 0051),
# spelled nowhere in the code.
set -eu
name=docs-drift
. ci/lib.sh

: "${MAP_EXCLUDE:?MAP_EXCLUDE not set; run this via ./go ci}"
t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT

out=$(make --no-print-directory help 2>&1) || nogo "make --no-print-directory help exited nonzero" "$out"
printf '%s\n' "$out" | awk '/^  [a-z]/{print $1}' > "$t/targets"

# The check must be able to fail: a page citing a missing path, an unknown
# target and an unknown key gives exactly those three findings.
probe="$t/probe"
mkdir -p "$probe/docs"
git -C "$probe" init -q
printf 'x\n' > "$probe/docs/real.sh"
# shellcheck disable=SC2016 # the backticks are the page's Markdown, not a command
printf '# Page\n\n`docs/real.sh`, `docs/gone.sh`, `./go no-such-target`, `NO_SUCH_KEY=1`.\n' > "$probe/docs/page.md"
found=$(python3 core/map.py drift --repo "$probe" --targets "$t/targets" 2>&1) \
  && nogo "a page citing a missing path, target and key passed"
[ "$found" = "docs/page.md:3: command ./go no-such-target names nothing
docs/page.md:3: key NO_SUCH_KEY names nothing
docs/page.md:3: path docs/gone.sh names nothing" ] || nogo "the probe page did not give its three findings" "$found"

found=$(python3 core/map.py drift --repo . --targets "$t/targets" --exclude "$MAP_EXCLUDE" \
  --known CONTAINER_CONNECTION 2>&1) \
  || nogo "$(printf '%s\n' "$found" | wc -l | tr -d ' ') citation(s) name nothing" "$found"
go

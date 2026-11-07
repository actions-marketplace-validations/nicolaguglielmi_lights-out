#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-map: proves docs/adr/0054 end to end, cold: no engine, no network,
# temp git repositories and the real `make map`, core/map.py and the file
# Tracker.
#   (a) `make map` builds this repository at HEAD and says so (§2).
#   (b) `make map` builds workloads/minimal as an attached repository of
#       its own: its tickets are .lights-out/tickets (§1, ADR 0037 §2).
#   (c) a map built at one commit is refused at another, naming both (§2).
#   (d) after a merge that changes a path a page cites, after-merge builds
#       at the merge and files one docs ticket whose perimeter is that
#       page; a re-run files nothing new (§4).
#   (e) a merge that changes no cited path files nothing (§4).
# core/tests/test_map.py pins each rule on its own.
set -eu
name=map
. ci/lib.sh

unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY
export GIT_AUTHOR_NAME=ci GIT_AUTHOR_EMAIL=ci@localhost GIT_COMMITTER_NAME=ci GIT_COMMITTER_EMAIL=ci@localhost
export PYTHONDONTWRITEBYTECODE=1
t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT
commit() { r=$1; shift; git -C "$r" -c commit.gpgsign=false commit -q "$@"; }
# A nested make starts from the bundled workload unless ATTACHED says otherwise.
mk() { env -u WORKLOAD -u MAKEFLAGS -u MFLAGS -u MAKELEVEL make --no-print-directory "$@"; }

# (a)
head=$(git rev-parse HEAD)
line=$(mk map MAP_FILE="$t/self.sqlite" 2>&1) || nogo "make map on this repository failed" "$line"
case "$line" in "GO: map — $head "*" → $t/self.sqlite") ;; *) nogo "make map on this repository: $line" ;; esac

# (b)
cp -R workloads/minimal "$t/minimal"
git -C "$t/minimal" init -q -b main
git -C "$t/minimal" add -A
commit "$t/minimal" -m "the user's repository"
line=$(mk map ATTACHED="$t/minimal" MAP_FILE="$t/minimal.sqlite" 2>&1) || nogo "make map on workloads/minimal failed" "$line"
case "$line" in "GO: map — $(git -C "$t/minimal" rev-parse HEAD) "*"ticket=1"*) ;;
  *) nogo "make map on workloads/minimal did not map its one ticket: $line" ;; esac

# (c)
printf '\n' >> "$t/minimal/README.md"
commit "$t/minimal" -am "a later commit"
later=$(git -C "$t/minimal" rev-parse HEAD)
if err=$(python3 core/map.py slice --map "$t/minimal.sqlite" --base "$later" \
    --ticket "$t/minimal/.lights-out/tickets/0001.md" 2>&1 >/dev/null); then
  nogo "a map of an earlier commit was read at $later"
fi
case "$err" in *"built at $(git -C "$t/minimal" rev-parse HEAD^)"*"the base is $later"*"./go map"*) ;;
  *) nogo "a stale map was refused without naming both commits: $err" ;; esac

# (d) the merge changes tests/sast/run.sh, which .lights-out/worker.md
# cites through `tests/sast/`.
git -C "$t/minimal" checkout -q -b ticket/0001
printf '# changed\n' >> "$t/minimal/tests/sast/run.sh"
commit "$t/minimal" -am "fix"
git -C "$t/minimal" checkout -q main
git -C "$t/minimal" -c commit.gpgsign=false merge -q --no-ff -m "Merge pull request 'fix' (#1) from ticket/0001 into main" ticket/0001
merge=$(git -C "$t/minimal" rev-parse HEAD)
after() {
  TRACKER=file TICKETS_DIR="$t/tickets" python3 core/map.py after-merge --clone-url "$t/minimal" \
    --merge-sha "$1" --tickets .lights-out/tickets --targets /dev/null --out "$t/merged.sqlite"
}
out=$(after "$merge" 2>&1) || nogo "after-merge failed" "$out"
[ "$(printf '%s' "$out" | jq -r '.map.sha + " " + .map.docs_ticket')" = "$merge 0001" ] \
  || nogo "after-merge did not record the merge and docs ticket 0001: $out"
grep -qxF -- "- Origin: docs merge $merge" "$t/tickets/0001.md" || nogo "the docs ticket carries no origin"
perimeter=$(awk '/^## Perimeter/{p=1; next} p && /^## /{exit} p && /^- /' "$t/tickets/0001.md")
# shellcheck disable=SC2016 # the backticks are the ticket's Markdown, not a command
[ "$perimeter" = '- `.lights-out/worker.md`' ] || nogo "the docs ticket's perimeter is not the page alone: $perimeter"
out=$(after "$merge" 2>&1) || nogo "after-merge re-run failed" "$out"
set -- "$t/tickets"/*
[ "$*" = "$t/tickets/0001.md" ] || nogo "a re-run filed a second docs ticket: $*"

# (e)
printf 'notes\n' > "$t/minimal/NOTES.txt"
git -C "$t/minimal" add NOTES.txt
commit "$t/minimal" -m "uncited"
out=$(after "$(git -C "$t/minimal" rev-parse HEAD)" 2>&1) || nogo "after-merge on an uncited change failed" "$out"
[ "$(printf '%s' "$out" | jq -r '.map.docs_ticket')" = null ] || nogo "a change no page cites filed a docs ticket: $out"
go

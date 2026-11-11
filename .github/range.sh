#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# The range a push of `self` judges (docs/adr/0074), run by its gates job
# in a full checkout of the pushed commit. Appends to $GITHUB_OUTPUT:
#   base=<sha>      §1: the nearest first-parent ancestor of HEAD (HEAD^1
#                   first, never HEAD) whose most recent `lights-out gates`
#                   check by GitHub Actions is success, ignoring checks
#                   whose record names another head
#   judged=<shas>   §3: for each merge on the first-parent path base..HEAD,
#                   the nearest commit of its second parent's first-parent
#                   chain, before the merge-base, whose most recent check
#                   is a green record (§2, external_id <base>..<itself>),
#                   kept only when sound: its records' bases lead to an
#                   ancestor-or-self of base before an unrecorded commit
# No green ancestor within $bound first-parent commits: one NO-GO line on
# stdout, exit 1. Everything else on stderr and in the step summary. Needs
# git, gh and jq, GH_TOKEN with checks: read.
set -eu

# Provenance, decision (docs/adr/0074 §1): one API call per commit, a
# tenth of the token's 1,000 requests an hour, eight times the longest
# branch here (M39's 12 commits).
bound=100

repo=${GITHUB_REPOSITORY:?run this in a GitHub Actions job}
output=${GITHUB_OUTPUT:?run this in a GitHub Actions job}
summary=${GITHUB_STEP_SUMMARY:-/dev/null}
head=$(git rev-parse HEAD)
cache=$(mktemp -d)
trap 'rm -rf "$cache"' EXIT

# latest <sha>: "<conclusion> <external_id>" of the commit's most recent
# lights-out gates check posted by GitHub Actions whose record, if any,
# names this commit; nothing when there is none or the API fails (a failure
# only widens what is judged).
latest() {
  if [ ! -f "$cache/$1" ]; then
    if gh api "repos/$repo/commits/$1/check-runs?check_name=lights-out%20gates&filter=all&per_page=100" > "$cache/$1.json" 2>"$cache/$1.err"; then
      jq -r --arg sha "$1" '[.check_runs[]
          | select(.app.slug == "github-actions")
          | select((.external_id // "") == "" or ((.external_id // "") | endswith(".." + $sha)))]
        | max_by(.id) // empty | "\(.conclusion // "none") \(.external_id // "")"' \
        "$cache/$1.json" > "$cache/$1" 2>/dev/null || : > "$cache/$1"
    else
      printf 'range: the checks of %s could not be read: %s\n' "$1" "$(head -c 300 "$cache/$1.err")" >&2
      : > "$cache/$1"
    fi
  fi
  cat "$cache/$1"
}

green() {
  case "$(latest "$1")" in success\ *|success) return 0 ;; *) return 1 ;; esac
}

# record <sha>: the base its green record names, when the most recent check
# is a green record of this very commit and the base is one of its
# ancestors; nothing otherwise.
record() {
  l=$(latest "$1")
  case "$l" in success\ *..*) ;; *) return 0 ;; esac
  r=${l#success }
  b=${r%%..*}
  [ "${r#*..}" = "$1" ] || return 0
  git rev-parse -q --verify "$b^{commit}" >/dev/null 2>&1 || return 0
  git merge-base --is-ancestor "$b" "$1" 2>/dev/null || return 0
  git rev-parse "$b^{commit}"
}

# sound <sha>: its records' bases reach an ancestor-or-self of $base
# within $bound steps, never through an unrecorded commit.
sound() {
  t=$1
  i=0
  while [ "$i" -lt "$bound" ]; do
    b=$(record "$t")
    [ -n "$b" ] || return 1
    if git merge-base --is-ancestor "$b" "$base" 2>/dev/null; then return 0; fi
    t=$b
    i=$((i + 1))
  done
  return 1
}

base=""
for c in $(git rev-list --first-parent --max-count="$bound" "$head^1" 2>/dev/null); do
  if green "$c"; then base=$c; break; fi
done
if [ -z "$base" ]; then
  printf 'NO-GO: gates — no green ancestor within %s first-parent commits of %s\n' "$bound" "$head"
  exit 1
fi

judged=""
for m in $(git rev-list --first-parent --merges "$base..$head"); do
  p2=$(git rev-parse -q --verify "$m^2") || continue
  mb=$(git merge-base "$m^1" "$p2") || continue
  for c in $(git rev-list --first-parent --max-count="$bound" "$p2" "^$mb"); do
    [ -n "$(record "$c")" ] || continue
    if sound "$c"; then
      case " $judged " in *" $c "*) ;; *) judged="${judged:+$judged }$c" ;; esac
    else
      printf 'range: %s, the nearest record on the side of the merge %s, does not lead back to %s: not judged (docs/adr/0074 §3)\n' "$c" "$m" "$base" >&2
    fi
    break
  done
done

printf 'base=%s\njudged=%s\n' "$base" "$judged" >> "$output"
printf 'range: base %s (its last green ancestor), judged trees: %s\n' "$base" "${judged:-none}" >&2
{
  printf 'Judged from %s, the nearest green first-parent ancestor of %s (docs/adr/0074 §1).\n' "$base" "$head"
  if [ -n "$judged" ]; then
    printf 'Mutation skips the lines shared with the judged trees %s (§3).\n' "$judged"
  fi
} >> "$summary"

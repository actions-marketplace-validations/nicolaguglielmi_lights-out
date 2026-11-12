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
#                   A rewritten ancestor with no check of its own inherits
#                   the green of the commit .github/rewritten says it
#                   replaced, when both have the same tree, or of its
#                   parent, when it only translates the parent's excuses (§5)
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

# same_tree <new> <old>: the API gives <old>'s tree and it is <new>'s.
same_tree() {
  ot=$(gh api "repos/$repo/git/commits/$2" 2>/dev/null | jq -r '.tree.sha // empty' 2>/dev/null) || return 1
  [ -n "$ot" ] && [ "$ot" = "$(git rev-parse "$1^{tree}")" ]
}

# inherited <sha>: §5, a history rewritten without a change to any tree
# (an author fixed, a trailer dropped) keeps its greens. The commit has no
# check of its own, .github/rewritten (git filter-repo's commit-map, "<new>
# <old>" per line) names the commit it replaced, that commit is green and
# both have the same tree. It is a base, never a record.
inherited() {
  [ -f .github/rewritten ] || return 1
  old=$(awk -v n="$1" '$1 == n && length($2) == 40 && $2 !~ /[^0-9a-f]/ { print $2; exit }' .github/rewritten)
  [ -n "$old" ] || return 1
  case "$(latest "$old")" in success\ *|success) ;; *) return 1 ;; esac
  same_tree "$1" "$old" || return 1
  printf 'range: %s inherits the green of %s, which it replaced with the same tree (docs/adr/0074 §5)\n' "$1" "$old" >&2
}

# own_green <sha>: its own green, or one inherited from the commit it replaced.
own_green() {
  case "$(latest "$1")" in
    success\ *|success) return 0 ;;
    '') inherited "$1" ;;
    *) return 1 ;;
  esac
}

# translated <sha>: §5, the excuses follow the commits. A commit with no
# check of its own whose first parent is green (own_green) and whose tree
# is exactly the tree .github/excuses.sh makes of that parent, the parent's
# .lights-out/.gitleaksignore with its rewritten commits renamed and
# nothing else, inherits the parent's green. The secrets gate reads its
# excuses from the base, so the base must be such a commit for a rewritten
# history to be judged at all.
translated() {
  [ -f .github/excuses.sh ] || return 1
  p=$(git rev-parse -q --verify "$1^1") || return 1
  own_green "$p" || return 1
  x=$(sh .github/excuses.sh "$p" 2>/dev/null) || return 1
  [ "$x" != "$p" ] && [ "$(git rev-parse "$x^{tree}")" = "$(git rev-parse "$1^{tree}")" ] || return 1
  printf 'range: %s inherits the green of %s, of which it only translates the excuses (docs/adr/0074 §5)\n' "$1" "$p" >&2
}

green() {
  own_green "$1" && return 0
  [ -n "$(latest "$1")" ] && return 1
  translated "$1"
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

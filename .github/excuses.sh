#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# .github/excuses.sh BASE (docs/adr/0074 §5): the base self's judge reads
# its excuses from. gitleaks excuses a finding by a fingerprint that names
# a commit, so a rewritten history leaves the base's
# .lights-out/.gitleaksignore naming commits that are gone. Each
# fingerprint whose commit .github/rewritten names as replaced, by a
# commit with the same tree as the API gives for the old one, is made to
# name the new commit. Nothing else changes. Prints BASE when nothing is
# translated, else a local commit: BASE's tree with the translated file,
# BASE its only parent, never pushed. Needs git, gh and jq, and
# GITHUB_REPOSITORY.
set -eu
base=${1:?usage: .github/excuses.sh BASE}
repo=${GITHUB_REPOSITORY:?run this in a GitHub Actions job}
file=.lights-out/.gitleaksignore

# same_tree <new> <old>: the API gives <old>'s tree and it is <new>'s.
same_tree() {
  ot=$(gh api "repos/$repo/git/commits/$2" 2>/dev/null | jq -r '.tree.sha // empty' 2>/dev/null) || return 1
  [ -n "$ot" ] && [ "$ot" = "$(git rev-parse "$1^{tree}")" ]
}

if [ ! -f .github/rewritten ] || ! git cat-file -e "$base:$file" 2>/dev/null; then
  printf '%s\n' "$base"
  exit 0
fi
t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT
git show "$base:$file" > "$t/in"
: > "$t/out"
n=0
while IFS= read -r line || [ -n "$line" ]; do
  sha=${line%%:*}
  new=""
  if [ "$sha" != "$line" ] && [ "${#sha}" -eq 40 ]; then
    new=$(awk -v o="$sha" '$2 == o && length($1) == 40 && $1 !~ /[^0-9a-f]/ { print $1; exit }' .github/rewritten)
  fi
  if [ -n "$new" ] && same_tree "$new" "$sha"; then
    printf '%s:%s\n' "$new" "${line#*:}" >> "$t/out"
    printf 'excuses: %s now names %s, which replaced %s with the same tree (docs/adr/0074 §5)\n' "${line#*:}" "$new" "$sha" >&2
    n=$((n + 1))
  else
    printf '%s\n' "$line" >> "$t/out"
  fi
done < "$t/in"
if [ "$n" -eq 0 ]; then
  printf '%s\n' "$base"
  exit 0
fi
blob=$(git hash-object -w "$t/out")
GIT_INDEX_FILE=$t/index git read-tree "$base"
GIT_INDEX_FILE=$t/index git update-index --cacheinfo "100644,$blob,$file"
tree=$(GIT_INDEX_FILE=$t/index git write-tree)
GIT_AUTHOR_NAME=self GIT_AUTHOR_EMAIL=self@localhost GIT_COMMITTER_NAME=self GIT_COMMITTER_EMAIL=self@localhost \
  git commit-tree "$tree" -p "$base" -m "the excuses of $base, translated through .github/rewritten (docs/adr/0074 §5)"

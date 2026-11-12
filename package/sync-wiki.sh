#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# package/sync-wiki.sh PAGES DIR [--push] (docs/adr/0077 §3): clones the
# wiki's repository into DIR, replaces every file in it with the pages in
# PAGES (what package/wiki.py rendered), and commits them as the owner's
# noreply identity, as sync-action.sh does (ADR 0075 §3). Pushes only with
# --push; without it the commit stays in DIR and the push is printed.
# Pages equal to the wiki's commit and push nothing. A wiki with no
# repository yet is a failure naming the owner's first step: GitHub creates
# it only when a first page is saved in the web UI.
#
#   WIKI_REMOTE  the repository (default https://github.com/nicolaguglielmi/lights-out.wiki.git)
#   WIKI_TOKEN   for an https remote: the workflow's GITHUB_TOKEN, with
#                contents: write; handed to git through GIT_CONFIG_* (never
#                a URL, an argument or a file), as actions/checkout does.
#
# Glue, not a gate: what it did on stdout, git's noise and the reason of a
# failure on stderr.
set -eu
usage='usage: package/sync-wiki.sh PAGES DIR [--push]'
pages=${1:?$usage}
dir=${2:?$usage}
push=0
case "${3:-}" in --push) push=1 ;; "") ;; *) echo "$usage" >&2; exit 2 ;; esac
remote=${WIKI_REMOTE:-https://github.com/nicolaguglielmi/lights-out.wiki.git}

[ -f "$pages/Home.md" ] || { echo "sync-wiki: $pages has no Home.md; render it first with package/wiki.py" >&2; exit 1; }
case "$remote" in
  https://*)
    [ -n "${WIKI_TOKEN:-}" ] || { echo "sync-wiki: $remote needs WIKI_TOKEN (the job's GITHUB_TOKEN, contents: write)" >&2; exit 1; }
    # git reads these as `-c http.https://github.com/.extraheader=...`, without them appearing in ps or .git/config.
    GIT_CONFIG_COUNT=1
    GIT_CONFIG_KEY_0=http.https://github.com/.extraheader
    GIT_CONFIG_VALUE_0="AUTHORIZATION: basic $(printf 'x-access-token:%s' "$WIKI_TOKEN" | base64 | tr -d '\n')"
    export GIT_CONFIG_COUNT GIT_CONFIG_KEY_0 GIT_CONFIG_VALUE_0 ;;
esac

if ! git clone -q "$remote" "$dir" >&2; then
  echo "sync-wiki: cannot clone $remote. If the wiki has no page yet, save a first page in the repository's Wiki tab: GitHub creates the wiki's repository only then (docs/launch/checklist.md, The wiki)" >&2
  exit 1 # no wiki repository
fi
branch=$(git -C "$dir" symbolic-ref --short HEAD)
find "$dir" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -R "$pages/." "$dir/"
git -C "$dir" add -A
if git -C "$dir" diff --cached --quiet; then
  echo "wiki: $branch already holds these pages; nothing to push"
  exit 0
fi
# the owner's noreply identity, author and committer; the environment cannot override it
email=45848139+nicolaguglielmi@users.noreply.github.com
v=$(sed -n 's/^version=//p' lights-out 2>/dev/null || true)
GIT_AUTHOR_NAME=Nicola GIT_AUTHOR_EMAIL=$email GIT_COMMITTER_NAME=Nicola GIT_COMMITTER_EMAIL=$email git -C "$dir" \
  commit -q -m "The wiki at lights-out v${v:-unknown}, rendered by package/wiki.py (docs/adr/0077)"
git -C "$dir" show --stat --format='wiki: %h %s' HEAD

if [ "$push" = 1 ]; then
  git -C "$dir" push -q origin "HEAD:refs/heads/$branch" >&2
  echo "wiki: pushed $branch to $remote"
else
  echo "wiki: dry run, nothing pushed; with --push: git push origin HEAD:refs/heads/$branch"
fi

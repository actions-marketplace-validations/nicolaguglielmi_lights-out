#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# package/sync-action.sh NAME VERSION DIR [--push] (docs/adr/0075 §3): copies
# actions/NAME/action.yml, actions/NAME/README.md and LICENSE to the root of
# NAME's own repository, the Marketplace's copy (ADR 0057 §7), commits them as
# the owner's noreply identity and tags vVERSION, in a clone at DIR. Run from
# the lights-out repository's root. Pushes the branch and the tag only with
# --push; without it the commit and the tag stay in DIR, and the push is
# printed. A remote tag vVERSION that already holds the same three files is
# success with nothing pushed; one that holds other files is a failure: a
# published tag never moves.
#
#   ACTION_REMOTE       the repository (default https://github.com/nicolaguglielmi/NAME.git)
#   ACTION_REPOS_TOKEN  for --push to an https remote: a fine-grained token on
#                       the two Action repositories only, Contents read and
#                       write; handed to git through GIT_CONFIG_* (never a URL,
#                       an argument or a file), as actions/checkout does.
#
# Glue, not a gate: what it did on stdout, git's noise and the reason of a
# failure on stderr.
set -eu
usage='usage: package/sync-action.sh NAME VERSION DIR [--push]'
action=${1:?$usage}
version=${2:?$usage}
dir=${3:?$usage}
push=0
case "${4:-}" in --push) push=1 ;; "") ;; *) echo "$usage" >&2; exit 2 ;; esac
here=$(pwd -P)
src=$here/actions/$action
remote=${ACTION_REMOTE:-https://github.com/nicolaguglielmi/$action.git}
tag=v$version

[ -f "$src/action.yml" ] && [ -f "$src/README.md" ] && [ -f "$here/LICENSE" ] \
  || { echo "sync-action: $src/action.yml, its README.md or LICENSE is missing (run from the lights-out root)" >&2; exit 1; }
awk -v want="nicolaguglielmi/lights-out@$tag" '$1 == "-" && $2 == "uses:" && $3 == want { found = 1 } $1 == "uses:" && $2 == want { found = 1 } END { exit !found }' "$src/action.yml" \
  || { echo "sync-action: $src/action.yml does not use nicolaguglielmi/lights-out@$tag" >&2; exit 1 # the shim is not at this version
  }
if [ "$push" = 1 ] && [ -z "${ACTION_REPOS_TOKEN:-}" ]; then
  case "$remote" in https://*) echo "sync-action: --push to $remote needs ACTION_REPOS_TOKEN (docs/launch/checklist.md, Release automation)" >&2; exit 1 # no token
    ;; esac
fi
if [ -n "${ACTION_REPOS_TOKEN:-}" ]; then
  # git reads these as `-c http.https://github.com/.extraheader=...`, without them appearing in ps or .git/config.
  GIT_CONFIG_COUNT=1
  GIT_CONFIG_KEY_0=http.https://github.com/.extraheader
  GIT_CONFIG_VALUE_0="AUTHORIZATION: basic $(printf 'x-access-token:%s' "$ACTION_REPOS_TOKEN" | base64 | tr -d '\n')"
  export GIT_CONFIG_COUNT GIT_CONFIG_KEY_0 GIT_CONFIG_VALUE_0
fi

git clone -q "$remote" "$dir" >&2
branch=$(git -C "$dir" symbolic-ref --short HEAD)
cp "$src/action.yml" "$src/README.md" "$dir/"
cp "$here/LICENSE" "$dir/"

# same REF: REF in the clone holds the three files exactly as copied.
same() {
  for f in action.yml README.md LICENSE; do
    git -C "$dir" show "$1:$f" 2>/dev/null | cmp -s - "$dir/$f" || return 1
  done
}
if git -C "$dir" rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
  if same "$tag"; then
    echo "$action: $tag already holds these files; nothing to push"
    exit 0
  fi
  echo "sync-action: $remote has $tag holding other files; a published tag never moves" >&2
  exit 1 # the tag holds other files
fi

src_sha=$(git -C "$here" rev-parse --short HEAD 2>/dev/null || echo unknown)
git -C "$dir" add action.yml README.md LICENSE
if git -C "$dir" diff --cached --quiet; then
  echo "$action: $branch already holds these files; tagging it"
else
  # the owner's noreply identity, author and committer, as the 0.3.x copies; the environment cannot override it
  email=45848139+nicolaguglielmi@users.noreply.github.com
  GIT_AUTHOR_NAME=Nicola GIT_AUTHOR_EMAIL=$email GIT_COMMITTER_NAME=Nicola GIT_COMMITTER_EMAIL=$email git -C "$dir" \
    commit -q -m "$action at lights-out $tag: the Action and its README, copied from actions/$action in nicolaguglielmi/lights-out at $src_sha"
fi
git -C "$dir" tag "$tag"
echo "$action: $(git -C "$dir" log -1 --format='%h %s' "$tag")"
git -C "$dir" show --stat --format= "$tag"

if [ "$push" = 1 ]; then
  git -C "$dir" push -q origin "HEAD:refs/heads/$branch" "refs/tags/$tag" >&2
  echo "$action: pushed $branch and $tag to $remote"
else
  echo "$action: dry run, nothing pushed; with --push: git push origin HEAD:refs/heads/$branch refs/tags/$tag"
fi

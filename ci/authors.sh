#!/bin/sh
# ci-authors: every commit reachable from HEAD is attributed to the account
# that made it (docs/adr/0074 §5's 2026-11-12 amendment: the history was
# rewritten once for this, and this check keeps it so). GitHub attributes a
# commit by email (author, committer and Co-authored-by trailers), so:
#   - no author, committer or Co-authored-by/Signed-off-by address is
#     noreply@anthropic.com: the tools that write this repository are not
#     its contributors (the owner's rule);
#   - no address at users.noreply.github.com lacks its account id
#     (<id>+<login>@): a bare <login>@ is the old form, and it names
#     whichever account owns that login today. One such commit credited a
#     stranger's account.
# Anyone else may contribute under their own address. Then the check runs
# itself on a planted history and must refuse each case.
set -eu
name=authors
. ci/lib.sh

command -v git >/dev/null 2>&1 || nogo "git is not installed"
git rev-parse -q --verify HEAD >/dev/null 2>&1 || nogo "no HEAD: run it in a clone"
[ "$(git rev-parse --is-shallow-repository)" = false ] || nogo "a shallow clone: fetch the whole history (fetch-depth: 0)"

# scan DIR: one line per misattributed commit
scan() {
  git -C "$1" log --format='%x01%H%x09%ae%x09%ce%n%B' HEAD | awk '
    function bad(e,   l) {
      e = tolower(e)
      if (e == "noreply@anthropic.com") return "an Anthropic address"
      if (e ~ /@users\.noreply\.github\.com$/) {
        l = e; sub(/@.*/, "", l)
        if (l !~ /^[0-9]+\+/) return "a noreply address with no account id"
      }
      return ""
    }
    /^\001/ {
      split(substr($0, 2), f, "\t"); c = substr(f[1], 1, 7)
      r = bad(f[2]); if (r != "") print c ": author " f[2] ", " r
      r = bad(f[3]); if (r != "") print c ": committer " f[3] ", " r
      next
    }
    tolower($0) ~ /^(co-authored-by|signed-off-by):/ {
      e = $0; sub(/^[^<]*</, "", e); sub(/>.*$/, "", e)
      r = bad(e); if (r != "") print c ": trailer \"" $0 "\", " r
    }'
}

found=$(scan .)
[ -z "$found" ] || nogo "$(printf '%s\n' "$found" | awk 'END{print NR}') misattribution(s) in HEAD's history, first: $(printf '%s\n' "$found" | sed -n 1p)" "$found"

# The check on a planted history: each bad case refused, each good one not.
t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT
GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL GIT_CONFIG_NOSYSTEM
plant() {  # CASE AUTHOR-EMAIL COMMITTER-EMAIL [MESSAGE]
  d=$t/$1
  git init -q "$d"
  GIT_AUTHOR_NAME=a GIT_AUTHOR_EMAIL=$2 GIT_COMMITTER_NAME=c GIT_COMMITTER_EMAIL=$3 \
    git -C "$d" commit -q --allow-empty -m "${4:-x}"
}
own=45848139+nicolaguglielmi@users.noreply.github.com
plant ok-own "$own" "$own" "$(printf 'x\n\nSigned-off-by: N <%s>' "$own")"
plant ok-stranger dev@example.org noreply@github.com
plant ok-bot '49699333+dependabot[bot]@users.noreply.github.com' noreply@github.com
plant bad-author noreply@anthropic.com "$own"
plant bad-committer "$own" Noreply@Anthropic.com
plant bad-coauthor "$own" "$own" "$(printf 'x\n\nCo-Authored-By: Claude <noreply@anthropic.com>')"
plant bad-signoff "$own" "$own" "$(printf 'x\n\nSigned-off-by: Claude <noreply@anthropic.com>')"
plant bad-bare-login nicola@users.noreply.github.com "$own"
plant bad-bare-coauthor "$own" "$own" "$(printf 'x\n\nCo-authored-by: N <nicola@users.noreply.github.com>')"
for c in ok-own ok-stranger ok-bot; do
  [ -z "$(scan "$t/$c")" ] || nogo "the planted case $c was refused: $(scan "$t/$c")"
done
for c in bad-author bad-committer bad-coauthor bad-signoff bad-bare-login bad-bare-coauthor; do
  [ -n "$(scan "$t/$c")" ] || nogo "the planted case $c was accepted"
done
go_with "$(git rev-list --count HEAD) commits, each attributed to its own account"

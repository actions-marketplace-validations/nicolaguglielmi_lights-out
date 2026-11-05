#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-secrets: no committed or uncommitted secret. Full git history plus the
# working tree, so a staged-but-not-committed leak also fails the gate.
# No allowlist file at M0 (docs/adr/0002-self-ci-is-make-ci.md) ends at M8
# (docs/adr/0025 Consequences, "Amended 2026-09-20, owner ruling"): the
# working tree carries the local cosign key ./go up generates at
# .crew/cosign.key, which gitleaks' own private-key rule matches. The
# allowlist that excuses it lives at ci/gitleaks-worktree.toml — not
# .gitleaks.toml, not at the repo root, so gitleaks never loads it by
# itself — and is wired below into the working-tree scan only; the history
# scan below keeps running with no config, so nothing ever committed can be
# allowlisted, only a file gitleaks sees live and uncommitted.
#
# Before either scan: the one path the allowlist can match must be
# git-ignored and must not be tracked or staged, checked here (not inside a
# gate of its own) so the gate that carries the exception is the gate that
# proves it inert. `git check-ignore` matches the pattern, not the file, so
# this holds even before the first `./go up` has created the key.
#
# Tracked-or-staged is checked first, deliberately: once a path is in the
# index (staged, or `git add -f`'d past .gitignore), `git check-ignore`
# reports it as *not* ignored — the pattern text is still in .gitignore, but
# git no longer applies it to a path it already tracks (confirmed live
# 2026-09-20 on the git pinned into the workbench). Checking ls-files first
# means that case is named for what it is ("tracked", fix: unstage it) and
# check-ignore's answer is only trusted for a path that is still untracked,
# which is the one case it actually describes.
set -eu
name=secrets
. ci/lib.sh

# As a PR gate on an attached repository's range (docs/adr/0037 §3, amended
# by docs/adr/0042 §4 and docs/adr/0049 §4): that repository's whole
# history, as reachable from HEAD, is scanned with the platform's config
# (ci/gitleaks-attached.toml: the default rules, no allowlist, and never
# the repository's own .gitleaks.toml, which a PR could write) and inline
# `gitleaks:allow` comments ignored. A key in history is live until it is
# rotated, so the history gates, not just the range. A finding a human has
# excused stays excused only by fingerprint, in gitleaks' own
# .gitleaksignore format, read from the BASE commit's
# .lights-out/.gitleaksignore and never from HEAD: a change cannot excuse
# its own finding. gitleaks also loads a .gitleaksignore from the root of
# the directory it scans (cmd/root.go, 8.30.1), so it scans the git
# directory, which has no working tree and so no HEAD copy of the file.
# Each excused finding is still reported on stderr. Not the working tree:
# the clone is HEAD plus what lights-out put there (the init draft, a
# venv, node_modules), and every line at HEAD is in the commit that added
# it. The exemptions below are this checkout's local files.
if [ -n "${WORKLOAD_ATTACHED:-}" ] && [ -n "${BASE:-}" ] && [ -n "${HEAD:-}" ]; then
  require_range
  scan_tmp=$(mktemp -d)
  trap 'rm -rf "$scan_tmp"' EXIT
  mkdir "$scan_tmp/none" "$scan_tmp/base"
  if [ "$(git -C "$WORKLOAD" cat-file -t "$base")" = commit ] \
     && git -C "$WORKLOAD" cat-file -e "$base:./.lights-out/.gitleaksignore" 2>/dev/null; then
    git -C "$WORKLOAD" show "$base:./.lights-out/.gitleaksignore" > "$scan_tmp/base/.gitleaksignore"
  fi
  git_dir=$(git -C "$WORKLOAD" rev-parse --absolute-git-dir) || nogo "$WORKLOAD is not a git repository"
  # scan <.gitleaksignore dir> <report>: gitleaks' exit code.
  scan() {
    gitleaks git -c ci/gitleaks-attached.toml --ignore-gitleaks-allow -i "$1" --log-opts="$head" \
      --no-banner --no-color --redact --report-format json --report-path "$2" "$git_dir" >&2
  }
  rc=0
  scan "$scan_tmp/base" "$scan_tmp/judged.json" || rc=$?
  if [ -s "$scan_tmp/base/.gitleaksignore" ]; then
    scan "$scan_tmp/none" "$scan_tmp/all.json" || :
    jq -r --slurpfile judged "$scan_tmp/judged.json" \
      '[$judged[0][].Fingerprint] as $kept | .[] | .Fingerprint | select(. as $f | $kept | index($f) | not)' \
      "$scan_tmp/all.json" | while IFS= read -r fp; do
        printf '%s: %s excused by base %s (.lights-out/.gitleaksignore)\n' "$name" "$fp" "$(printf '%s' "$base" | cut -c1-7)" >&2
      done
  fi
  [ "$rc" -eq 0 ] \
    || nogo "gitleaks found a secret in the attached repository's history that the base's .lights-out/.gitleaksignore does not excuse"
  go
fi

# Four allowlisted local paths (ci/gitleaks-worktree.toml): the cosign key
# ./go up generates; the GEMINI_API_KEY line of .env, where .env.example
# tells the user to put their key (amended 2026-11-02: that line made
# ./go demo NO-GO for anyone who followed the example); and .attached/,
# the clone of a user's repository (docs/adr/0037 §3), whose content its
# own range gate scans above, not this checkout's self-check; and
# .crew/cache, the uv and npm caches the workbench toolchain form keeps
# (docs/adr/0042 §2), third-party sources whose test fixtures look like
# keys. Four paths, then.
for exempt in .crew/cosign.key .env .attached .crew/cache; do
  if git ls-files --error-unmatch -- "$exempt" >/dev/null 2>&1; then
    nogo "$exempt is tracked or staged; a real secret must never be committed — fix .gitignore and unstage it (git rm --cached)"
  fi
  if git check-ignore -q -- "$exempt"; then
    :
  else
    nogo ".gitignore does not ignore $exempt; fix .gitignore before ci/gitleaks-worktree.toml's allowlist can be trusted"
  fi
done

# The history judged is HEAD's: the commits that reach this checkout's
# tree. gitleaks' default log is `--all`, and a CI checkout with full depth
# fetches every branch, so another branch's commit (a work-in-progress
# session, 2026-11-04) turned this check red on unrelated pushes.
if git rev-parse HEAD >/dev/null 2>&1; then
  gitleaks git --log-opts=HEAD --no-banner --no-color --redact . >&2 || nogo "gitleaks found a secret in git history"
else
  printf '%s: empty repository, no commits yet; scanning the working tree only\n' "$name" >&2
fi

gitleaks dir -c ci/gitleaks-worktree.toml --no-banner --no-color --redact . >&2 \
  || nogo "gitleaks found a secret in the working tree"

go

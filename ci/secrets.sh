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

if git ls-files --error-unmatch -- .crew/cosign.key >/dev/null 2>&1; then
  nogo ".crew/cosign.key is tracked or staged; a real key must never be committed — fix .gitignore and unstage it (git rm --cached)"
fi
if git check-ignore -q -- .crew/cosign.key; then
  :
else
  nogo ".gitignore does not ignore .crew/cosign.key; fix .gitignore before ci/gitleaks-worktree.toml's allowlist can be trusted"
fi

if git rev-parse HEAD >/dev/null 2>&1; then
  gitleaks git --no-banner --no-color --redact . >&2 || nogo "gitleaks found a secret in git history"
else
  printf '%s: empty repository, no commits yet; scanning the working tree only\n' "$name" >&2
fi

gitleaks dir -c ci/gitleaks-worktree.toml --no-banner --no-color --redact . >&2 \
  || nogo "gitleaks found a secret in the working tree"

go

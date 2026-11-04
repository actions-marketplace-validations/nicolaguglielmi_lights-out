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
# by docs/adr/0042 §4): that repository's history is scanned, with the
# platform's config (ci/gitleaks-attached.toml: the default rules, no
# allowlist, and never the repository's own .gitleaks.toml, which a PR
# could write) and inline `gitleaks:allow` comments ignored. Not its
# working tree: the clone is HEAD plus what lights-out put there (the init
# draft, a venv, node_modules), and every line at HEAD is in the commit
# that added it. The exemptions below are this checkout's local files.
if [ -n "${WORKLOAD_ATTACHED:-}" ] && [ -n "${BASE:-}" ] && [ -n "${HEAD:-}" ]; then
  gitleaks git -c ci/gitleaks-attached.toml --ignore-gitleaks-allow \
      --no-banner --no-color --redact "$WORKLOAD" >&2 \
    || nogo "gitleaks found a secret in the attached repository's history"
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

if git rev-parse HEAD >/dev/null 2>&1; then
  gitleaks git --no-banner --no-color --redact . >&2 || nogo "gitleaks found a secret in git history"
else
  printf '%s: empty repository, no commits yet; scanning the working tree only\n' "$name" >&2
fi

gitleaks dir -c ci/gitleaks-worktree.toml --no-banner --no-color --redact . >&2 \
  || nogo "gitleaks found a secret in the working tree"

go

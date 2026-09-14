#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-secrets: no committed or uncommitted secret. Full git history plus the
# working tree, so a staged-but-not-committed leak also fails the gate.
# No allowlist file at M0 (docs/adr/0002-self-ci-is-make-ci.md).
set -eu
name=secrets

if git rev-parse HEAD >/dev/null 2>&1; then
  if ! gitleaks git --no-banner --redact .; then
    printf 'NO-GO: %s: gitleaks found a secret in git history\n' "$name" >&2
    exit 1
  fi
else
  printf '%s: empty repository, no commits yet; scanning the working tree only\n' "$name"
fi

if ! gitleaks dir --no-banner --redact .; then
  printf 'NO-GO: %s: gitleaks found a secret in the working tree\n' "$name" >&2
  exit 1
fi

printf 'GO: %s\n' "$name"

#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-secrets: no committed or uncommitted secret. Full git history plus the
# working tree, so a staged-but-not-committed leak also fails the gate.
# No allowlist file at M0 (docs/adr/0002-self-ci-is-make-ci.md).
set -eu
name=secrets
. ci/lib.sh

if git rev-parse HEAD >/dev/null 2>&1; then
  gitleaks git --no-banner --no-color --redact . >&2 || nogo "gitleaks found a secret in git history"
else
  printf '%s: empty repository, no commits yet; scanning the working tree only\n' "$name" >&2
fi

gitleaks dir --no-banner --no-color --redact . >&2 || nogo "gitleaks found a secret in the working tree"

go

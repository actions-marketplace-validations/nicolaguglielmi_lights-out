#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# core-history-findings (docs/adr/0049 §4): what the secrets gate will find
# in an attached repository's history, listed by `./go init` on stderr
# with each finding's fingerprint, the same scan as ci/secrets.sh's
# attached branch with nothing excused. It never writes an ignore file:
# whether a finding is a false positive, and goes into
# the contract's .gitleaksignore, or a key to rotate, is a human's call.
# Nothing on stdout; exit 0 unless gitleaks itself cannot run.
set -eu

: "${WORKLOAD:?WORKLOAD not set; run this via ./go, not directly}"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
git_dir=$(git -C "$WORKLOAD" rev-parse --absolute-git-dir)

rc=0
gitleaks git -c ci/gitleaks-attached.toml --ignore-gitleaks-allow -i "$tmp" --log-opts=HEAD \
  --no-banner --no-color --redact --report-format json --report-path "$tmp/found.json" "$git_dir" \
  >/dev/null 2>"$tmp/log" || rc=$?
case "$rc" in
  0) printf 'init: no secret in the history; the secrets gate starts clean\n' >&2 ;;
  1)
    jq -r '.[] | "init: history finding \(.Fingerprint) (\(.Description))"' "$tmp/found.json" >&2
    printf 'init: %s finding(s) in the history, and the secrets gate is NO-GO on each: rotate a real key; a false positive is excused by its fingerprint, committed in .gitleaksignore in the contract directory, which init never drafts\n' \
      "$(jq length "$tmp/found.json")" >&2 ;;
  *) cat "$tmp/log" >&2; exit "$rc" ;;
esac

#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-secrets-history: the secrets gate on an attached repository's history
# (docs/adr/0049 §4), written from the owner's spec of 2026-11-05, on a
# throwaway repository, gitleaks for real:
#   (a) a new leak in the range is NO-GO;
#   (b) a finding excused only at HEAD, in .lights-out/.gitleaksignore or a
#       root .gitleaksignore, is still NO-GO;
#   (c) a finding excused at the base is GO, with one stderr line saying
#       "excused by base";
#   (d) init lists a history finding on stderr and drafts no ignore file.
# The fake key is assembled at run time, so this file holds none.
set -eu
name=secrets-history
. ci/lib.sh

t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT
r="$t/repo"
export GIT_AUTHOR_NAME=ci GIT_AUTHOR_EMAIL=ci@localhost GIT_COMMITTER_NAME=ci GIT_COMMITTER_EMAIL=ci@localhost
commit() { git -C "$r" add -A && git -C "$r" -c commit.gpgsign=false commit -q -m "$1" && git -C "$r" rev-parse HEAD; }

mismatch=""
fail_case() {
  [ -z "$mismatch" ] || return 0
  mismatch="$1"; printf 'ci-secrets-history: %s: %s\n' "$1" "$2" >&2
}

# gate BASE HEAD: the attached secrets gate's line on stdout, its stderr in $t/err.
gate() {
  WORKLOAD_ATTACHED=1 WORKLOAD="$r" BASE="$1" HEAD="$2" sh ci/secrets.sh 2>"$t/err" || :
}

mkdir -p "$r"
git -C "$r" init -q -b main
printf 'print("hello")\n' > "$r/app.py"
c1=$(commit "clean")

body=$(printf 'MIIEowIBAAKCAQEA%.0s' 1 2 3 4 5 6)
{ printf -- '-----BEGIN RSA %s-----\n' "PRIVATE KEY"; printf '%s\n' "$body" "$body"; printf -- '-----END RSA %s-----\n' "PRIVATE KEY"; } > "$r/id_rsa"
c2=$(commit "a leaked key")

line=$(gate "$c1" "$c2")
case "$line" in "NO-GO: secrets — "*) ;; *) fail_case a-new-leak "a new leak in the range gave '$line', want NO-GO" ;; esac

gitleaks git -c ci/gitleaks-attached.toml --ignore-gitleaks-allow -i "$t" --log-opts="$c2" --no-banner --no-color \
  --redact --report-format json --report-path "$t/found.json" "$r/.git" >/dev/null 2>&1 || :
fp=$(jq -r '.[0].Fingerprint // empty' "$t/found.json")
[ -n "$fp" ] || fail_case a-fingerprint "gitleaks found nothing to fingerprint in the fake key"

mkdir -p "$r/.lights-out"
printf '%s\n' "$fp" > "$r/.lights-out/.gitleaksignore"
printf '%s\n' "$fp" > "$r/.gitleaksignore"
c3=$(commit "excuse it, at HEAD only")
line=$(gate "$c2" "$c3")
case "$line" in "NO-GO: secrets — "*) ;; *) fail_case b-head-only "a finding excused only at HEAD gave '$line', want NO-GO" ;; esac

printf 'print("bye")\n' >> "$r/app.py"
c4=$(commit "a clean change on a base that excuses it")
line=$(gate "$c3" "$c4")
[ "$line" = "GO: secrets" ] || fail_case c-base "a finding excused at the base gave '$line', want GO: secrets"
grep -q "^secrets: $fp excused by base " "$t/err" || fail_case c-stderr "no 'excused by base' line on stderr for $fp"

# (d) init's listing, through the same helper core/init.sh calls; the
# draft directory gets no ignore file.
mkdir -p "$t/draft"
WORKLOAD="$r" WORKLOAD_CONTRACT="$t/draft" sh core/history-findings.sh 2>"$t/err" >/dev/null || :
grep -q "$fp" "$t/err" || fail_case d-init-lists "core/history-findings.sh did not list $fp on stderr"
[ ! -e "$t/draft/.gitleaksignore" ] || fail_case d-init-drafts "an ignore file was drafted"

[ -z "$mismatch" ] || nogo "case $mismatch disagrees with docs/adr/0049 §4"
go

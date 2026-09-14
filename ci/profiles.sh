#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-profiles: every profiles/*.env is only comments, blank lines or
# KEY=value with KEY in [A-Z][A-Z0-9_]* and a value with no quotes, spaces
# or `$`; all profiles define the same key set as profiles/l0.env.
set -eu
name=profiles

ref=profiles/l0.env
if [ ! -f "$ref" ]; then
  printf 'NO-GO: %s: %s not found\n' "$name" "$ref" >&2
  exit 1
fi

bad=""
for f in profiles/*.env; do
  [ -e "$f" ] || continue
  ln=0
  while IFS= read -r line || [ -n "$line" ]; do
    ln=$((ln + 1))
    case "$line" in
      '') continue ;;
      \#*) continue ;;
    esac
    printf '%s' "$line" | grep -Eq '^[A-Z][A-Z0-9_]*=[^"'\''$ ]*$' || bad="$bad $f:$ln"
  done < "$f"
done

if [ -n "$bad" ]; then
  printf 'NO-GO: %s: malformed line(s):%s\n' "$name" "$bad" >&2
  exit 1
fi

keys_of() {
  grep -E '^[A-Z][A-Z0-9_]*=' "$1" | cut -d= -f1 | sort -u
}

ref_keys=$(keys_of "$ref")

for f in profiles/*.env; do
  [ -e "$f" ] || continue
  [ "$f" = "$ref" ] && continue
  f_keys=$(keys_of "$f")
  if [ "$f_keys" != "$ref_keys" ]; then
    printf 'NO-GO: %s: %s defines a different key set than %s\n' "$name" "$f" "$ref" >&2
    exit 1
  fi
done

printf 'GO: %s\n' "$name"

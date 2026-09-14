#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# fetch URL SHA256 DEST: download DEST from URL and fail unless it matches SHA256.
set -eu
url=$1; want=$2; dest=$3
curl -fsSL --retry 3 -o "$dest" "$url"
got=$(sha256sum "$dest" | cut -d' ' -f1)
if [ "$got" != "$want" ]; then
  printf 'fetch: checksum mismatch for %s\n  want %s\n  got  %s\n' "$url" "$want" "$got" >&2
  rm -f "$dest"
  exit 1
fi

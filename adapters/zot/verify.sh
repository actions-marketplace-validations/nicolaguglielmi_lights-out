#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# verify-zot: verifies the cosign signature on <tag> and prints the
# immutable reference it verified (<repo>@sha256:…) on stdout — the
# digest the caller must deploy, never the mutable tag (docs/adr/0025
# §1, §6). --allow-http-registry and --insecure-ignore-tlog are the
# verify-side twins of publish.sh's signing flags: without them, a
# passwordless local signature with no transparency-log entry does not
# verify (docs/adr/0025 §2). Not a gate (docs/adr/0012 §6): silent on
# success beyond the one stdout line, one stderr line and exit 1 on
# failure — cosign's own reason is printed first.
set -eu
tag=${1:?usage: verify.sh <tag>}
: "${PLANE_HOST:=host.containers.internal}"
: "${COSIGN_KEY:=.crew/cosign.pub}"
repo=lights-out-backend
ref="$PLANE_HOST:5050/$repo:$tag"

[ -f "$COSIGN_KEY" ] || { printf 'verify-zot: %s not found; ./go up generates it\n' "$COSIGN_KEY" >&2; exit 1; }

cosign verify --key "$COSIGN_KEY" --insecure-ignore-tlog --allow-http-registry "$ref" >&2 \
  || { printf 'verify-zot: %s does not verify\n' "$ref" >&2; exit 1; }

digest=$(curl -fsSI --connect-timeout 1 --max-time 5 \
    -H 'Accept: application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json' \
    "http://$PLANE_HOST:5050/v2/$repo/manifests/$tag" \
  | tr -d '\r' | awk -F': ' 'tolower($1) == "docker-content-digest" { print $2 }')
[ -n "$digest" ] || { printf 'verify-zot: could not read the digest of %s:%s from the manifest\n' "$repo" "$tag" >&2; exit 1; }

printf '%s@%s\n' "$repo" "$digest"

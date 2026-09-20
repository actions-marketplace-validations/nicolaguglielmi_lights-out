#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# publish-zot: builds the `backend` image at TAG (the current checkout),
# pushes it and signs it with the local cosign key (docs/adr/0025 §1-§2).
# Build and push run through docker-compose (the engine daemon's own view
# of "localhost", not workbench's — compose.yaml's image: field is
# registry-qualified as localhost:5050/…); the sign runs through cosign, a
# workbench-side HTTP client that reaches the same Zot over PLANE_HOST
# instead. The build is not redundant with ./go up's own: that one tags
# APP_TAG at whatever HEAD was current then; the Gitea Actions job calling
# this checks out the merge commit fresh and has never built it — cached
# and near-instant when the layers already exist (./go up's own call),
# real work when they do not (found running this job for real, not
# assumed: "image not known" is what docker-compose push says when
# nothing built the tag first). --allow-http-registry and --tlog-
# upload=false are what let a local, unauthenticated, plain-HTTP registry
# work with no account and no network beyond it (docs/adr/0025 §2). Not a
# gate (docs/adr/0012 §6): one stderr line and exit 1 on failure. Prints
# the immutable reference (<repo>@sha256:…) on stdout, the one line a
# caller may capture.
set -eu
tag=${1:?usage: publish.sh <tag>}
: "${PLANE_HOST:=host.containers.internal}"
: "${COSIGN_KEY:=.crew/cosign.key}"
repo=lights-out-backend

[ -f "$COSIGN_KEY" ] || { printf 'publish-zot: %s not found; ./go up generates it\n' "$COSIGN_KEY" >&2; exit 1; }

APP_TAG="$tag" docker-compose build backend >&2 \
  || { printf 'publish-zot: build %s:%s failed\n' "$repo" "$tag" >&2; exit 1; }
APP_TAG="$tag" docker-compose push backend >&2 \
  || { printf 'publish-zot: push %s:%s failed\n' "$repo" "$tag" >&2; exit 1; }

digest=$(curl -fsSI --connect-timeout 1 --max-time 5 \
    -H 'Accept: application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json' \
    "http://$PLANE_HOST:5050/v2/$repo/manifests/$tag" \
  | tr -d '\r' | awk -F': ' 'tolower($1) == "docker-content-digest" { print $2 }')
[ -n "$digest" ] || { printf 'publish-zot: could not read the digest of %s:%s from the manifest\n' "$repo" "$tag" >&2; exit 1; }

# --use-signing-config=false: cosign 3.1.3 defaults to a TUF-provided
# signing config (a newer feature than ADR 0025 §2's research), and
# --tlog-upload=false alone conflicts with it ("not supported with
# --signing-config or --use-signing-config" — verified live 2026-09-20,
# the ADR's flag pair was necessary but no longer sufficient). Explicitly
# false reverts to the plain behaviour --tlog-upload=false expects.
# shellcheck disable=SC1007 # deliberately empty: cosign's passwordless-key convention
COSIGN_PASSWORD= cosign sign --key "$COSIGN_KEY" --tlog-upload=false --use-signing-config=false --allow-http-registry --yes \
    "$PLANE_HOST:5050/$repo@$digest" >&2 \
  || { printf 'publish-zot: sign %s@%s failed\n' "$repo" "$digest" >&2; exit 1; }

printf '%s@%s\n' "$repo" "$digest"

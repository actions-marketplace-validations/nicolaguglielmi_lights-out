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
#
# Before the signature, the SBOM (docs/adr/0072 §2): the image saved to an
# archive through the engine's API socket (the workbench has no engine
# CLI; GET /images/<name>/get is the Docker API both engines serve), one
# SPDX 2.3 document from it by the pinned osv-scanner (exit 1 only means
# advisories were found), attested with the same key and flags as the
# signature, then read back with cosign verify-attestation. Any of these
# failing fails publish before the image is signed, so no signed image
# without an SBOM reaches the registry.
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

# The SBOM, before the signature (docs/adr/0072 §2).
sock=${DOCKER_HOST:-}
sock=${sock#unix://}
[ -S "$sock" ] || { printf 'publish-zot: no engine socket at %s to save %s:%s for its SBOM\n' "${sock:-(DOCKER_HOST unset)}" "$repo" "$tag" >&2; exit 1; }
sbom_t0=$(date +%s)
sbom_dir=$(mktemp -d)
trap 'rm -rf "$sbom_dir"' EXIT
curl -fsS --unix-socket "$sock" -o "$sbom_dir/image.tar" \
    "http://engine/images/$(printf 'localhost:5050/%s:%s' "$repo" "$tag" | sed 's|/|%2F|g')/get" \
  || { printf 'publish-zot: could not save %s:%s from the engine for its SBOM\n' "$repo" "$tag" >&2; exit 1; }
osv-scanner scan image --archive "$sbom_dir/image.tar" --format spdx-2-3 --all-packages \
    --output-file "$sbom_dir/sbom.spdx.json" >/dev/null 2>"$sbom_dir/osv.err" && rc=0 || rc=$?
case "$rc" in
  0|1) : ;;
  *) cat "$sbom_dir/osv.err" >&2; printf 'publish-zot: osv-scanner exited %s on %s:%s; no SBOM\n' "$rc" "$repo" "$tag" >&2; exit 1 ;;
esac
# shellcheck disable=SC1007 # deliberately empty: cosign's passwordless-key convention
COSIGN_PASSWORD= cosign attest --key "$COSIGN_KEY" --type spdxjson --predicate "$sbom_dir/sbom.spdx.json" \
    --tlog-upload=false --use-signing-config=false --allow-http-registry --yes "$PLANE_HOST:5050/$repo@$digest" >&2 \
  || { printf 'publish-zot: attest the SBOM of %s@%s failed\n' "$repo" "$digest" >&2; exit 1; }
cosign verify-attestation --key "${COSIGN_KEY%.key}.pub" --type spdxjson --insecure-ignore-tlog --allow-http-registry \
    "$PLANE_HOST:5050/$repo@$digest" >/dev/null 2>"$sbom_dir/va.err" \
  || { cat "$sbom_dir/va.err" >&2; printf 'publish-zot: the SBOM attestation of %s@%s does not verify\n' "$repo" "$digest" >&2; exit 1; }
printf 'publish-zot: SBOM of %s@%s: %s package(s), attested and verified in %ss\n' "$repo" "$digest" \
  "$(jq '.packages | length' "$sbom_dir/sbom.spdx.json")" "$(($(date +%s) - sbom_t0))" >&2

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

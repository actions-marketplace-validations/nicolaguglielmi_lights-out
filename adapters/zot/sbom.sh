#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# sbom-zot: prints the digest of the SPDX attestation publish.sh attached
# to <repo>@sha256:… (docs/adr/0072 §2), the newest when there are several,
# read from Zot's OCI referrers API: the sigstore bundle whose predicate
# type is https://spdx.dev/Document. An optional Registry verb: the release
# record's `sbom` (core/launchpad.sh), never a verdict, so no gate reads it
# and a Registry adapter without it records none. Exit 1 and one stderr
# line when the image has no such attestation.
set -eu
ref=${1:?usage: sbom.sh <repo>@sha256:...}
: "${PLANE_HOST:=host.containers.internal}"
repo=${ref%@*}
digest=${ref#*@}

got=$(curl -fsS --connect-timeout 1 --max-time 5 "http://$PLANE_HOST:5050/v2/$repo/referrers/$digest" \
  | jq -r '[.manifests[]? | select(.annotations["dev.sigstore.bundle.predicateType"] == "https://spdx.dev/Document")]
           | sort_by(.annotations["org.opencontainers.image.created"] // "") | last | .digest // empty') || got=""
[ -n "$got" ] || { printf 'sbom-zot: %s has no SPDX attestation\n' "$ref" >&2; exit 1; }
printf '%s\n' "$got"

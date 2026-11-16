#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# install-argo-rollouts: the controller cluster.sh puts on the local node
# (docs/adr/0051 §4, moved here by docs/adr/0095 §5). Not a Delivery verb:
# a team that already runs Argo Rollouts never calls it. KUBECONFIG is the
# node's, set by cluster.sh.
set -eu
: "${READY_TIMEOUT:=60}"
# The latest stable Argo Rollouts on 2026-11-06; install.yaml is not in
# the release's checksums file, so its sha256 is the one measured that
# day, and the manifest pins the controller image to the same tag.
ARGO_ROLLOUTS_VERSION=v1.10.2
ARGO_INSTALL_SHA256=b8280994791eaee7eb91c8b84450efcc6e0292fca5aafc18c1b0ebc5d18dbefe

printf 'cluster-argo-rollouts: installing Argo Rollouts %s\n' "$ARGO_ROLLOUTS_VERSION" >&2
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
curl -fsSL "https://github.com/argoproj/argo-rollouts/releases/download/$ARGO_ROLLOUTS_VERSION/install.yaml" -o "$tmp"
got=$(sha256sum "$tmp" | cut -d' ' -f1)
[ "$got" = "$ARGO_INSTALL_SHA256" ] || {
  printf 'install-argo-rollouts: install.yaml %s has sha256 %s, want %s\n' "$ARGO_ROLLOUTS_VERSION" "$got" "$ARGO_INSTALL_SHA256" >&2
  exit 1
}
kubectl create namespace argo-rollouts --dry-run=client -o yaml | kubectl apply -f - >&2
kubectl apply --server-side -n argo-rollouts -f "$tmp" >&2
kubectl -n argo-rollouts rollout status deployment/argo-rollouts --timeout="${READY_TIMEOUT}s" >&2

#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# install-flagger: the controller adapters/argo-rollouts/cluster.sh puts on
# the local node when CLUSTER_ADAPTER=adapters/flagger (docs/adr/0095 §5).
# Not a Delivery verb: a team that already runs Flagger never calls it.
# KUBECONFIG is the node's, set by cluster.sh.
#
# Flagger v1.45.0 (2026-09-01), the latest release on 2026-11-16
# (https://github.com/fluxcd/flagger/releases/tag/v1.45.0; the docs at
# docs.flagger.app, pages usage/webhooks and tutorials/traefik-progressive-
# delivery, read 2026-11-16; the URLs are in docs/adr/0095). The release's
# checksums cover its binaries only, so each file below is checked against
# the sha256 measured on 2026-11-16 at the tag:
#   - kustomize/base/flagger: the CRDs, RBAC, account and controller, into
#     flagger-system, the controller on the Traefik router k3s ships and on
#     the plane's Prometheus, bridged into the Canary's namespace;
#   - kustomize/tester: the loadtester 0.39.0, whose gate API holds the
#     Canary's webhooks, into the Canary's namespace.
# Applied with kubectl's built-in kustomize: no Helm in the workbench.
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/flagger/env.sh
. "$here/env.sh"
FLAGGER_VERSION=v1.45.0
raw=https://raw.githubusercontent.com/fluxcd/flagger/$FLAGGER_VERSION/kustomize

die() { printf 'install-flagger: %s\n' "$*" >&2; exit 1; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/base" "$tmp/tester"
# fetch PATH SHA256 DEST: one file of the tag, checked.
fetch() {
  curl -fsSL "$raw/$1" -o "$3" || die "could not download $1 at $FLAGGER_VERSION"
  got=$(sha256sum "$3" | cut -d' ' -f1)
  [ "$got" = "$2" ] || die "$1 at $FLAGGER_VERSION has sha256 $got, want $2"
}
fetch base/flagger/kustomization.yaml 0dffb950e31ddd095f5643a46a9d218308535f65ace1948e0c37448dabd843f7 "$tmp/base/kustomization.yaml"
fetch base/flagger/account.yaml 3271efb026036c641e9d714cf39359c4406ad2fe961cb63c53fa4b83dfc24c9c "$tmp/base/account.yaml"
fetch base/flagger/rbac.yaml 1ce196b2ec3af9cdad1a16ed32e2119fa8f2c8dc78685e60e619932b8836ae6b "$tmp/base/rbac.yaml"
fetch base/flagger/crd.yaml 58bd594b9e33deb0edceac81f6ed160b458a7933039fb295552724f656033ee5 "$tmp/base/crd.yaml"
fetch base/flagger/deployment.yaml c8c4c8a85010fbb09c5d39a4a13a16a67fd2c05406fd8ff43c4cf09794a8595b "$tmp/base/deployment.yaml"
fetch tester/deployment.yaml 373424c4b628dcdd26ac1ddf1a07b2711dc3b4222642d44ba0abe95a5dbc915b "$tmp/tester/deployment.yaml"
fetch tester/service.yaml 278919c9ad49fb11bb94fcfbb05f32b09f08f1f49a407006faac274606c946d0 "$tmp/tester/service.yaml"

# The base's ClusterRole at v1.45.0 grants nothing on traefik.io, which
# the Helm chart's does (charts/flagger/templates/rbac.yaml, the rule
# copied here): without it the Traefik router cannot read its
# TraefikService and the Canary never leaves Initializing (found on the
# first run, 2026-11-16).
cat > "$tmp/traefik-rbac.yaml" <<EOF
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: flagger-traefik
rules:
  - apiGroups: [traefik.io]
    resources: [traefikservices]
    verbs: [get, list, watch, create, update, patch, delete]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: flagger-traefik
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: flagger-traefik
subjects:
  - kind: ServiceAccount
    name: flagger
    namespace: flagger-system
EOF
# The base sets the image tag to 1.45.0 and the namespace; the flags are
# this adapter's: Traefik, and Prometheus by the name cluster.sh bridges.
cat > "$tmp/kustomization.yaml" <<EOF
resources:
  - base
  - traefik-rbac.yaml
patches:
  - target:
      kind: Deployment
      name: flagger
    patch: |
      - op: add
        path: /spec/template/spec/containers/0/args
        value:
          - -log-level=info
          - -mesh-provider=traefik
          - -metrics-server=http://prometheus.$FLAGGER_NAMESPACE:9090
EOF
printf 'install-flagger: installing Flagger %s and its loadtester\n' "$FLAGGER_VERSION" >&2
kubectl create namespace flagger-system --dry-run=client -o yaml | kubectl apply -f - >&2
kubectl apply --server-side -k "$tmp" >&2
kubectl -n flagger-system rollout status deployment/flagger --timeout="${READY_TIMEOUT}s" >&2

kubectl create namespace "$FLAGGER_NAMESPACE" --dry-run=client -o yaml | kubectl apply -f - >&2
k apply -f "$tmp/tester/service.yaml" -f "$tmp/tester/deployment.yaml" >&2
k rollout status "deployment/$FLAGGER_LOADTESTER" --timeout="${READY_TIMEOUT}s" >&2

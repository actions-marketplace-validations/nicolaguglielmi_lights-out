#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# cluster-argo-rollouts: the local cluster the adapter is proved on
# (docs/adr/0051 §4). Not a Delivery verb and not a gate: a team that
# already runs Argo Rollouts never calls it.
#
#   cluster.sh up <manifests-dir> <image>   k3s on the running plane, Argo
#       Rollouts installed, the workload's manifests applied with <image>
#       (a verified repo@digest) as the stable revision, its plane
#       dependencies bridged in, then ready.sh
#   cluster.sh down                          the node and its volumes gone
#
# A Service without a selector in the manifests is a plane service the
# workload depends on: it gets an EndpointSlice with the IP of the compose
# service of the same name, read from the engine API, because a pod
# cannot use the engine's resolver (docker's answers on 127.0.0.11 inside
# the node only). Writes the kubeconfig to .crew/argo/kubeconfig.
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/argo-rollouts/env.sh
. "$here/env.sh"
: "${PLANE_HOST:=host.containers.internal}"
: "${ARGO_API_PORT:=6443}"
: "${ARGO_REGISTRY_HOST:=localhost:5050}"
: "${COMPOSE_PROJECT_NAME:=lights-out}"
out=.crew/argo
export KUBECONFIG="$out/kubeconfig"
COMPOSE_FILE="${COMPOSE_FILE:-compose.yaml}:adapters/argo-rollouts/compose.yaml"
export COMPOSE_FILE

# The latest stable Argo Rollouts on 2026-11-06; install.yaml is not in
# the release's checksums file, so its sha256 is the one measured that
# day, and the manifest pins the controller image to the same tag.
ARGO_ROLLOUTS_VERSION=v1.10.2
ARGO_INSTALL_SHA256=b8280994791eaee7eb91c8b84450efcc6e0292fca5aafc18c1b0ebc5d18dbefe

die() { printf 'cluster-argo-rollouts: %s\n' "$*" >&2; exit 1; }

# wait_for SECONDS WHAT CMD...: run CMD each second until it succeeds.
wait_for() {
  n=$1; what=$2; shift 2
  i=0
  while [ "$i" -lt "$n" ]; do
    "$@" >/dev/null 2>&1 && return 0
    i=$((i + 1))
    sleep 1
  done
  die "$what not ready after ${n}s"
}

# compose_ip SERVICE: the IP of the plane's SERVICE on the plane's default
# network, through the engine API workbench already holds (./go).
compose_ip() {
  curl -fsS --unix-socket "${DOCKER_HOST#unix://}" -G http://engine/containers/json \
      --data-urlencode "filters={\"label\":[\"com.docker.compose.project=$COMPOSE_PROJECT_NAME\",\"com.docker.compose.service=$1\"]}" \
    | jq -er --arg n "${COMPOSE_PROJECT_NAME}_default" 'first | .NetworkSettings.Networks[$n].IPAddress | select(. != null and . != "")'
}

up() {
  manifests=${1:?usage: cluster.sh up <manifests-dir> <image>}
  image=${2:?usage: cluster.sh up <manifests-dir> <image>}
  [ -d "$manifests" ] || die "$manifests not found: the workload has no Kubernetes manifests (docs/adr/0051 §5)"

  mkdir -p "$out"
  rm -f "$out/kubeconfig.yaml" "$out/kubeconfig"
  docker-compose --profile argo up -d k8s >&2
  wait_for "$READY_TIMEOUT" "k3s kubeconfig" test -s "$out/kubeconfig.yaml"
  sed "s|https://127.0.0.1:6443|https://$PLANE_HOST:$ARGO_API_PORT|" "$out/kubeconfig.yaml" > "$out/kubeconfig"
  wait_for "$READY_TIMEOUT" "the k3s API server" kubectl get --raw /readyz
  wait_for "$READY_TIMEOUT" "the k3s node" kubectl wait --for=condition=Ready node --all --timeout=1s
  # k3s installs Traefik through a Helm job that may run twice, replacing
  # the Traefik pod on the way: a GET through the router in that window
  # fails (found 2026-11-06, the launchpad's stable read in case 1).
  wait_for "$READY_TIMEOUT" "Traefik's install job" kubectl -n kube-system wait --for=condition=complete job/helm-install-traefik --timeout=1s
  kubectl -n kube-system rollout status deployment/traefik --timeout="${READY_TIMEOUT}s" >&2

  printf 'cluster-argo-rollouts: installing Argo Rollouts %s\n' "$ARGO_ROLLOUTS_VERSION" >&2
  tmp=$(mktemp)
  trap 'rm -f "$tmp"' EXIT
  curl -fsSL "https://github.com/argoproj/argo-rollouts/releases/download/$ARGO_ROLLOUTS_VERSION/install.yaml" -o "$tmp"
  got=$(sha256sum "$tmp" | cut -d' ' -f1)
  [ "$got" = "$ARGO_INSTALL_SHA256" ] || die "install.yaml $ARGO_ROLLOUTS_VERSION has sha256 $got, want $ARGO_INSTALL_SHA256"
  kubectl create namespace argo-rollouts --dry-run=client -o yaml | kubectl apply -f - >&2
  kubectl apply --server-side -n argo-rollouts -f "$tmp" >&2
  kubectl -n argo-rollouts rollout status deployment/argo-rollouts --timeout="${READY_TIMEOUT}s" >&2

  kubectl create namespace "$ARGO_NAMESPACE" --dry-run=client -o yaml | kubectl apply -f - >&2
  for f in "$manifests"/*.yaml; do
    sed "s|@STABLE_IMAGE@|$ARGO_REGISTRY_HOST/$image|" "$f"
    printf '\n---\n'
  done | k apply -f - >&2

  k get services -o json \
    | jq -c '.items[] | select(.spec.selector == null) | {name: .metadata.name, ports: [.spec.ports[] | {name: (.name // ""), port: .targetPort, protocol}]}' \
    | while read -r svc; do
        name=$(printf '%s' "$svc" | jq -r .name)
        ip=$(compose_ip "$name") || die "no plane service $name on ${COMPOSE_PROJECT_NAME}_default to bridge"
        printf 'cluster-argo-rollouts: %s -> %s\n' "$name" "$ip" >&2
        printf '%s' "$svc" | jq --arg ip "$ip" '{
          apiVersion: "discovery.k8s.io/v1", kind: "EndpointSlice",
          metadata: {name: "\(.name)-plane", labels: {"kubernetes.io/service-name": .name}},
          addressType: "IPv4", ports: .ports, endpoints: [{addresses: [$ip]}]}' \
          | k apply -f - >&2
      done

  sh "$here/ready.sh"
}

down() {
  docker-compose --profile argo rm -fsv k8s >&2
  rm -rf "$out"
}

case "${1:-}" in
  up) shift; up "$@" ;;
  down) down ;;
  *) die "usage: cluster.sh up <manifests-dir> <image> | cluster.sh down" ;;
esac

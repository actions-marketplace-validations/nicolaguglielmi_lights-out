#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# argo-rollouts-env: the cluster, the Rollout and the helpers every verb of
# this adapter shares (docs/adr/0051 §2). Sourced, not executed. kubectl
# reads KUBECONFIG; the namespace and the Rollout's name are the only two
# things this adapter needs to know about a team's cluster.
: "${ARGO_NAMESPACE:=lights-out}"
: "${ARGO_ROLLOUT:=backend}"
# The port every revision answers /healthz on: the Workload port's :8000
# (docs/adr/0030 §2).
: "${ARGO_HEALTH_PORT:=8000}"
: "${READY_TIMEOUT:=60}"

k() {
  kubectl --namespace "$ARGO_NAMESPACE" "$@"
}

# rollout_json: the Rollout object as JSON on stdout, or exit 1.
rollout_json() {
  k get rollout "$ARGO_ROLLOUT" -o json
}

# status_patch PATCH: a merge patch on the Rollout's status subresource,
# which is how kubectl-argo-rollouts itself promotes, aborts and retries
# (pkg/kubectl-argo-rollouts/cmd/{promote,abort,retry}, v1.10.2): a status
# patch on the main resource is silently ignored.
status_patch() {
  k patch rollout "$ARGO_ROLLOUT" --subresource=status --type merge -p "$1" >/dev/null
}

# version_of HASH: the version the first Ready pod of the ReplicaSet with
# pod-template-hash HASH reports at its own /healthz, read through the API
# server's pod proxy — the pod directly, not through the traffic router,
# as envoy-canary reads its containers (docs/adr/0013 §4). Empty, exit 1,
# when no such pod answers.
version_of() {
  pod=$(k get pods -l "rollouts-pod-template-hash=$1" -o json \
    | jq -r '[.items[] | select(.metadata.deletionTimestamp == null)
              | select(any(.status.conditions[]?; .type == "Ready" and .status == "True"))
              | .metadata.name] | first // empty')
  [ -n "$pod" ] || return 1
  kubectl get --raw "/api/v1/namespaces/$ARGO_NAMESPACE/pods/$pod:$ARGO_HEALTH_PORT/proxy/healthz" 2>/dev/null \
    | jq -er .version
}

# weight_of JSON: the canary weight the traffic router was given, 0 when
# none was (a Rollout at rest, or aborted).
weight_of() {
  printf '%s' "$1" | jq -r '.status.canary.weights.canary.weight // 0'
}

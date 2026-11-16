#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# flagger-env: the cluster, the Canary and the helpers every verb of this
# adapter shares (docs/adr/0095 §1). Sourced, not executed. kubectl reads
# KUBECONFIG. Flagger runs the analysis; lights-out holds two of its
# webhooks on the loadtester's gate API (docs/adr/0095 §2):
#   confirm-traffic-increase -> /gate/check      opened by shift.sh, one step
#   rollback                 -> /rollback/check  opened by rollback.sh
#   confirm-promotion        -> /gate/halt       never opened by lights-out
: "${FLAGGER_NAMESPACE:=lights-out}"
: "${FLAGGER_CANARY:=backend}"
# The port every revision answers /healthz on: the Workload port's :8000
# (docs/adr/0030 §2).
: "${FLAGGER_HEALTH_PORT:=8000}"
: "${READY_TIMEOUT:=60}"
# The loadtester's Service, in the Canary's namespace (adapters/flagger/
# install.sh puts it there).
: "${FLAGGER_LOADTESTER:=flagger-loadtester}"

k() {
  kubectl --namespace "$FLAGGER_NAMESPACE" "$@"
}

# canary_json: the Canary object as JSON on stdout, or exit 1.
canary_json() {
  k get canaries.flagger.app "$FLAGGER_CANARY" -o json
}

# field JSON FILTER: one jq -r read of a Canary JSON.
field() {
  printf '%s' "$1" | jq -r "$2"
}

# tester PATH: one POST of {"name","namespace"} to the loadtester, through
# the API server's service proxy: /gate/open, /gate/close, /rollback/open,
# /rollback/close (pkg/loadtester/server.go, v1.45.0). Exit 1 if it fails.
tester() {
  body=$(mktemp)
  jq -cn --arg n "$FLAGGER_CANARY" --arg ns "$FLAGGER_NAMESPACE" '{name: $n, namespace: $ns}' > "$body"
  if kubectl create --raw "/api/v1/namespaces/$FLAGGER_NAMESPACE/services/$FLAGGER_LOADTESTER:80/proxy$1" -f "$body" >/dev/null 2>&1; then
    rm -f "$body"
  else
    rm -f "$body"
    printf 'flagger: POST %s on %s/%s failed\n' "$1" "$FLAGGER_NAMESPACE" "$FLAGGER_LOADTESTER" >&2
    return 1
  fi
}

# version_of NAME: the version the first Ready pod labelled
# app.kubernetes.io/name=NAME reports at its own /healthz, read through the
# API server's pod proxy, the pod directly, not through the router (docs/
# adr/0013 §4). NAME is the Canary's target for the canary and
# <target>-primary for the primary, the labels Flagger gives them. Empty,
# exit 1, when no such pod answers.
version_of() {
  pod=$(k get pods -l "app.kubernetes.io/name=$1" -o json \
    | jq -r '[.items[] | select(.metadata.deletionTimestamp == null)
              | select(any(.status.conditions[]?; .type == "Ready" and .status == "True"))
              | .metadata.name] | first // empty')
  [ -n "$pod" ] || return 1
  kubectl get --raw "/api/v1/namespaces/$FLAGGER_NAMESPACE/pods/$pod:$FLAGGER_HEALTH_PORT/proxy/healthz" 2>/dev/null \
    | jq -er .version
}

# in_flight PHASE: true when Flagger has a canary revision out (docs/adr/
# 0095 §3): analysing, or held at the promotion gate, or being promoted.
in_flight() {
  case "$1" in Progressing|WaitingPromotion|Promoting|Finalising) return 0 ;; *) return 1 ;; esac
}

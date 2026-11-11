#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# canary-url-envoy-canary: the Delivery port's optional fifth verb (docs/adr/
# 0072 §3): one URL on stdout that reaches only the canary revision, here
# Envoy's canary-only listener (envoy.yaml, port 8081, routed to the canary
# cluster whatever the weights). It is a name on the plane's network, where
# verify/dast.sh runs the scanner, and is published on no host port: a
# port more on the host would be one more to collide on, for a check that
# is off by default. Through Envoy, as the stable is at APP_URL, so the two
# scans see the same proxy's headers. Not a gate: no GO/NO-GO.
set -eu
printf 'http://envoy:8081\n'

#!/bin/sh
# shellcheck disable=SC2034 # every var here is for the sourcing script
# SPDX-License-Identifier: Apache-2.0
#
# gitea-env: identity and endpoints for the bootstrapped L0 repo (docs/adr/
# 0017 §5). Sourced, not executed, by bootstrap.sh, clone-url.sh, push.sh
# and open-pr.sh — never invoked as a command itself. The password is
# deliberately low-entropy, the docs/adr/0012 §9 precedent: at L0 Gitea
# holds no data worth protecting, and a duller string keeps gitleaks quiet
# without an allowlist.
: "${PLANE_HOST:=host.containers.internal}"
GITEA_OWNER=lights-out
# The workload's repository: this checkout for the bundled app, the
# attached one otherwise (docs/adr/0036 §9).
GITEA_REPO=workload
GITEA_USER=lights-out
GITEA_PASSWORD=lights-out-local-not-a-secret
GITEA_EMAIL=lights-out@lights-out.invalid
GITEA_URL="http://$PLANE_HOST:3000"
GITEA_API="$GITEA_URL/api/v1"
# Authenticated URL for a push or a fetch that needs write access; never
# written to a .git/config, always passed as a command argument (docs/adr/
# 0017 §4: the model never holds this credential).
GITEA_PUSH_URL="http://$GITEA_USER:$GITEA_PASSWORD@$PLANE_HOST:3000/$GITEA_OWNER/$GITEA_REPO.git"
# Anonymous clone URL: the worker clones with no credential.
GITEA_CLONE_URL="$GITEA_URL/$GITEA_OWNER/$GITEA_REPO.git"

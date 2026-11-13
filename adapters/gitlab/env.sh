#!/bin/sh
# shellcheck disable=SC2034 # every var here is for the sourcing script
# SPDX-License-Identifier: Apache-2.0
#
# gitlab-env: identity and endpoints of the GitLab CE instance the adapter
# is proved on (docs/adr/0058 §8), beside the plane at GITLAB_PORT. Sourced,
# never executed. The token is the docs/adr/0012 §9 precedent, as
# adapters/gitea/env.sh's password: a published, low-entropy constant that
# instance.sh seeds, on an instance that holds nothing worth protecting.
: "${PLANE_HOST:=host.containers.internal}"
: "${GITLAB_PORT:=8929}"
GITLAB_OWNER=root
# The workload's repository, as Gitea's (docs/adr/0037 §9).
GITLAB_REPO=workload
GITLAB_TOKEN=lights-out-local-gitlab-not-a-secret
GITLAB_URL="http://$PLANE_HOST:$GITLAB_PORT"
GITLAB_API="$GITLAB_URL/api/v4"
# The project id GitLab's API takes: the path, URL-encoded.
GITLAB_PROJECT="$GITLAB_API/projects/$GITLAB_OWNER%2F$GITLAB_REPO"
# Authenticated URL for a push, passed as an argument only, never written to
# a .git/config (docs/adr/0017 §4); oauth2 is the user GitLab takes a token as.
GITLAB_PUSH_URL="http://oauth2:$GITLAB_TOKEN@$PLANE_HOST:$GITLAB_PORT/$GITLAB_OWNER/$GITLAB_REPO.git"
# Anonymous clone URL: the project is public.
GITLAB_CLONE_URL="$GITLAB_URL/$GITLAB_OWNER/$GITLAB_REPO.git"
# The secret gates/codehost-conformance.sh case 10 looks for.
CODEHOST_SECRET=$GITLAB_TOKEN

# api CURL-ARGS...: one call to the API, the token on curl's stdin, never in
# an argv (the docs/adr/0043 §2 rule the GitHub verbs keep). -f is the
# caller's choice: some answers are expected failures.
api() {
  printf 'PRIVATE-TOKEN: %s\n' "$GITLAB_TOKEN" | curl -sS --connect-timeout 2 --max-time 30 -H @- "$@"
}

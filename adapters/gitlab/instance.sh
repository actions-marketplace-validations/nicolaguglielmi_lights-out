#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# instance-gitlab: the GitLab CE the adapter is proved on (docs/adr/0058 §8),
# beside the plane. Not a CodeHost verb and not a gate: a team that already
# runs GitLab never calls it.
#
#   instance.sh up     start it, wait until it serves, seed the token
#                      adapters/gitlab/env.sh names, then ready.sh
#   instance.sh down   the container and its volumes gone
#
# GITLAB_BOOT_TIMEOUT, 600 s, is this file's decision: 224 s measured on
# 2026-11-13 (a 4.5 GiB podman VM), with room for a slower runner.
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=adapters/gitlab/env.sh
. "$here/env.sh"
: "${GITLAB_BOOT_TIMEOUT:=600}"
compose() { docker-compose -f "$here/compose.yaml" "$@"; }
die() { printf 'instance-gitlab: %s\n' "$*" >&2; exit 1; }

case "${1:-}" in
  up)
    export GITLAB_PORT
    compose up -d gitlab >&2 || die "docker-compose up failed"
    i=0
    until [ "$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 --max-time 10 "$GITLAB_URL/users/sign_in")" = 200 ]; do
      i=$((i + 5))
      [ "$i" -lt "$GITLAB_BOOT_TIMEOUT" ] || { compose logs --tail 40 gitlab >&2 || :; die "$GITLAB_URL does not serve after ${GITLAB_BOOT_TIMEOUT}s"; }
      sleep 5
    done
    printf 'instance-gitlab: serving after about %ss; seeding the token\n' "$i" >&2
    # The token, set to the published constant (no password grant in GitLab
    # 19: a personal access token is the API's credential). Three tries:
    # right after boot the database can still cancel the runner's query on
    # its statement timeout (seen 2026-11-13 on a loaded VM).
    n=0
    until compose exec -T gitlab gitlab-rails runner "
      u = User.find_by_username('root')
      t = u.personal_access_tokens.find_by(name: 'lights-out') ||
          u.personal_access_tokens.new(name: 'lights-out', scopes: [:api, :write_repository], expires_at: 300.days.from_now)
      t.set_token('$GITLAB_TOKEN')
      t.save!
    " >&2; do
      n=$((n + 1))
      [ "$n" -lt 3 ] || die "seeding the token failed 3 times"
      printf 'instance-gitlab: seeding the token failed, try %s of 3 in 20 s\n' "$((n + 1))" >&2
      sleep 20
    done
    READY_TIMEOUT=${READY_TIMEOUT:-60} sh "$here/ready.sh"
    ;;
  down)
    compose down -v >&2
    ;;
  *)
    die "usage: instance.sh up | down"
    ;;
esac

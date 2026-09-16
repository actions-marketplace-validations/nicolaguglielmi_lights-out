#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# bootstrap-gitea: creates the admin user, the lights-out/lights-out repo
# with Actions off, and force-pushes this checkout's HEAD to its main
# branch (docs/adr/0017 §5). Idempotent: safe on every `assign`, because
# Gitea holds no persistent volume (docs/adr/0012) and starts empty on
# every `./go up`. Actions stay off: a job nobody consults before M6 is
# noise, not proof (docs/adr/0017 §5 amends docs/adr/0015 §7 — the runner
# socket and the first Gitea job move to M6). Adapter convention (docs/adr/
# 0012 §6): not a gate, silent on success, one stderr line and exit 1 on
# failure.
set -eu
# shellcheck disable=SC1007 # CDPATH= is the portable way to neutralise CDPATH
here=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# shellcheck source=adapters/gitea/env.sh
. "$here/adapters/gitea/env.sh"

# 1. Admin user. INSTALL_LOCK skips the web installer, so the CLI is the
# only way to create the first user. "already exists" is success.
if ! out=$(docker-compose exec -T gitea gitea admin user create \
    --admin --username "$GITEA_USER" --password "$GITEA_PASSWORD" \
    --email "$GITEA_EMAIL" --must-change-password=false 2>&1); then
  case "$out" in
    *"already exists"*) : ;;
    *) printf 'bootstrap-gitea: user create failed: %s\n' "$out" >&2; exit 1 ;;
  esac
fi

# 2. Repo, public, no template. 201 created, 409 already exists. No -f:
# curl's own failure-on-HTTP-error would discard the body and the code
# together on the expected, idempotent 409, which is not a failure here.
tmp=$(mktemp)
code=$(curl -sS -o "$tmp" -w '%{http_code}' \
  -u "$GITEA_USER:$GITEA_PASSWORD" -H 'Content-Type: application/json' \
  -d "{\"name\":\"$GITEA_REPO\",\"private\":false,\"auto_init\":false}" \
  "$GITEA_API/user/repos") || code=000
body=$(cat "$tmp"); rm -f "$tmp"
case "$code" in
  201|409) : ;;
  *) printf 'bootstrap-gitea: create repo returned %s: %s\n' "$code" "$body" >&2; exit 1 ;;
esac

# 3. Actions off: a job that runs on every push and nobody reads before M6.
curl -fsS -u "$GITEA_USER:$GITEA_PASSWORD" -H 'Content-Type: application/json' \
  -X PATCH -d '{"has_actions":false}' \
  "$GITEA_API/repos/$GITEA_OWNER/$GITEA_REPO" >/dev/null \
  || { printf 'bootstrap-gitea: could not disable Actions\n' >&2; exit 1; }

# 4. Mirror this checkout's HEAD onto Gitea's main. Force: the L0 repo is a
# mirror of the local clone, not a place to keep hand-made history.
git -C "$here" push --force "$GITEA_PUSH_URL" HEAD:refs/heads/main >&2 \
  || { printf 'bootstrap-gitea: push to main failed\n' >&2; exit 1; }

# 5. Wait until Gitea has processed that push. The repo is created empty
# and stays `empty: true` until the post-receive hook has run, which is
# asynchronous to `git push` returning; an empty repo has no pulls unit,
# so open-pr.sh right after this got 404 from mustAllowPulls (docs/adr/
# 0019, seen on a cold plane 2026-09-16; the transient HANDOFF M5 noted).
: "${READY_TIMEOUT:=60}"
i=0
while [ "$i" -lt "$READY_TIMEOUT" ]; do
  empty=$(curl -fsS --connect-timeout 1 --max-time 3 -u "$GITEA_USER:$GITEA_PASSWORD" \
    "$GITEA_API/repos/$GITEA_OWNER/$GITEA_REPO" | jq -r .empty 2>/dev/null) || empty=""
  [ "$empty" = false ] && exit 0
  i=$((i + 1)); sleep 1
done
printf 'bootstrap-gitea: repo still reports empty=%s %ss after the push\n' "${empty:-no answer}" "$READY_TIMEOUT" >&2
exit 1

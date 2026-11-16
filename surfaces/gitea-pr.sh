#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gitea-pr: a Gitea of a surface demo's own and a PR on it (docs/adr/0058
# §7, shared by docs/adr/0095 §8). Sourced by surfaces/jenkins/demo.sh and
# surfaces/circleci/demo.sh, never run. The caller sets engine, here, work,
# net, gitea, gitea_image and pw, and defines say, nogo (ci/lib.sh) and
# `agent ENTRYPOINT ARGS...`, one command with curl and jq on the network,
# $work at its own path. Optional: PR_RECIPE, a file put on main at
# PR_RECIPE_AT. Leaves: api, token (write:repository), repo, base, head and
# number, the PR's.
# --- 2. Gitea ----------------------------------------------------------------
"$engine" network create "$net" >/dev/null || nogo "could not create the network $net"
"$engine" run -d --name "$gitea" --network "$net" \
  -e GITEA__security__INSTALL_LOCK=true -e GITEA__actions__ENABLED=false \
  -e GITEA__server__ROOT_URL="http://$gitea:3000/" "$gitea_image" >/dev/null \
  || nogo "Gitea did not start"
api=http://$gitea:3000/api/v1
i=0
until agent curl -fsS --max-time 3 "$api/version" >/dev/null 2>&1; do
  i=$((i + 1))
  [ "$i" -lt 60 ] || nogo "Gitea does not answer at $api after 60 tries"
  sleep 1
done
"$engine" exec "$gitea" gitea admin user create --admin --username lights-out --password "$pw" \
  --email lights-out@lights-out.invalid --must-change-password=false >/dev/null \
  || nogo "could not create the Gitea user"
token=$("$engine" exec "$gitea" gitea admin user generate-access-token --username lights-out \
  --token-name surface --scopes write:repository --raw) || nogo "could not create a Gitea token"
agent curl -fsS -o /dev/null -u "lights-out:$pw" -H 'Content-Type: application/json' \
  -d '{"name":"minimal","private":false}' "$api/user/repos" || nogo "could not create the repository"
say "Gitea $gitea_image up as $gitea"

# --- 3. the repository and the PR ------------------------------------------------
repo=$work/minimal
mkdir -p "$repo"
cp -R workloads/minimal/. "$repo/"
gitc() { git -C "$repo" -c user.name=lights-out-demo -c user.email=demo@lights-out.invalid -c commit.gpgsign=false "$@"; }
gitc init -q -b main
gitc add -A
gitc commit -q -m "workloads/minimal, as a repository of its own"
out=$(cd "$repo" && LIGHTS_OUT_OUT="$work/init" sh "$here/lights-out" init) || nogo "lights-out init: $out"
[ -f "$work/init/.lights-out/workload.env" ] || nogo "init left no draft"
cp -R "$work/init/.lights-out/." "$repo/.lights-out/"
# A recipe the surface reads from the repository, on main with the contract.
if [ -n "${PR_RECIPE:-}" ]; then
  mkdir -p "$repo/$(dirname "$PR_RECIPE_AT")"
  cp "$PR_RECIPE" "$repo/$PR_RECIPE_AT"
fi
gitc add -A
gitc commit -q -m "the lights-out contract, the gates half drafted by lights-out init"
base=$(gitc rev-parse HEAD)
gitc checkout -q -b version
printf '\n\n@app.get("/version")\ndef version():\n    return {"version": APP_VERSION}\n' >> "$repo/minimal/app.py"
printf '\n\ndef test_version_returns_the_app_version(client):\n    assert client.get("/version").json() == {"version": APP_VERSION}\n' >> "$repo/tests/test_app.py"
gitc add -A
gitc commit -q -m "a /version route, and its test"
head=$(gitc rev-parse HEAD)
agent git -C "$repo" push -q "http://lights-out:$pw@$gitea:3000/lights-out/minimal.git" main version >&2 \
  || nogo "could not push main and version to Gitea"
# Gitea takes a push in the background, and a repository it still reports
# empty has no pulls to open (adapters/gitea/bootstrap.sh, step 4).
i=0
until [ "$(agent sh -c "curl -fsS '$api/repos/lights-out/minimal' | jq -r .empty" 2>/dev/null)" = false ]; do
  i=$((i + 1))
  [ "$i" -lt 60 ] || nogo "Gitea still reports the repository empty after the push"
  sleep 1
done
agent curl -fsS -o "$work/pr.json" -u "lights-out:$pw" -H 'Content-Type: application/json' \
  -d '{"title":"a /version route","head":"version","base":"main"}' "$api/repos/lights-out/minimal/pulls" \
  || nogo "could not open the PR"
number=$(agent jq -r '.number // empty' "$work/pr.json")
[ -n "$number" ] || nogo "Gitea's answer to the PR has no number: $(cat "$work/pr.json")"
say "PR #$number: main $base <- version $head"

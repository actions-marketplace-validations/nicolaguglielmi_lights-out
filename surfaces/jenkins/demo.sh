#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# The M32 acceptance for Jenkins (docs/adr/0058 §7), `./go demo-jenkins`:
# another CI posts the lights-out gates line on a local PR, and stays a
# surface. On the host, as demo-package is, because its subject is the
# wrapper and an engine, as on a Jenkins agent. Nothing of the plane: a
# Gitea of its own on a network of its own, so the shared plane slot is free.
#
#   1. the agent image: surfaces/jenkins/Containerfile, built once per revision
#   2. Gitea, a user, a token for statuses, a public repository
#   3. workloads/minimal as a repository, its init-drafted contract on main
#      (the wrapper on the host, as demo-package drafts it), a change and its
#      test on a branch, both pushed, a PR opened
#   4. Jenkinsfile Runner runs surfaces/jenkins/Jenkinsfile on a clone of the
#      PR's head, the engine socket mounted, the workspace at its own path
#   5. GO when the line Jenkins printed is a GO, Gitea shows it as the
#      lights-out/jenkins status on the PR's head, success, the description
#      the line (cut at 140 characters), and no status named gates or review
#      was posted: the tower's contexts are not a surface's (§6)
#
# LIGHTS_OUT_IMAGE, when set, is the gates image the wrapper runs; else the
# wrapper's own published version.
set -eu
name=demo-jenkins
. ci/lib.sh

engine=${CONTAINER_ENGINE:?CONTAINER_ENGINE not set; run this via ./go demo-jenkins}
here=$(pwd -P)
start=$(date +%s)
image="localhost/lights-out-jenkins:$(cksum < surfaces/jenkins/Containerfile | cut -d' ' -f1)"
gitea_image=$(awk '/^  gitea:$/ { f = 1 } f && /^    image:/ { print $2; exit }' compose.yaml)
[ -n "$gitea_image" ] || nogo "no gitea image in compose.yaml"
run_id=$(date -u +%Y%m%d%H%M%S)-$$
net=lights-out-jenkins-$run_id
gitea=lights-out-jenkins-gitea-$run_id
# Under the checkout: a path the engine's VM shares, at the same path.
work=$here/.crew/jenkins/$run_id
pw=lights-out-local-not-a-secret
say() { printf '[demo-jenkins] %s\n' "$*" >&2; }

cleanup() {
  ec=$?
  "$engine" rm -f "$gitea" >/dev/null 2>&1 || :
  "$engine" network rm "$net" >/dev/null 2>&1 || :
  # The gates container wrote as root through the socket.
  "$engine" run --rm -v "$here/.crew/jenkins:/j" --entrypoint rm "$image" -rf "/j/$run_id" >/dev/null 2>&1 || rm -rf "$work"
  exit "$ec"
}
trap cleanup EXIT INT TERM
mkdir -p "$work"

# The engine's socket, as ./go finds it for the workbench.
if [ "$engine" = podman ]; then
  sock=$(podman info --format '{{.Host.RemoteSocket.Path}}'); sock=${sock#unix://}
else
  sock=${DOCKER_HOST:-}; sock=${sock#unix://}; [ -n "$sock" ] || sock=/var/run/docker.sock
fi
[ -n "$sock" ] || nogo "$engine has no API socket to hand the Jenkins agent"

# --- 1. the agent ------------------------------------------------------------
if ! "$engine" image inspect "$image" >/dev/null 2>&1; then
  say "building $image (Jenkinsfile Runner, amd64; emulated on arm64, a few minutes once)"
  "$engine" build --platform linux/amd64 -t "$image" -f surfaces/jenkins/Containerfile surfaces/jenkins >&2 \
    || nogo "the Jenkins agent image did not build (see above)"
fi
# agent ENTRYPOINT ARGS...: one command in the agent image, on the network.
agent() {
  ep=$1
  shift
  "$engine" run --rm -i --platform linux/amd64 --network "$net" --security-opt label=disable \
    -v "$work:$work" --entrypoint "$ep" "$image" "$@"
}

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
  --token-name jenkins --scopes write:repository --raw) || nogo "could not create a Gitea token"
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

# --- 4. Jenkins ------------------------------------------------------------------
ws=$work/ws
git clone -q "$repo" "$ws"
git -C "$ws" checkout -q "$head"
say "Jenkinsfile Runner on PR #$number's head"
# The runner itself, not the image's launcher, which fixes its own workspace.
set -- --jenkins-war /app/jenkins --plugins /usr/share/jenkins/ref/plugins \
  --file /workspace/Jenkinsfile --runWorkspace "$ws"
image_flag=""
[ -z "${LIGHTS_OUT_IMAGE:-}" ] || image_flag="-e LIGHTS_OUT_IMAGE"
export LIGHTS_OUT_STATUS_TOKEN="$token" LIGHTS_OUT_BASE="$base" LIGHTS_OUT_HEAD="$head" \
  LIGHTS_OUT_STATUSES="$api/repos/lights-out/minimal/statuses"
# shellcheck disable=SC2086 # image_flag is one flag or none
if "$engine" run --rm --platform linux/amd64 --network "$net" --security-opt label=disable \
    -v "$sock:/var/run/docker.sock" -e DOCKER_HOST=unix:///var/run/docker.sock -e CONTAINER_ENGINE=docker \
    -v "$work:$work" -v "$here/lights-out:/usr/local/bin/lights-out:ro" \
    -v "$here/surfaces/jenkins/Jenkinsfile:/workspace/Jenkinsfile:ro" \
    -e LIGHTS_OUT_STATUS_TOKEN -e LIGHTS_OUT_BASE -e LIGHTS_OUT_HEAD -e LIGHTS_OUT_STATUSES $image_flag --entrypoint /app/bin/jenkinsfile-runner "$image" "$@" > "$work/jenkins.log" 2>&1; then
  jrc=0
else
  jrc=$?
fi
unset LIGHTS_OUT_STATUS_TOKEN
sed 's/^/  [jenkins] /' "$work/jenkins.log" | tail -n 40 >&2
line=$(sed -n 's/^lights-out line: //p' "$work/jenkins.log" | tail -n 1)
[ -n "$line" ] || nogo "Jenkins printed no lights-out line (exit $jrc)"
case "$line" in
  "GO: gates — "*) ;;
  *) nogo "Jenkins judged the change: [$line]" ;;
esac
[ "$jrc" -eq 0 ] || nogo "the line is GO and Jenkins still failed the build (exit $jrc)"

# --- 5. what Gitea shows -------------------------------------------------------
statuses=$(agent curl -fsS "$api/repos/lights-out/minimal/commits/$head/statuses") || nogo "could not read the statuses of $head"
mine=$(printf '%s' "$statuses" | agent jq -c '[.[] | select(.context == "lights-out/jenkins")] | first // empty')
[ -n "$mine" ] || nogo "no lights-out/jenkins status on $head: $statuses"
state=$(printf '%s' "$mine" | agent jq -r .status)
desc=$(printf '%s' "$mine" | agent jq -r .description)
[ "$state" = success ] || nogo "the lights-out/jenkins status is $state, the line was GO"
case "$line" in
  "$desc") ;;
  "$desc"*) [ "${#desc}" -ge 100 ] || nogo "the status says [$desc], Jenkins printed [$line]" ;;
  *) nogo "the status says [$desc], Jenkins printed [$line]" ;;
esac
others=$(printf '%s' "$statuses" | agent jq -r '[.[] | select(.context == "gates" or .context == "review")] | length')
[ "$others" = 0 ] || nogo "a surface posted under the tower's own contexts: $statuses"
pr_head=$(agent curl -fsS "$api/repos/lights-out/minimal/pulls/$number" | agent jq -r .head.sha)
[ "$pr_head" = "$head" ] || nogo "PR #$number's head is $pr_head, the status is on $head"

go_with "Jenkinsfile Runner posted [$line] as lights-out/jenkins on PR #$number, $(( $(date +%s) - start ))s"

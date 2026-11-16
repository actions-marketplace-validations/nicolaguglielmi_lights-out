#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# The M62 acceptance for GitLab CI (docs/adr/0095 §7), `./go demo-gitlab-ci`:
# GitLab itself runs surfaces/gitlab-ci/.gitlab-ci.yml on a merge request and
# the job posts the lights-out gates line as its own commit status. On the
# host, as demo-jenkins is, because its subject is the recipe, a runner and
# an engine. Nothing of the plane: everything on a network of its own.
#
#   1. a tools image (docker:29-cli with git, curl and jq) for the API calls
#      and the pushes, built once
#   2. GitLab CE, the gitlab adapter's image and settings (adapters/gitlab/
#      compose.yaml, docs/adr/0058 §8), its external_url on the network's
#      name, so a job reaches the API and the clone URL; a token for the API
#      and runner creation
#   3. workloads/minimal as a project: its init-drafted contract and the
#      recipe as .gitlab-ci.yml on main, a change and its test on a branch;
#      the project's variables LIGHTS_OUT_STATUS_TOKEN (and LIGHTS_OUT_IMAGE)
#   4. a real gitlab-runner v19.5.3, docker executor, socket binding: the job
#      containers get the engine's socket, the builds directory at the same
#      path on both sides (so the wrapper's bind mount means the same thing),
#      and this checkout's wrapper on PATH
#   5. a merge request: GitLab starts the merge request pipeline; GO when the
#      job printed a GO line, GitLab shows lights-out/gitlab-ci on the head,
#      success, the line (cut at 140) as its description, and nothing named
#      gates or review
#
# GitLab needs about 2.4 GB and four minutes (docs/adr/0058 §8): on a small
# podman VM run this alone. LIGHTS_OUT_IMAGE, when set, is the gates image
# the job runs; else the wrapper's own published version.
set -eu
name=demo-gitlab-ci
. ci/lib.sh

engine=${CONTAINER_ENGINE:?CONTAINER_ENGINE not set; run this via ./go demo-gitlab-ci}
here=$(pwd -P)
start=$(date +%s)
# The adapter's instance, read from its compose file: one image, one pin.
gitlab_image=$(awk '/^  gitlab:$/ { f = 1 } f && /^    image:/ { print $2; exit }' adapters/gitlab/compose.yaml)
[ -n "$gitlab_image" ] || nogo "no gitlab image in adapters/gitlab/compose.yaml"
# shellcheck source=adapters/gitlab/env.sh
. adapters/gitlab/env.sh
# GitLab Runner v19.5.3, the newest tag on 2026-11-16 (docs/adr/0095).
runner_image=docker.io/gitlab/gitlab-runner:v19.5.3@sha256:ffe21f021468d4aa1e56f05316d88597c23bf4818840e8edaa858131fabd7991
# The shell the surface demos run in: the docker CLI, git, curl, jq; root
# on files the host user owns, so git trusts every directory.
tools_file='FROM docker.io/library/docker:29-cli
RUN apk add --no-cache git curl jq >/dev/null && git config --system --add safe.directory "*"'
tools_image="localhost/lights-out-surface-tools:$(printf '%s' "$tools_file" | cksum | cut -d' ' -f1)"
run_id=$(date -u +%Y%m%d%H%M%S)-$$
net=lights-out-gitlab-ci-$run_id
gitlab=lights-out-gitlab-ci-$run_id
runner=lights-out-gitlab-runner-$run_id
# Under the checkout: a path the engine's VM shares, at the same path.
work=$here/.crew/gitlab-ci/$run_id
pw=lights-out-local-not-a-secret
url=http://gitlab:$GITLAB_PORT
api=$url/api/v4
say() { printf '[demo-gitlab-ci] %s\n' "$*" >&2; }

cleanup() {
  ec=$?
  "$engine" rm -f "$runner" >/dev/null 2>&1 || :
  # The job containers the runner left, on this network.
  for c in $("$engine" ps -aq --filter "network=$net" 2>/dev/null); do "$engine" rm -f "$c" >/dev/null 2>&1 || :; done
  "$engine" rm -f "$gitlab" >/dev/null 2>&1 || :
  "$engine" network rm "$net" >/dev/null 2>&1 || :
  # The jobs wrote as root through the socket.
  "$engine" run --rm -v "$here/.crew/gitlab-ci:/g" --entrypoint rm "$tools_image" -rf "/g/$run_id" >/dev/null 2>&1 || rm -rf "$work"
  exit "$ec"
}
trap cleanup EXIT INT TERM
mkdir -p "$work/builds" "$work/runner"

if [ "$engine" = podman ]; then
  sock=$(podman info --format '{{.Host.RemoteSocket.Path}}'); sock=${sock#unix://}
else
  sock=${DOCKER_HOST:-}; sock=${sock#unix://}; [ -n "$sock" ] || sock=/var/run/docker.sock
fi
[ -n "$sock" ] || nogo "$engine has no API socket to hand the runner"

# --- 1. the tools ------------------------------------------------------------
if ! "$engine" image inspect "$tools_image" >/dev/null 2>&1; then
  printf '%s\n' "$tools_file" \
    | "$engine" build -t "$tools_image" -f - "$work" >&2 || nogo "the tools image did not build"
fi
# t ARGS...: one command in the tools image, on the network, $work at its path.
t() {
  ep=$1
  shift
  "$engine" run --rm -i --network "$net" --security-opt label=disable -v "$work:$work" -w "$work" \
    --entrypoint "$ep" "$tools_image" "$@"
}
# gl CURL-ARGS...: one call to GitLab's API with the token on stdin.
gl() {
  printf 'PRIVATE-TOKEN: %s\n' "$GITLAB_TOKEN" | t sh -c 'exec curl -fsS --max-time 30 -H @- "$@"' sh "$@"
}

# --- 2. GitLab ---------------------------------------------------------------
"$engine" network create "$net" >/dev/null || nogo "could not create the network $net"
# The adapter's settings (adapters/gitlab/compose.yaml), external_url on the
# network's name.
"$engine" run -d --name "$gitlab" --network "$net" --network-alias gitlab --shm-size 256m \
  -e GITLAB_ROOT_PASSWORD="$pw" \
  -e GITLAB_OMNIBUS_CONFIG="external_url '$url'; puma['worker_processes'] = 0; sidekiq['concurrency'] = 5; prometheus_monitoring['enable'] = false; registry['enable'] = false; gitlab_kas['enable'] = false; gitlab_rails['usage_ping_enabled'] = false;" \
  "$gitlab_image" >/dev/null || nogo "GitLab did not start"
say "GitLab starting ($gitlab_image); about four minutes"
i=0
until [ "$(t curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$url/users/sign_in" 2>/dev/null)" = 200 ]; do
  i=$((i + 5))
  [ "$i" -lt 900 ] || nogo "GitLab does not serve after 900 s"
  sleep 5
done
say "GitLab serves after about ${i}s; seeding the token"
n=0
until "$engine" exec "$gitlab" gitlab-rails runner "
  u = User.find_by_username('root')
  t = u.personal_access_tokens.new(name: 'lights-out', scopes: [:api, :write_repository, :create_runner], expires_at: 300.days.from_now)
  t.set_token('$GITLAB_TOKEN')
  t.save!
" >&2; do
  n=$((n + 1))
  [ "$n" -lt 3 ] || nogo "seeding the token failed 3 times"
  sleep 20
done
i=0
until gl -o /dev/null "$api/version" 2>/dev/null; do
  i=$((i + 1)); [ "$i" -lt 60 ] || nogo "GitLab's API does not take the token"; sleep 1
done

# --- 3. the project ------------------------------------------------------------
gl -o /dev/null -X POST -d name=minimal -d visibility=public "$api/projects" || nogo "could not create the project"
project="$api/projects/root%2Fminimal"
gl -o /dev/null -X POST -d key=LIGHTS_OUT_STATUS_TOKEN --data-urlencode "value=$GITLAB_TOKEN" "$project/variables" \
  || nogo "could not set LIGHTS_OUT_STATUS_TOKEN"
if [ -n "${LIGHTS_OUT_IMAGE:-}" ]; then
  gl -o /dev/null -X POST -d key=LIGHTS_OUT_IMAGE --data-urlencode "value=$LIGHTS_OUT_IMAGE" "$project/variables" \
    || nogo "could not set LIGHTS_OUT_IMAGE"
fi
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
cp surfaces/gitlab-ci/.gitlab-ci.yml "$repo/.gitlab-ci.yml"
gitc add -A
gitc commit -q -m "the lights-out contract and the GitLab CI recipe"
base=$(gitc rev-parse HEAD)
gitc checkout -q -b version
printf '\n\n@app.get("/version")\ndef version():\n    return {"version": APP_VERSION}\n' >> "$repo/minimal/app.py"
printf '\n\ndef test_version_returns_the_app_version(client):\n    assert client.get("/version").json() == {"version": APP_VERSION}\n' >> "$repo/tests/test_app.py"
gitc add -A
gitc commit -q -m "a /version route, and its test"
head=$(gitc rev-parse HEAD)
t git -c safe.directory='*' -C "$repo" push -q "http://oauth2:$GITLAB_TOKEN@gitlab:$GITLAB_PORT/root/minimal.git" main version >&2 \
  || nogo "could not push main and version to GitLab"
say "project root/minimal: main $base <- version $head"

# --- 4. the runner -------------------------------------------------------------
reg=$(gl -X POST -d runner_type=instance_type -d run_untagged=true -d description=lights-out-demo "$api/user/runners") \
  || nogo "could not create a runner"
rtoken=$(printf '%s' "$reg" | t jq -r '.token // empty')
[ -n "$rtoken" ] || nogo "GitLab's answer to the runner has no token"
cat > "$work/runner/config.toml" <<EOF
concurrent = 1
check_interval = 3
[[runners]]
  name = "lights-out-demo"
  url = "$url"
  clone_url = "$url"
  token = "$rtoken"
  executor = "docker"
  builds_dir = "$work/builds"
  [runners.docker]
    image = "docker.io/library/docker:29-cli"
    network_mode = "$net"
    pull_policy = ["if-not-present"]
    volumes = ["$sock:/var/run/docker.sock", "$work/builds:$work/builds", "$here/lights-out:/usr/local/bin/lights-out:ro"]
EOF
"$engine" run -d --name "$runner" --network "$net" --security-opt label=disable \
  -v "$sock:/var/run/docker.sock" -v "$work/runner:/etc/gitlab-runner" "$runner_image" run >/dev/null \
  || nogo "the runner did not start"
say "gitlab-runner $runner_image up, socket binding"

# --- 5. the merge request ------------------------------------------------------
mr=$(gl -X POST -d source_branch=version -d target_branch=main -d "title=a /version route" "$project/merge_requests") \
  || nogo "could not open the merge request"
iid=$(printf '%s' "$mr" | t jq -r '.iid // empty')
[ -n "$iid" ] || nogo "GitLab's answer to the merge request has no iid"
say "merge request !$iid opened; waiting for its pipeline"
i=0
status=""
while :; do
  p=$(gl "$project/merge_requests/$iid/pipelines" 2>/dev/null) || p='[]'
  status=$(printf '%s' "$p" | t jq -r 'first | .status // empty')
  pid=$(printf '%s' "$p" | t jq -r 'first | .id // empty')
  case "$status" in success|failed|canceled|skipped) break ;; esac
  i=$((i + 5))
  [ "$i" -lt 900 ] || nogo "the merge request pipeline is ${status:-absent} after 900 s; runner: $("$engine" logs --tail 20 "$runner" 2>&1 | tr '\n' ' ')"
  sleep 5
done
job=$(gl "$project/pipelines/$pid/jobs" | t jq -r '[.[] | select(.name == "lights-out")] | first | .id // empty')
[ -n "$job" ] || nogo "pipeline $pid has no lights-out job"
gl "$project/jobs/$job/trace" > "$work/job.log" || nogo "could not read job $job's log"
sed 's/^/  [gitlab-ci] /' "$work/job.log" | tail -n 40 >&2
# GitLab 19 prefixes every trace line with a timestamp and a stream mark
# ("2026-11-16T09:03:57.859373Z 01O "): the line is what follows the label.
line=$(tr -d '\r' < "$work/job.log" | sed -n 's/^.*lights-out line: //p' | tail -n 1)
[ -n "$line" ] || nogo "the job printed no lights-out line (pipeline $status)"
case "$line" in
  "GO: gates — "*) ;;
  *) nogo "GitLab CI judged the change: [$line]" ;;
esac
[ "$status" = success ] || nogo "the line is GO and the pipeline is $status"

statuses=$(gl "$project/repository/commits/$head/statuses?all=true") || nogo "could not read the statuses of $head"
mine=$(printf '%s' "$statuses" | t jq -c '[.[] | select(.name == "lights-out/gitlab-ci")] | first // empty')
[ -n "$mine" ] || nogo "no lights-out/gitlab-ci status on $head: $statuses"
state=$(printf '%s' "$mine" | t jq -r .status)
desc=$(printf '%s' "$mine" | t jq -r .description)
[ "$state" = success ] || nogo "the lights-out/gitlab-ci status is $state, the line was GO"
case "$line" in
  "$desc") ;;
  "$desc"*) [ "${#desc}" -ge 100 ] || nogo "the status says [$desc], the job printed [$line]" ;;
  *) nogo "the status says [$desc], the job printed [$line]" ;;
esac
others=$(printf '%s' "$statuses" | t jq -r '[.[] | select(.name == "gates" or .name == "review")] | length')
[ "$others" = 0 ] || nogo "a surface posted under the tower's own contexts: $statuses"

go_with "GitLab CI (gitlab-runner, merge request !$iid's pipeline) posted [$line] as lights-out/gitlab-ci, $(( $(date +%s) - start ))s"

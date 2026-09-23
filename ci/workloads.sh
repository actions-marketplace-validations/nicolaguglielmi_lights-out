#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-workloads: replaces ci/compose.sh (docs/adr/0030 §5). Every workload
# directory in the repo -- today's app/, tomorrow's workloads/minimal/,
# found by the two globs docs/adr/0030 §5 names, */workload.env and
# workloads/*/workload.env -- is checked against the Workload port
# (docs/adr/0030 §2-3), independent of whichever WORKLOAD the enclosing
# `make` invocation itself selected:
#   (a) workload.env defines exactly the seven keys, no more, no fewer --
#       an extra one could silently override DELIVERY or a `?=` default
#       (docs/adr/0030 §4's trap);
#   (b) `docker-compose config`, with that workload's own compose.yaml
#       merged in explicitly (-f, not the ambient COMPOSE_FILE, which
#       reflects only the enclosing make's own WORKLOAD) and WORKLOAD set
#       for interpolation, shows the three fixed services with their
#       profiles and images (docs/adr/0030 §3);
#   (c) that workload's flags/flags.json defines release-freeze and its
#       own WORKLOAD_KILL_SWITCH.
# `docker-compose config` only renders the merged project; it needs no
# engine socket (ci/compose.sh's own rationale, docs/adr/0012), only the
# WORKBENCH_IMAGE precondition every other compose call in this repo has
# (the root compose.yaml's gemini-cli and runner services require it, :?).
set -eu
name=workloads
. ci/lib.sh

[ -n "${WORKBENCH_IMAGE:-}" ] || nogo "WORKBENCH_IMAGE is not set; run this via ./go, not directly"

err_log=$(mktemp)
trap 'rm -f "$err_log"' EXIT

expected_keys='CANARY_VERSION MUTATION_BASELINE WORKLOAD_KILL_SWITCH WORKLOAD_SAMPLE_PATH WORKLOAD_LOCKFILES WORKLOAD_MUTATION_SCOPE WORKLOAD_TEST_ROOT'

envs=""
for f in */workload.env workloads/*/workload.env; do
  [ -e "$f" ] || continue
  envs="$envs $f"
done
[ -n "$envs" ] || nogo "no */workload.env or workloads/*/workload.env found"

for f in $envs; do
  wd=$(dirname "$f")

  # (a) exactly the seven keys. workload.env is "profile syntax" (its own
  # header): KEY=VALUE, one per line, no quotes, no inline comments -- a
  # comment line is dropped whole, never a suffix, so a naive substring
  # search on the raw text would be wrong here.
  reason=$(python3 - "$f" "$expected_keys" <<'PY'
import sys

path, expected_s = sys.argv[1], sys.argv[2]
expected = set(expected_s.split())

with open(path) as fh:
    raw_lines = [ln.strip() for ln in fh]

keys = []
for ln in raw_lines:
    if not ln or ln.startswith("#"):
        continue
    key, sep, _ = ln.partition("=")
    if not sep:
        print(f"{path}: not KEY=VALUE: {ln!r}")
        sys.exit(1)
    keys.append(key)

seen = set()
dupes = sorted({k for k in keys if k in seen or seen.add(k)})
if dupes:
    print(f"{path} defines a key more than once: {', '.join(dupes)}")
    sys.exit(1)

actual = set(keys)
extra = sorted(actual - expected)
missing = sorted(expected - actual)
if extra or missing:
    bits = []
    if extra:
        bits.append("extra: " + ", ".join(extra))
    if missing:
        bits.append("missing: " + ", ".join(missing))
    print(f"{path} must define exactly the seven docs/adr/0030 §2 keys ({'; '.join(bits)})")
    sys.exit(1)
PY
  ) && ok=1 || ok=0
  [ "$ok" -eq 1 ] || nogo "$reason"

  # (b) the merged project, with this workload's compose.yaml explicit,
  # shows the three fixed services (docs/adr/0030 §3). --profile canary
  # --profile test: `config` renders only the default-profile services
  # unless a profile is explicitly enabled (confirmed empirically,
  # docker-compose v5.0.1), so backend-canary and backend-test would
  # otherwise never appear in the output at all. stderr goes to a log, not
  # into $config_json: any warning on stderr on an otherwise-successful run
  # would land inside the string the next step parses as JSON.
  set +e
  config_json=$(WORKLOAD="$wd" docker-compose --profile canary --profile test \
    -f compose.yaml -f "$wd/compose.yaml" config --format json 2>"$err_log")
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    cat "$err_log" >&2
    nogo "docker-compose config failed for WORKLOAD=$wd; see stderr"
  fi

  reason=$(python3 - "$wd" "$config_json" <<'PY'
import json
import sys

wd, config_json = sys.argv[1], sys.argv[2]
try:
    data = json.loads(config_json)
except ValueError as exc:
    print(f"{wd}: docker-compose config did not print valid JSON: {exc}")
    sys.exit(1)

services = data.get("services", {})
want_profiles = {
    "backend": [],
    "backend-canary": ["canary"],
    "backend-test": ["test"],
}
missing = [s for s in want_profiles if s not in services]
if missing:
    print(f"{wd}: docker-compose config is missing service(s): {', '.join(missing)}")
    sys.exit(1)

for svc_name, want in want_profiles.items():
    profiles = services[svc_name].get("profiles") or []
    if profiles != want:
        print(f"{wd}: service {svc_name} has profiles {profiles}, want {want}")
        sys.exit(1)

backend_image = services["backend"].get("image", "")
if not backend_image.startswith("localhost:5050/lights-out-backend:"):
    print(f"{wd}: service backend image is {backend_image!r}, want the localhost:5050/lights-out-backend: prefix (docs/adr/0030 §3)")
    sys.exit(1)

if "build" in services["backend-canary"]:
    print(f"{wd}: service backend-canary has a build: section; docs/adr/0030 §3 says only the verified digest runs, never a build")
    sys.exit(1)
if not services["backend-canary"].get("image"):
    print(f"{wd}: service backend-canary has no image")
    sys.exit(1)
PY
  ) && ok=1 || ok=0
  [ "$ok" -eq 1 ] || nogo "$reason"

  # (c) the flag file defines release-freeze and this workload's own kill
  # switch -- read from this workload's own file, never the ambient
  # $WORKLOAD_KILL_SWITCH, which only reflects the enclosing make's WORKLOAD.
  kill_switch=$(grep -v '^[[:space:]]*#' "$f" | sed -n 's/^WORKLOAD_KILL_SWITCH=//p')
  [ -n "$kill_switch" ] || nogo "$f: WORKLOAD_KILL_SWITCH is empty"

  flags_file="$wd/flags/flags.json"
  [ -f "$flags_file" ] || nogo "$flags_file does not exist"

  reason=$(python3 - "$flags_file" "$kill_switch" <<'PY'
import json
import sys

path, kill_switch = sys.argv[1], sys.argv[2]
with open(path) as f:
    try:
        data = json.load(f)
    except ValueError as exc:
        print(f"{path} is not valid JSON: {exc}")
        sys.exit(1)

flags = data.get("flags", {})
missing = [n for n in ("release-freeze", kill_switch) if n not in flags]
if missing:
    print(f"{path} does not define flag(s): {', '.join(missing)}")
    sys.exit(1)
PY
  ) && ok=1 || ok=0
  [ "$ok" -eq 1 ] || nogo "$reason"
done

go

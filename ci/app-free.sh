#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-app-free: core/, gates/, verify/ and adapters/ never name the app
# workload (docs/adr/0030 §5) -- a workload is a directory chosen by
# WORKLOAD=<path>, reached only through workload.env's seven keys, the
# three fixed compose services and the two in-image runners, never by a
# literal app path, the meetup domain, its flag or its geocoder dependency.
# vendor-free's shape (ci/vendor-free.sh): a comment naming the app to say
# "not here" is a coupling too, the day the app moves it turns false. The
# word list is docs/adr/0030 §5's; grown when a workload gains a new name
# to hide, never shrunk.
#
# docs/adr/0037 §6-§7 grew it twice. The dev-worker's prompt is scanned
# too: the workload's layout is in its brief, worker.md. And an attached
# repository is reached only through WORKLOAD and WORKLOAD_CONTRACT, so
# neither its clone's location (.attached, the Makefile's and ./go's) nor
# its contract directory (.lights-out) is spelt here. core/attach.sh is the
# one exception to the second: it refuses a repository without a contract
# before any make runs to compute one.
set -eu
name=app-free
. ci/lib.sh

for d in core gates verify adapters roles/dev-worker; do
  [ -d "$d" ] || nogo "$d/ not found"
done

words='app/|meetup|waitlist|geocoder|workloads/|\.attached'

hits=$(grep -rniE "$words" core gates verify adapters roles/dev-worker \
  --include='*.sh' --include='*.py' --include='*.md' --include='*.promql' \
  --include='*.yaml' --include='*.yml' \
  --exclude-dir=__pycache__ --exclude-dir=.pytest_cache || true)
contract_hits=$(grep -rnE '\.lights-out' core gates verify adapters roles/dev-worker \
  --include='*.sh' --include='*.py' --include='*.md' --include='*.promql' \
  --include='*.yaml' --include='*.yml' \
  --exclude-dir=__pycache__ --exclude-dir=.pytest_cache | grep -v '^core/attach\.sh:' || true)

[ -z "$hits" ] || nogo "core/, gates/, verify/, adapters/ or roles/dev-worker/ names a workload" "$hits"
[ -z "$contract_hits" ] || nogo "core/, gates/, verify/, adapters/ or roles/dev-worker/ spells the contract directory instead of WORKLOAD_CONTRACT" "$contract_hits"

go

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
set -eu
name=app-free
. ci/lib.sh

for d in core gates verify adapters; do
  [ -d "$d" ] || nogo "$d/ not found"
done

words='app/|meetup|waitlist|geocoder|workloads/'

hits=$(grep -rniE "$words" core gates verify adapters \
  --include='*.sh' --include='*.py' --include='*.md' --include='*.promql' \
  --include='*.yaml' --include='*.yml' \
  --exclude-dir=__pycache__ --exclude-dir=.pytest_cache || true)

[ -z "$hits" ] || nogo "core/, gates/, verify/ or adapters/ names the app workload" "$hits"

go

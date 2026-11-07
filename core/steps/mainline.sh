#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# step-mainline (docs/adr/0056 §3, §4): main is checked after merge. The
# logic is core/mainline.py's `check` (docs/adr/0052 §3): it judges main's
# head against the last green main with the tree gates, in groups of at
# most MAINLINE_GROUP_MAX (policy/mainline.env), bisects a red group,
# reverts the culprit through the code host and judges main again. Prints
# main-green, or ci-failed when this ticket's own merge was reverted; a
# main still red after one revert fails the step, the reason in the
# `mainline`/`main` document. Next state: main-green or ci-failed.
set -eu
: "${TICKET:?TICKET not set}"
: "${DOC_FILE:?DOC_FILE not set; run this via core/tower.sh, not directly}"
: "${CODE_HOST:?CODE_HOST not set; run this via ./go, not directly}"
exec python3 core/mainline.py check

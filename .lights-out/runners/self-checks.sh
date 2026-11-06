#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# lights-out's own TEST_CMD (docs/adr/0049): `make ci`, the thirty
# self-checks `./go ci` runs (shellcheck, the gate output contract, the
# unit tests, roles=6 and the rest), from the repository root, in the
# workbench the gates run in. `make gates` exports every make variable
# into the gate's environment (BASE, HEAD, WORKLOAD, GATES_OUT...), and
# the self-checks must see a cold checkout, as `./go ci` gives them: the
# environment is emptied but for what the workbench image itself sets
# (PATH, and git's safe.directory, workbench/Containerfile's ENV; without
# it ci/attach.sh's probe ran git blind). The exit code is the verdict
# (docs/adr/0042 §1).
set -eu

exec env -i PATH="$PATH" HOME=/tmp NO_COLOR=1 \
  GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*' \
  WORKBENCH_IMAGE="${WORKBENCH_IMAGE:?WORKBENCH_IMAGE not set; this runs inside the lights-out image}" \
  make --no-print-directory ci

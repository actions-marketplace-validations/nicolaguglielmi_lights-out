#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-codehost-conformance: the CodeHost port's conformance suite (docs/adr/
# 0043 §5, in the shape of docs/adr/0026 and 0041). Written from the ADR and
# the port's contract, never from an adapter. It drives whichever CODE_HOST
# is set, only through adapters/$CODE_HOST/*.sh, plus plain git for the
# commits it makes and for the clones it reads back. Ten cases, in this
# order, the first disagreement a NO-GO naming the case:
#   1 bootstrap, then its postcondition: the host's default branch is at the
#     workload's HEAD
#   2 clone-url.sh, a clone of it, and a .git/config with no credential
#   3 push.sh of conformance/<run id>, one commit adding one file
#   4 open-pr.sh twice, which must return the same PR number
#   5 status.sh pending, then a 200-character success, then await.sh -> success
#   6 pr.sh: open, not merged, the head as pushed, merge_sha null
#   7 a second commit is pushed; a merge at the old head must exit 1 and
#     leave the PR unmerged
#   8 a merge at the new head prints "<merge> <head>"; pr.sh agrees, and the
#     merge commit's second parent is that head (docs/adr/0019 §5)
#   9 the same merge again prints the same line
#  10 no secret appears in anything the suite captured from the adapters
#
# It writes to a real repository: a branch, a PR, a status and a merge commit
# that adds one file to the default branch. Point it at a throwaway one only;
# the nightly does (.github/workflows/nightly-github.yml). Cleanup is the
# suite's temporary directory and nothing else: no verb deletes a branch or
# closes a PR, and a merged PR cannot be deleted, so every run leaves its
# conformance/<run id> branch, its PR and its merge commit behind (a failed
# run leaves the PR open). The branch name is date and random, so runs never
# collide.
#
# Where it runs: ci.yml's `launch` job against Gitea with the plane up
# (CODE_HOST=gitea; Gitea's bootstrap pushes this checkout's HEAD to main),
# and the nightly against an attached throwaway repository on GitHub
# (CODE_HOST=github). A red nightly with a green launch points at the GitHub
# adapter, not the suite.
#
# Case 10 reads what the suite captured: the stdout and stderr of every verb
# and of every git command it ran. It looks for GITHUB_TOKEN when that is set,
# and for the Gitea adapter's password when CODE_HOST=gitea, both read here
# and handed over in CONFORMANCE_SECRETS. That password is
# a published, low-entropy constant (adapters/gitea/env.sh); the case still
# proves that git's own output, which redacts the userinfo of a URL it prints,
# and the adapter's messages never carry it. Before it looks, the scan is
# shown to find a secret it is handed.
#
# The numbers are decisions of this suite, none a measurement: a branch on the
# host is awaited 60 s (30 polls, 2 s apart) before the second commit counts
# as pushed; a merge that the host does not accept at once is tried 3 times,
# 5 s apart, because a host computes mergeability after a push, and any other
# answer is final; await.sh gets 2 s for the pending status, which must not
# end it, and 60 s for the success. 200 characters is ADR 0043 §5's: longer
# than the 140 GitHub accepts (§3).
#
# Lives in gates/, so ci/contract.sh cold-runs it inside `make ci` with no
# CONFORMANCE set and no plane: the guard below must be the first thing that
# runs. `make codehost-conformance` is the only caller that sets
# CONFORMANCE=1; the acceptance commands are `./go codehost-conformance`
# (Gitea, plane up) and `./go codehost-conformance CODE_HOST=github`, never a
# bare `sh gates/...` (CLAUDE.md). The cases are core/gates/codehost.py
# (docs/adr/0084).
set -eu
name=codehost-conformance
. ci/lib.sh

# Instant NO-GO, before anything touches a host (docs/adr/0026 §4).
if [ "${CONFORMANCE:-}" != "1" ]; then
  nogo "set CONFORMANCE=1: this suite pushes a branch, opens a PR and merges it on the code host (./go codehost-conformance)"
fi

# The secrets case 10 looks for, one a line. Naming a host is this file's,
# never core/'s (docs/adr/0024 §1, ci/vendor-free.sh).
CONFORMANCE_SECRETS=${GITHUB_TOKEN:-}
if [ "${CODE_HOST:-}" = gitea ]; then
  # shellcheck source=adapters/gitea/env.sh
  password=$(. adapters/gitea/env.sh; printf '%s' "$GITEA_PASSWORD") \
    || nogo "adapters/gitea/env.sh could not be read for the password case 10 looks for"
  CONFORMANCE_SECRETS="$CONFORMANCE_SECRETS
$password"
fi
export CONFORMANCE_SECRETS
verdict core.gates.codehost

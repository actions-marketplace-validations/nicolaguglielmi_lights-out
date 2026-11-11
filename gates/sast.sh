#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# gates-sast: docs/adr/0015 §4, as amended by docs/adr/0072 §1. Static
# analysis over the workload's shipped code by the workload's own SAST_CMD
# (docs/adr/0042 §1), run where its TOOLCHAIN_IMAGE says (core/toolchain.sh).
# The runner prints one JSON line on stdout, `{"findings": N, "items":
# [{"rule", "file", "line"}]}`, `file` relative to the directory it runs
# from ($WORKLOAD/$WORKLOAD_TEST_ROOT), its report on stderr, non-zero only
# if the tool itself failed. For the bundled app the command is `sh
# tests/sast/run.sh` (bandit) in the compose service backend-test.
#
# The verdict is on the diff, as gates/deps.sh's (docs/adr/0072 §1): the
# runner scans HEAD's checkout, and, when HEAD has findings, the merge-base
# in a worktree of its own. core/sastdiff.py fingerprints each finding as
# (rule, file followed through renames, hash of the flagged line's text
# with whitespace stripped) and only a fingerprint HEAD has more times than
# the base is NO-GO; inherited findings are listed on stderr and in
# sast.json. A HEAD with no finding is GO without scanning the base. A
# runner that prints no `items`, on either side, predates ADR 0072: HEAD is
# judged whole, any finding NO-GO, as before, and stderr says so. No
# severity floor: it would be a number with no provenance. `# nosec` (or
# the stack's own) stays the escape hatch for a new finding.
#
# Both sides run the runner the checkout carries: in the tower's CI step a
# contract's runners/ are the base's (docs/adr/0033), and the merge-base's
# own are the base's by definition.
set -eu
name=sast
. ci/lib.sh
require_range
. core/toolchain.sh

out_dir=${GATES_OUT:-.gates-out}
mkdir -p "$out_dir"

[ -n "${SAST_CMD:-}" ] || nogo "SAST_CMD is empty (docs/adr/0042 §1)"
toolchain_preflight

tmp=$(mktemp -d)
bwt=""
trap '[ -z "$bwt" ] || git -C "$WORKLOAD" worktree remove --force "$bwt" >/dev/null 2>&1 || :; rm -rf "$tmp"' EXIT

# The run directory's path from the repository root, and on disk.
tr=${WORKLOAD_TEST_ROOT:-}
tr=${tr%/}
[ -z "$tr" ] || tr="$tr/"
wl_prefix=$(git -C "$WORKLOAD" rev-parse --show-prefix)

# scan SIDE: SAST_CMD's stdout to $tmp/SIDE.out, its exit code to $scan_rc.
scan() {
  set +e
  run_in_toolchain "$SAST_CMD" > "$tmp/$1.out"
  scan_rc=$?
  set -e
}

# whole COUNT: today's whole-tree verdict, for a runner with no items.
whole() {
  printf 'sast: the runner prints no items (it predates docs/adr/0072): HEAD judged whole\n' >&2
  printf '{"findings": %s, "where": "%s"}\n' "$1" "$toolchain_where" > "$out_dir/sast.json"
  [ "$1" -eq 0 ] || nogo "in $toolchain_where: $1 SAST finding(s) in the workload's scope"
  go_with "in $toolchain_where"
}

scan head
if [ "$scan_rc" -eq 125 ]; then
  printf '{"findings": null, "where": "%s"}\n' "$toolchain_where" > "$out_dir/sast.json"
  nogo "in $toolchain_where: the toolchain itself failed before the scan ran; see stderr"
fi
summary=$(python3 core/sastdiff.py read "$tmp/head.out") || {
  printf '{"findings": null, "where": "%s"}\n' "$toolchain_where" > "$out_dir/sast.json"
  nogo "in $toolchain_where: $summary"
}
count=${summary% *}
kind=${summary#* }
if [ "$count" -eq 0 ] && [ "$scan_rc" -ne 0 ]; then
  printf '{"findings": null, "where": "%s"}\n' "$toolchain_where" > "$out_dir/sast.json"
  nogo "in $toolchain_where: SAST_CMD exited $scan_rc with no findings parsed; see stderr"
fi
[ "$kind" = items ] || whole "$count"
if [ "$count" -eq 0 ]; then
  printf '{"findings": 0, "where": "%s", "new": [], "inherited": []}\n' "$toolchain_where" > "$out_dir/sast.json"
  go_with "in $toolchain_where, none new (0 inherited)"
fi

# The base: nothing to scan for the empty tree; the same scan for an empty
# range; otherwise the merge-base, in a worktree, with the same command.
base_root=-
base_line=-
if [ "$(git -C "$WORKLOAD" cat-file -t "$base")" = tree ]; then
  printf 'sast: the base is a tree with nothing to scan: every finding is new\n' >&2
elif [ "$base" = "$head" ]; then
  base_root="$WORKLOAD/$tr"
  base_line="$tmp/head.out"
else
  bwt="$tmp/base"
  git -C "$WORKLOAD" worktree add -q --detach "$bwt" "$base" >&2 \
    || nogo "in $toolchain_where: could not check out the base $base"
  printf 'sast: %s finding(s) at HEAD; scanning the base %s to tell new from inherited\n' "$count" "$base" >&2
  # A compose file of this repository's (a bundled workload) resolves its
  # build context from the current directory: the base's run starts from
  # the base's copy of it. An attached contract names ${WORKLOAD} instead.
  here=""
  if [ "$toolchain_form" = compose ] \
    && [ "$(git -C "$WORKLOAD" rev-parse --show-toplevel)" = "$(git rev-parse --show-toplevel 2>/dev/null)" ]; then
    here="$bwt/$(git rev-parse --show-prefix)"
  fi
  # shellcheck disable=SC2030 # WORKLOAD is the base's in this subshell only
  (
    [ -z "$here" ] || cd "$here"
    WORKLOAD="$bwt/$wl_prefix"
    scan base
    exit "$scan_rc"
  ) && scan_rc=0 || scan_rc=$?
  [ "$scan_rc" -ne 125 ] || nogo "in $toolchain_where: the toolchain itself failed on the base; see stderr"
  base_summary=$(python3 core/sastdiff.py read "$tmp/base.out") \
    || nogo "in $toolchain_where: on the base, $base_summary"
  if [ "${base_summary% *}" -eq 0 ] && [ "$scan_rc" -ne 0 ]; then
    nogo "in $toolchain_where: SAST_CMD exited $scan_rc on the base with no findings parsed; see stderr"
  fi
  [ "${base_summary#* }" = items ] || whole "$count"
  base_root="$bwt/$wl_prefix$tr"
  base_line="$tmp/base.out"
  # shellcheck disable=SC2031 # the parent's WORKLOAD, HEAD's, as meant
  git -C "$WORKLOAD" diff -M --name-status -z "$base" "$head" > "$tmp/renames"
fi
[ -f "$tmp/renames" ] || : > "$tmp/renames"

# shellcheck disable=SC2031 # the parent's WORKLOAD, HEAD's, as meant
verdict=$(python3 core/sastdiff.py diff "$out_dir/sast.json" "$toolchain_where" "$wl_prefix$tr" \
  "$WORKLOAD/$tr" "$tmp/head.out" "$base_root" "$base_line" < "$tmp/renames") && rc=0 || rc=$?
case "$rc" in
  0) go_with "in $toolchain_where, $verdict" ;;
  1) nogo "in $toolchain_where: $verdict" ;;
  *) nogo "in $toolchain_where: could not compare the two scans: $verdict" ;;
esac

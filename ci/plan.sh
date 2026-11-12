#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-plan: the plan job of the workflows (docs/adr/0065). Two halves.
# The classifier, `sh .github/plan.sh classify` with the changed paths on
# stdin, prints `docs` when every path is documentation (§3) and `code`
# otherwise; a table of paths, written from §3, says which is which. And
# every job of ci, stranger, self, podman and package but plan and publish
# needs plan and runs only on its outputs (§1, §4): run for every job,
# full too for every job a docs-only push skips. package.yml's release jobs,
# dist, pypi, actions and release, are exempt like publish (docs/adr/0075
# §1): they run on a v* tag or a dispatch, never on a branch push, and a
# tag on a commit already green would otherwise skip its own release. The
# exemption names that file only. The check first proves each half can fail.
set -eu
name=plan
. ci/lib.sh

t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT

classify() { printf '%s\n' "$@" | sh .github/plan.sh classify; }

[ -f .github/plan.sh ] || nogo ".github/plan.sh is missing"

# One path each: what §3 calls documentation, then what it does not.
for p in README.md ROADMAP.md docs/PLAN.md docs/adr/0065-one-proof-per-commit.md \
         docs/launch/checklist.md site/index.html site/render.py .claude/skills/milestone/SKILL.md \
         actions/test-proof/README.md console/README.md; do
  [ "$(classify "$p")" = docs ] || nogo "$p is documentation (docs/adr/0065 §3); the classifier says $(classify "$p")"
done
for p in Makefile ci/lib.sh core/map.py docs/assets/lights-out.jpg tickets/0001.md \
         roles/dev-worker/prompt.md workloads/minimal/README.md .lights-out/worker.md \
         fixtures/logbook/README.md console/index.html actions/test-proof/action.yml \
         .github/workflows/ci.yml lights-out action.yml; do
  [ "$(classify "$p")" = code ] || nogo "$p is not documentation (docs/adr/0065 §3); the classifier says $(classify "$p")"
done
[ "$(classify README.md docs/PLAN.md)" = docs ] || nogo "two documentation paths are not docs"
[ "$(classify README.md Makefile)" = code ] || nogo "a documentation path and the Makefile are not code"
[ "$(printf '' | sh .github/plan.sh classify)" = code ] || nogo "no paths at all is not code: an empty compare proves nothing"

# The workflows: every job but plan, publish and package.yml's release jobs is gated on plan.
cat > "$t/gated.py" <<'PY'
import sys, yaml
FULL_KEEP = {("ci.yml", "ci"), ("self.yml", "gates")}
RELEASE = {("package.yml", n) for n in ("dist", "pypi", "actions", "release")}
def flaws(root, names):
    for f in names:
        d = yaml.safe_load(open(f"{root}/.github/workflows/{f}"))
        jobs = d.get("jobs") or {}
        p = jobs.get("plan")
        if not p:
            yield f"{f}: no plan job"
            continue
        if set((p.get("outputs") or {})) != {"run", "full"}:
            yield f"{f}: plan's outputs are not run and full"
        if p.get("permissions") != {"actions": "read", "contents": "read"}:
            yield f"{f}: plan's permissions are {p.get('permissions')}, want actions: read and contents: read"
        for n, j in jobs.items():
            if n in ("plan", "publish") or (f, n) in RELEASE:
                continue
            needs = j.get("needs") or []
            needs = [needs] if isinstance(needs, str) else needs
            c = str(j.get("if", ""))
            if "plan" not in needs or "needs.plan.outputs.run == 'true'" not in c:
                yield f"{f}: job {n} does not need plan and run only when run is true"
            elif (f, n) not in FULL_KEEP and "needs.plan.outputs.full == 'true'" not in c:
                yield f"{f}: job {n} runs on a docs-only push"
root = sys.argv[1]
out = list(flaws(root, sys.argv[2:]))
print("\n".join(out))
sys.exit(1 if out else 0)
PY
mkdir -p "$t/probe/.github/workflows"
cat > "$t/probe/.github/workflows/w.yml" <<'YML'
jobs:
  plan: {permissions: {actions: read, contents: read}, outputs: {run: x, full: y}}
  free: {if: "github.server_url == 'https://github.com'"}
  half: {needs: plan, if: "needs.plan.outputs.run == 'true'"}
  dist: {if: "github.server_url == 'https://github.com'"}
YML
found=$(python3 "$t/gated.py" "$t/probe" w.yml) && nogo "a job not gated on plan passed"
[ "$found" = "w.yml: job free does not need plan and run only when run is true
w.yml: job half runs on a docs-only push
w.yml: job dist does not need plan and run only when run is true" ] || nogo "the probe workflow did not give its two findings" "$found"

found=$(python3 "$t/gated.py" . ci.yml stranger.yml self.yml podman.yml package.yml) \
  || nogo "$(printf '%s\n' "$found" | wc -l | tr -d ' ') job(s) escape the plan job" "$found"
go

# SPDX-License-Identifier: Apache-2.0
"""gates/mutation.sh's judgement (docs/adr/0015 §3, docs/adr/0042 §1,
docs/adr/0074 §3-§4).

    python3 -m core.gates.mutation <base> <head> <where>

The workload's MUTATION_CMD over the lines the range BASE..HEAD added or
changed under $WORKLOAD/$WORKLOAD_MUTATION_SCOPE, run through
`sh core/toolchain-run.sh` (the wrapper already ran the preflight; WHERE is
its $toolchain_where). Its lines go in as MUTATION_LINES, groups
"<path>=<start>-<end>,...", space-separated, the path relative to the
workload's place in its repository plus WORKLOAD_TEST_ROOT (dropped as a
prefix), only the new side of each hunk, a pure deletion contributing
nothing. JUDGED names commits whose trees were already judged: each must be
a commit and an ancestor of HEAD; only the lines HEAD adds against the base
and against every judged tree are mutated, so a line any of them already has
is not mutated again. No line to mutate is GO by absence of subject,
`{"total": 0, "score": null}` in mutation.json and nothing run.

The score is the last non-empty stdout line of the command, one JSON object
written to mutation.json as read: GO when it has no mutant (total 0) or its
score is at least MUTATION_BASELINE - MUTATION_MARGIN (the effective policy,
docs/adr/0037 §5); otherwise NO-GO with the "SURVIVOR file:line operator"
lines of the command's stderr as details. Exit 125 is the toolchain failing,
any other non-zero exit a run that failed before scoring.
"""

import json
import os
import re
import tempfile

from . import PIPE, NoGo, main, proc, say

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def git(workload, *args):
    return proc(["git", "-C", workload, *args], stdout=PIPE, stderr=PIPE, text=True)


def added(diff, prefix):
    """{path: [(start, end), ...]}: the new side of each hunk of a -U0 diff."""
    ranges = {}
    current = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[4:].split("\t", 1)[0]
            if path == "/dev/null":
                current = None
                continue
            if path.startswith("b/"):
                path = path[2:]
            current = path[len(prefix):] if path.startswith(prefix) else path
        elif current and line.startswith("@@"):
            m = HUNK.match(line)
            if not m:
                continue
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            if count:
                ranges.setdefault(current, []).append((start, start + count - 1))
    return ranges


def numbers(ranges):
    return {n for a, b in ranges for n in range(a, b + 1)}


def runs(lines):
    """Sorted line numbers as (start, end) runs."""
    out = []
    for n in sorted(lines):
        if out and n == out[-1][1] + 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return [tuple(r) for r in out]


def unjudged(ranges, others):
    """RANGES kept to the lines in every one of OTHERS (HEAD's hunks against
    each judged tree); the kept ranges and the count of lines dropped."""
    kept, skipped = {}, 0
    for path, rs in ranges.items():
        lines = numbers(rs)
        before = len(lines)
        for other in others:
            lines &= numbers(other.get(path, []))
        skipped += before - len(lines)
        if lines:
            kept[path] = runs(lines)
    return kept, skipped


def groups(ranges):
    return " ".join(f"{p}={','.join(f'{a}-{b}' for a, b in rs)}" for p, rs in sorted(ranges.items()))


def score(line, baseline, margin):
    """(ok, data, reason) for the runner's one JSON line."""
    threshold = baseline - margin
    try:
        data = json.loads(line)
        if not isinstance(data, dict):
            raise ValueError("not a JSON object")
    except ValueError as exc:
        return False, None, f"malformed mutation run output: {exc}: {line!r}"
    total = data.get("total", 0)
    value = data.get("score")
    if total == 0 or (value is not None and value >= threshold):
        return True, data, None
    shown = "none" if value is None else f"{value:.3f}"
    return False, data, (f"{data.get('killed', 0)}/{total} mutants on changed lines killed "
                         f"({shown} < {threshold:.3f}); survivors on stderr")


def effective_policy(env, out):
    """ci/lib.sh's effective_policy, into OUT: None, or the reason it failed."""
    contract = env.get("WORKLOAD_CONTRACT")
    if not contract:
        return "WORKLOAD_CONTRACT is not set; run this via ./go, not directly"
    got = proc(["python3", "core/policy.py", "--platform", "policy/merge.env", "--workload-env",
                f"{contract}/workload.env", "--overrides", f"{contract}/policy.env", "--out", out],
               stdout=PIPE, text=True)
    if got.returncode != 0:
        return got.stdout.strip() or "core/policy.py failed without a reason; see stderr"
    return None


def toolchain(cmd, lines, log):
    """CMD through core/toolchain-run.sh: (exit code, stdout), stderr in LOG."""
    with open(log, "w") as err:
        got = proc(["sh", "core/toolchain-run.sh", cmd], env=dict(os.environ, MUTATION_LINES=lines),
                   stdout=PIPE, stderr=err, text=True)
    return got.returncode, got.stdout


def policy_value(path, key):
    with open(path) as fh:
        return "\n".join(ln.rstrip("\n")[len(key) + 1:] for ln in fh if ln.startswith(key + "="))


def judge(argv, env=None, run=toolchain, policy=effective_policy):
    env = os.environ if env is None else env
    base, head, where = argv
    workload = env.get("WORKLOAD", ".")
    gates_out = env.get("GATES_OUT") or ".gates-out"
    os.makedirs(gates_out, exist_ok=True)
    scope = env.get("WORKLOAD_MUTATION_SCOPE", "")
    got = git(workload, "rev-parse", "--show-prefix")
    if got.returncode != 0:
        raise NoGo(f"{workload} is not inside a git repository")
    prefix = got.stdout.strip() + env.get("WORKLOAD_TEST_ROOT", "")

    judged, short = [], []
    for j in (env.get("JUDGED") or "").split():
        jc = git(workload, "rev-parse", "-q", "--verify", f"{j}^{{commit}}")
        if jc.returncode != 0:
            raise NoGo(f"JUDGED names {j}, which is not a commit of the workload's repository (docs/adr/0074 §4)")
        jc = jc.stdout.strip()
        if git(workload, "merge-base", "--is-ancestor", jc, head).returncode != 0:
            raise NoGo(f"JUDGED names {j}, which is not an ancestor of HEAD {head} (docs/adr/0074 §4)")
        judged.append(jc)
        short.append(git(workload, "rev-parse", "--short", jc).stdout.strip())

    def diff_from(old):
        got = git(workload, "diff", "-U0", old, head, "--", scope)
        if got.returncode != 0:
            raise NoGo(f"could not read the diff for {base}..{head}")
        return added(got.stdout, prefix)

    ranges = diff_from(base)
    waived = ""
    if judged:
        ranges, skipped = unjudged(ranges, [diff_from(j) for j in judged])
        waived = f", {skipped} lines judged at {' '.join(short)}"
        say(f"mutation: {skipped} changed line(s) of {base}..{head} already judged at {' '.join(short)} "
            "(docs/adr/0074 §3)")
    lines = groups(ranges)
    if not lines:
        say(f"mutation: 0 mutants on changed lines in {base}..{head}; GO by absence of subject, nothing ran")
        with open(os.path.join(gates_out, "mutation.json"), "w") as fh:
            fh.write('{"total": 0, "score": null}\n')
        return f"in {where}{waived}, nothing ran"

    effective = os.path.join(gates_out, "effective-policy.env")
    failed = policy(env, effective)
    if failed:
        raise NoGo(failed)
    baseline = policy_value(effective, "MUTATION_BASELINE")
    if not baseline:
        raise NoGo("MUTATION_BASELINE is empty")
    try:
        baseline_f, margin_f = float(baseline), float(policy_value(effective, "MUTATION_MARGIN"))
    except ValueError:
        raise NoGo("MUTATION_BASELINE or MUTATION_MARGIN is not a number in the effective policy") from None

    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, "log")
        rc, out = run(env.get("MUTATION_CMD", ""), lines, log)
        with open(log) as fh:
            noise = fh.read()
    if noise:
        say(noise.rstrip("\n"))
    if rc == 125:
        raise NoGo(f"in {where}: the toolchain itself failed before the mutation run; see stderr")
    if rc != 0:
        raise NoGo(f"in {where}: mutation run failed before scoring (baseline or tooling error); see stderr")
    result = ([ln for ln in out.splitlines() if ln.strip()] or [""])[-1]
    survivors = [ln[len("SURVIVOR "):] for ln in noise.splitlines() if ln.startswith("SURVIVOR ")]
    ok, data, reason = score(result, baseline_f, margin_f)
    if data is not None:
        with open(os.path.join(gates_out, "mutation.json"), "w") as fh:
            json.dump(data, fh)
            fh.write("\n")
        if data.get("total", 0) == 0:
            say(f"mutation: 0 mutants on changed lines in {base}..{head} after running the mutation command; "
                "GO by absence of subject")
    if not ok:
        raise NoGo(f"in {where}: {reason}", *survivors)
    return f"in {where}{waived}"


if __name__ == "__main__":
    raise SystemExit(main(judge))

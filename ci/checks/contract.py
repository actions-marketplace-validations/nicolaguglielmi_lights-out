# SPDX-License-Identifier: Apache-2.0
"""ci-contract: meta-gate. Judges every other gate, and the light tier's entry
point (docs/adr/0061), on its stdout alone, and fails unless each one honours
the output contract in ci/lib.sh: exactly one stdout line, "GO: <name>"
(optionally followed by " — <detail>", docs/adr/0042 §3) with exit 0 or
"NO-GO: <name> — <reason>" with exit 1, no ANSI escape sequences. The gate's
own verdict does not matter here, only its shape. Scans ci/, gates/ and
verify/ (docs/adr/0011 §4), skipping directories that do not exist yet; gate
basenames must be unique across the three. A ci/ check that this `./go ci`
has already run is judged on the record of that run, the stdout and exit
code `record_check` left in $CI_RECORDS, and not run a second time
(docs/adr/0062 §3); every gate with no usable record, which is every gate
when ci-contract runs alone, is run cold: stdout captured, stderr discarded.
It also checks the lib's own side of the contract: `nogo` may leave its
details in the file $NOGO_DETAILS names, and stdout stays the one line
(docs/adr/0038 §5); `record_check` leaves NAME.out and NAME.rc only when
CI_RECORDS names a directory, and passes stdout and the exit code through
(docs/adr/0062 §1-§2). Each of those checks is shown to fail on a broken
lib, and the record judging on a planted tree of gates and records, run by
this check itself with CONTRACT_PLANTED=1.

Run by ci/contract.sh through `verdict` (docs/adr/0094: a ci/ check's logic
in ci/checks/, its tests in ci/tests/).
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

ESC = "\x1b"
GATE_DIRS = ("ci", "gates", "verify")
NOT_GATES = ("ci/lib.sh", "ci/contract.sh")

# The planted tree (CONTRACT_PLANTED): each gate's record or cold run, and the
# reason the planted run must give for rejecting it; the two it must accept.
PLANTED_REJECTED = {
    "two-lines": "lines=2", "ansi": "ansi", "go-exit-1": "GO,exit=1", "nogo-exit-0": "NO-GO,exit=0",
    "wrong-name": "format", "blank-after": "lines=2", "no-rc": "lines=2", "bad-rc": "lines=2",
    "never-run": "lines=2", "rc-check": "lines=2",
}
PLANTED_ACCEPTED = ("good", "good-nogo")
RECORDS = {  # gate: (NAME.out, NAME.rc or None); a gate absent here has no record
    "two-lines": ("GO: two-lines\nGO: two-lines\n", "0\n"),
    "ansi": ("GO: ansi — %s[31mred\n" % ESC, "0\n"),
    "go-exit-1": ("GO: go-exit-1\n", "1\n"),
    "nogo-exit-0": ("NO-GO: nogo-exit-0 — planted\n", "0\n"),
    "wrong-name": ("GO: someone-else\n", "0\n"),
    "blank-after": ("GO: blank-after\n\n", "0\n"),
    "no-rc": ("GO: no-rc\n", None),
    "bad-rc": ("GO: bad-rc\n", "zero\n"),
    "good": ("GO: good — planted\n", "0\n"),
    "good-nogo": ("NO-GO: good-nogo — planted\n", "1\n"),
}
COLD_LINES = {"two-lines": 1, "ansi": 1, "go-exit-1": 1, "nogo-exit-0": 1, "wrong-name": 1, "blank-after": 1,
              "good": 2, "good-nogo": 2, "no-rc": 2, "bad-rc": 2, "never-run": 2}

# nogo's side (docs/adr/0038 §5): a gate with details and one without, and
# three libs that break it, each one way.
WITH_DETAILS = 'set -eu\nname=probe\n. "$PROBE_LIB"\nnogo "the reason" "first detail" "second detail"\n'
NO_DETAILS = 'set -eu\nname=probe\n. "$PROBE_LIB"\nnogo "the reason"\n'
BROKEN_NOGO = {
    "bad-stdout": """nogo() { printf 'NO-GO: %s — %s\\n' "$name" "$1"; shift; printf '%s\\n' "$@"; printf '%s\\n' "$@" > "${NOGO_DETAILS:-/dev/null}"; exit 1; }\n""",
    "bad-nofile": """nogo() { printf 'NO-GO: %s — %s\\n' "$name" "$1"; shift; printf '%s\\n' "$@" >&2; exit 1; }\n""",
    "bad-unset": """nogo() { printf 'NO-GO: %s — %s\\n' "$name" "$1"; shift; printf '%s\\n' "$@" >&2; [ -z "$NOGO_DETAILS" ] || printf '%s\\n' "$@" > "$NOGO_DETAILS"; exit 1; }\n""",
}
RC_RUN = 'cd "$1"\n. ./ci/lib.sh\nrecord_check ci/rc-check.sh rc-check && rc=0 || rc=$?\necho "$rc" > "$2"\n'


def say(line):
    print(line, file=sys.stderr, flush=True)


def run(argv, **kw):
    """(exit code, stdout): stderr discarded unless KW says otherwise."""
    kw.setdefault("stderr", subprocess.DEVNULL)
    got = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True, check=False, **kw)
    return got.returncode, got.stdout


def shape(gate, rc, out):
    """Why OUT and RC break the contract for GATE ('lines=N', 'ansi',
    'GO,exit=N', 'NO-GO,exit=N', 'format'), or None."""
    lines = out.split("\n")
    if lines[-1] == "":
        lines.pop()
    if len(lines) != 1:
        return "lines=%d" % len(lines)
    line = lines[0]
    if ESC in line:
        return "ansi"
    if line == "GO: " + gate or (line.startswith("GO: %s — " % gate) and len(line) > len("GO: %s — " % gate)):
        return None if rc == 0 else "GO,exit=%d" % rc
    if line.startswith("NO-GO: %s — " % gate) and len(line) > len("NO-GO: %s — " % gate):
        return None if rc == 1 else "NO-GO,exit=%d" % rc
    return "format"


def usable(records, gate):
    """A record `./go ci` left for GATE: NAME.out, and NAME.rc one number of 0 to 255."""
    if not records:
        return False
    out, rc = os.path.join(records, gate + ".out"), os.path.join(records, gate + ".rc")
    if not (os.path.isfile(out) and os.access(out, os.R_OK) and os.path.isfile(rc) and os.access(rc, os.R_OK)):
        return False
    with open(rc, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    return len(lines) == 1 and re.fullmatch(r"[0-9]{1,3}", lines[0]) is not None and int(lines[0]) <= 255


def discover(root):
    """(the gates under ROOT's ci/, gates/ and verify/, in order; the basenames
    found twice)."""
    files, seen, dupes = [], set(), []
    for d in GATE_DIRS:
        if not os.path.isdir(os.path.join(root, d)):
            continue
        for name in sorted(os.listdir(os.path.join(root, d))):
            rel = "%s/%s" % (d, name)
            if not name.endswith(".sh") or rel in NOT_GATES or not os.path.isfile(os.path.join(root, rel)):
                continue
            gate = name[:-3]
            if gate in seen:
                dupes.append(gate)
            seen.add(gate)
            files.append(rel)
    return files, dupes


def rejected(line):
    """The planted run's NO-GO, read gate by gate: {gate: why}."""
    tail = line.split("violate the output contract:", 1)[1] if "violate the output contract:" in line else ""
    return {m.group(1): m.group(2) for m in re.finditer(r" ([A-Za-z0-9_.-]+)\(([^)]*)\)", tail)}


def planted_flaws(got):
    """What is wrong with the planted run's rejections GOT, one token each."""
    flaws = []
    for gate, why in PLANTED_REJECTED.items():
        if gate not in got:
            flaws.append("record %s accepted" % gate)
        elif got[gate] != why:
            flaws.append("record %s wrong-why" % gate)
    flaws += ["record %s rejected" % gate for gate in PLANTED_ACCEPTED if gate in got]
    return flaws


def _write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def details_flaw(lib):
    """What is wrong with LIB's nogo, or None (docs/adr/0038 §5)."""
    d = tempfile.mkdtemp()
    try:
        _write(d + "/with.sh", WITH_DETAILS)
        _write(d + "/without.sh", NO_DETAILS)
        good = lambda rc, out: rc == 1 and out == "NO-GO: probe — the reason\n"  # noqa: E731 - the one line
        env = dict(os.environ, PROBE_LIB=lib, NOGO_DETAILS=d + "/details")
        got = subprocess.run(["sh", d + "/with.sh"], env=env, capture_output=True, text=True, check=False)
        if not good(got.returncode, got.stdout):
            return "with details: not one contract line and exit 1"
        if _read(d + "/details") != "first detail\nsecond detail\n":
            return "NOGO_DETAILS does not hold the two detail lines"
        if "first detail" not in got.stderr.splitlines() or "second detail" not in got.stderr.splitlines():
            return "the details left stderr"
        if not good(*run(["sh", d + "/without.sh"], env=dict(env, NOGO_DETAILS=d + "/none"))):
            return "without details: not one contract line and exit 1"
        env.pop("NOGO_DETAILS")
        if not good(*run(["sh", d + "/with.sh"], env=env)):
            return "NOGO_DETAILS unset: not one contract line and exit 1"
        return None
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _listing(*dirs):
    return sorted(os.path.join(r, n) for d in dirs for r, ds, fs in os.walk(d) for n in ds + fs)


def record_flaw(lib, tree=None, recs=None):
    """What is wrong with LIB's record_check, or None (docs/adr/0062 §1-§2):
    with CI_RECORDS unset or empty it only runs the check, writing nothing;
    set, it leaves NAME.out (stdout byte for byte) and NAME.rc (the exit code);
    each way, both stdout lines reach the caller and the exit code is returned."""
    d = tempfile.mkdtemp()
    tree, recs = tree or d + "/tree", recs or d + "/records"
    try:
        os.makedirs(tree + "/ci", exist_ok=True)
        os.makedirs(recs, exist_ok=True)
        shutil.copy(lib, tree + "/ci/lib.sh")
        _write(tree + "/ci/rc-check.sh", 'printf "GO: rc-check\\nsecond line\\n"\nexit 1\n')
        _write(d + "/rc-run.sh", RC_RUN)
        want = "GO: rc-check\nsecond line\n"
        for label, value in (("unset", None), ("empty", ""), ("set", recs)):
            before = _listing(tree, recs)
            env = dict(os.environ)
            env.pop("CI_RECORDS", None)
            if value is not None:
                env["CI_RECORDS"] = value
            _, out = run(["sh", d + "/rc-run.sh", tree, d + "/rc-code"], env=env)
            if out != want or (_read(d + "/rc-code") or "").strip() != "1":
                return "CI_RECORDS %s: not both lines on stdout and return 1" % label
            if value is not None and value == recs:
                break
            if _listing(tree, recs) != before:
                return "CI_RECORDS %s: wrote something" % label
        if _read(recs + "/rc-check.out") != want:
            return "NAME.out does not hold both lines"
        if _read(recs + "/rc-check.rc") != "1\n":
            return "NAME.rc is not the line 1"
        return None
    finally:
        shutil.rmtree(d, ignore_errors=True)


def light_probes(probe, judge):
    """The light tier's entry point (docs/adr/0061): python3 -m core."""
    env = dict(os.environ, PYTHONSAFEPATH="1", PYTHONPATH=".")
    light = lambda *a, **kw: run(["python3", "-m", "core", *a], env=dict(env, **kw))  # noqa: E731
    bad = []
    rc = judge("gates-light", *light("gates", "--light"))
    rc = judge("gates-light", *light("gates", "--light", "NOT_AN_ARGUMENT=1"))
    if rc != 1:
        bad.append("gates-light(an unknown argument passed)")
    if judge("gates", *light("gates")) != 1:
        bad.append("gates(the light package printed GO: gates)")
    good = "\n".join(["# 0099 — a request", "", "## Acceptance criteria", "", "Given a number",
                      "When the caller negates it", "Then the result is the number with its sign flipped", "",
                      "## Perimeter", "", "- `calc.py`"]) + "\n"
    _write(probe + "/good-spec.md", good)
    _write(probe + "/vague-spec.md", good.replace("Then the result is the number with its sign flipped",
                                                  "Then it works correctly"))
    if judge("spec", *light("spec", probe + "/good-spec.md")) != 0:
        bad.append("spec(a testable spec was refused)")
    if judge("spec", *light("spec", probe + "/vague-spec.md")) != 1:
        bad.append("spec(a vague spec passed)")
    if judge("map", *light("map", "--repo", ".", "--out", probe + "/map.sqlite")) != 0:
        bad.append("map(this checkout's map was refused)")
    os.makedirs(probe + "/no-repo")
    if judge("map", *light("map", "--repo", probe + "/no-repo", "--out", probe + "/none.sqlite",
                           GIT_CEILING_DIRECTORIES=probe)) != 1:
        bad.append("map(a directory that is no repository passed)")
    if judge("lights-out", *light("not-a-command")) != 1:
        bad.append("lights-out(an unknown command passed)")
    return bad


def planted_run(probe, bad):
    """The record judging, on a tree of planted gates and records."""
    tree, recs = probe + "/tree", probe + "/records"
    os.makedirs(tree + "/ci/checks", exist_ok=True)
    os.makedirs(recs, exist_ok=True)
    here = os.path.dirname(os.path.abspath(__file__))
    for f in ("ci/lib.sh", "ci/contract.sh", "ci/__init__.py"):
        shutil.copy(f, tree + "/" + f)
    shutil.copy(os.path.join(here, "__init__.py"), tree + "/ci/checks/__init__.py")
    shutil.copy(os.path.abspath(__file__), tree + "/ci/checks/contract.py")
    for gate, lines in COLD_LINES.items():
        _write("%s/ci/%s.sh" % (tree, gate), "set -eu\nname=%s\n. ci/lib.sh\n%sgo\n"
               % (gate, 'echo "a second line"\n' if lines == 2 else ""))
    for gate, (out, rc) in RECORDS.items():
        _write("%s/%s.out" % (recs, gate), out)
        if rc is not None:
            _write("%s/%s.rc" % (recs, gate), rc)
    flaw = record_flaw("ci/lib.sh", tree, recs)
    if flaw:
        bad.append("contract(record_check: %s)" % flaw)
        say("contract: record_check: %s" % flaw)
    _, out = run(["sh", "ci/contract.sh"], cwd=tree, env=dict(os.environ, CI_RECORDS=recs, CONTRACT_PLANTED="1"))
    flaws = planted_flaws(rejected(out.split("\n")[0]))
    for f in flaws:
        bad.append("contract(%s)" % f)
        say("contract: planted %s" % f)
    if flaws:
        say("contract: the planted run said: %s" % out.strip())


def judge(argv):
    files, dupes = discover(".")
    if dupes:
        return "duplicate gate basename(s) across ci/gates/verify:" + "".join(" " + d for d in dupes), False
    bad = []

    def judged(gate, rc, out):
        why = shape(gate, rc, out)
        if why:
            bad.append("%s(%s)" % (gate, why))
            say("%s: %s: %s" % (gate, why, out.rstrip("\n")))
        return rc

    records = os.environ.get("CI_RECORDS", "")
    for f in files:
        gate = os.path.basename(f)[:-3]
        if f.startswith("ci/"):
            if usable(records, gate):
                judged(gate, int(_read("%s/%s.rc" % (records, gate)).strip()), _read("%s/%s.out" % (records, gate)))
                continue
            if records:
                say("%s: no usable record in %s, run cold" % (gate, records))
        judged(gate, *run(["sh", f]))

    probe = tempfile.mkdtemp()
    try:
        bad += light_probes(probe, judged)
        flaw = details_flaw("ci/lib.sh")
        if flaw:
            bad.append("lib.sh(nogo: %s)" % flaw)
            say("lib.sh: nogo: %s" % flaw)
        for name, text in BROKEN_NOGO.items():
            _write("%s/%s.sh" % (probe, name), text)
            if details_flaw("%s/%s.sh" % (probe, name)) is None:
                bad.append("contract(%s.sh accepted)" % name)
                say("contract: the nogo check accepted %s" % name)
        if not os.environ.get("CONTRACT_PLANTED"):
            planted_run(probe, bad)
    finally:
        shutil.rmtree(probe, ignore_errors=True)
    if bad:
        return "gate(s) violate the output contract:" + "".join(" " + b for b in bad), False
    return "", True


def main():
    line, ok = judge(sys.argv[1:])
    if line:
        print(line)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

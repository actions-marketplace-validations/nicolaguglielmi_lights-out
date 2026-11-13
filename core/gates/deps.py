# SPDX-License-Identifier: Apache-2.0
"""gates/deps.sh's judgement: the dependency scan on the diff (docs/adr/0015
§5 as amended by docs/adr/0032).

    python3 -m core.gates.deps <base> <head>

`osv-scanner` over every lockfile WORKLOAD_LOCKFILES names (colon-separated,
relative to WORKLOAD, docs/adr/0030 §2), each read from git at the
merge-base and at HEAD, never from the working tree. A finding is the tuple
(ecosystem, package, advisory id); only a tuple HEAD has and the base does
not is NO-GO. Advisories already in the base are inherited debt: counted
and listed on stderr every run, never gating. A lockfile absent at the base
is judged whole. Any osv-scanner exit other than 0 (clean) or 1 (findings)
is NO-GO with the tool's own error on stderr, except 128 with "No package
sources found" (osv-scanner 2.6.0 on a lockfile that lists no package, seen
2026-11-03), which is nothing to judge. $GATES_OUT/deps.json records the
lockfiles, the two counts and the verdict.
"""

import json
import os
import tempfile

from . import PIPE, NoGo, main, proc, say


def osv(files, out_path):
    """osv-scanner over FILES: (exit code, its stderr), its JSON in OUT_PATH."""
    argv = ["osv-scanner", "scan", "source", "--format", "json"]
    for f in files:
        argv += ["-L", f]
    with open(out_path, "w") as out:
        got = proc(argv, stdout=out, stderr=PIPE, text=True)
    return got.returncode, got.stderr or ""


def git(workload, *args):
    return proc(["git", "-C", workload, *args], capture_output=True)


def scan(scanner, files, out_path):
    """The scanner's findings over FILES, as a set of tuples, or NoGo."""
    if not files:
        return set()
    rc, err = scanner(files, out_path)
    if rc == 128 and "No package sources found" in err:
        say("deps: the lockfile(s) list no package; nothing to scan")
        return set()
    if rc not in (0, 1):
        say(err.rstrip("\n"))
        raise NoGo(f"osv-scanner exited {rc}; error on stderr")
    return tuples(out_path)


def jq_str(value):
    """A value as jq's string interpolation prints it."""
    return value if isinstance(value, str) else json.dumps(value)


def tuples(path):
    """{"ecosystem package id"} for every advisory in osv-scanner's JSON."""
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        raise NoGo(f"osv-scanner wrote output that cannot be read as JSON: {path}") from None
    found = set()
    for result in data.get("results") or [] if isinstance(data, dict) else []:
        for pkg in (result or {}).get("packages") or []:
            p = pkg.get("package") or {}
            for vuln in pkg.get("vulnerabilities") or []:
                found.add(f"{jq_str(p.get('ecosystem'))} {jq_str(p.get('name'))} {jq_str(vuln.get('id'))}")
    return found


def entries_of(value):
    """WORKLOAD_LOCKFILES split as `set -- $X` with IFS=: splits it."""
    if not value:
        raise NoGo("WORKLOAD_LOCKFILES is empty")
    parts = value[:-1].split(":") if value.endswith(":") else value.split(":")
    if any(p == "" for p in parts):
        raise NoGo("WORKLOAD_LOCKFILES names an empty entry")
    return parts


def judge(argv, env=None, scanner=osv):
    env = os.environ if env is None else env
    base, head = argv
    workload = env.get("WORKLOAD", ".")
    gates_out = env.get("GATES_OUT") or ".gates-out"
    os.makedirs(gates_out, exist_ok=True)
    entries = entries_of(env.get("WORKLOAD_LOCKFILES", ""))
    paths = [f"{workload}/{e}" for e in entries]
    for e, path in zip(entries, paths):
        if git(workload, "cat-file", "-e", f"{head}:./{e}").returncode != 0:
            raise NoGo(f"{path} is not tracked at {head} (from WORKLOAD_LOCKFILES)")
    say(f"deps: scanning {len(entries)} lockfile(s) at {head} and at the base {base}: {' '.join(paths)}")

    with tempfile.TemporaryDirectory() as tmp:
        sides = {"head": [], "base": []}
        for e, path in zip(entries, paths):
            for side, rev in (("head", head), ("base", base)):
                if side == "base" and git(workload, "cat-file", "-e", f"{base}:./{e}").returncode != 0:
                    say(f"deps: {path} is new at HEAD, judged whole")
                    continue
                target = os.path.join(tmp, side, e)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "wb") as fh:
                    fh.write(git(workload, "show", f"{rev}:./{e}").stdout)
                sides[side].append(target)
        at_head = scan(scanner, sides["head"], os.path.join(tmp, "head.json"))
        at_base = scan(scanner, sides["base"], os.path.join(tmp, "base.json"))

    new = sorted(at_head - at_base)
    inherited = sorted(at_head & at_base)
    if inherited:
        say(f"deps: {len(inherited)} advisory finding(s) inherited from the base, not gating (docs/adr/0032):")
        for t in inherited:
            say(f"  {t}")
    if new:
        say(f"deps: {len(new)} advisory finding(s) introduced by this diff:")
        for t in new:
            say(f"  {t}")
    record = {"lockfiles": paths, "new": len(new), "inherited": len(inherited), "verdict": "NO-GO" if new else "GO"}
    with open(os.path.join(gates_out, "deps.json"), "w") as fh:
        fh.write(json.dumps(record, separators=(",", ":")) + "\n")
    if new:
        raise NoGo(f"this diff introduces {len(new)} advisory finding(s); list on stderr")
    return None


if __name__ == "__main__":
    raise SystemExit(main(judge))

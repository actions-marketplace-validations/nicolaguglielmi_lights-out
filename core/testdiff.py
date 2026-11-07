"""What a PR does to its tests (docs/adr/0053 §1-§3): stdlib only, no process.

    python3 core/testdiff.py subject <test-globs> <prefix>             < git diff --name-only
    python3 core/testdiff.py weakening <test-globs> <prefix> [<ticket>] < git diff -M -U0

<test-globs> is the contract's WORKLOAD_TEST_PATHS: colon-separated globs
relative to the workload's root, `*` crossing `/` (fnmatch, as RISK_* and
`## Perimeter`). <prefix> is the workload's place in its repository (`git
rev-parse --show-prefix`, empty for an attached one); paths on stdin are
the repository's, as git prints them.

`subject`, for gates/test-proof.sh: exit 0 with the changed test files on
stdout, one per line, when the PR changes both tests and something else;
exit 3 with one line saying why there is nothing to prove otherwise.

`weakening`, for gates/test-weakening.sh: exit 0 with one detail line, or
exit 1 with the reason on the first line and one finding per line after
it. A finding on a file the ticket's `## Removes tests` declares is
excused and reported on stderr instead.
"""

import fnmatch
import re
import sys

USAGE = ("usage: testdiff.py subject <test-globs> <prefix> < names | "
         "weakening <test-globs> <prefix> [<ticket>] < diff")

# The patterns of docs/adr/0053 §3, with their provenance there.
PYTHON = {
    "assertion": re.compile(
        r"^\s*assert\b|\.assert[A-Z]\w*\s*\(|\.assert_\w+\s*\(|\bpytest\.(raises|warns)\s*\("),
    "test": re.compile(r"^\s*(async\s+)?def\s+test\w*\s*\(|^\s*class\s+Test\w*"),
    "skip": re.compile(
        r"\bpytest\.mark\.(skip|skipif|xfail)\b|\bpytest\.(skip|xfail|importorskip)\s*\("
        r"|\bunittest\.(skip|skipIf|skipUnless|expectedFailure)\b"
        r"|^\s*@(skip|skipIf|skipUnless|expectedFailure)\b|\.skipTest\s*\(|\bSkipTest\b"),
    "comment": ("#",),
}
JAVASCRIPT = {
    "assertion": re.compile(r"\bassert(\.\w+)?\s*\(|\bexpect\s*\("),
    "test": re.compile(r"\b(it|test)\s*\("),
    "skip": re.compile(
        r"\b(describe|suite|it|test)\.(skip|todo|only)\s*\(|\b(xit|xdescribe|xtest)\s*\("
        r"|\b(skip|todo|only)\s*:|\bt\.(skip|todo)\s*\("),
    "comment": ("//", "/*", "*"),
}
LANGUAGES = {".py": PYTHON}
LANGUAGES.update({ext: JAVASCRIPT for ext in
                  (".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx")})

# What a finding calls each loss.
LOSS = {"assertion": "assertion", "test": "test definition"}


def globs_of(spec):
    return [g for g in spec.split(":") if g]


def in_workload(path, prefix):
    """PATH relative to the workload's root, or None when it is outside it."""
    if not prefix:
        return path
    return path[len(prefix):] if path.startswith(prefix) else None


def is_test(path, globs, prefix):
    rel = in_workload(path, prefix) if path else None
    return rel is not None and any(fnmatch.fnmatchcase(rel, g) for g in globs)


def subject(names, spec, prefix):
    """(changed test files, None), or ([], why there is nothing to prove)."""
    globs = globs_of(spec)
    names = [n for n in names if n]
    tests = [n for n in names if is_test(n, globs, prefix)]
    if not tests:
        return [], "no test changed: nothing to fail on the base"
    if len(tests) == len(names):
        return [], "only test files changed: no code for them to prove"
    return tests, None


def declared(ticket_text):
    """The globs of a ticket's `## Removes tests`, in the `## Perimeter` form."""
    found, out = False, []
    for line in ticket_text.splitlines():
        if line.startswith("## "):
            found = line.rstrip() == "## Removes tests"
            continue
        if found and line.startswith("- "):
            out.append(line[2:].strip().replace("`", ""))
    return out


def files(diff_text):
    """[(old path or None, new path or None, removed lines, added lines)] per file."""
    out, cur, in_hunk = [], None, False
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            cur = {"old": None, "new": None, "removed": [], "added": []}
            out.append(cur)
            in_hunk = False
        elif cur is None:
            continue
        elif line.startswith("@@"):
            in_hunk = True
        elif in_hunk and line.startswith("-"):
            cur["removed"].append(line[1:])
        elif in_hunk and line.startswith("+"):
            cur["added"].append(line[1:])
        elif not in_hunk and line.startswith(("--- ", "+++ ", "rename from ", "rename to ")):
            key = "old" if line.startswith(("--- ", "rename from ")) else "new"
            path = line.split(" ", 2)[-1] if line.startswith("rename") else line[4:]
            if path == "/dev/null":
                continue
            if line.startswith(("--- a/", "+++ b/")):
                path = path[2:]
            cur[key] = path
    return [(f["old"], f["new"], f["removed"], f["added"]) for f in out]


def count(lines, pattern, comment):
    return sum(1 for line in lines
               if pattern.search(line) and not line.lstrip().startswith(comment))


def findings_for(old, new, removed, added, globs, prefix):
    """The findings on one changed file, or None when it is not a test file."""
    old_test, new_test = is_test(old, globs, prefix), is_test(new, globs, prefix)
    if not old_test and not new_test:
        return None
    if old_test and not new_test:
        how = "deleted" if new is None else f"renamed out of the test paths to {new}"
        return [f"{old}: test file {how}"]
    lang = LANGUAGES.get("." + new.rsplit(".", 1)[-1]) if "." in new else None
    if lang is None:
        return []
    out = []
    for kind in ("assertion", "test"):
        lost = count(removed, lang[kind], ()) - count(added, lang[kind], lang["comment"])
        if lost > 0:
            out.append(f"{new}: loses {lost} {LOSS[kind]}{'s' if lost > 1 else ''}")
    gained = count(added, lang["skip"], lang["comment"]) - count(removed, lang["skip"], ())
    if gained > 0:
        out.append(f"{new}: adds {gained} skip, xfail, todo or only marker{'s' if gained > 1 else ''}")
    return out


def weakening(diff_text, spec, prefix, excuse):
    """(findings, excused findings, a detail line for GO) for a diff."""
    globs = globs_of(spec)
    findings, excused, judged, unknown = [], [], 0, 0
    for old, new, removed, added in files(diff_text):
        found = findings_for(old, new, removed, added, globs, prefix)
        if found is None:
            continue
        judged += 1
        if new and is_test(new, globs, prefix) and "." + new.rsplit(".", 1)[-1] not in LANGUAGES:
            unknown += 1
        declared_here = any(fnmatch.fnmatchcase(p, g) for p in (old, new) if p for g in excuse)
        (excused if declared_here else findings).extend(found)
    if judged == 0:
        detail = "no test changed"
    else:
        detail = f"{judged} test file{'s' if judged > 1 else ''} changed, none weakened"
        if unknown:
            detail += f" ({unknown} with no patterns for its language: deletion checked only)"
    return findings, excused, detail


def main(argv, stdin=None):
    stdin = sys.stdin if stdin is None else stdin
    if len(argv) < 3 or argv[0] not in ("subject", "weakening"):
        print(USAGE, file=sys.stderr)
        return 2
    cmd, spec, prefix = argv[0], argv[1], argv[2]
    if cmd == "subject":
        tests, why = subject(stdin.read().splitlines(), spec, prefix)
        if why:
            print(why)
            return 3
        print("\n".join(tests))
        return 0
    excuse = []
    if len(argv) > 3 and argv[3]:
        try:
            with open(argv[3], encoding="utf-8") as f:
                excuse = declared(f.read())
        except OSError as exc:
            print(f"cannot read the ticket {argv[3]}: {exc.strerror}")
            return 1
    findings, excused, detail = weakening(stdin.read(), spec, prefix, excuse)
    for line in excused:
        print(f"test-weakening: declared by the ticket's ## Removes tests: {line}", file=sys.stderr)
    if findings:
        n = len(findings)
        print(f"{n} test file finding{'s' if n > 1 else ''} that no ## Removes tests in the ticket "
              f"declares: {findings[0]}{' and more' if n > 1 else ''}; details on stderr")
        print("\n".join(findings))
        return 1
    print(detail)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

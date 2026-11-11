"""Which tests a mutant runs (docs/adr/0075), for mutation.sh.

    python select.py map <package> <coverage dir> <out dir>
        After the clean run, with the runners' interpreter (coverage.py):
        combines the per-process data in <coverage dir> into <out dir>/map.json,
        each statement of the package's files with the tests that executed
        it ("*" when it ran outside any test), and copies the package's .py
        files to <out dir>/pristine. Exit 3, nothing written, when no test
        context was recorded: coverage cannot say.

    python3 select.py run
        cosmic-ray's test command. LIGHTS_OUT_SELECT_DIR is <out dir>,
        <out dir>/command the repository's test command. Finds the mutated
        file and lines against the pristine copy, from the current
        directory (a shard's tree or the repository), and executes the test
        command: whole, with the selected tests only, or not at all (exit 0,
        the mutant survives) when no test executed its statement. Appends
        "none", "some" or "all" to <out dir>/runs for the runner's tally.
"""

import ast
import difflib
import hashlib
import json
import os
import shlex
import shutil
import sys

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hook")
OUTSIDE = "-"


def statements(source):
    """Line -> the line that opens its statement group: the innermost
    ast.stmt holding it; a compound statement keeps its header lines
    (decorators, `def`, `if`, `else:`), its bodies belong to theirs."""
    owner = {}
    for node in ast.walk(ast.parse(source)):  # parents before children
        if isinstance(node, ast.stmt):
            first = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
            for line in range(first, node.end_lineno + 1):
                owner[line] = first
    return owner


def package_files(package):
    for top, dirs, files in os.walk(package):
        dirs.sort()
        for name in sorted(files):
            if name.endswith(".py"):
                yield os.path.join(top, name)


def build(package, data_dir, out):
    import coverage

    cov = coverage.Coverage(data_file=os.path.join(data_dir, "cov"), config_file=False)
    cov.set_option("run:disable_warnings", ["no-data-collected"])
    try:
        cov.combine([data_dir], keep=True)
    except coverage.exceptions.NoDataError:
        return 3
    data = cov.get_data()
    cwd = os.getcwd()
    measured = {}
    for path in data.measured_files():
        rel = os.path.relpath(path, cwd)
        if not rel.startswith(".."):
            measured[rel] = data.contexts_by_lineno(path)
    tests = sorted({c for lines in measured.values() for cs in lines.values() for c in cs}
                   - {OUTSIDE, ""})
    if not tests:
        return 3
    index = {t: i for i, t in enumerate(tests)}
    files = {}
    for rel in package_files(package):
        with open(rel, encoding="utf-8") as f:
            owner = statements(f.read())
        groups = {}
        for line, contexts in measured.get(rel, {}).items():
            first = owner.get(line)
            if first is None:
                continue
            group = groups.setdefault(first, set())
            for c in contexts:
                group.add("*" if c in (OUTSIDE, "") else index[c])
        files[rel] = {
            "owner": {str(line): first for line, first in owner.items()},
            "groups": {str(first): ("*" if "*" in g else sorted(g)) for first, g in groups.items()},
        }
        os.makedirs(os.path.dirname(os.path.join(out, "pristine", rel)), exist_ok=True)
        shutil.copyfile(rel, os.path.join(out, "pristine", rel))
    with open(os.path.join(out, "map.json"), "w", encoding="utf-8") as f:
        json.dump({"tests": tests, "files": files}, f)
    return 0


def changed_lines(before, after):
    lines = set()
    matcher = difflib.SequenceMatcher(None, before.splitlines(), after.splitlines(), autojunk=False)
    for tag, i1, i2, _, _ in matcher.get_opcodes():
        if tag != "equal":
            lines.update(range(i1 + 1, max(i2, i1 + 1) + 1))
    return lines


def choose(selection):
    """(mutated, tests): tests None for the whole suite, [] for no test."""
    with open(os.path.join(selection, "map.json"), encoding="utf-8") as f:
        index = json.load(f)
    mutated = False
    chosen = set()
    for rel, entry in index["files"].items():
        with open(os.path.join(selection, "pristine", rel), encoding="utf-8") as f:
            before = f.read()
        with open(rel, encoding="utf-8") as f:
            after = f.read()
        if before == after:
            continue
        mutated = True
        for line in changed_lines(before, after):
            first = entry["owner"].get(str(line))
            if first is None:
                return True, None
            group = entry["groups"].get(str(first), [])
            if group == "*":
                return True, None
            chosen.update(group)
    if not mutated:
        return False, None
    return True, sorted(index["tests"][i] for i in chosen)


def run():
    selection = os.environ["LIGHTS_OUT_SELECT_DIR"]
    with open(os.path.join(selection, "command"), encoding="utf-8") as f:
        argv = shlex.split(f.read())
    mutated, tests = choose(selection)
    env = dict(os.environ)
    if tests is None:
        tally = "all"
    elif not tests:
        tally = "none"
    else:
        tally = "some"
        body = "\n".join(tests) + "\n"
        listing = os.path.join(selection, "select-" + hashlib.sha256(body.encode()).hexdigest()[:16])
        if not os.path.exists(listing):
            with open(listing + f".{os.getpid()}", "w", encoding="utf-8") as f:
                f.write(body)
            os.replace(listing + f".{os.getpid()}", listing)
        env["LIGHTS_OUT_SELECT"] = listing
        path = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = HOOK + (os.pathsep + path if path else "")
    if mutated:
        with open(os.path.join(selection, "runs"), "a", encoding="utf-8") as f:
            f.write(tally + "\n")
    if tally == "none":
        print("lights-out: no test executes the mutated statement; nothing to run", file=sys.stderr)
        return 0
    sys.stdout.flush()
    os.execvpe(argv[0], argv, env)
    return 1


def main(argv):
    if argv[1:2] == ["map"] and len(argv) == 5:
        return build(*argv[2:5])
    if argv[1:] == ["run"]:
        return run()
    print("usage: select.py map <package> <coverage dir> <out dir> | select.py run", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

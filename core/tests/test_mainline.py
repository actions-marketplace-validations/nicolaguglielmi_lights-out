"""Tests for the pure part of core/mainline.py, written from docs/adr/0056
§1, §3 and §4 and from core/perimeter.sh's parsing rule (the ADR says to
match it), never from the implementation.

The first half is the pure rules: the ticket's perimeter, the match of a
path against it, the overlap of the commits main gained with it, the size
of a group, and the bisection's culprit and its cost.

The second half is ADR 0056 §7's cases, in process: `mainline.main` run
against a temp root that holds stub adapter verbs (a CodeHost backed by a
bare repository, a Tracker, a file-backed StateStore) and a stub workload
whose `gates` target is a script. They sit here and not only in
ci/mainline.sh because the self gate (ADR 0049) measures core/ with this
suite alone. ci/mainline.sh runs the real step scripts for the headline
cases.
"""

import contextlib
import io
import json
import os
import re
import subprocess  # nosec B404 - git and sh, argv lists only
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import mainline

POLICY = Path(__file__).resolve().parents[2] / "policy" / "mainline.env"

TICKET = """# 0021 - a ticket

## Goal

- an item that is not in the perimeter

## Perimeter

- `svc/backend/store/db.py`
- `docs/*`
-   tests/test_db.py

## Notes

- an item after the section, not in the perimeter
"""


def ceil_log2(n):
    """ceil(log2 n) for n >= 1, exact on integers: (n - 1).bit_length()."""
    return (n - 1).bit_length()


class Perimeter(unittest.TestCase):
    """The list items of `## Perimeter`, as core/perimeter.sh reads them."""

    def test_the_items_of_the_section_with_backticks_dropped_and_spaces_trimmed(self):
        self.assertEqual(mainline.perimeter(TICKET),
                         ["svc/backend/store/db.py", "docs/*", "tests/test_db.py"])

    def test_the_order_of_the_ticket_is_kept(self):
        text = "## Perimeter\n\n- `z.py`\n- `a.py`\n- `m.py`\n"
        self.assertEqual(mainline.perimeter(text), ["z.py", "a.py", "m.py"])

    def test_items_outside_the_section_are_not_in_it(self):
        text = "- before\n\n## Perimeter\n\n- `inside.py`\n\n## Later\n\n- after\n"
        self.assertEqual(mainline.perimeter(text), ["inside.py"])

    def test_the_section_may_be_the_last_without_a_final_newline(self):
        self.assertEqual(mainline.perimeter("## Perimeter\n\n- `a.py`\n- `b/*`"), ["a.py", "b/*"])

    def test_only_dash_space_lines_are_items(self):
        text = ("## Perimeter\n\n* `star.py`\n  - `indented.py`\n-`nospace.py`\n"
                "prose about the perimeter\n- `real.py`\n")
        self.assertEqual(mainline.perimeter(text), ["real.py"])

    def test_a_deeper_heading_does_not_end_the_section(self):
        # core/perimeter.sh stops at /^## /: three hashes are not that.
        text = "## Perimeter\n\n- `a.py`\n\n### Detail\n\n- `b.py`\n\n## End\n\n- `c.py`\n"
        self.assertEqual(mainline.perimeter(text), ["a.py", "b.py"])

    def test_a_ticket_without_the_section_has_an_empty_perimeter(self):
        self.assertEqual(mainline.perimeter("# 0001 - t\n\n## Context\n\n- `a.py`\n"), [])
        self.assertEqual(mainline.perimeter(""), [])

    def test_the_result_is_a_list_of_strings(self):
        got = mainline.perimeter(TICKET)
        self.assertIsInstance(got, list)
        self.assertTrue(all(isinstance(g, str) for g in got))


class InPerimeter(unittest.TestCase):
    """fnmatch.fnmatchcase on any glob; `*` crosses `/` (ADR 0056 §1)."""

    def test_an_exact_path(self):
        self.assertTrue(mainline.in_perimeter("svc/db.py", ["svc/db.py"]))

    def test_star_crosses_slashes(self):
        self.assertTrue(mainline.in_perimeter("svc/backend/store/db.py", ["svc/*"]))
        self.assertTrue(mainline.in_perimeter("a/b/c/d.py", ["*.py"]))
        self.assertTrue(mainline.in_perimeter("docs/guide/deep/intro.txt", ["docs/*"]))

    def test_any_glob_of_the_list_is_enough(self):
        self.assertTrue(mainline.in_perimeter("docs/a.md", ["src/*", "docs/*"]))
        self.assertTrue(mainline.in_perimeter("src/a.py", ["src/*", "docs/*"]))

    def test_a_path_matching_no_glob_is_outside(self):
        self.assertFalse(mainline.in_perimeter("tests/a.py", ["src/*", "docs/*"]))
        self.assertFalse(mainline.in_perimeter("svc/db.py.bak", ["svc/db.py"]))

    def test_a_directory_name_is_not_a_prefix(self):
        # A glob without a wildcard names a path, not a directory.
        self.assertFalse(mainline.in_perimeter("docs/a.md", ["docs"]))
        self.assertFalse(mainline.in_perimeter("docs/a.md", ["docs/"]))

    def test_the_match_is_case_sensitive(self):
        self.assertFalse(mainline.in_perimeter("svc/db.py", ["Svc/*"]))
        self.assertFalse(mainline.in_perimeter("SVC/DB.PY", ["svc/db.py"]))

    def test_an_empty_perimeter_holds_nothing(self):
        self.assertFalse(mainline.in_perimeter("a.py", []))

    def test_the_answer_is_a_bool(self):
        self.assertIs(mainline.in_perimeter("a.py", ["a.py"]), True)
        self.assertIs(mainline.in_perimeter("b.py", ["a.py"]), False)


class Overlaps(unittest.TestCase):
    """Every (commit, path) of what main gained that lies in the perimeter."""

    GLOBS = ["src/a.txt", "docs/*"]

    def test_no_commit_touched_the_perimeter(self):
        moved = [("c1", ["src/b.txt"]), ("c2", ["README.md", "src/c.txt"])]
        self.assertEqual(mainline.overlaps(self.GLOBS, moved), [])

    def test_nothing_moved(self):
        self.assertEqual(mainline.overlaps(self.GLOBS, []), [])

    def test_an_empty_perimeter_overlaps_nothing(self):
        self.assertEqual(mainline.overlaps([], [("c1", ["src/a.txt"])]), [])

    def test_one_commit_one_path(self):
        self.assertEqual(mainline.overlaps(self.GLOBS, [("c1", ["src/a.txt"])]),
                         [("c1", "src/a.txt")])

    def test_only_the_paths_in_the_perimeter_are_reported(self):
        moved = [("c1", ["src/other.txt", "src/a.txt", "x/y.txt", "docs/deep/er/z.md"])]
        self.assertEqual(mainline.overlaps(self.GLOBS, moved),
                         [("c1", "src/a.txt"), ("c1", "docs/deep/er/z.md")])

    def test_oldest_commit_first_and_the_paths_in_the_order_given(self):
        moved = [("c1", ["docs/b.md", "docs/a.md"]), ("c2", ["src/b.txt"]), ("c3", ["src/a.txt"])]
        self.assertEqual(mainline.overlaps(self.GLOBS, moved),
                         [("c1", "docs/b.md"), ("c1", "docs/a.md"), ("c3", "src/a.txt")])

    def test_touched_and_then_reverted_still_counts(self):
        # The input is per commit, so a change a later commit undid is two
        # entries: ADR 0056 §1 reads what each commit touched, not the net diff.
        moved = [("c1", ["src/a.txt"]), ("c2", ["src/a.txt"])]
        self.assertEqual(mainline.overlaps(self.GLOBS, moved),
                         [("c1", "src/a.txt"), ("c2", "src/a.txt")])

    def test_the_same_path_in_two_commits_is_two_overlaps(self):
        moved = [("c1", ["docs/a.md"]), ("c2", ["docs/a.md"]), ("c3", ["docs/a.md"])]
        self.assertEqual(len(mainline.overlaps(self.GLOBS, moved)), 3)

    def test_a_commit_with_no_paths_is_no_overlap(self):
        self.assertEqual(mainline.overlaps(self.GLOBS, [("c1", []), ("c2", ["src/a.txt"])]),
                         [("c2", "src/a.txt")])

    def test_the_result_is_a_list_of_pairs(self):
        got = mainline.overlaps(self.GLOBS, [("c1", ["src/a.txt"])])
        self.assertIsInstance(got, list)
        self.assertIsInstance(got[0], tuple)

    def test_the_inputs_are_left_alone(self):
        globs = list(self.GLOBS)
        moved = [("c1", ["src/a.txt", "x"])]
        mainline.overlaps(globs, moved)
        self.assertEqual(globs, self.GLOBS)
        self.assertEqual(moved, [("c1", ["src/a.txt", "x"])])


class Group(unittest.TestCase):
    """At most MAINLINE_GROUP_MAX commits at a time, the oldest first (§3)."""

    def test_the_limit_in_the_policy_is_four(self):
        text = POLICY.read_text(encoding="utf-8")
        values = re.findall(r"^MAINLINE_GROUP_MAX=[\"']?(\d+)[\"']?\s*$", text, re.M)
        self.assertEqual(values, ["4"], f"{POLICY} must set MAINLINE_GROUP_MAX=4 exactly once")

    def test_a_long_list_is_cut_to_the_limit_keeping_the_oldest(self):
        self.assertEqual(mainline.group(["c1", "c2", "c3", "c4", "c5", "c6"], 4),
                         ["c1", "c2", "c3", "c4"])

    def test_a_list_within_the_limit_is_whole(self):
        self.assertEqual(mainline.group(["c1", "c2"], 4), ["c1", "c2"])
        self.assertEqual(mainline.group(["c1", "c2", "c3", "c4"], 4), ["c1", "c2", "c3", "c4"])

    def test_nothing_after_the_green_is_an_empty_group(self):
        self.assertEqual(mainline.group([], 4), [])

    def test_a_limit_of_one(self):
        self.assertEqual(mainline.group(["c1", "c2"], 1), ["c1"])

    def test_the_input_is_left_alone(self):
        commits = ["c1", "c2", "c3"]
        mainline.group(commits, 2)
        self.assertEqual(commits, ["c1", "c2", "c3"])

    def test_taking_groups_in_turn_covers_every_commit_once_in_order(self):
        commits = [f"c{i}" for i in range(1, 12)]
        rest, seen = list(commits), []
        while rest:
            taken = mainline.group(rest, 4)
            self.assertLessEqual(len(taken), 4)
            seen += taken
            rest = rest[len(taken):]
        self.assertEqual(seen, commits)


class FirstRed(unittest.TestCase):
    """The first red commit of a group whose newest commit is known red (§4)."""

    def commits(self, n):
        return [f"{i:040x}" for i in range(1, n + 1)]

    def bisect(self, n, culprit):
        """first_red over n commits where commits[culprit:] are red; (answer, asked)."""
        commits = self.commits(n)
        asked = []

        def is_green(commit):
            self.assertIn(commit, commits[:-1], "is_green was given a commit that is not a candidate")
            asked.append(commit)
            return commits.index(commit) < culprit

        return mainline.first_red(commits, is_green), commits, asked

    def test_the_culprit_at_every_position_of_every_length(self):
        for n in range(1, 34):
            for culprit in range(n):
                with self.subTest(n=n, culprit=culprit):
                    got, commits, asked = self.bisect(n, culprit)
                    self.assertEqual(got, commits[culprit])
                    self.assertLessEqual(len(asked), ceil_log2(n),
                                         f"{len(asked)} runs for {n} commits, at most {ceil_log2(n)} allowed")

    def test_the_lengths_the_group_limit_allows(self):
        # ADR 0056 §3: a group of four is bisected in at most two runs.
        for culprit in range(4):
            with self.subTest(culprit=culprit):
                _, _, asked = self.bisect(4, culprit)
                self.assertLessEqual(len(asked), 2)

    def test_a_single_commit_is_the_culprit_without_a_run(self):
        got, commits, asked = self.bisect(1, 0)
        self.assertEqual(got, commits[0])
        self.assertEqual(asked, [])

    def test_the_newest_commit_is_never_judged_again(self):
        # It is the one known red: a run on it is a wasted gate run.
        for n in range(1, 17):
            for culprit in range(n):
                with self.subTest(n=n, culprit=culprit):
                    _, commits, asked = self.bisect(n, culprit)
                    self.assertNotIn(commits[-1], asked)

    def test_a_commit_is_not_judged_twice(self):
        for n in range(2, 17):
            for culprit in range(n):
                with self.subTest(n=n, culprit=culprit):
                    _, _, asked = self.bisect(n, culprit)
                    self.assertEqual(len(asked), len(set(asked)))

    def test_a_long_group_still_costs_a_logarithm(self):
        for n, culprit in ((100, 0), (100, 57), (100, 99), (1000, 500)):
            with self.subTest(n=n, culprit=culprit):
                got, commits, asked = self.bisect(n, culprit)
                self.assertEqual(got, commits[culprit])
                self.assertLessEqual(len(asked), ceil_log2(n))

    def test_the_answer_is_one_of_the_commits_given(self):
        got, commits, _ = self.bisect(5, 3)
        self.assertIn(got, commits)

    def test_the_input_is_left_alone(self):
        commits = self.commits(6)
        before = list(commits)
        mainline.first_red(commits, lambda c: commits.index(c) < 2)
        self.assertEqual(commits, before)


# --- ADR 0056 §7, in process: the stub world ---------------------------------
#
# A temp root is the tower's checkout (the cwd, as for the real steps):
# adapters/stub-*/ hold the verbs core/mainline.py calls, host.git is the
# code host's repository, work/ is the workload's clone where the tower
# judges, author/ is where tickets and people write their commits. The
# workload is a repository whose `gates` target is a script: a tree is red
# when a `call NAME` line under src/ has no `def NAME` line. So two diffs
# that each pass alone can fail together (one renames what the other starts
# calling), and the verdict is a function of the tree, never of a sha.

SH_HERE = 'set -eu\nd=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)\n'

STUBS = {
    "adapters/stub-state/get.sh": SH_HERE + 'f="$d/state/$1.$2.json"\n[ -f "$f" ] || exit 1\ncat "$f"\n',
    "adapters/stub-state/put.sh": SH_HERE + 'cat > "$d/state/$1.$2.json"\n',
    "adapters/stub-tracker/get.sh": SH_HERE + 'f="$d/tickets/$1.md"\n[ -f "$f" ] || exit 1\ncat "$f"\n',
    "adapters/stub-codehost/clone-url.sh": SH_HERE + 'printf \'%s\\n\' "$d/host.git"\n',
    # What the reference CodeHost verbs do: push forces HEAD to the branch; open-pr
    # refuses a pr.json with no title and prints "<number> <url>"; merge
    # makes a merge commit while the PR's head is the one given, and prints
    # "<merge sha> <head sha>" again for a PR already merged.
    "adapters/stub-codehost/push.sh": SH_HERE + 'git -C "$1" push -q --force "$d/host.git" "HEAD:refs/heads/$2" >&2\n',
    "adapters/stub-codehost/open-pr.sh": SH_HERE + r"""[ -s "$2" ] || { printf 'stub-codehost: %s is missing or empty\n' "$2" >&2; exit 1; }
python3 -I -c 'import json, sys; sys.exit(0 if json.load(open(sys.argv[1])).get("title") else 1)' "$2" \
  || { printf 'stub-codehost: %s has no title\n' "$2" >&2; exit 1; }
tip=$(git -C "$d/host.git" rev-parse --verify -q "refs/heads/$1") \
  || { printf 'stub-codehost: no branch %s\n' "$1" >&2; exit 1; }
n=$(cat "$d/world/.seq" 2>/dev/null || printf 100)
n=$((n + 1))
printf '%s' "$n" > "$d/world/.seq"
mkdir -p "$d/world/pr-$n"
printf '%s\n' "$1" > "$d/world/pr-$n/branch"
printf '%s\n' "$tip" > "$d/world/pr-$n/head"
cp "$2" "$d/world/pr-$n/pr.json"
printf '%s stub://pr/%s\n' "$n" "$n"
""",
    "adapters/stub-codehost/merge.sh": SH_HERE + r"""p="$d/world/pr-$1"
[ -d "$p" ] || { printf 'stub-codehost: no PR #%s\n' "$1" >&2; exit 1; }
if [ ! -f "$p/merge_sha" ]; then
  branch=$(cat "$p/branch")
  tip=$(git -C "$d/host.git" rev-parse "refs/heads/$branch")
  [ "$tip" = "$2" ] || { printf 'stub-codehost: PR #%s head is %s, not %s\n' "$1" "$tip" "$2" >&2; exit 1; }
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  git clone -q "$d/host.git" "$tmp/m" 2>/dev/null
  git -C "$tmp/m" -c user.name=host -c user.email=host@lights-out.invalid -c commit.gpgsign=false \
    merge -q --no-ff -m "Merge PR #$1" "origin/$branch" >/dev/null 2>&1 \
    || { printf 'stub-codehost: PR #%s does not merge\n' "$1" >&2; exit 1; }
  git -C "$tmp/m" push -q origin HEAD:refs/heads/main 2>/dev/null
  git -C "$tmp/m" rev-parse HEAD > "$p/merge_sha"
fi
printf '%s %s\n' "$(cat "$p/merge_sha")" "$(cat "$p/head")"
""",
}

# The stub judge. It logs every run (BASE HEAD GATES) to $RUNS_LOG, outside
# any repository, so a gate that did not run leaves no line.
GATES_RUN = r"""set -eu
base=$1 head=$2 gates=$3 out=$4
mkdir -p "$out"
printf '%s %s %s\n' "$base" "$head" "$gates" >> "$RUNS_LOG"
defs=$(cat src/*.txt | sed -n 's/^def //p' | tr '\n' ' ')
bad=""
: > "$out/test.details"
for name in $(cat src/*.txt | sed -n 's/^call //p'); do
  case " $defs " in
    *" $name "*) ;;
    *) bad="$bad $name"; printf 'undefined call: %s\n' "$name" >> "$out/test.details" ;;
  esac
done
if [ -n "$bad" ]; then
  # The verdict is verdict.env's, as the tower reads it; the exit code is left 0 so that
  # make has nothing to complain about on stderr.
  printf 'GATES=NO-GO\nFAILED=test\n' > "$out/verdict.env"
  printf 'NO-GO: gates — test: undefined call(s)%s in %s\n' "$bad" "$head"
  exit 0
fi
printf 'GATES=GO\n' > "$out/verdict.env"
printf 'GO: gates\n'
"""

REPO = {
    "Makefile": ('GATES ?= sast test\nGATES_OUT ?= .gates-out\n.PHONY: gates\n'
                 'gates: ; @sh gates/run.sh "$(BASE)" "$(HEAD)" "$(GATES)" "$(GATES_OUT)"\n'),
    "gates/run.sh": GATES_RUN,
    "src/lib.txt": "def foo\n",
    "src/use.txt": "# callers\n",
    **{f"src/{name}.txt": "".join(f"{name}{i}\n" for i in range(1, 6)) for name in "abcde"},
    "docs/notes.txt": "notes\n",
}

# A commit that loosens the judge: the Makefile and the gate both say GO.
WEAK_MAKEFILE = (".PHONY: gates\n"
                 'gates: ; @mkdir -p "$(GATES_OUT)" && printf \'GATES=GO\\n\' > "$(GATES_OUT)/verdict.env"'
                 " && printf 'GO: gates\\n'\n")

# Nothing of the user's or the machine's git configuration reaches a test, and
# no identity is guessed: a commit the tower makes must name its own author.
GIT_ISOLATION = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
                 "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "user.useConfigOnly", "GIT_CONFIG_VALUE_0": "true"}
GIT_STRAY = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
             "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "EMAIL")
AUTHOR = ["-c", "user.name=author", "-c", "user.email=author@lights-out.invalid", "-c", "commit.gpgsign=false"]

_template = None
_environ = None


def git(*args, cwd, ident=False, check=True):
    cmd = ["git", *(AUTHOR if ident else []), *args]
    got = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)  # nosec B603 B607
    if check and got.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {cwd}: {got.stderr.strip()}")
    return got


def setUpModule():
    """The repository every world starts from, built once: a root commit and the base on top of it."""
    global _template, _environ
    _template = tempfile.TemporaryDirectory()
    root = Path(_template.name).resolve()
    (root / "home").mkdir()
    _environ = mock.patch.dict(os.environ, {**GIT_ISOLATION, "HOME": str(root / "home")})
    _environ.start()
    for var in GIT_STRAY:
        os.environ.pop(var, None)
    src = root / "src"
    src.mkdir()
    for rel, body in REPO.items():
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_text(body, encoding="utf-8")
    git("init", "-q", "-b", "main", cwd=src)
    git("add", "-A", cwd=src)
    git("commit", "-q", "-m", "initial", cwd=src, ident=True)
    with (src / "docs" / "notes.txt").open("a", encoding="utf-8") as notes:
        notes.write("base\n")
    git("commit", "-q", "-a", "-m", "base", cwd=src, ident=True)
    git("clone", "-q", "--bare", "src", "host.git", cwd=root)


def tearDownModule():
    _environ.stop()
    _template.cleanup()


class WorldCase(unittest.TestCase):
    """A fresh world per test: the host at the base, an author's clone, the workload's clone."""

    limit = 4

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(os.chdir, os.getcwd())  # registered second, so it runs first
        self.root = Path(tmp.name).resolve()
        os.chdir(self.root)
        env = mock.patch.dict(os.environ, {"RUNS_LOG": str(self.root / "runs.log")})
        env.start()
        self.addCleanup(env.stop)
        for rel, body in STUBS.items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(body, encoding="utf-8")
        for name in ("state", "world", "tickets", "docs", "policy"):
            (self.root / name).mkdir()
        (self.root / "policy" / "mainline.env").write_text(f"MAINLINE_GROUP_MAX={self.limit}\n", encoding="utf-8")
        (self.root / "runs.log").write_text("")
        shutil.copytree(Path(_template.name) / "host.git", self.root / "host.git")
        git("clone", "-q", "host.git", "author", cwd=self.root)
        git("clone", "-q", "host.git", "work", cwd=self.root)
        self.author = self.root / "author"
        self.ports = {"CODE_HOST": "stub-codehost", "TRACKER": "stub-tracker", "STATE_STORE": "stub-state",
                      "WORKLOAD": "work", "WORKLOAD_CONTRACT": "work", "WORKLOAD_ATTACHED": ""}
        self.docs = {}
        self.stderr = ""
        self.base = self.main()

    # -- the code host and the author

    def host(self, *args, check=True):
        return git(*args, cwd=self.root / "host.git", check=check)

    def ref(self, name):
        return self.host("rev-parse", "--verify", "-q", name, check=False).stdout.strip()

    def main(self):
        return self.ref("refs/heads/main")

    def anc(self, older, newer):
        return self.host("merge-base", "--is-ancestor", older, newer, check=False).returncode == 0

    def main_file(self, rel):
        got = self.host("show", f"refs/heads/main:{rel}", check=False)
        return got.stdout if got.returncode == 0 else None

    def au(self, *args):
        return git(*args, cwd=self.author, ident=True).stdout.strip()

    def sync(self):
        self.au("fetch", "-q", "origin")
        self.au("checkout", "-q", "-f", "-B", "main", "origin/main")

    def append(self, rel, line):
        path = self.author / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as out:
            out.write(line + "\n")

    def replace(self, rel, old, new):
        path = self.author / rel
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def edit_first(self, rel, line):
        path = self.author / rel
        rest = path.read_text(encoding="utf-8").splitlines()[1:]
        path.write_text("\n".join([line, *rest]) + "\n", encoding="utf-8")

    def remove_line(self, rel, line):
        path = self.author / rel
        kept = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln != line]
        path.write_text("".join(ln + "\n" for ln in kept), encoding="utf-8")

    def rename_foo(self):
        self.replace("src/lib.txt", "def foo", "def bar")

    def outside(self, edit):
        """A commit on main made by a person, with no ticket and no PR; its sha."""
        self.sync()
        edit()
        self.au("add", "-A")
        self.au("commit", "-q", "--allow-empty", "-m", "outside")
        self.au("push", "-q", "origin", "HEAD:refs/heads/main")
        return self.main()

    def byhand_revert(self, rev, merge=False):
        self.sync()
        self.au("revert", "--no-edit", *(["-m", "1"] if merge else []), rev)
        self.au("push", "-q", "origin", "HEAD:refs/heads/main")
        return self.main()

    def rewrite_main(self):
        """Main's last commit amended and force-pushed: the base a PR was judged on is gone."""
        self.sync()
        self.au("commit", "-q", "--amend", "--allow-empty", "-m", "history rewritten")
        self.au("push", "-q", "-f", "origin", "HEAD:refs/heads/main")

    def revert_branches(self):
        got = self.host("for-each-ref", "--format=%(refname:short)", "refs/heads/revert")
        return got.stdout.split()

    def revert_prs(self):
        found = []
        for pr in sorted((self.root / "world").glob("pr-*")):
            number = int(pr.name.split("-")[1])
            if number >= 100:
                data = json.loads((pr / "pr.json").read_text(encoding="utf-8"))
                found.append({"number": number, "branch": (pr / "branch").read_text().strip(),
                              "title": data.get("title"), "body": data.get("body", ""),
                              "merged": (pr / "merge_sha").exists()})
        return found

    def pr_merged(self, number):
        return (self.root / "world" / f"pr-{number}" / "merge_sha").exists()

    def runs(self):
        """Every gate run so far, as (BASE, HEAD, GATES)."""
        return [tuple(line.split(" ", 2)) for line in (self.root / "runs.log").read_text().splitlines()]

    def mainline_doc(self):
        path = self.root / "state" / "mainline.main.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    # -- tickets

    def propose(self, n, path, edit, base=None, perimeter=None):
        """Ticket n declares `perimeter` (default: path); its PR is two commits off `base`,
        the second touching `path` again; CI has passed it. Returns the PR's head."""
        tid, base = f"{n:04d}", base or self.base
        self.au("checkout", "-q", "-f", "-B", f"ticket/{tid}", base)
        edit()
        self.au("add", "-A")
        self.au("commit", "-q", "-m", f"ticket {tid}")
        self.append(path, f"# {tid} follow-up")
        self.au("commit", "-q", "-a", "-m", f"ticket {tid}: follow-up")
        self.au("push", "-q", "-f", "origin", f"HEAD:refs/heads/ticket/{tid}")
        head = self.au("rev-parse", "HEAD")
        globs = perimeter or [path]
        (self.root / "tickets" / f"{tid}.md").write_text(
            f"# {tid} - stub ticket\n\n## Perimeter\n\n" + "".join(f"- `{g}`\n" for g in globs), encoding="utf-8")
        pr = self.root / "world" / f"pr-{n}"
        pr.mkdir()
        (pr / "branch").write_text(f"ticket/{tid}\n")
        (pr / "head").write_text(f"{head}\n")
        self.docs[n] = {"id": tid, "state": "ci-passed", "attempt": 1, "history": [],
                        "pr": {"number": n, "base_sha": base, "head_sha": head},
                        "ci": {"verdict": "GO", "risk_level": "low", "decision": "auto-merge", "head_sha": head}}
        self.save(n)
        return head

    def simple(self, n, name):
        """A ticket that appends a line to src/<name>.txt."""
        return (n, f"src/{name}.txt", lambda: self.append(f"src/{name}.txt", f"{name}6"))

    def save(self, n):
        (self.root / "docs" / f"{n:04d}.json").write_text(json.dumps(self.docs[n]), encoding="utf-8")

    def apply(self, n, result):
        """What the tower does with a step's JSON: the state and the fields it printed."""
        self.docs[n]["state"] = result["state"]
        if "mainline" in result:
            self.docs[n]["mainline"] = result["mainline"]
        self.save(n)

    def step_env(self, n):
        return {**self.ports, "TICKET": f"{n:04d}", "DOC_FILE": str(self.root / "docs" / f"{n:04d}.json")}

    def run_main(self, argv, env):
        """(exit code, the one JSON object on stdout or None); stderr is kept in self.stderr."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = mainline.main(argv, env)
        self.stderr = err.getvalue()
        printed = out.getvalue()
        if not printed.strip():
            return rc, None
        self.assertEqual(len(printed.splitlines()), 1, f"stdout is the step's one JSON line: {printed!r}")
        return rc, json.loads(printed)

    def rejudge(self, n):
        return self.run_main(["rejudge"], self.step_env(n))

    def check(self, n):
        rc, got = self.run_main(["check"], self.step_env(n))
        if rc == 0 and got is not None:
            self.apply(n, got)
        return rc, got

    def merge(self, n):
        """core/steps/merge.sh: the re-judge rule, then the adapter's merge. The rework JSON, or None when merged."""
        rc, result = self.rejudge(n)
        self.assertEqual(rc, 0, f"the re-judge failed: {self.stderr}")
        if result is not None:
            self.apply(n, result)
            return result
        doc = self.docs[n]
        got = subprocess.run(["sh", "adapters/stub-codehost/merge.sh", str(n), doc["ci"]["head_sha"]],
                             capture_output=True, text=True, check=False)  # nosec B603 B607
        self.assertEqual(got.returncode, 0, got.stderr)
        sha, head = got.stdout.split()
        doc.update(state="merged", merge={"sha": sha, "head_sha": head})
        self.save(n)
        return None

    def merge_all(self, specs):
        """specs: (n, path, edit); each proposed off the base, then merged in order. {n: merge sha}."""
        for n, path, edit in specs:
            self.propose(n, path, edit)
        shas = {}
        for n, _, _ in specs:
            self.assertIsNone(self.merge(n))
            shas[n] = self.docs[n]["merge"]["sha"]
        return shas

    def assert_main_green(self, n, got, exactly=None):
        """main-green carries the green commit the ticket's merge is in, and that is what releases."""
        self.assertEqual(got["state"], "main-green")
        green = got["mainline"]["green"]
        self.assertTrue(self.anc(self.docs[n]["merge"]["sha"], green), "the green commit holds the ticket's merge")
        self.assertTrue(self.anc(green, self.main()), "the green commit is on main")
        if exactly is not None:
            self.assertEqual(green, exactly)


class Rejudge(WorldCase):
    """ADR 0056 §1: the PR merges without its gates again unless main moved under its perimeter."""

    def assert_base_line(self, line, base, path, commit):
        self.assertRegex(line, "^" + re.escape("NO-GO: base — main moved under the perimeter since ")
                         + re.escape(base[:7]) + "[0-9a-f]*" + re.escape(f": {path} by ") + re.escape(commit[:7])
                         + "[0-9a-f]*$")

    def test_a_move_outside_the_perimeter_merges_with_no_gate_run(self):
        self.propose(1, "src/a.txt", lambda: self.append("src/a.txt", "a6"))
        self.propose(2, "src/b.txt", lambda: self.append("src/b.txt", "b6"))
        # Base unmoved: the first ticket merges.
        self.assertEqual(self.rejudge(1), (0, None))
        self.assertIsNone(self.merge(1))
        self.assertEqual(self.main(), self.docs[1]["merge"]["sha"])
        # Main has moved twice, by a merge and by a person, and neither touched src/b.txt.
        moved = self.outside(lambda: self.edit_first("src/e.txt", "e1 by hand"))
        self.assertIsNone(self.merge(2))
        self.assertEqual(self.ref("refs/heads/main^1"), moved, "the host merged onto the moved main")
        self.assertEqual(self.runs(), [], "no gate ran again")

    def test_a_commit_that_touched_the_perimeter_sends_the_ticket_to_rework_and_nothing_is_merged(self):
        head = self.propose(1, "src/a.txt", lambda: self.append("src/a.txt", "a6"), perimeter=["src/a.txt", "docs/*"])
        # A ticket file inside the repository is not the ticket: the Tracker's is.
        (self.root / "work" / "tickets").mkdir()
        (self.root / "work" / "tickets" / "0001.md").write_text("## Perimeter\n\n- `nowhere/*`\n")
        self.outside(lambda: self.edit_first("src/e.txt", "e1 by hand"))
        first = self.outside(lambda: self.append("docs/guide/intro.txt", "hello"))
        last = self.outside(lambda: self.edit_first("src/a.txt", "a1 by hand"))
        rc, got = self.rejudge(1)
        self.assertEqual(rc, 0, self.stderr)
        self.assertEqual(got["state"], "ci-failed")
        verdict = got["mainline"]
        self.assertEqual((verdict["verdict"], verdict["judge"], verdict["head_sha"]), ("NO-GO", "base", head))
        # The first overlap, oldest commit first, and `*` crossing `/` to reach docs/guide/.
        self.assert_base_line(verdict["line"], self.base, "docs/guide/intro.txt", first)
        self.assertEqual(len(verdict["details"]), 2, "one entry per overlap, not one per commit moved")
        self.assertTrue(all(isinstance(d, str) for d in verdict["details"]))
        self.assertIn("docs/guide/intro.txt", verdict["details"][0])
        self.assertIn(first[:7], verdict["details"][0])
        self.assertIn("src/a.txt", verdict["details"][1])
        self.assertIn(last[:7], verdict["details"][1])
        self.assertEqual(self.main(), last, "nothing was merged")
        self.assertFalse(self.pr_merged(1))
        self.assertEqual(self.runs(), [])

    def test_a_retry_after_the_merge_is_not_judged_against_its_own_merge(self):
        # ADR 0056 §1: the step died after the code host merged (docs/adr/0019 §9);
        # its own merge touched its perimeter, and is not main moving under it.
        self.propose(1, "src/a.txt", lambda: self.append("src/a.txt", "a6"))
        self.outside(lambda: self.edit_first("src/e.txt", "e1 by hand"))
        self.assertIsNone(self.merge(1))
        self.docs[1]["state"] = "ci-passed"
        self.save(1)
        self.assertEqual(self.rejudge(1), (0, None))

    def test_a_change_main_has_since_reverted_still_counts(self):
        head = self.propose(1, "src/a.txt", lambda: self.append("src/a.txt", "a6"))
        touched = self.outside(lambda: self.edit_first("src/a.txt", "a1 by hand"))
        undone = self.byhand_revert(touched)
        self.assertEqual(self.main_file("src/a.txt"), REPO["src/a.txt"], "premise: the net diff is empty")
        rc, got = self.rejudge(1)
        self.assertEqual(rc, 0, self.stderr)
        self.assertEqual(got["state"], "ci-failed")
        self.assert_base_line(got["mainline"]["line"], self.base, "src/a.txt", touched)
        self.assertEqual(got["mainline"]["head_sha"], head)
        details = got["mainline"]["details"]
        self.assertEqual(len(details), 2)
        self.assertIn(touched[:7], details[0])
        self.assertIn(undone[:7], details[1])

    def test_a_merge_is_named_by_its_own_sha_and_counted_once(self):
        # Two tickets that share a file, which ADR 0053's holds would prevent:
        # the second finds the first's merge, a first-parent commit, not the
        # two commits inside it.
        self.propose(1, "src/a.txt", lambda: self.edit_first("src/a.txt", "a1 ticket one"))
        self.propose(2, "src/a.txt", lambda: self.append("src/a.txt", "a6"))
        self.assertIsNone(self.merge(1))
        first = self.docs[1]["merge"]["sha"]
        rc, got = self.rejudge(2)
        self.assertEqual(rc, 0, self.stderr)
        self.assert_base_line(got["mainline"]["line"], self.base, "src/a.txt", first)
        self.assertEqual(len(got["mainline"]["details"]), 1)

    def test_a_base_that_is_not_on_main_fails_the_step_and_nothing_is_merged(self):
        self.propose(1, "src/a.txt", lambda: self.append("src/a.txt", "a6"))
        self.rewrite_main()
        self.assertFalse(self.anc(self.base, self.main()), "premise: the base was rewritten away")
        self.assertEqual(self.rejudge(1), (1, None))
        self.assertFalse(self.pr_merged(1))

    def test_the_command_and_its_ports_are_required(self):
        self.propose(1, "src/a.txt", lambda: self.append("src/a.txt", "a6"))
        self.outside(lambda: self.edit_first("src/a.txt", "a1 by hand"))  # the move that needs every port
        env = self.step_env(1)
        self.assertEqual(self.rejudge(1)[0], 0)
        for argv, given in (([], env), (["bisect"], env), (["rejudge", "check"], env), (["rejudge"], {})):
            with self.subTest(argv=argv, given=sorted(given)):
                rc, got = self.run_main(argv, given)
                self.assertNotEqual(rc, 0)
                self.assertIsNone(got)
        for var in ("DOC_FILE", "CODE_HOST", "TRACKER", "WORKLOAD"):
            with self.subTest(missing=var):
                rc, got = self.run_main(["rejudge"], {k: v for k, v in env.items() if k != var})
                self.assertNotEqual(rc, 0)
                self.assertIsNone(got)


class Check(WorldCase):
    """ADR 0056 §3-§5: main judged after the merges, a red group bisected and its culprit reverted."""

    def test_a_merge_onto_an_unmoved_main_is_green_without_a_gate_run(self):
        # ./go demo's single ticket: the merge's tree is the tree CI passed.
        self.propose(1, "src/a.txt", lambda: self.append("src/a.txt", "a6"))
        self.merge(1)
        merged = self.docs[1]["merge"]["sha"]
        rc, got = self.check(1)
        self.assertEqual(rc, 0, self.stderr)
        self.assert_main_green(1, got, exactly=merged)
        self.assertEqual(self.runs(), [])
        doc = self.mainline_doc()
        self.assertEqual((doc["state"], doc["green"], doc["head"], doc.get("reverted", [])),
                         ("green", merged, merged, []))

    def test_a_merge_onto_a_moved_main_is_judged(self):
        self.propose(1, "src/a.txt", lambda: self.append("src/a.txt", "a6"))
        self.outside(lambda: self.edit_first("src/e.txt", "e1 by hand"))
        self.merge(1)
        merged = self.docs[1]["merge"]["sha"]
        rc, got = self.check(1)
        self.assertEqual(rc, 0, self.stderr)
        self.assert_main_green(1, got, exactly=merged)
        self.assertEqual(self.runs(), [(self.base, merged, "sast test")])

    def test_a_green_group_is_judged_once_and_the_next_check_starts_from_its_green(self):
        m = self.merge_all([self.simple(1, "a"), self.simple(2, "b"), self.simple(3, "c")])
        rc, got = self.check(1)
        self.assertEqual(rc, 0, self.stderr)
        self.assert_main_green(1, got, exactly=m[3])
        self.assertEqual(self.runs(), [(self.base, m[3], "sast test")], "one run: the tree gates, at the group's head")
        doc = self.mainline_doc()
        self.assertEqual((doc["state"], doc["green"], doc["head"]), ("green", m[3], m[3]))
        for n in (2, 3):
            rc, got = self.check(n)
            self.assertEqual(rc, 0, self.stderr)
            self.assert_main_green(n, got, exactly=m[3])
        self.assertEqual(len(self.runs()), 1, "the other two tickets paid nothing")
        # A ticket judged on the old base merges after them: G is the document's green, not that base.
        self.propose(4, "src/d.txt", lambda: self.append("src/d.txt", "d6"))
        self.assertIsNone(self.merge(4))
        merged = self.docs[4]["merge"]["sha"]
        rc, got = self.check(4)
        self.assertEqual(rc, 0, self.stderr)
        self.assert_main_green(4, got, exactly=merged)
        self.assertEqual(self.runs()[1:], [(m[3], merged, "sast test")])

    def test_a_group_is_at_most_the_limit_and_counts_first_parent_commits(self):
        # Ticket 1's PR has two commits: counted wrongly, the group would be cut elsewhere.
        self.propose(1, "src/a.txt", lambda: self.append("src/a.txt", "a6"))
        self.merge(1)
        commits = [self.docs[1]["merge"]["sha"]]
        for i in range(self.limit):
            commits.append(self.outside(lambda i=i: self.append("src/e.txt", f"e{6 + i}")))
        self.assertEqual(len(commits), self.limit + 1)
        rc, got = self.check(1)
        self.assertEqual(rc, 0, self.stderr)
        self.assertEqual(self.runs(), [(self.base, commits[self.limit - 1], "sast test"),
                                       (commits[self.limit - 1], commits[self.limit], "sast test")])
        self.assert_main_green(1, got)
        self.assertEqual(self.mainline_doc()["green"], commits[-1])

    def test_a_tree_the_green_main_already_has_is_green_without_a_run(self):
        # A person reverts the ticket's merge: main's tree is G's own again.
        self.propose(1, "src/a.txt", lambda: self.append("src/a.txt", "a6"))
        self.merge(1)
        undone = self.byhand_revert(self.docs[1]["merge"]["sha"], merge=True)
        rc, got = self.check(1)
        self.assertEqual(rc, 0, self.stderr)
        self.assertEqual(self.runs(), [])
        self.assert_main_green(1, got)
        self.assertEqual(self.mainline_doc()["green"], undone)

    def test_a_red_group_is_bisected_its_culprit_reverted_and_main_is_green_again(self):
        # Ticket 1 renames what ticket 3 starts calling: each passes alone.
        m = self.merge_all([
            (1, "src/lib.txt", self.rename_foo),
            self.simple(2, "b"),
            (3, "src/use.txt", lambda: self.append("src/use.txt", "call foo")),
            self.simple(4, "d")])
        rc, got = self.check(1)
        self.assertEqual(rc, 0, self.stderr)
        runs = self.runs()
        self.assertEqual(runs[0], (self.base, m[4], "sast test"), "the group's newest commit is judged first")
        self.assertLessEqual(len(runs), 4, "that, two for the bisection of four, and the revert's head")
        head = self.main()
        self.assertEqual(runs[-1][1], head, "the revert's head is judged")

        # Reverted through the code host: a branch off main's head, a PR, a merge. Never a force push.
        branch = f"revert/{m[3][:12]}"
        self.assertEqual(self.revert_branches(), [branch])
        self.assertEqual(self.ref(f"refs/heads/{branch}^"), m[4], "the branch starts at main's head")
        prs = self.revert_prs()
        self.assertEqual([(p["branch"], p["merged"]) for p in prs], [(branch, True)])
        self.assertTrue(prs[0]["title"])
        self.assertIn("undefined call: foo", prs[0]["body"], "the verdict is the PR's body")
        self.assertIn(m[3][:7], prs[0]["body"])
        self.assertNotEqual(head, m[4])
        self.assertTrue(self.anc(m[3], head) and self.anc(m[4], head), "history keeps both")
        self.assertNotIn("call foo", self.main_file("src/use.txt"))
        self.assertIn("def bar", self.main_file("src/lib.txt"), "the other tickets stay")
        self.assertIn("b6", self.main_file("src/b.txt"))
        self.assertIn("d6", self.main_file("src/d.txt"))

        doc = self.mainline_doc()
        self.assertEqual((doc["state"], doc["green"], doc["head"]), ("green", head, head))
        self.assertEqual(len(doc["reverted"]), 1)
        entry = doc["reverted"][0]
        self.assertEqual(entry["merge"], m[3])
        self.assertNotEqual(entry["revert"], m[3])
        self.assertTrue(self.anc(entry["revert"], head))
        self.assertIn(m[3][:7], entry["line"], "the culprit's own verdict, not the group's newest")
        self.assertNotIn(m[4][:7], entry["line"])
        self.assertEqual(entry["details"], ["undefined call: foo"])

        # The step's own ticket, and the others: main-green, released from a commit that was judged green.
        self.assert_main_green(1, got)
        self.assertNotIn(got["mainline"]["green"], (m[3], m[4]))
        after = len(runs)
        for n in (2, 4):
            rc, other = self.check(n)
            self.assertEqual(rc, 0, self.stderr)
            self.assert_main_green(n, other)
            self.assertNotIn(other["mainline"]["green"], (m[3], m[4]), "a red commit is never what ships")
        # The culprit's ticket learns it from its own step: back to rework, with the verdict.
        rc, back = self.check(3)
        self.assertEqual(rc, 0, self.stderr)
        self.assertEqual(back["state"], "ci-failed")
        verdict = back["mainline"]
        self.assertEqual((verdict["verdict"], verdict["judge"]), ("NO-GO", "main"))
        self.assertTrue(verdict["line"].startswith("NO-GO"))
        self.assertIn(m[3][:7], verdict["line"])
        self.assertEqual(verdict["details"], ["undefined call: foo"])
        self.assertIn(verdict["head_sha"], (self.docs[3]["pr"]["head_sha"], m[3]))
        self.assertEqual(len(self.runs()), after, "those steps judged nothing")

    def test_the_judges_are_the_last_green_mains_not_the_commits_own(self):
        self.propose(1, "src/a.txt", lambda: self.append("src/a.txt", "a6"))
        self.merge(1)

        def weaken():
            (self.author / "Makefile").write_text(WEAK_MAKEFILE, encoding="utf-8")
            (self.author / "gates" / "run.sh").write_text("exit 0\n", encoding="utf-8")
            self.append("src/use.txt", "call ghost")

        bad = self.outside(weaken)  # a person's commit that loosens the judge and breaks main
        rc, got = self.check(1)
        self.assertEqual(rc, 0, self.stderr)
        self.assertEqual(self.runs()[0], (self.base, bad, "sast test"), "judged by the base's gates")
        doc = self.mainline_doc()
        self.assertEqual((doc["state"], [r["merge"] for r in doc["reverted"]]), ("green", [bad]))
        self.assertEqual(self.main_file("Makefile"), REPO["Makefile"], "the weakening is reverted with it")
        # Not a merge: a plain commit is reverted without -m, and nobody is sent back to rework.
        parents = self.host("rev-list", "--parents", "-n", "1", f"refs/heads/revert/{bad[:12]}").stdout.split()
        self.assertEqual(len(parents), 2)
        self.assert_main_green(1, got)

    def test_a_revert_that_does_not_apply_leaves_main_red(self):
        stuck = self.red_main_that_cannot_be_reverted()
        rc, got = self.check(1)
        self.assertEqual((rc, got), (1, None))
        doc = self.mainline_doc()
        self.assertEqual((doc["state"], doc["green"]), ("red", self.base), "red since the last green main")
        self.assertTrue(doc["line"])
        self.assertEqual(doc.get("reverted", []), [])
        self.assertEqual(self.main(), stuck, "nothing landed on main")
        self.assertEqual(self.revert_branches(), [])
        self.assertEqual(self.revert_prs(), [])

    def red_main_that_cannot_be_reverted(self):
        """Ticket 1 merged, then a person renames foo, another calls it, and a third edits a line
        the call's revert would remove. Returns main's head."""
        self.merge_all([self.simple(1, "a")])
        self.outside(self.rename_foo)
        self.outside(lambda: (self.append("src/use.txt", "call foo"), self.append("src/use.txt", "# kept")))
        return self.outside(lambda: self.replace("src/use.txt", "# kept", "# kept (edited by hand)"))

    def test_a_red_main_is_judged_as_it_is_and_lifted_by_a_fix(self):
        stuck = self.red_main_that_cannot_be_reverted()
        self.assertEqual(self.check(1), (1, None))
        before = len(self.runs())
        # Nobody fixed it: main's head is looked at, not bisected again, not reverted again.
        self.assertEqual(self.check(1), (1, None))
        self.assertLessEqual(len(self.runs()) - before, 1)
        self.assertEqual((self.mainline_doc()["state"], self.main()), ("red", stuck))
        self.assertEqual((self.revert_branches(), self.revert_prs()), ([], []))
        # A person fixes main; the next step turns the document green.
        fixed = self.outside(lambda: self.remove_line("src/use.txt", "call foo"))
        before = len(self.runs())
        rc, got = self.check(1)
        self.assertEqual(rc, 0, self.stderr)
        self.assert_main_green(1, got, exactly=fixed)
        self.assertEqual([run[1] for run in self.runs()[before:]], [fixed], "one run, at main's head")
        doc = self.mainline_doc()
        self.assertEqual((doc["state"], doc["green"], doc["head"]), ("green", fixed, fixed))

    def test_two_culprits_in_one_group_leave_main_red_after_one_revert(self):
        self.merge_all([self.simple(1, "a")])
        self.outside(self.rename_foo)
        first = self.outside(lambda: self.append("src/use.txt", "call foo"))
        self.outside(lambda: self.append("src/e.txt", "call ghost"))
        self.assertEqual(self.check(1), (1, None))
        self.assertEqual(self.mainline_doc()["state"], "red")
        self.assertEqual([(p["branch"], p["merged"]) for p in self.revert_prs()], [(f"revert/{first[:12]}", True)],
                         "the first culprit is reverted, the second is not bisected")
        # Red: the next step judges the head and stops there.
        before = len(self.runs())
        self.assertEqual(self.check(1), (1, None))
        self.assertLessEqual(len(self.runs()) - before, 1)
        self.assertEqual(len(self.revert_prs()), 1)
        self.assertEqual(self.mainline_doc()["state"], "red")

    def test_a_culprit_that_is_a_revert_is_not_reverted(self):
        self.propose(1, "src/a.txt", lambda: self.append("src/a.txt", "a6"))
        self.merge(1)
        defined = self.outside(lambda: self.append("src/lib.txt", "def baz"))
        self.outside(lambda: self.append("src/use.txt", "call baz"))
        undone = self.byhand_revert(defined)  # takes the definition away, leaving the call
        self.assertEqual(self.check(1), (1, None))
        doc = self.mainline_doc()
        self.assertEqual(doc["state"], "red")
        self.assertEqual((self.revert_branches(), self.revert_prs()), ([], []))
        self.assertEqual(self.main(), undone)

    def test_a_ticket_whose_merge_is_not_on_main_fails_the_step(self):
        stray = self.propose(1, "src/b.txt", lambda: self.append("src/b.txt", "b6"))  # a PR head, never merged
        git("fetch", "-q", str(self.root / "host.git"), "refs/heads/ticket/0001", cwd=self.root / "work")
        self.docs[1].update(state="merged", merge={"sha": stray, "head_sha": stray})
        self.save(1)
        self.assertEqual(self.check(1), (1, None))
        self.assertIsNone(self.mainline_doc())

    def test_a_green_that_is_no_longer_on_main_falls_back_to_the_tickets_base(self):
        self.propose(1, "src/a.txt", lambda: self.append("src/a.txt", "a6"))
        self.propose(2, "src/b.txt", lambda: self.append("src/b.txt", "b6"))
        self.merge(1)
        self.assertEqual(self.check(1)[0], 0)
        old = self.mainline_doc()["green"]
        # Main is rewritten, as the L0 replays do: back to the base, and a new commit.
        self.au("push", "-q", "-f", "origin", f"{self.base}:refs/heads/main")
        self.outside(lambda: self.edit_first("src/e.txt", "e1 by hand"))
        self.assertFalse(self.anc(old, self.main()), "premise: the document's green is gone from main")
        self.assertIsNone(self.merge(2))
        merged = self.docs[2]["merge"]["sha"]
        rc, got = self.check(2)
        self.assertEqual(rc, 0, self.stderr)
        self.assert_main_green(2, got, exactly=merged)
        self.assertEqual(self.runs(), [(self.base, merged, "sast test")])

    def test_the_command_needs_its_ports(self):
        self.propose(1, "src/a.txt", lambda: self.append("src/a.txt", "a6"))
        self.outside(lambda: self.edit_first("src/e.txt", "e1 by hand"))  # so that a gate has to run
        self.merge(1)
        env = self.step_env(1)
        for var in ("DOC_FILE", "CODE_HOST", "STATE_STORE", "WORKLOAD", "WORKLOAD_CONTRACT"):
            with self.subTest(missing=var):
                rc, got = self.run_main(["check"], {k: v for k, v in env.items() if k != var})
                self.assertNotEqual(rc, 0)
                self.assertIsNone(got)
        self.assertEqual(self.check(1)[0], 0, self.stderr)


class SmallGroups(WorldCase):
    limit = 2

    def test_the_limit_is_read_from_the_policy_file(self):
        commits = [self.merge_all([self.simple(1, "a")])[1]]
        commits += [self.outside(lambda i=i: self.append("src/e.txt", f"e{6 + i}")) for i in range(2)]
        rc, _ = self.check(1)
        self.assertEqual(rc, 0, self.stderr)
        self.assertEqual(self.runs(), [(self.base, commits[1], "sast test"), (commits[1], commits[2], "sast test")])

    def test_an_empty_commit_after_a_judged_group_is_not_judged_again(self):
        commits = [self.merge_all([self.simple(1, "a")])[1]]
        commits.append(self.outside(lambda: self.append("src/e.txt", "e6")))
        empty = self.outside(lambda: None)  # a third commit, in the next group, with the tree just judged
        rc, _ = self.check(1)
        self.assertEqual(rc, 0, self.stderr)
        self.assertEqual(self.runs(), [(self.base, commits[1], "sast test")])
        self.assertEqual(self.mainline_doc()["green"], empty)


if __name__ == "__main__":
    unittest.main()

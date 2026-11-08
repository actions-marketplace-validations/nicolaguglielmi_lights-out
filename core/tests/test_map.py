"""Tests for core/map.py, written from docs/adr/0054 §1-§5 and the command line
the module exposes (build, slice, drift, after-merge), never from the
implementation.

Every test builds a throwaway git repository with `git init` and a handful of
commits, runs `core.map.main` in-process with stdout and stderr captured, and
reads the SQLite file back with `sqlite3`, so a rule is pinned by the rows it
produces: exact sets of node names, edges and citation rows, not a count.
Fixtures are built once per class where a class only reads them. Nothing here
touches the network or the host's git configuration (a temp HOME, no system
or global config). `ci/map.sh` proves the same commands end to end on this
repository and on an attachable workload; these pin each rule on its own.

Where the ADR leaves a form open the test accepts the forms the ADR allows and
nothing else: a command citation's stored target may be `demo` or `./go demo`;
a key's `NAME` or `NAME=`; `from core import tower` may also draw an edge to
the package's `__init__.py`. A citation is located by its line (1-based) in a
page that holds one citation per line, so the tests do not depend on how a
target is spelled after resolution.

Not asserted, because the ADR does not say: the headings and wording of the
slice; whether a Markdown link's `#fragment` is stripped before resolving; a
`# comment` that starts a line of a fenced block (only the ` # …` tail is
specified); `async function` and class methods in JS; a nested class or a
function under an `if` in Python; what `after-merge` titles the ticket.
"""

import collections
import contextlib
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import map as projmap

ROOT = Path(__file__).resolve().parents[2]
HEX40 = re.compile(r"^[0-9a-f]{40}$")
TARGETS = ("assign", "ci", "demo", "demo-seam", "help", "map")

Result = collections.namedtuple("Result", "code out err")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = projmap.main(list(argv))
        except SystemExit as stop:
            code = stop.code if isinstance(stop.code, int) else 1
    return Result(code, out.getvalue(), err.getvalue())


def fresh(parent):
    return Path(tempfile.mkdtemp(dir=parent)).resolve()


class Repo:
    """A throwaway git repository on branch main."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q")

    def git(self, *args):
        proc = subprocess.run(
            [
                "git",
                "-c", "user.name=t",
                "-c", "user.email=t@t.invalid",
                "-c", "commit.gpgsign=false",
                "-c", "init.defaultBranch=main",
                "-C", str(self.path),
                *args,
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode:
            raise AssertionError(f"git {' '.join(args)}: {proc.stderr}")
        return proc.stdout

    def write(self, files):
        for rel, body in files.items():
            target = self.path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(body, bytes):
                target.write_bytes(body)
            else:
                target.write_text(body, encoding="utf-8")

    def commit(self, files=None, message="c", delete=()):
        self.write(files or {})
        for rel in delete:
            (self.path / rel).unlink()
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.head()

    def head(self):
        return self.git("rev-parse", "HEAD").strip()


def query(path, sql, *args):
    con = sqlite3.connect(str(path))
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def meta(path):
    return dict(query(path, "SELECT key, value FROM meta"))


def names(path, kind):
    return {name for (name,) in query(path, "SELECT name FROM node WHERE kind = ?", kind)}


def title_of(path, kind, name):
    rows = query(path, "SELECT title FROM node WHERE kind = ? AND name = ?", kind, name)
    return rows[0][0] if rows else None


def edges(path, kind):
    ref = dict(query(path, "SELECT id, name FROM node"))
    return {
        (ref.get(src, src), ref.get(dst, dst))
        for src, dst in query(path, "SELECT src, dst FROM edge WHERE kind = ?", kind)
    }


def cites(path):
    """Citation rows as (page, line, kind, bare target, ok)."""
    ref = dict(query(path, "SELECT id, name FROM node"))
    rows = query(path, "SELECT src, line, kind, target, ok FROM cite")
    return [(ref.get(src, src), line, kind, bare(target), bool(ok)) for src, line, kind, target, ok in rows]


def bare(target):
    for prefix in ("./go ", "make "):
        if target.startswith(prefix):
            target = target[len(prefix):]
    return target.rstrip("=")


def dump(path):
    con = sqlite3.connect(str(path))
    try:
        return "\n".join(con.iterdump())
    finally:
        con.close()


def page(entries):
    """A page of one line per (key, text) entry and the 1-based line of each key."""
    text = "\n".join(line for _, line in entries) + "\n"
    return text, {key: number for number, (key, _) in enumerate(entries, start=1)}


def perimeter_lines(text):
    """The list items of a document's `## Perimeter` section, as written."""
    items, inside = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line.strip() == "## Perimeter"
        elif inside and line.startswith("- "):
            items.append(line)
    return items


class MapCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        holder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(holder.cleanup)
        cls.tmp = Path(holder.name).resolve()
        home = cls.tmp / "home"
        home.mkdir()
        patch = mock.patch.dict(
            os.environ,
            {
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(home),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0",
            },
        )
        patch.start()
        cls.addClassCleanup(patch.stop)
        for leaked in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR", "GIT_PREFIX"):
            os.environ.pop(leaked, None)

    @classmethod
    def workdir(cls):
        return fresh(cls.tmp)

    @classmethod
    def new_repo(cls):
        return Repo(cls.workdir() / "repo")

    @classmethod
    def targets_file(cls):
        path = cls.tmp / "targets.txt"
        path.write_text("\n".join(TARGETS) + "\n", encoding="utf-8")
        return path

    @classmethod
    def build_map(cls, repo, out, *extra):
        return run(
            "build", "--repo", str(repo.path), "--targets", str(cls.targets_file()), "--out", str(out), *extra
        )

    @classmethod
    def built(cls, files, *extra):
        """A repository with one commit of `files` and the map built from it."""
        repo = cls.new_repo()
        repo.commit(files, "base")
        out = cls.workdir() / "map.sqlite"
        res = cls.build_map(repo, out, *extra)
        if res.code != 0:
            raise AssertionError(f"build failed: {res.err}")
        return repo, out

    def assertRefused(self, res, one_line=True):
        self.assertEqual(res.code, 1, res.err)
        self.assertEqual(res.out, "")
        self.assertTrue(res.err.startswith("map: "), res.err)
        if one_line:
            self.assertEqual(len(res.err.splitlines()), 1, res.err)


# ---------------------------------------------------------------- §1 kinds


class Kinds(MapCase):
    FILES = {
        "docs/adr/0001-first.md": "# First\n",
        "docs/adrs/0002-second.md": "# Second\n",
        "adr/0003-top.md": "# Third\n",
        "docs/adr/README.md": "# Index\n",
        "docs/adr/12-short.md": "# Short\n",
        "tickets/0001.md": "# 0001 — Ticket\n",
        "docs/0005.md": "# Numbered but not a ticket\n",
        "README.md": "# Readme\n",
        "docs/guide.md": "# Guide\n",
        "fixtures/case/notes.md": "# Fixture\n",
        "svc/fixtures/y.md": "# Nested fixture\n",
        "svc/main.py": "x = 1\n",
        "Makefile": "all:\n",
        "go": "#!/bin/sh\n",
        "data/blob.bin": b"\xff\xfe\x00\x01",
        "core/test_alpha.py": "x = 1\n",
        "core/beta_test.py": "x = 1\n",
        "web/a.test.js": "x\n",
        "web/b.spec.js": "x\n",
        "web/c.test.mjs": "x\n",
        "web/d.spec.cjs": "x\n",
        "web/e.test.cjs": "x\n",
        "web/f.spec.mjs": "x\n",
        "core/conftest.py": "x = 1\n",
        "core/testing.py": "x = 1\n",
        "core/latest.py": "x = 1\n",
        "core/test.py": "x = 1\n",
        "web/mytest.js": "x\n",
        "web/a.test.ts": "x\n",
        "core/test_data.json": "{}\n",
    }

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.repo, cls.out = cls.built(cls.FILES)

    def test_adr_is_a_numbered_markdown_file_in_an_adr_or_adrs_directory(self):
        self.assertEqual(
            names(self.out, "adr"),
            {"docs/adr/0001-first.md", "docs/adrs/0002-second.md", "adr/0003-top.md"},
        )

    def test_ticket_is_a_numbered_markdown_file_of_the_tickets_directory_named_by_its_id(self):
        self.assertEqual(names(self.out, "ticket"), {"0001"})

    def test_page_is_any_other_markdown_file_outside_fixtures(self):
        self.assertEqual(
            names(self.out, "page"),
            {"README.md", "docs/guide.md", "docs/0005.md", "docs/adr/README.md", "docs/adr/12-short.md"},
        )

    def test_a_test_is_named_like_one_in_python_or_javascript(self):
        self.assertEqual(
            names(self.out, "test"),
            {
                "core/test_alpha.py",
                "core/beta_test.py",
                "web/a.test.js",
                "web/b.spec.js",
                "web/c.test.mjs",
                "web/d.spec.cjs",
                "web/e.test.cjs",
                "web/f.spec.mjs",
            },
        )

    def test_every_other_tracked_path_is_a_file(self):
        self.assertEqual(
            names(self.out, "file"),
            {
                "fixtures/case/notes.md",
                "svc/fixtures/y.md",
                "svc/main.py",
                "Makefile",
                "go",
                "data/blob.bin",
                "core/conftest.py",
                "core/testing.py",
                "core/latest.py",
                "core/test.py",
                "web/mytest.js",
                "web/a.test.ts",
                "core/test_data.json",
            },
        )

    def test_a_path_has_one_node(self):
        total = query(self.out, "SELECT COUNT(*) FROM node WHERE kind IN ('adr', 'page', 'test', 'file')")[0][0]
        self.assertEqual(total, len(self.FILES) - 1)  # tickets/0001.md is the ticket node

    def test_a_node_is_unique_on_kind_and_name(self):
        copy = self.workdir() / "copy.sqlite"
        shutil.copy(self.out, copy)
        con = sqlite3.connect(str(copy))
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("INSERT INTO node(kind, name, title) VALUES ('file', 'svc/main.py', NULL)")
        finally:
            con.close()

    def test_the_tables_are_the_five_of_schema_2(self):
        def columns(table):
            return [row[1] for row in query(self.out, f"PRAGMA table_info({table})")]

        self.assertEqual(columns("meta"), ["key", "value"])
        self.assertEqual(columns("node"), ["id", "kind", "name", "title"])
        self.assertEqual(columns("edge"), ["src", "dst", "kind"])
        self.assertEqual(columns("cite"), ["src", "kind", "target", "line", "ok"])
        self.assertEqual(columns("doc"), ["node", "status", "text"])
        self.assertEqual(
            {name for (name,) in query(self.out, "SELECT name FROM sqlite_master WHERE type = 'table'")},
            {"meta", "node", "edge", "cite", "doc"},
        )


class TicketsDirectory(MapCase):
    def test_tickets_option_names_the_directory_of_an_attached_repository(self):
        _, out = self.built(
            {
                ".contract/tickets/0007.md": "# 0007 — Attached\n",
                "tickets/0001.md": "# 0001 — Not this checkout's\n",
                "README.md": "# Readme\n",
            },
            "--tickets",
            ".contract/tickets",
        )
        self.assertEqual(names(out, "ticket"), {"0007"})
        self.assertNotIn(".contract/tickets/0007.md", names(out, "page"))
        self.assertEqual(meta(out)["tickets"], ".contract/tickets")


# ------------------------------------------------------- §1 build, §2 rebuilt


class Build(MapCase):
    def test_prints_one_line_the_sha_and_the_sorted_kind_counts(self):
        repo = self.new_repo()
        repo.commit(RICH, "base")
        out = self.workdir() / "map.sqlite"
        res = self.build_map(repo, out)
        self.assertEqual(res.code, 0, res.err)
        self.assertRegex(res.out, r"^[0-9a-f]{40}( [a-z]+=\d+)+\n$")
        sha, *pairs = res.out.split()
        self.assertEqual(sha, repo.head())
        kinds = [pair.split("=")[0] for pair in pairs]
        self.assertEqual(kinds, sorted(kinds))
        counts = {kind: int(count) for kind, count in (pair.split("=") for pair in pairs) if int(count)}
        self.assertEqual(counts, dict(query(out, "SELECT kind, COUNT(*) FROM node GROUP BY kind")))
        self.assertGreaterEqual(len(counts), 8)

    def test_meta_holds_the_schema_the_sha_the_tickets_directory_and_the_exclude_list(self):
        repo, out = self.built({"a.txt": "a\n"}, "--exclude", "docs/PLAN.md docs/plans/*")
        values = meta(out)
        self.assertEqual(set(values), {"schema", "sha", "tickets", "exclude"})
        self.assertEqual(str(values["schema"]), "2")
        self.assertEqual(values["sha"], repo.head())
        self.assertEqual(values["tickets"], "tickets")
        self.assertEqual(values["exclude"], "docs/PLAN.md docs/plans/*")

    def test_no_exclude_list_is_an_empty_one(self):
        _, out = self.built({"a.txt": "a\n"})
        self.assertFalse(meta(out)["exclude"])

    def test_rev_selects_the_commit_to_read(self):
        repo = self.new_repo()
        first = repo.commit({"old.py": "x = 1\n"}, "first")
        repo.commit({"new.py": "x = 1\n"}, "second")
        out = self.workdir() / "map.sqlite"
        res = self.build_map(repo, out, "--rev", "HEAD~1")
        self.assertEqual(res.code, 0, res.err)
        self.assertTrue(res.out.startswith(first + " "), res.out)
        self.assertEqual(meta(out)["sha"], first)
        self.assertEqual(names(out, "file"), {"old.py"})

    def test_head_is_the_default_commit(self):
        repo = self.new_repo()
        repo.commit({"old.py": "x = 1\n"}, "first")
        second = repo.commit({"new.py": "x = 1\n"}, "second")
        out = self.workdir() / "map.sqlite"
        self.assertEqual(self.build_map(repo, out).code, 0)
        self.assertEqual(meta(out)["sha"], second)
        self.assertEqual(names(out, "file"), {"old.py", "new.py"})

    def test_the_working_tree_is_never_read(self):
        repo = self.new_repo()
        repo.commit(
            {
                "a.py": "def real():\n    pass\n",
                "gone.py": "x = 1\n",
                "README.md": "# Readme\n",
            },
            "base",
        )
        repo.write(
            {
                "a.py": "def real():\n    pass\n\n\ndef dirty():\n    pass\n",
                "new.py": "def untracked():\n    pass\n",
                "README.md": "# Readme\n\nSee `core/zz.py` and `./go nosuch`.\n",
            }
        )
        (repo.path / "gone.py").unlink()
        out = self.workdir() / "map.sqlite"
        self.assertEqual(self.build_map(repo, out).code, 0)
        self.assertEqual(names(out, "file"), {"a.py", "gone.py"})
        self.assertEqual(names(out, "symbol"), {"a.py::real"})
        self.assertEqual(cites(out), [])

    def test_a_build_replaces_the_old_file(self):
        out = self.workdir() / "map.sqlite"
        out.write_bytes(b"not a sqlite file at all")
        first = self.new_repo()
        first.commit({"one.py": "x = 1\n"}, "first repository")
        self.assertEqual(self.build_map(first, out).code, 0)
        self.assertEqual(names(out, "file"), {"one.py"})
        second = self.new_repo()
        second.commit({"two.py": "x = 1\n"}, "second repository")
        self.assertEqual(self.build_map(second, out).code, 0)
        self.assertEqual(names(out, "file"), {"two.py"})
        self.assertEqual(meta(out)["sha"], second.head())

    def test_the_same_commit_gives_the_same_rows(self):
        repo, first = self.built(RICH)
        second = self.workdir() / "again.sqlite"
        self.assertEqual(self.build_map(repo, second).code, 0)
        self.assertEqual(dump(first), dump(second))

    def test_the_same_commit_gives_the_same_rows_whatever_the_hash_seed(self):
        repo, _ = self.built(RICH)
        code = "import sys; from core import map as m; sys.exit(m.main(sys.argv[1:]))"
        dumps = []
        for seed in ("1", "2"):
            out = self.workdir() / "map.sqlite"
            proc = subprocess.run(
                [
                    sys.executable, "-c", code,
                    "build", "--repo", str(repo.path), "--targets", str(self.targets_file()), "--out", str(out),
                ],
                cwd=ROOT,
                env=dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=str(ROOT)),
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            dumps.append(dump(out))
        self.assertEqual(dumps[0], dumps[1])

    def test_an_unknown_rev_is_refused(self):
        repo = self.new_repo()
        repo.commit({"a.txt": "a\n"}, "base")
        res = self.build_map(repo, self.workdir() / "map.sqlite", "--rev", "no-such-rev")
        self.assertRefused(res, one_line=False)

    def test_a_directory_that_is_not_a_repository_is_refused(self):
        plain = self.workdir() / "plain"
        plain.mkdir()
        res = run(
            "build", "--repo", str(plain), "--targets", str(self.targets_file()), "--out", str(self.workdir() / "m.sqlite")
        )
        self.assertRefused(res, one_line=False)

    def test_no_command_is_refused(self):
        self.assertNotEqual(run().code, 0)


# --------------------------------------------------------------- §1 symbols

PYTHON = '''\
"""Module docstring."""
import os

LIMIT = 3


def alpha():
    def inner():
        return 1

    return inner


async def gamma():
    return 2


@some.decorator
def decorated():
    return 3


class Beta:
    attr = 1

    def run(self):
        def nested():
            return 4

        return nested

    async def arun(self):
        return 5

    @property
    def prop(self):
        return 6
'''

PYTHON_TEST = '''\
import unittest


class TestX(unittest.TestCase):
    def test_a(self):
        pass


def helper():
    pass
'''

PYTHON_REDEFINED = '''\
class Box:
    @property
    def size(self):
        return 1

    @size.setter
    def size(self, value):
        pass


def twice():
    pass


def twice():
    pass
'''

JAVASCRIPT = """\
function plain(a) {
  return a;
}
class Widget {
  method() {}
}
const TOP = 1;
let counter = 0;
var legacy = 2;
export function exported() {}
export class ExportedClass {}
export const EXPORTED = 3;
exports.helper = function () {};
exports.other = () => 1;
function outer() {
  const inner = 1;
  let local = 2;
  return inner + local;
}
"""


class Symbols(MapCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.repo, cls.out = cls.built(
            {
                "svc/m.py": PYTHON,
                "core/test_x.py": PYTHON_TEST,
                "svc/dup.py": PYTHON_REDEFINED,
                "svc/broken.py": "def broken(:\n    pass\n",
                "web/lib.js": JAVASCRIPT,
                "web/lib.test.js": "function testHelper() {}\n",
            }
        )

    def symbols_of(self, path):
        prefix = path + "::"
        return {name[len(prefix):] for name in names(self.out, "symbol") if name.startswith(prefix)}

    def test_python_defines_its_top_level_functions_classes_and_methods(self):
        self.assertEqual(
            self.symbols_of("svc/m.py"),
            {"alpha", "gamma", "decorated", "Beta", "Beta.run", "Beta.arun", "Beta.prop"},
        )

    def test_a_defines_edge_runs_from_the_file_to_each_symbol(self):
        defined = {dst for src, dst in edges(self.out, "defines") if src == "svc/m.py"}
        self.assertEqual(defined, {"svc/m.py::" + name for name in self.symbols_of("svc/m.py")})

    def test_a_test_defines_symbols_too(self):
        self.assertEqual(self.symbols_of("core/test_x.py"), {"TestX", "TestX.test_a", "helper"})
        self.assertIn(("core/test_x.py", "core/test_x.py::TestX.test_a"), edges(self.out, "defines"))

    def test_a_name_defined_twice_is_one_symbol(self):
        self.assertEqual(self.symbols_of("svc/dup.py"), {"Box", "Box.size", "twice"})

    def test_a_python_file_that_does_not_parse_builds_without_symbols(self):
        self.assertIn("svc/broken.py", names(self.out, "file"))
        self.assertEqual(self.symbols_of("svc/broken.py"), set())

    def test_javascript_defines_functions_classes_top_level_bindings_and_exports(self):
        self.assertEqual(
            self.symbols_of("web/lib.js"),
            {
                "plain", "Widget", "TOP", "counter", "legacy", "exported",
                "ExportedClass", "EXPORTED", "helper", "other", "outer",
            },
        )

    def test_javascript_bindings_inside_a_function_are_not_symbols(self):
        symbols = self.symbols_of("web/lib.js")
        self.assertFalse({"inner", "local"} & symbols)

    def test_a_javascript_test_defines_symbols_too(self):
        self.assertEqual(self.symbols_of("web/lib.test.js"), {"testHelper"})
        self.assertIn(("web/lib.test.js", "web/lib.test.js::testHelper"), edges(self.out, "defines"))

    def test_symbol_names_are_the_path_and_the_name(self):
        for name in names(self.out, "symbol"):
            self.assertRegex(name, r"^[^:]+::[^:]+$")


# ----------------------------------------------- §1 imports and tests edges


class Imports(MapCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.repo, cls.out = cls.built(
            {
                "lib.py": "thing = 1\n",
                "pkg/__init__.py": "\n",
                "pkg/helper.py": "h = 1\n",
                "pkg/mate.py": "m = 1\n",
                "pkg/other.py": "f = 1\n",
                "pkg/sub/__init__.py": "\n",
                "pkg/sub/leaf.py": "l = 1\n",
                "pkg/sub/main.py": "import helper\nfrom lib import thing\nimport pkg.sub.leaf\nimport os\nimport json\n",
                "pkg/sub/deep.py": "from .. import mate\nfrom ..other import f\nfrom . import leaf\n",
                "pkg/sub/rel.py": "from .leaf import l\n",
                "core/__init__.py": "\n",
                "core/tower.py": "def main():\n    pass\n",
                "core/tests/__init__.py": "\n",
                "core/tests/test_a.py": "import core.tower\n",
                "core/tests/test_b.py": "import unittest\nfrom core.tower import main\nfrom core.tests import test_a\n",
                "core/tests/test_c.py": "from core import tower\n",
                "web/app.js": (
                    "const lib = require('./lib');\n"
                    'import x from "./esm";\n'
                    "import './side.js';\n"
                    "const d = require('./dir');\n"
                    "const c = require('./cjs');\n"
                    "const up = require('../shared/util');\n"
                    "const ex = require('express');\n"
                    "const nope = require('./missing');\n"
                    "const both = require('./both');\n"
                ),
                "web/lib.js": "x\n",
                "web/esm.mjs": "x\n",
                "web/side.js": "x\n",
                "web/dir/index.js": "x\n",
                "web/cjs.cjs": "x\n",
                "web/both.js": "x\n",
                "web/both/index.js": "x\n",
                "shared/util.js": "x\n",
                "web/app.test.js": "const app = require('./app');\n",
            },
        )

    def imported_by(self, path):
        return {dst for src, dst in edges(self.out, "imports") if src == path}

    def files_covered_by(self, path):
        return {dst for src, dst in edges(self.out, "tests") if src == path}

    def assertImports(self, found, expected):
        """Exactly `expected`, plus package `__init__.py` files the ADR leaves open."""
        extra = {path for path in found - expected if path.endswith("__init__.py")}
        self.assertEqual(found - extra, expected)

    def test_a_python_module_resolves_from_the_importers_directory_up_to_the_root(self):
        self.assertImports(
            self.imported_by("pkg/sub/main.py"),
            {"pkg/helper.py", "lib.py", "pkg/sub/leaf.py"},
        )

    def test_a_relative_python_import_resolves_from_the_importers_package(self):
        self.assertImports(
            self.imported_by("pkg/sub/deep.py"),
            {"pkg/mate.py", "pkg/other.py", "pkg/sub/leaf.py"},
        )
        self.assertImports(self.imported_by("pkg/sub/rel.py"), {"pkg/sub/leaf.py"})

    def test_javascript_relative_specifiers_resolve_with_their_extensions(self):
        self.assertEqual(
            self.imported_by("web/app.js"),
            {
                "web/lib.js",
                "web/esm.mjs",
                "web/side.js",
                "web/dir/index.js",
                "web/cjs.cjs",
                "shared/util.js",
                "web/both.js",
            },
        )

    def test_a_test_covers_the_non_test_files_it_imports(self):
        self.assertImports(self.files_covered_by("core/tests/test_a.py"), {"core/tower.py"})
        self.assertImports(self.files_covered_by("core/tests/test_c.py"), {"core/tower.py"})
        self.assertEqual(self.files_covered_by("web/app.test.js"), {"web/app.js"})

    def test_a_test_does_not_cover_a_test_it_imports(self):
        self.assertImports(self.files_covered_by("core/tests/test_b.py"), {"core/tower.py"})

    def test_only_tests_have_tests_edges(self):
        self.assertTrue({src for src, _ in edges(self.out, "tests")} <= names(self.out, "test"))


# ------------------------------------------- §1 perimeter, declares, history

TICKET_ONE = """\
# 0001 — Perimeter and title

Preamble text.

- Status: open
- Labels: bug, feature:checkout, svc/backend

## Problem

Mentions `lib/other.py` in prose.

## Perimeter

- `svc/*.py`
- docs/guide.md
- `lib/mod?.py`
- `nothing/here/*.py`

## Notes

- `lib/notglob.py`
"""


class TicketRows(MapCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.repo, cls.out = cls.built(
            {
                "tickets/0001.md": TICKET_ONE,
                "tickets/0002.md": "# 0002 — Cart\n\n- Labels: feature:checkout, feature:cart\n",
                "tickets/0003.md": "# 0003 — Plain\n\n- Labels: bug, svc/backend, M4 (contract test), checkout, features\n",
                "tickets/0004.md": (
                    "Some preface line.\n\n## Not a title\n\n# Plain title\n\n# Second title\n\n"
                    "- Status: open\n\nNote: feature:ghost is not declared here.\n"
                ),
                "svc/a.py": "x = 1\n",
                "svc/sub/deep.py": "x = 1\n",
                "svc/readme.txt": "x\n",
                "svc/test_a.py": "x = 1\n",
                "docs/guide.md": "# Guide\n",
                "lib/mod1.py": "x = 1\n",
                "lib/mod12.py": "x = 1\n",
                "lib/notglob.py": "x = 1\n",
                "lib/other.py": "x = 1\n",
            }
        )

    def test_a_ticket_is_titled_by_its_first_heading_line(self):
        self.assertEqual(title_of(self.out, "ticket", "0004"), "Plain title")
        self.assertIn("Perimeter and title", title_of(self.out, "ticket", "0001"))

    def test_perimeter_edges_run_to_each_tracked_path_a_glob_matches(self):
        self.assertEqual(
            {dst for src, dst in edges(self.out, "perimeter") if src == "0001"},
            {"svc/a.py", "svc/sub/deep.py", "svc/test_a.py", "docs/guide.md", "lib/mod1.py"},
        )

    def test_a_ticket_without_a_perimeter_has_no_perimeter_edges(self):
        self.assertEqual({src for src, _ in edges(self.out, "perimeter")}, {"0001"})

    def test_a_feature_label_declares_a_feature(self):
        self.assertEqual(names(self.out, "feature"), {"checkout", "cart"})
        self.assertEqual(
            edges(self.out, "declares"),
            {("checkout", "0001"), ("checkout", "0002"), ("cart", "0002")},
        )


class Features(MapCase):
    def test_a_label_without_the_prefix_declares_nothing(self):
        _, out = self.built(
            {
                "tickets/0001.md": "# 0001 — A\n\n- Labels: bug, svc/backend, checkout, features, my-feature:x\n",
                "tickets/0002.md": "# 0002 — B\n\n- Status: open\n\nfeature:ghost\n",
            }
        )
        self.assertEqual(names(out, "feature"), set())
        self.assertEqual(edges(out, "declares"), set())


class History(MapCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        repo = cls.new_repo()
        repo.commit(
            {
                "tickets/0002.md": "# 0002 — Two\n",
                "tickets/0003.md": "# 0003 — Three\n",
                "svc/a.py": "x = 1\n",
                "svc/b.py": "x = 1\n",
                "svc/c.py": "x = 1\n",
                "svc/d.py": "x = 1\n",
                "svc/gone.py": "x = 1\n",
            },
            "base",
        )
        repo.git("checkout", "-q", "-b", "ticket/0003")
        repo.commit({"svc/b.py": "x = 2\n", "svc/c.py": "x = 2\n"}, "wip")
        repo.git("checkout", "-q", "main")
        repo.commit({"svc/a.py": "x = 2\n"}, "fix a (ticket 0002)")
        repo.commit({"svc/gone.py": "x = 2\n"}, "touch gone\n\nRefs ticket/0002")
        repo.commit(delete=["svc/gone.py"], message="remove gone")
        repo.commit({"svc/d.py": "x = 2\n"}, "hotfix ticket 0099")
        repo.git("merge", "--no-ff", "-q", "-m", "Merge pull request #4 from lights-out/ticket/0003", "ticket/0003")
        cls.repo = repo
        cls.out = cls.workdir() / "map.sqlite"
        res = cls.build_map(repo, cls.out)
        if res.code != 0:
            raise AssertionError(res.err)

    def test_history_runs_from_a_ticket_to_the_tracked_paths_its_commits_changed(self):
        self.assertEqual(
            edges(self.out, "history"),
            {("0002", "svc/a.py"), ("0003", "svc/b.py"), ("0003", "svc/c.py")},
        )

    def test_a_merge_counts_against_its_first_parent(self):
        # The branch's own commit says "wip"; only the merge commit's message names the ticket.
        self.assertIn(("0003", "svc/b.py"), edges(self.out, "history"))

    def test_a_path_deleted_since_has_no_history_edge(self):
        self.assertNotIn(("0002", "svc/gone.py"), edges(self.out, "history"))

    def test_a_commit_naming_no_ticket_the_map_holds_has_no_edge(self):
        self.assertNotIn("svc/d.py", {dst for _, dst in edges(self.out, "history")})


# -------------------------------------------------------- §3 the citations

GUIDE = page(
    [
        ("first_line", "`core/x.py` opens the page."),
        ("link_sibling", "See [a](a.md)."),
        ("link_up", "See [b](../core/x.py)."),
        ("link_wrong_dir", "See [c](docs/adr/0001-a.md)."),
        ("link_page_dir", "See [d](adr/0001-a.md)."),
        ("link_missing", "See [e](missing.md)."),
        ("link_https", "See [f](https://example.com/x/y.md)."),
        ("link_http", "See [g](http://example.com/x.md)."),
        ("link_anchor", "See [h](#top)."),
        ("two_links", "See [i](a.md) and [j](nope.md)."),
        ("root_path", "The engine is `core/x.py`."),
        ("root_dir", "The directory `core/sub/` holds more."),
        ("root_dir_bare", "The directory `core/sub` too."),
        ("root_missing", "Gone: `core/nope.py`."),
        ("root_dir_missing", "Gone: `core/nosub/`."),
        ("page_dir_path", "Records in `adr/0001-a.md`."),
        ("page_dir_missing", "Records in `adr/9999-z.md`."),
        ("suffix", "The contract file is `.contract/worker.md`."),
        ("suffix_missing", "The other file is `.contract/nope.md`."),
        ("suffix_not_a_boundary", "Not a boundary: `bc/d.py`."),
        ("glob", "All of `core/*.py`."),
        ("glob_none", "All of `core/*.rs`."),
        ("unknown_first_segment", "Either `and/or` works."),
        ("two_tokens", "Both `core/x.py` and `core/nope2.py`."),
        ("cmd_ok", "Run `./go demo` first."),
        ("cmd_bad", "Run `./go nosuch`."),
        ("make_ok", "Run `make ci`."),
        ("make_bad", "Run `make nosuch`."),
        ("cmd_hyphen", "Run `./go demo-seam`."),
        ("cmd_with_keys", "Run `./go assign TICKET=0001 MAP_BRIEF=on`."),
        ("cmd_with_unknown_key", "Run `./go demo APP_PORT=9000 GHOST_KEY=1`."),
        ("prose_cmd", "Run ./go nosuch2 to see."),
        ("prose_make", "We make sure it works; make nosuch3 is prose."),
        ("prose_key", "Set GHOST_PROSE=1 in prose."),
        ("key_ok", "Set `APP_PORT=9000`."),
        ("key_script", "Set `SCRIPT_VAR=1`."),
        ("key_markdown_only", "Set `OTHER_MD_KEY=1`."),
        ("key_self_only", "Set `GHOST_SELF=1`."),
        ("fence_open", "```sh"),
        ("f_cmd", "./go demo"),
        ("f_make_bad", "make nosuch4"),
        ("f_key_cmd", "APP_PORT=1 ./go demo-seam"),
        ("f_key_bad", "GHOST_FENCE=1 ./go demo"),
        ("f_comment", "./go demo  # then make nosuch5 and GHOST_COMMENT=1"),
        ("f_path", "cat core/nope3.py"),
        ("f_link", "[x](missing-in-fence.md)"),
        ("fence_close", "```"),
        ("after_fence", "See [y](missing-after-fence.md)."),
    ]
)

CHARS = page(
    [
        ("real", "Real: `docs/real.md`."),
        ("lt", "Template: `docs/<id>.md`."),
        ("gt", "Odd: `docs/a>b.md`."),
        ("dollar", "Shell: `docs/$HOME/x`."),
        ("open_brace", "Brace: `docs/{a.md`."),
        ("close_brace", "Brace: `docs/a}.md`."),
        ("equals", "Assign: `docs/a=b.md`."),
        ("at", "At: `docs/a@b.md`."),
        ("pipe", "Pipe: `docs/a|b.md`."),
        ("semicolon", "Semi: `docs/a;b.md`."),
        ("ellipsis_char", "Dots: `docs/a….md`."),
        ("three_dots", "Dots: `docs/a...md`."),
        ("scheme", "Url: `docs/x://y`."),
        ("space", "Spaced: `docs/a b.md`."),
    ]
)

CITATION_FILES = {
    "docs/guide.md": GUIDE[0],
    "docs/chars.md": CHARS[0],
    "docs/real.md": "# Real\n",
    "docs/a.md": "# A\n",
    "docs/notes.md": "# Notes\n\nOTHER_MD_KEY=1 is only a note.\n",
    "docs/adr/0001-a.md": "# ADR\nCites `core/nope.py` and `./go demo`.\n",
    "core/x.py": "x = 1\n",
    "core/sub/y.py": "y = 1\n",
    ".contract/other.txt": "x\n",
    "w/.contract/worker.md": "# Worker\n",
    "w/abc/d.py": "d = 1\n",
    "bc/other.txt": "x\n",
    "profiles/p.env": "APP_PORT=1\nMAP_BRIEF=off\nTICKET=\n",
    "scripts/run.sh": 'echo "$SCRIPT_VAR"\n',
    "tickets/0001.md": "# 0001 — T\n\nFiles `core/nope.py` and `./go ticketonly`.\n",
    "fixtures/case/notes.md": "Files `core/nope.py`.\n",
    "svc/fixtures/y.md": "Files `core/nope.py`.\n",
}


class Citations(MapCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.repo, cls.out = cls.built(CITATION_FILES)
        cls.rows = cites(cls.out)
        cls.lines = GUIDE[1]
        cls.char_lines = CHARS[1]

    def at(self, key, page_name="docs/guide.md"):
        return sorted((kind, ok) for src, line, kind, _, ok in self.rows if src == page_name and line == self.lines[key])

    def test_a_citation_is_located_by_its_one_based_line(self):
        self.assertEqual(self.at("first_line"), [("path", True)])

    def test_only_pages_and_adrs_cite(self):
        self.assertEqual({row[0] for row in self.rows}, {"docs/guide.md", "docs/chars.md", "docs/adr/0001-a.md"})

    def test_an_adr_is_cited_in_the_map(self):
        adr = sorted((kind, ok) for src, _, kind, _, ok in self.rows if src == "docs/adr/0001-a.md")
        self.assertEqual(adr, [("command", True), ("path", False)])

    def test_a_link_resolves_from_the_pages_directory(self):
        self.assertEqual(self.at("link_sibling"), [("path", True)])
        self.assertEqual(self.at("link_up"), [("path", True)])
        self.assertEqual(self.at("link_page_dir"), [("path", True)])
        self.assertEqual(self.at("link_missing"), [("path", False)])

    def test_a_link_relative_to_the_wrong_directory_names_nothing(self):
        self.assertEqual(self.at("link_wrong_dir"), [("path", False)])

    def test_urls_and_anchors_are_not_citations(self):
        for key in ("link_https", "link_http", "link_anchor"):
            self.assertEqual(self.at(key), [], key)

    def test_two_links_on_a_line_are_two_citations(self):
        self.assertEqual(self.at("two_links"), [("path", False), ("path", True)])

    def test_two_backticked_paths_on_a_line_are_two_citations(self):
        self.assertEqual(self.at("two_tokens"), [("path", False), ("path", True)])

    def test_a_backticked_path_resolves_from_the_root_when_it_starts_in_a_top_level_directory(self):
        self.assertEqual(self.at("root_path"), [("path", True)])
        self.assertEqual(self.at("root_missing"), [("path", False)])
        self.assertIn(
            ("docs/guide.md", self.lines["root_path"], "path", "core/x.py", True),
            self.rows,
        )

    def test_a_directory_resolves_with_or_without_the_trailing_slash(self):
        self.assertEqual(self.at("root_dir"), [("path", True)])
        self.assertEqual(self.at("root_dir_bare"), [("path", True)])
        self.assertEqual(self.at("root_dir_missing"), [("path", False)])

    def test_a_backticked_path_resolves_from_the_pages_directory_when_it_starts_there(self):
        self.assertEqual(self.at("page_dir_path"), [("path", True)])
        self.assertEqual(self.at("page_dir_missing"), [("path", False)])

    def test_a_path_that_ends_a_tracked_path_resolves(self):
        self.assertEqual(self.at("suffix"), [("path", True)])
        self.assertEqual(self.at("suffix_missing"), [("path", False)])

    def test_a_path_that_ends_a_tracked_path_only_at_a_segment_boundary(self):
        self.assertEqual(self.at("suffix_not_a_boundary"), [("path", False)])

    def test_a_glob_resolves_when_it_matches_a_tracked_path(self):
        self.assertEqual(self.at("glob"), [("path", True)])
        self.assertEqual(self.at("glob_none"), [("path", False)])

    def test_a_backticked_token_that_starts_nowhere_known_is_not_a_citation(self):
        self.assertEqual(self.at("unknown_first_segment"), [])

    def test_a_token_with_one_of_the_excluded_characters_is_not_a_citation(self):
        paths = [(line, ok) for src, line, kind, _, ok in self.rows if src == "docs/chars.md" and kind == "path"]
        self.assertEqual(paths, [(self.char_lines["real"], True)])

    def test_a_command_resolves_when_make_help_lists_its_target(self):
        self.assertEqual(self.at("cmd_ok"), [("command", True)])
        self.assertEqual(self.at("cmd_bad"), [("command", False)])
        self.assertEqual(self.at("make_ok"), [("command", True)])
        self.assertEqual(self.at("make_bad"), [("command", False)])
        self.assertEqual(self.at("cmd_hyphen"), [("command", True)])

    def test_a_command_citation_stores_the_word_it_names(self):
        stored = {
            (kind, target)
            for src, line, kind, target, _ in self.rows
            if src == "docs/guide.md" and line == self.lines["cmd_with_keys"]
        }
        self.assertEqual(stored, {("command", "assign"), ("key", "TICKET"), ("key", "MAP_BRIEF")})

    def test_a_command_line_cites_every_assignment_on_it(self):
        self.assertEqual(self.at("cmd_with_keys"), [("command", True), ("key", True), ("key", True)])
        self.assertEqual(self.at("cmd_with_unknown_key"), [("command", True), ("key", False), ("key", True)])

    def test_go_and_make_words_in_plain_prose_are_not_citations(self):
        for key in ("prose_cmd", "prose_make", "prose_key"):
            self.assertEqual(self.at(key), [], key)

    def test_a_key_resolves_when_a_tracked_file_that_is_not_markdown_names_it(self):
        self.assertEqual(self.at("key_ok"), [("key", True)])
        self.assertEqual(self.at("key_script"), [("key", True)])

    def test_a_key_that_only_markdown_names_names_nothing(self):
        self.assertEqual(self.at("key_markdown_only"), [("key", False)])
        self.assertEqual(self.at("key_self_only"), [("key", False)])

    def test_a_fenced_block_checks_commands_and_keys_but_not_paths_or_links(self):
        self.assertEqual(self.at("f_cmd"), [("command", True)])
        self.assertEqual(self.at("f_make_bad"), [("command", False)])
        self.assertEqual(self.at("f_key_cmd"), [("command", True), ("key", True)])
        self.assertEqual(self.at("f_key_bad"), [("command", True), ("key", False)])
        self.assertEqual(self.at("f_path"), [])
        self.assertEqual(self.at("f_link"), [])

    def test_a_shell_comment_in_a_fenced_block_is_not_read(self):
        self.assertEqual(self.at("f_comment"), [("command", True)])

    def test_the_fence_ends_where_it_closes(self):
        self.assertEqual(self.at("fence_close"), [])
        self.assertEqual(self.at("after_fence"), [("path", False)])


class CitationNodes(MapCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.repo, cls.out = cls.built(
            {
                "profiles/p.env": "APP_PORT=1\nMAP_BRIEF=off\n",
                "README.md": "# Readme\nUse `make ci` and `./go demo`.\nRun ./go demo-seam in prose; make sure about it.\n",
                "docs/adr/0001-a.md": "# ADR\nSet `MAP_BRIEF=on` and run `./go demo`.\n",
                "tickets/0001.md": "# 0001 — T\n\nUses `./go map` and `APP_PORT=2`.\n",
            }
        )

    def test_what_pages_and_adrs_cite_becomes_command_and_key_nodes(self):
        self.assertEqual(names(self.out, "command"), {"make ci", "./go demo"})
        self.assertEqual(names(self.out, "key"), {"MAP_BRIEF"})

    def test_a_cites_edge_runs_from_the_page_or_adr_to_what_it_cites(self):
        self.assertEqual(
            edges(self.out, "cites"),
            {
                ("README.md", "make ci"),
                ("README.md", "./go demo"),
                ("docs/adr/0001-a.md", "MAP_BRIEF"),
                ("docs/adr/0001-a.md", "./go demo"),
            },
        )


# ------------------------------------- docs/adr/0059 §3: schema 2, what search needs


class Docs(MapCase):
    """The `doc` table: one row per ADR node, its `- Status:` and its whole text."""

    FILES = {
        "docs/adr/0001-first.md": (
            "# ADR 0001 — First\n\n- Status: accepted\n- Date: 2026-11-01\n\n"
            "Body of the first, with a café — and a tab\there.\n"
        ),
        "docs/adr/0002-second.md": (
            "# ADR 0002 — Second\n\nProse before the status line.\n\n"
            "- Status:   proposed — amends ADR 0001  \n- Status: accepted\n"
        ),
        "docs/adrs/0003-third.md": "# ADR 0003 — Third\n\nNo status line here.\n",
        "adr/0004-fourth.md": "# Fourth\n\n- Status:\n",
        "docs/adr/0005-fifth.md": "# Fifth\n\nStatus: no dash, not a status line\n- Statusquo: nor this\n",
        "docs/adr/README.md": "# Index\n\n- Status: not an ADR\n",
        "docs/guide.md": "# Guide\n\n- Status: not an ADR either\n",
        "tickets/0001.md": "# 0001 — T\n\n- Status: open\n",
    }
    STATUS = {
        "docs/adr/0001-first.md": "accepted",
        "docs/adr/0002-second.md": "proposed — amends ADR 0001",
        "docs/adrs/0003-third.md": "",
        "adr/0004-fourth.md": "",
        "docs/adr/0005-fifth.md": "",
    }

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.repo, cls.out = cls.built(cls.FILES)

    def rows(self):
        return {
            name: (status, text)
            for name, status, text in query(
                self.out, "SELECT n.name, d.status, d.text FROM doc d JOIN node n ON n.id = d.node"
            )
        }

    def test_there_is_one_row_per_adr_node_and_none_for_anything_else(self):
        self.assertEqual(set(self.rows()), set(self.STATUS))
        self.assertEqual(set(self.rows()), names(self.out, "adr"))
        count = query(self.out, "SELECT COUNT(*) FROM doc")[0][0]
        self.assertEqual(count, len(self.STATUS))

    def test_the_status_is_what_follows_the_first_status_line_stripped(self):
        self.assertEqual({name: status for name, (status, _) in self.rows().items()}, self.STATUS)

    def test_a_missing_status_is_the_empty_string_not_null(self):
        for status, in query(self.out, "SELECT status FROM doc"):
            self.assertIsInstance(status, str)

    def test_the_text_is_the_whole_file(self):
        for name, (_, text) in self.rows().items():
            self.assertEqual(text, self.FILES[name], name)

    def test_doc_is_keyed_by_the_node_and_neither_text_column_takes_null(self):
        copy = self.workdir() / "doc.sqlite"
        shutil.copy(self.out, copy)
        con = sqlite3.connect(str(copy))
        try:
            node = query(copy, "SELECT node FROM doc LIMIT 1")[0][0]
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("INSERT INTO doc(node, status, text) VALUES (?, 'x', 'y')", (node,))
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("INSERT INTO doc(node, status, text) VALUES (-1, NULL, 'y')")
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("INSERT INTO doc(node, status, text) VALUES (-2, 'x', NULL)")
        finally:
            con.close()

    def test_a_map_without_adrs_has_the_table_and_no_row(self):
        _, out = self.built({"README.md": "# Readme\n"})
        self.assertEqual(query(out, "SELECT COUNT(*) FROM doc"), [(0,)])

    def test_the_same_commit_gives_the_same_doc_rows(self):
        out = self.workdir() / "again.sqlite"
        self.assertEqual(self.build_map(self.repo, out).code, 0)
        self.assertEqual(sorted(query(out, "SELECT * FROM doc")), sorted(query(self.out, "SELECT * FROM doc")))


class Mentions(MapCase):
    """`mentions` edges: from an ADR or a ticket to the ADRs (`ADR NNNN`) and
    tickets (`ticket NNNN`) its text names that the map holds. Not citations."""

    FILES = {
        "docs/adr/0001-first.md": (
            "# ADR 0001 — First\n\n"
            "See ADR 0002 and again ADR 0002; ADR 0999 is held nowhere; this is ADR 0001. "
            "Ticket 0003 and ticket 0007 asked for it; ticket 9999 is held nowhere. "
            "A neighbour in another folder is ADR 0004.\n"
        ),
        "docs/adr/0002-second.md": "# ADR 0002 — Second\n\nBuilds on ADR 0001 and on ADR 0003.\n",
        "docs/adrs/0003-third.md": (
            "# ADR 0003 — Third\n\nThese name nothing: "
            "adr 0004, ADR-0004, ADR 00041, ADR 000, ADR 12345, ticket0007, TICKET 0007, ticket 00071.\n"
        ),
        "adr/0004-fourth.md": "# Fourth\n\nA heading with no number; its number is its file name's.\n",
        "tickets/0003.md": (
            "# 0003 — Three\n\n## Perimeter\n\n- `core/x.py`\n\n"
            "This ticket 0003 follows ADR 0001 and ADR 0002, and ticket 0007, not ADR 0888.\n"
        ),
        "tickets/0007.md": "# 0007 — Seven\n\nNothing here.\n",
        "README.md": "# Readme\n\nSee ADR 0001 and ticket 0003.\n",
        "docs/guide.md": "# Guide\n\nThe decision is ADR 0002; the work is ticket 0007.\n",
        "core/x.py": "x = 1\n",
    }
    A1, A2, A3, A4 = ("docs/adr/0001-first.md", "docs/adr/0002-second.md", "docs/adrs/0003-third.md",
                      "adr/0004-fourth.md")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.repo, cls.out = cls.built(cls.FILES)

    def test_an_adr_or_a_ticket_mentions_the_adrs_and_tickets_the_map_holds(self):
        self.assertEqual(
            edges(self.out, "mentions"),
            {
                (self.A1, self.A2),
                (self.A1, self.A4),
                (self.A1, "0003"),
                (self.A1, "0007"),
                (self.A2, self.A1),
                (self.A2, self.A3),
                ("0003", self.A1),
                ("0003", self.A2),
                ("0003", "0007"),
            },
        )

    def test_an_adr_is_named_by_the_four_digits_its_file_name_starts_with(self):
        self.assertIn((self.A1, self.A4), edges(self.out, "mentions"))
        self.assertIn((self.A2, self.A3), edges(self.out, "mentions"))

    def test_a_thing_the_map_does_not_hold_is_no_edge_and_no_node(self):
        self.assertEqual(names(self.out, "adr"), {self.A1, self.A2, self.A3, self.A4})
        self.assertEqual(names(self.out, "ticket"), {"0003", "0007"})
        reached = {dst for _, dst in edges(self.out, "mentions")}
        self.assertFalse(reached & {"0999", "9999", "0888"}, reached)

    def test_nothing_mentions_itself(self):
        for src, dst in edges(self.out, "mentions"):
            self.assertNotEqual(src, dst)

    def test_only_adrs_and_tickets_mention(self):
        sources = {src for src, _ in edges(self.out, "mentions")}
        self.assertEqual(sources, {self.A1, self.A2, "0003"})

    def test_a_mention_is_one_edge_however_often_it_is_made(self):
        rows = query(self.out, "SELECT COUNT(*) FROM edge WHERE kind = 'mentions'")
        self.assertEqual(rows, [(9,)])

    def test_a_mention_is_not_a_citation(self):
        self.assertEqual(cites(self.out), [])
        self.assertEqual(edges(self.out, "cites"), set())
        self.assertEqual(names(self.out, "command") | names(self.out, "key"), set())

    def test_a_ticket_keeps_its_perimeter_and_its_citations_apart_from_its_mentions(self):
        self.assertEqual(edges(self.out, "perimeter"), {("0003", "core/x.py")})
        self.assertEqual(set(edges(self.out, "mentions")) & set(edges(self.out, "perimeter")), set())

    def test_the_same_commit_gives_the_same_mentions(self):
        out = self.workdir() / "again.sqlite"
        self.assertEqual(self.build_map(self.repo, out).code, 0)
        self.assertEqual(edges(out, "mentions"), edges(self.out, "mentions"))


class MentionsAreNotDrift(MapCase):
    """An ADR naming one the plan has reserved is not drift (docs/adr/0059 §3)."""

    BASE = {"core/x.py": "x = 1\n", "profiles/p.env": "APP_PORT=1\n"}

    def drift(self, files, *extra):
        repo = self.new_repo()
        repo.commit({**self.BASE, **files}, "base")
        return run("drift", "--repo", str(repo.path), "--targets", str(self.targets_file()), *extra)

    def test_names_of_adrs_and_tickets_the_map_does_not_hold_are_not_findings(self):
        res = self.drift(
            {
                "docs/adr/0001-a.md": "# ADR 0001\n\nSee ADR 0999 and ticket 9999, reserved by the plan.\n",
                "tickets/0001.md": "# 0001 — T\n\nSee ADR 0998 and Ticket 9998.\n",
                "README.md": "# Readme\n\nThe next decision is ADR 0997; ticket 9997 waits.\n",
                "docs/guide.md": "# Guide\n\nSee ADR 0001 and ticket 0001, which exist.\n",
            }
        )
        self.assertEqual((res.code, res.out), (0, ""))

    def test_a_real_finding_is_still_one_line_beside_the_mentions(self):
        res = self.drift(
            {
                "docs/adr/0001-a.md": "# ADR 0001\n",
                "README.md": "# Readme\n\nSee ADR 0999 and `core/gone.py`, and ticket 9999.\n",
            }
        )
        self.assertEqual((res.code, res.out), (1, "README.md:3: path core/gone.py names nothing\n"))


# --------------------------------------------------------- §3 docs-drift


class Drift(MapCase):
    GITIGNORE = ".crew/\n.env\n"

    def drift(self, repo, *extra):
        return run("drift", "--repo", str(repo.path), "--targets", str(self.targets_file()), *extra)

    def repo_of(self, files):
        repo = self.new_repo()
        repo.commit(files, "base")
        return repo

    def findings(self, res):
        return sorted(res.out.splitlines())

    BASE = {
        "core/x.py": "x = 1\n",
        "profiles/p.env": "APP_PORT=1\n",
    }

    def test_a_tree_that_cites_only_what_exists_prints_nothing_and_exits_0(self):
        repo = self.repo_of(
            {
                **self.BASE,
                "README.md": "# Readme\n\nThe engine is `core/x.py`; run `./go demo` with `APP_PORT=9000`.\n",
            }
        )
        res = self.drift(repo)
        self.assertEqual((res.code, res.out), (0, ""))

    def test_each_finding_is_one_line_naming_the_page_the_line_the_kind_and_the_target(self):
        repo = self.repo_of(
            {
                **self.BASE,
                "README.md": (
                    "# Readme\n\nSee `core/gone.py`.\n\nRun `./go nosuch`.\n\nSet `GHOST_KEY=1`.\n\n"
                    "See [x](docs/gone.md).\n"
                ),
            }
        )
        res = self.drift(repo)
        self.assertEqual(res.code, 1)
        lines = self.findings(res)
        self.assertEqual(len(lines), 4, res.out)
        self.assertIn("README.md:3: path core/gone.py names nothing", lines)
        self.assertIn("README.md:7: key GHOST_KEY names nothing", lines)
        self.assertIn("README.md:9: path docs/gone.md names nothing", lines)
        command = [line for line in lines if line.startswith("README.md:5:")]
        self.assertEqual(len(command), 1)
        self.assertRegex(command[0], r"^README\.md:5: command (?:\./go )?nosuch names nothing$")

    def test_a_page_in_a_directory_is_named_by_its_path(self):
        repo = self.repo_of({**self.BASE, "docs/guide.md": "# Guide\n\nSee `core/gone.py`.\n"})
        res = self.drift(repo)
        self.assertEqual((res.code, res.out), (1, "docs/guide.md:3: path core/gone.py names nothing\n"))

    def test_make_commands_are_judged_too(self):
        repo = self.repo_of({**self.BASE, "README.md": "# Readme\n\nRun `make nowhere` or `make ci`.\n"})
        res = self.drift(repo)
        self.assertEqual(res.code, 1)
        lines = self.findings(res)
        self.assertEqual(len(lines), 1, res.out)
        self.assertRegex(lines[0], r"^README\.md:3: command (?:make )?nowhere names nothing$")

    BAD = "Files `core/gone.py`, run `./go nosuch`, set `GHOST_KEY=1`.\n"

    def test_adrs_tickets_and_fixtures_are_not_judged(self):
        repo = self.repo_of(
            {
                **self.BASE,
                "docs/adr/0001-x.md": "# ADR\n" + self.BAD,
                "tickets/0001.md": "# 0001 — T\n" + self.BAD,
                "fixtures/f/notes.md": self.BAD,
                "README.md": "# Readme\n",
            }
        )
        res = self.drift(repo)
        self.assertEqual((res.code, res.out), (0, ""))
        (repo.path / "docs" / "page.md").write_text("# Page\n" + self.BAD, encoding="utf-8")
        res = self.drift(repo)
        self.assertEqual(res.code, 1)
        self.assertEqual(len(self.findings(res)), 3, res.out)
        self.assertTrue(all(line.startswith("docs/page.md:2: ") for line in res.out.splitlines()), res.out)

    def test_the_tickets_option_names_the_directory_that_is_not_judged(self):
        repo = self.repo_of(
            {**self.BASE, ".contract/tickets/0001.md": "# 0001 — T\n" + self.BAD, "README.md": "# Readme\n"}
        )
        self.assertEqual(self.drift(repo, "--tickets", ".contract/tickets").code, 0)
        self.assertEqual(self.drift(repo).code, 1)

    def test_excluded_globs_are_not_judged(self):
        bad = "# Page\n" + self.BAD
        repo = self.repo_of(
            {
                **self.BASE,
                "docs/PLAN.md": bad,
                "docs/plans/p.md": bad,
                "docs/plans/deep/q.md": bad,
                ".claude/n.md": bad,
                "docs/guide.md": bad,
            }
        )
        everything = self.drift(repo)
        self.assertEqual(everything.code, 1)
        self.assertEqual(len(self.findings(everything)), 15, everything.out)
        res = self.drift(repo, "--exclude", "docs/PLAN.md docs/plans/* .claude/*")
        self.assertEqual(res.code, 1)
        self.assertEqual(len(self.findings(res)), 3, res.out)
        self.assertTrue(all(line.startswith("docs/guide.md:2: ") for line in res.out.splitlines()), res.out)

    def test_a_known_name_resolves(self):
        repo = self.repo_of(
            {
                **self.BASE,
                "README.md": "# Readme\n\nSet `CONTAINER_CONNECTION=podman` and `OTHER_NAME=1`.\n",
            }
        )
        res = self.drift(repo)
        self.assertEqual(sorted(line.split(" names")[0] for line in res.out.splitlines()), [
            "README.md:3: key CONTAINER_CONNECTION",
            "README.md:3: key OTHER_NAME",
        ])
        res = self.drift(repo, "--known", "CONTAINER_CONNECTION")
        self.assertEqual((res.code, res.out), (1, "README.md:3: key OTHER_NAME names nothing\n"))
        res = self.drift(repo, "--known", "CONTAINER_CONNECTION", "--known", "OTHER_NAME")
        self.assertEqual((res.code, res.out), (0, ""))

    def test_it_reads_the_working_tree_not_the_commit(self):
        repo = self.repo_of({**self.BASE, "README.md": "# Readme\n\nThe engine is `core/x.py`.\n"})
        self.assertEqual(self.drift(repo).code, 0)
        repo.write({"README.md": "# Readme\n\nThe engine is `core/gone.py`.\n"})
        res = self.drift(repo)
        self.assertEqual((res.code, res.out), (1, "README.md:3: path core/gone.py names nothing\n"))

    def test_an_untracked_page_is_judged(self):
        repo = self.repo_of({**self.BASE, "README.md": "# Readme\n"})
        repo.write({"docs/new.md": "# New\n\nSee `core/gone.py`.\n"})
        res = self.drift(repo)
        self.assertEqual((res.code, res.out), (1, "docs/new.md:3: path core/gone.py names nothing\n"))

    def test_an_untracked_file_is_something_a_page_can_name(self):
        repo = self.repo_of({**self.BASE, "README.md": "# Readme\n\nSee `core/new.py`.\n"})
        self.assertEqual(self.drift(repo).code, 1)
        repo.write({"core/new.py": "x = 1\n"})
        res = self.drift(repo)
        self.assertEqual((res.code, res.out), (0, ""))

    def test_a_key_the_working_tree_spells_resolves(self):
        repo = self.repo_of({**self.BASE, "README.md": "# Readme\n\nSet `NEW_KEY=1`.\n"})
        self.assertEqual(self.drift(repo).code, 1)
        repo.write({"profiles/p.env": "APP_PORT=1\nNEW_KEY=2\n"})
        self.assertEqual(self.drift(repo).code, 0)

    def test_a_path_git_ignores_is_not_a_finding(self):
        files = {**self.BASE, "README.md": "# Readme\n\nThe map is `.crew/map.sqlite`.\n"}
        control = self.repo_of(files)
        control.write({".crew/run.json": "{}\n"})
        res = self.drift(control)
        self.assertEqual((res.code, res.out), (1, "README.md:3: path .crew/map.sqlite names nothing\n"))
        ignoring = self.repo_of({**files, ".gitignore": self.GITIGNORE})
        ignoring.write({".crew/run.json": "{}\n"})
        res = self.drift(ignoring)
        self.assertEqual((res.code, res.out), (0, ""))


# ------------------------------------------------------------- §5 the slice

SLICE_FILES = {
    "svc/a_main.py": "def serve():\n    pass\n\n\nclass Cfg:\n    def load(self):\n        pass\n",
    "svc/b_util.py": "def helper():\n    pass\n",
    "svc/c_extra.py": "X = 1\n",
    "svc/test_a_main.py": "import a_main\n\n\ndef test_it():\n    pass\n",
    "svc/test_b_util.py": "import b_util\n\n\ndef test_it():\n    pass\n",
    "docs/adr/0042-the-app.md": "# ADR 42\n\nThe entry is `svc/a_main.py`.\n",
    "docs/adr/0043-other.md": "# ADR 43\n\nThe helpers are `svc/b_util.py`.\n",
    "docs/adr/0044-lib.md": "# ADR 44\n\nThe library is `lib/unrelated.py`.\n",
    "docs/app.md": "# App\n\nSee `svc/a_main.py`.\n",
    "docs/unrelated.md": "# Unrelated\n\nSee `lib/unrelated.py`.\n",
    "lib/unrelated.py": "y = 1\n",
    "tickets/0077.md": "# 0077 — History\n\n## Perimeter\n\n- `lib/*.py`\n",
    "tickets/0078.md": "# 0078 — Perimeter\n\n## Perimeter\n\n- `svc/a_main.py`\n- `svc/b_*.py`\n",
    "tickets/0079.md": "# 0079 — Elsewhere\n\n## Perimeter\n\n- `lib/*.py`\n",
}

SLICE_TICKET = "# 9999 — Slice me\n\n## Perimeter\n\n- `svc/a_main.py`\n- `svc/b_*.py`\n\n## Problem\n\nText.\n"


class Slice(MapCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        repo = cls.new_repo()
        repo.commit(SLICE_FILES, "base")
        cls.sha = repo.commit({"svc/a_main.py": SLICE_FILES["svc/a_main.py"] + "\n\nTWO = 2\n"}, "fix serve (ticket 0077)")
        cls.out = cls.workdir() / "map.sqlite"
        res = cls.build_map(repo, cls.out)
        if res.code != 0:
            raise AssertionError(res.err)
        cls.repo = repo
        cls.ticket = cls.workdir() / "ticket.md"
        cls.ticket.write_text(SLICE_TICKET, encoding="utf-8")

    def slice(self, ticket_text=None, base=None, map_file=None):
        ticket = self.ticket
        if ticket_text is not None:
            ticket = self.workdir() / "ticket.md"
            ticket.write_text(ticket_text, encoding="utf-8")
        return run(
            "slice", "--map", str(map_file or self.out), "--base", base or self.sha, "--ticket", str(ticket)
        )

    def test_it_lists_what_the_perimeter_reaches(self):
        res = self.slice()
        self.assertEqual(res.code, 0, res.err)
        for want in (
            "svc/a_main.py",
            "svc/b_util.py",
            "docs/adr/0042-the-app.md",
            "docs/adr/0043-other.md",
            "docs/app.md",
            "svc/test_a_main.py",
            "svc/test_b_util.py",
            "0077",
            "0078",
            "Cfg.load",
            "helper",
        ):
            self.assertIn(want, res.out, want)

    def test_it_leaves_out_what_the_perimeter_does_not_reach(self):
        res = self.slice()
        for unwanted in ("svc/c_extra.py", "docs/unrelated.md", "lib/unrelated.py", "0079", "docs/adr/0044-lib.md"):
            self.assertNotIn(unwanted, res.out, unwanted)

    def test_a_ticket_that_touched_a_path_by_history_or_by_perimeter_is_listed(self):
        # 0077 only by the commit that names it, 0078 only by its perimeter.
        res = self.slice()
        self.assertIn("0077", res.out)
        self.assertIn("0078", res.out)

    def test_every_list_is_sorted(self):
        out = self.slice().out
        for first, second in (
            ("svc/a_main.py", "svc/b_util.py"),
            ("docs/adr/0042-the-app.md", "docs/adr/0043-other.md"),
            ("svc/test_a_main.py", "svc/test_b_util.py"),
            ("0077", "0078"),
        ):
            self.assertLess(out.index(first), out.index(second), (first, second))
        self.assertLess(out.index("Cfg.load"), re.search(r"\bserve\b", out).start())

    def test_a_list_with_nothing_in_it_says_none(self):
        res = self.slice("# T\n\n## Perimeter\n\n- `svc/c_extra.py`\n")
        self.assertEqual(res.code, 0, res.err)
        self.assertIn("svc/c_extra.py", res.out)
        self.assertGreaterEqual(len(re.findall(r"\bnone\b", res.out)), 4, res.out)

    def test_a_slice_with_every_list_filled_says_none_nowhere(self):
        self.assertNotRegex(self.slice().out, r"\bnone\b")

    def test_a_glob_that_matches_nothing_yet_is_listed(self):
        res = self.slice("# T\n\n## Perimeter\n\n- `svc/future/*.py`\n- `svc/c_extra.py`\n")
        self.assertEqual(res.code, 0, res.err)
        self.assertIn("svc/future/*.py", res.out)
        self.assertIn("svc/c_extra.py", res.out)

    def test_the_same_map_and_ticket_give_the_same_slice(self):
        self.assertEqual(self.slice().out, self.slice().out)

    def test_a_missing_map_is_refused_naming_go_map(self):
        res = self.slice(map_file=self.workdir() / "absent.sqlite")
        self.assertRefused(res)
        self.assertIn("./go map", res.err)

    def test_a_map_built_at_another_commit_is_refused_naming_both_shas_and_go_map(self):
        other = "a" * 40
        res = self.slice(base=other)
        self.assertRefused(res)
        self.assertIn(other, res.err)
        self.assertIn(self.sha, res.err)
        self.assertIn("./go map", res.err)

    def test_a_map_of_another_schema_is_refused(self):
        for other in ("1", "3", "banana"):
            copy = self.workdir() / "other-schema.sqlite"
            shutil.copy(self.out, copy)
            con = sqlite3.connect(str(copy))
            try:
                con.execute("UPDATE meta SET value = ? WHERE key = 'schema'", (other,))
                con.commit()
            finally:
                con.close()
            res = self.slice(map_file=copy)
            self.assertRefused(res)
            self.assertTrue("schema" in res.err.lower() or "./go map" in res.err, res.err)

    def test_a_map_of_schema_1_is_refused_naming_go_map(self):
        """docs/adr/0059 §3: M28's maps are schema 1; every reader refuses them."""
        copy = self.workdir() / "schema-1.sqlite"
        shutil.copy(self.out, copy)
        con = sqlite3.connect(str(copy))
        try:
            con.execute("UPDATE meta SET value = '1' WHERE key = 'schema'")
            con.commit()
        finally:
            con.close()
        res = self.slice(map_file=copy)
        self.assertRefused(res)
        self.assertTrue("schema" in res.err.lower() or "./go map" in res.err, res.err)
        self.assertEqual(str(meta(self.out)["schema"]), "2")
        self.assertEqual(self.slice().code, 0)

    def test_a_ticket_without_a_perimeter_is_refused(self):
        res = self.slice("# T\n\n## Problem\n\nText.\n")
        self.assertRefused(res)
        self.assertIn("perimeter", res.err.lower())


# ----------------------------------------------------------- §4 after merge

STUB_PUT = """\
set -eu
dir=$STUB_DIR
n=0
[ ! -f "$dir/count" ] || n=$(cat "$dir/count")
echo $((n + 1)) > "$dir/count"
printf '%s' "$1" > "$dir/title"
printf '%s' "$2" > "$dir/origin"
cat > "$dir/body"
printf '0042\\n'
"""

FAIL_PUT = """\
cat > /dev/null
echo 'stub-fail: refusing to file' >&2
exit 1
"""

BASE_DOCS = {
    "core/sub/x.py": "x = 1\n",
    "core/sub/y.py": "y = 1\n",
    "lib/z.py": "z = 1\n",
    "docs/guide.md": "# Guide\n\nThe engine is `core/sub/x.py`.\n",
    "docs/adr/0001-engine.md": "# ADR 1\n\nSee `core/sub/x.py`.\n",
    "docs/dir.md": "# Dir\n\nEverything in `core/sub/` matters.\n",
    "docs/link.md": "# Link\n\nSee [the engine](../core/sub/x.py).\n",
    "docs/layout.md": "# Layout\n\nThe code lives in `core/`.\n",
    "docs/other.md": "# Other\n\nSee `lib/z.py`.\n",
    "tickets/0001.md": "# 0001 — T\n\nTouches `core/sub/x.py`.\n",
}
CITING = {"docs/guide.md", "docs/adr/0001-engine.md", "docs/dir.md", "docs/link.md"}


class AfterMerge(MapCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._hosts = {}

    def setUp(self):
        self.root = self.workdir()
        files = {
            "adapters/stub-tracker/put.sh": STUB_PUT,
            "adapters/stub-fail/put.sh": FAIL_PUT,
            "adapters/file/put.sh": (ROOT / "adapters" / "file" / "put.sh").read_text(encoding="utf-8"),
        }
        for rel, body in files.items():
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
        (self.root / "stub").mkdir()
        (self.root / "filed").mkdir()
        patch = mock.patch.dict(
            os.environ,
            {"TRACKER": "stub-tracker", "STUB_DIR": str(self.root / "stub"), "TICKETS_DIR": str(self.root / "filed")},
        )
        patch.start()
        self.addCleanup(patch.stop)
        previous = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        self.map_file = self.root / "map.sqlite"

    @classmethod
    def merged(cls, base, branch, main=None, branch_delete=()):
        """A code host whose main took `branch` through a merge commit; (repo, merge sha)."""
        repo = Repo(cls.workdir() / "host")
        repo.commit(base, "base")
        repo.git("checkout", "-q", "-b", "feature")
        repo.commit(branch, "feature work", delete=branch_delete)
        repo.git("checkout", "-q", "main")
        if main:
            repo.commit(main, "main moves on")
        repo.git("merge", "--no-ff", "-q", "-m", "Merge feature", "feature")
        return repo, repo.head()

    @classmethod
    def engine(cls):
        """The merge most tests share: BASE_DOCS and a change to core/sub/x.py. Read-only, built once."""
        if "engine" not in cls._hosts:
            cls._hosts["engine"] = cls.merged(BASE_DOCS, {"core/sub/x.py": "x = 2\n"})
        return cls._hosts["engine"]

    def after_merge(self, repo, sha, *extra):
        return run(
            "after-merge",
            "--clone-url", str(repo.path),
            "--merge-sha", sha,
            "--targets", str(self.targets_file()),
            "--out", str(self.map_file),
            *extra,
        )

    def stub(self, name):
        path = self.root / "stub" / name
        return path.read_text(encoding="utf-8") if path.exists() else None

    def assertReport(self, res, sha, docs_ticket):
        self.assertEqual(res.code, 0, res.err)
        self.assertEqual(res.out.count("\n"), 1, res.out)
        doc = json.loads(res.out)
        self.assertEqual(list(doc), ["map"])
        self.assertEqual(set(doc["map"]), {"sha", "file", "docs_ticket"})
        self.assertEqual(doc["map"]["sha"], sha)
        self.assertEqual(Path(doc["map"]["file"]).resolve(), self.map_file.resolve())
        self.assertEqual(doc["map"]["docs_ticket"], docs_ticket)
        self.assertEqual(meta(self.map_file)["sha"], sha)

    def assertPerimeter(self, body, documents):
        self.assertIn("## Perimeter", body.splitlines())
        self.assertEqual(sorted(perimeter_lines(body)), sorted(f"- `{path}`" for path in documents))

    def test_one_ticket_lists_the_documents_that_cite_a_changed_path(self):
        repo, sha = self.engine()
        res = self.after_merge(repo, sha)
        self.assertReport(res, sha, "0042")
        self.assertEqual(self.stub("count").strip(), "1")
        self.assertEqual(self.stub("origin"), f"docs merge {sha}")
        self.assertTrue(self.stub("title").strip())
        self.assertPerimeter(self.stub("body"), CITING)

    def test_a_directory_of_two_segments_covers_the_paths_below_it_and_a_top_level_one_does_not(self):
        repo, sha = self.engine()
        self.after_merge(repo, sha)
        body = self.stub("body")
        self.assertIn("- `docs/dir.md`", body.splitlines())
        self.assertNotIn("- `docs/layout.md`", body.splitlines())

    def test_a_link_to_a_changed_path_is_a_citation_of_it(self):
        repo, sha = self.engine()
        self.after_merge(repo, sha)
        self.assertIn("- `docs/link.md`", self.stub("body").splitlines())

    def test_a_tickets_citation_is_not_a_page_and_not_in_the_perimeter(self):
        repo, sha = self.engine()
        self.after_merge(repo, sha)
        self.assertNotIn("- `tickets/0001.md`", self.stub("body").splitlines())

    def test_a_top_level_directory_cited_alone_files_nothing(self):
        repo, sha = self.merged(
            {"core/sub/x.py": "x = 1\n", "docs/layout.md": "# Layout\n\nThe code lives in `core/`.\n"},
            {"core/sub/x.py": "x = 2\n"},
        )
        res = self.after_merge(repo, sha)
        self.assertReport(res, sha, None)
        self.assertIsNone(self.stub("count"))

    def test_a_merge_touching_only_uncited_files_files_nothing(self):
        repo, sha = self.merged({**BASE_DOCS, "svc/uncited.py": "u = 1\n"}, {"svc/uncited.py": "u = 2\n"})
        res = self.after_merge(repo, sha)
        self.assertReport(res, sha, None)
        self.assertIsNone(self.stub("count"))

    def test_a_document_the_merge_changed_itself_is_not_in_the_perimeter(self):
        repo, sha = self.merged(
            BASE_DOCS,
            {"core/sub/x.py": "x = 2\n", "docs/guide.md": "# Guide\n\nThe engine, rewritten: `core/sub/x.py`.\n"},
        )
        res = self.after_merge(repo, sha)
        self.assertReport(res, sha, "0042")
        self.assertPerimeter(self.stub("body"), CITING - {"docs/guide.md"})

    def test_when_the_merge_changed_every_citing_document_nothing_is_filed(self):
        repo, sha = self.merged(
            {"core/sub/x.py": "x = 1\n", "docs/guide.md": "# Guide\n\n`core/sub/x.py`.\n"},
            {"core/sub/x.py": "x = 2\n", "docs/guide.md": "# Guide\n\nAgain `core/sub/x.py`.\n"},
        )
        res = self.after_merge(repo, sha)
        self.assertReport(res, sha, None)
        self.assertIsNone(self.stub("count"))

    def test_an_excluded_page_is_not_in_the_perimeter(self):
        base = {
            **BASE_DOCS,
            "docs/plans/p.md": "# Plan\n\nWill change `core/sub/x.py`.\n",
            "docs/plans/deep/q.md": "# Deep plan\n\nWill change `core/sub/x.py`.\n",
            ".claude/notes.md": "# Notes\n\n`core/sub/x.py` was edited on a day.\n",
        }
        repo, sha = self.merged(base, {"core/sub/x.py": "x = 2\n"})
        res = self.after_merge(repo, sha, "--exclude", "docs/plans/* .claude/*")
        self.assertReport(res, sha, "0042")
        self.assertPerimeter(self.stub("body"), CITING)
        self.assertEqual(meta(self.map_file)["exclude"], "docs/plans/* .claude/*")

    def test_without_the_exclude_list_the_same_pages_are_in_it(self):
        base = {**BASE_DOCS, "docs/plans/p.md": "# Plan\n\nWill change `core/sub/x.py`.\n"}
        repo, sha = self.merged(base, {"core/sub/x.py": "x = 2\n"})
        self.after_merge(repo, sha)
        self.assertPerimeter(self.stub("body"), CITING | {"docs/plans/p.md"})

    def test_the_diff_is_against_the_first_parent(self):
        repo, sha = self.merged(
            BASE_DOCS,
            {"core/sub/x.py": "x = 2\n"},
            main={"lib/z.py": "z = 2\n"},
        )
        res = self.after_merge(repo, sha)
        self.assertReport(res, sha, "0042")
        self.assertPerimeter(self.stub("body"), CITING)
        self.assertNotIn("- `docs/other.md`", self.stub("body").splitlines())

    def test_a_deleted_path_is_a_changed_path(self):
        repo, sha = self.merged(
            {"core/sub/x.py": "x = 1\n", "core/sub/y.py": "y = 1\n", "docs/guide.md": "# Guide\n\n`core/sub/x.py`.\n"},
            {},
            branch_delete=["core/sub/x.py"],
        )
        res = self.after_merge(repo, sha)
        self.assertReport(res, sha, "0042")
        self.assertPerimeter(self.stub("body"), {"docs/guide.md"})

    def test_the_ticket_is_filed_through_the_tracker_in_the_environment(self):
        repo, sha = self.engine()
        os.environ["TRACKER"] = "file"
        res = self.after_merge(repo, sha)
        self.assertReport(res, sha, "0001")
        filed = (self.root / "filed" / "0001.md").read_text(encoding="utf-8")
        self.assertIn(f"- Origin: docs merge {sha}", filed.splitlines())
        self.assertPerimeter(filed, CITING)
        self.assertIsNone(self.stub("count"))

    def test_a_rerun_files_nothing_new(self):
        repo, sha = self.engine()
        os.environ["TRACKER"] = "file"
        first = self.after_merge(repo, sha)
        self.assertReport(first, sha, "0001")
        filed = self.root / "filed" / "0001.md"
        before = filed.read_bytes()
        second = self.after_merge(repo, sha)
        self.assertReport(second, sha, "0001")
        self.assertEqual(sorted(path.name for path in (self.root / "filed").iterdir()), ["0001.md"])
        self.assertEqual(filed.read_bytes(), before)

    def test_the_tickets_option_reaches_the_map_it_builds(self):
        base = {**BASE_DOCS, ".contract/tickets/0007.md": "# 0007 — Attached\n"}
        repo, sha = self.merged(base, {"core/sub/x.py": "x = 2\n"})
        res = self.after_merge(repo, sha, "--tickets", ".contract/tickets")
        self.assertReport(res, sha, "0042")
        self.assertEqual(meta(self.map_file)["tickets"], ".contract/tickets")
        self.assertEqual(names(self.map_file, "ticket"), {"0007"})

    def test_a_tracker_that_fails_fails_the_command(self):
        repo, sha = self.engine()
        os.environ["TRACKER"] = "stub-fail"
        res = self.after_merge(repo, sha)
        self.assertRefused(res, one_line=False)

    def test_a_short_merge_sha_is_refused(self):
        repo, sha = self.engine()
        res = self.after_merge(repo, sha[:12])
        self.assertRefused(res)
        self.assertIsNone(self.stub("count"))

    def test_a_sha_the_clone_does_not_hold_is_refused(self):
        repo, _ = self.engine()
        res = self.after_merge(repo, "0" * 40)
        self.assertRefused(res, one_line=False)
        self.assertIsNone(self.stub("count"))

    def test_a_clone_url_that_cannot_be_cloned_is_refused(self):
        res = run(
            "after-merge",
            "--clone-url", str(self.root / "no-such-repository"),
            "--merge-sha", "a" * 40,
            "--targets", str(self.targets_file()),
            "--out", str(self.map_file),
        )
        self.assertRefused(res, one_line=False)


# One fixture that holds every kind of node and edge, for the determinism tests.
RICH = {
    "tickets/0001.md": TICKET_ONE,
    "tickets/0002.md": "# 0002 — Cart\n\n- Labels: feature:checkout, feature:cart\n\n## Perimeter\n\n- `web/*.js`\n",
    "svc/a.py": PYTHON,
    "svc/test_a.py": "import a\n\n\nclass TestA:\n    def test_a(self):\n        pass\n",
    "svc/sub/deep.py": "from .. import a\n",
    "svc/readme.txt": "APP_PORT=1\n",
    "lib/mod1.py": "x = 1\n",
    "web/app.js": JAVASCRIPT + "const lib = require('./lib');\n",
    "web/lib.js": "exports.x = 1;\n",
    "web/app.test.js": "const app = require('./app');\n",
    "docs/guide.md": "# Guide\n\nSee `svc/a.py`, `./go demo` and `APP_PORT=1`; also [x](../lib/mod1.py).\n",
    "docs/adr/0001-first.md": "# ADR\n\nCites `svc/gone.py` and `make ci`.\n",
    "README.md": "# Readme\n\n```sh\nGHOST=1 ./go map  # note\n```\n",
}


if __name__ == "__main__":
    unittest.main()

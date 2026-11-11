"""Tests for `python3 -m core mcp`, `spec` and `map`, written from
docs/adr/0069 §5-§7 and the acceptance criteria of M39's first slice in
docs/PLAN.md, never from the implementation.

Black box. A fixture repository is built with git (an ADR and a page citing
a module, the module, its test, a ticket whose perimeter matches the module,
a commit whose message names the ticket), its map with `core.map.build`, and
the server is a subprocess that gets newline-delimited JSON-RPC on stdin and
is read on stdout. The package commands are subprocesses too, judged on their
stdout line and exit code. Each docstring names the ADR section it comes from.

Where the ADR leaves a form open the tests accept the forms it allows:
  - an answer is `content[0].text`; its first line names the map's sha, the
    item lines are `- <item>` and the item's first word is the path (a
    trailing note such as the slice's ` (covers ...)` is allowed), an empty
    list is `none` or `- none`;
  - the ticket is named by its id `0001` or its path `tickets/0001.md`.
Not asserted, because the ADR does not say: the wording of any refusal beyond
what §7 requires it to name; `structuredContent` (allowed, not required); the
headings of an answer; an absolute path that lies inside the repository.
"""

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

from core import map as projmap

ROOT = Path(__file__).resolve().parents[2]
HEX40 = re.compile(r"^[0-9a-f]{40}$")
MODERN, LEGACY = "2026-07-28", "2025-11-25"
VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
CAPS_KEY = "io.modelcontextprotocol/clientCapabilities"
TOOLS = ["adrs_for_path", "tests_for_path", "tickets_for_path", "check_spec"]
DASH = "—"

MODULE = "pkg/mod.py"
TEST = "tests/test_mod.py"
ADR = "docs/adr/0001-x.md"
PAGE = "docs/page.md"
TICKET = "tickets/0001.md"

GOOD_SPEC = """# 0099 — a request

## Problem

Something is wrong.

## Acceptance criteria

Given a event at capacity
When a new member signs up
Then they join the waiting list instead of getting a 409

Given a waiting list with one member, when an attendee cancels, then the
first member on the list is promoted to attendee

## Perimeter

- `src/events/*.py`
"""
VAGUE_SPEC = GOOD_SPEC.replace(
    "Then they join the waiting list instead of getting a 409",
    "Then the signup works correctly")

FILES = {
    "pkg/__init__.py": "",
    MODULE: "def add(a, b):\n    return a + b\n",
    "tests/__init__.py": "",
    TEST: ("import unittest\n\nfrom pkg import mod\n\n\nclass T(unittest.TestCase):\n"
           "    def test_add(self):\n        self.assertEqual(mod.add(1, 2), 3)\n"),
    ADR: "# ADR 0001 — x\n\n- Status: accepted\n\nThe module is `pkg/mod.py`.\n",
    PAGE: "# A page\n\nIt documents `pkg/mod.py`.\n",
    TICKET: ("# 0001 — a change to the module\n\n- Status: open\n\n## Problem\n\nIt adds.\n\n"
             "## Perimeter\n\n- `pkg/*.py`\n"),
}


def env(**extra):
    out = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    out.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, NO_COLOR="1",
               GIT_AUTHOR_NAME="scratch", GIT_AUTHOR_EMAIL="scratch@localhost.invalid",
               GIT_COMMITTER_NAME="scratch", GIT_COMMITTER_EMAIL="scratch@localhost.invalid",
               PYTHONPATH=str(ROOT), PYTHONSAFEPATH="1")
    out.update(extra)
    return out


def git(repo, *args):
    p = subprocess.run(["git", "-c", "commit.gpgsign=false", "-C", str(repo), *args],
                       env=env(), capture_output=True, text=True)
    if p.returncode:
        raise AssertionError(f"git {' '.join(args)}: {p.stderr}")
    return p.stdout.strip()


def commit(repo, message, files=None):
    for rel, body in (files or {}).items():
        target = Path(repo) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def make_repo(parent, name="repo"):
    """The fixture repository; returns (path, sha of its only commit)."""
    repo = Path(parent) / name
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    return repo, commit(repo, "ticket 0001: add the module", FILES)


def build_map(repo, out):
    return projmap.build(str(repo), "HEAD", str(out), "tickets")[0]


def msg(id_, method, params=None, meta=True):
    out = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None or meta:
        out["params"] = dict(params or {})
        if meta:
            out["params"]["_meta"] = {VERSION_KEY: MODERN, CAPS_KEY: {}}
    return out


def call(id_, tool, meta=True, **arguments):
    return msg(id_, "tools/call", {"name": tool, "arguments": arguments}, meta)


class Session:
    def __init__(self, replies, lines, err, code):
        self.replies, self.lines, self.err, self.code = replies, lines, err, code

    def __getitem__(self, id_):
        return self.replies[id_]

    def answer(self, id_):
        """(isError, text) of a tools/call reply that is a result."""
        reply = self.replies[id_]
        assert "result" in reply, reply
        result = reply["result"]
        content = result["content"]
        assert content[0]["type"] == "text", content
        return bool(result.get("isError")), content[0]["text"]


def serve(messages, repo, mapfile=None, args=None):
    """Write MESSAGES (dicts) to the server, close stdin, collect what it said."""
    argv = [sys.executable, "-m", "core", "mcp", "--repo", str(repo)]
    if mapfile is not None:
        argv += ["--map", str(mapfile)]
    argv += args or []
    stdin = "".join(json.dumps(m) + "\n" for m in messages)
    p = subprocess.run(argv, input=stdin, cwd=ROOT, env=env(), capture_output=True, text=True,
                       encoding="utf-8", timeout=120)
    lines = [ln for ln in p.stdout.splitlines() if ln.strip()]
    replies = {}
    for ln in lines:
        doc = json.loads(ln)
        if "id" in doc:
            replies[doc["id"]] = doc
    return Session(replies, lines, p.stderr, p.returncode)


def items(text):
    """The item lines of an answer, as the first word after `- `."""
    return [ln[2:].split(" ")[0] if not ln.startswith("- none") else "none"
            for ln in text.splitlines() if ln.startswith("- ")]


class Fixture(unittest.TestCase):
    """A scratch repository and the map built at its commit, shared by a class."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="mcp-")).resolve()
        cls.repo, cls.sha = make_repo(cls.tmp)
        cls.map = cls.tmp / "map.sqlite"
        build_map(cls.repo, cls.map)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, True)

    def ask(self, tool, **arguments):
        s = serve([call(1, tool, **arguments)], self.repo, self.map)
        return s.answer(1)

    def assert_answer(self, tool, path, want, absent=()):
        """§7: the sha, then sorted `- <item>` lines; WANT among them, ABSENT not."""
        is_error, text = self.ask(tool, path=path)
        self.assertFalse(is_error, text)
        self.assertIn(self.sha, text)
        found = items(text)
        self.assertEqual(found, sorted(found), "the lines are sorted")
        for item in want:
            self.assertTrue(any(item in f for f in found), (item, text))
        for item in absent:
            self.assertFalse(any(item in f for f in found), (item, text))
        return text


# --------------------------------------------------------------- §7 tools

class Tools(Fixture):
    def test_tools_list_is_the_four_tools_in_order_each_read_only(self):
        """§7: four tools in this order, each readOnlyHint true, one string argument."""
        s = serve([msg(1, "tools/list")], self.repo, self.map)
        tools = s[1]["result"]["tools"]
        self.assertEqual([t["name"] for t in tools], TOOLS)
        for tool in tools:
            self.assertIs(tool["annotations"]["readOnlyHint"], True, tool["name"])
            schema = tool["inputSchema"]
            self.assertEqual(schema["type"], "object")
            (arg, spec), = schema["properties"].items()
            self.assertEqual(spec["type"], "string")
            self.assertEqual(arg, "text" if tool["name"] == "check_spec" else "path", tool["name"])

    def test_tools_list_is_deterministic(self):
        """§Verified: tools/list is deterministic."""
        a = serve([msg(1, "tools/list")], self.repo, self.map)
        b = serve([msg(1, "tools/list")], self.repo, self.map)
        self.assertEqual(a[1]["result"]["tools"], b[1]["result"]["tools"])

    def test_adrs_for_path_lists_the_adr_then_the_page(self):
        """§7: ADRs, then pages, citing the path."""
        text = self.assert_answer("adrs_for_path", MODULE, [ADR, PAGE])
        self.assertLess(text.index(ADR), text.index(PAGE))

    def test_adrs_for_a_path_nothing_cites_is_none(self):
        """§7: `none` when empty."""
        text = self.assert_answer("adrs_for_path", TEST, [], absent=[ADR, PAGE])
        self.assertTrue("none" in items(text) or "none" in text.splitlines())

    def test_tests_for_path_lists_the_test_that_imports_the_module(self):
        """§7: `tests` edges to the path."""
        self.assert_answer("tests_for_path", MODULE, [TEST])

    def test_tests_for_path_of_a_test_lists_itself(self):
        """§7: or itself if the path is a test."""
        self.assert_answer("tests_for_path", TEST, [TEST])

    def test_tests_for_a_path_no_test_covers_is_none(self):
        """§7: `none` when empty."""
        text = self.assert_answer("tests_for_path", PAGE, [], absent=[TEST])
        self.assertTrue("none" in items(text) or "none" in text.splitlines())

    def test_tickets_for_path_names_the_ticket_with_its_kinds(self):
        """§7: `perimeter` and `history` edges, with their kind."""
        text = self.assert_answer("tickets_for_path", MODULE, ["0001"])
        self.assertIn("perimeter", text)
        self.assertIn("history", text)

    def test_tickets_for_a_path_no_ticket_touched_is_none(self):
        """§7: `none` when empty. The fixture's one commit names ticket 0001 and
        adds every file (a `history` edge to each, ADR 0054 §1), and its
        perimeter covers pkg/, so the path comes from a later commit that names
        no ticket, outside the perimeter, on a map built there."""
        repo, _ = make_repo(self.tmp, "untouched")
        sha = commit(repo, "another commit", {"notes/other.txt": "x\n"})
        out = self.tmp / "untouched.sqlite"
        build_map(repo, out)
        is_error, text = serve([call(1, "tickets_for_path", path="notes/other.txt")], repo, out).answer(1)
        self.assertFalse(is_error, text)
        self.assertIn(sha, text)
        self.assertFalse(any("0001" in f for f in items(text)), text)
        self.assertTrue("none" in items(text) or "none" in text.splitlines())

    def test_check_spec_on_a_good_spec_is_go_and_no_error(self):
        """§5, §7: the spec gate's line; not an error."""
        is_error, text = self.ask("check_spec", text=GOOD_SPEC)
        self.assertFalse(is_error)
        self.assertEqual(text.strip(), "GO: spec")

    def test_check_spec_on_a_vague_criterion_is_a_nogo_answer_not_an_error(self):
        """§7: a NO-GO is an answer, not an error."""
        is_error, text = self.ask("check_spec", text=VAGUE_SPEC)
        self.assertFalse(is_error)
        self.assertTrue(text.startswith(f"NO-GO: spec {DASH} "), text)
        self.assertEqual(len(text.strip().splitlines()), 1)

    def test_check_spec_agrees_with_the_package_command(self):
        """§5: the same verdict as `lights-out-gates spec`."""
        path = self.tmp / "vague.md"
        path.write_text(VAGUE_SPEC, encoding="utf-8")
        p = subprocess.run([sys.executable, "-m", "core", "spec", str(path)], cwd=ROOT, env=env(),
                           capture_output=True, text=True)
        _, text = self.ask("check_spec", text=VAGUE_SPEC)
        self.assertEqual(text.strip(), p.stdout.strip())


# ---------------------------------------------------------- §7 refusals

class Refusals(Fixture):
    def refused(self, tool, **arguments):
        is_error, text = self.ask(tool, **arguments)
        self.assertTrue(is_error, text)
        self.assertEqual(len(text.strip().splitlines()), 1, text)
        return text

    def test_a_path_not_in_the_map_is_an_error(self):
        """§7."""
        for tool in TOOLS[:3]:
            self.refused(tool, path="pkg/nope.py")

    def test_a_path_outside_the_repository_is_an_error(self):
        """§7: `../x` and an absolute path elsewhere."""
        for tool in TOOLS[:3]:
            self.refused(tool, path="../x")
            self.refused(tool, path="/etc/passwd")

    def test_a_map_built_at_another_commit_names_both_shas_and_the_rebuild(self):
        """§7: stale maps are refused, the line names both shas and `lights-out-gates map`."""
        repo, old = make_repo(self.tmp, "stale")
        out = self.tmp / "stale.sqlite"
        build_map(repo, out)
        new = commit(repo, "another commit", {"pkg/other.py": "x = 1\n"})
        s = serve([call(1, "adrs_for_path", path=MODULE)], repo, out)
        is_error, text = s.answer(1)
        self.assertTrue(is_error)
        self.assertEqual(len(text.strip().splitlines()), 1, text)
        for needle in (old, new, "lights-out-gates map"):
            self.assertIn(needle, text)

    def test_a_missing_map_names_the_rebuild(self):
        """§7: missing maps are refused naming `lights-out-gates map`."""
        s = serve([call(1, "tests_for_path", path=MODULE)], self.repo, self.tmp / "absent.sqlite")
        is_error, text = s.answer(1)
        self.assertTrue(is_error)
        self.assertIn("lights-out-gates map", text)
        self.assertEqual(len(text.strip().splitlines()), 1, text)
        self.assertFalse((self.tmp / "absent.sqlite").exists(), "the server never builds a map")

    def test_a_file_that_is_not_a_map_is_an_error(self):
        """§7: other-schema or not-a-map files are refused."""
        junk = self.tmp / "junk.sqlite"
        junk.write_text("this is not a database\n", encoding="utf-8")
        s = serve([call(1, "tests_for_path", path=MODULE)], self.repo, junk)
        self.assertTrue(s.answer(1)[0])
        self.assertEqual(junk.read_text(encoding="utf-8"), "this is not a database\n")

    def test_a_map_of_another_schema_is_an_error(self):
        """§7."""
        other = self.tmp / "schema.sqlite"
        shutil.copy(self.map, other)
        db = sqlite3.connect(str(other))
        db.execute("UPDATE meta SET value = '1' WHERE key = 'schema'")
        db.commit()
        db.close()
        s = serve([call(1, "tests_for_path", path=MODULE)], self.repo, other)
        self.assertTrue(s.answer(1)[0])

    def test_check_spec_needs_no_map(self):
        """§7: it starts with no map, and the spec gate does not read one."""
        s = serve([call(1, "check_spec", text=GOOD_SPEC)], self.repo, self.tmp / "absent.sqlite")
        self.assertEqual(s.answer(1), (False, "GO: spec"))


# ------------------------------------------------- JSON-RPC errors, §7

class Errors(Fixture):
    def code(self, message):
        s = serve([message], self.repo, self.map)
        self.assertIn("error", s[message["id"]], s.lines)
        return s[message["id"]]["error"]["code"]

    def test_an_unknown_tool_is_32602(self):
        self.assertEqual(self.code(call(1, "nope", path=MODULE)), -32602)

    def test_a_missing_argument_is_32602(self):
        self.assertEqual(self.code(call(1, "adrs_for_path")), -32602)
        self.assertEqual(self.code(call(1, "check_spec")), -32602)

    def test_an_extra_argument_is_32602(self):
        self.assertEqual(self.code(call(1, "tests_for_path", path=MODULE, more="x")), -32602)

    def test_an_argument_of_the_wrong_type_is_32602(self):
        self.assertEqual(self.code(call(1, "tickets_for_path", path=1)), -32602)

    def test_an_unknown_method_is_32601(self):
        self.assertEqual(self.code(msg(1, "resources/list")), -32601)


# ---------------------------------------------------------- the two eras

class Eras(Fixture):
    def test_initialize_selects_legacy_and_answers_2025_11_25(self):
        """§7: any protocolVersion in, `2025-11-25` out, tools and a server name."""
        for asked in ("2024-11-05", "2025-03-26", MODERN, "1999-01-01"):
            init = msg(1, "initialize", {"protocolVersion": asked, "capabilities": {},
                                         "clientInfo": {"name": "t", "version": "0"}}, meta=False)
            note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
            s = serve([init, note, msg(2, "tools/list", meta=False)], self.repo, self.map)
            result = s[1]["result"]
            self.assertEqual(result["protocolVersion"], LEGACY, asked)
            self.assertIn("tools", result["capabilities"])
            self.assertTrue(result["serverInfo"]["name"])
            self.assertEqual(len(s.replies), 2, "the notification gets no reply")
            self.assertEqual([t["name"] for t in s[2]["result"]["tools"]], TOOLS)

    def test_legacy_calls_are_served_without_meta(self):
        """§7: later requests without `_meta` are served."""
        init = msg(1, "initialize", {"protocolVersion": LEGACY, "capabilities": {}}, meta=False)
        note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        s = serve([init, note, call(2, "tests_for_path", meta=False, path=MODULE)], self.repo, self.map)
        is_error, text = s.answer(2)
        self.assertFalse(is_error)
        self.assertIn(TEST, text)

    def test_without_initialize_every_request_needs_the_meta(self):
        """§7: 2026-07-28 is stateless, a request with no `_meta` is -32602."""
        for message in (msg(1, "tools/list", meta=False),
                        call(1, "tests_for_path", meta=False, path=MODULE),
                        msg(1, "tools/list", {"_meta": {VERSION_KEY: MODERN}}, meta=False),
                        msg(1, "tools/list", {"_meta": {CAPS_KEY: {}}}, meta=False)):
            s = serve([message], self.repo, self.map)
            self.assertEqual(s[1]["error"]["code"], -32602, message)

    def test_a_client_capabilities_that_is_not_an_object_is_32602(self):
        """§7: `clientCapabilities` (an object)."""
        bad = msg(1, "tools/list", {"_meta": {VERSION_KEY: MODERN, CAPS_KEY: "yes"}}, meta=False)
        self.assertEqual(serve([bad], self.repo, self.map)[1]["error"]["code"], -32602)

    def test_another_version_is_32022_naming_both_served_versions(self):
        """§7: -32022 with data.supported holding both."""
        bad = msg(1, "tools/list", {"_meta": {VERSION_KEY: "2099-01-01", CAPS_KEY: {}}}, meta=False)
        error = serve([bad], self.repo, self.map)[1]["error"]
        self.assertEqual(error["code"], -32022)
        self.assertIn(MODERN, error["data"]["supported"])
        self.assertIn(LEGACY, error["data"]["supported"])

    def test_server_discover_names_both_versions_and_the_tools_capability(self):
        """§7: `server/discover`."""
        result = serve([msg(1, "server/discover")], self.repo, self.map)[1]["result"]
        self.assertIn(MODERN, result["supportedVersions"])
        self.assertIn(LEGACY, result["supportedVersions"])
        self.assertIn("tools", result["capabilities"])
        self.assertEqual(result["resultType"], "complete")

    def test_modern_results_carry_result_type_complete(self):
        """§7."""
        s = serve([msg(1, "tools/list"), call(2, "check_spec", text=GOOD_SPEC),
                   call(3, "adrs_for_path", path="pkg/nope.py")], self.repo, self.map)
        for id_ in (1, 2, 3):
            self.assertEqual(s[id_]["result"]["resultType"], "complete", id_)


# ------------------------------------------------------------ the process

class Process(Fixture):
    def test_stdout_holds_only_json_rpc_lines(self):
        """§Verified: nothing else on stdout; logs go to stderr."""
        s = serve([msg(1, "server/discover"), msg(2, "tools/list"), call(3, "adrs_for_path", path=MODULE),
                   call(4, "adrs_for_path", path="../x"), call(5, "nope"), msg(6, "nope/nope"),
                   msg(7, "tools/list", meta=False)], self.repo, self.map)
        self.assertGreaterEqual(len(s.lines), 7)
        for line in s.lines:
            self.assertEqual(json.loads(line)["jsonrpc"], "2.0", line)

    def test_it_starts_with_no_map_and_exits_0_on_eof(self):
        """§7: starts with no map; exit on stdin EOF."""
        s = serve([msg(1, "tools/list")], self.repo, self.tmp / "none.sqlite")
        self.assertEqual(s.code, 0, s.err)
        self.assertEqual([t["name"] for t in s[1]["result"]["tools"]], TOOLS)
        self.assertEqual(serve([], self.repo, self.map).code, 0)

    def test_it_never_writes_the_map(self):
        """§7: opens mode=ro, never rebuilds."""
        before = (self.map.read_bytes(), self.map.stat().st_mtime_ns, sorted(os.listdir(self.tmp)))
        serve([call(1, "adrs_for_path", path=MODULE), call(2, "tests_for_path", path=TEST),
               call(3, "tickets_for_path", path=MODULE), call(4, "tickets_for_path", path="nope")],
              self.repo, self.map)
        after = (self.map.read_bytes(), self.map.stat().st_mtime_ns, sorted(os.listdir(self.tmp)))
        self.assertEqual(before, after)

    def test_the_default_map_is_the_git_path_of_the_repository(self):
        """§6: with no --map, `git rev-parse --git-path lights-out/map.sqlite`, relative to the repo."""
        repo, sha = make_repo(self.tmp, "default")
        where = Path(git(repo, "rev-parse", "--git-path", "lights-out/map.sqlite"))
        where = where if where.is_absolute() else repo / where
        self.assertFalse(where.exists())
        s = serve([call(1, "tests_for_path", path=MODULE)], repo)
        self.assertTrue(s.answer(1)[0], "no map there yet: a refusal")
        build_map(repo, where)
        is_error, text = serve([call(1, "tests_for_path", path=MODULE)], repo).answer(1)
        self.assertFalse(is_error, text)
        self.assertIn(sha, text)
        self.assertIn(TEST, text)


# ------------------------------------------------------ package commands §5

def run_core(*argv, cwd=ROOT, **extra):
    p = subprocess.run([sys.executable, "-m", "core", *argv], cwd=cwd, env=env(**extra),
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    return p.returncode, p.stdout, p.stderr


class Commands(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cmd-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def one_line(self, out):
        lines = out.splitlines()
        self.assertEqual(len(lines), 1, out)
        return lines[0]

    def test_spec_on_a_good_file_is_one_go_line(self):
        """§5."""
        path = self.tmp / "good.md"
        path.write_text(GOOD_SPEC, encoding="utf-8")
        code, out, _ = run_core("spec", str(path))
        self.assertEqual((code, out), (0, "GO: spec\n"))

    def test_spec_on_a_vague_file_is_one_nogo_line_and_exit_1(self):
        """§5."""
        path = self.tmp / "vague.md"
        path.write_text(VAGUE_SPEC, encoding="utf-8")
        code, out, _ = run_core("spec", str(path))
        self.assertEqual(code, 1)
        self.assertTrue(self.one_line(out).startswith(f"NO-GO: spec {DASH} "), out)

    def test_map_builds_the_head_map_at_the_git_path_default(self):
        """§5, §6: one `GO: map — <sha>` line; the file inside .git."""
        repo, sha = make_repo(self.tmp)
        code, out, err = run_core("map", "--repo", str(repo))
        self.assertEqual(code, 0, err)
        self.assertTrue(self.one_line(out).startswith(f"GO: map {DASH} {sha}"), out)
        where = Path(git(repo, "rev-parse", "--git-path", "lights-out/map.sqlite"))
        where = where if where.is_absolute() else repo / where
        self.assertTrue(where.is_file())
        self.assertIn(".git", where.parts)
        db = sqlite3.connect(str(where))
        self.assertEqual(dict(db.execute("SELECT key, value FROM meta"))["sha"], sha)
        db.close()
        self.assertFalse((repo / ".crew").exists())
        self.assertEqual(git(repo, "status", "--porcelain"), "", "nothing appears in the work tree")

    def test_a_map_built_by_the_command_is_the_one_the_server_reads(self):
        """§5, §6, §7."""
        repo, sha = make_repo(self.tmp)
        self.assertEqual(run_core("map", "--repo", str(repo))[0], 0)
        is_error, text = serve([call(1, "adrs_for_path", path=MODULE)], repo).answer(1)
        self.assertFalse(is_error, text)
        self.assertIn(sha, text)
        self.assertIn(ADR, text)

    def test_map_out_writes_there_and_not_at_the_default(self):
        """§5: `--out FILE`."""
        repo, sha = make_repo(self.tmp)
        out_file = self.tmp / "elsewhere" / "m.sqlite"
        code, out, err = run_core("map", "--repo", str(repo), "--out", str(out_file))
        self.assertEqual(code, 0, err)
        self.assertTrue(self.one_line(out).startswith(f"GO: map {DASH} {sha}"))
        self.assertTrue(out_file.is_file())
        where = Path(git(repo, "rev-parse", "--git-path", "lights-out/map.sqlite"))
        where = where if where.is_absolute() else repo / where
        self.assertFalse(where.exists())

    def tickets_of(self, repo):
        out_file = self.tmp / "t.sqlite"
        self.assertEqual(run_core("map", "--repo", str(repo), "--out", str(out_file))[0], 0)
        db = sqlite3.connect(str(out_file))
        try:
            return (dict(db.execute("SELECT key, value FROM meta"))["tickets"],
                    [r[0] for r in db.execute("SELECT name FROM node WHERE kind = 'ticket'")])
        finally:
            db.close()

    def test_tickets_are_read_from_the_contract_directory_when_the_commit_has_it(self):
        """§5: tickets `.lights-out/tickets` when that commit has it, else `tickets`."""
        repo = self.tmp / "attached"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        commit(repo, "c", {".lights-out/tickets/0007.md": "# 0007 — T\n", "tickets/0001.md": "# 0001 — no\n"})
        # A ticket node is named by its id (ADR 0054 §1), whichever directory holds it.
        self.assertEqual(self.tickets_of(repo), (".lights-out/tickets", ["0007"]))
        plain, _ = make_repo(self.tmp, "plain")
        self.assertEqual(self.tickets_of(plain), ("tickets", ["0001"]))

    def test_map_outside_a_repository_is_one_nogo_line_and_exit_1(self):
        """§5."""
        bare = self.tmp / "bare"
        bare.mkdir()
        code, out, _ = run_core("map", "--repo", str(bare), GIT_CEILING_DIRECTORIES=str(self.tmp))
        self.assertEqual(code, 1)
        self.assertTrue(self.one_line(out).startswith(f"NO-GO: map {DASH} "), out)

    def test_an_unknown_command_names_spec_map_and_mcp(self):
        """§5: the unknown-command line lists the new commands."""
        code, out, _ = run_core("frobnicate")
        self.assertEqual(code, 1)
        line = self.one_line(out)
        self.assertTrue(line.startswith("NO-GO: "), line)
        for word in ("spec", "map", "mcp"):
            self.assertIn(word, line)


if __name__ == "__main__":
    unittest.main()

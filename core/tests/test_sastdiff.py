"""Tests for core/sastdiff.py, written from docs/adr/0072 decision 1 (which
amends ADR 0030 §3) and docs/adr/0052 §3, never from the implementation.

The module is exercised through its CLI, the only contract the ADR gives:

  sastdiff.py read <line-file>
      validates a SAST runner's last non-empty stdout line:
      `<N> items`, `<N> none` (an old runner) or exit 1 with one reason.
  sastdiff.py diff <json-out> <where> <prefix> <head-root> <head-line-file>
                   <base-root> <base-line-file>  < git diff -M --name-status -z
      judges which findings a diff introduces. A finding's fingerprint is
      (rule, repository path, sha256 of the flagged line with every
      whitespace removed); line numbers are not part of it; counting is a
      multiset; base paths go through the renames.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "core", "sastdiff.py")


def cli(*args, stdin=b""):
    """Run the CLI from the repository root: (exit code, stdout, stderr)."""
    p = subprocess.run(  # noqa: S603  # nosec B603 - fixed argv, no shell
        [sys.executable, SCRIPT, *args],
        input=stdin,
        capture_output=True,
        cwd=ROOT,
        check=False,
    )
    return p.returncode, p.stdout.decode(), p.stderr.decode()


def runner_line(items=None, findings=None):
    """The line of a runner that prints items (or, with items None, an old one)."""
    if items is None:
        return json.dumps({"findings": findings})
    n = len(items) if findings is None else findings
    return json.dumps(
        {"findings": n, "items": [{"rule": r, "file": f, "line": ln} for r, f, ln in items]}
    )


def name_status(*records):
    """`git diff -M --name-status -z` output from ("M", path) or ("R100", old, new)."""
    out = b""
    for rec in records:
        for field in rec:
            out += field.encode() + b"\0"
    return out


class Tmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = self._tmp.name

    def write(self, rel, text):
        path = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path


class ReadTest(Tmp):
    def read(self, text):
        path = self.write("line.txt", text)
        return cli("read", path)

    def accepts(self, text, want):
        rc, out, err = self.read(text)
        self.assertEqual((rc, out.rstrip("\n")), (0, want), err)
        self.assertEqual(out.count("\n"), 1, "stdout must be one line")

    def rejects(self, text):
        rc, out, err = self.read(text)
        self.assertEqual(rc, 1, f"accepted {text!r}: {out!r} {err!r}")
        self.assertEqual(out.count("\n"), 1, f"want one reason line, got {out!r}")
        self.assertTrue(out.strip(), "the reason is empty")

    def test_items_are_counted(self):
        self.accepts(runner_line([("B101", "pkg/a.py", 12), ("B311", "pkg/b.py", 0)]) + "\n", "2 items")

    def test_zero_findings_with_empty_items(self):
        self.accepts('{"findings": 0, "items": []}\n', "0 items")

    def test_line_zero_is_allowed(self):
        self.accepts(runner_line([("B101", "a.py", 0)]) + "\n", "1 items")

    def test_old_runner_has_no_items(self):
        self.accepts('{"findings": 3}\n', "3 none")
        self.accepts('{"findings": 0}\n', "0 none")

    def test_the_runner_line_is_the_last_non_empty_line(self):
        noise = "scanning...\n{not json}\nreport: 1 issue\n"
        self.accepts(noise + runner_line([("B101", "a.py", 1)]) + "\n\n  \n\n", "1 items")
        self.accepts(noise + '{"findings": 2}', "2 none")

    def test_an_earlier_valid_line_does_not_rescue_a_bad_last_line(self):
        self.rejects(runner_line([("B101", "a.py", 1)]) + "\nnot json\n")

    def test_not_json(self):
        self.rejects("findings: 1\n")
        self.rejects('{"findings": 1\n')

    def test_empty_file(self):
        self.rejects("")
        self.rejects("\n\n   \n")

    def test_not_an_object(self):
        self.rejects("[1, 2]\n")
        self.rejects("3\n")

    def test_findings_missing_or_mistyped(self):
        self.rejects('{"items": []}\n')
        self.rejects('{"findings": -1, "items": []}\n')
        self.rejects('{"findings": "1", "items": []}\n')
        self.rejects('{"findings": null}\n')
        self.rejects('{"findings": true}\n')
        self.rejects('{"findings": false, "items": []}\n')
        self.rejects('{"findings": true, "items": [{"rule": "B1", "file": "a.py", "line": 1}]}\n')

    def test_items_not_a_list(self):
        self.rejects('{"findings": 1, "items": {"rule": "B1", "file": "a.py", "line": 1}}\n')
        self.rejects('{"findings": 1, "items": "B1"}\n')
        self.rejects('{"findings": 0, "items": null}\n')

    def test_length_differs_from_findings(self):
        self.rejects(runner_line([("B101", "a.py", 1)], findings=2) + "\n")
        self.rejects(runner_line([("B101", "a.py", 1), ("B101", "b.py", 1)], findings=1) + "\n")
        self.rejects(runner_line([], findings=1) + "\n")
        self.rejects('{"findings": 0, "items": [{"rule": "B1", "file": "a.py", "line": 1}]}\n')

    def test_item_fields(self):
        def one(item):
            return json.dumps({"findings": 1, "items": [item]}) + "\n"

        self.accepts(one({"rule": "B1", "file": "a.py", "line": 1}), "1 items")
        self.rejects(one({"file": "a.py", "line": 1}))
        self.rejects(one({"rule": "B1", "line": 1}))
        self.rejects(one({"rule": "B1", "file": "a.py"}))
        self.rejects(one({"rule": "", "file": "a.py", "line": 1}))
        self.rejects(one({"rule": "B1", "file": "", "line": 1}))
        self.rejects(one({"rule": 101, "file": "a.py", "line": 1}))
        self.rejects(one({"rule": "B1", "file": 7, "line": 1}))
        self.rejects(one({"rule": "B1", "file": "a.py", "line": -1}))
        self.rejects(one({"rule": "B1", "file": "a.py", "line": "12"}))
        self.rejects(one({"rule": "B1", "file": "a.py", "line": True}))
        self.rejects(one({"rule": "B1", "file": "a.py", "line": None}))
        self.rejects(one("B1 a.py 1"))
        self.rejects(one(None))

    def test_one_bad_item_among_good_ones(self):
        text = json.dumps(
            {
                "findings": 2,
                "items": [
                    {"rule": "B1", "file": "a.py", "line": 1},
                    {"rule": "B1", "file": "a.py"},
                ],
            }
        )
        self.rejects(text + "\n")


class DiffTest(Tmp):
    """Each case lays out two directories (the head's and the base's roots)."""

    def judge(
        self,
        head,
        base,
        head_items,
        base_items,
        renames=(),
        prefix="",
        where="workbench",
        empty_base=False,
    ):
        """head/base: {relative path: text}; *_items: (rule, file, line) tuples.
        Returns (exit code, stdout, stderr, json record)."""
        shutil_root = os.path.join(self.tmp, "run")
        os.makedirs(shutil_root, exist_ok=True)
        head_root = os.path.join(shutil_root, "head")
        base_root = os.path.join(shutil_root, "base")
        os.makedirs(head_root, exist_ok=True)
        os.makedirs(base_root, exist_ok=True)
        for rel, text in head.items():
            self.write(os.path.join("run", "head", rel), text)
        for rel, text in base.items():
            self.write(os.path.join("run", "base", rel), text)
        head_line = self.write("run/head.line", "runner noise\n" + runner_line(head_items) + "\n")
        out_json = os.path.join(shutil_root, "out.json")
        if empty_base:
            base_root_arg, base_line_arg = "-", "-"
        else:
            base_root_arg = base_root
            base_line_arg = self.write("run/base.line", runner_line(base_items) + "\n")
        rc, out, err = cli(
            "diff", out_json, where, prefix, head_root, head_line, base_root_arg, base_line_arg,
            stdin=name_status(*renames),
        )
        record = None
        if os.path.exists(out_json):
            with open(out_json, encoding="utf-8") as f:
                record = json.load(f)
        self.assertEqual(out.count("\n"), 1, f"stdout must be one line: {out!r} (stderr {err!r})")
        return rc, out.rstrip("\n"), err, record

    def assertNone(self, result, inherited):
        rc, out, err, record = result
        self.assertEqual((rc, out), (0, f"none new ({inherited} inherited)"), err)
        self.assertEqual(len(record["new"]), 0)
        self.assertEqual(len(record["inherited"]), inherited)

    def assertNew(self, result, n, inherited=0):
        rc, out, err, record = result
        self.assertEqual((rc, out), (1, f"this diff introduces {n} finding(s); list on stderr"), err)
        self.assertEqual(len(record["new"]), n)
        self.assertEqual(len(record["inherited"]), inherited)

    def test_clean_head(self):
        res = self.judge({"a.py": "x = 1\n"}, {"a.py": "assert x\n"}, [], [("B101", "a.py", 1)])
        self.assertNone(res, 0)
        self.assertEqual(res[3]["findings"], 0)
        self.assertEqual(res[3]["where"], "workbench")

    def test_finding_added_on_clean_base(self):
        res = self.judge({"a.py": "x = 1\nassert x\n"}, {"a.py": "x = 1\n"}, [("B101", "a.py", 2)], [])
        self.assertNew(res, 1)
        self.assertIn("B101", res[2])
        self.assertIn("a.py", res[2])
        record = res[3]
        self.assertEqual(record["findings"], 1)
        self.assertEqual(record["new"], [{"rule": "B101", "file": "a.py", "line": 2}])
        self.assertEqual(record["inherited"], [])

    def test_inherited_finding_whose_line_moved(self):
        res = self.judge(
            {"a.py": "import os\n\n\nx = 1\nassert x\n"},
            {"a.py": "assert x\n"},
            [("B101", "a.py", 5)],
            [("B101", "a.py", 1)],
            renames=[("M", "a.py")],
        )
        self.assertNone(res, 1)
        self.assertEqual(res[3]["inherited"], [{"rule": "B101", "file": "a.py", "line": 5}])
        self.assertIn("B101", res[2])
        self.assertIn("a.py", res[2])

    def test_reindented_is_inherited(self):
        for head_text in (
            "    assert   x\n",
            "\tassert\tx   \n",
            "assert x\r\n",
            "  a s s e r t x\n",
        ):
            with self.subTest(head=head_text):
                res = self.judge({"a.py": head_text}, {"a.py": "assert x\n"}, [("B101", "a.py", 1)], [("B101", "a.py", 1)])
                self.assertNone(res, 1)

    def test_changed_text_is_new(self):
        res = self.judge(
            {"a.py": "assert y\n"}, {"a.py": "assert x\n"}, [("B101", "a.py", 1)], [("B101", "a.py", 1)]
        )
        self.assertNew(res, 1)

    def test_a_different_rule_on_the_same_text_is_new(self):
        res = self.judge(
            {"a.py": "assert x\n"}, {"a.py": "assert x\n"}, [("B102", "a.py", 1)], [("B101", "a.py", 1)]
        )
        self.assertNew(res, 1)

    def test_same_text_in_a_renamed_file_is_inherited(self):
        res = self.judge(
            {"new.py": "import os\nassert x\n"},
            {"old.py": "assert x\n"},
            [("B101", "new.py", 2)],
            [("B101", "old.py", 1)],
            renames=[("M", "other.py"), ("R090", "old.py", "new.py"), ("D", "gone.py"), ("A", "added.py")],
        )
        self.assertNone(res, 1)
        self.assertEqual(res[3]["inherited"], [{"rule": "B101", "file": "new.py", "line": 2}])
        self.assertIn("new.py", res[2])

    def test_other_records_are_skipped_correctly(self):
        # A misaligned parse would pair "M a.py" with the next status.
        res = self.judge(
            {"b.py": "assert x\n"},
            {"a.py": "assert x\n"},
            [("B101", "b.py", 1)],
            [("B101", "a.py", 1)],
            renames=[("M", "m1.py"), ("D", "d1.py"), ("A", "a1.py"), ("R100", "a.py", "b.py"), ("M", "m2.py")],
        )
        self.assertNone(res, 1)

    def test_a_rename_is_not_applied_to_other_paths(self):
        res = self.judge(
            {"new.py": "assert x\n", "stay.py": "assert x\n"},
            {"old.py": "assert x\n"},
            [("B101", "new.py", 1), ("B101", "stay.py", 1)],
            [("B101", "old.py", 1)],
            renames=[("R100", "old.py", "new.py")],
        )
        self.assertNew(res, 1, inherited=1)
        self.assertEqual([i["file"] for i in res[3]["new"]], ["stay.py"])

    def test_a_finding_moved_to_another_file_is_new(self):
        res = self.judge(
            {"b.py": "assert x\n"},
            {"a.py": "assert x\n"},
            [("B101", "b.py", 1)],
            [("B101", "a.py", 1)],
            renames=[("M", "a.py"), ("A", "b.py")],
        )
        self.assertNew(res, 1)

    def test_a_second_identical_line_is_one_new(self):
        res = self.judge(
            {"a.py": "assert x\nfoo()\nassert x\n"},
            {"a.py": "assert x\n"},
            [("B101", "a.py", 1), ("B101", "a.py", 3)],
            [("B101", "a.py", 1)],
        )
        self.assertNew(res, 1, inherited=1)
        self.assertEqual(res[3]["findings"], 2)

    def test_counting_is_a_multiset(self):
        two = {"a.py": "assert x\nassert x\n"}
        three = {"a.py": "assert x\nassert x\nassert x\n"}
        h3 = [("B101", "a.py", n) for n in (1, 2, 3)]
        b2 = [("B101", "a.py", n) for n in (1, 2)]
        res = self.judge(three, two, h3, b2)
        self.assertNew(res, 1, inherited=2)
        # Fewer in head than in base: nothing new, only min() inherited.
        res = self.judge(two, three, b2, h3)
        self.assertNone(res, 2)
        self.assertEqual(res[3]["findings"], 2)

    def test_base_only_findings_are_neither_new_nor_inherited(self):
        res = self.judge(
            {"a.py": "assert x\n", "b.py": "ok\n"},
            {"a.py": "assert x\n", "b.py": "assert y\n"},
            [("B101", "a.py", 1)],
            [("B101", "a.py", 1), ("B101", "b.py", 1)],
        )
        self.assertNone(res, 1)
        self.assertEqual(res[3]["findings"], 1)
        self.assertNotIn("b.py", res[2])

    def test_empty_tree_base_makes_every_finding_new(self):
        res = self.judge(
            {"a.py": "assert x\n", "b.py": "assert y\n"},
            {},
            [("B101", "a.py", 1), ("B101", "b.py", 1)],
            [],
            empty_base=True,
        )
        self.assertNew(res, 2)
        self.assertEqual(res[3]["findings"], 2)

    def test_empty_tree_base_with_a_clean_head(self):
        self.assertNone(self.judge({"a.py": "x\n"}, {}, [], [], empty_base=True), 0)

    def test_counts_add_up(self):
        res = self.judge(
            {"a.py": "assert x\nassert z\n", "b.py": "eval(q)\n"},
            {"a.py": "assert x\n"},
            [("B101", "a.py", 1), ("B101", "a.py", 2), ("B307", "b.py", 1)],
            [("B101", "a.py", 1)],
        )
        self.assertNew(res, 2, inherited=1)
        record = res[3]
        self.assertEqual(len(record["new"]) + len(record["inherited"]), record["findings"])
        for item in record["new"] + record["inherited"]:
            self.assertEqual(set(item), {"rule", "file", "line"})
        for want in ("B101", "B307", "b.py"):
            self.assertIn(want, res[2])

    def test_the_json_carries_the_where_argument(self):
        res = self.judge({"a.py": "assert x\n"}, {}, [("B101", "a.py", 1)], [], where="compose:backend-test", empty_base=True)
        self.assertEqual(res[3]["where"], "compose:backend-test")

    def test_prefix_is_carried_into_paths(self):
        prefix = "svc/backend/"
        res = self.judge(
            {"src/new.py": "x\nassert x\n", "src/fresh.py": "eval(q)\n"},
            {"src/old.py": "assert x\n"},
            [("B101", "./src/new.py", 2), ("B307", "src//fresh.py", 1)],
            [("B101", "src/old.py", 1)],
            renames=[("R100", "svc/backend/src/old.py", "svc/backend/src/new.py")],
            prefix=prefix,
        )
        self.assertNew(res, 1, inherited=1)
        record = res[3]
        self.assertEqual(record["inherited"], [{"rule": "B101", "file": "svc/backend/src/new.py", "line": 2}])
        self.assertEqual(record["new"], [{"rule": "B307", "file": "svc/backend/src/fresh.py", "line": 1}])
        self.assertIn("svc/backend/src/fresh.py", res[2])

    def test_prefix_makes_paths_repository_paths_for_the_comparison(self):
        # The rename record names repository paths: without the prefix on the
        # runner's relative paths the two would never meet.
        res = self.judge(
            {"new.py": "assert x\n"},
            {"old.py": "assert x\n"},
            [("B101", "new.py", 1)],
            [("B101", "old.py", 1)],
            renames=[("R100", "svc/old.py", "svc/new.py")],
            prefix="svc/",
        )
        self.assertNone(res, 1)
        self.assertEqual(res[3]["inherited"][0]["file"], "svc/new.py")

    def test_file_paths_are_normalised(self):
        res = self.judge(
            {"pkg/a.py": "assert x\n"},
            {"pkg/a.py": "assert x\n"},
            [("B101", "./pkg/../pkg/a.py", 1)],
            [("B101", "pkg//a.py", 1)],
        )
        self.assertNone(res, 1)
        self.assertEqual(res[3]["inherited"][0]["file"], "pkg/a.py")

    def test_a_missing_file_or_line_has_empty_text(self):
        # Both sides unreadable: the same (empty) text, so inherited.
        res = self.judge({"a.py": "one line\n"}, {}, [("B101", "a.py", 9), ("B1", "gone.py", 1)], [("B101", "a.py", 4), ("B1", "gone.py", 3)])
        self.assertNone(res, 2)
        # Readable at HEAD, unreadable at the base: a different text, so new.
        res = self.judge({"a.py": "assert x\n"}, {}, [("B101", "a.py", 1)], [("B101", "a.py", 7)])
        self.assertNew(res, 1)
        # Line 0 and a line past the end do not crash either.
        res = self.judge({"a.py": "assert x\n"}, {"a.py": "assert x\n"}, [("B101", "a.py", 0)], [("B101", "a.py", 99)])
        self.assertEqual(res[0], 0)

    def test_line_numbers_are_one_based(self):
        res = self.judge(
            {"a.py": "safe\nassert x\n"},
            {"a.py": "assert x\nsafe\n"},
            [("B101", "a.py", 2)],
            [("B101", "a.py", 1)],
        )
        self.assertNone(res, 1)
        # Off by one in either direction would read "safe" and call it new.

    def test_whitespace_is_stripped_everywhere_in_the_line(self):
        res = self.judge(
            {"a.py": "foo(  a ,\tb )\n"},
            {"a.py": "foo(a,b)\n"},
            [("B1", "a.py", 1)],
            [("B1", "a.py", 1)],
        )
        self.assertNone(res, 1)

    def test_head_and_base_text_come_from_their_own_roots(self):
        # The same path holds different text on the two sides: new.
        res = self.judge({"a.py": "eval(a)\n"}, {"a.py": "eval(b)\n"}, [("B307", "a.py", 1)], [("B307", "a.py", 1)])
        self.assertNew(res, 1)


if __name__ == "__main__":
    unittest.main()

"""Tests for core/testdiff.py, written from docs/adr/0053 §1-§3, never from
the implementation.

`subject` decides whether gates/test-proof.sh has anything to run: the
changed test files, or the reason there is nothing to prove. `weakening`
judges a `git diff -M -U0` restricted to the contract's test paths: a
deleted test file, lost assertions, lost tests or added skips are findings,
counted per file, unless the ticket's `## Removes tests` declares the file.
"""

import contextlib
import io
import unittest

from core import testdiff

APP_TESTS = "backend/tests/test_*.py:backend/tests/conftest.py"


def diff(*files):
    """A `git diff -M -U0` text from (old, new, removed, added, kind) tuples."""
    out = []
    for old, new, removed, added, kind in files:
        out.append(f"diff --git a/{old or new} b/{new or old}")
        if kind == "deleted":
            out.append("deleted file mode 100644")
        elif kind == "new":
            out.append("new file mode 100644")
        elif kind == "renamed":
            out += ["similarity index 90%", f"rename from {old}", f"rename to {new}"]
        out.append("index 1111111..2222222 100644")
        out.append(f"--- {'a/' + old if old else '/dev/null'}")
        out.append(f"+++ {'b/' + new if new else '/dev/null'}")
        out.append("@@ -1,0 +1,0 @@")
        out += ["-" + line for line in removed]
        out += ["+" + line for line in added]
    return "\n".join(out) + "\n"


def judge(text, globs=APP_TESTS, prefix="svc/", declared=()):
    return testdiff.weakening(text, globs, prefix, list(declared))


class Subject(unittest.TestCase):
    def test_tests_and_code_changed_is_a_subject_listing_the_test_files(self):
        tests, reason = testdiff.subject(
            ["svc/backend/orders/billing_client.py", "svc/backend/tests/test_orders.py"],
            APP_TESTS, "svc/")
        self.assertEqual(tests, ["svc/backend/tests/test_orders.py"])
        self.assertIsNone(reason)

    def test_no_test_changed_is_absence(self):
        tests, reason = testdiff.subject(["svc/backend/orders/app.py"], APP_TESTS, "svc/")
        self.assertEqual(tests, [])
        self.assertIn("no test", reason)

    def test_only_tests_changed_is_absence(self):
        tests, reason = testdiff.subject(
            ["svc/backend/tests/test_orders.py", "svc/backend/tests/conftest.py"], APP_TESTS, "svc/")
        self.assertEqual(tests, [])
        self.assertIn("only test", reason)

    def test_a_docs_or_contract_change_is_code_to_prove(self):
        tests, reason = testdiff.subject(
            ["svc/contracts/billing/examples.json", "svc/backend/tests/test_orders.py"],
            APP_TESTS, "svc/")
        self.assertEqual(tests, ["svc/backend/tests/test_orders.py"])
        self.assertIsNone(reason)

    def test_globs_are_relative_to_the_workload_and_star_crosses_slash(self):
        tests, _ = testdiff.subject(
            ["src/a.js", "test/unit/a.test.js", "test/helpers.js"], "*.test.*", "")
        self.assertEqual(tests, ["test/unit/a.test.js"])

    def test_the_runners_beside_the_tests_are_not_tests(self):
        tests, reason = testdiff.subject(
            ["svc/backend/tests/mutation/run.sh", "svc/backend/orders/app.py"], APP_TESTS, "svc/")
        self.assertEqual(tests, [])
        self.assertIn("no test", reason)

    def test_a_path_outside_the_workload_is_never_a_test(self):
        tests, _ = testdiff.subject(
            ["backend/tests/test_x.py", "svc/backend/orders/app.py"], APP_TESTS, "svc/")
        self.assertEqual(tests, [])

    def test_blank_names_are_ignored(self):
        tests, reason = testdiff.subject(["", "svc/backend/orders/app.py", ""], APP_TESTS, "svc/")
        self.assertEqual(tests, [])
        self.assertIn("no test", reason)


class Deletion(unittest.TestCase):
    def test_a_deleted_test_file_is_a_finding(self):
        findings, _, _ = judge(diff(("backend/tests/test_auth.py", None,
                                      ["def test_x():", "    assert True"], [], "deleted")),
                               prefix="")
        self.assertEqual(len(findings), 1)
        self.assertIn("backend/tests/test_auth.py", findings[0])
        self.assertIn("deleted", findings[0])

    def test_a_test_renamed_out_of_the_test_paths_is_a_deletion(self):
        findings, _, _ = judge(diff(("backend/tests/test_auth.py", "backend/tests/off_auth.py",
                                      [], [], "renamed")), prefix="")
        self.assertEqual(len(findings), 1)
        self.assertIn("backend/tests/test_auth.py", findings[0])

    def test_a_test_renamed_within_the_test_paths_is_not(self):
        findings, _, _ = judge(diff(("backend/tests/test_a.py", "backend/tests/test_b.py",
                                      [], [], "renamed")), prefix="")
        self.assertEqual(findings, [])

    def test_a_deleted_file_outside_the_test_paths_is_none_of_its_business(self):
        findings, _, summary = judge(diff(("backend/orders/old.py", None,
                                            ["assert x"], [], "deleted")), prefix="")
        self.assertEqual(findings, [])
        self.assertIn("no test", summary)

    def test_the_deletion_rule_holds_for_a_language_with_no_patterns(self):
        findings, _, _ = judge(diff(("spec/a_spec.rb", None, ["it 'x' do"], [], "deleted")),
                               globs="spec/*", prefix="")
        self.assertEqual(len(findings), 1)


class Python(unittest.TestCase):
    path = "svc/backend/tests/test_orders.py"

    def one(self, removed, added, **kw):
        return judge(diff((self.path, self.path, removed, added, "modified")), **kw)

    def test_a_removed_assert_is_a_lost_assertion(self):
        findings, _, _ = self.one(['    assert body["venue_lon"] == 1'], [])
        self.assertEqual(len(findings), 1)
        self.assertIn("assertion", findings[0])
        self.assertIn(self.path, findings[0])

    def test_an_edited_assert_is_not(self):
        findings, _, _ = self.one(["    assert lat == pytest.approx(45.4641)"],
                                  ["    assert lat == pytest.approx(45.4642)"])
        self.assertEqual(findings, [])

    def test_a_commented_out_assert_is_a_lost_assertion(self):
        findings, _, _ = self.one(["    assert resp.status_code == 404"],
                                  ["    # assert resp.status_code == 404"])
        self.assertEqual(len(findings), 1)

    def test_unittest_and_mock_assert_methods_count(self):
        for line in ("        self.assertEqual(a, b)", "        self.assertRaises(KeyError, f)",
                     "    mocked.assert_called_once_with(1)"):
            findings, _, _ = self.one([line], [])
            self.assertEqual(len(findings), 1, line)

    def test_pytest_raises_and_warns_count(self):
        for line in ("    with pytest.raises(ValueError):", "    with pytest.warns(UserWarning):"):
            findings, _, _ = self.one([line], [])
            self.assertEqual(len(findings), 1, line)

    def test_a_removed_test_function_is_a_lost_test(self):
        findings, _, _ = self.one(["def test_get_unknown_order_is_404(client):"], [])
        self.assertEqual(len(findings), 1)
        self.assertIn("test", findings[0])

    def test_async_test_functions_and_test_classes_count(self):
        for line in ("async def test_stream(client):", "class TestAuth:",
                     "    def test_method(self):"):
            findings, _, _ = self.one([line], [])
            self.assertEqual(len(findings), 1, line)

    def test_a_renamed_test_function_is_not_a_loss(self):
        findings, _, _ = self.one(["def test_old_name(client):"], ["def test_new_name(client):"])
        self.assertEqual(findings, [])

    def test_a_helper_that_is_not_a_test_may_go(self):
        findings, _, _ = self.one(["def _signup_and_login(client, email):"], [])
        self.assertEqual(findings, [])

    def test_every_skip_marker_is_a_finding(self):
        for line in ("@pytest.mark.skip(reason='later')", "@pytest.mark.skipif(True, reason='x')",
                     "@pytest.mark.xfail", "pytestmark = pytest.mark.skip",
                     "    pytest.skip('flaky')", "    pytest.xfail('flaky')",
                     "pytest.importorskip('numpy')", "@unittest.skip('later')",
                     "@unittest.skipIf(True, 'x')", "@unittest.skipUnless(False, 'x')",
                     "@unittest.expectedFailure", "@skip('later')", "@expectedFailure",
                     "        self.skipTest('later')", "    raise unittest.SkipTest('x')"):
            findings, _, _ = self.one([], [line])
            self.assertEqual(len(findings), 1, line)
            self.assertIn("skip", findings[0])

    def test_removing_a_skip_is_welcome(self):
        findings, _, _ = self.one(["@pytest.mark.skip(reason='later')"], [])
        self.assertEqual(findings, [])

    def test_a_skip_inside_a_comment_is_not_a_skip(self):
        findings, _, _ = self.one([], ["# not @pytest.mark.skip: it runs"])
        self.assertEqual(findings, [])

    def test_additions_only_are_clean(self):
        findings, _, summary = self.one([], ["def test_new(client):", "    assert client"])
        self.assertEqual(findings, [])
        self.assertIn("1", summary)

    def test_one_file_finding_per_rule(self):
        findings, _, _ = self.one(["def test_a(c):", "    assert a", "    assert b"], ["@pytest.mark.xfail"])
        self.assertEqual(len(findings), 3)


class JavaScript(unittest.TestCase):
    path = "test/calc.test.js"
    globs = "test/*:*.test.*"

    def one(self, removed, added, path=None):
        p = path or self.path
        return judge(diff((p, p, removed, added, "modified")), globs=self.globs, prefix="")

    def test_assert_forms_count(self):
        for line in ("  assert.strictEqual(add(1, 2), 3);", "  assert(ok);",
                     "  t.assert.equal(x, 1);", "  expect(add(1, 2)).toBe(3);"):
            findings, _, _ = self.one([line], [])
            self.assertEqual(len(findings), 1, line)
            self.assertIn("assertion", findings[0])

    def test_test_definitions_count(self):
        for line in ("test('adds', () => {", "it('adds', () => {", "  it(\"adds\", async () => {"):
            findings, _, _ = self.one([line], [])
            self.assertEqual(len(findings), 1, line)

    def test_skip_todo_and_only_are_findings(self):
        for line in ("test.skip('adds', () => {", "it.todo('later');", "describe.only('calc', () => {",
                     "suite.skip('x', () => {", "xit('adds', () => {", "xdescribe('calc', () => {",
                     "xtest('adds', () => {", "test('adds', { skip: true }, () => {",
                     "test('adds', { todo: 'later' }, () => {", "test('adds', { only: true }, () => {",
                     "  t.skip('later');", "  t.todo();"):
            findings, _, _ = self.one([], [line])
            self.assertEqual(len(findings), 1, line)

    def test_comments_do_not_count_as_added(self):
        for line in ("// assert.strictEqual(add(1, 2), 3);", "/* expect(x) */", " * assert(x)"):
            findings, _, _ = self.one(["  assert.strictEqual(add(1, 2), 3);"], [line])
            self.assertEqual(len(findings), 1, line)

    def test_typescript_and_module_extensions_use_the_same_patterns(self):
        for path in ("test/a.test.ts", "test/a.test.mjs", "test/a.test.tsx", "test/a.cjs"):
            findings, _, _ = self.one(["  expect(a).toBe(1);"], [], path=path)
            self.assertEqual(len(findings), 1, path)


class Declared(unittest.TestCase):
    ticket = """# 0099 — drop the legacy auth tests

## Perimeter

- `svc/backend/orders/auth.py`

## Removes tests

- `svc/backend/tests/test_auth.py`
- svc/backend/tests/test_legacy_*.py

## Notes

- `svc/backend/tests/test_orders.py`
"""

    def test_the_section_is_read_as_perimeter_style_globs(self):
        self.assertEqual(testdiff.declared(self.ticket),
                         ["svc/backend/tests/test_auth.py", "svc/backend/tests/test_legacy_*.py"])

    def test_no_section_declares_nothing(self):
        self.assertEqual(testdiff.declared("# 0001\n\n## Perimeter\n\n- `a`\n"), [])

    def test_a_declared_file_is_excused_and_reported(self):
        text = diff(("backend/tests/test_auth.py", None, ["def test_x():"], [], "deleted"),
                    ("backend/tests/test_legacy_login.py", "backend/tests/test_legacy_login.py",
                     ["    assert ok"], [], "modified"))
        findings, excused, _ = judge(text, prefix="",
                                     declared=["backend/tests/test_auth.py", "backend/tests/test_legacy_*.py"])
        self.assertEqual(findings, [])
        self.assertEqual(len(excused), 2)

    def test_the_declaration_excuses_only_its_files(self):
        text = diff(("backend/tests/test_auth.py", None, ["def test_x():"], [], "deleted"),
                    ("backend/tests/test_orders.py", "backend/tests/test_orders.py",
                     ["    assert ok"], [], "modified"))
        findings, excused, _ = judge(text, prefix="", declared=["backend/tests/test_auth.py"])
        self.assertEqual(len(findings), 1)
        self.assertIn("test_orders.py", findings[0])
        self.assertEqual(len(excused), 1)


class Cli(unittest.TestCase):
    def run_main(self, argv, stdin):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = testdiff.main(argv, io.StringIO(stdin))
        return code, out.getvalue(), err.getvalue()

    def test_subject_prints_the_test_paths_and_exits_0(self):
        code, out, _ = self.run_main(["subject", APP_TESTS, "svc/"],
                                     "svc/backend/orders/a.py\nsvc/backend/tests/test_a.py\n")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["svc/backend/tests/test_a.py"])

    def test_no_subject_prints_one_reason_line_and_exits_3(self):
        code, out, _ = self.run_main(["subject", APP_TESTS, "svc/"], "svc/backend/orders/a.py\n")
        self.assertEqual(code, 3)
        self.assertEqual(len(out.splitlines()), 1)

    def test_weakening_go_prints_one_detail_line(self):
        code, out, _ = self.run_main(["weakening", APP_TESTS, ""], "")
        self.assertEqual(code, 0)
        self.assertEqual(len(out.splitlines()), 1)

    def test_weakening_nogo_prints_the_reason_then_one_line_per_finding(self):
        text = diff(("backend/tests/test_a.py", "backend/tests/test_a.py", ["    assert a"], [], "modified"),
                    ("backend/tests/test_b.py", None, ["def test_b():"], [], "deleted"))
        code, out, _ = self.run_main(["weakening", APP_TESTS, ""], text)
        self.assertEqual(code, 1)
        lines = out.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("2", lines[0])

    def test_weakening_reads_the_ticket_file_when_given(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".md") as t:
            t.write("## Removes tests\n\n- backend/tests/test_b.py\n")
            t.flush()
            text = diff(("backend/tests/test_b.py", None, ["def test_b():"], [], "deleted"))
            code, _, err = self.run_main(["weakening", APP_TESTS, "", t.name], text)
        self.assertEqual(code, 0)
        self.assertIn("backend/tests/test_b.py", err)

    def test_a_missing_ticket_file_is_an_error(self):
        code, out, _ = self.run_main(["weakening", APP_TESTS, "", "/nonexistent/ticket.md"], "")
        self.assertEqual(code, 1)
        self.assertIn("ticket", out)

    def test_usage(self):
        code, _, err = self.run_main([], "")
        self.assertEqual(code, 2)
        self.assertIn("usage", err)


if __name__ == "__main__":
    unittest.main()

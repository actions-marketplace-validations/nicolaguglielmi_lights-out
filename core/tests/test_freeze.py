"""Tests for the frozen console snapshot, written from docs/adr/0089, never
from the implementation: a minimal page, a small logbook, and the committed
console over the golden logbook.
"""

import json
import os
import re
import subprocess  # nosec B404 - the command under test is a script
import sys
import tempfile
import unittest

from core import freeze

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOLDEN = os.path.join(REPO, "fixtures", "logbook", "golden-1.5.json")
CONSOLE = os.path.join(REPO, "console", "index.html")

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>page</title>
<script>document.documentElement.dataset.theme = "light";</script>
</head>
<body class="b">
<main id="main">hello</main>
<script>
fetch("/v1/logbook.json").then((r) => r.json()).then((b) => { document.getElementById("main").textContent = b.schema; });
</script>
</body>
</html>
"""

BOOK = {
    "schema": "lights-out/logbook/1.5",
    "source": {"commit": "c0ffee1234567"},
    "tickets": [{"id": "0001", "title": "x </script><script>alert(1)</script>",
                 "history": [{"step": "request", "at": "2026-11-14T09:00:00Z"},
                             {"step": "release", "at": "2026-11-14T10:00:00Z"}]}],
    "releases": [{"version": "1.0.0", "at": "2026-11-14T09:30:00Z",
                  "answer": {"answer": "NO-GO", "at": "2026-11-14T10:05:00Z"}}],
}


def data(html, ident):
    m = re.search(r'<script type="application/json" id="%s">(.*?)</script>' % ident, html, re.S)
    assert m, ident
    return json.loads(m.group(1))


class Freeze(unittest.TestCase):
    """§1, §3: the file the freezer writes."""

    def setUp(self):
        self.out = freeze.freeze(PAGE, json.dumps(BOOK))

    def test_the_logbook_parses_back_equal(self):
        self.assertEqual(data(self.out, "frozen-logbook"), BOOK)

    def test_the_console_answer(self):
        con = data(self.out, "frozen-console")
        self.assertEqual((con["mode"], con["auth"], con["can_launch"], con["identity"], con["read_error"]),
                         ("snapshot", "public", False, None, None))
        self.assertEqual(con["snapshot"], "logbook of c0ffee1, last event 2026-11-14T10:05:00Z")

    def test_the_insertions_come_before_the_first_script(self):
        first_page_script = self.out.index("<script>document.documentElement")
        for ident in ('id="frozen-logbook"', 'id="frozen-console"', 'id="frozen-shim"'):
            self.assertLess(self.out.index(ident), first_page_script, ident)
        self.assertLess(self.out.index('id="frozen-logbook"'), self.out.index('id="frozen-shim"'))
        self.assertIn('http-equiv="Content-Security-Policy"', self.out)
        self.assertIn("default-src 'none'", self.out)

    def test_the_banner_is_the_body_first_element(self):
        body = self.out[self.out.index('<body class="b">') + len('<body class="b">'):]
        self.assertTrue(body.startswith('<!-- frozen: begin --><div id="frozen-banner"'), body[:80])
        banner = body[:body.index("</div>")]
        self.assertIn("logbook of c0ffee1, last event 2026-11-14T10:05:00Z", banner)
        self.assertIn("read-only", banner.lower())

    def test_the_page_is_otherwise_untouched(self):
        # §1: every insertion sits between the freezer's two markers.
        self.assertEqual(self.out.count("<!-- frozen: begin -->"), 2)
        self.assertEqual(re.sub(r"<!-- frozen: begin -->.*?<!-- frozen: end -->", "", self.out, flags=re.S), PAGE)

    def test_a_closing_tag_in_a_value_is_escaped(self):
        self.assertNotIn("<script>alert(1)", self.out)
        self.assertEqual(self.out.count("</script>"), PAGE.count("</script>") + 3)

    def test_the_shim_answers_the_two_reads_and_refuses_the_rest(self):
        shim = re.search(r'<script id="frozen-shim">(.*?)</script>', self.out, re.S).group(1)
        for s in ("/v1/logbook.json", "/v1/console.json", "403", "a frozen snapshot: nothing behind it, nothing is sent",
                  "window.fetch"):
            self.assertIn(s, shim)

    def test_a_label_replaces_the_default(self):
        out = freeze.freeze(PAGE, json.dumps(BOOK), label="x")
        self.assertEqual(data(out, "frozen-console")["snapshot"], "x")

    def test_a_prefix_goes_before_the_label(self):
        out = freeze.freeze(PAGE, json.dumps(BOOK), prefix="evidence pack 1.0.0")
        self.assertEqual(data(out, "frozen-console")["snapshot"],
                         "evidence pack 1.0.0, logbook of c0ffee1, last event 2026-11-14T10:05:00Z")

    def test_equal_inputs_give_equal_bytes(self):
        self.assertEqual(self.out, freeze.freeze(PAGE, json.dumps(BOOK)))

    def test_a_logbook_with_no_time(self):
        book = {"schema": "lights-out/logbook/1.5", "source": {}, "tickets": [], "releases": []}
        self.assertEqual(data(freeze.freeze(PAGE, json.dumps(book)), "frozen-console")["snapshot"],
                         "logbook of ?, last event ?")


class Refusals(unittest.TestCase):
    """§4: one line, exit 1."""

    def run_cli(self, page_text, book_text, name="book.json"):
        with tempfile.TemporaryDirectory() as d:
            page = os.path.join(d, "page.html")
            with open(page, "w", encoding="utf-8") as f:
                f.write(page_text)
            book = os.path.join(d, name)
            if book_text is not None:
                with open(book, "w", encoding="utf-8") as f:
                    f.write(book_text)
            out = os.path.join(d, "out.html")
            p = subprocess.run([sys.executable, "core/freeze.py", "--page", page, "--logbook", book, "--out", out],
                               cwd=REPO, capture_output=True, text=True, timeout=60, check=False)
            return p, os.path.exists(out)

    def refused(self, page_text, book_text, word):
        p, written = self.run_cli(page_text, book_text)
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertEqual(len(p.stdout.splitlines()), 1, p.stdout)
        self.assertIn(word, p.stdout)
        self.assertFalse(written)

    def test_a_missing_logbook(self):
        self.refused(PAGE, None, "book.json")

    def test_a_logbook_that_is_not_json(self):
        self.refused(PAGE, "{", "not JSON")

    def test_another_schema(self):
        self.refused(PAGE, json.dumps({"schema": "other/1"}), "other/1")

    def test_a_page_with_no_body(self):
        self.refused(PAGE.replace('<body class="b">', ""), json.dumps(BOOK), "<body>")

    def test_success_prints_the_path(self):
        p, written = self.run_cli(PAGE, json.dumps(BOOK))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue(written)
        self.assertTrue(p.stdout.strip().endswith("out.html"))


class CommittedConsole(unittest.TestCase):
    """§1, §2: the console of this commit, frozen over the golden logbook."""

    @classmethod
    def setUpClass(cls):
        with open(CONSOLE, encoding="utf-8") as f:
            cls.page = f.read()
        with open(GOLDEN, encoding="utf-8") as f:
            cls.out = freeze.freeze(cls.page, f.read())

    def test_nothing_external(self):
        self.assertNotRegex(self.out, r'(src|href)\s*=\s*["\']?https?://')
        self.assertNotRegex(self.out, r'<link[^>]+rel=["\']?stylesheet')

    def test_every_route_the_page_fetches_is_answered_or_refused(self):
        routes = set(re.findall(r'fetch\(\s*"(/[^"]*)"', self.page))
        self.assertIn("/v1/logbook.json", routes)
        self.assertIn("/v1/console.json", routes)
        # Every other route is a write: the shim answers it 403 whatever it is.
        for route in routes - {"/v1/logbook.json", "/v1/console.json"}:
            self.assertTrue(route.startswith("/v1/"), route)
        self.assertNotRegex(self.page, r'fetch\(\s*[^"\s/]', "a fetch whose route the test cannot read")

    def test_the_golden_logbook_is_inlined(self):
        with open(GOLDEN, encoding="utf-8") as f:
            self.assertEqual(data(self.out, "frozen-logbook"), json.load(f))


if __name__ == "__main__":
    unittest.main()

"""Tests for the light tier (`python3 -m core gates --light`), written from
docs/adr/0061 §1-§7 and §9, never from the implementation.

Black box: every test builds a scratch git repository with a
`.lights-out/workload.env` (or the bundled `workload.env`) and Python tests
run by `python3 -m unittest`, runs the CLI in it and reads what it prints, its
exit code, the `verdict.env` it writes and what it leaves in the repository.
Each docstring names the ADR section the case comes from.
"""

import hashlib
import importlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core import spec

ROOT = Path(__file__).resolve().parents[2]
DASH = "—"
GATE_ORDER = ["risk", "perimeter", "test-weakening", "test", "test-proof", "spec"]

# The line of ADR 0061 §5, in its four shapes (what ran decides the tail).
GO = f"GO: gates-light {DASH} risk low, auto-merge; "
IMAGE = "secrets, deps, sast, mutation need the image"
NEED_HOST = "; test, test-proof need TEST_ON_HOST=1"
NEED_TICKET = "; perimeter, spec need TICKET="
GO_DEFAULT = f"{GO}2 of 10 gates ran; {IMAGE}{NEED_HOST}{NEED_TICKET}"
GO_TICKET = f"{GO}4 of 10 gates ran; {IMAGE}{NEED_HOST}"
GO_HOST = f"{GO}4 of 10 gates ran; {IMAGE}{NEED_TICKET}"
GO_BOTH = f"{GO}6 of 10 gates ran; {IMAGE}"

# The scratch workload: a calculator with a suite, laid out like the bundled
# app (sources and tests under `backend/`, the contract's test root).
CALC = "def add(a, b):\n    return a + b\n\n\ndef neg(a):\n    return a\n"
CALC_PLUS = CALC + "\n\ndef double(a):\n    return a * 2\n"
CALC_FIXED = CALC.replace("def neg(a):\n    return a\n", "def neg(a):\n    return -a\n")
CALC_BROKEN = CALC.replace("return a + b", "return a - b")
TESTS = (
    "import unittest\n\nimport calc\n\n\nclass CalcTest(unittest.TestCase):\n"
    "    def test_add(self):\n"
    "        self.assertEqual(calc.add(1, 2), 3)\n"
    "        self.assertEqual(calc.add(2, 2), 4)\n"
)
TESTS_WEAK = TESTS.replace("        self.assertEqual(calc.add(2, 2), 4)\n", "")
TESTS_MORE = TESTS + "        self.assertEqual(calc.add(5, 5), 10)\n"
TESTS_NEG = TESTS + "\n    def test_neg(self):\n        self.assertEqual(calc.neg(3), -3)\n"
TESTS_ZERO = TESTS + "\n    def test_add_zero(self):\n        self.assertEqual(calc.add(0, 0), 0)\n"

GOOD_CRITERIA = """Given a calculator with two numbers
When the caller adds them
Then the result is their sum

Given a number
When the caller negates it
Then the result is the number with its sign flipped"""
VAGUE_CRITERIA = GOOD_CRITERIA.replace(
    "Then the result is their sum", "Then the calculator works correctly")

SCRUBBED = ("BASE", "HEAD", "STAGED", "TICKET", "TEST_ON_HOST", "WORKLOAD", "GATES_OUT",
            "TEST_CMD", "NO_COLOR", "GATES_TICKET", "WORKLOAD_CONTRACT", "NOGO_DETAILS")


def clean_env(**extra):
    """The caller's environment minus git's and the gates' variables, so the
    scratch repositories and the arguments are all the CLI sees."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k not in SCRUBBED}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_AUTHOR_NAME="scratch", GIT_AUTHOR_EMAIL="scratch@localhost.invalid",
               GIT_COMMITTER_NAME="scratch", GIT_COMMITTER_EMAIL="scratch@localhost.invalid",
               PYTHONPATH=str(ROOT), PYTHONSAFEPATH="1")
    env.update(extra)
    return env


def read_env(path):
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            out[key] = value
    return out


def words(value):
    """A RAN value as a list, whether it is space- or comma-separated."""
    return [w for w in re.split(r"[ ,]+", value.strip()) if w]


def suite_cmd(log=None, leak=False):
    """A TEST_CMD: noise on stdout, an optional line in LOG (where it ran and
    NO_COLOR), an optional file written into the cwd, then the unittest suite."""
    parts = ["echo suite-noise"]
    if log:
        parts.append(f"echo $(pwd -P) $NO_COLOR >> {log}")
    if leak:
        parts.append("touch leak.txt")
    parts.append("python3 -m unittest discover -s tests -t .")
    return " && ".join(parts)


def ticket_text(perimeter=("backend/calc.py",), criteria=GOOD_CRITERIA, removes=()):
    out = [f"# 0042 {DASH} a change to the calculator", "", "- Status: open", "",
           "## Problem", "", "Something to change.", ""]
    if criteria is not None:
        out += ["## Acceptance criteria", "", criteria, ""]
    if perimeter is not None:
        out += ["## Perimeter", ""] + [f"- `{p}`" for p in perimeter] + [""]
    if removes:
        out += ["## Removes tests", ""] + [f"- `{p}`" for p in removes] + [""]
    return "\n".join(out)


def snapshot(path, git=True):
    """{relative path: content hash, link target or 'dir'} for everything under PATH."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(path):
        if not git and ".git" in dirnames:
            dirnames.remove(".git")
        dirnames.sort()
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, path)
            if os.path.islink(full):
                out[rel] = "link:" + os.readlink(full)
            elif os.path.isdir(full):
                out[rel] = "dir"
            else:
                with open(full, "rb") as fh:
                    out[rel] = hashlib.sha256(fh.read()).hexdigest()
    return out


class Repo:
    """A scratch repository whose workload sits at WORKLOAD (empty: the top)."""

    def __init__(self, path, workload="", root="backend/", bundled=False, test_cmd=None,
                 image="workbench", baseline=None, paths=None):
        self.path = Path(path)
        self.wl = f"{workload}/" if workload else ""
        self.root = root
        self.test_cmd = test_cmd or suite_cmd()
        self.image, self.baseline = image, baseline
        self.paths = paths if paths is not None else f"{root}tests/test_*.py:{root}tests/conftest.py"
        self.calc = f"{self.wl}{root}calc.py"
        self.tests = f"{self.wl}{root}tests/test_calc.py"
        self.contract = f"{self.wl}workload.env" if bundled else f"{self.wl}.lights-out/workload.env"
        self.path.mkdir(parents=True)
        self.git("init", "-q", "-b", "main")

    def git(self, *args, check=True):
        p = subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=self.path,
                           env=clean_env(), capture_output=True, text=True, check=False)
        if check and p.returncode:
            raise AssertionError(f"git {' '.join(args)}: {p.stderr}")
        return p.stdout.strip()

    def write(self, rel, text):
        full = self.path / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(text, encoding="utf-8")

    def commit(self, message="change"):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.sha()

    def sha(self, ref="HEAD"):
        return self.git("rev-parse", ref)

    def contract_text(self, **over):
        env = {"WORKLOAD_TEST_PATHS": self.paths, "WORKLOAD_TEST_ROOT": self.root,
               "TEST_CMD": self.test_cmd, "TOOLCHAIN_IMAGE": self.image}
        if self.baseline:
            env["MUTATION_BASELINE"] = self.baseline
        env.update(over)
        return "# Workload contract of a scratch repository.\n" + "".join(
            f"{k}={v}\n" for k, v in env.items())

    def populate(self, contract=True):
        if contract:
            self.write(self.contract, self.contract_text())
        self.write(self.calc, CALC)
        self.write(f"{self.wl}{self.root}tests/__init__.py", "")
        self.write(self.tests, TESTS)


class LightCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="light-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.count = 0

    def repo(self, base=True, contract=True, **kw):
        """A scratch repository; with BASE a first commit holding the workload."""
        self.count += 1
        r = Repo(self.tmp / f"repo{self.count}", **kw)
        r.populate(contract)
        if base:
            r.commit("base")
        return r

    def outside(self, name):
        return self.tmp / name

    def cli(self, args, cwd, contract=True, env=None):
        p = subprocess.run([sys.executable, "-m", "core", *args], cwd=cwd, stdin=subprocess.DEVNULL,
                           env=clean_env(**(env or {})), capture_output=True, text=True,
                           encoding="utf-8", timeout=120)
        if contract:
            self.assert_one_line(p)
        return p

    def light(self, r, *args, env=None):
        return self.cli(["gates", "--light", *args], r.path, env=env)

    def assert_one_line(self, p):
        """ADR 0061 §5 and CLAUDE.md: one line, no colour, GO exits 0, NO-GO exits 1,
        and never `GO: gates`."""
        why = f"\nstdout: {p.stdout!r}\nstderr: {p.stderr}"
        self.assertTrue(p.stdout.endswith("\n") and p.stdout.count("\n") == 1, "not one line" + why)
        self.assertNotIn("\x1b", p.stdout, "ANSI in stdout" + why)
        line = p.stdout[:-1]
        self.assertNotEqual(line, "GO: gates", why)
        self.assertFalse(line.startswith("GO: gates "), why)
        if line.startswith("GO: "):
            self.assertEqual(p.returncode, 0, "GO with a non-zero exit" + why)
        else:
            self.assertTrue(line.startswith("NO-GO: "), "neither GO nor NO-GO" + why)
            self.assertEqual(p.returncode, 1, "NO-GO without exit 1" + why)

    def line(self, p):
        return p.stdout[:-1]

    def assert_go(self, p, line=None):
        self.assertEqual(p.returncode, 0, f"stdout: {p.stdout!r}\nstderr: {p.stderr}")
        if line is not None:
            self.assertEqual(self.line(p), line)

    def assert_nogo(self, p, prefix):
        self.assertEqual(p.returncode, 1, f"stdout: {p.stdout!r}\nstderr: {p.stderr}")
        self.assertTrue(self.line(p).startswith(prefix), f"{self.line(p)!r}\nstderr: {p.stderr}")

    def assert_nogo_at(self, p, gate):
        self.assert_nogo(p, f"NO-GO: gates-light {DASH} {gate}: ")

    def log_lines(self, log):
        return log.read_text().splitlines() if log.exists() else []


class Importable(unittest.TestCase):
    def test_the_package_has_a_light_tier_and_a_callable_main(self):
        """§1, §3: `lights_out.__main__:main` is the console script; core/light.py the tier."""
        importlib.import_module("core.light")
        self.assertTrue(callable(importlib.import_module("core.__main__").main))


class Fixtures(unittest.TestCase):
    """The tickets below are what they claim to be, by the spec gate's own rules."""

    def test_the_good_ticket_passes_and_the_vague_and_the_bare_ones_do_not(self):
        self.assertIsNone(spec.check(ticket_text()))
        self.assertIn("works", spec.check(ticket_text(criteria=VAGUE_CRITERIA)))
        self.assertIn("Acceptance criteria", spec.check(ticket_text(criteria=None)))


class TheLine(LightCase):
    def test_default_runs_risk_and_test_weakening_and_names_what_did_not_run(self):
        """§4, §5: two of ten, the exact line."""
        r = self.repo()
        r.write(r.calc, CALC_PLUS)
        r.commit()
        self.assert_go(self.light(r), GO_DEFAULT)

    def test_a_ticket_adds_perimeter_and_spec(self):
        """§4, §5: four of ten, the TEST_ON_HOST hint only."""
        r = self.repo()
        r.write(r.calc, CALC_PLUS)
        r.commit()
        ticket = self.outside("ticket.md")
        ticket.write_text(ticket_text(), encoding="utf-8")
        self.assert_go(self.light(r, f"TICKET={ticket}"), GO_TICKET)

    def test_test_on_host_adds_test_and_test_proof(self):
        """§4, §5: four of ten, the TICKET hint only."""
        r = self.repo()
        r.write(r.calc, CALC_PLUS)
        r.commit()
        self.assert_go(self.light(r, "TEST_ON_HOST=1"), GO_HOST)

    def test_both_run_six_of_ten_and_only_the_image_is_missing(self):
        """§4, §5: six of ten."""
        r = self.repo()
        r.write(r.calc, CALC_PLUS)
        r.commit()
        ticket = self.outside("ticket.md")
        ticket.write_text(ticket_text(), encoding="utf-8")
        self.assert_go(self.light(r, f"TICKET={ticket}", "TEST_ON_HOST=1"), GO_BOTH)

    def test_a_relative_ticket_path_is_read_from_the_working_directory(self):
        """§6: `TICKET=<file>`, as the hook recipes write it."""
        r = self.repo()
        r.write("tickets/0042.md", ticket_text())
        r.commit("the ticket")
        r.write(r.calc, CALC_PLUS)
        r.commit()
        self.assert_go(self.light(r, "TICKET=tickets/0042.md"))

    def test_a_platform_path_is_high_risk_and_goes_to_review(self):
        """§3, §5: the level and decision of core/risk.py with the platform policy."""
        r = self.repo()
        r.write("Makefile", "all:\n\ttrue\n")
        r.commit()
        self.assert_go(self.light(r), GO_DEFAULT.replace("risk low, auto-merge", "risk high, review"))

    def test_a_large_change_is_medium_risk_and_goes_to_review(self):
        """§3: RISK_SIZE_MEDIUM_LINES=200 of policy/merge.env, 250 lines changed."""
        r = self.repo()
        r.write("backend/big.py", "x = 1\n" * 250)
        r.commit()
        self.assert_go(self.light(r), GO_DEFAULT.replace("risk low, auto-merge", "risk medium, review"))

    def test_nothing_of_the_suite_reaches_stdout(self):
        """§5: the tools' noise is on stderr; the suite prints on stdout."""
        r = self.repo()
        r.write(r.calc, CALC_PLUS)
        r.commit()
        p = self.light(r, "TEST_ON_HOST=1")
        self.assert_go(p)
        self.assertNotIn("suite-noise", p.stdout)

    def test_a_nogo_is_one_line_with_the_gate_and_the_reason(self):
        """§5: `NO-GO: gates-light — <gate>: <reason>`, exit 1."""
        r = self.repo()
        r.write(r.tests, TESTS_WEAK)
        r.commit()
        p = self.light(r)
        self.assert_nogo(p, f"NO-GO: gates-light {DASH} test-weakening: ")
        self.assertGreater(len(self.line(p)), len(f"NO-GO: gates-light {DASH} test-weakening: "))

    def test_not_a_repository_is_a_nogo(self):
        """§5: a refusal is still the one line."""
        bare = self.outside("bare")
        bare.mkdir()
        self.assert_nogo(self.cli(["gates", "--light"], bare), f"NO-GO: gates-light {DASH} ")


class Refusals(LightCase):
    def test_gates_without_light_is_refused_with_the_way_out(self):
        """§5: the package never prints `GO: gates`."""
        r = self.repo()
        p = self.cli(["gates"], r.path)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(self.line(p), (
            f"NO-GO: gates {DASH} this package runs the light tier only: lights-out gates --light; "
            "the eight gates run from the image (the lights-out wrapper) or a clone (./go gates)"))

    def test_an_unknown_argument_is_named(self):
        """§5: `NO-GO: gates-light — '<arg>' is not an argument ...`."""
        r = self.repo()
        for arg in ("banana", "--fast"):
            p = self.light(r, arg)
            self.assert_nogo(p, f"NO-GO: gates-light {DASH} '{arg}' is not an argument")

    def test_an_unknown_key_is_not_an_argument_either(self):
        """§5, §6: the vocabulary is closed."""
        r = self.repo()
        p = self.light(r, "FOO=1")
        self.assertEqual(p.returncode, 1)
        self.assertRegex(self.line(p), rf"^NO-GO: gates-light {DASH} '[^']*FOO[^']*' is not an argument")

    def test_an_unknown_command_lists_the_two_there_are(self):
        """§5: `NO-GO: lights-out — unknown command '<cmd>'; one of: gates --light, version`."""
        r = self.repo()
        p = self.cli(["frobnicate"], r.path)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(self.line(p), (
            f"NO-GO: lights-out {DASH} unknown command 'frobnicate'; one of: gates --light, version"))

    def test_version_exits_zero(self):
        """§5: `version` is a command."""
        r = self.repo()
        p = self.cli(["version"], r.path, contract=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("Traceback", p.stderr)


class TestWeakening(LightCase):
    def test_a_removed_assertion_is_a_nogo(self):
        """§4, §6: test-weakening, by the rules of ADR 0053."""
        r = self.repo()
        r.write(r.tests, TESTS_WEAK)
        r.commit()
        p = self.light(r)
        self.assert_nogo_at(p, "test-weakening")
        self.assertIn("test_calc.py", p.stdout + p.stderr)

    def test_an_added_assertion_is_fine(self):
        """§4: only losses count."""
        r = self.repo()
        r.write(r.tests, TESTS_MORE)
        r.commit()
        self.assert_go(self.light(r), GO_DEFAULT)

    def test_the_tickets_removes_tests_excuses_it(self):
        """§4: `TICKET=` makes test-weakening read `## Removes tests`."""
        r = self.repo()
        r.write(r.tests, TESTS_WEAK)
        r.commit()
        excused = self.outside("excused.md")
        excused.write_text(ticket_text(perimeter=[r.tests], removes=[r.tests]), encoding="utf-8")
        self.assert_go(self.light(r, f"TICKET={excused}"), GO_TICKET)
        plain = self.outside("plain.md")
        plain.write_text(ticket_text(perimeter=[r.tests]), encoding="utf-8")
        self.assert_nogo_at(self.light(r, f"TICKET={plain}"), "test-weakening")

    def test_a_deleted_test_file_is_a_nogo(self):
        """§4: ADR 0053's deletion rule."""
        r = self.repo()
        (r.path / r.tests).unlink()
        r.commit()
        self.assert_nogo_at(self.light(r), "test-weakening")


class Perimeter(LightCase):
    def test_a_path_outside_the_tickets_perimeter_is_a_nogo(self):
        """§3, §4: core/perimeter.sh, with the changed paths."""
        r = self.repo()
        r.write("backend/other.py", "x = 1\n")
        r.commit()
        ticket = self.outside("ticket.md")
        ticket.write_text(ticket_text(), encoding="utf-8")
        p = self.light(r, f"TICKET={ticket}")
        self.assert_nogo_at(p, "perimeter")
        self.assertIn("backend/other.py", p.stdout + p.stderr)

    def test_a_path_inside_it_is_fine(self):
        """§4: the same ticket, a change inside."""
        r = self.repo()
        r.write(r.calc, CALC_PLUS)
        r.commit()
        ticket = self.outside("ticket.md")
        ticket.write_text(ticket_text(), encoding="utf-8")
        self.assert_go(self.light(r, f"TICKET={ticket}"), GO_TICKET)

    def test_a_ticket_with_no_perimeter_is_a_nogo_at_the_perimeter(self):
        """§4: perimeter runs before spec, and refuses a ticket with no `## Perimeter`."""
        r = self.repo()
        r.write(r.calc, CALC_PLUS)
        r.commit()
        ticket = self.outside("ticket.md")
        ticket.write_text(ticket_text(perimeter=None), encoding="utf-8")
        self.assert_nogo_at(self.light(r, f"TICKET={ticket}"), "perimeter")

    def test_without_a_ticket_the_perimeter_is_not_judged(self):
        """§4: it runs only with a ticket."""
        r = self.repo()
        r.write("anywhere/at/all.py", "x = 1\n")
        r.commit()
        self.assert_go(self.light(r), GO_DEFAULT)

    def test_a_missing_ticket_file_is_a_nogo_in_one_line(self):
        """§5, §6: the shape holds for a bad argument."""
        r = self.repo()
        r.write(r.calc, CALC_PLUS)
        r.commit()
        self.assert_nogo(self.light(r, f"TICKET={self.tmp}/nope.md"), f"NO-GO: gates-light {DASH} ")


class Spec(LightCase):
    def ticketed(self, text):
        r = self.repo()
        r.write(r.calc, CALC_PLUS)
        r.commit()
        ticket = self.outside("ticket.md")
        ticket.write_text(text, encoding="utf-8")
        return self.light(r, f"TICKET={ticket}")

    def test_a_vague_criterion_is_a_nogo(self):
        """§4: core/spec.py check, ADR 0055 §4."""
        p = self.ticketed(ticket_text(criteria=VAGUE_CRITERIA))
        self.assert_nogo_at(p, "spec")
        self.assertIn("works", p.stdout + p.stderr)

    def test_no_acceptance_criteria_is_a_nogo(self):
        """§4: a ticket with nothing to test."""
        self.assert_nogo_at(self.ticketed(ticket_text(criteria=None)), "spec")

    def test_a_well_formed_ticket_is_fine(self):
        """§4."""
        self.assert_go(self.ticketed(ticket_text()), GO_TICKET)


class OnTheHost(LightCase):
    def test_a_failing_suite_on_the_head_is_a_nogo_at_test_and_test_proof_does_not_run(self):
        """§4: test, then test-proof; the first NO-GO stops the rest."""
        log = self.outside("suite.log")
        r = self.repo(test_cmd=suite_cmd(log))
        r.write(r.calc, CALC_BROKEN)
        r.write(r.tests, TESTS_NEG)
        r.commit()
        out = self.outside("out")
        out.mkdir()
        p = self.light(r, "TEST_ON_HOST=1", f"GATES_OUT={out}")
        self.assert_nogo_at(p, "test")
        self.assertNotIn("test-proof", self.line(p))
        self.assertEqual(len(self.log_lines(log)), 1, "the suite ran again on the base")
        verdict = read_env(out / "verdict.env")
        self.assertEqual((verdict["GATES"], verdict["FAILED"]), ("NO-GO", "test"))
        self.assertNotIn("test-proof", words(verdict["RAN"]))

    def test_a_changed_test_that_passes_on_the_base_too_is_a_nogo_at_test_proof(self):
        """§4: the changed test files must fail on the base (ADR 0053 §2)."""
        r = self.repo()
        r.write(r.calc, CALC_PLUS)
        r.write(r.tests, TESTS_ZERO)
        r.commit()
        self.assert_nogo_at(self.light(r, "TEST_ON_HOST=1"), "test-proof")

    def test_a_changed_test_that_fails_on_the_base_proves_the_change(self):
        """§4: copied onto a checkout of the base, TEST_CMD fails: GO."""
        log = self.outside("suite.log")
        r = self.repo(test_cmd=suite_cmd(log))
        r.write(r.calc, CALC_FIXED)
        r.write(r.tests, TESTS_NEG)
        r.commit()
        self.assert_go(self.light(r, "TEST_ON_HOST=1"), GO_HOST)
        self.assertEqual(len(self.log_lines(log)), 2, "head, then base")

    def test_no_test_changed_means_test_proof_runs_nothing(self):
        """§4: test once on the head; test-proof has no subject (testdiff.subject)."""
        log = self.outside("suite.log")
        r = self.repo(test_cmd=suite_cmd(log))
        r.write(r.calc, CALC_PLUS)
        r.commit()
        self.assert_go(self.light(r, "TEST_ON_HOST=1"), GO_HOST)
        self.assertEqual(len(self.log_lines(log)), 1)

    def test_only_tests_changed_means_test_proof_runs_nothing(self):
        """§4: ADR 0053 §2, a test-only change has nothing to fail on."""
        log = self.outside("suite.log")
        r = self.repo(test_cmd=suite_cmd(log))
        r.write(r.tests, TESTS_MORE)
        r.commit()
        self.assert_go(self.light(r, "TEST_ON_HOST=1"), GO_HOST)
        self.assertEqual(len(self.log_lines(log)), 1)

    def test_by_default_no_code_of_the_repository_runs(self):
        """§4: safe for a hook, with a ticket too."""
        log = self.outside("suite.log")
        r = self.repo(test_cmd=suite_cmd(log))
        r.write(r.calc, CALC_FIXED)
        r.write(r.tests, TESTS_NEG)
        r.commit()
        ticket = self.outside("ticket.md")
        ticket.write_text(ticket_text(perimeter=[r.calc, r.tests]), encoding="utf-8")
        self.assert_go(self.light(r))
        self.assert_go(self.light(r, f"TICKET={ticket}"))
        self.assertFalse(log.exists(), "TEST_CMD ran without TEST_ON_HOST=1")

    def test_test_cmd_runs_in_the_test_root_of_a_checkout_outside_the_repository(self):
        """§4: `<workload>/<WORKLOAD_TEST_ROOT>` of a throwaway checkout, NO_COLOR=1."""
        log = self.outside("suite.log")
        r = self.repo(workload="bundled", bundled=True, test_cmd=suite_cmd(log))
        r.write(r.calc, CALC_PLUS)
        r.commit()
        self.assert_go(self.light(r, "WORKLOAD=bundled", "TEST_ON_HOST=1"))
        (entry,) = self.log_lines(log)
        cwd, no_color = entry.split()
        self.assertTrue(cwd.endswith("/bundled/backend"), cwd)
        self.assertEqual(no_color, "1")
        here = os.path.realpath(r.path)
        self.assertNotEqual(os.path.commonpath([here, os.path.realpath(cwd)]), here)

    def test_a_workload_with_no_test_root_runs_from_its_top(self):
        """§4: WORKLOAD_TEST_ROOT empty, the layout of a flat repository."""
        r = self.repo(root="")
        r.write(r.calc, CALC_PLUS)
        r.commit()
        self.assert_go(self.light(r, "TEST_ON_HOST=1"), GO_HOST)

    def test_the_host_is_the_toolchain_whatever_the_contract_names(self):
        """§4: TOOLCHAIN_IMAGE=compose:backend-test does not stop TEST_ON_HOST=1."""
        r = self.repo(image="compose:backend-test", baseline="0.5")
        r.write(r.calc, CALC_PLUS)
        r.commit()
        self.assert_go(self.light(r, "TEST_ON_HOST=1"), GO_HOST)

    def test_a_root_commit_is_tested_and_has_nothing_to_fail_on(self):
        """§4, §6: the base is the empty tree; test-proof runs nothing."""
        log = self.outside("suite.log")
        r = self.repo(test_cmd=suite_cmd(log))
        p = self.light(r, "TEST_ON_HOST=1")
        self.assert_go(p, GO_HOST.replace("risk low, auto-merge", "risk high, review"))
        self.assertEqual(len(self.log_lines(log)), 1)


class Order(LightCase):
    def test_the_first_nogo_stops_the_rest(self):
        """§4: risk, perimeter, test-weakening, test, test-proof, spec."""
        log = self.outside("suite.log")
        r = self.repo(test_cmd=suite_cmd(log))
        r.write("backend/other.py", "x = 1\n")
        r.write(r.calc, CALC_BROKEN)
        r.write(r.tests, TESTS_WEAK)
        r.commit()
        ticket = self.outside("ticket.md")
        ticket.write_text(ticket_text(criteria=VAGUE_CRITERIA), encoding="utf-8")
        out = self.outside("out")
        out.mkdir()
        args = [f"TICKET={ticket}", "TEST_ON_HOST=1", f"GATES_OUT={out}"]
        self.assert_nogo_at(self.light(r, *args), "perimeter")
        self.assertFalse(log.exists())
        ran = words(read_env(out / "verdict.env")["RAN"])
        self.assertIn("risk", ran)
        self.assertEqual(set(ran) & {"test-weakening", "test", "test-proof", "spec"}, set())

    def test_test_weakening_comes_before_test(self):
        """§4."""
        log = self.outside("suite.log")
        r = self.repo(test_cmd=suite_cmd(log))
        r.write(r.calc, CALC_BROKEN)
        r.write(r.tests, TESTS_WEAK)
        r.commit()
        self.assert_nogo_at(self.light(r, "TEST_ON_HOST=1"), "test-weakening")
        self.assertFalse(log.exists())

    def test_spec_comes_after_test(self):
        """§4: a vague ticket and a failing suite name the suite."""
        r = self.repo()
        r.write(r.calc, CALC_BROKEN)
        r.commit()
        ticket = self.outside("ticket.md")
        ticket.write_text(ticket_text(criteria=VAGUE_CRITERIA), encoding="utf-8")
        self.assert_nogo_at(self.light(r, f"TICKET={ticket}", "TEST_ON_HOST=1"), "test")

    def test_the_vague_ticket_alone_is_named_when_nothing_else_fails(self):
        """§4: spec is the last gate, not a skipped one."""
        r = self.repo()
        r.write(r.calc, CALC_PLUS)
        r.commit()
        ticket = self.outside("ticket.md")
        ticket.write_text(ticket_text(criteria=VAGUE_CRITERIA), encoding="utf-8")
        self.assert_nogo_at(self.light(r, f"TICKET={ticket}", "TEST_ON_HOST=1"), "spec")


class Range(LightCase):
    def test_the_default_is_the_last_commit(self):
        """§6: a weakening in an earlier commit is not judged."""
        r = self.repo()
        r.write(r.tests, TESTS_WEAK)
        r.commit("weaken")
        r.write(r.calc, CALC_PLUS)
        r.commit("harmless")
        self.assert_go(self.light(r), GO_DEFAULT)

    def test_base_alone_widens_the_range_to_head(self):
        """§6: BASE..HEAD, HEAD the checked-out commit."""
        r = self.repo()
        first = r.sha()
        r.write(r.tests, TESTS_WEAK)
        r.commit("weaken")
        r.write(r.calc, CALC_PLUS)
        r.commit("harmless")
        self.assert_nogo_at(self.light(r, f"BASE={first}"), "test-weakening")
        self.assert_go(self.light(r, f"BASE={r.sha('HEAD~1')}", f"HEAD={r.sha()}"), GO_DEFAULT)

    def test_the_range_is_the_merge_base_to_head(self):
        """§6: what the branch did, not what the base branch did since."""
        r = self.repo()
        r.git("checkout", "-q", "-b", "feature")
        r.write(r.calc, CALC_PLUS)
        r.commit("feature")
        r.git("checkout", "-q", "main")
        r.write(r.tests, TESTS_MORE)
        r.commit("main moves on")
        # A plain main..feature diff would show feature losing main's new assertion.
        self.assert_go(self.light(r, "BASE=main", "HEAD=feature"), GO_DEFAULT)

    def test_head_names_a_commit_that_is_not_checked_out(self):
        """§6: HEAD= is the commit judged."""
        r = self.repo()
        r.git("checkout", "-q", "-b", "feature")
        r.write(r.tests, TESTS_WEAK)
        r.commit("feature")
        r.git("checkout", "-q", "main")
        self.assert_nogo_at(self.light(r, "BASE=main", "HEAD=feature"), "test-weakening")

    def test_a_root_commit_is_judged_against_the_empty_tree(self):
        """§6: the whole tree is the diff; the repository's contract is the head's."""
        r = self.repo()
        self.assert_go(self.light(r), GO_DEFAULT.replace("risk low, auto-merge", "risk high, review"))

    def test_an_open_stdin_nobody_writes_to_does_not_stall_the_root_commit(self):
        """§6, §8: the empty tree of a root commit, run from a hook whose stdin is a pipe
        that stays open. The light tier reads no stdin, so it answers all the same."""
        r = self.repo()
        out, err = self.outside("stdout"), self.outside("stderr")
        with open(out, "w") as o, open(err, "w") as e:
            proc = subprocess.Popen([sys.executable, "-m", "core", "gates", "--light"], cwd=r.path,
                                    env=clean_env(), stdin=subprocess.PIPE, stdout=o, stderr=e)
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                self.fail("no answer in 8 s: the light tier is waiting on its inherited stdin")
            finally:
                proc.stdin.close()
        self.assertTrue(out.read_text().startswith("GO: gates-light"), out.read_text())

    def test_a_base_that_is_not_a_commit_is_a_nogo(self):
        """§5."""
        r = self.repo()
        self.assert_nogo(self.light(r, "BASE=no-such-ref"), f"NO-GO: gates-light {DASH} ")


class Staged(LightCase):
    def staged(self, **kw):
        r = self.repo(**kw)
        r.write(r.calc, CALC_PLUS)
        r.git("add", "-A")
        return r

    def frozen(self, r):
        """Everything STAGED=1 must leave alone, read without disturbing it."""
        r.git("status", "--porcelain=v2")  # let git settle the index's stat data first
        r.git("status", "--porcelain=v2")
        return {
            "files": snapshot(r.path),
            "status": r.git("status", "--porcelain=v2"),
            "head": r.sha(),
            "index_mtime": os.stat(r.path / ".git" / "index").st_mtime_ns,
        }

    def test_the_index_is_judged_against_head(self):
        """§6: `git diff --cached`."""
        r = self.staged()
        self.assert_go(self.light(r, "STAGED=1"), GO_DEFAULT)

    def test_the_last_commit_is_not_what_is_judged(self):
        """§6: HEAD against the index, not HEAD~1 against HEAD."""
        r = self.repo()
        r.write(r.tests, TESTS_WEAK)
        r.commit("weaken")
        r.write(r.calc, CALC_PLUS)
        r.git("add", "-A")
        self.assert_go(self.light(r, "STAGED=1"), GO_DEFAULT)

    def test_a_staged_weakening_is_a_nogo_even_when_the_working_tree_undoes_it(self):
        """§6: the staged state is what is judged."""
        r = self.repo()
        r.write(r.tests, TESTS_WEAK)
        r.git("add", "-A")
        r.write(r.tests, TESTS)
        self.assert_nogo_at(self.light(r, "STAGED=1"), "test-weakening")

    def test_a_staged_platform_path_is_high_risk(self):
        """§6, §3."""
        r = self.repo()
        r.write("Makefile", "all:\n\ttrue\n")
        r.git("add", "-A")
        self.assert_go(self.light(r, "STAGED=1"), GO_DEFAULT.replace("risk low, auto-merge", "risk high, review"))

    def test_the_perimeter_is_judged_on_the_staged_paths(self):
        """§6, §4."""
        r = self.repo()
        r.write("backend/other.py", "x = 1\n")
        r.git("add", "-A")
        ticket = self.outside("ticket.md")
        ticket.write_text(ticket_text(), encoding="utf-8")
        self.assert_nogo_at(self.light(r, "STAGED=1", f"TICKET={ticket}"), "perimeter")

    def test_the_committed_head_contract_judges_the_staged_change(self):
        """§7: under STAGED=1 the contract is the committed HEAD's, so a staged edit of
        workload.env cannot move the test paths away from the weakened file."""
        r = self.repo()
        r.write(r.tests, TESTS_WEAK)
        r.write(r.contract, r.contract_text(WORKLOAD_TEST_PATHS="docs/*.md"))
        r.git("add", "-A")
        self.assert_nogo_at(self.light(r, "STAGED=1"), "test-weakening")

    def test_nothing_staged_is_a_nogo(self):
        """§6."""
        r = self.repo()
        self.assert_nogo(self.light(r, "STAGED=1"), f"NO-GO: gates-light {DASH} ")

    def test_staged_with_a_base_is_a_nogo(self):
        """§6: the range is HEAD against the index; a BASE contradicts it."""
        r = self.staged()
        self.assert_nogo(self.light(r, "STAGED=1", f"BASE={r.sha()}"), f"NO-GO: gates-light {DASH} ")

    def test_the_repository_is_byte_identical_after_a_staged_run(self):
        """§6: no commit, worktree or object is written to the repository or its .git."""
        r = self.staged()
        r.write("notes.txt", "untracked\n")
        before = self.frozen(r)
        self.assert_go(self.light(r, "STAGED=1"))
        after = {"files": snapshot(r.path), "head": r.sha(),
                 "index_mtime": os.stat(r.path / ".git" / "index").st_mtime_ns}
        after["status"] = r.git("status", "--porcelain=v2")
        for key in after:
            self.assertEqual(before[key], after[key], key)
        self.assertEqual(r.git("worktree", "list").count("\n"), 0)

    def test_the_repository_is_byte_identical_after_a_staged_run_on_the_host(self):
        """§4, §6: the suite's checkout is outside the repository and shares nothing writable."""
        r = self.staged(test_cmd=suite_cmd(leak=True))
        before = self.frozen(r)
        self.assert_go(self.light(r, "STAGED=1", "TEST_ON_HOST=1"), GO_HOST)
        self.assertEqual(before["files"], snapshot(r.path))
        self.assertEqual(before["head"], r.sha())
        self.assertEqual(before["status"], r.git("status", "--porcelain=v2"))

    def test_the_suite_sees_the_staged_state_not_the_working_tree(self):
        """§4: an unstaged edit that would break the suite never reaches it."""
        r = self.staged()
        r.write(r.calc, CALC_BROKEN)
        self.assert_go(self.light(r, "STAGED=1", "TEST_ON_HOST=1"), GO_HOST)

    def test_and_a_staged_break_fails_even_when_the_working_tree_is_fine(self):
        """§4: the mirror, so the case above cannot pass for the wrong reason."""
        r = self.repo()
        r.write(r.calc, CALC_BROKEN)
        r.git("add", "-A")
        r.write(r.calc, CALC)
        self.assert_nogo_at(self.light(r, "STAGED=1", "TEST_ON_HOST=1"), "test")

    def test_a_staged_fix_with_its_test_is_proved_on_the_base(self):
        """§4: test-proof on HEAD with the staged test copied onto it."""
        r = self.repo()
        r.write(r.calc, CALC_FIXED)
        r.write(r.tests, TESTS_NEG)
        r.git("add", "-A")
        r.write(r.tests, TESTS)
        self.assert_go(self.light(r, "STAGED=1", "TEST_ON_HOST=1"), GO_HOST)


class Leaks(LightCase):
    def test_what_the_suite_writes_never_lands_in_the_repository(self):
        """§4: a throwaway checkout outside the repository."""
        r = self.repo(test_cmd=suite_cmd(leak=True))
        r.write(r.calc, CALC_FIXED)
        r.write(r.tests, TESTS_NEG)
        r.commit()
        before = snapshot(r.path)
        self.assert_go(self.light(r, "TEST_ON_HOST=1"), GO_HOST)
        self.assertEqual(before, snapshot(r.path))
        self.assertEqual(r.git("status", "--porcelain"), "")

    def test_without_gates_out_nothing_new_appears_in_the_working_tree(self):
        """§6: `without it nothing is written anywhere`."""
        r = self.repo()
        r.write(r.calc, CALC_PLUS)
        r.commit()
        before = snapshot(r.path, git=False)
        self.assert_go(self.light(r))
        self.assertEqual(before, snapshot(r.path, git=False))
        self.assertFalse((r.path / ".gates-out").exists())


class BaseContract(LightCase):
    def test_a_head_that_points_the_test_paths_elsewhere_is_still_judged_by_the_base(self):
        """§7: the base's workload.env is read, so a change cannot loosen what judges it."""
        r = self.repo()
        r.write(r.tests, TESTS_WEAK)
        r.write(r.contract, r.contract_text(WORKLOAD_TEST_PATHS="docs/*.md"))
        r.commit()
        p = self.light(r)
        self.assert_nogo_at(p, "test-weakening")
        self.assertIn("test_calc.py", p.stdout + p.stderr)

    def test_a_head_that_empties_the_test_paths_is_still_judged_by_the_base(self):
        """§7: the same, with the key emptied."""
        r = self.repo()
        r.write(r.tests, TESTS_WEAK)
        r.write(r.contract, r.contract_text(WORKLOAD_TEST_PATHS=""))
        r.commit()
        p = self.light(r)
        self.assert_nogo_at(p, "test-weakening")
        self.assertIn("test_calc.py", p.stdout + p.stderr)

    def test_the_heads_contract_is_read_only_when_the_base_has_none(self):
        """§7: the base has no contract, the head's own judges it."""
        r = self.repo(contract=False)
        r.write(r.contract, r.contract_text())
        r.write(r.tests, TESTS_WEAK)
        r.commit("the contract arrives, and a weakening")
        self.assert_nogo_at(self.light(r), "test-weakening")

    def test_no_contract_at_base_or_head_is_a_nogo(self):
        """§7."""
        r = self.repo(contract=False)
        r.write(r.calc, CALC_PLUS)
        r.commit()
        self.assert_nogo(self.light(r), f"NO-GO: gates-light {DASH} ")

    def test_the_bases_policy_env_is_read(self):
        """§7: policy.env from the base, over the platform policy."""
        r = self.repo()
        r.write(".lights-out/policy.env",
                "# Provenance, decision: the scratch repository keeps its migrations here.\n"
                "RISK_HIGH_MIGRATIONS=backend/migrations/*\n")
        r.commit("policy")
        r.write("backend/migrations/0001.sql", "select 1;\n")
        r.commit("a migration")
        self.assert_go(self.light(r), GO_DEFAULT.replace("risk low, auto-merge", "risk high, review"))

    def test_without_that_policy_the_same_change_is_low_risk(self):
        """§7: the control for the case above."""
        r = self.repo()
        r.write("backend/migrations/0001.sql", "select 1;\n")
        r.commit("a migration")
        self.assert_go(self.light(r), GO_DEFAULT)

    def test_the_repositorys_own_platform_policy_is_not_read(self):
        """§7: the platform policy is the package's own merge.env."""
        r = self.repo()
        r.write("policy/merge.env", "RISK_HIGH_PLATFORM=\nRISK_SIZE_MEDIUM_LINES=100000\n")
        r.commit("a lax policy")
        r.write("Makefile", "all:\n\ttrue\n")
        r.commit("a platform path")
        self.assert_go(self.light(r), GO_DEFAULT.replace("risk low, auto-merge", "risk high, review"))


class GatesOut(LightCase):
    def test_a_go_writes_the_verdict_in_the_shape_of_make_gates(self):
        """§6: GATES, RISK_LEVEL, RISK_DECISION and RAN; no FAILED on a GO."""
        r = self.repo()
        r.write(r.calc, CALC_PLUS)
        r.commit()
        out = self.outside("out")
        out.mkdir()
        self.assert_go(self.light(r, f"GATES_OUT={out}"), GO_DEFAULT)
        verdict = read_env(out / "verdict.env")
        ran = words(verdict.pop("RAN"))
        self.assertEqual(verdict, {"GATES": "GO", "RISK_LEVEL": "low", "RISK_DECISION": "auto-merge"})
        self.assertEqual(ran, ["risk", "test-weakening"])

    def test_a_nogo_names_the_failed_gate(self):
        """§6: FAILED on a gate NO-GO, the risk of the range, what ran."""
        r = self.repo()
        r.write(r.tests, TESTS_WEAK)
        r.commit()
        out = self.outside("out")
        out.mkdir()
        self.assert_nogo_at(self.light(r, f"GATES_OUT={out}"), "test-weakening")
        verdict = read_env(out / "verdict.env")
        ran = words(verdict.pop("RAN"))
        self.assertEqual(verdict, {"GATES": "NO-GO", "FAILED": "test-weakening",
                                   "RISK_LEVEL": "low", "RISK_DECISION": "auto-merge"})
        self.assertEqual(ran[0], "risk")
        self.assertIn("test-weakening", ran)

    def test_every_gate_that_ran_is_listed_in_order(self):
        """§4, §6: RAN with both options is the six, in the order of §4."""
        r = self.repo()
        r.write(r.calc, CALC_PLUS)
        r.commit()
        ticket = self.outside("ticket.md")
        ticket.write_text(ticket_text(), encoding="utf-8")
        out = self.outside("out")
        out.mkdir()
        self.assert_go(self.light(r, f"TICKET={ticket}", "TEST_ON_HOST=1", f"GATES_OUT={out}"), GO_BOTH)
        self.assertEqual(words(read_env(out / "verdict.env")["RAN"]), GATE_ORDER)

    def test_the_risk_of_a_high_risk_change_is_in_the_verdict(self):
        """§6: RISK_LEVEL and RISK_DECISION come from the classifier."""
        r = self.repo()
        r.write("Makefile", "all:\n\ttrue\n")
        r.commit()
        out = self.outside("out")
        out.mkdir()
        self.assert_go(self.light(r, f"GATES_OUT={out}"))
        verdict = read_env(out / "verdict.env")
        self.assertEqual((verdict["RISK_LEVEL"], verdict["RISK_DECISION"]), ("high", "review"))

    def test_an_output_directory_that_does_not_exist_yet_is_made(self):
        """§6: `GATES_OUT=<dir> writes verdict.env`, as `make gates` makes its own."""
        r = self.repo()
        r.write(r.calc, CALC_PLUS)
        r.commit()
        out = self.outside("deep") / "out"
        self.assert_go(self.light(r, f"GATES_OUT={out}"))
        self.assertTrue((out / "verdict.env").is_file())


class Workload(LightCase):
    def test_the_bundled_form_is_read_from_the_workload_directory(self):
        """§6: `<dir>/workload.env` for the bundled app, paths relative to the workload."""
        r = self.repo(workload="bundled", bundled=True)
        r.write(r.tests, TESTS_WEAK)
        r.commit()
        p = self.light(r, "WORKLOAD=bundled")
        self.assert_nogo_at(p, "test-weakening")
        self.assertIn("bundled/backend/tests/test_calc.py", p.stdout + p.stderr)

    def test_the_bundled_form_passes_a_clean_change(self):
        """§6."""
        r = self.repo(workload="bundled", bundled=True)
        r.write(r.calc, CALC_PLUS)
        r.commit()
        self.assert_go(self.light(r, "WORKLOAD=bundled"), GO_DEFAULT)

    def test_the_attached_form_is_read_from_the_workloads_lights_out_directory(self):
        """§6: `<dir>/.lights-out/` under a directory of the repository."""
        r = self.repo(workload="svc")
        r.write(r.tests, TESTS_WEAK)
        r.commit()
        self.assert_nogo_at(self.light(r, "WORKLOAD=svc"), "test-weakening")

    def test_the_default_workload_is_the_repositorys_top(self):
        """§6."""
        r = self.repo()
        r.write(r.tests, TESTS_WEAK)
        r.commit()
        self.assert_nogo_at(self.light(r), "test-weakening")

    def test_a_workload_directory_with_no_contract_is_a_nogo(self):
        """§6, §7."""
        r = self.repo()
        r.write(r.calc, CALC_PLUS)
        r.commit()
        self.assert_nogo(self.light(r, "WORKLOAD=nowhere"), f"NO-GO: gates-light {DASH} ")


if __name__ == "__main__":
    unittest.main()

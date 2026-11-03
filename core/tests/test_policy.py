"""Tests for core/policy.py, written from docs/adr/0036 §5 and the CLI contract
(--platform, --workload-env, --overrides, --out), never from the implementation.

Every test writes its own platform-defaults file in a temp dir instead of
reading policy/merge.env: the real file's values are a separate decision, and
the override rules (what is looser, what is refused) must hold for any
defaults. The defaults below have non-empty lists, so "a glob dropped" has
something to drop.
"""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core import policy

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PY = REPO_ROOT / "core" / "policy.py"

PLATFORM = {
    "RISK_HIGH_MIGRATIONS": "db/migrations/*:schema/*",
    "RISK_HIGH_AUTH": "auth/*",
    "RISK_HIGH_PAYMENTS": "",
    "RISK_HIGH_PLATFORM": "gates/*:ci/*",
    "RISK_SIZE_MEDIUM_LINES": "200",
    "RISK_SIZE_EXCLUDE": "*.lock",
    "RISK_AUTO_MERGE_LEVELS": "low",
    "MUTATION_MARGIN": "0.10",
    "ERROR_RATE_MAX_DELTA": "0.01",
    "LATENCY_P95_MAX_DELTA": "0.25",
}
BASELINE = "0.8"
# The workload's contract has more keys than the baseline; only the baseline
# may reach the effective policy.
WORKLOAD = f"# a workload contract\nWORKLOAD_KILL_SWITCH=x\nMUTATION_BASELINE={BASELINE}\n"
# Sentinel: pass --overrides naming a file that does not exist.
MISSING = object()


def block(assignment, kind="decision"):
    return f"# Provenance, {kind}: written by the test.\n{assignment}\n"


def overrides(*assignments):
    """An override file: each assignment under its own provenance block."""
    return "\n".join(block(a) for a in assignments)


class PolicyTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.out = self.dir / "effective.env"

    def run_policy(self, text=None, *, platform=None, baseline=BASELINE):
        """text: override-file content, MISSING, or None (no --overrides)."""
        defaults = {**PLATFORM, **(platform or {})}
        (self.dir / "platform.env").write_text(
            "# test defaults\n" + "".join(f"{k}={v}\n" for k, v in defaults.items())
        )
        (self.dir / "workload.env").write_text(
            WORKLOAD.replace(f"={BASELINE}\n", f"={baseline}\n")
        )
        cmd = [
            "--platform", str(self.dir / "platform.env"),
            "--workload-env", str(self.dir / "workload.env"),
            "--out", str(self.out),
        ]
        if text is MISSING:
            cmd += ["--overrides", str(self.dir / "no-such-policy.env")]
        elif text is not None:
            (self.dir / "policy.env").write_text(text)
            cmd += ["--overrides", str(self.dir / "policy.env")]
        # In process: the same argv, exit code, stdout and stderr as the
        # script, without a Python start-up per case (CliEntryTests runs
        # the script itself once).
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = policy.main(cmd)
        return SimpleNamespace(returncode=rc, stdout=out.getvalue(), stderr=err.getvalue())

    def effective(self):
        pairs = []
        for line in self.out.read_text().splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            self.assertEqual(sep, "=", f"effective line is not KEY=VALUE: {line!r}")
            pairs.append((key, value))
        keys = [k for k, _ in pairs]
        self.assertEqual(len(keys), len(set(keys)), f"a key is written twice: {keys}")
        return dict(pairs)

    def ok(self, proc):
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertEqual(proc.stdout, "")

    def nogo(self, proc, *names):
        """Exit 1, exactly one stdout line, and it contains one of names."""
        self.assertEqual(proc.returncode, 1, proc.stderr)
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, repr(proc.stdout))
        self.assertTrue(
            any(n in lines[0] for n in names),
            f"{lines[0]!r} names none of {names}",
        )
        return lines[0]

    def looser_lines(self, proc):
        return [l for l in proc.stderr.splitlines() if "looser" in l]

    def check_silent(self, key, value, **kw):
        proc = self.run_policy(overrides(f"{key}={value}"), **kw)
        self.ok(proc)
        self.assertNotIn("looser", proc.stderr.lower(), proc.stderr)
        self.assertEqual(self.effective()[key], value)

    def check_looser(self, key, value, **kw):
        # Looser is applied and reported, not refused.
        proc = self.run_policy(overrides(f"{key}={value}"), **kw)
        self.ok(proc)
        lines = self.looser_lines(proc)
        self.assertEqual(len(lines), 1, proc.stderr)
        self.assertIn(key, lines[0])
        self.assertEqual(self.effective()[key], value)


class NoOverridesTests(PolicyTestCase):
    def assert_defaults_plus_baseline(self, proc):
        self.ok(proc)
        self.assertEqual(proc.stderr, "")
        self.assertEqual(self.effective(), {**PLATFORM, "MUTATION_BASELINE": BASELINE})

    def test_overrides_file_that_does_not_exist_means_no_overrides(self):
        self.assert_defaults_plus_baseline(self.run_policy(MISSING))

    def test_no_overrides_flag_means_no_overrides(self):
        self.assert_defaults_plus_baseline(self.run_policy(None))

    def test_empty_overrides_file_means_no_overrides(self):
        self.assert_defaults_plus_baseline(self.run_policy(""))

    def test_comments_and_blank_lines_only_means_no_overrides(self):
        self.assert_defaults_plus_baseline(self.run_policy("# nothing here\n\n# or here\n"))

    def test_stale_effective_file_is_replaced(self):
        self.out.write_text("MUTATION_MARGIN=0.99\nSTALE=1\n")
        self.assert_defaults_plus_baseline(self.run_policy(None))

    def test_other_workload_keys_do_not_reach_the_effective_policy(self):
        self.ok(self.run_policy(None))
        self.assertNotIn("WORKLOAD_KILL_SWITCH", self.effective())


class StricterOverrideTests(PolicyTestCase):
    def test_all_nine_keys_are_overridable_and_stricter_is_silent(self):
        new = {
            "MUTATION_MARGIN": "0.05",
            "RISK_SIZE_MEDIUM_LINES": "99",
            "RISK_AUTO_MERGE_LEVELS": "",
            "RISK_HIGH_MIGRATIONS": "db/migrations/*:schema/*:extra/*",
            "RISK_HIGH_AUTH": "auth/*:login/*",
            "RISK_HIGH_PAYMENTS": "pay/*",
            "ERROR_RATE_MAX_DELTA": "0.005",
            "LATENCY_P95_MAX_DELTA": "0.1",
            "MUTATION_BASELINE": "0.9",
        }
        proc = self.run_policy(overrides(*[f"{k}={v}" for k, v in new.items()]))
        self.ok(proc)
        self.assertNotIn("looser", proc.stderr.lower(), proc.stderr)
        self.assertEqual(self.effective(), {**PLATFORM, **new})

    def test_untouched_keys_keep_their_defaults(self):
        self.ok(self.run_policy(overrides("MUTATION_MARGIN=0.05")))
        want = {**PLATFORM, "MUTATION_BASELINE": BASELINE, "MUTATION_MARGIN": "0.05"}
        self.assertEqual(self.effective(), want)

    def test_equal_to_default_is_silent(self):
        for key, value in PLATFORM.items():
            if key in ("RISK_HIGH_PLATFORM", "RISK_SIZE_EXCLUDE"):
                continue
            with self.subTest(key=key):
                self.check_silent(key, value)
        self.check_silent("MUTATION_BASELINE", BASELINE)

    def test_numerically_equal_spelling_is_silent(self):
        self.check_silent("MUTATION_MARGIN", "0.1")  # default is 0.10

    def test_size_is_compared_as_a_number_not_a_string(self):
        self.check_silent("RISK_SIZE_MEDIUM_LINES", "99")  # "99" > "200" as text

    def test_glob_order_and_extra_globs_are_silent(self):
        self.check_silent("RISK_HIGH_MIGRATIONS", "schema/*:db/migrations/*")
        self.check_silent("RISK_HIGH_MIGRATIONS", "x/*:schema/*:db/migrations/*")

    def test_globs_over_an_empty_default_are_silent(self):
        # What the real platform defaults rely on: a workload that declares
        # its own paths is never reported as dropping the platform's.
        self.check_silent("RISK_HIGH_PAYMENTS", "svc/pay*.py:svc/billing*.py")

    def test_auto_merge_levels_compare_as_a_set(self):
        both = {"RISK_AUTO_MERGE_LEVELS": "low:medium"}
        self.check_silent("RISK_AUTO_MERGE_LEVELS", "medium:low", platform=both)
        self.check_silent("RISK_AUTO_MERGE_LEVELS", "low", platform=both)
        self.check_silent("RISK_AUTO_MERGE_LEVELS", "", platform=both)

    def test_empty_lists_are_accepted(self):
        for key in ("RISK_HIGH_MIGRATIONS", "RISK_HIGH_AUTH", "RISK_HIGH_PAYMENTS"):
            with self.subTest(key=key):
                proc = self.run_policy(overrides(f"{key}="))
                self.ok(proc)
                self.assertEqual(self.effective()[key], "")

    def test_boundary_values_are_accepted(self):
        good = {
            "MUTATION_MARGIN": ["0.0", "1.0"],
            "MUTATION_BASELINE": ["0.0", "1.0"],
            "ERROR_RATE_MAX_DELTA": ["0.0", "1.0"],
            "LATENCY_P95_MAX_DELTA": ["0.0", "2.5"],
            "RISK_SIZE_MEDIUM_LINES": ["1"],
        }
        for key, values in good.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    proc = self.run_policy(overrides(f"{key}={value}"))
                    self.ok(proc)
                    self.assertEqual(self.effective()[key], value)

    def test_each_provenance_kind_is_accepted(self):
        for kind in ("measurement", "external", "decision"):
            with self.subTest(kind=kind):
                self.ok(self.run_policy(block("MUTATION_MARGIN=0.05", kind)))
                self.assertEqual(self.effective()["MUTATION_MARGIN"], "0.05")

    def test_provenance_may_sit_anywhere_in_the_comment_block(self):
        text = (
            "# A header comment, then a blank line.\n"
            "\n"
            "# Why this number: the suite is slow.\n"
            "# Provenance, measurement: ten runs, 2026-11-03.\n"
            "# More prose after the provenance line.\n"
            "MUTATION_MARGIN=0.05\n"
            "\n"
            "# Provenance, external: a vendor limit.\n"
            "RISK_SIZE_MEDIUM_LINES=99"  # no trailing newline
        )
        self.ok(self.run_policy(text))
        eff = self.effective()
        self.assertEqual((eff["MUTATION_MARGIN"], eff["RISK_SIZE_MEDIUM_LINES"]), ("0.05", "99"))


class MutationBaselineTests(PolicyTestCase):
    def test_baseline_comes_from_the_workload_env(self):
        self.ok(self.run_policy(None, baseline="0.65"))
        self.assertEqual(self.effective()["MUTATION_BASELINE"], "0.65")

    def test_baseline_override_replaces_the_workloads(self):
        proc = self.run_policy(overrides("MUTATION_BASELINE=0.85"))
        self.ok(proc)
        self.assertEqual(self.effective()["MUTATION_BASELINE"], "0.85")

    def test_baseline_looseness_is_relative_to_the_workloads_baseline(self):
        self.check_silent("MUTATION_BASELINE", "0.7", baseline="0.6")
        self.check_looser("MUTATION_BASELINE", "0.7", baseline="0.9")


class LooserOverrideTests(PolicyTestCase):
    def test_higher_margin_is_looser(self):
        self.check_looser("MUTATION_MARGIN", "0.20")

    def test_higher_size_is_looser(self):
        self.check_looser("RISK_SIZE_MEDIUM_LINES", "1000")  # "1000" < "200" as text

    def test_higher_error_rate_delta_is_looser(self):
        self.check_looser("ERROR_RATE_MAX_DELTA", "0.05")

    def test_higher_latency_delta_is_looser(self):
        self.check_looser("LATENCY_P95_MAX_DELTA", "0.5")

    def test_lower_baseline_is_looser(self):
        self.check_looser("MUTATION_BASELINE", "0.7")

    def test_auto_merge_level_the_default_lacks_is_looser(self):
        for value in ("medium", "low:medium", "medium:low"):
            with self.subTest(value=value):
                self.check_looser("RISK_AUTO_MERGE_LEVELS", value)

    def test_dropping_a_default_glob_is_looser(self):
        cases = {
            "RISK_HIGH_MIGRATIONS": ["db/migrations/*", "x/*:db/migrations/*", ""],
            "RISK_HIGH_AUTH": [""],
        }
        for key, values in cases.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.check_looser(key, value)

    def test_each_looser_key_gets_its_own_line(self):
        new = {
            "MUTATION_MARGIN": "0.20",
            "RISK_SIZE_MEDIUM_LINES": "1000",
            "RISK_AUTO_MERGE_LEVELS": "low:medium",
            "RISK_HIGH_MIGRATIONS": "db/migrations/*",
            "ERROR_RATE_MAX_DELTA": "0.05",
            "LATENCY_P95_MAX_DELTA": "0.5",
            "MUTATION_BASELINE": "0.7",
        }
        proc = self.run_policy(overrides(*[f"{k}={v}" for k, v in new.items()]))
        self.ok(proc)
        lines = self.looser_lines(proc)
        self.assertEqual(len(lines), len(new), proc.stderr)
        for key in new:
            with self.subTest(key=key):
                self.assertEqual(sum(key in l for l in lines), 1, proc.stderr)
        self.assertEqual(self.effective(), {**PLATFORM, **new})

    def test_only_the_looser_key_is_reported(self):
        proc = self.run_policy(overrides("MUTATION_MARGIN=0.05", "ERROR_RATE_MAX_DELTA=0.05"))
        self.ok(proc)
        lines = self.looser_lines(proc)
        self.assertEqual(len(lines), 1, proc.stderr)
        self.assertIn("ERROR_RATE_MAX_DELTA", lines[0])
        self.assertNotIn("MUTATION_MARGIN", lines[0])


class RefusedKeyTests(PolicyTestCase):
    def test_unknown_key_is_refused_by_name(self):
        # RISK_HIGH_PLATFORM and RISK_SIZE_EXCLUDE are platform-only: a
        # repository cannot loosen what counts as the platform.
        for key in ("RISK_HIGH_PLATFORM", "RISK_SIZE_EXCLUDE", "WORKLOAD_KILL_SWITCH", "SOMETHING_ELSE"):
            with self.subTest(key=key):
                self.nogo(self.run_policy(overrides(f"{key}=1")), key)

    def test_duplicate_key_is_refused_by_name(self):
        cases = {
            "MUTATION_MARGIN": ("0.05", "0.05"),
            "RISK_HIGH_AUTH": ("auth/*", "login/*"),
            "MUTATION_BASELINE": ("0.85", "0.9"),
        }
        for key, (first, second) in cases.items():
            with self.subTest(key=key):
                self.nogo(self.run_policy(overrides(f"{key}={first}", f"{key}={second}")), key)

    def test_high_in_auto_merge_levels_is_refused(self):
        for value in ("high", "low:high", "medium:high"):
            with self.subTest(value=value):
                self.nogo(
                    self.run_policy(overrides(f"RISK_AUTO_MERGE_LEVELS={value}")),
                    "RISK_AUTO_MERGE_LEVELS",
                )


class ProvenanceTests(PolicyTestCase):
    def test_key_without_any_comment_is_refused_by_name(self):
        self.nogo(self.run_policy("MUTATION_MARGIN=0.05\n"), "MUTATION_MARGIN")

    def test_comment_block_without_provenance_is_refused_by_name(self):
        text = "# I think this is fine.\nMUTATION_MARGIN=0.05\n"
        self.nogo(self.run_policy(text), "MUTATION_MARGIN")

    def test_provenance_separated_by_a_blank_line_is_refused_by_name(self):
        text = "# Provenance, decision: the owner said so.\n\nMUTATION_MARGIN=0.05\n"
        self.nogo(self.run_policy(text), "MUTATION_MARGIN")

    def test_provenance_after_the_key_is_refused_by_name(self):
        text = "MUTATION_MARGIN=0.05\n# Provenance, decision: the owner said so.\n"
        self.nogo(self.run_policy(text), "MUTATION_MARGIN")

    def test_unrecognised_provenance_kind_is_refused_by_name(self):
        for line in (
            "# Provenance, guess: it felt right.",
            "# Provenance: it felt right.",
        ):
            with self.subTest(line=line):
                self.nogo(self.run_policy(f"{line}\nMUTATION_MARGIN=0.05\n"), "MUTATION_MARGIN")

    def test_one_provenance_block_covers_one_key(self):
        # The second key has no comment block directly above it, only the
        # first key's line: it is the one named.
        text = (
            "# Provenance, decision: covers the line right below it.\n"
            "MUTATION_MARGIN=0.05\n"
            "RISK_SIZE_MEDIUM_LINES=99\n"
        )
        line = self.nogo(self.run_policy(text), "RISK_SIZE_MEDIUM_LINES")
        self.assertNotIn("MUTATION_MARGIN", line)

    def test_nogo_names_the_offending_key_only(self):
        text = block("MUTATION_MARGIN=0.05") + "\n" + block("ERROR_RATE_MAX_DELTA=abc")
        line = self.nogo(self.run_policy(text), "ERROR_RATE_MAX_DELTA")
        self.assertNotIn("MUTATION_MARGIN", line)

    def test_missing_provenance_is_refused_even_for_a_stricter_value(self):
        self.nogo(self.run_policy("RISK_SIZE_MEDIUM_LINES=1\n"), "RISK_SIZE_MEDIUM_LINES")


class MalformedValueTests(PolicyTestCase):
    NOT_A_DECIMAL = ["abc", "nan", "inf", "1e-2", "-0.1", ""]
    NOT_A_LIST = ["a/*::b/*", "a/*:", ":a/*", "a/* :b/*", "a b/*", "a/*\t:b/*"]

    MALFORMED = {
        # decimal in [0,1]
        "MUTATION_MARGIN": NOT_A_DECIMAL + ["1.5"],
        "MUTATION_BASELINE": NOT_A_DECIMAL + ["1.5"],
        "ERROR_RATE_MAX_DELTA": NOT_A_DECIMAL + ["1.5"],
        # decimal >= 0, no upper bound
        "LATENCY_P95_MAX_DELTA": NOT_A_DECIMAL,
        # integer >= 1
        "RISK_SIZE_MEDIUM_LINES": ["abc", "nan", "0", "-5", "1.5", "2e2", "1_000", ""],
        # colon-separated low/medium; every entry must be one
        "RISK_AUTO_MERGE_LEVELS": ["critical", "low:", ":low", "low::medium", "low:nope"],
        # colon-separated globs, no empty entry, no whitespace
        "RISK_HIGH_MIGRATIONS": NOT_A_LIST,
        "RISK_HIGH_AUTH": NOT_A_LIST,
        "RISK_HIGH_PAYMENTS": NOT_A_LIST,
    }

    def test_malformed_value_is_refused_by_name(self):
        for key, values in self.MALFORMED.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.nogo(self.run_policy(overrides(f"{key}={value}")), key)

    def test_spaces_around_equals_are_refused(self):
        for assignment in ("MUTATION_MARGIN = 0.05", "MUTATION_MARGIN= 0.05", "MUTATION_MARGIN =0.05"):
            with self.subTest(assignment=assignment):
                self.nogo(self.run_policy(overrides(assignment)), "MUTATION_MARGIN", "KEY=VALUE")

    def test_inline_comment_is_refused(self):
        self.nogo(
            self.run_policy(overrides("MUTATION_MARGIN=0.05 # a note")),
            "MUTATION_MARGIN", "KEY=VALUE",
        )

    def test_quoted_value_is_refused(self):
        self.nogo(
            self.run_policy(overrides('MUTATION_MARGIN="0.05"')),
            "MUTATION_MARGIN", "KEY=VALUE",
        )


class NotKeyValueTests(PolicyTestCase):
    def test_line_that_is_not_an_assignment_is_refused(self):
        for line in ("this is not an assignment", "MUTATION_MARGIN", "=0.05", "0.05"):
            with self.subTest(line=line):
                text = block("MUTATION_MARGIN=0.05") + "\n" + line + "\n"
                self.nogo(self.run_policy(text), "KEY=VALUE")

    def test_line_that_is_not_an_assignment_is_refused_on_its_own(self):
        self.nogo(self.run_policy("just some words\n"), "KEY=VALUE")


if __name__ == "__main__":
    unittest.main()


class CliEntryTests(unittest.TestCase):
    def test_runs_as_a_script_from_the_repo_root(self):
        # The gates call `python3 core/policy.py ...` from the repo root.
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "platform.env").write_text("".join(f"{k}={v}\n" for k, v in PLATFORM.items()))
            (d / "workload.env").write_text(WORKLOAD)
            proc = subprocess.run(
                [sys.executable, str(POLICY_PY), "--platform", str(d / "platform.env"),
                 "--workload-env", str(d / "workload.env"), "--out", str(d / "out.env")],
                capture_output=True, text=True, cwd=REPO_ROOT,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn(f"MUTATION_BASELINE={BASELINE}", (d / "out.env").read_text())


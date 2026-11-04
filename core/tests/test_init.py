"""Tests for core/init.py, written from docs/adr/0042 §1, §6 and "Resolved while
planning" 4 and 8, never from the implementation.

The runtime matchers answer one question (Resolved 8): does a declared
runtime (`requires-python`, `engines.node`) admit the workbench's version, so
that the draft says `TOOLCHAIN_IMAGE=workbench`? PEP 440 specifiers and npm
ranges are the two languages; the workbench is Python 3.13 and Node 24
(workbench/Containerfile), the versions these tests pass in. A range init does
not understand is never admitted: a guess would put a repository on a
toolchain it did not declare.

The renderer is tested on a hand-built inference, not on a repository: every
key of the draft sits under a "# Provenance," comment (§6), and a committed
contract's plane keys are kept (Resolved 4).

Not asserted: a range that names a minor of the workbench's Node (`~24.1`,
`>=24.5`). The matcher is given a major only, and the workbench's own minor
(24.21.0) decides those; the ADR does not say which the matcher answers.
"""

import unittest

from core.init import node_admits, python_admits, render_workload_env

WORKBENCH_PYTHON = (3, 13)
WORKBENCH_NODE = 24

ELEVEN_KEYS = {
    "CANARY_VERSION",
    "MUTATION_BASELINE",
    "WORKLOAD_KILL_SWITCH",
    "WORKLOAD_SAMPLE_PATH",
    "WORKLOAD_LOCKFILES",
    "WORKLOAD_MUTATION_SCOPE",
    "WORKLOAD_TEST_ROOT",
    "TOOLCHAIN_IMAGE",
    "TEST_CMD",
    "SAST_CMD",
    "MUTATION_CMD",
}


class PythonAdmitsTest(unittest.TestCase):
    def check(self, spec, expected):
        self.assertIs(
            python_admits(spec, WORKBENCH_PYTHON),
            expected,
            f"requires-python = {spec!r} against Python 3.13",
        )

    def test_admitted(self):
        for spec in (
            "==3.13.*",
            ">=3.11",
            ">=3.11,<3.14",
            ">=3.13",
            "<=3.13",
            "~=3.12",
            "~=3.13",
            "~=3.11",
            "!=3.12.*",
            ">3.12",
            "",
        ):
            with self.subTest(spec=spec):
                self.check(spec, True)

    def test_not_admitted(self):
        for spec in (
            "==3.11.*",
            "==3.12.*",
            "<3.13",
            ">=3.11,<3.13",
            ">=3.14",
            ">3.13",
            "!=3.13.*",
            "~=3.11.0",
        ):
            with self.subTest(spec=spec):
                self.check(spec, False)

    def test_spaces_around_clauses_do_not_change_the_answer(self):
        self.check(">=3.11, <3.13", False)
        self.check(">=3.11, <3.14", True)

    def test_the_answer_depends_on_the_version_asked(self):
        self.assertTrue(python_admits("==3.12.*", (3, 12)))
        self.assertFalse(python_admits("==3.12.*", (3, 13)))
        self.assertTrue(python_admits(">=3.11,<3.13", (3, 12)))
        self.assertFalse(python_admits(">=3.11,<3.13", (3, 13)))


class NodeAdmitsTest(unittest.TestCase):
    def check(self, range_text, expected):
        self.assertIs(
            node_admits(range_text, WORKBENCH_NODE),
            expected,
            f"engines.node = {range_text!r} against Node 24",
        )

    def test_admitted(self):
        for range_text in (
            ">=22",
            ">=20",
            ">=18 <25",
            "^24",
            "24.x",
            "24",
            "*",
            "",
            "^20 || ^24",
            "22 - 24",
            ">20",
            "<=24",
        ):
            with self.subTest(range_text=range_text):
                self.check(range_text, True)

    def test_not_admitted(self):
        for range_text in (
            "^20",
            "^22",
            "22",
            "18 - 22",
            ">=25",
            "<24",
            ">=18 <24",
            "^18 || ^20",
        ):
            with self.subTest(range_text=range_text):
                self.check(range_text, False)

    def test_an_unparseable_range_is_not_admitted(self):
        self.check("latest", False)

    def test_the_answer_depends_on_the_major_asked(self):
        self.assertTrue(node_admits("^20", 20))
        self.assertFalse(node_admits("^20", 24))
        self.assertTrue(node_admits("18 - 22", 22))
        self.assertFalse(node_admits("18 - 22", 24))


def inference():
    """What an inference of a repository holds, for the keys the draft reads."""
    return {
        "lockfiles": "uv.lock",
        "lockfiles_evidence": "uv.lock at the root",
        "scope": "demo/",
        "scope_evidence": "demo/__init__.py exists",
        "test_root": "",
        "test_root_evidence": "nothing to strip",
        "toolchain": "workbench",
        "toolchain_evidence": "requires-python admits the workbench",
        "test_cmd": "uv run --locked pytest tests -q",
        "test_cmd_evidence": "tests/ exists",
        "sast_cmd": "sh .lights-out/runners/sast.sh demo",
        "sast_cmd_evidence": "bandit over the package",
        "mutation_cmd": 'sh .lights-out/runners/mutation.sh demo "uv run --locked pytest tests -q -x"',
        "mutation_cmd_evidence": "cosmic-ray over the package",
    }


def parse(text):
    """(key -> value, key -> the comment block directly above it)."""
    values = {}
    blocks = {}
    block = []
    for line in text.split("\n"):
        if line.startswith("#"):
            block.append(line)
        elif not line.strip():
            block = []
        else:
            key, sep, value = line.partition("=")
            assert sep, f"not KEY=VALUE: {line!r}"
            assert key not in values, f"{key} appears twice"
            values[key] = value
            blocks[key] = block
            block = []
    return values, blocks


class RenderWorkloadEnvTest(unittest.TestCase):
    def render(self, committed):
        return render_workload_env(inference(), committed, "2026-11-03", "abc1234")

    def test_exactly_the_eleven_keys_once_each(self):
        for committed in ({}, {"CANARY_VERSION": "1"}):
            with self.subTest(committed=committed):
                values, _ = parse(self.render(committed))
                self.assertEqual(set(values), ELEVEN_KEYS)

    def test_every_key_has_a_provenance_line_directly_above(self):
        for committed in ({}, {"CANARY_VERSION": "1"}):
            with self.subTest(committed=committed):
                _, blocks = parse(self.render(committed))
                for key in ELEVEN_KEYS:
                    self.assertTrue(
                        any(line.startswith("# Provenance,") for line in blocks[key]),
                        f"{key} has no '# Provenance,' line in the comment block above it: {blocks[key]}",
                    )

    def test_no_committed_contract_leaves_the_plane_keys_and_the_baseline_empty(self):
        values, _ = parse(self.render({}))
        for key in ("CANARY_VERSION", "WORKLOAD_KILL_SWITCH", "WORKLOAD_SAMPLE_PATH", "MUTATION_BASELINE"):
            self.assertEqual(values[key], "", key)

    def test_the_inferred_values_are_the_inferences(self):
        values, _ = parse(self.render({}))
        d = inference()
        self.assertEqual(values["WORKLOAD_LOCKFILES"], d["lockfiles"])
        self.assertEqual(values["WORKLOAD_MUTATION_SCOPE"], d["scope"])
        self.assertEqual(values["WORKLOAD_TEST_ROOT"], d["test_root"])
        self.assertEqual(values["TOOLCHAIN_IMAGE"], d["toolchain"])
        self.assertEqual(values["TEST_CMD"], d["test_cmd"])
        self.assertEqual(values["SAST_CMD"], d["sast_cmd"])
        self.assertEqual(values["MUTATION_CMD"], d["mutation_cmd"])

    def test_the_evidence_is_in_the_comment_above_its_key(self):
        _, blocks = parse(self.render({}))
        d = inference()
        for key, evidence in (
            ("WORKLOAD_LOCKFILES", d["lockfiles_evidence"]),
            ("WORKLOAD_MUTATION_SCOPE", d["scope_evidence"]),
            ("TOOLCHAIN_IMAGE", d["toolchain_evidence"]),
            ("TEST_CMD", d["test_cmd_evidence"]),
        ):
            self.assertIn(evidence, "\n".join(blocks[key]), key)

    def test_a_committed_plane_key_is_kept_and_says_so(self):
        values, blocks = parse(self.render({"CANARY_VERSION": "1"}))
        self.assertEqual(values["CANARY_VERSION"], "1")
        self.assertTrue(
            blocks["CANARY_VERSION"][-1].startswith("# Provenance, kept"),
            f"the line above CANARY_VERSION: {blocks['CANARY_VERSION']}",
        )

    def test_a_committed_contract_does_not_carry_its_other_keys_into_the_draft(self):
        committed = {
            "CANARY_VERSION": "1",
            "MUTATION_BASELINE": "0.9",
            "WORKLOAD_LOCKFILES": "old.lock",
            "TEST_CMD": "echo old",
        }
        values, _ = parse(self.render(committed))
        self.assertEqual(values["MUTATION_BASELINE"], "")
        self.assertEqual(values["WORKLOAD_LOCKFILES"], "uv.lock")
        self.assertEqual(values["TEST_CMD"], inference()["test_cmd"])

    def test_the_other_plane_keys_are_kept_too(self):
        committed = {"CANARY_VERSION": "1", "WORKLOAD_KILL_SWITCH": "ks", "WORKLOAD_SAMPLE_PATH": "/p"}
        values, _ = parse(self.render(committed))
        self.assertEqual(values["WORKLOAD_KILL_SWITCH"], "ks")
        self.assertEqual(values["WORKLOAD_SAMPLE_PATH"], "/p")

    def test_no_value_carries_a_dollar_or_an_inline_comment(self):
        # make's include would expand the one and cut at the other (Resolved 2).
        text = self.render({"CANARY_VERSION": "1"})
        for line in text.split("\n"):
            if line and not line.startswith("#"):
                self.assertNotIn("$", line)
                self.assertNotIn("#", line)

    def test_the_file_ends_with_one_newline(self):
        text = self.render({})
        self.assertTrue(text.endswith("\n"))
        self.assertFalse(text.endswith("\n\n"))


if __name__ == "__main__":
    unittest.main()

"""Tests for the plain git hook recipes, written from docs/use-on-your-repo.md,
"Plain git hooks", never from the recipes' text.

The guide holds two `sh` blocks that start with `#!/bin/sh` and, on the next
line, `# pre-commit:` or `# pre-push:`. Each test copies the block as the
guide prints it into a scratch repository's `.git/hooks/` and runs git.

The pre-commit hook runs the light tier, `lights-out-gates --light STAGED=1`:
a staged change that removes an assertion is refused and no commit lands,
also when `git commit -a` or `git commit <path>` stages it; a clean change
lands; a commit with nothing staged (a reworded `--amend`) is not judged.

The pre-push hook runs the wrapper, `lights-out gates`, once per ref the push
sends: BASE the remote's commit for an update, the merge-base with the
remote's HEAD for a new branch, nothing for a delete. A NO-GO stops the push
and the remote does not move. The wrapper runs the gates image, which a unit
test does not pull: here `lights-out` on PATH is a stand-in that records its
arguments, reads its stdin as `podman run -i` does, and answers GO or NO-GO
as told. The real wrapper behind this hook was run by hand (the guide says
when and on what).
"""

import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

from core.tests.test_light import (CALC_PLUS, TESTS_WEAK, LightCase, clean_env)

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "use-on-your-repo.md"


def recipe(hook):
    """The guide's sh block for HOOK, as printed."""
    lines = GUIDE.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "```sh" and i + 2 < len(lines) and lines[i + 1] == "#!/bin/sh" \
                and lines[i + 2].startswith(f"# {hook}:"):
            end = lines.index("```", i + 1)
            return "\n".join(lines[i + 1:end]) + "\n"
    raise AssertionError(f"{GUIDE.name} has no sh block starting with #!/bin/sh and '# {hook}:'")


def executable(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class HookCase(LightCase):
    def setUp(self):
        super().setUp()
        self.bin = self.tmp / "bin"
        # lights-out-gates as the console script runs it: `gates` implied.
        executable(self.bin / "lights-out-gates", textwrap.dedent(f"""\
            #!{sys.executable}
            import sys
            sys.path.insert(0, {str(ROOT)!r})
            from core.__main__ import gates_main
            sys.exit(gates_main())
            """))

    def env(self, **extra):
        return clean_env(PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}", **extra)

    def git(self, r, *args, **extra):
        return subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=r.path,
                              env=self.env(**extra), capture_output=True, text=True,
                              encoding="utf-8", timeout=180, stdin=subprocess.DEVNULL)

    def install(self, r, hook):
        executable(r.path / ".git" / "hooks" / hook, recipe(hook))


class PreCommit(HookCase):
    def setUp(self):
        super().setUp()
        self.r = self.repo()
        self.install(self.r, "pre-commit")
        self.base = self.r.sha()

    def assert_refused(self, p):
        self.assertNotEqual(p.returncode, 0, p.stderr)
        self.assertIn("NO-GO: gates-light", p.stderr)
        self.assertIn("test-weakening", p.stderr)
        self.assertEqual(self.r.sha(), self.base, "a commit landed")

    def test_a_staged_change_that_removes_an_assertion_is_refused(self):
        self.r.write(self.r.tests, TESTS_WEAK)
        self.r.git("add", "-A")
        self.assert_refused(self.git(self.r, "commit", "-q", "-m", "weak"))

    def test_commit_a_is_judged_on_what_it_stages(self):
        self.r.write(self.r.tests, TESTS_WEAK)
        self.assert_refused(self.git(self.r, "commit", "-q", "-a", "-m", "weak"))

    def test_commit_with_a_path_is_judged_on_that_path(self):
        self.r.write(self.r.tests, TESTS_WEAK)
        self.assert_refused(self.git(self.r, "commit", "-q", "-m", "weak", self.r.tests))

    def test_a_clean_change_lands(self):
        self.r.write(self.r.calc, CALC_PLUS)
        self.r.git("add", "-A")
        p = self.git(self.r, "commit", "-q", "-m", "clean")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("GO: gates-light", p.stderr)
        self.assertNotEqual(self.r.sha(), self.base)

    def test_nothing_staged_is_not_judged(self):
        p = self.git(self.r, "commit", "-q", "--amend", "-m", "reworded")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("gates-light", p.stderr)
        self.assertEqual(self.r.git("log", "-1", "--format=%s"), "reworded")


class PrePush(HookCase):
    """`lights-out` is a stand-in for the wrapper (the module docstring says why)."""

    def setUp(self):
        super().setUp()
        self.calls = self.tmp / "calls"
        executable(self.bin / "lights-out", textwrap.dedent(f"""\
            #!/bin/sh
            cat >/dev/null
            echo "$*" >> {self.calls}
            if [ "${{FAKE_VERDICT:-GO}}" = GO ]; then echo "GO: gates"; else echo "NO-GO: gates — planted"; exit 1; fi
            """))
        self.r = self.repo()
        self.remote = self.tmp / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(self.remote)], env=clean_env(), check=True)
        self.r.git("remote", "add", "origin", str(self.remote))
        self.r.git("push", "-q", "origin", "main")
        self.r.git("fetch", "-q", "origin")
        self.r.git("remote", "set-head", "origin", "main")
        self.install(self.r, "pre-push")

    def recorded(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def remote_sha(self, ref):
        return subprocess.run(["git", "--git-dir", str(self.remote), "rev-parse", ref],
                              env=clean_env(), capture_output=True, text=True).stdout.strip()

    def test_an_update_judges_what_the_remote_lacks(self):
        old = self.r.sha()
        self.r.write(self.r.calc, CALC_PLUS)
        new = self.r.commit("one")
        self.r.write("README", "two\n")
        new = self.r.commit("two")
        p = self.git(self.r, "push", "-q", "origin", "main")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.recorded(), [f"gates BASE={old} HEAD={new}"])
        self.assertEqual(self.remote_sha("main"), new)

    def test_a_new_branch_is_judged_from_the_remote_head(self):
        fork = self.r.sha()
        self.r.git("switch", "-q", "-c", "feature")
        self.r.write(self.r.calc, CALC_PLUS)
        self.r.commit("one")
        self.r.write("README", "two\n")
        new = self.r.commit("two")
        p = self.git(self.r, "push", "-q", "origin", "feature")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.recorded(), [f"gates BASE={fork} HEAD={new}"])

    def test_every_ref_of_one_push_is_judged(self):
        old = self.r.sha()
        self.r.write(self.r.calc, CALC_PLUS)
        main = self.r.commit("on main")
        self.r.git("switch", "-q", "-c", "feature")
        self.r.write("README", "two\n")
        feature = self.r.commit("on feature")
        p = self.git(self.r, "push", "-q", "origin", "main", "feature")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(sorted(self.recorded()),
                         sorted([f"gates BASE={old} HEAD={main}", f"gates BASE={old} HEAD={feature}"]))

    def test_a_no_go_stops_the_push(self):
        old = self.r.sha()
        self.r.write(self.r.calc, CALC_PLUS)
        self.r.commit("one")
        p = self.git(self.r, "push", "-q", "origin", "main", FAKE_VERDICT="NO-GO")
        self.assertNotEqual(p.returncode, 0, p.stderr)
        self.assertIn("NO-GO: gates", p.stdout + p.stderr)
        self.assertEqual(self.remote_sha("main"), old, "the remote moved")

    def test_a_delete_is_not_judged(self):
        self.r.git("push", "-q", "--no-verify", "origin", "main:gone")
        p = self.git(self.r, "push", "-q", "origin", ":gone")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.recorded(), [])

"""Tests for core/gates/toolchain.py, written from docs/adr/0042 §2-§4 and §7,
docs/adr/0084's amendment of 2026-11-16 (A3) and core/toolchain.sh's header,
never from the implementation.

The three forms of TOOLCHAIN_IMAGE; the preflight's NO-GOs, each naming what
is missing; where the command ran, for the gate's line and for `make gates`;
and the run: the workbench form in-process, the two engine forms through a
docker-compose of the test's own on PATH, which records what it was asked.
"""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest

from core.gates import NoGo, toolchain

DIGEST = "docker.io/library/node:24@sha256:" + "0123456789abcdef" * 4

FAKE_COMPOSE = """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_LOG"
case " $* " in
  *" build "*) [ -z "${FAKE_BUILD_FAILS:-}" ] || exit 1; echo built ;;
  *" run "*) echo "ran in the engine"; exit "${FAKE_RUN_RC:-0}" ;;
esac
"""


class Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.wl = os.path.join(self.dir, "wl")
        os.makedirs(self.wl + "/sub")
        os.makedirs(self.wl + "/.contract")
        self.sock = os.path.join(self.dir, "s.sock")
        s = socket.socket(socket.AF_UNIX)
        s.bind(self.sock)
        self.addCleanup(s.close)

    def env(self, **kw):
        env = {"WORKLOAD": self.wl, "WORKLOAD_CONTRACT": self.wl + "/.contract", "WORKBENCH_IMAGE": "lo-workbench-test"}
        env.update(kw)
        return env


class Form(unittest.TestCase):
    def test_the_three_forms(self):
        self.assertEqual(toolchain.form("workbench"), "workbench")
        self.assertEqual(toolchain.form("compose:backend-test"), "compose")
        for ref in ("node:24", "docker.io/library/node:24", DIGEST, "ghcr.io/astral-sh/uv:python3.12-trixie-slim"):
            self.assertEqual(toolchain.form(ref), "image", ref)

    def test_an_unknown_form_names_the_value(self):
        with self.assertRaises(NoGo) as no:
            toolchain.form("")
        self.assertIn("TOOLCHAIN_IMAGE is empty (docs/adr/0042 §2)", no.exception.reason)
        with self.assertRaises(NoGo) as no:
            toolchain.form("compose:")
        self.assertIn("TOOLCHAIN_IMAGE=compose: names no service", no.exception.reason)
        with self.assertRaises(NoGo) as no:
            toolchain.form("compose:a b")
        self.assertIn("TOOLCHAIN_IMAGE=compose:a b is not compose:<service>", no.exception.reason)
        for bad in ("Not An Image", "node 24", "Docker.IO/Library/Node:24", "docker.io/library/node:24@sha256:abc",
                    "-node", "node-"):
            with self.assertRaises(NoGo) as no:
                toolchain.form(bad)
            self.assertIn("TOOLCHAIN_IMAGE=%s is none of workbench, compose:<service> or an image reference" % bad,
                          no.exception.reason)


class Socket(Tmp):
    def test_the_socket_docker_host_names(self):
        self.assertEqual(toolchain.socket_path({"DOCKER_HOST": "unix://" + self.sock}), self.sock)
        self.assertEqual(toolchain.socket_path({"DOCKER_HOST": self.sock}), self.sock)
        open(self.dir + "/file", "w").close()
        for dh in (None, "", "unix://" + self.dir + "/missing.sock", self.dir + "/file", "unix://" + self.dir):
            env = {} if dh is None else {"DOCKER_HOST": dh}
            self.assertEqual(toolchain.socket_path(env), "", dh)


class Preflight(Tmp):
    def test_workbench_needs_no_engine_and_says_where(self):
        out = self.dir + "/gout"
        os.makedirs(out)
        self.assertEqual(toolchain.preflight(self.env(TOOLCHAIN_IMAGE="workbench", GATES_OUT=out)), "workbench")
        with open(out + "/toolchain.where") as fh:
            self.assertEqual(fh.read(), "workbench\n")
        self.assertEqual(toolchain.preflight(self.env(TOOLCHAIN_IMAGE="workbench", GATES_OUT=self.dir + "/none")),
                         "workbench")

    def test_isolated_workbench_needs_the_engine(self):
        env = self.env(TOOLCHAIN_IMAGE="workbench", TOOLCHAIN_ISOLATE="1")
        with self.assertRaises(NoGo) as no:
            toolchain.preflight(env)
        self.assertEqual(no.exception.reason,
                         "in workbench (isolated): the engine socket is not available and TOOLCHAIN_ISOLATE=1 needs the engine")
        self.assertEqual(toolchain.preflight(dict(env, DOCKER_HOST="unix://" + self.sock)), "workbench (isolated)")
        del env["WORKBENCH_IMAGE"]
        with self.assertRaises(NoGo) as no:
            toolchain.preflight(dict(env, DOCKER_HOST="unix://" + self.sock))
        self.assertIn("WORKBENCH_IMAGE not set", no.exception.reason)

    def test_engine_forms_without_a_socket_name_the_socket_and_the_value(self):
        open(self.wl + "/.contract/compose.yaml", "w").close()
        for value in ("compose:backend-test", "node:24", DIGEST):
            with self.assertRaises(NoGo) as no:
                toolchain.preflight(self.env(TOOLCHAIN_IMAGE=value))
            self.assertTrue(no.exception.reason.startswith("in %s: the engine socket is not available" % value),
                            no.exception.reason)
            self.assertIn("set TOOLCHAIN_IMAGE=workbench", no.exception.reason)
            self.assertEqual(toolchain.preflight(self.env(TOOLCHAIN_IMAGE=value, DOCKER_HOST="unix://" + self.sock)), value)

    def test_compose_needs_the_plane_half_of_the_contract(self):
        with self.assertRaises(NoGo) as no:
            toolchain.preflight(self.env(TOOLCHAIN_IMAGE="compose:x", DOCKER_HOST="unix://" + self.sock))
        self.assertEqual(no.exception.reason, "in compose:x: %s/.contract has no compose.yaml; the compose form needs "
                         "the plane half of the contract (docs/adr/0042 §7)" % self.wl)

    def test_the_workload_must_be_named(self):
        env = self.env(TOOLCHAIN_IMAGE="workbench")
        del env["WORKLOAD"]
        with self.assertRaises(NoGo) as no:
            toolchain.preflight(env)
        self.assertEqual(no.exception.reason, "WORKLOAD not set; run this via ./go, not directly")
        with self.assertRaises(NoGo) as no:
            toolchain.preflight(self.env())
        self.assertIn("TOOLCHAIN_IMAGE is empty", no.exception.reason)


class Run(Tmp):
    def setUp(self):
        super().setUp()
        self.cwd = os.getcwd()
        self.addCleanup(os.chdir, self.cwd)
        self.bin = self.dir + "/bin"
        os.makedirs(self.bin)
        with open(self.bin + "/docker-compose", "w") as fh:
            fh.write(FAKE_COMPOSE)
        os.chmod(self.bin + "/docker-compose", 0o755)
        self.log = self.dir + "/compose.log"
        self.caller = self.dir + "/caller"
        os.makedirs(self.caller)
        os.chdir(self.caller)

    def run_cmd(self, cmd, **kw):
        out = self.dir + "/out"
        env = self.env(PATH=self.bin + ":" + os.environ["PATH"], FAKE_LOG=self.log, **kw)
        with open(out, "w") as fh:
            rc = toolchain.run(cmd, env, stdout=fh)
        with open(out) as fh:
            return rc, fh.read()

    def calls(self):
        with open(self.log) as fh:
            return fh.read().splitlines()

    def test_workbench_runs_from_the_test_root_with_its_environment(self):
        rc, out = self.run_cmd('pwd -P; echo "ml=$MUTATION_LINES"; echo "uvdl=$UV_PYTHON_DOWNLOADS"; '
                               'echo "nc=$NO_COLOR"; echo "venv=$UV_PROJECT_ENVIRONMENT"; exit 7',
                               TOOLCHAIN_IMAGE="workbench", WORKLOAD_TEST_ROOT="sub", MUTATION_LINES="src/a.py:1-3")
        self.assertEqual(rc, 7)
        lines = out.splitlines()
        self.assertEqual(lines[0], os.path.realpath(self.wl + "/sub"))
        self.assertEqual(lines[1:4], ["ml=src/a.py:1-3", "uvdl=never", "nc=1"])
        self.assertTrue(lines[4].startswith("venv=" + os.path.realpath(self.caller) + "/.crew/cache/venv/")
                        or lines[4].startswith("venv=" + self.caller + "/.crew/cache/venv/"), lines[4])
        for d in ("uv", "npm", "venv"):
            self.assertTrue(os.path.isdir(self.caller + "/.crew/cache/" + d), d)
        self.assertFalse(os.path.exists(self.log), "the workbench form called the engine")

    def test_workbench_with_no_test_root_and_no_mutation_lines(self):
        rc, out = self.run_cmd('pwd -P; echo "ml=[${MUTATION_LINES-unset}]"', TOOLCHAIN_IMAGE="workbench")
        self.assertEqual(rc, 0)
        self.assertEqual(out.splitlines(), [os.path.realpath(self.wl), "ml=[]"])

    def test_the_venv_is_one_per_workload(self):
        a = toolchain.venv_dir("/c", self.wl)
        self.assertEqual(a, toolchain.venv_dir("/c", self.wl))
        self.assertNotEqual(a, toolchain.venv_dir("/c", self.dir))
        self.assertTrue(a.startswith("/c/venv/"))

    def test_a_test_root_that_is_not_there_is_the_toolchain_failing(self):
        rc, _ = self.run_cmd("true", TOOLCHAIN_IMAGE="workbench", WORKLOAD_TEST_ROOT="missing")
        self.assertEqual(rc, 125)

    def test_compose_builds_apart_runs_under_its_own_project_and_tears_down(self):
        rc, out = self.run_cmd("make test", TOOLCHAIN_IMAGE="compose:backend-test", MUTATION_LINES="all",
                               FAKE_RUN_RC="3")
        self.assertEqual(rc, 3)
        self.assertEqual(out, "ran in the engine\n")
        calls = self.calls()
        self.assertEqual(calls[0], "-p lo-toolchain --profile test build backend-test")
        self.assertEqual(calls[1], "-p lo-toolchain --profile test run --rm -T -e MUTATION_LINES=all backend-test sh -c make test")
        self.assertEqual(calls[2], "-p lo-toolchain --profile test down -v --remove-orphans")

    def test_a_failed_build_is_125_and_runs_nothing(self):
        for image in ("compose:backend-test", "node:24"):
            os.path.exists(self.log) and os.remove(self.log)
            rc, out = self.run_cmd("make test", TOOLCHAIN_IMAGE=image, FAKE_BUILD_FAILS="1")
            self.assertEqual(rc, 125, image)
            self.assertNotIn("ran in the engine", out)
            self.assertFalse([c for c in self.calls() if " run " in " %s " % c], image)

    def test_an_image_is_a_throwaway_built_from_the_workload(self):
        rc, out = self.run_cmd("npm test", TOOLCHAIN_IMAGE=DIGEST, WORKLOAD_TEST_ROOT="sub")
        self.assertEqual((rc, out), (0, "ran in the engine\n"))
        calls = self.calls()
        self.assertEqual(len(calls), 3)
        for call, verb in zip(calls, ("build toolchain", "run --rm -T toolchain sh -c npm test", "down --remove-orphans")):
            self.assertTrue(call.startswith("-p lo-toolchain -f "), call)
            self.assertTrue(call.endswith("/compose.yaml " + verb), call)
        tmp = calls[0].split(" -f ")[1].split(" ")[0]
        self.assertFalse(os.path.exists(tmp), "the throwaway compose file was left behind")

    def test_isolated_workbench_is_the_image_form_on_the_workbench_image(self):
        rc, _ = self.run_cmd("true", TOOLCHAIN_IMAGE="workbench", TOOLCHAIN_ISOLATE="1")
        self.assertEqual(rc, 0)
        self.assertIn("build toolchain", self.calls()[0])

    def test_a_bad_form_at_run_time_is_125(self):
        rc, _ = self.run_cmd("true", TOOLCHAIN_IMAGE="node 24")
        self.assertEqual(rc, 125)


class ImageFiles(unittest.TestCase):
    def test_nothing_of_the_host_is_mounted_and_the_caches_are_volumes(self):
        cf, compose = toolchain.image_files("node:24", "/ctx", "/tmp/x/Containerfile", "sub", "src/a.py:1")
        self.assertEqual(cf, "FROM node:24\nCOPY . /work\nWORKDIR /work\n")
        for want in ("context: /ctx", "dockerfile: /tmp/x/Containerfile", "working_dir: /work/sub",
                     "MUTATION_LINES: src/a.py:1", "UV_LINK_MODE: copy", 'NO_COLOR: "1"',
                     "lo-toolchain-uv:/root/.cache/uv", "lo-toolchain-npm:/root/.npm"):
            self.assertIn(want, compose)
        self.assertNotIn(":/work", compose.replace("/work/sub", ""))


class CommandLine(Tmp):
    def env(self, **kw):
        """This process's environment without the toolchain's own keys (./go ci sets some), plus the test's."""
        base = {k: v for k, v in os.environ.items()
                if k not in ("WORKLOAD_TEST_ROOT", "TOOLCHAIN_ISOLATE", "TOOLCHAIN_IMAGE", "MUTATION_LINES", "DOCKER_HOST",
                             "GATES_OUT", "PYTHONPATH")}
        return dict(base, **super().env(**kw))

    def test_preflight_prints_where_or_the_reason(self):
        here = os.getcwd()
        env = self.env(TOOLCHAIN_IMAGE="workbench")
        got = subprocess.run([sys.executable, "-m", "core.gates.toolchain", "preflight"], cwd=here, env=env,
                             capture_output=True, text=True)
        self.assertEqual((got.returncode, got.stdout), (0, "workbench\n"))
        env["TOOLCHAIN_IMAGE"] = "node:24"
        env.pop("DOCKER_HOST", None)
        got = subprocess.run([sys.executable, "-m", "core.gates.toolchain", "preflight"], cwd=here, env=env,
                             capture_output=True, text=True)
        self.assertEqual(got.returncode, 1)
        self.assertEqual(len(got.stdout.splitlines()), 1)
        self.assertTrue(got.stdout.startswith("in node:24: the engine socket is not available"), got.stdout)

    def test_run_returns_the_commands_exit_and_a_bad_form_says_toolchain(self):
        env = self.env(TOOLCHAIN_IMAGE="workbench")
        got = subprocess.run([sys.executable, "-m", "core.gates.toolchain", "run", "echo out; echo err >&2; exit 4"],
                             cwd=os.getcwd(), env=env, capture_output=True, text=True)
        self.assertEqual((got.returncode, got.stdout, got.stderr), (4, "out\n", "err\n"))
        env["TOOLCHAIN_IMAGE"] = "compose:"
        got = subprocess.run([sys.executable, "-m", "core.gates.toolchain", "run", "true"], cwd=os.getcwd(), env=env,
                             capture_output=True, text=True)
        self.assertEqual((got.returncode, got.stdout), (125, ""))
        self.assertEqual(got.stderr, "toolchain: TOOLCHAIN_IMAGE=compose: names no service\n")

    def test_cmd_gets_the_callers_pythonpath_back(self):
        root = os.getcwd()
        env = self.env(TOOLCHAIN_IMAGE="workbench")
        for given, want in ((root + ":/elsewhere", "[/elsewhere]"), (root, "[unset]"), ("/mine", "[/mine]")):
            env["PYTHONPATH"] = given
            got = subprocess.run([sys.executable, "-m", "core.gates.toolchain", "run", 'echo "[${PYTHONPATH-unset}]"'],
                                 cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(got.stdout, want + "\n", given)


if __name__ == "__main__":
    unittest.main()

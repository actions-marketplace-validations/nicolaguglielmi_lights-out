"""The python mutation runner's hook (docs/adr/0075), first on PYTHONPATH
only while mutation.sh runs the repository's suite. Inert unless the runner
set one of its two variables:

LIGHTS_OUT_COV_DIR (the clean run): coverage.py measures this process, its
data written there at exit, under the context of the test running in it.
In the process that runs the tests (no LIGHTS_OUT_COV_CONTEXT inherited)
the context is unittest.TestCase.id() around each TestCase.run, "-"
outside a test; a process the suite spawns inherits the running test's
context through the environment, and the hook puts itself back on the
PYTHONPATH of a subprocess.Popen whose env dropped it.

LIGHTS_OUT_SELECT (a mutant's run): a file of test ids; the process that
reads it first runs only those, by filtering
unittest.TestLoader.getTestCaseNames, and removes the variable so the
processes it spawns run their own tests unfiltered.
"""

import atexit
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONTEXT = "LIGHTS_OUT_COV_CONTEXT"
OUTSIDE = "-"
CARRIED = ("LIGHTS_OUT_COV_DIR", "LIGHTS_OUT_COV_SITE", CONTEXT)
WARNINGS = ["already-imported", "couldnt-parse", "dynamic-conflict", "include-ignored",
            "module-not-imported", "module-not-measured", "module-not-python",
            "no-ctracer", "no-data-collected", "no-sysmon", "trace-changed"]


def _coverage():
    site_dir = os.environ.get("LIGHTS_OUT_COV_SITE", "")
    sys.path.append(site_dir)
    try:
        import coverage
    except ImportError:
        return None
    finally:
        sys.path.remove(site_dir)
    return coverage


def _carry_into_children():
    import subprocess

    init = subprocess.Popen.__init__

    def popen(self, *args, **kwargs):
        env = kwargs.get("env")
        if env is not None:
            env = dict(env)
            for key in CARRIED:
                if key in os.environ:
                    env[key] = os.environ[key]
            path = env.get("PYTHONPATH", "")
            if HERE not in path.split(os.pathsep):
                env["PYTHONPATH"] = HERE + (os.pathsep + path if path else "")
            kwargs["env"] = env
        init(self, *args, **kwargs)

    subprocess.Popen.__init__ = popen


def _measure(data_dir):
    coverage = _coverage()
    if coverage is None:
        return
    top = CONTEXT not in os.environ
    cov = coverage.Coverage(data_file=os.path.join(data_dir, "cov"), data_suffix=True,
                            config_file=False)
    # Never a word on the suite's stderr: tests read their children's.
    cov.set_option("run:disable_warnings", WARNINGS)
    cov.start()
    cov.switch_context(os.environ.get(CONTEXT) or OUTSIDE)

    def save():
        cov.stop()
        cov.save()

    atexit.register(save)
    _carry_into_children()
    if not top:
        return
    os.environ[CONTEXT] = OUTSIDE
    import unittest

    run = unittest.TestCase.run

    def traced(self, result=None):
        if os.environ.get(CONTEXT) != OUTSIDE:
            return run(self, result)
        test = self.id()
        os.environ[CONTEXT] = test
        cov.switch_context(test)
        try:
            return run(self, result)
        finally:
            os.environ[CONTEXT] = OUTSIDE
            cov.switch_context(OUTSIDE)

    unittest.TestCase.run = traced


def _select(listing):
    with open(listing, encoding="utf-8") as f:
        chosen = set(f.read().split())
    import unittest

    names = unittest.TestLoader.getTestCaseNames

    def selected(self, case):
        prefix = f"{case.__module__}.{case.__qualname__}."
        return [n for n in names(self, case) if prefix + n in chosen]

    unittest.TestLoader.getTestCaseNames = selected


if os.environ.get("LIGHTS_OUT_COV_DIR"):
    _measure(os.environ["LIGHTS_OUT_COV_DIR"])
if os.environ.get("LIGHTS_OUT_SELECT"):
    _select(os.environ.pop("LIGHTS_OUT_SELECT"))

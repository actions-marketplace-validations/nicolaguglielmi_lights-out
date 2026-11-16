"""Tests for ci/checks/zero_to_hero.py, written from docs/adr/0097 §1, §2,
§3 and §5, never from the implementation.

A good tree is GO: the tutorial opens with "From zero to hero" and its seven
levels, each with Time, You need, You will see and Go deeper, and a last
fenced block that ends on its verdict right after a source comment; the
README links every level and has no "Five ways in"; the dev container pins
its image by digest and Docker-in-Docker to an exact version, sets
CONTAINER_ENGINE=docker and asks for 4 CPUs and the preflight's disk; the
stranger workflow runs ./go demo through devcontainers/ci pinned by commit;
every Codespaces link says, within 400 characters, that it needs a GitHub
account and uses Codespaces quota; the site's first hero action opens the
frozen console. Each case then breaks one thing and wants its NO-GO.
"""

import os
import shutil
import tempfile
import unittest

from ci.checks import zero_to_hero as z

FENCE = "```"


def level(n, title, last_line, source=True, drop=None):
    labels = ["**Time:** about a minute.", "**You need:** a browser.",
              "**You will see:** a canary rolled back.", "**Go deeper:** [the demo](#1-the-demo)."]
    lines = ["### Level %d: %s" % (n, title), ""]
    lines += [x for x in labels if not (drop and x.startswith(drop))]
    lines += ["", FENCE + "sh", "./go something", FENCE, ""]
    if source:
        lines.append("<!-- source: ci run 1, job 2 -->")
    lines += [FENCE, "some progress", last_line, FENCE, ""]
    return "\n".join(lines)


TITLES = ["See it", "Run the demo", "Your repository", "Your rules",
          "Your service", "Live agents", "Your CI/CD"]


def tutorial(levels=None, first="## From zero to hero"):
    if levels is None:
        levels = [level(n, t, "NO-GO: launchpad — 5%: rolled back" if n == 0 else "GO: thing — %d" % n)
                  for n, t in enumerate(TITLES)]
    return "# Tutorial\n\nIntro.\n\n%s\n\n%s\n## 1. The demo\n\nText.\n" % (first, "\n".join(levels))


def readme(levels=range(7), extra=""):
    rows = "\n".join("| [%d](docs/tutorial.md#level-%d-x) | x |" % (n, n) for n in levels)
    return ("# lights-out\n\n## Quick start\n\n" + CODESPACES_MD + "\n\n## From zero to hero\n\n| Level | |\n|---|---|\n"
            + rows + "\n" + extra)


CODESPACES_MD = ("[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)]"
                 "(https://codespaces.new/o/r?quickstart=1) It needs a GitHub account and uses your Codespaces quota.")

DEVCONTAINER = """// SPDX-License-Identifier: Apache-2.0
// a comment with a URL: https://example.invalid/x
{
  "image": "mcr.microsoft.com/devcontainers/base:3.0.13-noble@sha256:%s",
  "features": {
    // pinned
    "ghcr.io/devcontainers/features/docker-in-docker:4.1.3": {}
  },
  "containerEnv": { "CONTAINER_ENGINE": "docker" },
  "hostRequirements": { "cpus": 4, "memory": "8gb", "storage": "32gb" }
}
""" % ("a" * 64)

WORKFLOW = """name: stranger
jobs:
  demo:
    runs-on: ubuntu-latest
    steps:
      - run: ./go doctor
  codespace:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@%s # v7
      - name: ./go demo in the dev container
        uses: devcontainers/ci@%s # v0.3
        with:
          push: never
          runCmd: |
            s=$(date +%%s)
            ./go demo
      - if: always()
        run: echo done
""" % ("b" * 40, "c" * 40)

SITE = """<!doctype html><html><body>
<header class="hero" id="top">
  <div class="cta">
    <a class="btn primary" href="console/snapshot.html#ticket/0001">See it in 10 seconds</a>
    <a class="btn" href="#try">Run it</a>
    <a class="btn" href="#try-repo">Try it on your repo</a>
  </div>
  <button type="button" data-play="overview">Watch the tour</button>
</header>
<section id="try"><p><a href="https://codespaces.new/o/r?quickstart=1">Open in Codespaces</a>:
it needs a GitHub account and uses your Codespaces quota.</p></section>
</body></html>
"""


class Tutorial(unittest.TestCase):
    def test_good(self):
        self.assertEqual(z.tutorial(tutorial()), [])

    def test_the_path_must_be_the_first_section(self):
        text = "# Tutorial\n\n## 0. Before you start\n\nx\n\n" + tutorial().split("\n\n", 2)[2]
        self.assertTrue(any("first section" in p for p in z.tutorial(text)))

    def test_a_missing_level(self):
        levels = [level(n, t, "NO-GO: x — rolled back" if n == 0 else "GO: x") for n, t in enumerate(TITLES) if n != 4]
        self.assertTrue(any("level" in p.lower() and "4" in p for p in z.tutorial(tutorial(levels))))

    def test_levels_out_of_order(self):
        levels = [level(n, t, "NO-GO: x — rolled back" if n == 0 else "GO: x") for n, t in enumerate(TITLES)]
        levels[2], levels[3] = levels[3], levels[2]
        self.assertNotEqual(z.tutorial(tutorial(levels)), [])

    def test_a_level_without_time(self):
        levels = [level(n, t, "NO-GO: x — rolled back" if n == 0 else "GO: x", drop="**Time:**" if n == 2 else None)
                  for n, t in enumerate(TITLES)]
        problems = z.tutorial(tutorial(levels))
        self.assertTrue(any("2" in p and "Time" in p for p in problems), problems)

    def test_each_label_is_required(self):
        for label in ("**You need:**", "**You will see:**", "**Go deeper:**"):
            levels = [level(n, t, "NO-GO: x — rolled back" if n == 0 else "GO: x", drop=label if n == 5 else None)
                      for n, t in enumerate(TITLES)]
            self.assertTrue(any("5" in p and label.strip("*: ") in p for p in z.tutorial(tutorial(levels))), label)

    def test_a_level_after_zero_must_end_on_go(self):
        levels = [level(n, t, "NO-GO: x — rolled back" if n in (0, 3) else "GO: x") for n, t in enumerate(TITLES)]
        problems = z.tutorial(tutorial(levels))
        self.assertTrue(any("3" in p and "GO" in p for p in problems), problems)

    def test_level_zero_may_end_on_go_too(self):
        levels = [level(n, t, "GO: x") for n, t in enumerate(TITLES)]
        self.assertEqual(z.tutorial(tutorial(levels)), [])

    def test_the_last_block_must_end_on_a_verdict(self):
        levels = [level(n, t, "progress only" if n == 1 else ("NO-GO: x" if n == 0 else "GO: x"))
                  for n, t in enumerate(TITLES)]
        self.assertTrue(any("1" in p for p in z.tutorial(tutorial(levels))))

    def test_a_level_without_a_source(self):
        levels = [level(n, t, "NO-GO: x" if n == 0 else "GO: x", source=n != 6) for n, t in enumerate(TITLES)]
        problems = z.tutorial(tutorial(levels))
        self.assertTrue(any("6" in p and "source" in p for p in problems), problems)


class Readme(unittest.TestCase):
    def test_good(self):
        self.assertEqual(z.readme(readme()), [])

    def test_a_level_not_linked(self):
        problems = z.readme(readme(levels=[0, 1, 2, 3, 5, 6]))
        self.assertTrue(any("4" in p for p in problems), problems)

    def test_five_ways_in_is_gone(self):
        self.assertTrue(any("Five ways in" in p for p in z.readme(readme(extra="\n## Five ways in\n\nx\n"))))


class Devcontainer(unittest.TestCase):
    def test_good(self):
        self.assertEqual(z.devcontainer(DEVCONTAINER, 8000), [])

    def test_image_by_tag(self):
        text = DEVCONTAINER.replace("@sha256:" + "a" * 64, "")
        self.assertTrue(any("digest" in p for p in z.devcontainer(text, 8000)))

    def test_feature_by_major(self):
        text = DEVCONTAINER.replace("docker-in-docker:4.1.3", "docker-in-docker:4")
        self.assertTrue(any("docker-in-docker" in p for p in z.devcontainer(text, 8000)))

    def test_no_feature(self):
        text = DEVCONTAINER.replace("docker-in-docker:4.1.3", "node:1.6.3")
        self.assertTrue(any("docker-in-docker" in p for p in z.devcontainer(text, 8000)))

    def test_no_engine(self):
        text = DEVCONTAINER.replace('"CONTAINER_ENGINE": "docker"', '"OTHER": "docker"')
        self.assertTrue(any("CONTAINER_ENGINE" in p for p in z.devcontainer(text, 8000)))

    def test_two_cpus(self):
        text = DEVCONTAINER.replace('"cpus": 4', '"cpus": 2')
        self.assertTrue(any("cpus" in p for p in z.devcontainer(text, 8000)))

    def test_storage_under_the_preflight_need(self):
        text = DEVCONTAINER.replace('"32gb"', '"6gb"')
        self.assertTrue(any("storage" in p for p in z.devcontainer(text, 8000)))
        text = DEVCONTAINER.replace('"32gb"', '"8000mb"')
        self.assertEqual(z.devcontainer(text, 8000), [])

    def test_not_json(self):
        self.assertNotEqual(z.devcontainer("{ nope", 8000), [])


class Workflow(unittest.TestCase):
    def test_good(self):
        self.assertEqual(z.workflow(WORKFLOW), [])

    def test_pinned_by_tag(self):
        self.assertNotEqual(z.workflow(WORKFLOW.replace("devcontainers/ci@" + "c" * 40, "devcontainers/ci@v0.3")), [])

    def test_no_demo_in_its_step(self):
        text = WORKFLOW.replace("            ./go demo\n", "            ./go doctor\n").replace(
            "        run: echo done", "        run: ./go demo")
        self.assertNotEqual(z.workflow(text), [])

    def test_no_job(self):
        self.assertNotEqual(z.workflow("name: stranger\njobs:\n  demo:\n    steps:\n      - run: ./go demo\n"), [])


class Quota(unittest.TestCase):
    def test_good(self):
        self.assertEqual(z.quota_words("README.md", CODESPACES_MD), [])
        self.assertEqual(z.quota_words("site/index.html", SITE), [])

    def test_no_link_no_rule(self):
        self.assertEqual(z.quota_words("README.md", "nothing about it"), [])

    def test_no_word_of_the_quota(self):
        text = CODESPACES_MD.replace(" and uses your Codespaces quota", "")
        self.assertTrue(any("quota" in p for p in z.quota_words("README.md", text)))

    def test_no_word_of_the_account(self):
        text = CODESPACES_MD.replace("It needs a GitHub account and uses", "It uses")
        self.assertTrue(any("account" in p for p in z.quota_words("README.md", text)))

    def test_too_far_away(self):
        text = CODESPACES_MD.split(" It needs")[0] + "\n\n" + "x " * 300 + "\n\nIt needs a GitHub account and uses your Codespaces quota."
        self.assertNotEqual(z.quota_words("README.md", text), [])


class Site(unittest.TestCase):
    def test_good(self):
        self.assertEqual(z.site_hero(SITE), [])

    def test_the_tour_first(self):
        text = SITE.replace('  <div class="cta">\n', '  <div class="cta">\n    <button type="button" data-play="overview">Watch the tour</button>\n')
        self.assertTrue(any("frozen console" in p for p in z.site_hero(text)))

    def test_no_hero(self):
        self.assertNotEqual(z.site_hero("<html><body><a href='console/snapshot.html'>x</a></body></html>"), [])


class Judge(unittest.TestCase):
    """The whole check over a planted tree: GO, then one NO-GO naming the file."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        files = {
            "docs/tutorial.md": tutorial(),
            "README.md": readme(),
            ".devcontainer/devcontainer.json": DEVCONTAINER,
            ".github/workflows/stranger.yml": WORKFLOW,
            "site/index.html": SITE,
            "core/preflight.sh": "need_mb=${PREFLIGHT_DISK_NEED_MB:-8000}\n",
        }
        for path, text in files.items():
            full = os.path.join(self.root, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(text)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_go(self):
        line, ok = z.judge(self.root)
        self.assertTrue(ok, line)

    def test_nogo_names_the_file(self):
        os.remove(os.path.join(self.root, ".devcontainer/devcontainer.json"))
        line, ok = z.judge(self.root)
        self.assertFalse(ok)
        self.assertIn(".devcontainer/devcontainer.json", line)

    def test_the_disk_need_is_the_preflights(self):
        with open(os.path.join(self.root, "core/preflight.sh"), "w", encoding="utf-8") as f:
            f.write("need_mb=${PREFLIGHT_DISK_NEED_MB:-40000}\n")
        line, ok = z.judge(self.root)
        self.assertFalse(ok)
        self.assertIn("storage", line)


if __name__ == "__main__":
    unittest.main()

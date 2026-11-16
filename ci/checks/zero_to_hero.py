# SPDX-License-Identifier: Apache-2.0
"""ci-zero-to-hero: the path from zero to hero and the second door, as
docs/adr/0097 §5 says. NO-GO, naming the file and what is missing, when:

a. docs/tutorial.md's first section is not "From zero to hero" with seven
   levels, `### Level 0` to `### Level 6` in order, each with its **Time:**,
   **You need:**, **You will see:** and **Go deeper:** lines, and a last
   fenced block that ends on a verdict line right after a `<!-- source: … -->`
   comment; level 0 may end on `NO-GO:` or `GO:`, every other on `GO:`;
b. README.md does not link each level (`tutorial.md#level-<n>…`), or still
   has the "Five ways in" section;
c. .devcontainer/devcontainer.json (full-line `//` comments stripped) does
   not pin its image by digest, pins docker-in-docker to anything but an
   exact x.y.z, does not set CONTAINER_ENGINE=docker, or asks for fewer than
   4 CPUs or less storage than core/preflight.sh's disk need;
d. .github/workflows/stranger.yml has no step that uses devcontainers/ci
   pinned by a full commit and runs ./go demo;
e. README.md or site/index.html links codespaces.new/… without the words
   "GitHub account" and "quota" within 400 characters of the link;
f. the first action in site/index.html's hero is not a link to the frozen
   console (console/snapshot.html).

Run by ci/zero-to-hero.sh through `verdict` (docs/adr/0094).
"""

import json
import os
import re
import sys

LEVELS = 7
LABELS = ("Time", "You need", "You will see", "Go deeper")
WINDOW = 400
MIN_CPUS = 4


def _sections(text, prefix):
    """(heading, body) for each heading line starting with prefix."""
    out, cur, body = [], None, []
    for line in text.splitlines():
        if line.startswith(prefix):
            if cur is not None:
                out.append((cur, body))
            cur, body = line, []
        elif cur is not None:
            body.append(line)
    if cur is not None:
        out.append((cur, body))
    return out


def _last_block(body):
    """(lines of the last fenced block, the non-blank line before it), or None."""
    fences = [i for i, line in enumerate(body) if line.startswith("```")]
    if len(fences) < 2:
        return None
    start, end = fences[-2], fences[-1]
    before = next((body[i] for i in range(start - 1, -1, -1) if body[i].strip()), "")
    return body[start + 1:end], before


def tutorial(text):
    problems = []
    chapters = [h for h in text.splitlines() if h.startswith("## ")]
    if not chapters or chapters[0].strip() != "## From zero to hero":
        return ["docs/tutorial.md: its first section is not '## From zero to hero'"]
    path = text.split("## From zero to hero", 1)[1]
    path = re.split(r"(?m)^## ", path, maxsplit=1)[0]
    levels = _sections(path, "### ")
    numbers = []
    for heading, _ in levels:
        m = re.match(r"### Level (\d+): \S", heading)
        if not m:
            problems.append("docs/tutorial.md: '%s' is not '### Level <n>: <title>'" % heading)
            continue
        numbers.append(int(m.group(1)))
    if numbers != list(range(LEVELS)):
        problems.append("docs/tutorial.md: levels %s, want 0 to %d in order (missing: %s)" % (
            numbers, LEVELS - 1, sorted(set(range(LEVELS)) - set(numbers)) or "none"))
    for heading, body in levels:
        m = re.match(r"### Level (\d+)", heading)
        if not m:
            continue
        n = int(m.group(1))
        for label in LABELS:
            if not any(line.startswith("**%s:**" % label) for line in body):
                problems.append("docs/tutorial.md: level %d has no '**%s:**' line" % (n, label))
        block = _last_block(body)
        if block is None:
            problems.append("docs/tutorial.md: level %d has no fenced block ending on its verdict" % n)
            continue
        lines, before = block
        last = next((x for x in reversed(lines) if x.strip()), "")
        allowed = ("GO: ", "NO-GO: ") if n == 0 else ("GO: ",)
        if not last.startswith(allowed):
            problems.append("docs/tutorial.md: level %d's last block ends on '%s', not on %s" % (
                n, last[:60], " or ".join(a.strip() for a in allowed)))
        if not before.strip().startswith("<!-- source:"):
            problems.append("docs/tutorial.md: level %d's last block has no '<!-- source: … -->' right before it" % n)
    return problems


def readme(text):
    problems = []
    for n in range(LEVELS):
        if not re.search(r"tutorial\.md#level-%d-" % n, text):
            problems.append("README.md: no link to level %d (docs/tutorial.md#level-%d-…)" % (n, n))
    if re.search(r"(?m)^#+ Five ways in", text):
        problems.append("README.md: still has 'Five ways in'; the levels replace it")
    return problems


def _mb(size):
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(tb|gb|mb|kb)\s*", str(size).lower())
    if not m:
        return None
    return float(m.group(1)) * {"tb": 1000 * 1000, "gb": 1000, "mb": 1, "kb": 0.001}[m.group(2)]


def devcontainer(text, need_mb):
    where = ".devcontainer/devcontainer.json"
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))
    try:
        dc = json.loads(body)
    except ValueError as e:
        return ["%s: not JSON once its // comments are stripped: %s" % (where, e)]
    problems = []
    if not re.search(r"@sha256:[0-9a-f]{64}$", str(dc.get("image", ""))):
        problems.append("%s: the image is not pinned by digest" % where)
    dind = [k for k in (dc.get("features") or {}) if k.startswith("ghcr.io/devcontainers/features/docker-in-docker:")]
    if not dind:
        problems.append("%s: no docker-in-docker feature" % where)
    elif not re.search(r":\d+\.\d+\.\d+$", dind[0]):
        problems.append("%s: docker-in-docker is not pinned to an exact version: %s" % (where, dind[0]))
    if (dc.get("containerEnv") or {}).get("CONTAINER_ENGINE") != "docker":
        problems.append("%s: containerEnv does not set CONTAINER_ENGINE=docker" % where)
    host = dc.get("hostRequirements") or {}
    try:
        cpus = int(host.get("cpus", 0))
    except (TypeError, ValueError):
        cpus = 0
    if cpus < MIN_CPUS:
        problems.append("%s: hostRequirements.cpus is %s, want at least %d" % (where, host.get("cpus"), MIN_CPUS))
    storage = _mb(host.get("storage", ""))
    if storage is None or storage < need_mb:
        problems.append("%s: hostRequirements.storage is %s, under the preflight's %d MB" % (
            where, host.get("storage"), need_mb))
    return problems


def workflow(text):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not re.search(r"\buses:\s*devcontainers/ci@", line):
            continue
        if not re.search(r"\buses:\s*devcontainers/ci@[0-9a-f]{40}\b", line):
            continue
        # The step: back to its dash, on to the next line at the dash's indent or less.
        j = i
        while j > 0 and not lines[j].lstrip().startswith("- "):
            j -= 1
        indent = len(lines[j]) - len(lines[j].lstrip())
        step = [lines[j]]
        for nxt in lines[j + 1:]:
            if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= indent:
                break
            step.append(nxt)
        commands = [x for x in step if not re.match(r"\s*(- )?name:", x)]
        if any(re.search(r"(^|\s)\./go demo(\s|$)", x) for x in commands):
            return []
    return [".github/workflows/stranger.yml: no step uses devcontainers/ci pinned by commit to run ./go demo"]


def quota_words(where, text):
    problems = []
    for m in re.finditer(r"codespaces\.new/", text):
        around = text[max(0, m.start() - WINDOW):m.end() + WINDOW]
        flat = re.sub(r"\s+", " ", around).lower()
        for words in ("github account", "quota"):
            if words not in flat:
                problems.append("%s: a Codespaces link with no '%s' within %d characters" % (where, words, WINDOW))
    return problems


def site_hero(text):
    m = re.search(r'<header class="hero".*?</header>', text, re.S)
    if not m:
        return ["site/index.html: no hero (<header class=\"hero\">)"]
    first = re.search(r"<(a|button)\b[^>]*>", m.group(0))
    if not first or first.group(1) != "a" or "console/snapshot.html" not in first.group(0):
        return ["site/index.html: the hero's first action is not the frozen console (console/snapshot.html)"]
    return []


def _read(root, path):
    try:
        with open(os.path.join(root, path), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def judge(root):
    problems = []
    texts = {}
    for path in ("docs/tutorial.md", "README.md", ".devcontainer/devcontainer.json",
                 ".github/workflows/stranger.yml", "site/index.html", "core/preflight.sh"):
        texts[path] = _read(root, path)
        if texts[path] is None:
            problems.append("%s: not found" % path)
    need = re.search(r"need_mb=\$\{PREFLIGHT_DISK_NEED_MB:-(\d+)\}", texts["core/preflight.sh"] or "")
    if texts["core/preflight.sh"] is not None and not need:
        problems.append("core/preflight.sh: no need_mb default to compare the dev container's storage with")
    if texts["docs/tutorial.md"] is not None:
        problems += tutorial(texts["docs/tutorial.md"])
    if texts["README.md"] is not None:
        problems += readme(texts["README.md"]) + quota_words("README.md", texts["README.md"])
    if texts[".devcontainer/devcontainer.json"] is not None and need:
        problems += devcontainer(texts[".devcontainer/devcontainer.json"], int(need.group(1)))
    if texts[".github/workflows/stranger.yml"] is not None:
        problems += workflow(texts[".github/workflows/stranger.yml"])
    if texts["site/index.html"] is not None:
        problems += site_hero(texts["site/index.html"]) + quota_words("site/index.html", texts["site/index.html"])
    if problems:
        return "\n".join(problems), False
    return "seven levels, the dev container and its proof, the frozen console first", True


def main():
    line, ok = judge(os.getcwd())
    print(line)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

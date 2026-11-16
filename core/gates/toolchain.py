# SPDX-License-Identifier: Apache-2.0
"""core-toolchain (docs/adr/0042 §2, §4): where a workload's declared command
runs. core/toolchain.sh keeps the two functions its callers source and calls
this module (docs/adr/0084, amendment A3):

    python3 -P -m core.gates.toolchain preflight   # where, or the NO-GO reason; exit 0 or 1
    python3 -P -m core.gates.toolchain run CMD     # CMD's exit code, or 125

`preflight` checks the form of TOOLCHAIN_IMAGE (the workload's contract), the
socket an engine form needs and the plane half a compose form needs, and
prints where the command will run: the text a gate puts on its GO line
(docs/adr/0042 §3), also written to $GATES_OUT/toolchain.where for `make
gates`' own line. `run` runs CMD, one `sh -c` line, with MUTATION_LINES
carried into CMD's environment and nothing else of the gate's. CMD's stdout
is the caller's stdout (a gate captures it: the runner's one JSON line), its
stderr passes through, and the exit is CMD's -- or 125, with one
"toolchain:" line on stderr, when the form is malformed or an image build
failed. It never prints a contract line: a caller captures or redirects its
stdout, where a contract line would be lost.

Three forms of TOOLCHAIN_IMAGE:
  workbench            in this container, in-process, no engine: from
                       $WORKLOAD/$WORKLOAD_TEST_ROOT, with uv and npm caches
                       under .crew/cache/ of the caller's directory and the
                       repository's venv outside its tree.
                       UV_PYTHON_DOWNLOADS=never: a Python the workbench lacks
                       fails loudly instead of being downloaded. Under
                       TOOLCHAIN_ISOLATE=1 (core/steps/ci.sh: the tower never
                       runs a PR's tests in its own container) it is the image
                       form below on the workbench image.
  compose:<service>    a profile-test service of the contract's compose
                       fragment, built and run under its own project name, in
                       the image's own working directory, torn down after.
  <image reference>    a throwaway image built through compose from an inline
                       Containerfile -- FROM <ref>, COPY . /work -- so nothing
                       of the host is bind-mounted (the compose client sends
                       the context over the socket) and CMD cannot write into
                       the clone. Named volumes keep the uv and npm caches.
The two engine forms need the socket ./go mounts; for gates, init and
mutation-baseline it is optional (docs/adr/0042 §4), so its absence is a
NO-GO naming it, never a silent in-process run. Each image build is apart
from its run: `run --build` would put the build's log on stdout, where the
caller reads the runner's line.
"""

import os
import re
import shutil
import stat
import sys
import tempfile
import zlib

from core.gates import DEVNULL, NoGo, proc

PROJECT = "lo-toolchain"
IMAGE_REF = r"[a-z0-9]([a-z0-9._/-]*[a-z0-9])?(:[A-Za-z0-9._-]+)?(@sha256:[0-9a-f]{64})?"


def form(image):
    """workbench, compose or image, from TOOLCHAIN_IMAGE; NoGo naming the value otherwise."""
    if not image:
        raise NoGo("TOOLCHAIN_IMAGE is empty (docs/adr/0042 §2)")
    if image == "workbench":
        return "workbench"
    if image == "compose:":
        raise NoGo("TOOLCHAIN_IMAGE=compose: names no service")
    if image.startswith("compose:"):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", image[len("compose:"):]):
            raise NoGo("TOOLCHAIN_IMAGE=%s is not compose:<service>" % image)
        return "compose"
    if re.fullmatch(IMAGE_REF, image):
        return "image"
    raise NoGo("TOOLCHAIN_IMAGE=%s is none of workbench, compose:<service> or an image reference" % image)


def socket_path(env):
    """The engine socket ./go mounted (DOCKER_HOST, unix:// or a path), or ''."""
    sock = env.get("DOCKER_HOST") or ""
    if sock.startswith("unix://"):
        sock = sock[len("unix://"):]
    try:
        return sock if sock and stat.S_ISSOCK(os.stat(sock).st_mode) else ""
    except OSError:
        return ""


def need(env, key):
    if not env.get(key):
        raise NoGo("%s not set; run this via ./go, not directly" % key)
    return env[key]


def preflight(env):
    """Where the command will run, written to $GATES_OUT/toolchain.where; NoGo
    on a contract error."""
    need(env, "WORKLOAD")
    image = env.get("TOOLCHAIN_IMAGE", "")
    kind = form(image)
    where = image
    if kind == "workbench":
        where = "workbench (isolated)" if env.get("TOOLCHAIN_ISOLATE") == "1" else "workbench"
        if where != "workbench":
            need(env, "WORKBENCH_IMAGE")
    out = env.get("GATES_OUT")
    if out and os.path.isdir(out):
        with open(os.path.join(out, "toolchain.where"), "w", encoding="utf-8") as fh:
            fh.write(where + "\n")
    if where == "workbench":
        return where
    if not socket_path(env):
        raise NoGo("in %s: the engine socket is not available and %s" % (where, {
            "workbench": "TOOLCHAIN_ISOLATE=1 needs the engine",
            "compose": "the compose form needs the engine; run with podman or docker up, or set TOOLCHAIN_IMAGE=workbench",
            "image": "an image needs the engine; run with podman or docker up, or set TOOLCHAIN_IMAGE=workbench",
        }[kind]))
    if kind == "compose" and not os.path.isfile(os.path.join(need(env, "WORKLOAD_CONTRACT"), "compose.yaml")):
        raise NoGo("in %s: %s has no compose.yaml; the compose form needs the plane half of the contract "
                   "(docs/adr/0042 §7)" % (image, env["WORKLOAD_CONTRACT"]))
    return where


def venv_dir(cache, workload):
    """The workload's venv under the cache, one per workload, outside its tree."""
    return "%s/venv/%d" % (cache, zlib.crc32(os.path.realpath(workload).encode()))


def image_files(ref, context, containerfile, test_root, mutation_lines):
    """(Containerfile, compose.yaml) of the throwaway image: build context the
    workload's root, nothing of the host mounted, the caches named volumes."""
    cf = "FROM %s\nCOPY . /work\nWORKDIR /work\n" % ref
    compose = """services:
  toolchain:
    build:
      context: %s
      dockerfile: %s
    working_dir: /work/%s
    environment:
      MUTATION_LINES: %s
      UV_LINK_MODE: copy
      NO_COLOR: "1"
    volumes:
      - lo-toolchain-uv:/root/.cache/uv
      - lo-toolchain-npm:/root/.npm
volumes:
  lo-toolchain-uv: {}
  lo-toolchain-npm: {}
""" % (context, containerfile, test_root, mutation_lines)
    return cf, compose


def compose(env, *args, **kw):
    return proc(["docker-compose", *args], env=env, **kw).returncode


def say(line):
    print("toolchain: " + line, file=sys.stderr, flush=True)


def image_run(ref, cmd, env, stdout):
    tc = tempfile.mkdtemp()
    try:
        cf, yaml = image_files(ref, os.path.realpath(env["WORKLOAD"]), tc + "/Containerfile",
                               env.get("WORKLOAD_TEST_ROOT", ""), env.get("MUTATION_LINES", ""))
        for name, text in (("Containerfile", cf), ("compose.yaml", yaml)):
            with open(os.path.join(tc, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        files = ("-p", PROJECT, "-f", tc + "/compose.yaml")
        if compose(env, *files, "build", "toolchain", stdin=DEVNULL, stdout=2) != 0:
            say("the image build on %s failed" % ref)
            return 125
        rc = compose(env, *files, "run", "--rm", "-T", "toolchain", "sh", "-c", cmd, stdin=DEVNULL, stdout=stdout)
        compose(env, *files, "down", "--remove-orphans", stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL)
        return rc
    finally:
        shutil.rmtree(tc, ignore_errors=True)


def run(cmd, env, stdout=None):
    """CMD where TOOLCHAIN_IMAGE says: its exit code, or 125 when the toolchain failed."""
    try:
        kind = form(env.get("TOOLCHAIN_IMAGE", ""))
    except NoGo as no:
        say(no.reason)
        return 125
    if kind == "workbench" and env.get("TOOLCHAIN_ISOLATE") == "1":
        return image_run(env.get("WORKBENCH_IMAGE", ""), cmd, env, stdout)
    if kind == "image":
        return image_run(env["TOOLCHAIN_IMAGE"], cmd, env, stdout)
    if kind == "compose":
        svc = env["TOOLCHAIN_IMAGE"][len("compose:"):]
        test = ("-p", PROJECT, "--profile", "test")
        if compose(env, *test, "build", svc, stdin=DEVNULL, stdout=2) != 0:
            say("the %s image build failed" % svc)
            return 125
        rc = compose(env, *test, "run", "--rm", "-T", "-e", "MUTATION_LINES=" + env.get("MUTATION_LINES", ""), svc,
                     "sh", "-c", cmd, stdin=DEVNULL, stdout=stdout)
        compose(env, *test, "down", "-v", "--remove-orphans", stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL)
        return rc
    cache = os.path.join(os.getcwd(), ".crew/cache")
    for d in ("uv", "npm", "venv"):
        os.makedirs(os.path.join(cache, d), exist_ok=True)
    where = os.path.join(env["WORKLOAD"], env.get("WORKLOAD_TEST_ROOT", ""))
    if not os.path.isdir(where):
        say("%s is not a directory: the workload's test root (WORKLOAD_TEST_ROOT)" % where)
        return 125
    run_env = dict(env, MUTATION_LINES=env.get("MUTATION_LINES", ""), UV_PYTHON_DOWNLOADS="never", UV_LINK_MODE="copy",
                   UV_CACHE_DIR=cache + "/uv", UV_PROJECT_ENVIRONMENT=venv_dir(cache, env["WORKLOAD"]),
                   npm_config_cache=cache + "/npm", NO_COLOR="1")
    return proc(["sh", "-c", cmd], cwd=where, env=run_env, stdout=stdout).returncode


def main(argv):
    env = dict(os.environ)
    # core/toolchain.sh put this checkout on PYTHONPATH to import this module;
    # CMD gets the caller's PYTHONPATH back, never lights-out's core/. The one
    # entry it added is dropped wherever it sits: something that wraps every
    # Python process (a coverage hook, docs/adr/0076) may have put itself first.
    root = os.path.realpath(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    parts = env.get("PYTHONPATH", "").split(":")
    at = next((i for i, p in enumerate(parts) if p and os.path.realpath(p) == root), None)
    if at is not None:
        del parts[at]
        if any(parts):
            env["PYTHONPATH"] = ":".join(parts)
        else:
            del env["PYTHONPATH"]
    if argv[:1] == ["preflight"]:
        try:
            print(preflight(env))
            return 0
        except NoGo as no:
            print(no.reason)
            return 1
    if len(argv) == 2 and argv[0] == "run":
        return run(argv[1], env)
    say("usage: python3 -m core.gates.toolchain preflight | run CMD")
    return 125


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

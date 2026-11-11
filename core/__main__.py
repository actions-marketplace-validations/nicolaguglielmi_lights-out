# SPDX-License-Identifier: Apache-2.0
"""The `lights-out-gates` command of the Python package (docs/adr/0061 and
its amendment of 2026-11-09: PyPI refused the name `lights-out`).

    lights-out-gates --light [KEY=VALUE ...]   the gates that need only git and Python, one line
    lights-out-gates spec <file>               the spec gate on a draft, one line
    lights-out-gates map [--repo DIR] [--out FILE]
                                               the project map at HEAD, one line (docs/adr/0054)
    lights-out-gates mcp [--repo DIR] [--map FILE]
                                               the read-only MCP server over stdio (docs/adr/0069)
    lights-out-gates version                   the package's version
    lights-out-gates help

From a clone, `python3 -m core gates --light`. The eight gates of the full
judgement run from the image (the `lights-out` wrapper) or a clone (`./go
gates`): this package never prints `GO: gates`. Every outcome of `gates` is
one stdout line, exit 0 for GO and 1 for NO-GO, details on stderr.
"""

import os
import sys
import traceback

try:
    from . import light
except ImportError:  # run as a script: core/ is sys.path[0]
    import light

TOOLS = ("spec", "map", "mcp")


def version():
    if __package__ != "lights_out":
        return "from a clone"
    try:
        from importlib.metadata import version as installed
        return installed("lights-out-gates")
    except Exception:  # noqa: BLE001 - metadata missing is not an error of the command
        return "unknown"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    os.environ["NO_COLOR"] = "1"
    cmd = argv[0] if argv else "help"
    if cmd in ("help", "-h", "--help"):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 0
    if cmd == "version":
        print(f"lights-out-gates {version()} (the light tier: --light)")
        return 0
    if cmd in TOOLS:
        return toolbelt(cmd, argv[1:])
    if cmd != "gates":
        print(f"NO-GO: lights-out — unknown command '{cmd}'; one of: gates --light, spec, map, mcp, version")
        return 1
    rest = argv[1:]
    if "--light" not in rest:
        print("NO-GO: gates — this package runs the light tier only: lights-out-gates --light; "
              "the eight gates run from the image (the lights-out wrapper) or a clone (./go gates)")
        return 1
    try:
        line, code, _ = light.judge([a for a in rest if a != "--light"])
    except Exception as exc:  # noqa: BLE001 - one line on stdout whatever happened
        traceback.print_exc(file=sys.stderr)
        line, code = f"NO-GO: {light.NAME} — {type(exc).__name__}: {exc}", 1
    print(line)
    return code


def toolbelt(cmd, rest):
    """spec, map and mcp (docs/adr/0069 §5): one stdout line each, but mcp, whose stdout is the protocol."""
    if cmd == "mcp":
        try:
            from . import mcp
        except ImportError:
            import mcp
        return mcp.main(rest)
    try:
        from . import map as project_map, spec
    except ImportError:
        import map as project_map
        import spec
    if cmd == "spec":
        if len(rest) != 1:
            print("NO-GO: spec — usage: lights-out-gates spec <file>")
            return 1
        try:
            with open(rest[0], encoding="utf-8") as handle:
                why = spec.check(handle.read())
        except (OSError, UnicodeDecodeError) as exc:
            print(f"NO-GO: spec — cannot read {rest[0]}: " + " ".join(str(exc).split()))
            return 1
        print(f"NO-GO: spec — {why}" if why else "GO: spec")
        return 1 if why else 0
    repo, out = ".", None
    args = list(rest)
    while args:
        flag = args.pop(0)
        if flag in ("--repo", "--out") and args:
            value = args.pop(0)
            repo, out = (value, out) if flag == "--repo" else (repo, value)
        else:
            print(f"NO-GO: map — unknown argument {flag}; usage: lights-out-gates map [--repo DIR] [--out FILE]")
            return 1
    try:
        # Inside .git, one per worktree, never committed by `git add -A` (docs/adr/0069 §6).
        out = out or os.path.join(repo, project_map.git(repo, "rev-parse", "--git-path", "lights-out/map.sqlite")
                                  .decode().strip())
        attached = project_map.git(repo, "ls-tree", "HEAD", ".lights-out/tickets").strip()
        sha, counts = project_map.build(repo, "HEAD", out, ".lights-out/tickets" if attached else "tickets")
    except (project_map.Refused, OSError) as exc:
        print("NO-GO: map — " + " ".join(str(exc).split()))
        return 1
    print(f"GO: map — {sha} " + " ".join(f"{k}={v}" for k, v in counts.items()) + f" → {out}")
    return 0


def gates_main(argv=None):
    """The console script `lights-out-gates`: `gates` implied, so
    `lights-out-gates --light` is `gates --light` (the amendment's §2)."""
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("help", "-h", "--help", "version", *TOOLS):
        return main(argv)
    return main(["gates", *argv])


if __name__ == "__main__":
    sys.exit(main())

# SPDX-License-Identifier: Apache-2.0
"""The `lights-out-gates` command of the Python package (docs/adr/0061 and
its amendment of 2026-11-09: PyPI refused the name `lights-out`).

    lights-out-gates --light [KEY=VALUE ...]   the gates that need only git and Python, one line
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
    if cmd != "gates":
        print(f"NO-GO: lights-out — unknown command '{cmd}'; one of: gates --light, version")
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


def gates_main(argv=None):
    """The console script `lights-out-gates`: `gates` implied, so
    `lights-out-gates --light` is `gates --light` (the amendment's §2)."""
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("help", "-h", "--help", "version"):
        return main(argv)
    return main(["gates", *argv])


if __name__ == "__main__":
    sys.exit(main())

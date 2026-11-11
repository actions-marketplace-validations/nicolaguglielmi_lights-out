#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# The Codex plugin's hook skill (docs/adr/0069, amendment 2026-11-11 §3):
#   sh hook.sh install|remove
# Writes into, or removes from, <repo>/.codex/hooks.json the verified
# recipe's PreToolUse entry (docs/use-on-your-repo.md: matcher *, timeout
# 30, lights-out-gates from PATH). Other hooks are untouched; a second
# install changes nothing; remove drops only that entry and the keys or the
# file it emptied. One stdout line: GO: hook — … (exit 0), or NO-GO: hook —
# … (exit 1) with nothing written.
set -u
case ${1:-} in
  install|remove) ;;
  *) echo "NO-GO: hook — usage: sh hook.sh install|remove"; exit 1 ;;
esac
top=$(git rev-parse --show-toplevel 2>/dev/null) || { echo "NO-GO: hook — not inside a git repository"; exit 1; }
exec python3 - "$1" "$top/.codex/hooks.json" <<'PY'
import json, os, sys

action, path = sys.argv[1], sys.argv[2]
COMMAND = "sh -c 'if grep -q \"git commit\"; then lights-out-gates --light STAGED=1 >&2 || exit 2; fi'"
ENTRY = {"matcher": "*", "hooks": [{"type": "command", "command": COMMAND, "timeout": 30}]}


def say(line, code):
    print(line)
    sys.exit(code)


doc = {}
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as handle:
            doc = json.load(handle)
    except (OSError, ValueError) as exc:
        say(f"NO-GO: hook — {path} is not readable JSON ({' '.join(str(exc).split())}); nothing written", 1)
    if not isinstance(doc, dict) or not isinstance(doc.get("hooks", {}), dict) \
            or not isinstance(doc.get("hooks", {}).get("PreToolUse", []), list):
        say(f"NO-GO: hook — {path} is not a hooks file this skill can merge into; nothing written", 1)
groups = doc.get("hooks", {}).get("PreToolUse", [])
ours = [g for g in groups if g == ENTRY]
if action == "install":
    if ours:
        say(f"GO: hook — already in {path}; trust it with /hooks if Codex has not run it", 0)
    doc.setdefault("hooks", {}).setdefault("PreToolUse", []).append(ENTRY)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=2)
        handle.write("\n")
    say(f"GO: hook — installed in {path}: review and trust it with /hooks before Codex runs it", 0)
if not ours:
    say(f"GO: hook — not in {path}; nothing to remove", 0)
rest = [g for g in groups if g != ENTRY]
if rest:
    doc["hooks"]["PreToolUse"] = rest
else:
    del doc["hooks"]["PreToolUse"]
    if not doc["hooks"]:
        del doc["hooks"]
if doc:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, indent=2)
        handle.write("\n")
else:
    os.remove(path)
    try:
        os.rmdir(os.path.dirname(path))
    except OSError:
        pass
say(f"GO: hook — removed from {path}", 0)
PY

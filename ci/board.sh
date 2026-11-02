#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-board: the board tells the truth about the tower and about the plane
# (docs/adr/0035), cold: no plane, no socket. Written from ADR 0035 §2-§4,
# not from board/.
#   a. The transition table board/index.html embeds (the explainer's
#      scenarios are validated against it) equals core/tower.sh's
#      precondition() and next() tables.
#   b. With nothing to read, every probe in /state.json answers ok:false
#      with a non-empty error and no value: no default ever stands in for
#      the plane.
#   c. board/serve.py calls no adapter verb but get, evaluate and status.
#   d. GET / serves the page, GET /state.json serves JSON.
#   e. With BOARD_STATIC=1 (§6) GET / serves the page and GET /state.json
#      answers 404, so a hosted copy offers no live view.
set -eu
name=board
. ci/lib.sh

[ -f board/index.html ] || nogo "board/index.html not found"
[ -f board/serve.py ] || nogo "board/serve.py not found"

# a.
out=$(python3 - <<'PY' 2>&1
import json, re, sys
page = open("board/index.html", encoding="utf-8").read()
m = re.search(r'<script type="application/json" id="tower-machine">(.*?)</script>', page, re.S)
if not m:
    sys.exit("board/index.html embeds no tower-machine table")
board = json.loads(m.group(1))
tower = open("core/tower.sh", encoding="utf-8").read()
def table(fn):
    body = re.search(fn + r'\(\) \{\n  case "\$1" in\n(.*?)\n  esac', tower, re.S)
    if not body:
        sys.exit(f"core/tower.sh has no {fn}() case table")
    return dict(re.findall(r"^\s*([a-z-]+)\) printf '([a-z-]+)' ;;", body.group(1), re.M))
for fn in ("precondition", "next"):
    if board.get(fn) != table(fn):
        sys.exit(f"{fn}: board {board.get(fn)} vs core/tower.sh {table(fn)}")
PY
) || nogo "the board's tower table disagrees with core/tower.sh" "$out"

# b.
tmp=$(mktemp -d)
trap 'kill "$pid" 2>/dev/null || true; rm -rf "$tmp"' EXIT
pid=""
out=$(PLANE_HOST=127.0.0.1 DOCKER_HOST="unix://$tmp/no.sock" \
  RELEASE_RECORD="$tmp/release.json" PROMOTE_OUT="$tmp/promote" WORKLOAD_KILL_SWITCH=flag \
  python3 - <<'PY' 2>&1
import importlib.util, sys
spec = importlib.util.spec_from_file_location("serve", "board/serve.py")
serve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serve)
snap = serve.snapshot()
for key in ("tickets", "delivery", "freeze", "record", "brief"):
    p = snap[key]
    if p.get("ok") is not False or not p.get("error") or "value" in p:
        sys.exit(f"{key} with nothing to read answered {p}")
ks = snap["kill_switch"]
if ks["canary"] is not None or ks["stable"] is not None:
    sys.exit(f"kill switch evaluated with no version from the plane: {ks}")
PY
) || nogo "a probe with nothing to read did not say so" "$out"

# c.
verbs=$(grep -o 'adapter("[A-Z_]*", "[a-z-]*")' board/serve.py | sed 's/.*, "\(.*\)")/\1/' | sort -u | tr '\n' ' ')
for v in $verbs; do
  case "$v" in
    get|evaluate|status) ;;
    *) nogo "board/serve.py calls the $v verb; the board is read-only" ;;
  esac
done
[ -n "$verbs" ] || nogo "board/serve.py calls no port verb at all"

# d.
port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
PLANE_HOST=127.0.0.1 DOCKER_HOST="unix://$tmp/no.sock" BOARD_LISTEN="$port" BOARD_POLL_S=60 \
  python3 board/serve.py 2>"$tmp/serve.log" &
pid=$!
i=0
until curl -fsS -o "$tmp/page" "http://127.0.0.1:$port/" 2>/dev/null; do
  i=$((i + 1))
  [ "$i" -lt 50 ] || nogo "board/serve.py did not answer on :$port" "$(cat "$tmp/serve.log")"
  sleep 0.2
done
grep -q 'id="tower-machine"' "$tmp/page" || nogo "GET / did not serve board/index.html"
curl -fsS "http://127.0.0.1:$port/state.json" | jq -e 'type == "object"' >/dev/null \
  || nogo "GET /state.json did not serve a JSON object"

kill "$pid" 2>/dev/null || true

# e.
port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
BOARD_STATIC=1 PORT="$port" python3 board/serve.py 2>"$tmp/static.log" &
pid=$!
i=0
until curl -fsS -o "$tmp/page" "http://127.0.0.1:$port/" 2>/dev/null; do
  i=$((i + 1))
  [ "$i" -lt 50 ] || nogo "board/serve.py with BOARD_STATIC=1 did not answer on :$port" "$(cat "$tmp/static.log")"
  sleep 0.2
done
grep -q 'id="tower-machine"' "$tmp/page" || nogo "BOARD_STATIC=1: GET / did not serve board/index.html"
code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/state.json")
[ "$code" = 404 ] || nogo "BOARD_STATIC=1: GET /state.json answered $code, want 404"

go

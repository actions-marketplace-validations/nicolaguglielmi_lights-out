#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# ci-decide: the Decide port and its two adapters (docs/adr/0091 §1-§5), cold:
# no network beyond loopback, no key. Written from that ADR and the M58 brief,
# not from core/decide.py or the adapters. Each adapter runs against a local
# stub of its provider's HTTP endpoint (the suite's own, in the temp dir),
# reached only through MODEL_BASE_URL.
#   a. Request validation: every refusal is exit 1, one stderr line, nothing on
#      stdout; the bounds themselves (1000 questions, 255 options or levels)
#      are accepted (they reach the lookup: exit 3).
#   b. `core/decide.py check`: a good answer passes; each planted bad answer
#      (missing or extra key, p_yes out of [0.01, 0.99], confidence, choice not
#      the argmax, probabilities not over the options or not summing to 1, a
#      wrong score, a wrong type, no tokens) is refused with one line.
#   c. The port refuses an adapter's answer that breaks the contract, and an
#      adapter that fails.
#   d. gemini-decisions and structured, each against its stub: the request the
#      provider saw, an answer that passes `check`, tokens; a missing key, a
#      provider error and (gemini) a blocked input are one line, exit 1,
#      nothing on stdout.
#   e. Replay: a planted recording replays with the recorded fields moved;
#      no recording is exit 3; DECIDE_RECORD=1 writes <sha256>.json.
set -eu
name=decide
. ci/lib.sh

for f in core/decide.py adapters/gemini-decisions/decide.sh adapters/structured/decide.sh; do
  [ -f "$f" ] || nogo "$f not found"
done

repo=$(pwd)
tmp=$(mktemp -d)
pids=""
# shellcheck disable=SC2329 # called by the EXIT trap below
cleanup() {
  for p in $pids; do kill "$p" 2>/dev/null || :; done
  rm -rf "$tmp"
}
trap cleanup EXIT

# denv ARGS...: a clean environment for the port and the adapters.
denv() {
  env -u MODEL_PROVIDER -u MODEL -u MODEL_BASE_URL -u GEMINI_API_KEY -u OPENAI_API_KEY \
    -u DECIDE -u DECIDE_FIXTURES -u DECIDE_RECORD -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
    NO_PROXY=127.0.0.1 no_proxy=127.0.0.1 "$@"
}
# cap NAME STDIN CMD...: stdout in $tmp/NAME.out, stderr in $tmp/NAME.err, exit in $rc.
cap() {
  cap_name=$1
  cap_in=$2
  shift 2
  rc=0
  "$@" < "$cap_in" > "$tmp/$cap_name.out" 2> "$tmp/$cap_name.err" || rc=$?
}
lines() { awk 'END{print NR}' "$1"; }
# fail1 NAME WHAT: the last cap exited 1 with one stderr line and nothing on stdout.
fail1() {
  [ "$rc" -eq 1 ] || nogo "$2: exit $rc, want 1" "$(cat "$tmp/$1.err")"
  [ ! -s "$tmp/$1.out" ] || nogo "$2: wrote on stdout" "$(cat "$tmp/$1.out")"
  [ "$(lines "$tmp/$1.err")" -eq 1 ] || nogo "$2: stderr has $(lines "$tmp/$1.err") lines, want 1" "$(cat "$tmp/$1.err")"
}
ok0() { [ "$rc" -eq 0 ] || nogo "$2: exit $rc, want 0" "$(cat "$tmp/$1.err")"; }

mkdir -p "$tmp/empty-fx"

# --- a. request validation ----------------------------------------------------
mkreq() { # NAME PYEXPR: write $tmp/NAME.json from a Python expression for the request
  python3 - "$tmp/$1.json" "$2" <<'PY'
import json, sys
req = eval(sys.argv[2])
open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(req))
PY
}
yn='{"type":"yes_no","instructions":"Is it so?"}'
mkreq no-questions '{"input":"x","questions":{}}'
mkreq many "{'input':'x','questions':{'q%d' % i: $yn for i in range(1001)}}"
mkreq ok-1000 "{'input':'x','questions':{'q%d' % i: $yn for i in range(1000)}}"
mkreq badkey-space "{'input':'x','questions':{'a b': $yn}}"
mkreq badkey-long "{'input':'x','questions':{'a'*65: $yn}}"
mkreq badkey-empty "{'input':'x','questions':{'': $yn}}"
mkreq badkey-dot "{'input':'x','questions':{'a.b': $yn}}"
mkreq ok-key64 "{'input':'x','questions':{'a'*64: $yn}}"
mkreq bad-type '{"input":"x","questions":{"q":{"type":"rank","instructions":"?"}}}'
mkreq choice-1 '{"input":"x","questions":{"q":{"type":"choice","instructions":"?","criteria":{"a":"A"}}}}'
mkreq choice-256 "{'input':'x','questions':{'q':{'type':'choice','instructions':'?','criteria':{'o%d' % i: 'd' for i in range(256)}}}}"
mkreq ok-choice-255 "{'input':'x','questions':{'q':{'type':'choice','instructions':'?','criteria':{'o%d' % i: 'd' for i in range(255)}}}}"
mkreq ok-choice-2 '{"input":"x","questions":{"q":{"type":"choice","instructions":"?","criteria":{"a":"A","b":"B"}}}}'
mkreq score-1 '{"input":"x","questions":{"q":{"type":"score","instructions":"?","criteria":["only"]}}}'
mkreq score-256 "{'input':'x','questions':{'q':{'type':'score','instructions':'?','criteria':['l%d' % i for i in range(256)]}}}"
mkreq ok-score-255 "{'input':'x','questions':{'q':{'type':'score','instructions':'?','criteria':['l%d' % i for i in range(255)]}}}"
printf '%s' '{not json' > "$tmp/notjson.json"
: > "$tmp/empty.json"

for c in no-questions many badkey-space badkey-long badkey-empty badkey-dot bad-type choice-1 choice-256 score-1 score-256 notjson empty; do
  cap "v-$c" "$tmp/$c.json" denv DECIDE=replay DECIDE_FIXTURES="$tmp/empty-fx" python3 core/decide.py ask
  fail1 "v-$c" "ask on the invalid request '$c'"
done
# The bounds are valid: they get past validation to the lookup, which has no recording.
for c in ok-1000 ok-key64 ok-choice-255 ok-choice-2 ok-score-255; do
  cap "b-$c" "$tmp/$c.json" denv DECIDE=replay DECIDE_FIXTURES="$tmp/empty-fx" python3 core/decide.py ask
  [ "$rc" -eq 3 ] || nogo "ask on the valid request '$c' (a bound) exited $rc, want 3 (no recording)" "$(cat "$tmp/b-$c.err")"
  [ ! -s "$tmp/b-$c.out" ] || nogo "ask on '$c' without a recording wrote on stdout"
done

# --- b. check -----------------------------------------------------------------
cat > "$tmp/req3.json" <<'JSON'
{"input": "A text.", "questions": {
  "k1": {"type": "yes_no", "instructions": "Is it so?", "criteria": {"true": "yes it is", "false": "no it is not"}},
  "k2": {"type": "choice", "instructions": "Which?", "criteria": {"a": "first", "b": "second", "c": "third"}},
  "k3": {"type": "score", "instructions": "How much?", "criteria": ["none", "some", "lots"]}}}
JSON
cat > "$tmp/good3.json" <<'JSON'
{"answers": {
  "k1": {"type": "yes_no", "p_yes": 0.8, "confidence": 0.8},
  "k2": {"type": "choice", "choice": "b", "probabilities": {"a": 0.2, "b": 0.5, "c": 0.3}, "confidence": 0.5},
  "k3": {"type": "score", "score": 1.3, "probabilities": {"0": 0.2, "1": 0.3, "2": 0.5}, "confidence": 0.5}},
 "adapter": "x", "provider": "p", "model": "m", "tokens": {"input": 10, "output": 0}, "duration_s": 0.1}
JSON
chk() { # NAME: check $tmp/NAME.json against req3
  cap "chk-$1" "$tmp/$1.json" denv python3 core/decide.py check "$tmp/req3.json"
}
chk good3
[ "$rc" -eq 0 ] || nogo "check refused a good answer" "$(cat "$tmp/chk-good3.err")"
[ ! -s "$tmp/chk-good3.out" ] || [ "$(lines "$tmp/chk-good3.out")" -le 1 ] || nogo "check on a good answer wrote more than a line on stdout"
# Within the tolerance of 0.001 it still passes.
jq '.answers.k3.score = 1.3005 | .answers.k1.confidence = 0.8005 | .answers.k2.probabilities.a = 0.2004' "$tmp/good3.json" > "$tmp/tol.json"
chk tol
[ "$rc" -eq 0 ] || nogo "check refused an answer inside the 0.001 tolerance" "$(cat "$tmp/chk-tol.err")"

plant() { # NAME JQ: a bad answer, and the check must refuse it with one line
  jq "$2" "$tmp/good3.json" > "$tmp/bad-$1.json"
  cap "chk-bad-$1" "$tmp/bad-$1.json" denv python3 core/decide.py check "$tmp/req3.json"
  [ "$rc" -eq 1 ] || nogo "check accepted a planted bad answer: $1 (exit $rc)" "$(cat "$tmp/chk-bad-$1.err")"
  [ "$(lines "$tmp/chk-bad-$1.err")" -eq 1 ] || nogo "check on '$1' printed $(lines "$tmp/chk-bad-$1.err") stderr lines, want 1" "$(cat "$tmp/chk-bad-$1.err")"
}
plant missing-key 'del(.answers.k3)'
plant extra-key '.answers.k4 = .answers.k1'
plant p-zero '.answers.k1.p_yes = 0 | .answers.k1.confidence = 1'
plant p-high '.answers.k1.p_yes = 1.2 | .answers.k1.confidence = 1.2'
plant p-over-clamp '.answers.k1.p_yes = 0.995 | .answers.k1.confidence = 0.995'
plant p-string '.answers.k1.p_yes = "0.8"'
plant confidence '.answers.k1.confidence = 0.9'
plant confidence-low '.answers.k2.confidence = 0.4'
plant choice-not-argmax '.answers.k2.choice = "a"'
plant choice-unknown '.answers.k2.choice = "z"'
plant probs-extra-option '.answers.k2.probabilities.d = 0'
plant probs-missing-option '.answers.k2.probabilities |= del(.c)'
plant probs-sum '.answers.k2.probabilities = {"a": 0.1, "b": 0.25, "c": 0.15} | .answers.k2.confidence = 0.25'
plant score-probs-sum '.answers.k3.probabilities = {"0": 0.2, "1": 0.3, "2": 0.4} | .answers.k3.confidence = 0.4'
plant score-probs-levels '.answers.k3.probabilities = {"0": 0.5, "1": 0.5} | .answers.k3.score = 0.5 | .answers.k3.confidence = 0.5'
plant score-wrong '.answers.k3.score = 1.0'
plant type-wrong '.answers.k1.type = "choice"'
plant type-swap '.answers.k2 = .answers.k1'
plant no-tokens 'del(.tokens)'
# A request that is itself invalid is not checkable either.
cap chk-badreq "$tmp/good3.json" denv python3 core/decide.py check "$tmp/no-questions.json"
[ "$rc" -eq 1 ] || nogo "check accepted an answer for a request with no questions (exit $rc)"

# --- c. the port judges what an adapter returns -------------------------------
croot="$tmp/croot"
mkdir -p "$croot/adapters" "$croot/fixtures"
ln -s "$repo/core" "$croot/core"
mkadapter() { # NAME BODY: adapters/NAME/decide.sh in the temp root
  mkdir -p "$croot/adapters/$1"
  printf '%s\n' "$2" > "$croot/adapters/$1/decide.sh"
}
cask() { # NAME ADAPTER REQFILE
  (cd "$croot" && denv DECIDE="$2" DECIDE_FIXTURES="$tmp/empty-fx" python3 core/decide.py ask < "$3" > "$tmp/$1.out" 2> "$tmp/$1.err") || rc=$?
}
mkadapter good 'cat > /dev/null; cat '"$tmp/good3.json"
rc=0
cask c-good good "$tmp/req3.json"
ok0 c-good "a conforming adapter through the port"
jq -e '.adapter == "good" and (.answers | keys == ["k1","k2","k3"])' "$tmp/c-good.out" > /dev/null \
  || nogo "the port's answer does not name the adapter (the directory name) or lost the answers" "$(cat "$tmp/c-good.out")"
jq -e '(.tokens.input | type) == "number" and (.duration_s | type) == "number"' "$tmp/c-good.out" > /dev/null \
  || nogo "the port's live answer has no tokens or duration_s"
for case in 'p-zero' 'extra-key' 'choice-not-argmax' 'probs-sum' 'score-wrong'; do
  mkadapter "bad-$case" 'cat > /dev/null; cat '"$tmp/bad-$case.json"
  rc=0
  cask "c-bad-$case" "bad-$case" "$tmp/req3.json"
  fail1 "c-bad-$case" "an adapter whose answer breaks the contract ($case)"
done
mkadapter notjson 'cat > /dev/null; echo "not json"'
rc=0; cask c-notjson notjson "$tmp/req3.json"
fail1 c-notjson "an adapter that prints something that is not JSON"
mkadapter failing 'cat > /dev/null; echo "the adapter says no" >&2; exit 1'
rc=0; cask c-failing failing "$tmp/req3.json"
fail1 c-failing "an adapter that fails"
mkadapter silent-fail 'cat > /dev/null; exit 1'
rc=0; cask c-silent silent-fail "$tmp/req3.json"
fail1 c-silent "an adapter that fails without a line"
rc=0; cask c-nodir no-such-adapter "$tmp/req3.json"
fail1 c-nodir "a DECIDE that names no adapter"

# --- d. the two adapters against their stubs ----------------------------------
cat > "$tmp/stub.py" <<'PY'
import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

kind, d = sys.argv[1], sys.argv[2]
count = [0]


def behave():
    p = os.path.join(d, "behave")
    return open(p).read().strip() if os.path.exists(p) else "ok"


def gemini_answers(body):
    out = {}
    for k, q in body["questions"].items():
        t = q["type"]
        if t == "noul":
            out[k] = {"type": "noul", "noul": 0.8, "confidence": 0.8}
        elif t == "choice":
            opts = list(q["criteria"])
            n = len(opts)
            w = [n - i for i in range(n)]
            p = [round(x / sum(w), 6) for x in w]
            out[k] = {"type": "choice", "choice": opts[0], "probabilities": dict(zip(opts, p)), "confidence": p[0]}
        else:
            n = len(q["criteria"])
            w = [i + 1 for i in range(n)]
            p = [round(x / sum(w), 6) for x in w]
            out[k] = {"type": "score", "score": round(sum(i * p[i] for i in range(n)), 6),
                      "legend": {str(i): q["criteria"][i] for i in range(n)},
                      "probabilities": {str(i): p[i] for i in range(n)}, "confidence": max(p)}
    return out


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("content-length") or 0))
        count[0] += 1
        i = count[0]
        with open(os.path.join(d, "req-%d.json" % i), "wb") as fh:
            fh.write(raw)
        with open(os.path.join(d, "req-%d.meta" % i), "w") as fh:
            json.dump({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}}, fh)
        mode = behave()
        if mode == "error400":
            return self.send(400, {"error": {"code": 400, "message": "the stub refuses this", "message_detail": "x"}})
        if mode == "error500":
            return self.send(500, {"error": {"code": 500, "message": "the stub is down"}})
        body = json.loads(raw)
        if kind == "gemini":
            if mode == "blocked":
                return self.send(200, {"prompt_feedback": {"block_reason": "safety"}})
            return self.send(200, {"answers": gemini_answers(body),
                                   "usage": {"total_input_tokens": 777, "total_output_tokens": 0}})
        content = open(os.path.join(d, "script.json")).read()
        return self.send(200, {"id": "x", "object": "chat.completion", "created": 0, "model": "stub",
                               "choices": [{"index": 0, "finish_reason": "stop",
                                            "message": {"role": "assistant", "content": content}}],
                               "usage": {"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168}})


srv = HTTPServer(("127.0.0.1", 0), H)
with open(os.path.join(d, "port.tmp"), "w") as fh:
    fh.write(str(srv.server_address[1]))
os.rename(os.path.join(d, "port.tmp"), os.path.join(d, "port"))
srv.serve_forever()
PY
start_stub() { # KIND DIR -> port in $tmp/DIRname/port
  mkdir -p "$2"
  python3 "$tmp/stub.py" "$1" "$2" 2> "$2/stub.err" &
  pids="$pids $!"
  n=0
  while [ ! -f "$2/port" ]; do
    n=$((n + 1))
    [ "$n" -le 100 ] || nogo "the $1 stub did not start" "$(cat "$2/stub.err")"
    sleep 0.1
  done
}
start_stub gemini "$tmp/gs"
start_stub openai "$tmp/os"
gport=$(cat "$tmp/gs/port")
oport=$(cat "$tmp/os/port")
nreq() { find "$1" -name 'req-*.json' | wc -l | tr -d ' '; }

# --- d1. gemini-decisions -----------------------------------------------------
gem() { # NAME [ENV...]: the adapter directly, request on stdin
  gem_name=$1
  shift
  cap "$gem_name" "$tmp/req3.json" denv MODEL_BASE_URL="http://127.0.0.1:$gport" "$@" sh adapters/gemini-decisions/decide.sh
}
printf ok > "$tmp/gs/behave"
before=$(nreq "$tmp/gs")
gem g-ok GEMINI_API_KEY=gem-key-123
ok0 g-ok "gemini-decisions on its stub"
[ ! -s "$tmp/g-ok.err" ] || nogo "gemini-decisions is not silent on success" "$(cat "$tmp/g-ok.err")"
[ "$(nreq "$tmp/gs")" -eq $((before + 1)) ] || nogo "gemini-decisions sent $(( $(nreq "$tmp/gs") - before )) requests, want 1"
last=$(nreq "$tmp/gs")
python3 - "$tmp/gs/req-$last.json" "$tmp/gs/req-$last.meta" "$tmp/req3.json" <<'PY' || nogo "the request gemini-decisions sent is not the Decisions API's (docs/adr/0091 §2)"
import json, sys
body = json.load(open(sys.argv[1]))
meta = json.load(open(sys.argv[2]))
req = json.load(open(sys.argv[3]))
def need(c, why):
    if not c:
        print(why, file=sys.stderr)
        sys.exit(1)
need(meta["path"] == "/v1beta/decisions", "path %r" % meta["path"])
need(meta["headers"].get("x-goog-api-key") == "gem-key-123", "x-goog-api-key header %r" % meta["headers"].get("x-goog-api-key"))
need(isinstance(body.get("model"), str) and body["model"], "no model")
need(body.get("input") == req["input"], "input is not the request's")
qs = body["questions"]
need(sorted(qs) == sorted(req["questions"]), "question keys differ")
need(qs["k1"]["type"] == "noul" and qs["k1"]["instructions"] == "Is it so?", "yes_no is not noul with its instructions")
need(qs["k1"]["criteria"] == {"true_description": "yes it is", "false_description": "no it is not"}, "yes_no criteria %r" % qs["k1"].get("criteria"))
need(qs["k2"]["type"] == "choice" and qs["k2"]["criteria"] == req["questions"]["k2"]["criteria"], "choice")
need(qs["k3"]["type"] == "score" and qs["k3"]["criteria"] == req["questions"]["k3"]["criteria"], "score")
PY
jq -e '.answers.k1 == {"type":"yes_no","p_yes":0.8,"confidence":0.8}
  and .answers.k2.type == "choice" and .answers.k2.choice == "a" and .answers.k2.confidence == 0.5
  and .answers.k3.type == "score" and (.answers.k3.score - 1.3333 | fabs) < 0.001
  and .provider == "gemini" and .tokens.input == 777 and .tokens.output == 0
  and (.model | type == "string" and length > 0)' "$tmp/g-ok.out" > /dev/null \
  || nogo "gemini-decisions did not map the provider's answer to the port's (yes_no, provider gemini, tokens 777/0)" "$(cat "$tmp/g-ok.out")"
# Through the port, and the port's check judges it.
gemask() { # NAME [ENV...]
  gemask_name=$1
  shift
  cap "$gemask_name" "$tmp/req3.json" denv DECIDE=gemini-decisions DECIDE_FIXTURES="$tmp/empty-fx" MODEL_BASE_URL="http://127.0.0.1:$gport" "$@" python3 core/decide.py ask
}
gemask g-ask GEMINI_API_KEY=gem-key-123
ok0 g-ask "ask through gemini-decisions"
jq -e '.adapter == "gemini-decisions" and (.duration_s | type == "number") and .replayed != true' "$tmp/g-ask.out" > /dev/null \
  || nogo "the port's answer through gemini-decisions lacks adapter or duration_s" "$(cat "$tmp/g-ask.out")"
cap g-check "$tmp/g-ask.out" denv python3 core/decide.py check "$tmp/req3.json"
[ "$rc" -eq 0 ] || nogo "the answer of gemini-decisions does not pass core/decide.py check" "$(cat "$tmp/g-check.err")"
# Failures: one line, exit 1, nothing on stdout.
before=$(nreq "$tmp/gs")
gem g-nokey
fail1 g-nokey "gemini-decisions with no GEMINI_API_KEY"
grep -q 'GEMINI_API_KEY' "$tmp/g-nokey.err" || nogo "the line for a missing Gemini key does not name GEMINI_API_KEY" "$(cat "$tmp/g-nokey.err")"
grep -q 'DECIDE=structured' "$tmp/g-nokey.err" || nogo "the line for a missing Gemini key does not name DECIDE=structured" "$(cat "$tmp/g-nokey.err")"
gem g-placeholder GEMINI_API_KEY=replace-me
fail1 g-placeholder "gemini-decisions with the placeholder key"
grep -q 'GEMINI_API_KEY' "$tmp/g-placeholder.err" || nogo "the placeholder-key line does not name GEMINI_API_KEY"
[ "$(nreq "$tmp/gs")" -eq "$before" ] || nogo "gemini-decisions sent a request with no usable key"
printf error400 > "$tmp/gs/behave"
gem g-400 GEMINI_API_KEY=gem-key-123
fail1 g-400 "gemini-decisions on a provider 400"
printf error500 > "$tmp/gs/behave"
gem g-500 GEMINI_API_KEY=gem-key-123
fail1 g-500 "gemini-decisions on a provider 500"
printf blocked > "$tmp/gs/behave"
gem g-blocked GEMINI_API_KEY=gem-key-123
fail1 g-blocked "gemini-decisions on a blocked input"
grep -q 'safety' "$tmp/g-blocked.err" || nogo "the blocked-input line does not name the block reason" "$(cat "$tmp/g-blocked.err")"
gemask g-ask-blocked GEMINI_API_KEY=gem-key-123
fail1 g-ask-blocked "ask through gemini-decisions on a blocked input"
printf ok > "$tmp/gs/behave"

# --- d2. structured -----------------------------------------------------------
cat > "$tmp/os/script.json" <<'JSON'
{"k1": {"p_yes": 0.7}, "k2": {"probabilities": {"a": 2, "b": 6, "c": 2}}, "k3": {"probabilities": {"0": 1, "1": 1, "2": 8}}}
JSON
stru() { # NAME [ENV...]: through the port, DECIDE=structured
  stru_name=$1
  shift
  cap "$stru_name" "$stru_in" denv DECIDE=structured DECIDE_FIXTURES="$tmp/empty-fx" MODEL_PROVIDER=openai MODEL=stub \
    MODEL_BASE_URL="http://127.0.0.1:$oport" "$@" python3 core/decide.py ask
}
stru_in="$tmp/req3.json"
printf ok > "$tmp/os/behave"
before=$(nreq "$tmp/os")
stru s-ok OPENAI_API_KEY=stub
ok0 s-ok "ask through structured on its stub"
jq -e '.adapter == "structured" and .provider == "openai" and .model == "stub" and .tokens.input == 123
  and (.duration_s | type == "number")
  and .answers.k1 == {"type":"yes_no","p_yes":0.7,"confidence":0.7}
  and .answers.k2.choice == "b" and (.answers.k2.probabilities.b - 0.6 | fabs) < 0.001 and (.answers.k2.confidence - 0.6 | fabs) < 0.001
  and (.answers.k3.score - 1.7 | fabs) < 0.001 and (.answers.k3.confidence - 0.8 | fabs) < 0.001' "$tmp/s-ok.out" > /dev/null \
  || nogo "structured did not normalise and derive the answers as docs/adr/0091 §3 says (choice b at 0.6, score 1.7)" "$(cat "$tmp/s-ok.out")"
cap s-check "$tmp/s-ok.out" denv python3 core/decide.py check "$tmp/req3.json"
[ "$rc" -eq 0 ] || nogo "the answer of structured does not pass core/decide.py check" "$(cat "$tmp/s-check.err")"
[ "$(nreq "$tmp/os")" -eq $((before + 1)) ] || nogo "structured sent $(( $(nreq "$tmp/os") - before )) requests, want 1"
last=$(nreq "$tmp/os")
python3 - "$tmp/os/req-$last.json" "$tmp/os/req-$last.meta" <<'PY' || nogo "the request structured sent has no JSON-schema response format requiring every question key (docs/adr/0091 §3)"
import json, sys
body = json.load(open(sys.argv[1]))
meta = json.load(open(sys.argv[2]))
def need(c, why):
    if not c:
        print(why, file=sys.stderr)
        sys.exit(1)
need(meta["path"].endswith("/chat/completions"), "path %r" % meta["path"])
rf = body.get("response_format") or {}
need(rf.get("type") == "json_schema", "response_format type %r" % rf.get("type"))
schema = (rf.get("json_schema") or {}).get("schema") or {}
need(sorted(schema.get("required", [])) == ["k1", "k2", "k3"], "schema required %r" % schema.get("required"))
need(sorted(schema.get("properties", {})) == ["k1", "k2", "k3"], "schema properties %r" % sorted(schema.get("properties", {})))
need(body.get("model", "").endswith("stub"), "model %r" % body.get("model"))
PY
# The clamp and the normalisation by the sum.
printf '%s' '{"input": "Members give their seat back.", "questions": {"q": {"type": "yes_no", "instructions": "Is it so?"}}}' > "$tmp/yn1.json"
for pair in "1.0:0.99" "0:0.01" "0.5:0.5"; do
  given=${pair%:*}
  want=${pair#*:}
  printf '{"q": {"p_yes": %s}}' "$given" > "$tmp/os/script.json"
  stru_in="$tmp/yn1.json"
  stru s-clamp OPENAI_API_KEY=stub
  ok0 s-clamp "structured with p_yes $given"
  jq -e --argjson w "$want" '(.answers.q.p_yes - $w | fabs) < 0.0001 and (.answers.q.confidence - ([$w, 1 - $w] | max) | fabs) < 0.0001' "$tmp/s-clamp.out" > /dev/null \
    || nogo "structured did not clamp p_yes $given to $want" "$(cat "$tmp/s-clamp.out")"
done
printf '%s' '{"q": {"type": "choice", "instructions": "Which?", "criteria": {"a": "A", "b": "B"}}}' > "$tmp/ch2.json"
printf '{"q": {"probabilities": {"a": 0, "b": 0}}}' > "$tmp/os/script.json"
stru_in="$tmp/ch2.json"
stru s-sum0 OPENAI_API_KEY=stub
fail1 s-sum0 "structured with a distribution whose sum is 0"
# Failures.
stru_in="$tmp/req3.json"
cat > "$tmp/os/script.json" <<'JSON'
{"k1": {"p_yes": 0.7}, "k2": {"probabilities": {"a": 2, "b": 6, "c": 2}}, "k3": {"probabilities": {"0": 1, "1": 1, "2": 8}}}
JSON
before=$(nreq "$tmp/os")
stru s-nokey
fail1 s-nokey "structured with no OPENAI_API_KEY"
grep -q 'OPENAI_API_KEY' "$tmp/s-nokey.err" || nogo "the missing-key line of structured does not name OPENAI_API_KEY" "$(cat "$tmp/s-nokey.err")"
[ "$(nreq "$tmp/os")" -eq "$before" ] || nogo "structured sent a request with no key"
printf error400 > "$tmp/os/behave"
stru s-400 OPENAI_API_KEY=stub
fail1 s-400 "structured on a provider error"
printf ok > "$tmp/os/behave"

# --- e. replay and record -----------------------------------------------------
# A request with a non-ASCII character and its keys in no sorted order: the key
# is the sha256 of the canonical form (sorted keys, indent 2, ensure_ascii).
cat > "$tmp/reqr.json" <<'JSON'
{"questions": {"b-q": {"instructions": "Café open?", "type": "yes_no"}}, "input": "Un café, s'il vous plaît."}
JSON
rkey=$(python3 - "$tmp/reqr.json" <<'PY'
import hashlib, json, sys
obj = json.load(open(sys.argv[1], encoding="utf-8"))
print(hashlib.sha256(json.dumps(obj, sort_keys=True, indent=2).encode("utf-8")).hexdigest())
PY
)
mkdir -p "$tmp/fx-plant"
python3 - "$tmp/reqr.json" "$tmp/fx-plant/$rkey.json" <<'PY'
import json, sys
req = json.load(open(sys.argv[1], encoding="utf-8"))
rec = {"request": req,
       "answer": {"answers": {"b-q": {"type": "yes_no", "p_yes": 0.9, "confidence": 0.9}},
                  "adapter": "gemini-decisions", "provider": "gemini", "model": "gemini-decision-1",
                  "tokens": {"input": 321, "output": 0}, "duration_s": 0.2},
       "recorded_at": "2026-11-16T10:00:00Z"}
json.dump(rec, open(sys.argv[2], "w", encoding="utf-8"))
PY
cap r-ok "$tmp/reqr.json" denv DECIDE=replay DECIDE_FIXTURES="$tmp/fx-plant" python3 core/decide.py ask
ok0 r-ok "replay of a planted recording"
jq -e '.answers == {"b-q": {"type":"yes_no","p_yes":0.9,"confidence":0.9}}
  and .adapter == "replay" and .replayed == true and .provider == null and .model == null
  and .tokens == {"input": 0, "output": 0}
  and .recorded.adapter == "gemini-decisions" and .recorded.provider == "gemini" and .recorded.model == "gemini-decision-1"
  and .recorded.tokens == {"input": 321, "output": 0}' "$tmp/r-ok.out" > /dev/null \
  || nogo "a replayed answer is not the recording's answers with replayed true, zero tokens and the recorded fields moved under 'recorded' (docs/adr/0091 §5)" "$(cat "$tmp/r-ok.out")"
[ ! -s "$tmp/r-ok.err" ] || nogo "a replay is not silent" "$(cat "$tmp/r-ok.err")"
# A request that differs by one character has no recording: exit 3 and the line.
jq -c '.input += "!"' "$tmp/reqr.json" > "$tmp/reqr2.json"
cap r-miss "$tmp/reqr2.json" denv DECIDE=replay DECIDE_FIXTURES="$tmp/fx-plant" python3 core/decide.py ask
[ "$rc" -eq 3 ] || nogo "a request with no recording exited $rc, want 3"
[ ! -s "$tmp/r-miss.out" ] || nogo "a request with no recording wrote on stdout"
[ "$(lines "$tmp/r-miss.err")" -eq 1 ] || nogo "the no-recording refusal is not one stderr line" "$(cat "$tmp/r-miss.err")"
case "$(cat "$tmp/r-miss.err")" in
  "no recording of this decision at L0 (fixtures/decide/"*) : ;;
  *) nogo "the no-recording line is '$(cat "$tmp/r-miss.err")', want it to start 'no recording of this decision at L0 (fixtures/decide/'" ;;
esac
# DECIDE_FIXTURES defaults to fixtures/decide: a temp root with an empty one.
mkdir -p "$croot/fixtures/decide"
rc=0
(cd "$croot" && denv DECIDE=replay python3 core/decide.py ask < "$tmp/reqr.json" > "$tmp/r-def.out" 2> "$tmp/r-def.err") || rc=$?
[ "$rc" -eq 3 ] || nogo "the default DECIDE_FIXTURES (fixtures/decide) was not read: exit $rc, want 3"

# DECIDE_RECORD=1 with a live adapter writes <sha256>.json; without it nothing.
mkdir -p "$tmp/fx-rec" "$tmp/fx-norec"
cap rec-off "$tmp/reqr.json" denv DECIDE=gemini-decisions DECIDE_FIXTURES="$tmp/fx-norec" MODEL_BASE_URL="http://127.0.0.1:$gport" GEMINI_API_KEY=gem-key-123 python3 core/decide.py ask
ok0 rec-off "a live call without DECIDE_RECORD"
[ -z "$(ls "$tmp/fx-norec")" ] || nogo "a live call without DECIDE_RECORD wrote a recording" "$(ls "$tmp/fx-norec")"
cap rec-on "$tmp/reqr.json" denv DECIDE=gemini-decisions DECIDE_RECORD=1 DECIDE_FIXTURES="$tmp/fx-rec" MODEL_BASE_URL="http://127.0.0.1:$gport" GEMINI_API_KEY=gem-key-123 python3 core/decide.py ask
ok0 rec-on "a live call with DECIDE_RECORD=1"
[ "$(ls "$tmp/fx-rec")" = "$rkey.json" ] || nogo "the recording is not <sha256 of the canonical request>.json" "want $rkey.json, found $(ls "$tmp/fx-rec")"
jq -e --slurpfile req "$tmp/reqr.json" '.request == $req[0] and (.answer.answers | keys == ["b-q"]) and .answer.provider == "gemini"
  and (.recorded_at | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]+Z$"))' "$tmp/fx-rec/$rkey.json" > /dev/null \
  || nogo "the recording does not hold the request, the adapter's answer and recorded_at" "$(cat "$tmp/fx-rec/$rkey.json")"
# What was recorded replays whole.
cap rec-replay "$tmp/reqr.json" denv DECIDE=replay DECIDE_FIXTURES="$tmp/fx-rec" python3 core/decide.py ask
ok0 rec-replay "replay of what DECIDE_RECORD wrote"
jq -e --slurpfile live "$tmp/rec-on.out" '.replayed == true and .answers == $live[0].answers and .recorded.provider == "gemini"' "$tmp/rec-replay.out" > /dev/null \
  || nogo "a recording made by DECIDE_RECORD=1 does not replay the live answers" "$(cat "$tmp/rec-replay.out")"
# Recording a failed call writes nothing.
printf error400 > "$tmp/gs/behave"
mkdir -p "$tmp/fx-failrec"
cap rec-fail "$tmp/reqr.json" denv DECIDE=gemini-decisions DECIDE_RECORD=1 DECIDE_FIXTURES="$tmp/fx-failrec" MODEL_BASE_URL="http://127.0.0.1:$gport" GEMINI_API_KEY=gem-key-123 python3 core/decide.py ask
fail1 rec-fail "a recorded call that fails"
[ -z "$(ls "$tmp/fx-failrec")" ] || nogo "a failed call left a recording"
printf ok > "$tmp/gs/behave"
# ask through structured: a contract-valid answer (also proved in d2).
go

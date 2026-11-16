"""fake-cli's run.sh: the adapter contract of docs/adr/0041, minus the container.

Run from the proof's tree as `sh adapters/fake-cli/run.sh`, exactly as the
suite runs a real harness. FAKE_DEFECT names the one thing it does wrong, if
any (core/gates/harness_proof.py's DEFECTS). Python because a fixture is no
reason for a long shell file (docs/adr/0084, amendment A2)."""
import glob
import hashlib
import json
import os
import subprocess
import sys
import time

env = os.environ
for var in ("ROLE", "TICKET", "WORKSPACE", "BASE", "OUT", "TICKET_FILE", "THINKING", "MAX_TURNS", "TIMEOUT_S",
            "TOKEN_BUDGET"):
    if not env.get(var):
        sys.exit("run.sh: %s: parameter null or not set" % var)
defect = env.get("FAKE_DEFECT", "")
here = os.path.dirname(os.path.abspath(__file__))
OUT, WORKSPACE = env["OUT"], env["WORKSPACE"]


def say(line):
    sys.stderr.write("harness-fake-cli: %s\n" % line)
    sys.stderr.flush()


def write(path, text):
    with open(path, "w") as fh:
        fh.write(text)


def conf(path, key):
    for line in open(path).read().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1]
    return ""


def git(*args):
    return subprocess.run(["git", "-C", WORKSPACE, *args], capture_output=True, text=True)


if defect == "late-refusal":
    try:
        subprocess.run(["docker-compose", "--profile", "crew", "run", "--rm", "fake-cli"], stdout=2, stdin=subprocess.DEVNULL)
    except OSError:
        pass
# The file whose PROVIDER is MODEL_PROVIDER, over every conformance file (docs/adr/0092 §2).
# `one-provider` reads conformance.env alone, so it refuses the second provider; `no-refusal`
# takes the first file for a provider no file declares.
files = [os.path.join(here, "conformance.env")]
if defect != "one-provider":
    files += sorted(glob.glob(os.path.join(here, "conformance.*.env")))
conf_file = next((f for f in files if os.path.isfile(f) and conf(f, "PROVIDER") == env.get("MODEL_PROVIDER", "")), "")
if not conf_file and defect == "no-refusal":
    conf_file = os.path.join(here, "conformance.env")
if not conf_file:
    if defect == "more-lines":
        say("starting up")
    say("MODEL_PROVIDER=%s needs the codex or gemini-cli harness; this harness runs anthropic and zai only"
        % env.get("MODEL_PROVIDER", ""))
    sys.exit(1)

# The one way out of the internal network (docs/adr/0046 §4), as every real run.sh
# asks for it: after its refusals, before it runs the container.
if subprocess.run(["sh", "core/egress.sh", conf(conf_file, "EGRESS")]).returncode != 0:
    sys.exit(1)
port = env["MODEL_BASE_URL"].rsplit(":", 1)[1]
extra = {"allow-sink": "conformance-sink:%s" % port, "sink-touch": "conformance-sink:%s" % port,
         "allow-model-port": "conformance-model:%d" % (int(port) + 1), "allow-example": "example.com:443",
         "side-host": "telemetry.example:%s" % port}.get(defect)
if extra:
    with open(".crew/egress/allow", "a") as fh:
        fh.write(extra + "\n")
# What compose gives the container: the proxy variables, and a network that only
# reaches the proxy (netshim/sitecustomize.py). A defect is a hole in that network.
for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    env[var] = "http://egress:3128"
env["NETSHIM_EGRESS_PORT"] = open(".proof/egress.port").read().strip()
env["NETSHIM_STUB_PORT"] = port
env["PYTHONPATH"] = os.path.join(here, "netshim")
env["NETSHIM_OPEN"] = {"direct-model": "dns-model tcp-stub", "open-dns": "dns-public", "open-public": "tcp-public",
                       "open-sink-direct": "dns-sink tcp-stub"}.get(defect, "")

# The thinking map of the file's provider (`map-of-first` reads the first provider's for every one),
# and the key from the file's KEY_VAR, which the suite exports for every conformance file.
prefix = "ANTHROPIC" if defect == "map-of-first" else env["MODEL_PROVIDER"].upper()
effort = conf(os.path.join(here, "thinking.env"), prefix + "_" + env["THINKING"].upper())
key = env.get(conf(conf_file, "KEY_VAR"), "")
if not key:
    sys.exit("run.sh: %s: parameter null or not set" % conf(conf_file, "KEY_VAR"))
os.makedirs(OUT, exist_ok=True)
if defect == "key-in-probe-case" and os.path.isfile(os.path.join(WORKSPACE, "probe.py")):
    write(OUT + "/leak.log", key + "\n")
if defect == "key-in-review" and env["ROLE"] == "test-reviewer":
    write(OUT + "/leak.log", key + "\n")

# The repository's MCP servers (docs/adr/0073 §8), as core/crew.sh hands them
# over: CREW_MCP holds decl.json; mcp.sh translates it into OUT/mcp, and the
# guard gets the named tools' qualified names (what an entrypoint exports).
mcp_dir = allow = ""
if env.get("CREW_MCP"):
    if not os.path.isfile(env["CREW_MCP"] + "/decl.json"):
        say("CREW_MCP=%s holds no decl.json (docs/adr/0073 §7)" % env["CREW_MCP"])
        sys.exit(1)
    os.makedirs(OUT + "/mcp", exist_ok=True)
    write(OUT + "/mcp/decl.json", open(env["CREW_MCP"] + "/decl.json").read())
    if subprocess.run(["sh", os.path.join(here, "mcp.sh"), OUT + "/mcp/decl.json", OUT + "/mcp", WORKSPACE]).returncode:
        sys.exit(1)
    mcp_dir = OUT + "/mcp"
    allow = " ".join(line.split()[0] for line in open(OUT + "/mcp/allow").read().splitlines() if line.strip())
env["CREW_MCP_DIR"], env["CREW_MCP_ALLOW"] = mcp_dir, allow
sha = hashlib.sha256(open(env["TICKET_FILE"], "rb").read()).hexdigest()
start = time.time()
with open(OUT + "/transcript.json", "w") as out, open(OUT + "/stderr.log", "w") as err:
    rc = subprocess.run(["python3", os.path.join(here, "fake_cli.py")], stdout=out, stderr=err,
                        env=dict(env, FAKE_EFFORT=effort, FAKE_KEY=key,
                                 FAKE_GUARD=os.path.join(here, "hooks/guard.sh"))).returncode
duration = int(time.time() - start)

if rc != 0:
    stop = open(OUT + "/stop").read() if os.path.exists(OUT + "/stop") else ""
    if stop == "MAX_TURNS":
        reason = "over MAX_TURNS (%s)" % env["MAX_TURNS"]
    elif stop == "TOKEN_BUDGET":
        reason = "over TOKEN_BUDGET (%s)" % env["TOKEN_BUDGET"]
        # A budget stop still records what the run spent (docs/adr/0087 §2); `no-run-on-stop` does not.
        if defect != "no-run-on-stop":
            write(OUT + "/run.json", json.dumps({"harness": "fake-cli", "provider": env["MODEL_PROVIDER"], "model": None,
                                                 "tokens": {"input": None, "output": None, "total": None},
                                                 "duration_s": duration, "exit_code": 1}) + "\n")
    elif stop == "TIMEOUT_S":
        reason = "over TIMEOUT_S (%s s)" % env["TIMEOUT_S"]
    else:
        lines = open(OUT + "/stderr.log").read().splitlines()
        reason = "fake-cli exited %d: %s" % (rc, lines[-1] if lines else "")
    if defect == "wrong-stop-phrase":
        reason = "stopped: budget"
    if defect == "key-on-stop":
        write(OUT + "/stop.log", key + "\n")
    say(reason)
    sys.exit(1)

# A declared server that did not come up fails the run, in one line naming it
# and the section, before any pr.json (docs/adr/0073 §8).
down = open(OUT + "/mcp/down").read().split() if mcp_dir and os.path.exists(OUT + "/mcp/down") else []
if down and defect != "mcp-down-ignored":
    if defect == "mcp-down-late":
        write(OUT + "/pr.json", '{"title": "late", "body": ""}\n')
    if defect == "mcp-down-vague":
        say("a tool server failed")
    else:
        say("declared MCP server %s did not come up (ADR 0073 §8)" % ", ".join(down))
    sys.exit(1)

transcript = json.load(open(OUT + "/transcript.json"))
final = transcript["final"]
write(OUT + "/final.md", ("Final answer:\n" if defect == "final-md-header" else "") + final + "\n")
lines = final.split("\n")
title = lines[0]
rest = lines[1:]
while rest and not rest[0]:
    rest.pop(0)
body = "\n".join(rest).rstrip("\n")
write(OUT + "/pr.json", json.dumps({"title": title, "body": body}) + "\n")
# The adapter commits what the model left, when it left something (a reviewer
# changes nothing); `commit-always` commits regardless, and fails on a clean tree.
if git("status", "--porcelain").stdout.strip() or defect == "commit-always":
    git("add", "-A")
    made = git("-c", "user.name=lights-out-crew", "-c", "user.email=crew@lights-out.invalid", "commit", "-q",
               "-m", title, "-m", body)
    if made.returncode != 0:
        sys.stderr.write(made.stderr)
        sys.exit(made.returncode)
write(OUT + "/patch", git("format-patch", "--stdout", env["BASE"] + "..HEAD").stdout)
# run.json's mcp (docs/adr/0073 §9): null when nothing is declared; the calls
# counted from hooks.log's ALLOW lines by core/agents.py calls.
mcp = None
if mcp_dir and defect != "mcp-null":
    hooks = OUT + "/hooks.log"
    if not os.path.isfile(hooks) or defect == "mcp-calls-unread":
        hooks = "/dev/null"
    got = subprocess.run(["python3", "core/agents.py", "calls", "--allow", OUT + "/mcp/allow", "--hooks", hooks],
                         capture_output=True, text=True)
    if got.returncode != 0:
        say("core/agents.py calls: %s" % got.stdout.strip())
        sys.exit(1)
    calls = json.loads(got.stdout)
    decl = json.load(open(OUT + "/mcp/decl.json"))
    servers = []
    for s in decl["servers"]:
        one = {"name": s.get("name"), "transport": s.get("transport")}
        if s.get("endpoint"):
            one["endpoint"] = s["endpoint"]
        one["tools"] = s.get("tools")
        servers.append(one)
    mcp = {"sha256": decl.get("sha256"), "servers": servers,
           "unlisted": "hidden" if defect == "mcp-says-hidden" else "visible-denied",
           "calls": calls.get("calls"), "denied": calls.get("denied")}
served = env["MODEL"] if defect == "raw-model" else transcript["served"]
tokens = transcript["tokens"] * (2 if defect == "tokens-doubled" else 1)
# tokens.cached (docs/adr/0092 §6): what the model reported cached, or no key (`omit-cached`, as
# a harness that does not report it); `cached-wrong` is one token too many.
cached = None if defect == "omit-cached" else transcript["cached"] + (1 if defect == "cached-wrong" else 0)
run = {"harness": "fake-cli", "provider": env["MODEL_PROVIDER"], "model": served, "thinking": env["THINKING"],
       "turns": transcript["turns"], "tokens": dict({"input": tokens * 9 // 10, "output": tokens // 10, "total": tokens},
                     **({} if cached is None else {"cached": cached})),
       "duration_s": duration, "exit_code": 0, "input_sha256": sha, "endpoint": env.get("MODEL_BASE_URL", ""),
       "mcp": mcp}
if defect == "no-endpoint":
    del run["endpoint"]
write(OUT + "/run.json", json.dumps(run, indent=2) + "\n")

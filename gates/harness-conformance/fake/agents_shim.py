"""core/agents.py with one defect planted in its mcp verb (FAKE_DEFECT), every
other verb the real module's (core/agents_real.py in the tree): case 10r judges
only that refusal."""
import os, subprocess, sys

here = os.path.dirname(os.path.abspath(__file__))
defect = os.environ.get("FAKE_DEFECT", "")
argv = sys.argv[1:]
real = [sys.executable, os.path.join(here, "agents_real.py")] + argv
if not argv or argv[0] != "mcp":
    os.execv(sys.executable, real)
r = subprocess.run(real, capture_output=True, text=True)
out = r.stdout
if defect == "agents-mcp-accepts":
    sys.exit(0)
if defect == "agents-mcp-chatty":
    out += "see docs/adr/0073\n"
if defect == "agents-mcp-other-words":
    out = "NO-GO: agents — no MCP servers on this harness\n"
if defect == "agents-mcp-wrong-list":
    out = out.rstrip("\n") + " fake-cli\n"
if defect == "agents-mcp-writes-decl":
    d = argv[argv.index("--out") + 1]
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "decl.json"), "w").write("{}\n")
sys.stdout.write(out)
sys.stderr.write(r.stderr)
sys.exit(r.returncode)

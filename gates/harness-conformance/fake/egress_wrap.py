"""The proxy: core/egress.py itself, with the names an engine's DNS would answer
for it, and 127.0.0.2 as the address its outgoing connections come from, so
that the stub can tell the proxy from anything else on this machine. An
unknown name does not resolve, as on a real network; example.com maps to
nothing that listens, so an allowlist that let it through reads as a 502."""
import socket, sys, runpy

NAMES = {"conformance-model": "127.0.0.1", "conformance-sink": "127.0.0.1",
         "telemetry.example": "127.0.0.1", "example.com": "127.0.0.1"}
real = socket.create_connection


def create_connection(address, timeout=None, source_address=None, **kw):
    host, port = address
    if host not in NAMES:
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
    return real((NAMES[host], port), timeout, ("127.0.0.2", 0))


socket.create_connection = create_connection
socket.gethostname = lambda: "proofegress1"
sys.argv = ["egress.py", sys.argv[1]]
runpy.run_path("core/egress.py", run_name="__main__")

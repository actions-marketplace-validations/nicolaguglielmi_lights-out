"""The harness container's network, for any Python it runs (fake_cli.py and the
probe the model has it run): internal, so nothing routes but the proxy, and
`egress` is the only name DNS answers. NETSHIM_OPEN lists holes, each the
stand-in for one real defect: dns-sink, dns-model, dns-public (a name resolves
that should not); tcp-stub (the stub's address is reachable), tcp-public
(1.1.1.1:443 is). NETSHIM_CUT, set for the probe alone, makes the proxy
unreachable from it: a probe that proves nothing."""
import errno, os, socket

HOLES = set(os.environ.get("NETSHIM_OPEN", "").split())
EGRESS, STUB = ("10.9.0.2", 3128), "10.9.0.3"
NAMES = {"egress": EGRESS[0]}
if "dns-sink" in HOLES:
    NAMES["conformance-sink"] = STUB
if "dns-model" in HOLES:
    NAMES["conformance-model"] = STUB
if "dns-public" in HOLES:
    NAMES["example.com"] = "93.184.216.34"
real_getaddrinfo, real_connect = socket.getaddrinfo, socket.socket.connect


def is_address(host):
    try:
        socket.inet_aton(host)
        return True
    except OSError:
        return False


def getaddrinfo(host, *args, **kwargs):
    if isinstance(host, str) and host in NAMES:
        host = NAMES[host]
    elif isinstance(host, str) and not is_address(host):
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
    return real_getaddrinfo(host, *args, **kwargs)


def connect(self, address):
    host, port = address[0], address[1]
    real = None
    if (host, port) == EGRESS and "NETSHIM_CUT" not in os.environ:
        real = ("127.0.0.1", int(os.environ["NETSHIM_EGRESS_PORT"]))
    elif host == STUB and "tcp-stub" in HOLES:
        real = ("127.0.0.1", port)
    elif (host, port) == ("1.1.1.1", 443) and "tcp-public" in HOLES:
        real = ("127.0.0.1", int(os.environ["NETSHIM_STUB_PORT"]))
    if real is None:
        raise OSError(errno.ENETUNREACH, "Network is unreachable")
    return real_connect(self, real)


socket.getaddrinfo, socket.socket.connect = getaddrinfo, connect

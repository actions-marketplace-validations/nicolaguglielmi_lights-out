"""The proof's one port picker, for every listener it starts (stub.py and
core/egress.py, both on 0.0.0.0): a port free on the address the listener
will bind. A port picked on 127.0.0.1 can be held, or in TIME_WAIT, on
127.0.0.2, where egress_wrap.py binds the proxy's outgoing sockets from the
same allocator, and the listener's bind then fails with EADDRINUSE. A pick is
only taken while no proxy runs, so nothing takes the port between the pick
and the bind. Proved by core/gates/harness_proof.py under the proxy's load."""
import socket

s = socket.socket()
s.bind(("0.0.0.0", 0))
print(s.getsockname()[1])

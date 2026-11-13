# SPDX-License-Identifier: Apache-2.0
"""gates/eventbus-conformance.sh's suite: the EventBus port (docs/adr/0060
§4; the contract is docs/adr/0019 §3). Written from the ADRs, never from an
adapter.

    python3 -m core.gates.eventbus

It drives whichever EVENT_BUS is set, only through `sh
adapters/$EVENT_BUS/{publish,pull,ack}.sh`. `pull` prints "<ackId> <data>"
on one line, or nothing; the line is split at its first space. Cases, in
this order, the first disagreement a NO-GO naming the case:
  0 the first pull prints nothing: a bus with someone else's message on it
    is "the bus is not idle", and the suite does not ack it
  1 publish, then pull: one line, the data byte for byte what was published
    (a JSON line with spaces, a double quote, a backslash and a non-ASCII
    character), the ackId non-empty with no whitespace in it
  2 while that message is leased, a second pull prints nothing
  3 ack exits 0, and the next pull prints nothing
  4 three messages are pulled and acked as exactly that set (no order is
    promised), then a pull prints nothing
  5 only when CONFORMANCE_ACK_DEADLINE gives the adapter's ack deadline, a
    positive integer of seconds: a message pulled and not acked comes back
    after it plus one second, one that was acked does not. Unset, the GO
    line says case 5 did not run.
It consumes nothing that is not its own: every message carries the run id.
On any exit after a publish it acks the ackIds it was handed for its own
messages, then drains the bus for its own still queued, at most 8 pulls (it
publishes six at most), leaving any other message alone.
"""

import os
import re
import time

from . import NoGo, adapter, main, run_id, say


def lines_of(text):
    """How many lines `awk 'END{print NR}'` counts."""
    return text.count("\n") + (1 if text and not text.endswith("\n") else 0)


def snip(text):
    return text.encode("utf-8")[:200].decode("utf-8", "ignore").replace("\n", " ")


class Suite:
    def __init__(self, bus, verb, deadline, sleep):
        self.bus, self.verb, self.deadline, self.sleep = bus, verb, deadline, sleep
        rid = run_id()
        self.mark = f"conf-{rid}"
        self.published = False
        self.pulled = []
        self.rc, self.out = 0, ""
        say(f"[eventbus-conformance] run {rid} on EVENT_BUS={bus}")

    def call(self, name, *args):
        self.rc, self.out, err = self.verb(name, *args)
        for line in err.splitlines():
            say(f"  [{name}] {line}")
        return self.rc

    def publish(self, data):
        self.published = True
        return self.call("publish", data)

    def pull(self):
        """Pull; sets nlines, line, ackid and data, keeps the suite's ackIds."""
        self.call("pull")
        self.nlines = lines_of(self.out)
        self.line = self.out.rstrip("\n")
        self.ackid = self.line.split(" ", 1)[0]
        self.data = self.line.split(" ", 1)[1] if " " in self.line else ""
        if self.nlines == 1 and self.mark in self.data:
            self.pulled.append(self.ackid)
        return self.rc

    def want_nothing(self, case, what):
        self.pull()
        if self.rc != 0 or self.out:
            raise NoGo(f"{case}: {what}, pull exited {self.rc} and printed [{snip(self.out)}], want exit 0 and nothing")

    def want_message(self, case, what):
        self.pull()
        if self.rc != 0:
            raise NoGo(f"{case}: {what}, pull exited {self.rc}")
        if self.nlines < 1:
            raise NoGo(f"{case}: {what}, pull printed nothing: the message is lost")
        if self.nlines != 1:
            raise NoGo(f"{case}: {what}, pull printed {self.nlines} lines [{snip(self.out)}], "
                       "want one '<ackId> <data>' line")
        if " " not in self.line:
            raise NoGo(f"{case}: {what}, pull printed [{snip(self.out)}], want '<ackId> <data>': "
                       "there is no space after the ackId")

    def message(self, step):
        return '{"ticket":"' + self.mark + '","step":"' + step + '"}'

    def cleanup(self):
        if not self.published:
            return
        for ackid in self.pulled:
            self.verb("ack", ackid)
        for _ in range(8):
            rc, out, _err = self.verb("pull")
            if rc != 0 or not out:
                break
            line = out.split("\n", 1)[0]
            if self.mark in line:
                self.verb("ack", line.split(" ", 1)[0])

    def run(self):
        if self.pull() != 0:
            raise NoGo(f"case0 idle: pull exited {self.rc} on a bus the suite has not written to")
        if self.out:
            raise NoGo(f"case0 idle: the bus is not idle, the first pull printed [{snip(self.out)}]; the suite did "
                       "not ack it, it is not the suite's and returns after the adapter's deadline")
        say("[eventbus-conformance] case 0 the bus is idle: GO")

        want = '{"ticket":"' + self.mark + '","step":"a b","note":"q\\"uote back\\\\slash ü"}'
        if self.publish(want):
            raise NoGo(f"case1 roundtrip: publish exited {self.rc}")
        self.want_message("case1 roundtrip", "after a publish")
        if not self.ackid or re.search(r"\s", self.ackid):
            raise NoGo(f"case1 roundtrip: the ackId [{self.ackid}] is empty or holds whitespace")
        if self.data != want:
            raise NoGo(f"case1 roundtrip: pull printed data [{self.data}], published [{want}] (or the ackId holds "
                       "whitespace, so the line was split in the wrong place)")
        lease = self.ackid
        say("[eventbus-conformance] case 1 publish and pull, the data byte for byte: GO")

        self.want_nothing("case2 lease", "the message is leased and not acked")
        say("[eventbus-conformance] case 2 a leased message is not handed out again: GO")

        if self.call("ack", lease):
            raise NoGo(f"case3 ack: ack exited {self.rc} on the ackId that pull printed")
        self.want_nothing("case3 ack", "after the ack")
        say("[eventbus-conformance] case 3 ack: GO")

        sent, got = [], []
        for k in ("m1", "m2", "m3"):
            if self.publish(self.message(k)):
                raise NoGo(f"case4 set: publish exited {self.rc} for {k}")
            sent.append(self.message(k))
        for k in (1, 2, 3):
            if self.pull():
                raise NoGo(f"case4 set: pull {k} of 3 exited {self.rc}")
            if self.nlines < 1:
                raise NoGo(f"case4 set: pull {k} of 3 printed nothing: a published message was lost")
            if self.nlines != 1:
                raise NoGo(f"case4 set: pull {k} of 3 printed {self.nlines} lines [{snip(self.out)}], want one message")
            got.append(self.data)
            if self.call("ack", self.ackid):
                raise NoGo(f"case4 set: ack exited {self.rc} on message {k} of 3")
        if sorted(got) != sorted(sent):
            raise NoGo(f"case4 set: the three pulls returned [{' '.join(got)}], the three published were "
                       f"[{' '.join(sent)}]")
        self.want_nothing("case4 set", "all three are acked")
        say("[eventbus-conformance] case 4 three messages are pulled and acked as that set: GO")

        if not self.deadline:
            return f"{self.bus}, 5 cases; case 5 (redelivery) not run: CONFORMANCE_ACK_DEADLINE unset"
        self.redelivery(int(self.deadline))
        return f"{self.bus}, 6 cases"

    def redelivery(self, deadline):
        case = "case5 redelivery"
        msg_a, msg_b = self.message("redelivery-A"), self.message("redelivery-B")
        for which, msg in (("A", msg_a), ("B", msg_b)):
            if self.publish(msg):
                raise NoGo(f"{case}: publish exited {self.rc} for {which}")
            self.want_message(case, f"pulling {which}")
            if self.data != msg:
                raise NoGo(f"{case}: pulling {which} printed [{self.data}], want [{msg}]")
            if which == "A" and self.call("ack", self.ackid):
                raise NoGo(f"{case}: ack exited {self.rc} on A")
        say(f"[eventbus-conformance] case 5: A acked, B pulled and not acked; waiting {deadline + 1} s for B's "
            "lease to end")
        self.sleep(deadline + 1)
        if self.pull():
            raise NoGo(f"{case}: pull exited {self.rc} after the deadline")
        if self.nlines < 1:
            raise NoGo(f"{case}: B was pulled and not acked, and did not come back {deadline + 1} s later "
                       f"(the deadline is {deadline} s)")
        if self.data == msg_a:
            raise NoGo(f"{case}: A came back after it was acked")
        if self.nlines != 1 or self.data != msg_b:
            raise NoGo(f"{case}: after the deadline pull printed [{snip(self.out)}], want B ({msg_b}): a message "
                       "that was acked came back, or B did not alone")
        if self.call("ack", self.ackid):
            raise NoGo(f"{case}: ack exited {self.rc} on B's redelivery")
        self.want_nothing(case, "B's redelivery is acked")
        say("[eventbus-conformance] case 5 redelivery after the deadline, of the unacked message only: GO")


def judge(argv, env=None, verb=None, sleep=time.sleep):
    env = os.environ if env is None else env
    bus = env.get("EVENT_BUS", "")
    if not bus:
        raise NoGo("EVENT_BUS is not set; a profile sets it: run this via ./go eventbus-conformance")
    if verb is None:
        for v in ("publish", "pull", "ack"):
            if not os.path.isfile(f"adapters/{bus}/{v}.sh"):
                raise NoGo(f"adapters/{bus}/{v}.sh is missing: an event bus ships publish, pull and ack "
                           "(docs/adr/0019 §3)")
        verb = adapter(f"adapters/{bus}")
    deadline = env.get("CONFORMANCE_ACK_DEADLINE", "")
    if deadline and not re.fullmatch(r"[1-9][0-9]*", deadline):
        raise NoGo(f"CONFORMANCE_ACK_DEADLINE is [{deadline}], want a positive integer of seconds without a "
                   "leading zero: the adapter's ack deadline")
    suite = Suite(bus, verb, deadline, sleep)
    try:
        return suite.run()
    finally:
        suite.cleanup()


if __name__ == "__main__":
    raise SystemExit(main(judge))

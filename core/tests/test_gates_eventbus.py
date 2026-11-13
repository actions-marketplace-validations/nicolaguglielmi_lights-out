"""Tests for core/gates/eventbus.py, written from docs/adr/0019 §3,
docs/adr/0060 §2, §4 and gates/eventbus-conformance.sh's header, never from
the implementation.

A fair bus is GO (5 cases, 6 with a deadline); a bus broken in one
behaviour is a NO-GO naming its case; a message that is not the suite's is
never acked; the suite's own are acked on its way out.
"""

import contextlib
import io
import unittest

from core.gates import NoGo, eventbus


class FakeBus:
    """An EventBus in memory with a lease clock the suite's sleep advances."""

    def __init__(self, brk=None, foreign=None):
        self.brk = brk
        self.queue = []  # [id, data, leased_until]
        self.now = 0
        self.n = 0
        self.acked = []
        if foreign:
            self.queue.append(["f1", foreign, -1])

    def sleep(self, s):
        self.now += s

    def __call__(self, name, *args, data=None):
        if name == "publish":
            self.n += 1
            self.queue.append([f"id{self.n}", args[0], -1])
            return 0, "", ""
        if name == "pull":
            for m in self.queue:
                if self.brk != "no-lease" and m[2] >= self.now:
                    continue
                m[2] = self.now + 1
                text = m[1]
                if self.brk == "ascii":
                    text = text.encode("ascii", "replace").decode()
                ackid = m[0] + (" x" if self.brk == "spaced-id" else "")
                return 0, f"{ackid} {text}\n", ""
            return 0, "", ""
        if name == "ack":
            self.acked.append(args[0])
            if self.brk == "ack-fails":
                return 1, "", "refused"
            if self.brk == "ack-keeps":
                return 0, "", ""
            if self.brk == "ack-unleases":
                for m in self.queue:
                    if m[0] == args[0]:
                        m[2] = -1
                return 0, "", ""
            self.queue = [m for m in self.queue if m[0] != args[0]]
            return 0, "", ""
        raise AssertionError(name)


class EventBusTest(unittest.TestCase):
    def suite(self, bus, deadline=""):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            try:
                return "GO", eventbus.judge([], env={"EVENT_BUS": "fake", "CONFORMANCE_ACK_DEADLINE": deadline},
                                            verb=bus, sleep=bus.sleep)
            except NoGo as no:
                return "NO-GO", no.reason
            finally:
                self.err = err.getvalue()

    def test_fair_bus_without_and_with_deadline(self):
        bus = FakeBus()
        self.assertEqual(self.suite(bus),
                         ("GO", "fake, 5 cases; case 5 (redelivery) not run: CONFORMANCE_ACK_DEADLINE unset"))
        self.assertEqual(bus.queue, [])
        bus = FakeBus()
        self.assertEqual(self.suite(bus, "1"), ("GO", "fake, 6 cases"))
        self.assertEqual(bus.queue, [])
        self.assertIn("waiting 2 s", self.err)

    def test_each_break_names_its_case(self):
        for brk, case, deadline in (("ascii", "case1 roundtrip", ""), ("spaced-id", "case1 roundtrip", ""),
                                    ("no-lease", "case2 lease", ""), ("ack-fails", "case3 ack", ""),
                                    ("ack-unleases", "case3 ack", ""), ("ack-keeps", "case5 redelivery", "1")):
            with self.subTest(brk=brk):
                verdict, reason = self.suite(FakeBus(brk), deadline)
                self.assertEqual(verdict, "NO-GO", reason)
                self.assertTrue(reason.startswith(case + ":"), reason)

    def test_a_foreign_message_is_not_idle_and_not_acked(self):
        bus = FakeBus(foreign="someone else's")
        verdict, reason = self.suite(bus)
        self.assertTrue(reason.startswith("case0 idle: the bus is not idle"), reason)
        self.assertEqual(bus.acked, [])
        self.assertEqual(len(bus.queue), 1)

    def test_own_messages_are_acked_on_the_way_out(self):
        bus = FakeBus("ack-fails")
        self.suite(bus)
        self.assertTrue(bus.acked)
        self.assertTrue(all(a.startswith("id") for a in bus.acked))

    def test_deadline_must_be_a_positive_integer(self):
        for value in ("0", "01", "1.5", "x", "-2"):
            with self.subTest(value=value):
                self.assertIn("CONFORMANCE_ACK_DEADLINE is [", self.suite(FakeBus(), value)[1])

    def test_lines_of_counts_as_awk(self):
        self.assertEqual([eventbus.lines_of(t) for t in ("", "a", "a\n", "a\nb", "a\nb\n")], [0, 1, 1, 2, 2])


if __name__ == "__main__":
    unittest.main()

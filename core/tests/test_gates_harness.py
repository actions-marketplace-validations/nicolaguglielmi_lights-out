"""Tests for core/gates/harness.py, written from docs/adr/0041 §8, docs/adr/
0046 ("Conformance"), docs/adr/0073 ("Tests"), docs/adr/0084's amendment of
2026-11-16 (A1) and the suite's header, never from the implementation.

The suite's judging is pure functions over a case's files: each returns the
reason a case fails, or None. These tests plant those files, one defect at a
time, with no engine; gates/harness-conformance/proof.sh runs the whole
suite on a made-up harness.
"""

import os
import shutil
import tempfile
import unittest

from core.gates import NoGo, harness

MODEL = "fake-model-1"


def req(**kw):
    """One record of the stub's requests.jsonl: an agent-loop request by default."""
    r = {"kind": "generate", "tools": True, "requested": MODEL, "auth": "ok", "peer": "10.0.0.2",
         "sink": False, "path": "/v1/messages", "step": 0, "op": "write", "hooked": True,
         "reported_tokens": 1000, "last_result": "", "declared": []}
    r.update(kw)
    return r


class Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def write(self, rel, text):
        path = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)
        return path


class Discovery(Tmp):
    """A CLI harness is an adapters/<name>/ with run.sh, Containerfile and a pin
    (package-lock.json or release.env): discovered, never listed (ADR 0050 §2)."""

    def adapter(self, name, *files):
        for f in files:
            self.write("adapters/%s/%s" % (name, f), "x\n")

    def test_discovers_cli_harnesses_sorted_and_nothing_else(self):
        self.adapter("zed-cli", "run.sh", "Containerfile", "release.env")
        self.adapter("alpha-cli", "run.sh", "Containerfile", "package-lock.json")
        self.adapter("no-pin", "run.sh", "Containerfile")
        self.adapter("no-image", "run.sh", "package-lock.json")
        self.adapter("verbs", "deploy.sh")
        self.assertEqual(harness.discover(os.path.join(self.dir, "adapters")), ["alpha-cli", "zed-cli"])

    def test_select_one_or_refuse_naming_what_exists(self):
        self.assertEqual(harness.select(["a", "b"], ""), ["a", "b"])
        self.assertEqual(harness.select(["a", "b"], "b"), ["b"])
        with self.assertRaises(NoGo) as no:
            harness.select(["a", "b"], "c")
        self.assertIn("CONFORMANCE_HARNESS=c is not a CLI harness", no.exception.reason)
        self.assertIn("found: a b", no.exception.reason)
        with self.assertRaises(NoGo) as no:
            harness.select([], "")
        self.assertIn("no CLI harness found", no.exception.reason)

    def test_conf_get_reads_the_first_value_and_drops_one_pair_of_quotes(self):
        p = self.write("c.env", 'A="quoted"\nB=\'single\'\nC=plain=with=eq\nC=second\n# D=no\n')
        self.assertEqual(harness.conf_get(p, "A"), "quoted")
        self.assertEqual(harness.conf_get(p, "B"), "single")
        self.assertEqual(harness.conf_get(p, "C"), "plain=with=eq")
        self.assertEqual(harness.conf_get(p, "D"), "")
        self.assertEqual(harness.conf_get(os.path.join(self.dir, "missing"), "A"), "")

    def contract(self, text, thinking=True):
        self.write("adapters/h/conformance.env", text)
        if thinking:
            self.write("adapters/h/thinking.env", "X_LOW=low\n")
        return lambda: harness.check_contract("h", os.path.join(self.dir, "adapters"))

    def test_contract_shape_every_key_a_variable_name_and_thinking_env(self):
        good = "PROVIDER=p\nMODEL=m\nKEY_VAR=FAKE_KEY\nTHINKING_PATH=.a.b\nEGRESS=h:443\n"
        self.contract(good)()
        for key in ("PROVIDER", "MODEL", "KEY_VAR", "THINKING_PATH", "EGRESS"):
            text = "".join(line + "\n" for line in good.splitlines() if not line.startswith(key + "="))
            with self.assertRaises(NoGo) as no:
                self.contract(text)()
            self.assertIn("has no %s=" % key, no.exception.reason)
        for bad in ("lower", "9LIVES", "_X", "A-B"):
            with self.assertRaises(NoGo) as no:
                self.contract(good.replace("FAKE_KEY", bad))()
            self.assertIn("KEY_VAR is not a variable name", no.exception.reason)
        os.remove(os.path.join(self.dir, "adapters/h/thinking.env"))
        with self.assertRaises(NoGo) as no:
            self.contract(good, thinking=False)()
        self.assertIn("thinking.env is missing", no.exception.reason)
        os.remove(os.path.join(self.dir, "adapters/h/conformance.env"))
        with self.assertRaises(NoGo) as no:
            harness.check_contract("h", os.path.join(self.dir, "adapters"))
        self.assertIn("conformance.env is missing", no.exception.reason)

    def test_is_var_name(self):
        for ok in ("A", "GEMINI_API_KEY", "K9"):
            self.assertTrue(harness.is_var_name(ok), ok)
        for bad in ("", "a", "9A", "_A", "A B", "A-B"):
            self.assertFalse(harness.is_var_name(bad), bad)

    def test_with_mcp_sh_names_every_adapter_with_one_sorted(self):
        self.write("adapters/zz/mcp.sh", "x")
        self.write("adapters/aa/mcp.sh", "x")
        self.write("adapters/bb/run.sh", "x")
        self.assertEqual(harness.with_mcp_sh(os.path.join(self.dir, "adapters")), "aa zz")


class Pairing(unittest.TestCase):
    """Case 0 offers a harness the other provider; the refusal names a harness
    that fits it: a discovered one of that provider, else ADR 0041 §2's pairing.
    A provider is one row of PAIRING (ADR 0084 A1)."""

    def test_the_other_provider(self):
        self.assertEqual(harness.other_provider("gemini"), "anthropic")
        self.assertEqual(harness.other_provider("anthropic"), "gemini")
        self.assertEqual(harness.other_provider("openai"), "gemini")
        self.assertEqual(harness.other_provider("a-provider-with-no-row"), "gemini")

    def test_fitting_prefers_discovered_harnesses_of_the_other_provider(self):
        providers = {"x-cli": "gemini", "y-cli": "anthropic", "z-cli": "gemini"}
        self.assertEqual(harness.fitting("gemini", providers), ["x-cli", "z-cli"])

    def test_fitting_falls_back_to_the_pairing_table(self):
        self.assertEqual(harness.fitting("anthropic", {}), ["claude-code"])
        self.assertEqual(harness.fitting("openai", {}), ["codex"])
        self.assertEqual(harness.fitting("gemini", {}), ["gemini-cli"])

    def test_every_row_names_a_provider_and_a_harness(self):
        for provider, (other, fallback) in harness.PAIRING.items():
            self.assertIn(other, harness.PAIRING, provider)
            self.assertTrue(fallback, provider)

    def test_thinking_key(self):
        self.assertEqual(harness.thinking_key("anthropic", "medium"), "ANTHROPIC_MEDIUM")


class Cases(unittest.TestCase):
    """The cases are data: eleven in a fixed order, 9 and 10 before 8 because
    case 8 reads every case's artefacts; 10b and 10c where the harness has an
    mcp.sh, 10r where it does not (ADR 0073)."""

    def test_order_with_and_without_mcp(self):
        self.assertEqual(harness.case_ids(True), ["0", "1", "2", "3", "4", "5", "6", "7", "9", "10a", "10b", "10c", "8"])
        self.assertEqual(harness.case_ids(False), ["0", "1", "2", "3", "4", "5", "6", "7", "9", "10a", "10r", "8"])

    def test_case_8_reads_every_case_that_ran_a_harness(self):
        self.assertEqual(harness.read_by_case_8(True), ["1", "2", "3", "4", "5", "6", "7", "9", "10a", "10b", "10c"])
        self.assertEqual(harness.read_by_case_8(False), ["1", "2", "3", "4", "5", "6", "7", "9", "10a", "10r"])

    def test_case_ids_are_unique(self):
        ids = [c.id for c in harness.CASES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_the_valid_run_writes_one_file_then_ends_with_title_and_body(self):
        steps = harness.valid_steps()
        self.assertEqual(steps[0], {"op": "write", "path": "conformance.txt", "content": "conformance\n"})
        self.assertEqual(steps[1]["op"], "final")
        title, _, body = steps[1]["text"].partition("\n\n")
        self.assertEqual((title, body), (harness.FINAL_TITLE, harness.FINAL_BODY))

    def test_endless_calls_a_tool_on_every_request_and_ends_at_step_20(self):
        steps = harness.endless_steps()
        self.assertEqual(len(steps), 21)
        self.assertTrue(all(s["op"] == "shell" for s in steps[:20]))
        self.assertEqual(steps[20]["op"], "final")

    def test_probes_come_before_the_valid_run(self):
        probe = [{"op": "shell", "cmd": "git push origin HEAD:refs/heads/conformance"}]
        self.assertEqual(harness.steps_after(probe), probe + harness.valid_steps())

    def test_case_3_probes_every_secret_way_the_adr_names(self):
        steps = harness.SECRET_PROBES
        self.assertGreaterEqual(len(steps), 6)
        self.assertIn({"op": "jsread", "path": ".env"}, steps)
        self.assertIn({"op": "shell", "cmd": "printenv"}, steps)
        self.assertTrue(any(s["op"] == "grep" for s in steps))

    def test_limits_from_the_adr(self):
        role = {"max_turns": 50, "token_budget": 900000, "timeout_s": 900}
        self.assertEqual(harness.limits("5", role, 30), (2, 900000, 900))
        self.assertEqual(harness.limits("6", role, 30), (50, 2500, 900))
        self.assertEqual(harness.limits("7", role, 4), (50, 900000, 4))
        self.assertEqual(harness.limits("1", role, 30), (50, 900000, 900))


class Requests(unittest.TestCase):
    def test_auth_every_generate_and_count_request_carries_the_canary(self):
        ok = [req(), req(kind="count"), req(kind="other", auth="missing")]
        self.assertIsNone(harness.auth_flaw(ok, "FAKE_KEY"))
        flaw = harness.auth_flaw(ok + [req(kind="count", auth="wrong")], "FAKE_KEY")
        self.assertIn("1 request(s) did not carry the key canary", flaw)
        self.assertIn("FAKE_KEY", flaw)

    def test_peers_every_request_from_egress_none_to_the_sink(self):
        ip = "10.0.0.2"
        self.assertIsNone(harness.peers_flaw([req()], ip))
        self.assertIn("the harness never reached the scripted model", harness.peers_flaw([], ip))
        flaw = harness.peers_flaw([req(), req(peer="10.0.0.9"), req(peer=None), req(peer="10.0.0.9")], ip)
        self.assertIn("the stub saw requests from 10.0.0.9,no peer recorded, not from egress (10.0.0.2)", flaw)
        self.assertIn("1 request(s) reached conformance-sink or /exfil", harness.peers_flaw([req(sink=True)], ip))
        self.assertIn("1 request(s) reached conformance-sink or /exfil",
                      harness.peers_flaw([req(path="/a/exfil?x=1")], ip))

    def test_loop_requests_are_the_models_generate_requests_with_tools(self):
        reqs = [req(), req(tools=False), req(kind="count"), req(requested="other")]
        self.assertEqual(len(harness.loop(reqs, MODEL)), 1)

    def test_probe_count_and_cli_refusals(self):
        reqs = [req(step=0, op="shell"), req(step=1, op="read", last_result="denied by hook"),
                req(step=2, op="write", last_result="Path not in workspace"),
                req(step=3, op="final", hooked=False, last_result="written")]
        self.assertEqual(harness.probe_count(reqs, MODEL), 2)
        self.assertEqual(harness.cli_refused_count(reqs, MODEL), 1)
        self.assertIsNone(harness.silent_denials(reqs, MODEL))

    def test_a_probe_whose_next_result_is_no_denial_is_named(self):
        reqs = [req(step=0, op="shell"), req(step=1, op="read", last_result="file contents"),
                req(step=2, op="final", hooked=False, last_result="DENIED")]
        self.assertEqual(harness.silent_denials(reqs, MODEL),
                         "the next request's tool result does not carry a denial for step(s) 0")

    def test_probe_output_all_eight_ways_blocked(self):
        lines = "\n".join("egress-probe %s blocked" % c for c in "abcdefgh")
        self.assertIsNone(harness.probe_output_flaw([req(step=1, last_result=lines)], MODEL))
        self.assertIn("carries no tool result", harness.probe_output_flaw([req(step=0)], MODEL))
        opened = lines.replace("egress-probe e blocked", "egress-probe e open")
        self.assertIn("channel e is open", harness.probe_output_flaw([req(step=1, last_result=opened)], MODEL))
        cut = "\n".join("egress-probe %s blocked" % c for c in "abc")
        self.assertIn("the tool result has no 'egress-probe d' line",
                      harness.probe_output_flaw([req(step=1, last_result=cut)], MODEL))


class Egress(unittest.TestCase):
    PORT = 8089

    def good(self):
        return ["ALLOW conformance-model:8089", "DENY conformance-sink:8089", "DENY conformance-sink:8089",
                "DENY conformance-model:8090", "DENY example.com:443"]

    def test_decisions_are_read_whatever_the_engine_prefixes(self):
        log = "egress-1  | 2026 ALLOW conformance-model:8089 ok\r\negress-1  | DENY example.com:443\nnoise\n"
        self.assertEqual(harness.decisions(log), ["ALLOW conformance-model:8089", "DENY example.com:443"])

    def test_good_log(self):
        self.assertEqual(harness.egress_missing(self.good(), self.PORT), "")
        self.assertIsNone(harness.egress_flaw(self.good(), self.PORT))

    def test_missing_denials_and_the_sink_twice(self):
        d = self.good()
        d.remove("DENY example.com:443")
        d.remove("DENY conformance-sink:8089")
        self.assertEqual(harness.egress_missing(d, self.PORT), " example.com:443 conformance-sink:8089(twice)")
        self.assertIn("the proxy's log holds no DENY for: example.com:443", harness.egress_flaw(d, self.PORT))

    def test_another_host_taken(self):
        flaw = harness.egress_flaw(self.good() + ["ALLOW telemetry.example:8089"], self.PORT)
        self.assertIn("the proxy took a host other than the scripted model: ALLOW telemetry.example:8089", flaw)
        self.assertIsNone(harness.egress_flaw(self.good() + ["FAIL conformance-model:8089"], self.PORT))

    def test_no_allow_for_the_model(self):
        d = [x for x in self.good() if not x.startswith("ALLOW")]
        self.assertIn("has no ALLOW conformance-model:8089", harness.egress_flaw(d, self.PORT))


class Artefacts(Tmp):
    def test_hooks_log_lines(self):
        self.assertIn("missing or empty", harness.hooks_log_flaw(None))
        self.assertIn("missing or empty", harness.hooks_log_flaw(""))
        self.assertIsNone(harness.hooks_log_flaw("ALLOW Write -\nDENY Bash git push\n"))
        self.assertIn("hooks.log has a line that is not", harness.hooks_log_flaw("ALLOW Write -\nallowed\n"))
        self.assertIn("DENY Bash", harness.hooks_log_flaw("DENY Bash\n"))

    def run_json(self, **over):
        rj = {"harness": "h", "provider": "p", "model": MODEL + "-conformance", "thinking": "medium",
              "tokens": {"input": 2700, "output": 300, "total": 3000}, "input_sha256": "abc", "exit_code": 0,
              "turns": 3, "duration_s": 4, "endpoint": "http://conformance-model:8089/v1"}
        rj.update(over)
        return rj

    WANT = {"harness": "h", "provider": "p", "model": MODEL + "-conformance", "thinking": "medium",
            "tokens": 3000, "input_sha256": "abc", "endpoint": "http://conformance-model:8089"}

    def test_run_json_good(self):
        self.assertIsNone(harness.run_json_flaw(self.run_json(), self.WANT))

    def test_run_json_each_field(self):
        cases = [({"model": MODEL}, "run.json .model is '%s', want '%s-conformance'" % (MODEL, MODEL)),
                 ({"tokens": {"input": 1, "output": 1, "total": 6000}}, "run.json .tokens.total is '6000', want '3000'"),
                 ({"provider": None}, "run.json .provider is 'null', want 'p'"),
                 ({"exit_code": 1}, "run.json .exit_code is '1', want '0'"),
                 ({"turns": 0}, "run.json .turns is not a number of at least 1"),
                 ({"turns": "3"}, "run.json .turns is not a number of at least 1"),
                 ({"tokens": {"input": "1", "output": 2, "total": 3000}}, ".tokens.input and .tokens.output are not numbers"),
                 ({"duration_s": None}, "run.json .duration_s is not a number"),
                 ({"endpoint": "http://elsewhere"}, "run.json .endpoint is 'http://elsewhere', want the MODEL_BASE_URL")]
        for over, want in cases:
            self.assertIn(want, harness.run_json_flaw(self.run_json(**over), self.WANT), over)
        rj = self.run_json()
        del rj["endpoint"]
        self.assertIn("run.json .endpoint is 'absent'", harness.run_json_flaw(rj, self.WANT))

    def test_jq_text_is_jq_tostring(self):
        self.assertEqual([harness.jq_text(v) for v in (None, "s", 3, 3.0, 2.5, True, [1])],
                         ["null", "s", "3", "3", "2.5", "true", "[1]"])

    def test_strings_are_every_string_in_order(self):
        body = {"system": "S", "messages": [{"content": [{"text": "A"}, {"n": 1}]}, "B"]}
        self.assertEqual(list(harness.strings(body)), ["S", "A", "B"])


class Review(unittest.TestCase):
    """10a: the role prompt's first line, then the role file's marker, then the
    restated output contract, system fields before the conversation."""

    def test_order(self):
        body = {"messages": [{"content": "ticket MARK tail end"}], "system": "PROMPT line"}
        self.assertEqual(harness.review_positions(body, "PROMPT", "MARK", "tail"), (0, 19, 24))
        self.assertIsNone(harness.review_flaw((0, 19, 24), "PROMPT", "tail"))

    def test_rindex_of_the_tail(self):
        body = {"input": "tail PROMPT MARK tail"}
        self.assertEqual(harness.review_positions(body, "PROMPT", "MARK", "tail"), (5, 12, 17))

    def test_missing_parts_are_named(self):
        self.assertEqual(harness.review_positions({"contents": "x"}, "P", "M", "T"), (None, None, None))
        self.assertEqual(harness.review_positions(["not", "an", "object"], "P", "M", "T"), (None, None, None))
        flaw = harness.review_flaw((1, 2, None), "P", "the tail")
        self.assertEqual(flaw, "the first request lacks the restated output contract (the tail)")
        flaw = harness.review_flaw((None, None, 3), "P", "T")
        self.assertEqual(flaw, "the first request lacks the role prompt's first line (P) the role file's marker ")

    def test_out_of_order(self):
        self.assertIn("out of order (at 9, 2, 30)", harness.review_flaw((9, 2, 30), "P", "T"))


class Mcp(unittest.TestCase):
    def test_catalog_from_the_first_request(self):
        reqs = [req(declared=["Bash", "mcp__notes__search_notes"])]
        self.assertEqual(harness.mcp_catalog(reqs, MODEL),
                         ("Bash mcp__notes__search_notes", "the first request", "declares", "declare"))

    def test_catalog_in_code_mode_from_all_tools(self):
        reqs = [req(declared=["functions.exec"]),
                req(step=1, last_result="x\nALL_TOOLS: a b mcp__notes__search_notes\nmore")]
        self.assertEqual(harness.mcp_catalog(reqs, MODEL),
                         ("a b mcp__notes__search_notes", "exec's ALL_TOOLS", "lists", "list"))
        self.assertIsNone(harness.mcp_catalog([req(declared=["functions.exec"])], MODEL))

    def test_unlisted_tools_hidden_or_visible_and_denied(self):
        hooks = "DENY mcp__notes__count_notes mcp tool not named\n"
        cat = ("mcp__notes__search_notes", "the first request", "declares", "declare")
        self.assertIsNone(harness.unlisted_flaw("hidden", cat, ""))
        both = ("mcp__notes__search_notes mcp__notes__count_notes", "the first request", "declares", "declare")
        self.assertIn("run.json says the unnamed tools are hidden, and the first request declares count_notes",
                      harness.unlisted_flaw("hidden", both, ""))
        self.assertIsNone(harness.unlisted_flaw("visible-denied", both, hooks))
        self.assertIn("does not declare count_notes", harness.unlisted_flaw("visible-denied", cat, hooks))
        self.assertIn("hooks.log has no DENY for count_notes", harness.unlisted_flaw("visible-denied", both, ""))
        self.assertIn("run.json .mcp.unlisted is 'absent', want hidden or visible-denied",
                      harness.unlisted_flaw("absent", both, hooks))
        missing = ("Bash", "the first request", "declares", "declare")
        self.assertIn("the first request declares no tool ending with search_notes",
                      harness.unlisted_flaw("hidden", missing, ""))

    def test_refusal_of_a_harness_with_no_mcp_sh(self):
        line = "NO-GO: agents — h cannot give the dev-worker MCP servers (ADR 0073 §8); use one of: zz aa"
        self.assertIsNone(harness.refusal_flaw(1, line + "\n", "h", "aa zz"))
        self.assertIn("exited 0 for a harness with no mcp.sh, want 1", harness.refusal_flaw(0, line, "h", "aa zz"))
        self.assertIn("refusal is 2 lines on stdout, want one", harness.refusal_flaw(1, line + "\nmore\n", "h", "aa zz"))
        self.assertIn("is not ADR 0073 §8's line", harness.refusal_flaw(1, "NO-GO: agents — no\n", "h", "aa zz"))
        self.assertIn("the refusal lists 'aa h zz', want the harnesses that have adapters/<name>/mcp.sh: 'aa zz'",
                      harness.refusal_flaw(1, line + " h\n", "h", "aa zz"))


if __name__ == "__main__":
    unittest.main()

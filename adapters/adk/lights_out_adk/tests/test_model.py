# SPDX-License-Identifier: Apache-2.0
"""Tests for lights_out_adk.model (docs/adr/0040 §1, §2, §3), written from
the ADR, never from the implementation. Run by `ci/evals.sh` step (c):
`python3 -m unittest discover -s adapters/adk/lights_out_adk/tests -t
adapters/adk`.

The contract under test: the profile's MODEL_PROVIDER and MODEL pick the
model, the chosen provider's key alone is required, the thinking map is
adapters/adk/thinking.env, Gemini's level travels on ADK's planner,
Claude's and OpenAI's as LiteLLM's reasoning_effort with no planner, and
L0 never imports litellm.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from google.adk.models.google_llm import Gemini
from google.adk.planners.built_in_planner import BuiltInPlanner
from google.genai import types

from lights_out_adk import model, replay

REPO = Path(__file__).resolve().parents[4]
LEVELS = ("low", "medium", "high")
PROVIDERS = ("gemini", "anthropic", "openai")


def _env(**values):
    base = {
        "LIGHTS_OUT_ROOT": str(REPO),
        "AGENT_HARNESS": "gemini-cli",
        "MODEL_PROVIDER": "",
        "MODEL": "",
        "GEMINI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "OPENAI_API_KEY": "",
        "ADK_RECORD": "",
    }
    base.update(values)
    return mock.patch.dict(os.environ, base)


class ThinkingMapTest(unittest.TestCase):
    def test_every_provider_and_level_maps_one_to_one_today(self):
        # docs/adr/0040 §2 and Verified: no level is rewritten on any provider.
        for provider in PROVIDERS:
            for level in LEVELS:
                self.assertEqual(model.thinking_map(provider, level), level, (provider, level))

    def test_a_missing_line_names_the_file_and_the_key(self):
        with self.assertRaises(model.ThinkingMapMissing) as ctx:
            model.thinking_map("anthropic", "xhigh")
        self.assertIn("thinking.env", str(ctx.exception))
        self.assertIn("ANTHROPIC_XHIGH", str(ctx.exception))


class ProviderFromEnvTest(unittest.TestCase):
    def test_a_provider_outside_the_three_is_refused(self):
        with _env(MODEL_PROVIDER="vertex", MODEL="x", GEMINI_API_KEY="k"):
            with self.assertRaises(model.BadProvider) as ctx:
                model.provider_from_env()
        self.assertIn("MODEL_PROVIDER", str(ctx.exception))

    def test_an_empty_provider_is_refused(self):
        with _env(MODEL="gemini-3.8-flash", GEMINI_API_KEY="k"):
            with self.assertRaises(model.BadProvider):
                model.provider_from_env()

    def test_an_empty_model_is_refused(self):
        with _env(MODEL_PROVIDER="gemini", GEMINI_API_KEY="k"):
            with self.assertRaises(model.NoModel) as ctx:
                model.provider_from_env()
        self.assertIn("MODEL", str(ctx.exception))

    def test_only_the_chosen_providers_key_is_required(self):
        with _env(MODEL_PROVIDER="anthropic", MODEL="claude-sonnet-5-5", GEMINI_API_KEY="k"):
            with self.assertRaises(model.NoKey) as ctx:
                model.provider_from_env()
        self.assertIn("ANTHROPIC_API_KEY", str(ctx.exception))
        with _env(MODEL_PROVIDER="anthropic", MODEL="claude-sonnet-5-5", ANTHROPIC_API_KEY="k"):
            self.assertEqual(model.provider_from_env(), ("anthropic", "claude-sonnet-5-5", "k"))

    def test_the_placeholder_key_is_refused(self):
        with _env(MODEL_PROVIDER="openai", MODEL="gpt-6.1-sol", OPENAI_API_KEY="replace-me"):
            with self.assertRaises(model.NoKey) as ctx:
                model.provider_from_env()
        self.assertIn("OPENAI_API_KEY", str(ctx.exception))


class SelectModelTest(unittest.TestCase):
    def test_replay_returns_replay_llm_and_no_planner_whatever_the_provider_says(self):
        with _env(AGENT_HARNESS="replay", MODEL_PROVIDER="anthropic", MODEL="claude-sonnet-5-5"):
            got = model.select_model("ops-triage", "low")
            self.assertIsInstance(got, replay.ReplayLlm)
            self.assertIsNone(model.planner_for("low"))

    def test_l0_never_imports_litellm(self):
        # docs/adr/0040 §3: building the three agents at replay loads no
        # litellm. A subprocess, so another test's import cannot pollute it.
        code = (
            "import sys, agents.ops_triage, agents.product, agents.release; "
            "sys.exit(1 if 'litellm' in sys.modules else 0)"
        )
        env = dict(os.environ, PYTHONPATH=str(REPO / "adapters" / "adk"), LIGHTS_OUT_ROOT=str(REPO),
                   AGENT_HARNESS="replay", MODEL_PROVIDER="", MODEL="")
        proc = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_gemini_is_adks_own_model_with_the_planner(self):
        with _env(MODEL_PROVIDER="gemini", MODEL="gemini-3.8-flash", GEMINI_API_KEY="k"):
            got = model.select_model("ops-triage", "high")
            self.assertIsInstance(got, Gemini)
            self.assertEqual(got.model, "gemini-3.8-flash")
            planner = model.planner_for("high")
            self.assertIsInstance(planner, BuiltInPlanner)
            self.assertEqual(planner.thinking_config.thinking_level, types.ThinkingLevel.HIGH)

    def test_recording_wraps_the_real_model_and_knows_the_provider(self):
        with _env(MODEL_PROVIDER="gemini", MODEL="gemini-3.8-flash", GEMINI_API_KEY="k", ADK_RECORD="1"):
            got = model.select_model("ops-triage", "low")
            self.assertIsInstance(got, replay.RecordingLlm)
            self.assertEqual(got.provider, "gemini")
            self.assertEqual(got.model, "gemini-3.8-flash")
            self.assertIsInstance(got.inner, Gemini)

    def test_anthropic_and_openai_go_through_litellm_with_one_reasoning_setting(self):
        try:
            from google.adk.models.lite_llm import LiteLlm
        except ImportError:
            self.skipTest("litellm is not installed here; the workbench has it")
        cases = {
            "anthropic": ("claude-sonnet-5-5", "ANTHROPIC_API_KEY"),
            "openai": ("gpt-6.1-sol", "OPENAI_API_KEY"),
        }
        for provider, (model_id, key_var) in cases.items():
            for level in LEVELS:
                with _env(MODEL_PROVIDER=provider, MODEL=model_id, **{key_var: "k"}):
                    got = model.select_model("ops-triage", level)
                    self.assertIsInstance(got, LiteLlm)
                    self.assertEqual(got.model, f"{provider}/{model_id}")
                    args = getattr(got, "_additional_args")
                    self.assertEqual(args.get("reasoning_effort"), model.thinking_map(provider, level))
                    self.assertEqual(args.get("api_key"), "k")
                    # Exactly one reasoning setting travels: no planner beside it.
                    self.assertIsNone(model.planner_for(level))
                with _env(MODEL_PROVIDER=provider, MODEL=model_id, ADK_RECORD="1", **{key_var: "k"}):
                    got = model.select_model("ops-triage", "low")
                    self.assertIsInstance(got, replay.RecordingLlm)
                    self.assertEqual(got.provider, provider)
                    self.assertIsInstance(got.inner, LiteLlm)


class LiteLlmTransformationTest(unittest.TestCase):
    """docs/adr/0040 §2: the value each vendor receives for each level,
    built offline from litellm's own request transformation."""

    def setUp(self):
        try:
            import litellm  # noqa: F401
        except ImportError:
            self.skipTest("litellm is not installed here; the workbench has it")

    def test_anthropic_receives_adaptive_thinking_and_the_effort(self):
        from litellm.llms.anthropic.chat.transformation import AnthropicConfig

        for level in LEVELS:
            got = AnthropicConfig().map_openai_params(
                non_default_params={"reasoning_effort": model.thinking_map("anthropic", level)},
                optional_params={}, model="claude-sonnet-5-5", drop_params=False,
            )
            self.assertEqual(
                got,
                {"thinking": {"type": "adaptive", "display": "summarized"}, "output_config": {"effort": level}},
                level,
            )

    def test_openai_receives_the_effort_unchanged(self):
        import litellm

        config = litellm.utils.ProviderConfigManager.get_provider_chat_config(
            model="gpt-6.1-sol", provider=litellm.LlmProviders.OPENAI
        )
        for level in LEVELS:
            got = config.map_openai_params(
                non_default_params={"reasoning_effort": model.thinking_map("openai", level)},
                optional_params={}, model="gpt-6.1-sol", drop_params=False,
            )
            self.assertEqual(got, {"reasoning_effort": level}, level)


if __name__ == "__main__":
    unittest.main()

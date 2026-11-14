"""The L0 model (docs/adr/0020 §2): a BaseLlm that replays LlmResponses
recorded once at L1, keyed by the first user message, indexed by how many
model turns the request already carries — stateless, re-runnable, and
loud when the recording is missing or exhausted. RecordingLlm is the
other half: it wraps the real model, whatever BaseLlm it is (Gemini or
LiteLlm, docs/adr/0040 §3), and writes the same file, provider included."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path
from typing import AsyncGenerator, Optional

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse

RECORD_COMMAND = "./go record-evals PROFILE=l1"
_WARNED: set[str] = set()


class NoRecording(RuntimeError):
    pass


class RecordingExhausted(RuntimeError):
    pass


def canonical(text: str) -> str:
    """JSON inputs are compared by content, not by whitespace: a file and an
    eval case with the same document share one key."""
    try:
        return json.dumps(json.loads(text), sort_keys=True, indent=2)
    except (ValueError, TypeError):
        return text.strip()


def key_for(text: str) -> str:
    return hashlib.sha256(canonical(text).encode()).hexdigest()


def first_user_text(llm_request: LlmRequest) -> str:
    for content in llm_request.contents or []:
        if content.role == "user":
            for part in content.parts or []:
                if part.text:
                    return part.text
    raise ValueError("the request carries no user text to key the replay on")


def model_turns(llm_request: LlmRequest) -> int:
    return sum(1 for c in llm_request.contents or [] if c.role == "model")


def fixture_path(fixtures_dir: str, role: str, key: str) -> Path:
    return Path(fixtures_dir) / role / f"{key}.json"


class ReplayLlm(BaseLlm):
    model: str = "replay"
    role: str
    fixtures_dir: str
    instruction_sha256: Optional[str] = None
    # The last recording replayed: run.json reports its provider and model
    # under `recorded` (docs/adr/0040 §3).
    recorded: Optional[dict] = None

    @classmethod
    def supported_models(cls) -> list[str]:
        return ["replay"]

    def load(self, key: str, input_text: str) -> dict:
        path = fixture_path(self.fixtures_dir, self.role, key)
        if not path.is_file():
            raise NoRecording(
                f"no recorded responses for role {self.role} at {path} "
                f"(input starts: {input_text.strip()[:80]!r}); record them with {RECORD_COMMAND}"
            )
        recording = json.loads(path.read_text())
        self.recorded = {"provider": recording.get("provider"), "model": recording.get("model")}
        recorded_under = recording.get("instruction_sha256")
        if (
            self.instruction_sha256
            and recorded_under
            and recorded_under != self.instruction_sha256
            and key not in _WARNED
        ):
            _WARNED.add(key)
            print(
                f"replay: {path.name} for role {self.role} was recorded under a different "
                f"prompt.md (recorded {recorded_under[:12]}, current {self.instruction_sha256[:12]}); "
                f"replaying anyway, re-record with {RECORD_COMMAND}",
                file=sys.stderr,
            )
        return recording

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        input_text = first_user_text(llm_request)
        key = key_for(input_text)
        recording = self.load(key, input_text)
        index = model_turns(llm_request)
        responses = recording.get("responses", [])
        if index >= len(responses):
            raise RecordingExhausted(
                f"role {self.role}, recording {key}: call {index} requested but only "
                f"{len(responses)} recorded; re-record with {RECORD_COMMAND}"
            )
        yield LlmResponse.model_validate(responses[index])


class RecordingLlm(BaseLlm):
    """Wraps the real model at L1 (ADK_RECORD=1) and writes what it answered,
    call by call, to the file ReplayLlm reads. With extend (ADK_RECORD=extend,
    docs/adr/0090 §4), a turn the recording already holds is replayed, not
    asked again: an interview the tower re-runs on every answer pays each
    turn once, and the person answers the question the recording holds."""

    model: str
    provider: str
    role: str
    fixtures_dir: str
    inner: BaseLlm
    instruction_sha256: Optional[str] = None
    extend: bool = False

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        input_text = first_user_text(llm_request)
        key = key_for(input_text)
        index = model_turns(llm_request)
        path = fixture_path(self.fixtures_dir, self.role, key)
        if self.extend and path.is_file():
            held = json.loads(path.read_text()).get("responses", [])
            if index < len(held):
                yield LlmResponse.model_validate(held[index])
                return
        if (index == 0 and not self.extend) or not path.is_file():
            recording = {
                "input": canonical(input_text),
                "instruction_sha256": self.instruction_sha256,
                "model": self.inner.model,
                "provider": self.provider,
                "recorded_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "responses": [],
            }
        else:
            recording = json.loads(path.read_text())
        final: Optional[LlmResponse] = None
        async for response in self.inner.generate_content_async(llm_request, stream=False):
            final = response
        if final is None:
            raise RuntimeError(f"role {self.role}: the model returned nothing")
        responses = recording["responses"]
        del responses[index:]
        responses.append(final.model_dump(exclude_none=True, mode="json"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(recording, indent=2, sort_keys=True) + "\n")
        yield final

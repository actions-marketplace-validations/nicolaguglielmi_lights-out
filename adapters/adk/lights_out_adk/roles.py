"""A role is a directory under roles/ (plan §6): prompt.md is the agent's
instruction, role.env its budgets. Agent directories are snake_case (the
ADK loader's rule, docs/adr/0020 §1); role directories are kebab-case."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


def repo_root() -> Path:
    override = os.environ.get("LIGHTS_OUT_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3]


def role_name(agent_dir_name: str) -> str:
    return agent_dir_name.replace("_", "-")


@dataclass(frozen=True)
class Role:
    name: str
    instruction: str
    thinking: str
    timeout_s: int

    @property
    def instruction_sha256(self) -> str:
        return hashlib.sha256(self.instruction.encode()).hexdigest()


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def load_role(name: str, prompt_file: str = "prompt.md") -> Role:
    """The role's instruction is roles/<name>/<prompt_file>: prompt.md, or
    another task's prompt of the same role (docs/adr/0090 §3)."""
    d = repo_root() / "roles" / name
    prompt = d / prompt_file
    env = d / "role.env"
    if not prompt.is_file():
        raise FileNotFoundError(f"roles/{name}/{prompt_file} not found")
    if not env.is_file():
        raise FileNotFoundError(f"roles/{name}/role.env not found")
    values = read_env(env)
    thinking = values.get("THINKING", "").lower()
    if thinking not in ("low", "medium", "high"):
        raise ValueError(f"roles/{name}/role.env: THINKING must be low, medium or high, got {thinking!r}")
    return Role(
        name=name,
        instruction=prompt.read_text(),
        thinking=thinking,
        timeout_s=int(values.get("TIMEOUT_S", "900")),
    )

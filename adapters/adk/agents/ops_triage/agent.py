"""The ops-triage role (plan §5, §8 step 7): an alert in, an incident with
ordered hypotheses and a proposal out. Three tools, none of which touches
anything: the proposal is a proposal (docs/adr/0020 §3)."""

from typing import Any

from lights_out_adk.agent import build


def file_incident(title: str, hypotheses: list[dict[str, Any]]) -> dict:
    """Open the incident. `hypotheses` is the ordered list of causes, most
    likely first: each item has `rank` (1 = most likely), `cause` (one
    sentence) and `evidence` (which number in the alert supports it, or
    which number contradicts the headline)."""
    return {"status": "recorded", "title": title, "hypotheses": hypotheses}


def propose_rollback(version: str, reason: str) -> dict:
    """Propose rolling back `version` — the canary named in the alert — when
    the numbers show the canary itself is failing and the stable is not.
    This proposes; a human or the release controller acts."""
    return {"status": "recorded", "action": "rollback", "version": version, "reason": reason}


def propose_hold(reason: str) -> dict:
    """Propose holding: no rollback, because the numbers do not show the
    canary as the cause (the stable fails too, or the canary has no
    traffic to judge). Say what to look at instead."""
    return {"status": "recorded", "action": "hold", "reason": reason}


root_agent = build("ops-triage", [file_incident, propose_rollback, propose_hold])

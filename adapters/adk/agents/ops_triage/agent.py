"""The ops-triage role (plan §5, §8 step 7): an alert in, an incident with
ordered hypotheses and a proposal out; an incident document in, a post
mortem out (docs/adr/0044 §4). Four tools, none of which touches anything:
the proposal is a proposal, the post mortem is filed by core (docs/adr/0020
§3)."""

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


def file_postmortem(
    title: str,
    timeline: list[dict[str, Any]],
    causes: list[dict[str, Any]],
    actions: list[dict[str, Any]],
) -> dict:
    """File the post mortem of the incident document you were given.
    `timeline` is oldest first: each item has `event` (one sentence) and
    `anchor`, one id the document holds (`release:<version>`,
    `release:<version>@<pct>`, `pr:<n>`, `merge:<sha>`, `ticket:<id>`,
    `log:<n>`, `alert:<n>`). `causes` are the contributing causes: each
    has `cause` and `evidence`. `actions` are the fixes: each has `title`,
    `problem` and `acceptance`, one per cause worth fixing. Write no
    times: the document has none to check them against."""
    return {"status": "recorded", "title": title, "timeline": timeline, "causes": causes, "actions": actions}


root_agent = build("ops-triage", [file_incident, file_postmortem, propose_rollback, propose_hold])

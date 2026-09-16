"""The release role (plan §5): composes the promotion brief a human reads
before go-for-launch. Two tools: the brief, or the reason there is none
(docs/adr/0020 §3, §4)."""

from lights_out_adk.agent import build


def submit_brief(version: str, brief: str) -> dict:
    """Submit the promotion brief for `version`, the canary held at 25%.
    `brief` is markdown: what is being promoted (version, stable it
    replaces), each stage with its verdict and the numbers that produced
    it, what remains unverified, and one line recommending GO or NO-GO."""
    return {"status": "recorded", "version": version, "brief": brief}


def decline_brief(reason: str) -> dict:
    """There is nothing to promote: the record is not a held canary (it was
    rolled back, or never reached the hold). Say why."""
    return {"status": "recorded", "reason": reason}


root_agent = build("release", [submit_brief, decline_brief])

"""The product role (plan §5): checks a ticket's acceptance criteria and
asks when they are missing. Two decisions, two tools (docs/adr/0020 §3)."""

from lights_out_adk.agent import build


def ask_product_owner(question: str) -> dict:
    """Ask the product owner the one question that blocks the ticket: what is
    missing or ambiguous in its acceptance criteria. Call this instead of
    guessing; the answer arrives as the next message."""
    return {"status": "recorded", "question": question}


def confirm_acceptance(criteria: list[str]) -> dict:
    """Confirm the ticket is ready for a developer: pass the acceptance
    criteria, one Given/When/Then string each, as they will be tested."""
    return {"status": "recorded", "criteria": criteria}


root_agent = build("product", [ask_product_owner, confirm_acceptance])

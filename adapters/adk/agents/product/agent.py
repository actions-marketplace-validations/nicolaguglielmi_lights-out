"""The product role (plan §5): checks a ticket's acceptance criteria and
asks when they are missing (docs/adr/0020 §3); in an intake, interviews
the client and proposes the tickets (docs/adr/0090 §2). Three decisions,
three tools."""

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


def propose_ticket(title: str, problem: str, criteria: list[str], feature: str, priority: str) -> dict:
    """Propose one ticket of an intake request; call it once per ticket.
    title: one line. problem: what the client cannot do today and why it
    matters. criteria: one Given/When/Then string each, as they will be
    tested. feature: a slug of lowercase letters and digits joined by
    hyphens, the same for tickets of one feature, or empty. priority: P0
    (most urgent) to P3, or empty."""
    return {"status": "recorded", "title": title}


root_agent = build("product", [ask_product_owner, confirm_acceptance, propose_ticket])

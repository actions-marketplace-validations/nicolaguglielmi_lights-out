# test-reviewer

Runs the AgentHarness port defined in docs/adr/0017 — the same port
dev-worker uses — but has no prompt yet: nobody has run it. M6's control
plane decides when the test-reviewer role runs; its prompt is written
against that first real run, not guessed here (docs/adr/0017 §7: an
unexercised prompt is a hypothesis, and the harness would rewrite it
against a real run anyway).

`role.env` sets this role's thinking level today (plan §5's table):
`high`, "deve trovare quello che l'autore non ha visto" — it has to find
what the author did not see.

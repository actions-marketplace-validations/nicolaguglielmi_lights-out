# test-reviewer — the review milestone after M8 (M9 proposed)

Runs the AgentHarness port defined in docs/adr/0017 — the same port
dev-worker uses — but has no prompt yet: nobody has run it. The review milestone after M8 (M9 proposed) owns the
first real run of the test-reviewer role; its prompt is written against that
first real run, not guessed here. At M7 the tower runs but the test-reviewer
role does not (review is terminal, ADR 0019 §8; re-dated by ADR 0020 §9 to
its own milestone after M8, none of it needing GCP: it needs a medium-risk
PR run at L1, the same `record` work as the dev-worker budget).

`role.env` sets this role's thinking level today (plan §5's table):
`high`, "deve trovare quello che l'autore non ha visto" — it has to find
what the author did not see.

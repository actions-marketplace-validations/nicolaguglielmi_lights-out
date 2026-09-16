# architect — M8

Runs the AgentHarness port defined in docs/adr/0017 — the same port
dev-worker uses — but has no prompt yet: nobody has run it. M8 owns the
first real run of the architect role (structural decisions, ADRs, plan §5);
its prompt is written against that first real run, not guessed here. At M7
the tower runs but the architect role does not (review is terminal, ADR 0019 §8;
re-dated to M8 by ADR 0020 §9: it needs a medium-risk PR run at L1, the
same `record` work as the dev-worker budget).

`role.env` sets this role's thinking level today (plan §5's table):
`high`, "poche chiamate, alto impatto" — few calls, high impact.

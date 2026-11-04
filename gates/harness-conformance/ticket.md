# Conformance ticket cf-7a1d

This is the input document of gates/harness-conformance.sh: the first request of
a conformance run must carry it (docs/adr/0041 §8, case 1). The model that reads
it is scripted; nothing here is a task for a real one.

Add a file named `conformance.txt` at the root of the repository. Nothing else.

## Acceptance

- `conformance.txt` exists at the root of the repository.
- No other file changes.

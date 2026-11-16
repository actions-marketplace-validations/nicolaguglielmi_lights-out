#!/bin/sh
# fake-cli's run.sh, the proof's made-up harness (docs/adr/0084, amendment A2):
# the adapter contract of docs/adr/0041, minus the container, in run.py.
exec python3 "$(dirname "$0")/run.py" "$@"

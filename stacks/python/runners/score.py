"""Score a cosmic-ray session dump (docs/adr/0015 #3, docs/adr/0042 §1, stdlib only).

The python stack's scorer, copied by `./go init` beside mutation.sh, which
pipes `cosmic-ray dump` into it; the same scorer as workloads/minimal's.

Reads `cosmic-ray dump SESSION_FILE` output on stdin: one JSON array
`[work_item, result_or_null]` per line (cosmic_ray.cli:dump, 8.7.0). Prints
one JSON line to stdout: `{"total": N, "killed": K, "survived": S, "score":
<killed/total, or null when total is 0>}`.

Population = killed + survived, over mutants on the changed lines (the
session was already scoped and filtered by mutation.sh before
`exec` ran). Every mutant not in {killed, survived} is excluded from the
population entirely:

- "incompetent" (cosmic_ray.work_item.TestOutcome.INCOMPETENT): the mutated
  code no longer runs at all (raised before the test suite could observe
  it) -- says nothing about the tests.
- a null `test_outcome`: either skipped (cr-filter-lines, cr-filter-
  operators or cr-filter-pragma marked it WorkerOutcome.SKIPPED before
  `exec` ever ran it) or WorkerOutcome.NO_TEST (cosmic-ray could not apply
  that occurrence of the operator at all). Neither is a signal about the
  tests either.

Timeouts need no special case: read from cosmic_ray/testing.py in the
installed 8.7.0 package, `run_tests()` already reports a timed-out run as
`(TestOutcome.KILLED, "timeout")` -- by the time a result reaches this
script, a timeout already *is* "killed" (the mutant changed behaviour
observably: the suite stopped finishing in time).

Every survivor is printed to stderr as `SURVIVOR file:line operator` (one
line per mutation in the work item -- almost always exactly one, since
mutation.sh only ever generates single-mutation sessions): the
`SURVIVOR ` prefix is what the mutation gate greps for to pass the list
through to its own stderr, and it is what a
worker needs to write the missing test.
"""

import json
import sys


def main() -> int:
    killed = 0
    survived = 0
    excluded = 0
    survivor_lines: list[str] = []

    for lineno, raw_line in enumerate(sys.stdin, start=1):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            work_item, result = json.loads(raw_line)
        except (ValueError, TypeError) as exc:
            print(f"score: malformed dump line {lineno}: {exc}", file=sys.stderr)
            return 1

        test_outcome = None if result is None else result.get("test_outcome")

        if test_outcome == "killed":
            killed += 1
        elif test_outcome == "survived":
            survived += 1
            for mutation in work_item.get("mutations", ()):
                start_line = mutation["start_pos"][0]
                survivor_lines.append(
                    f"SURVIVOR {mutation['module_path']}:{start_line} {mutation['operator_name']}"
                )
        else:
            # None (skipped or no-test) or "incompetent": not in the population.
            excluded += 1

    total = killed + survived
    score = (killed / total) if total > 0 else None

    print(json.dumps({"total": total, "killed": killed, "survived": survived, "score": score}))

    for line in survivor_lines:
        print(line, file=sys.stderr)
    print(
        f"score: {excluded} mutant(s) excluded from the population "
        "(skipped, no-test, or incompetent)",
        file=sys.stderr,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())

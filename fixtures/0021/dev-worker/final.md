Add a one-line size report of the metrics page

meetups/report.py's metrics_report() returns the metrics page's size in
bytes and lines, for the ops runbook; a test checks both numbers on a
page of known size.

Hand-written L0 fixture for ticket 0021 (docs/adr/0056 §7): no model
wrote this change.

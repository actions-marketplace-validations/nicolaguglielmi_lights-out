Test that a meetup capacity below one is refused

Written from ticket 0012's acceptance criteria alone, through the HTTP
API: capacity 0 and -1 answer 422 and list nothing; capacity 1 answers
201 with capacity 1.

Hand-written L0 fixture for ticket 0012's tests member (docs/adr/0036
§7): no model wrote this change.

Post the venue the contract answers 404 for

The unknown-venue test posted "Nowhere, Atlantis", the contract's
existing 200 [] example, so it passed with or without the 404 branch: the
mutants on geocoder_client.py's new lines survived. It now posts
"Unknown Venue, Nowhere", the example this change adds, whose 404 body is
a trap a client that reads it would turn into coordinates.

Hand-written L0 fixture for ticket 0013's attempt 2 (docs/adr/0038 §10):
the answer to attempt 1's mutation verdict. No model wrote this change.

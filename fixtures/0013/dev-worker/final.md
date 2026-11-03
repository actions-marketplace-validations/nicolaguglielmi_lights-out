Treat a 404 from the geocoder as no result

geocoder_client.geocode() only handled a status >= 500, so the fake's 404
for an unknown venue crashed on response.json() and POST /api/meetups
answered 500. A 404 now returns (None, None): the meetup is created with
201 and null coordinates, as a real Nominatim's 200 []. The contract gets
a 404 example; test_meetups.py posts an unknown venue and asserts the 201
and the null coordinates.

Hand-written L0 fixture for ticket 0013's attempt 1 (docs/adr/0038 §10):
no model wrote this change.

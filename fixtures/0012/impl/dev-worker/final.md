Refuse a meetup capacity below one with 422

POST /api/meetups validated capacity only as an integer, so 0 or a
negative number created a meetup that answered 409 "meetup is full" to
its first registration. MeetupCreateRequest now requires capacity >= 1;
FastAPI answers 422 before anything is created. The README row for the
route says so.

Hand-written L0 fixture for ticket 0012's impl member (docs/adr/0036 §7):
no model wrote this change.

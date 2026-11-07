Name the app's database connections

Every connection get_db() opens now carries application_name=meetups,
so Postgres's pg_stat_activity tells the app's sessions from the
migrations' and the tests'.

Hand-written L0 fixture for ticket 0022 (docs/adr/0056 §7): no model
wrote this change.

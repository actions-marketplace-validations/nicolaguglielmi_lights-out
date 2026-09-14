-- Contract: drop the old text column, promote the new one (docs/adr/0008).
ALTER TABLE meetups DROP COLUMN starts_at;
ALTER TABLE meetups RENAME COLUMN starts_at_ts TO starts_at;
ALTER TABLE meetups ALTER COLUMN starts_at SET NOT NULL;

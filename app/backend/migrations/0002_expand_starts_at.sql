-- Expand: add the new column, backfill it, keep the old one so readers on
-- the previous revision still work (docs/adr/0008).
ALTER TABLE meetups ADD COLUMN starts_at_ts timestamptz;
UPDATE meetups SET starts_at_ts = starts_at::timestamptz;

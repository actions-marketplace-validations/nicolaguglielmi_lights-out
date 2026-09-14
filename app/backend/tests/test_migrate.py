import os

import psycopg
import pytest

from meetups import migrate

TEST_DATABASE_URL = os.environ["TEST_DATABASE_URL"]


def _applied_names() -> set[str]:
    with psycopg.connect(TEST_DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute("SELECT name FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def test_running_migrations_twice_is_a_noop():
    before = _applied_names()
    migrate.run(TEST_DATABASE_URL)
    assert _applied_names() == before


def test_broken_migration_leaves_schema_migrations_unchanged(tmp_path, monkeypatch):
    (tmp_path / "0000_broken.sql").write_text("this is not valid sql at all;")
    monkeypatch.setattr(migrate, "MIGRATIONS_DIR", tmp_path)

    before = _applied_names()
    with pytest.raises(SystemExit):
        migrate.run(TEST_DATABASE_URL)
    assert _applied_names() == before


def test_real_migrations_leave_starts_at_as_not_null_timestamptz():
    with psycopg.connect(TEST_DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_name = 'meetups' AND column_name = 'starts_at'"
        )
        data_type, is_nullable = cur.fetchone()
    assert data_type == "timestamp with time zone"
    assert is_nullable == "NO"

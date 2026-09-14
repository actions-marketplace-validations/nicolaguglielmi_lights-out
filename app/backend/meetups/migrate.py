"""Forward-only SQL migration runner (docs/adr/0008). Usage: python -m meetups.migrate"""

import os
import sys
import time
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
ADVISORY_LOCK_KEY = 891001
CONNECT_RETRY_SECONDS = 60


def _connect_with_retry(dsn: str) -> psycopg.Connection:
    deadline = time.monotonic() + CONNECT_RETRY_SECONDS
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return psycopg.connect(dsn)
        except psycopg.OperationalError as exc:
            last_error = exc
            time.sleep(1)
    raise SystemExit(f"could not connect after {CONNECT_RETRY_SECONDS}s: {last_error}")


def _applied_names(cur: psycopg.Cursor) -> set[str]:
    cur.execute("SELECT to_regclass('public.schema_migrations') IS NOT NULL")
    (exists,) = cur.fetchone()
    if not exists:
        return set()
    cur.execute("SELECT name FROM schema_migrations")
    return {row[0] for row in cur.fetchall()}


def run(dsn: str) -> None:
    conn = _connect_with_retry(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (ADVISORY_LOCK_KEY,))
            applied = _applied_names(cur)
            pending = sorted(
                p for p in MIGRATIONS_DIR.glob("*.sql") if p.stem not in applied
            )
            for path in pending:
                try:
                    cur.execute(path.read_text())
                    cur.execute(
                        "INSERT INTO schema_migrations (name) VALUES (%s)",
                        (path.stem,),
                    )
                    conn.commit()
                except psycopg.Error as exc:
                    conn.rollback()
                    raise SystemExit(f"{path.name}: {exc}") from exc
                print(f"applied {path.name}", file=sys.stderr)
            cur.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_KEY,))
            conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    run(os.environ["DATABASE_URL"])

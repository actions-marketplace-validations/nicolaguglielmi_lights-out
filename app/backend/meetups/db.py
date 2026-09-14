"""One psycopg connection per request, no pool (docs/adr/0005)."""

import os
from collections.abc import Iterator

import psycopg


def get_db() -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        yield conn
    finally:
        conn.close()

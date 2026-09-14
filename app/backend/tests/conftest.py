import os
import shutil
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

# FlagdProvider() reads FLAGD_RESOLVER/FLAGD_OFFLINE_FLAG_SOURCE_PATH once, at
# import time, when `meetups.flags` (imported by `meetups.app`) first loads.
# These must be set, and the flag file must already exist, before any test
# module imports `meetups.app` — conftest.py is always imported first. The
# copy is writable so test_flags.py can flip it without touching the repo.
_REAL_FLAGS_FILE = Path(__file__).resolve().parent.parent / "flags" / "flags.json"
_flag_tmp_dir = tempfile.mkdtemp(prefix="waitlist-flag-")
WAITLIST_FLAG_FILE = Path(_flag_tmp_dir) / "flags.json"
shutil.copy(_REAL_FLAGS_FILE, WAITLIST_FLAG_FILE)

os.environ["FLAGD_RESOLVER"] = "file"
os.environ["FLAGD_OFFLINE_FLAG_SOURCE_PATH"] = str(WAITLIST_FLAG_FILE)
# openfeature-provider-flagd 0.5.2 reuses FLAGD_DEADLINE_MS (not
# FLAGD_OFFLINE_POLL_MS) as the file-watcher poll interval; set it low so
# test_flags.py doesn't have to wait 5s for a flip to be picked up.
os.environ["FLAGD_DEADLINE_MS"] = "50"

POSTGRES_MAINTENANCE_URL = os.environ["POSTGRES_MAINTENANCE_URL"]
TEST_DATABASE_URL = os.environ["TEST_DATABASE_URL"]

APP_TABLES = ("registrations", "meetups", "sessions", "users")


@pytest.fixture(scope="session", autouse=True)
def _migrated_database() -> None:
    conn = psycopg.connect(POSTGRES_MAINTENANCE_URL, autocommit=True)
    try:
        with conn.cursor() as cur:
            try:
                cur.execute("CREATE DATABASE meetups_test")
            except psycopg.errors.DuplicateDatabase:
                pass
    finally:
        conn.close()

    from meetups.migrate import run

    run(TEST_DATABASE_URL)


@pytest.fixture(autouse=True)
def _clean_database(_migrated_database: None) -> Iterator[None]:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    conn = psycopg.connect(TEST_DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE " + ", ".join(APP_TABLES) + " RESTART IDENTITY CASCADE"
            )
        conn.commit()
    finally:
        conn.close()
    yield


@pytest.fixture
def client() -> TestClient:
    from meetups.app import app

    return TestClient(app)


@pytest.fixture
def geocoder_server() -> Iterator[str]:
    from fakes.geocoder.server import create_server

    server = create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    os.environ["GEOCODER_URL"] = base_url
    yield base_url
    server.shutdown()
    server.server_close()

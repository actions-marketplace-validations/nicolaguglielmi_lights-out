"""Test config for the minimal workload. Mirrors app/backend/tests/
conftest.py's flagd override exactly, minus everything Postgres/geocoder-
related (docs/adr/0030 §6: this workload has neither).
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# FlagdProvider() reads FLAGD_RESOLVER/FLAGD_OFFLINE_FLAG_SOURCE_PATH once, at
# import time, when `minimal.app` first loads. These must be set, and the
# flag file must already exist, before any test module imports `minimal.app`
# -- conftest.py is always imported first. The copy is writable so a test
# flipping `outage` never touches the committed file.
_REAL_FLAGS_FILE = Path(__file__).resolve().parent.parent / ".lights-out" / "flags" / "flags.json"
_flag_tmp_dir = tempfile.mkdtemp(prefix="outage-flag-")
OUTAGE_FLAG_FILE = Path(_flag_tmp_dir) / "flags.json"
shutil.copy(_REAL_FLAGS_FILE, OUTAGE_FLAG_FILE)

os.environ["FLAGD_RESOLVER"] = "file"
os.environ["FLAGD_OFFLINE_FLAG_SOURCE_PATH"] = str(OUTAGE_FLAG_FILE)
# openfeature-provider-flagd 0.5.2 reuses FLAGD_DEADLINE_MS (not
# FLAGD_OFFLINE_POLL_MS) as the file-watcher poll interval; set it low so
# test_app.py doesn't have to wait 5s for a flip to be picked up.
os.environ["FLAGD_DEADLINE_MS"] = "50"


@pytest.fixture
def client() -> TestClient:
    from minimal.app import app

    return TestClient(app)

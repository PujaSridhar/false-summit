"""Test configuration.

Force the offline, deterministic path BEFORE any backend module is imported:
DuckDB storage, canned narrative, silent voice. Setting these keys (even to
empty) means backend/__init__'s .env loader leaves them alone.
"""
import os

os.environ["SNOWFLAKE_ACCOUNT"] = ""   # -> DuckDB backend
os.environ["GEMINI_API_KEY"] = ""      # -> canned narrative, no network
os.environ["ELEVENLABS_API_KEY"] = ""  # -> silent voice, no network
os.environ["GEMINI_TAUNTS"] = ""

import pytest  # noqa: E402

from backend import db_duckdb  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _fresh_db():
    """Start each test session from an empty DuckDB file."""
    db_duckdb._conn = None
    if db_duckdb.DB_PATH and os.path.exists(db_duckdb.DB_PATH):
        os.remove(db_duckdb.DB_PATH)
    yield


@pytest.fixture
def honest_ride():
    """A short honest ride on a simple segment, reused across tests."""
    from backend.physics import build_segment, simulate_ride
    from backend.levels import RIDER
    seg = build_segment("Test Loop", [(800, 0.02), (600, -0.01), (700, 0.0)], seed=11)
    pts = simulate_ride(seg, RIDER, seed=12)
    return seg, pts

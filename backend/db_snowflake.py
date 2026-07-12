"""Snowflake storage backend (production).

Two things make this a real "best use of Snowflake":

1. The audit forensics run as Snowflake SQL — the same window-function
   kinematics the game plays against, executed in the warehouse.
2. Level 5's snapshot diff uses genuine **Time Travel**. Instead of
   keeping a copy of the original file, an edit rewrites `trackpoints`
   and the audit queries the table AS IT EXISTED before the edit via
   `AT(TIMESTAMP => ...)`. The database's own history is the evidence.

The DuckDB dialect differs from Snowflake in exactly one construct we
use — `quantile_cont(expr, p)` — which `_to_snowflake` rewrites to
`percentile_cont(p) WITHIN GROUP (ORDER BY expr)`. Everything else
(window frames, corr/stddev/median/greatest, EXCEPT) is identical.
"""
import json
import os
import re
import threading
from decimal import Decimal

import snowflake.connector

snowflake.connector.paramstyle = "qmark"  # reuse the DuckDB '?' placeholders

BACKEND = "snowflake"
DB_PATH = None  # not applicable; present for interface parity

_lock = threading.Lock()
_conn = None
_original_ts = {}  # activity_id -> server timestamp captured just after upload

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS activities(
      id STRING, game_id STRING, level INTEGER, kind STRING,
      uploaded_at TIMESTAMP_NTZ DEFAULT current_timestamp())""",
    """CREATE TABLE IF NOT EXISTS trackpoints(
      activity_id STRING, idx INTEGER, ts DOUBLE, lat DOUBLE, lon DOUBLE,
      ele DOUBLE, hr INTEGER, cad INTEGER, dist_m DOUBLE)""",
    """CREATE TABLE IF NOT EXISTS segment_profile(
      game_id STRING, level INTEGER, dist_bucket INTEGER, ele DOUBLE)""",
    """CREATE TABLE IF NOT EXISTS audits(
      activity_id STRING, check_name STRING, passed BOOLEAN, detail STRING,
      evidence STRING, run_at TIMESTAMP_NTZ DEFAULT current_timestamp())""",
]

_QUANTILE = re.compile(r"quantile_cont\(\s*([A-Za-z_]\w*)\s*,\s*([0-9.]+)\s*\)")


def _to_snowflake(sql):
    return _QUANTILE.sub(r"percentile_cont(\2) within group (order by \1)", sql)


def conn():
    global _conn
    if _conn is None:
        database = os.environ.get("SNOWFLAKE_DATABASE", "FALSE_SUMMIT")
        warehouse = os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH")
        schema = os.environ.get("SNOWFLAKE_SCHEMA", "PUBLIC")
        # Connect without a database context first, then provision idempotently
        # so a fresh trial account needs zero manual setup.
        _conn = snowflake.connector.connect(
            account=os.environ["SNOWFLAKE_ACCOUNT"],
            user=os.environ["SNOWFLAKE_USER"],
            password=os.environ["SNOWFLAKE_PASSWORD"],
            client_session_keep_alive=True,
        )
        cur = _conn.cursor()
        cur.execute(f"CREATE WAREHOUSE IF NOT EXISTS {warehouse} "
                    "WITH WAREHOUSE_SIZE='XSMALL' AUTO_SUSPEND=60 AUTO_RESUME=TRUE")
        cur.execute(f"CREATE DATABASE IF NOT EXISTS {database}")
        cur.execute(f"USE DATABASE {database}")
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        cur.execute(f"USE SCHEMA {schema}")
        cur.execute(f"USE WAREHOUSE {warehouse}")
        for ddl in SCHEMA:
            cur.execute(ddl)
        cur.close()
    return _conn


def _rows(activity_id, points):
    from .physics import smoothed_dists
    d_list = smoothed_dists(points)
    return [(activity_id, i, p["ts"], p["lat"], p["lon"], p["ele"],
             p["hr"], p["cad"], d_list[i]) for i, p in enumerate(points)]


def insert_activity(activity_id, game_id, level, kind, points, snapshot=False):
    # Time Travel is our snapshot — the duplicate "snapshot" write is a no-op.
    if snapshot:
        return
    rows = _rows(activity_id, points)
    with _lock:
        cur = conn().cursor()
        cur.execute("INSERT INTO activities(id, game_id, level, kind) VALUES (?, ?, ?, ?)",
                    [activity_id, game_id, level, kind])
        cur.executemany(
            "INSERT INTO trackpoints VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        cur.execute("SELECT current_timestamp()")
        _original_ts[activity_id] = cur.fetchone()[0]
        cur.close()


def insert_profile(game_id, level, segment):
    rows = []
    seen = set()
    for d, _la, _lo, ele in segment["path"]:
        bucket = int(d // 10) * 10
        if bucket in seen:
            continue
        seen.add(bucket)
        rows.append((game_id, level, bucket, ele))
    with _lock:
        cur = conn().cursor()
        cur.executemany("INSERT INTO segment_profile VALUES (?, ?, ?, ?)", rows)
        cur.close()


def replace_activity_points(activity_id, points):
    """Rewrite the live file. The pre-edit rows survive only in Time Travel."""
    rows = _rows(activity_id, points)
    with _lock:
        cur = conn().cursor()
        cur.execute("DELETE FROM trackpoints WHERE activity_id = ?", [activity_id])
        cur.executemany(
            "INSERT INTO trackpoints VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        cur.close()


def snapshot_changed_count(activity_id):
    """Diff the current rows against the table as it existed at upload time,
    using Snowflake Time Travel. Zero unless the file was edited after upload."""
    ts = _original_ts.get(activity_id)
    if ts is None:
        return 0
    sql = """
    SELECT count(*) FROM (
      SELECT idx, ts, lat, lon, ele, hr FROM trackpoints WHERE activity_id = ?
      MINUS
      SELECT idx, ts, lat, lon, ele, hr
      FROM trackpoints AT(TIMESTAMP => ?::timestamp_ntz) WHERE activity_id = ?
    )
    """
    with _lock:
        cur = conn().cursor()
        cur.execute(sql, [activity_id, ts, activity_id])
        n = cur.fetchone()[0] or 0
        cur.close()
    return n


def record_audit(activity_id, results):
    rows = [(activity_id, r["name"], bool(r["passed"]), r["detail"],
             json.dumps(r.get("evidence", {}))) for r in results]
    with _lock:
        cur = conn().cursor()
        cur.executemany(
            "INSERT INTO audits(activity_id, check_name, passed, detail, evidence) "
            "VALUES (?, ?, ?, ?, ?)", rows)
        cur.close()


def _norm(v):
    # Snowflake returns NUMBER columns as Decimal; the rest of the app expects
    # plain floats/ints so JSON serialization and arithmetic just work.
    return float(v) if isinstance(v, Decimal) else v


def query(sql, params=None):
    with _lock:
        cur = conn().cursor()
        cur.execute(_to_snowflake(sql), params or [])
        out = cur.fetchall()
        cur.close()
    return [tuple(_norm(x) for x in row) for row in out]

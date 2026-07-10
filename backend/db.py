"""Storage layer. Dev runs on DuckDB with SQL kept Snowflake-compatible
(window functions, corr/stddev aggregates) so the prod swap is mechanical.
Snapshot tables stand in for Snowflake Time Travel during development."""
import json
import os
import threading

import duckdb

from .physics import smoothed_dists

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DATA_DIR, "game.duckdb")

_lock = threading.Lock()
_conn = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities(
  id TEXT, game_id TEXT, level INTEGER, kind TEXT,
  uploaded_at TIMESTAMP DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS trackpoints(
  activity_id TEXT, idx INTEGER, ts DOUBLE, lat DOUBLE, lon DOUBLE,
  ele DOUBLE, hr INTEGER, cad INTEGER, dist_m DOUBLE
);
CREATE TABLE IF NOT EXISTS trackpoints_snapshot(
  activity_id TEXT, idx INTEGER, ts DOUBLE, lat DOUBLE, lon DOUBLE,
  ele DOUBLE, hr INTEGER, cad INTEGER, dist_m DOUBLE
);
CREATE TABLE IF NOT EXISTS segment_profile(
  game_id TEXT, level INTEGER, dist_bucket INTEGER, ele DOUBLE
);
CREATE TABLE IF NOT EXISTS audits(
  activity_id TEXT, check_name TEXT, passed BOOLEAN, detail TEXT, evidence TEXT,
  run_at TIMESTAMP DEFAULT current_timestamp
);
"""


def conn():
    global _conn
    if _conn is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        _conn = duckdb.connect(DB_PATH)
        _conn.execute(SCHEMA)
    return _conn


def insert_activity(activity_id, game_id, level, kind, points, snapshot=False):
    """Store a ride; per-point dist_m is derived from immutable positions."""
    d_list = smoothed_dists(points)
    rows = []
    for i, p in enumerate(points):
        rows.append((activity_id, i, p["ts"], p["lat"], p["lon"], p["ele"],
                     p["hr"], p["cad"], d_list[i]))
    table = "trackpoints_snapshot" if snapshot else "trackpoints"
    with _lock:
        c = conn()
        if not snapshot:
            c.execute("INSERT INTO activities(id, game_id, level, kind) VALUES (?, ?, ?, ?)",
                      [activity_id, game_id, level, kind])
        c.executemany(
            f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)


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
        conn().executemany("INSERT INTO segment_profile VALUES (?, ?, ?, ?)", rows)


def replace_activity_points(activity_id, points):
    """An in-place edit of a live upload. The snapshot table keeps the
    original — that asymmetry IS the Time Travel mechanic."""
    d_list = smoothed_dists(points)
    rows = []
    for i, p in enumerate(points):
        rows.append((activity_id, i, p["ts"], p["lat"], p["lon"], p["ele"],
                     p["hr"], p["cad"], d_list[i]))
    with _lock:
        c = conn()
        c.execute("DELETE FROM trackpoints WHERE activity_id = ?", [activity_id])
        c.executemany("INSERT INTO trackpoints VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)


def record_audit(activity_id, results):
    rows = [(activity_id, r["name"], r["passed"], r["detail"], json.dumps(r.get("evidence", {})))
            for r in results]
    with _lock:
        conn().executemany(
            "INSERT INTO audits(activity_id, check_name, passed, detail, evidence) VALUES (?, ?, ?, ?, ?)",
            rows)


def query(sql, params=None):
    with _lock:
        return conn().execute(sql, params or []).fetchall()

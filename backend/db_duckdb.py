"""DuckDB storage backend (development default).

Snapshot tables stand in for Snowflake Time Travel here: an edit rewrites
`trackpoints` while `trackpoints_snapshot` preserves the as-uploaded rows,
so `snapshot_changed_count` can diff them. The Snowflake backend implements
the same contract with real Time Travel."""
import json
import os
import threading

import duckdb

from .physics import smoothed_dists

BACKEND = "duckdb"

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


def _rows(activity_id, points):
    d_list = smoothed_dists(points)
    return [(activity_id, i, p["ts"], p["lat"], p["lon"], p["ele"],
             p["hr"], p["cad"], d_list[i]) for i, p in enumerate(points)]


def insert_activity(activity_id, game_id, level, kind, points, snapshot=False):
    """Store a ride; per-point dist_m is derived from immutable positions."""
    rows = _rows(activity_id, points)
    table = "trackpoints_snapshot" if snapshot else "trackpoints"
    with _lock:
        c = conn()
        if not snapshot:
            c.execute("INSERT INTO activities(id, game_id, level, kind) VALUES (?, ?, ?, ?)",
                      [activity_id, game_id, level, kind])
        c.executemany(f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)


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
    """An in-place edit of a live upload. trackpoints_snapshot keeps the
    original — that asymmetry is what snapshot_changed_count detects."""
    rows = _rows(activity_id, points)
    with _lock:
        c = conn()
        c.execute("DELETE FROM trackpoints WHERE activity_id = ?", [activity_id])
        c.executemany("INSERT INTO trackpoints VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)


def snapshot_changed_count(activity_id):
    """How many points differ from the file as originally uploaded."""
    sql = """
    SELECT count(*) FROM (
      SELECT idx, ts, lat, lon, ele, hr FROM trackpoints WHERE activity_id = ?
      EXCEPT
      SELECT idx, ts, lat, lon, ele, hr FROM trackpoints_snapshot WHERE activity_id = ?
    )
    """
    return query(sql, [activity_id, activity_id])[0][0] or 0


def record_audit(activity_id, results):
    rows = [(activity_id, r["name"], r["passed"], r["detail"], json.dumps(r.get("evidence", {})))
            for r in results]
    with _lock:
        conn().executemany(
            "INSERT INTO audits(activity_id, check_name, passed, detail, evidence) "
            "VALUES (?, ?, ?, ?, ?)", rows)


def query(sql, params=None):
    with _lock:
        return conn().execute(sql, params or []).fetchall()

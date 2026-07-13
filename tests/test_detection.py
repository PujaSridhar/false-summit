"""Detection suite: each check in isolation, dialect translation, snapshot diff."""
import uuid

import pytest

from backend import detection, db_duckdb as db
from backend import db_snowflake
from backend.physics import build_segment, simulate_ride, simulate_effort
from backend.levels import RIDER
from backend.cheats import scale_time


def _aid():
    return "t_" + uuid.uuid4().hex[:10]


def _ctx(gid, level=1, history=None):
    return {"game_id": gid, "level": level, "mass": RIDER["mass"], "ftp": RIDER["ftp"],
            "history_wkg_p98": history, "profile_scale": 1.0}


def _honest(seed=30):
    seg = build_segment("D", [(1500, 0.05), (1000, -0.03), (900, 0.01)], seed=seed)
    pts = simulate_ride(seg, RIDER, seed=seed + 1)
    return seg, pts


# ---- individual checks on an honest ride: all pass ----

@pytest.mark.parametrize("name,params", [
    ("timestamps", {}),
    ("max_speed", {"limit": 26.0}),
    ("power_wkg", {"limit": 4.6}),
    ("accel_spikes", {"limit": 4.5}),
    ("hr_flat", {"min_sd": 2.5}),
])
def test_honest_ride_passes(name, params):
    seg, pts = _honest()
    aid = _aid()
    db.insert_activity(aid, "g", 1, "test", pts)
    res = detection.CHECKS[name](aid, params, _ctx("g"))
    assert res["passed"], res["detail"]


def test_juiced_ride_fails_power():
    seg, pts = _honest()
    juiced = scale_time(pts, params={"pct": 30})
    aid = _aid()
    db.insert_activity(aid, "g", 1, "test", juiced)
    res = detection.check_power_wkg(aid, {"limit": 4.0}, _ctx("g"))
    assert not res["passed"]
    assert res["evidence"]["wkg_p98"] > 4.0


def test_flat_hr_fails_hr_flat():
    seg = build_segment("D", [(1500, 0.04), (1000, -0.02)], seed=40)
    fake = simulate_effort(seg, RIDER, 250, noise=0.0, hr_mode="flat", seed=41)
    aid = _aid()
    db.insert_activity(aid, "g", 1, "test", fake)
    res = detection.check_hr_flat(aid, {"min_sd": 2.5}, _ctx("g"))
    assert not res["passed"]


def test_nonmonotonic_timestamps_fail():
    seg, pts = _honest()
    pts = [dict(p) for p in pts]
    pts[10]["ts"] = pts[9]["ts"] - 5  # inject a backwards jump
    aid = _aid()
    db.insert_activity(aid, "g", 1, "test", pts)
    res = detection.check_timestamps(aid, {}, _ctx("g"))
    assert not res["passed"]
    assert res["evidence"]["non_monotonic"] >= 1


def test_rider_baseline_flags_overperformance():
    seg, pts = _honest()
    juiced = scale_time(pts, params={"pct": 12})
    aid = _aid()
    db.insert_activity(aid, "g", 1, "test", juiced)
    # history baseline from the honest ride
    hist_aid = _aid()
    db.insert_activity(hist_aid, "g", 1, "history", pts)
    hist = detection.wkg_p98(hist_aid, RIDER["mass"])
    res = detection.check_rider_baseline(aid, {"margin": 1.10}, _ctx("g", history=hist))
    assert not res["passed"]


def test_elevation_match_passes_and_fails():
    seg, pts = _honest(seed=50)
    db.insert_profile("gele", 1, seg)
    aid = _aid()
    db.insert_activity(aid, "gele", 1, "test", pts)
    ok = detection.check_elevation_match(aid, {"max_m": 6.0}, _ctx("gele"))
    assert ok["passed"], ok["evidence"]
    # a ride shifted 40 m up should fail against the same profile
    shifted = [dict(p, ele=p["ele"] + 40) for p in pts]
    aid2 = _aid()
    db.insert_activity(aid2, "gele", 1, "test", shifted)
    bad = detection.check_elevation_match(aid2, {"max_m": 6.0}, _ctx("gele"))
    assert not bad["passed"]


def test_hr_correlation_short_ride_passes():
    # < 120 power points -> check abstains (returns pass) rather than false-flag
    seg = build_segment("D", [(300, 0.02)], seed=60)
    pts = simulate_ride(seg, RIDER, seed=61)
    aid = _aid()
    db.insert_activity(aid, "g", 1, "test", pts)
    res = detection.check_hr_correlation(aid, {"min_corr": 0.25}, _ctx("g"))
    assert res["passed"]


# ---- snapshot diff / Time Travel stand-in ----

def test_snapshot_unchanged_is_zero():
    seg, pts = _honest(seed=70)
    aid = _aid()
    db.insert_activity(aid, "g", 1, "upload", pts)
    db.insert_activity(aid, "g", 1, "upload", pts, snapshot=True)
    assert db.snapshot_changed_count(aid) == 0


def test_snapshot_detects_edit():
    seg, pts = _honest(seed=71)
    aid = _aid()
    db.insert_activity(aid, "g", 1, "upload", pts)
    db.insert_activity(aid, "g", 1, "upload", pts, snapshot=True)
    edited = scale_time(pts, params={"pct": 5})
    db.replace_activity_points(aid, edited)
    assert db.snapshot_changed_count(aid) > 0


# ---- Snowflake dialect translation (pure function, no connection) ----

def test_dialect_translates_quantile():
    out = db_snowflake._to_snowflake("SELECT quantile_cont(v, 0.99) FROM kin")
    assert out == "SELECT percentile_cont(0.99) within group (order by v) FROM kin"


def test_dialect_translates_multiple():
    out = db_snowflake._to_snowflake(
        "SELECT quantile_cont(v, 0.99), quantile_cont(wkg, 0.98) FROM t")
    assert "percentile_cont(0.99) within group (order by v)" in out
    assert "percentile_cont(0.98) within group (order by wkg)" in out
    assert "quantile_cont" not in out


def test_dialect_leaves_other_sql_untouched():
    sql = "SELECT median(abs(a)), corr(hr, wkg), stddev_samp(v) FROM t"
    assert db_snowflake._to_snowflake(sql) == sql

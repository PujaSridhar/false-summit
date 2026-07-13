"""Broad edge / degenerate-input coverage across every module.

The point is that pathological inputs — empty rides, zero/negative params,
missing API keys, unknown ids — return something sensible instead of raising.
"""
import uuid

import pytest

from backend import physics, cheats, detection, narrative, ai, voice
from backend import db_duckdb as db
from backend.levels import RIDER, LEVELS, level_cfg


def _aid():
    return "e_" + uuid.uuid4().hex[:10]


def _ctx(gid="g", history=None):
    return {"game_id": gid, "level": 1, "mass": RIDER["mass"], "ftp": RIDER["ftp"],
            "history_wkg_p98": history, "profile_scale": 1.0}


# ---------- physics degenerates ----------

def test_speed_from_power_zero_power():
    assert physics.speed_from_power(0, 0.0, 78) >= 0.3


def test_speed_from_power_steep_wall():
    v = physics.speed_from_power(200, 0.25, 78)
    assert 0 < v < 30


def test_speed_from_power_steep_descent():
    v = physics.speed_from_power(100, -0.20, 78)
    assert 0 < v <= 40


def test_grade_at_start_and_end():
    seg = physics.build_segment("S", [(500, 0.05)], seed=1)
    assert isinstance(physics.grade_at(seg, 0), float)
    assert isinstance(physics.grade_at(seg, seg["length_m"] + 500), float)  # past the end


def test_ride_stats_two_identical_points():
    p = {"ts": 0.0, "lat": 46.0, "lon": 7.0, "ele": 400, "hr": 100, "cad": 0}
    s = physics.ride_stats([p, dict(p, ts=1.0)])
    assert s["dist_m"] == pytest.approx(0.0, abs=1e-6)
    assert s["moving_s"] == 0  # never moved


def test_smoothed_dists_single_point():
    assert physics.smoothed_dists([{"lat": 1, "lon": 2}]) == [0.0]


# ---------- cheat degenerates ----------

def test_scale_time_empty_points():
    assert cheats.scale_time([], params={"pct": 20}) == []


def test_scale_time_negative_pct_slows_down(honest_ride):
    seg, pts = honest_ride
    out = cheats.scale_time(pts, params={"pct": -20})
    assert out[-1]["ts"] > pts[-1]["ts"]  # negative juice => slower


def test_scale_time_extreme_pct_clamped(honest_ride):
    seg, pts = honest_ride
    out = cheats.scale_time(pts, params={"pct": 100})  # f floors at 0.05, no divide-by-zero
    ts = [p["ts"] for p in out]
    assert ts == sorted(ts)


def test_trim_stops_empty():
    assert cheats.trim_stops([], segment=None) == []


def test_scale_time_range_empty():
    assert cheats.scale_time_range([], params={"pct": 30}) == []


def test_synthesize_tiny_target():
    seg = physics.build_segment("S", [(400, 0.02)], seed=2)
    out = cheats.synthesize(None, segment=seg, params={"target_s": 20, "humanize": 0})
    assert len(out) >= 1
    assert all(p["hr"] > 0 for p in out)


def test_apply_ops_does_not_mutate_input(honest_ride):
    seg, pts = honest_ride
    before = [dict(p) for p in pts]
    cheats.apply_ops(pts, seg, [{"tool": "scale_time", "params": {"pct": 50}}])
    assert [p["ts"] for p in pts] == [p["ts"] for p in before]


# ---------- detection degenerates ----------

def test_checks_on_empty_ride_do_not_crash():
    aid = _aid()  # never inserted -> zero trackpoints
    for name, params in [("timestamps", {}), ("max_speed", {"limit": 20}),
                         ("power_wkg", {"limit": 4}), ("accel_spikes", {"limit": 4}),
                         ("smoothness", {"min_mad": 0.05}), ("hr_flat", {"min_sd": 2}),
                         ("hr_correlation", {"min_corr": 0.2})]:
        res = detection.CHECKS[name](aid, params, _ctx())
        assert "passed" in res and "detail" in res


def test_snapshot_changed_count_unknown_activity_zero():
    assert db.snapshot_changed_count(_aid()) == 0


def test_wkg_p98_empty_returns_zero():
    assert detection.wkg_p98(_aid(), RIDER["mass"]) == 0.0


def test_tightened_only_touches_sensory_checks():
    checks = {"power_wkg": {"limit": 4.6}, "max_speed": {"limit": 26.0},
              "rider_baseline": {"margin": 1.12}}
    tight = detection.tightened(checks, 0.9)
    assert tight["max_speed"]["limit"] == pytest.approx(26.0 * 0.9)   # tightened
    assert tight["power_wkg"]["limit"] == 4.6                          # physiology untouched
    assert tight["rider_baseline"]["margin"] == 1.12                   # untouched


# ---------- narrative / AI / voice fallbacks (no keys in tests) ----------

def test_ai_and_voice_disabled_without_keys():
    assert ai.enabled() is False
    assert voice.enabled() is False


def test_taunt_falls_back_to_canned():
    assert ai.taunt(1, "Some Segment", "Dax") == narrative.taunt(1)


def test_voice_say_returns_none_without_key():
    assert voice.say("anything", role="rival") is None
    assert voice.say("", role="auditor") is None


def test_report_with_empty_dossier():
    rep = ai.investigation_report([], "Dax")
    assert rep["generated_by"] == "canned"
    assert "findings" in rep and rep["findings"] == []
    assert rep["title"]


def test_report_script_flattens_without_error():
    rep = ai.investigation_report([{"level": 1, "segment": "Loop", "tools": ["trim_stops"],
                                    "outcome": "caught",
                                    "checks": [{"name": "power_wkg", "passed": False}]}], "Dax")
    script = voice.report_script(rep)
    assert isinstance(script, str) and len(script) > 0


def test_canned_report_covers_every_check_name():
    # every detection check should have a human-readable "tell" for the report
    from backend.ai import CHECK_TELL
    for name in detection.CHECKS:
        assert name in CHECK_TELL, f"missing report tell for {name}"


def test_narrative_verdict_branches():
    assert "FLAGGED" in narrative.verdict(True, False)
    assert narrative.verdict(False, True)   # win line
    assert narrative.verdict(False, False)  # too-slow line


# ---------- level design invariants ----------

def test_every_level_is_internally_consistent():
    ids = [lv["id"] for lv in LEVELS]
    assert ids == [1, 2, 3, 4, 5]
    for lv in LEVELS:
        assert lv["tools"], f"L{lv['id']} has no tools"
        assert lv["checks"], f"L{lv['id']} has no checks"
        # every tool a level exposes is a real, applicable cheat
        for t in lv["tools"]:
            assert t["name"] in cheats.TOOLS
        # every check a level runs is a real detection check
        for name in lv["checks"]:
            assert name in detection.CHECKS


def test_level_cfg_unknown_returns_none():
    assert level_cfg(99) is None

"""Cheat tools: each op incl. boundary params."""
import pytest

from backend import cheats
from backend.physics import ride_stats


def test_scale_time_zero_is_noop(honest_ride):
    seg, pts = honest_ride
    out = cheats.scale_time(pts, params={"pct": 0})
    assert [p["ts"] for p in out] == [p["ts"] for p in pts]


def test_scale_time_compresses_elapsed(honest_ride):
    seg, pts = honest_ride
    base = ride_stats(pts)["elapsed_s"]
    out = cheats.scale_time(pts, params={"pct": 10})
    assert ride_stats(out)["elapsed_s"] == pytest.approx(base * 0.9, rel=0.02)


def test_scale_time_keeps_monotonic(honest_ride):
    seg, pts = honest_ride
    out = cheats.scale_time(pts, params={"pct": 25})
    ts = [p["ts"] for p in out]
    assert ts == sorted(ts)


def test_scale_time_distance_unchanged(honest_ride):
    seg, pts = honest_ride
    out = cheats.scale_time(pts, params={"pct": 15})
    assert ride_stats(out)["dist_m"] == pytest.approx(ride_stats(pts)["dist_m"], rel=1e-6)


def test_trim_stops_removes_stationary_time():
    from backend.physics import build_segment, simulate_ride
    from backend.levels import RIDER
    seg = build_segment("S", [(2000, 0.01)], seed=20)
    pts = simulate_ride(seg, RIDER, seed=21, stop=(1000, 150))
    trimmed = cheats.trim_stops(pts, segment=seg)
    assert ride_stats(trimmed)["elapsed_s"] < ride_stats(pts)["elapsed_s"]
    # distance essentially preserved (positions unchanged, just dropped stop)
    assert ride_stats(trimmed)["dist_m"] == pytest.approx(ride_stats(pts)["dist_m"], rel=0.05)


def test_trim_stops_no_stop_barely_changes(honest_ride):
    seg, pts = honest_ride  # no stop in this ride
    trimmed = cheats.trim_stops(pts, segment=seg)
    assert ride_stats(trimmed)["elapsed_s"] == pytest.approx(ride_stats(pts)["elapsed_s"], abs=3)


def test_scale_time_range_only_affects_slice(honest_ride):
    seg, pts = honest_ride
    out = cheats.scale_time_range(pts, params={"pct": 40, "from_frac": 0.5, "to_frac": 1.0})
    # first half timestamps unchanged
    n = len(pts)
    for i in range(n // 4):
        assert out[i]["ts"] == pytest.approx(pts[i]["ts"], abs=1e-6)
    # overall faster
    assert ride_stats(out)["elapsed_s"] < ride_stats(pts)["elapsed_s"]


def test_scale_time_range_inverted_bounds_no_crash(honest_ride):
    seg, pts = honest_ride
    out = cheats.scale_time_range(pts, params={"pct": 30, "from_frac": 0.9, "to_frac": 0.1})
    assert len(out) == len(pts)  # degenerate window handled, no exception


def test_scale_time_range_zero_pct_noop(honest_ride):
    seg, pts = honest_ride
    out = cheats.scale_time_range(pts, params={"pct": 0})
    assert [p["ts"] for p in out] == [p["ts"] for p in pts]


def test_synthesize_terrain_aware_hits_target(honest_ride):
    seg, _ = honest_ride
    out = cheats.synthesize(None, segment=seg,
                            params={"rival_time_s": 300, "faster_pct": 3,
                                    "humanize": 60, "hr_mode": "modeled",
                                    "terrain_aware": True})
    assert len(out) > 20
    assert ride_stats(out)["elapsed_s"] < 300


def test_synthesize_humanize_adds_noise(honest_ride):
    seg, _ = honest_ride
    clean = cheats.synthesize(None, segment=seg, params={"target_s": 300, "humanize": 0})
    noisy = cheats.synthesize(None, segment=seg, params={"target_s": 300, "humanize": 90})
    var_clean = _hr_spread(clean)
    var_noisy = _hr_spread(noisy)
    assert var_noisy >= var_clean  # humanize never reduces variation


def _hr_spread(pts):
    hrs = [p["hr"] for p in pts]
    return max(hrs) - min(hrs)


def test_apply_ops_unknown_tool_raises(honest_ride):
    seg, pts = honest_ride
    with pytest.raises(ValueError):
        cheats.apply_ops(pts, seg, [{"tool": "nope", "params": {}}])


def test_apply_ops_empty_is_copy(honest_ride):
    seg, pts = honest_ride
    out = cheats.apply_ops(pts, seg, [])
    assert out == pts
    assert out is not pts  # a copy, not the same list


def test_apply_ops_chains(honest_ride):
    seg, pts = honest_ride
    out = cheats.apply_ops(pts, seg, [
        {"tool": "scale_time", "params": {"pct": 5}},
        {"tool": "scale_time", "params": {"pct": 5}},
    ])
    assert ride_stats(out)["elapsed_s"] < ride_stats(pts)["elapsed_s"]

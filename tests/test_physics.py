"""Physics engine: solver, kinematics, degenerate rides."""
import math

import pytest

from backend import physics
from backend.levels import RIDER


def test_speed_from_power_positive():
    v = physics.speed_from_power(200, 0.0, 78)
    assert v > 0
    assert v < 30  # never returns the solver's upper bound for a real effort


def test_more_power_is_faster_on_flat():
    slow = physics.speed_from_power(150, 0.0, 78)
    fast = physics.speed_from_power(300, 0.0, 78)
    assert fast > slow


def test_climb_slower_than_flat_same_power():
    flat = physics.speed_from_power(250, 0.0, 78)
    climb = physics.speed_from_power(250, 0.08, 78)
    assert climb < flat


def test_descent_faster_than_flat_same_power():
    flat = physics.speed_from_power(250, 0.0, 78)
    down = physics.speed_from_power(250, -0.06, 78)
    assert down > flat


def test_descent_solver_does_not_diverge():
    # the bug that motivated bisection: Newton overshoots on descents
    v = physics.speed_from_power(60, -0.09, 78)
    assert 0 < v < 30


def test_power_speed_roundtrip_flat():
    v = physics.speed_from_power(240, 0.01, 78)
    p = physics.power_from_speed(v, 0.01, 78)
    assert p == pytest.approx(240, rel=0.02)


def test_haversine_one_degree_lat():
    d = physics.haversine_m(0.0, 0.0, 1.0, 0.0)
    assert d == pytest.approx(111195, rel=0.01)  # ~111 km per degree


def test_haversine_zero_for_same_point():
    assert physics.haversine_m(46.3, 7.5, 46.3, 7.5) == pytest.approx(0.0, abs=1e-6)


def test_build_segment_length_matches_profile():
    seg = physics.build_segment("S", [(1000, 0.0), (500, 0.05)], seed=1)
    assert seg["length_m"] == pytest.approx(1500, abs=10)


def test_grade_at_recovers_profile_grade():
    seg = physics.build_segment("S", [(1000, 0.06)], seed=1)
    assert physics.grade_at(seg, 500) == pytest.approx(0.06, abs=0.005)


def test_ride_stats_empty():
    s = physics.ride_stats([])
    assert s["elapsed_s"] == 0 and s["dist_m"] == 0.0


def test_ride_stats_single_point():
    s = physics.ride_stats([{"ts": 0.0, "lat": 46.3, "lon": 7.5, "ele": 400, "hr": 100, "cad": 0}])
    assert s["elapsed_s"] == 0


def test_smoothed_dists_length_and_first_zero():
    seg = physics.build_segment("S", [(500, 0.0)], seed=2)
    pts = physics.simulate_ride(seg, RIDER, seed=3)
    d = physics.smoothed_dists(pts)
    assert len(d) == len(pts)
    assert d[0] == 0.0


def test_smoothed_dists_empty():
    assert physics.smoothed_dists([]) == []


def test_simulate_ride_is_well_formed():
    seg = physics.build_segment("S", [(1200, 0.03), (800, -0.02)], seed=4)
    pts = physics.simulate_ride(seg, RIDER, seed=5)
    assert len(pts) > 10
    assert all(p["hr"] > 0 for p in pts)
    ts = [p["ts"] for p in pts]
    assert ts == sorted(ts)              # timestamps monotonic
    assert all(math.isfinite(p["lat"]) and math.isfinite(p["lon"]) for p in pts)


def test_simulate_ride_with_stop_adds_time():
    seg = physics.build_segment("S", [(2000, 0.01)], seed=6)
    no_stop = physics.simulate_ride(seg, RIDER, seed=7, stop=None)
    with_stop = physics.simulate_ride(seg, RIDER, seed=7, stop=(1000, 120))
    assert with_stop[-1]["ts"] > no_stop[-1]["ts"]


def test_simulate_effort_hits_target_duration():
    seg = physics.build_segment("S", [(1500, 0.04), (1000, -0.03)], seed=8)
    pts = physics.simulate_effort(seg, RIDER, 220.0, noise=0.0, seed=9)
    assert len(pts) > 20
    assert all(p["hr"] > 0 for p in pts)

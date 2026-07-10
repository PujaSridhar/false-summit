"""Cheat tools — the player's arsenal. Each takes trackpoints and returns
doctored trackpoints. These mirror real-world techniques (trimming stops,
Digital-EPO-style time compression, full GPX synthesis)."""
import math
import random

from .physics import haversine_m, _at, grade_at, simulate_effort, GPS_NOISE_M


def trim_stops(points, segment=None, params=None):
    """Remove stationary runs (the coffee stop) and stitch time back together."""
    params = params or {}
    min_stop_s = int(params.get("min_stop_s", 15))
    still_speed = float(params.get("still_speed", 0.8))

    drop = [False] * len(points)
    run_start = None
    hop = 4  # judge stillness over a 5s window; per-second GPS jitter lies
    for i in range(1, len(points)):
        j = max(0, i - hop)
        a, b = points[j], points[i]
        dt = (b["ts"] - a["ts"]) or 1.0
        v = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"]) / dt
        if v < still_speed:
            if run_start is None:
                run_start = i
        else:
            if run_start is not None and i - run_start >= min_stop_s:
                for j in range(run_start, i):
                    drop[j] = True
            run_start = None
    if run_start is not None and len(points) - run_start >= min_stop_s:
        for j in range(run_start, len(points)):
            drop[j] = True

    out = []
    removed_s = 0.0
    prev_orig_ts = None
    prev_new_ts = None
    for i, p in enumerate(points):
        if drop[i]:
            continue
        if prev_orig_ts is None:
            new_ts = p["ts"]
        else:
            gap = p["ts"] - prev_orig_ts
            # collapse any gap spanning dropped points to 1s
            new_ts = prev_new_ts + min(gap, 1.0)
            removed_s += gap - min(gap, 1.0)
        q = dict(p)
        q["ts"] = new_ts
        out.append(q)
        prev_orig_ts = p["ts"]
        prev_new_ts = new_ts
    return out


def scale_time(points, segment=None, params=None):
    """Digital-EPO-style juice: compress all timestamps by pct percent."""
    params = params or {}
    pct = float(params.get("pct", 0))
    f = max(0.05, 1.0 - pct / 100.0)
    t0 = points[0]["ts"] if points else 0.0
    out = []
    for p in points:
        q = dict(p)
        q["ts"] = round(t0 + (p["ts"] - t0) * f, 2)
        out.append(q)
    return out


def scale_time_range(points, segment=None, params=None):
    """Juice only a slice of the ride (by fraction of elapsed time).
    Watts are conspicuous on climbs; drag hides them on descents."""
    params = params or {}
    pct = float(params.get("pct", 0))
    lo = float(params.get("from_frac", 0.0))
    hi = float(params.get("to_frac", 1.0))
    if not points or pct <= 0:
        return [dict(p) for p in points]
    f = max(0.05, 1.0 - pct / 100.0)
    t0, t1 = points[0]["ts"], points[-1]["ts"]
    a = t0 + (t1 - t0) * lo
    b = t0 + (t1 - t0) * hi
    out = []
    shift = 0.0
    prev_ts = None
    for p in points:
        q = dict(p)
        ts = p["ts"]
        if prev_ts is not None:
            gap = ts - prev_ts
            if a <= ts <= b:
                shift += gap * (1.0 - f)
        q["ts"] = round(ts - shift, 2)
        out.append(q)
        prev_ts = ts
    return out


def synthesize(points, segment=None, params=None):
    """Fabricate the whole effort. faster_pct sets the target vs the rival's
    time; humanize mixes natural noise back in; hr_mode 'flat' is lazy,
    'modeled' fakes physiology; terrain_aware paces like a real rider
    (constant power budget) instead of constant speed."""
    from .levels import RIDER
    params = params or {}
    rival = float(params.get("rival_time_s", 600))
    faster = float(params.get("faster_pct", 3))
    target_s = int(params.get("target_s") or rival * (1 - faster / 100.0))
    humanize = float(params.get("humanize", 0.0)) / 100.0
    hr_mode = params.get("hr_mode", "flat")
    seed = int(params.get("seed", 99))

    if params.get("terrain_aware"):
        lo_p, hi_p = 60.0, 520.0
        pts = []
        for _ in range(16):
            mid = (lo_p + hi_p) / 2
            pts = simulate_effort(segment, RIDER, mid, noise=humanize,
                                  hr_mode=hr_mode, seed=seed)
            if len(pts) > target_s:
                lo_p = mid  # too slow, more watts
            else:
                hi_p = mid
        return pts

    rng = random.Random(seed)
    L = segment["length_m"]
    v_base = L / max(target_s, 30)
    pts = []
    d = 0.0
    hr = 150.0
    for t in range(1, target_s + 1):
        vv = v_base * (1 + humanize * 0.12 * math.sin(t / 9.0)) + rng.gauss(0, v_base * 0.05 * humanize)
        d = min(d + max(vv, 0.3), L)
        _, la, lo, el = _at(segment, d)
        noise = GPS_NOISE_M * humanize
        la += rng.gauss(0, noise) / 111320.0
        lo += rng.gauss(0, noise) / (111320.0 * math.cos(math.radians(la)))
        if hr_mode == "flat":
            h = 152 + rng.gauss(0, 0.5)
        else:
            grade = grade_at(segment, d)
            target_hr = 128 + 55 * min(1.0, max(grade, 0.0) * 14)
            hr += (target_hr - hr) / 20.0 + rng.gauss(0, 0.8)
            h = hr
        pts.append({
            "ts": float(t), "lat": la, "lon": lo,
            "ele": el + rng.gauss(0, 1.0 * humanize),
            "hr": int(round(h)), "cad": 88,
        })
    return pts


TOOLS = {
    "trim_stops": trim_stops,
    "scale_time": scale_time,
    "scale_time_range": scale_time_range,
    "synthesize": synthesize,
}


def apply_ops(points, segment, ops):
    out = [dict(p) for p in points]
    for op in ops:
        fn = TOOLS.get(op.get("tool"))
        if fn is None:
            raise ValueError(f"unknown tool: {op.get('tool')}")
        out = fn(out, segment=segment, params=op.get("params") or {})
    return out

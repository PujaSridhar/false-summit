"""Ride physics: synthetic segments, honest ride simulation, kinematics.

Every ride is generated from a rider power model, so detection checks
(which invert the same physics) always have a ground truth. Honest rides
carry natural noise — power variation, GPS jitter, heart-rate lag.
Cheat transforms break those invariants in measurable ways.
"""
import math
import random

G = 9.81
RHO = 1.226          # air density kg/m^3
CRR = 0.005          # rolling resistance coefficient
CDA = 0.32           # drag area m^2
DRAG_K = 0.5 * RHO * CDA  # 0.19616


def speed_from_power(power, grade, mass):
    """Solve P = (Crr + grade)*m*g*v + k*v^3 for v.

    Bisection, not Newton: on descents the linear term goes negative and
    Newton shoots past the physical root. f crosses zero exactly once on
    (0, 40], so bisection is provably correct."""
    roll = (CRR + grade) * mass * G
    lo, hi = 0.05, 40.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if roll * mid + DRAG_K * mid ** 3 - power < 0:
            lo = mid
        else:
            hi = mid
    return max(0.3, (lo + hi) / 2)


def power_from_speed(v, grade, mass):
    return (CRR + grade) * mass * G * v + DRAG_K * v ** 3


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def build_segment(name, profile, seed=7, start=(46.302, 7.522)):
    """profile: list of (length_m, grade). Path sampled every 5 m."""
    rng = random.Random(seed)
    step = 5.0
    lat, lon = start
    ele = 420.0
    d = 0.0
    bearing0 = rng.uniform(0, 360)
    path = [(0.0, lat, lon, ele)]
    for seg_len, grade in profile:
        for _ in range(int(seg_len / step)):
            b = math.radians(bearing0 + 28 * math.sin(d / 260.0))
            lat += step * math.cos(b) / 111320.0
            lon += step * math.sin(b) / (111320.0 * math.cos(math.radians(lat)))
            ele += grade * step
            d += step
            path.append((d, lat, lon, ele))
    return {"name": name, "length_m": d, "path": path, "step": step}


def _at(segment, d):
    """Position at distance d, linearly interpolated — snapping to the 5 m
    path grid would alias speed jitter into every generated file."""
    path, step = segment["path"], segment["step"]
    i = int(d / step)
    if i >= len(path) - 1:
        return path[-1]
    f = (d - i * step) / step
    d0, la0, lo0, e0 = path[i]
    d1, la1, lo1, e1 = path[i + 1]
    return (d0 + f * (d1 - d0), la0 + f * (la1 - la0),
            lo0 + f * (lo1 - lo0), e0 + f * (e1 - e0))


def grade_at(segment, d):
    path, step = segment["path"], segment["step"]
    i = min(int(d / step), len(path) - 2)
    return (path[i + 1][3] - path[i][3]) / step


GPS_NOISE_M = 1.2
ELE_NOISE_M = 0.5   # barometric-altimeter-grade
STOP_JITTER_M = 0.35


def simulate_ride(segment, rider, seed=1, stop=None):
    """Simulate an honest ride at 1 Hz. stop: (dist_m, duration_s)."""
    rng = random.Random(seed)
    L = segment["length_m"]
    pts = []
    t = 0
    d = 0.0
    hr = 98.0
    stop_done = False
    while d < L:
        grade = grade_at(segment, d)
        target = rider["ftp"] * (0.78 + 0.06 * math.sin(t / 47.0) + 3.2 * max(grade, 0.0))
        target = min(target, rider["ftp"] * 1.08)
        power = max(35.0, rng.gauss(target, 16.0))
        v = speed_from_power(power, grade, rider["mass"])
        d = min(d + v, L)
        t += 1
        hr_target = 98 + 82 * min(1.15, power / rider["ftp"])
        hr += (hr_target - hr) / 22.0 + rng.gauss(0, 0.7)
        _, la, lo, el = _at(segment, d)
        la += rng.gauss(0, GPS_NOISE_M) / 111320.0
        lo += rng.gauss(0, GPS_NOISE_M) / (111320.0 * math.cos(math.radians(la)))
        pts.append({
            "ts": float(t), "lat": la, "lon": lo,
            "ele": el + rng.gauss(0, ELE_NOISE_M),
            "hr": int(round(hr)),
            "cad": int(max(50, rng.gauss(86, 4))) if v > 1 else 0,
        })
        if stop and not stop_done and d >= stop[0]:
            stop_done = True
            base = pts[-1]
            for _ in range(stop[1]):
                t += 1
                hr = max(72.0, hr - 0.35 + rng.gauss(0, 0.4))
                pts.append({
                    "ts": float(t),
                    "lat": base["lat"] + rng.gauss(0, STOP_JITTER_M) / 111320.0,
                    "lon": base["lon"] + rng.gauss(0, STOP_JITTER_M) / 111320.0,
                    "ele": base["ele"] + rng.gauss(0, 0.3),
                    "hr": int(round(hr)), "cad": 0,
                })
    return pts


def simulate_effort(segment, rider, power_w, noise=1.0, hr_mode="modeled", seed=42):
    """Ride the segment at a constant power budget — pacing that respects
    terrain. This is what a *smart* fabrication looks like; `noise` scales
    how much natural variation gets mixed back in (0 = suspiciously clean)."""
    rng = random.Random(seed)
    L = segment["length_m"]
    pts = []
    t = 0
    d = 0.0
    hr = 110.0
    while d < L and t < 8000:
        grade = grade_at(segment, d)
        # human pacing: surge on the climbs — constant-power files have no
        # terrain signal for the heart rate to correlate with
        power = power_w * (0.78 + 0.06 * noise * math.sin(t / 41.0) + 3.2 * max(grade, 0.0))
        power = min(power, power_w * 1.08)
        power = max(30.0, power + rng.gauss(0, 16.0 * noise))
        v = speed_from_power(power, grade, rider["mass"])
        d = min(d + v, L)
        t += 1
        if hr_mode == "flat":
            hr_val = 152 + rng.gauss(0, 0.5)
        else:
            hr_target = 98 + 82 * min(1.15, power / power_w)
            hr += (hr_target - hr) / 22.0 + rng.gauss(0, 0.7 * max(noise, 0.4))
            hr_val = hr
        _, la, lo, el = _at(segment, d)
        la += rng.gauss(0, GPS_NOISE_M * noise) / 111320.0
        lo += rng.gauss(0, GPS_NOISE_M * noise) / (111320.0 * math.cos(math.radians(la)))
        pts.append({
            "ts": float(t), "lat": la, "lon": lo,
            "ele": el + rng.gauss(0, ELE_NOISE_M * noise),
            "hr": int(round(hr_val)),
            "cad": int(max(50, 86 + rng.gauss(0, 4 * max(noise, 0.2)))),
        })
    return pts


def smoothed_dists(points, half_window=2):
    """Per-point distance from the previous point, measured on rolling-mean
    positions — the platform denoises GPS before computing kinematics."""
    n = len(points)
    if n == 0:
        return []
    sm = []
    for i in range(n):
        a, b = max(0, i - half_window), min(n, i + half_window + 1)
        la = sum(p["lat"] for p in points[a:b]) / (b - a)
        lo = sum(p["lon"] for p in points[a:b]) / (b - a)
        sm.append((la, lo))
    out = [0.0]
    for i in range(1, n):
        out.append(haversine_m(sm[i - 1][0], sm[i - 1][1], sm[i][0], sm[i][1]))
    return out


def ride_stats(points):
    """Elapsed/moving time, distance, speeds — computed like the platform would."""
    if len(points) < 2:
        return {"elapsed_s": 0, "moving_s": 0, "dist_m": 0.0, "avg_kmh": 0.0, "moving_kmh": 0.0}
    dist = 0.0
    moving = 0.0
    d_list = smoothed_dists(points)
    for i in range(1, len(points)):
        d = d_list[i]
        dt = points[i]["ts"] - points[i - 1]["ts"]
        dist += d
        if dt > 0 and d / dt > 0.9:
            moving += dt
    elapsed = points[-1]["ts"] - points[0]["ts"]
    return {
        "elapsed_s": round(elapsed, 1),
        "moving_s": round(moving, 1),
        "dist_m": round(dist, 1),
        "avg_kmh": round(dist / elapsed * 3.6, 2) if elapsed else 0.0,
        "moving_kmh": round(dist / moving * 3.6, 2) if moving else 0.0,
    }

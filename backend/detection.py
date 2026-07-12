"""The audit suite — deterministic forensic checks, written as SQL over the
trackpoints table. Kinematics are derived in-query from positions and
timestamps (the two things an upload can't hide), smoothed over 5-second
windows to tolerate real GPS noise.

Physics inversion: P = (Crr + grade) * m * g * v + k * v^3, k = 0.19616.
"""
from . import db

# Rolling kinematics: speed over a 5 s window, gradient over a 10 s window
# (elevation is noisier than position, so it gets the longer baseline).
KIN = """
WITH base AS (
  SELECT idx, ts, ele, hr, cad, dist_m
  FROM trackpoints WHERE activity_id = ?
), w AS (
  SELECT idx, ts, ele, hr, cad, dist_m,
    sum(dist_m) OVER (ORDER BY idx ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS d5,
    ts  - lag(ts, 5)  OVER (ORDER BY idx) AS t5,
    sum(dist_m) OVER (ORDER BY idx ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS d10,
    ele - lag(ele, 10) OVER (ORDER BY idx) AS e10
  FROM base
), kin AS (
  SELECT idx, ts, hr, cad, d5, t5,
    CASE WHEN t5 > 0 THEN d5 / t5 END AS v,
    CASE WHEN d10 > 1 THEN e10 / d10 END AS grade
  FROM w
  WHERE t5 IS NOT NULL AND t5 > 0
)
"""

# Instantaneous estimates are noisy; audits judge 30-second rolling power,
# the same smoothing real performance analysts use. Descents are excluded —
# coasting and braking make power estimates meaningless below ~-0.8% grade,
# which is exactly the blind spot a clever cheat exploits.
WKG = """
, pw AS (
  SELECT idx, ts, hr, v, grade,
    greatest((0.005 + grade) * {mass} * 9.81 * v + 0.19616 * v * v * v, 0) / {mass} AS wkg_i
  FROM kin
  WHERE v IS NOT NULL AND grade IS NOT NULL AND v > 1.0 AND grade > -0.008
), pw30 AS (
  SELECT idx, ts, hr,
    avg(wkg_i) OVER (ORDER BY idx ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS wkg
  FROM pw
)
"""


def _one(sql, params):
    rows = db.query(sql, params)
    return rows[0] if rows else None


def check_timestamps(activity_id, params, ctx):
    row = _one(
        """
        SELECT min(dt), max(dt), sum(CASE WHEN dt <= 0 THEN 1 ELSE 0 END) FROM (
          SELECT ts - lag(ts) OVER (ORDER BY idx) AS dt
          FROM trackpoints WHERE activity_id = ?
        ) WHERE dt IS NOT NULL
        """, [activity_id])
    min_dt, max_dt, bad = row
    passed = (bad or 0) == 0
    return {
        "name": "timestamps", "title": "Timestamp integrity",
        "passed": bool(passed),
        "detail": "Timestamps are monotonic." if passed
                  else f"{bad} non-monotonic timestamp(s) — the file was hand-edited.",
        "evidence": {"min_dt": min_dt, "max_dt": max_dt, "non_monotonic": bad},
    }


def check_max_speed(activity_id, params, ctx):
    limit = float(params.get("limit", 16.0))
    row = _one(KIN + "SELECT max(v), quantile_cont(v, 0.99) FROM kin WHERE v IS NOT NULL",
               [activity_id])
    vmax, p99 = row
    val = p99 or 0.0
    passed = val <= limit
    return {
        "name": "max_speed", "title": "Speed plausibility",
        "passed": bool(passed),
        "detail": (f"Peak sustained speed {val*3.6:.1f} km/h is within human range."
                   if passed else
                   f"Peak sustained speed {val*3.6:.1f} km/h exceeds the plausible "
                   f"{limit*3.6:.0f} km/h for this segment."),
        "evidence": {"v_p99_ms": round(val, 2), "v_max_ms": round(vmax or 0, 2),
                     "limit_ms": limit},
    }


def check_power_wkg(activity_id, params, ctx):
    limit = float(params.get("limit", 5.5))
    mass = ctx["mass"]
    sql = (KIN + WKG.format(mass=mass) +
           "SELECT quantile_cont(wkg, 0.98), max(wkg) FROM pw30")
    row = _one(sql, [activity_id])
    p98, wmax = row
    val = p98 or 0.0
    passed = val <= limit
    return {
        "name": "power_wkg", "title": "Power-to-weight forensics",
        "passed": bool(passed),
        "detail": (f"Estimated effort peaks at {val:.1f} W/kg — believable for this rider."
                   if passed else
                   f"Sustained {val:.1f} W/kg estimated from speed and gradient. "
                   f"World Tour pros hold ~{limit:.1f}. This rider does not."),
        "evidence": {"wkg_p98": round(val, 2), "wkg_max": round(wmax or 0, 2),
                     "limit": limit},
    }


def wkg_p98(activity_id, mass):
    sql = (KIN + WKG.format(mass=mass) +
           "SELECT quantile_cont(wkg, 0.98) FROM pw30")
    row = _one(sql, [activity_id])
    return (row[0] if row else None) or 0.0


def check_rider_baseline(activity_id, params, ctx):
    """Not 'is this humanly possible' but 'is this possible for THIS rider' —
    the file is judged against the account's own uploaded history."""
    margin = float(params.get("margin", 1.12))
    mass = ctx["mass"]
    history = ctx.get("history_wkg_p98") or (ctx["ftp"] / mass)
    limit = history * margin
    p98 = wkg_p98(activity_id, mass)
    passed = p98 <= limit
    return {
        "name": "rider_baseline", "title": "Rider history consistency",
        "passed": bool(passed),
        "detail": (f"Effort ({p98:.2f} W/kg) is consistent with this rider's history."
                   if passed else
                   f"This file needs {p98:.2f} W/kg sustained. Every prior upload on "
                   f"this account tops out near {history:.2f}. Riders improve "
                   "gradually; files improve instantly."),
        "evidence": {"wkg_p98": round(p98, 2), "history_limit": round(limit, 2),
                     "account_history_wkg": round(history, 2)},
    }


def check_accel_spikes(activity_id, params, ctx):
    limit = float(params.get("limit", 4.0))
    sql = KIN + """
    , acc AS (
      SELECT idx, v - lag(v) OVER (ORDER BY idx) AS a
      FROM kin WHERE v IS NOT NULL
    )
    SELECT max(abs(a)), sum(CASE WHEN abs(a) > ? THEN 1 ELSE 0 END) FROM acc WHERE a IS NOT NULL
    """
    row = _one(sql, [activity_id, limit])
    amax, n_over = row
    passed = (n_over or 0) == 0
    return {
        "name": "accel_spikes", "title": "Acceleration analysis",
        "passed": bool(passed),
        "detail": ("No physics-defying accelerations." if passed else
                   f"{n_over} acceleration spike(s) up to {amax:.1f} m/s² — "
                   "bicycles don't teleport. Splice seams do."),
        "evidence": {"a_max": round(amax or 0, 2), "spikes": n_over, "limit": limit},
    }


def check_smoothness(activity_id, params, ctx):
    """Median |accel|, not stddev — a stddev measures terrain variety (a few
    big grade-transition steps dominate it); the median isolates the
    per-second device noise a real recording can't avoid."""
    min_mad = float(params.get("min_mad", 0.05))
    sql = KIN + """
    , acc AS (
      SELECT v - lag(v) OVER (ORDER BY idx) AS a
      FROM kin WHERE v IS NOT NULL AND v > 1.0
    )
    SELECT median(abs(a)) FROM acc WHERE a IS NOT NULL
    """
    row = _one(sql, [activity_id])
    mad = (row[0] if row else None) or 0.0
    passed = mad >= min_mad
    return {
        "name": "smoothness", "title": "Signal noise analysis",
        "passed": bool(passed),
        "detail": ("Natural device jitter present — recorded by a real unit." if passed else
                   f"Speed signal is too clean (median |Δv|={mad:.3f} m/s). Real "
                   "devices jitter every single second; generated files don't."),
        "evidence": {"speed_noise_mad": round(mad, 4), "min_mad": min_mad},
    }


def check_hr_flat(activity_id, params, ctx):
    min_sd = float(params.get("min_sd", 2.5))
    row = _one("SELECT stddev_samp(hr), avg(hr) FROM trackpoints WHERE activity_id = ? AND hr > 0",
               [activity_id])
    sd, avg = row
    sd = sd or 0.0
    passed = sd >= min_sd
    return {
        "name": "hr_flat", "title": "Heart-rate variability",
        "passed": bool(passed),
        "detail": ("Heart rate shows normal physiological variation." if passed else
                   f"Heart rate is a flat line at ~{avg:.0f} bpm (σ={sd:.1f}). "
                   "Hearts respond to hills. This one didn't."),
        "evidence": {"hr_sd": round(sd, 2), "hr_avg": round(avg or 0, 1), "min_sd": min_sd},
    }


def check_hr_correlation(activity_id, params, ctx):
    min_corr = float(params.get("min_corr", 0.25))
    mass = ctx["mass"]
    sql = (KIN + WKG.format(mass=mass) +
           "SELECT corr(hr, wkg), count(*) FROM pw30 WHERE hr > 0")
    row = _one(sql, [activity_id])
    c, n = row
    c = c if c is not None else 0.0
    passed = c >= min_corr or (n or 0) < 120
    return {
        "name": "hr_correlation", "title": "Cardiac response coupling",
        "passed": bool(passed),
        "detail": (f"Heart rate tracks effort (r={c:.2f})." if passed else
                   f"Heart rate is decoupled from effort (r={c:.2f}). "
                   "The legs climbed; the heart didn't notice."),
        "evidence": {"corr": round(c, 3), "min_corr": min_corr, "n": n},
    }


def check_elevation_match(activity_id, params, ctx):
    max_m = float(params.get("max_m", 6.0))
    scale = ctx.get("profile_scale", 1.0)
    sql = """
    WITH tp AS (
      SELECT idx, ele, sum(dist_m) OVER (ORDER BY idx) * ? AS cum
      FROM trackpoints WHERE activity_id = ?
    )
    SELECT avg(abs(tp.ele - p.ele)), count(*)
    FROM tp
    JOIN segment_profile p
      ON p.game_id = ? AND p.level = ?
     AND p.dist_bucket = CAST(floor(tp.cum / 10) AS INTEGER) * 10
    """
    row = _one(sql, [scale, activity_id, ctx["game_id"], ctx["level"]])
    diff, n = row
    diff = diff if diff is not None else 999.0
    passed = diff <= max_m
    return {
        "name": "elevation_match", "title": "Terrain cross-reference",
        "passed": bool(passed),
        "detail": (f"Elevation matches the real mountain (Δ {diff:.1f} m avg)." if passed else
                   f"Track floats {diff:.1f} m off the actual terrain model. "
                   "The road exists; this ride didn't happen on it."),
        "evidence": {"avg_ele_diff_m": round(diff, 2), "max_m": max_m, "matched_points": n},
    }


def check_snapshot_diff(activity_id, params, ctx):
    """Time Travel: compare current trackpoints against the file as it existed
    at upload time. The storage backend owns how the original is recovered —
    DuckDB via a snapshot table, Snowflake via AT(TIMESTAMP => ...)."""
    changed = db.snapshot_changed_count(activity_id)
    passed = changed == 0
    return {
        "name": "snapshot_diff", "title": "Historical record comparison",
        "passed": bool(passed),
        "detail": ("Upload matches the historical record." if passed else
                   f"{changed} trackpoint(s) differ from the file as originally uploaded. "
                   "You edited it after the flag. The database remembers."),
        "evidence": {"changed_points": changed},
    }


CHECKS = {
    "timestamps": check_timestamps,
    "max_speed": check_max_speed,
    "power_wkg": check_power_wkg,
    "rider_baseline": check_rider_baseline,
    "accel_spikes": check_accel_spikes,
    "smoothness": check_smoothness,
    "hr_flat": check_hr_flat,
    "hr_correlation": check_hr_correlation,
    "elevation_match": check_elevation_match,
    "snapshot_diff": check_snapshot_diff,
}

# Manual review re-examines the sensory checks with stricter thresholds;
# physiology baselines stay fixed (tightening those would flag honest riders).
REVIEW_TIGHTENS = ("max_speed", "accel_spikes", "smoothness", "elevation_match")


def tightened(checks, factor):
    out = {}
    for name, params in checks.items():
        q = dict(params or {})
        if name in REVIEW_TIGHTENS:
            if "limit" in q:
                q["limit"] = q["limit"] * factor
            if "max_m" in q:
                q["max_m"] = q["max_m"] * factor
            if "min_sd" in q:
                q["min_sd"] = q["min_sd"] / factor
            if "min_mad" in q:
                q["min_mad"] = q["min_mad"] / factor
        out[name] = q
    return out


def run_checks(activity_id, checks_cfg, ctx):
    results = []
    for name, params in checks_cfg.items():
        results.append(CHECKS[name](activity_id, params or {}, ctx))
    return results

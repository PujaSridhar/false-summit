"""End-to-end smoke test + threshold calibration readout.

Proves: L1 honest upload loses, trimmed upload wins clean;
L2 modest juice wins, greedy juice gets caught by physics.
Prints honest-ride metric distributions for threshold tuning.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# fresh db each run
from backend import db
if os.path.exists(db.DB_PATH):
    os.remove(db.DB_PATH)

from backend import game


def show(tag, resp):
    s = resp["stats"]
    print(f"\n=== {tag} ===")
    print(f"  outcome={resp['outcome']}  elapsed={s['elapsed_s']}s  "
          f"rival={resp['rival_time_s']}s  dist={s['dist_m']}m  avg={s['avg_kmh']}km/h")
    for c in resp["checks"]:
        mark = "PASS" if c["passed"] else "FAIL"
        print(f"  [{mark}] {c['title']}: {c['detail']}  {c['evidence']}")
    print(f"  verdict: {resp['verdict']}")
    return resp


def calibrate(gid):
    """Print honest-ride forensic metrics (what the checks would see)."""
    from backend.detection import KIN, WKG
    from backend.levels import RIDER
    import uuid
    g = game.GAMES[gid]
    aid = "cal_" + uuid.uuid4().hex[:8]
    db.insert_activity(aid, gid, g["level"], "calibration", g["honest"])
    q = lambda sql, p: db.query(sql, p)
    p99 = q(KIN + "SELECT quantile_cont(v,0.99), max(v) FROM kin WHERE v IS NOT NULL", [aid])[0]
    wkg = q(KIN + WKG.format(mass=RIDER["mass"]) +
            "SELECT quantile_cont(wkg,0.98), max(wkg) FROM pw30", [aid])[0]
    acc = q(KIN + ", acc AS (SELECT v - lag(v) OVER (ORDER BY idx) AS a FROM kin WHERE v IS NOT NULL) "
            "SELECT max(abs(a)), stddev_samp(a) FROM acc WHERE a IS NOT NULL", [aid])[0]
    hr = q("SELECT stddev_samp(hr) FROM trackpoints WHERE activity_id = ? AND hr > 0", [aid])[0]
    print(f"  honest L{g['level']}: v_p99={p99[0]:.2f} v_max={p99[1]:.2f} "
          f"wkg_p98={wkg[0]:.2f} wkg_max={wkg[1]:.2f} "
          f"a_max={acc[0]:.2f} a_sd={acc[1]:.3f} hr_sd={hr[0]:.2f}")


print("== create game ==")
st = game.create_game()
gid = st["id"]
print(f"game={gid} L1 rival={st['level']['rival_time_s']}s "
      f"honest elapsed={st['honest_stats']['elapsed_s']}s moving={st['honest_stats']['moving_s']}s")
calibrate(gid)

# L1: honest upload should lose (coffee stop), trim should win
r = show("L1 honest upload", game.upload(gid, []))
assert r["outcome"] == "too_slow", "honest L1 upload should lose to rival"

r = show("L1 trimmed", game.upload(gid, [{"tool": "trim_stops", "params": {}}]))
assert r["outcome"] == "win", "trimmed L1 should win"

# now on L2
st = game.state(gid)
assert st["level"]["id"] == 2
print(f"\nL2 rival={st['level']['rival_time_s']}s honest moving={st['honest_stats']['moving_s']}s")
calibrate(gid)

r = show("L2 greedy juice 25%", game.upload(gid, [{"tool": "scale_time", "params": {"pct": 25}}]))
assert r["outcome"] == "caught", "25% juice should be caught"

r = show("L2 modest juice 8%", game.upload(gid, [{"tool": "scale_time", "params": {"pct": 8}}]))
assert r["outcome"] == "win", "8% juice should win L2"

# ---- L3: Col du Faux — sector juice on the descent -------------------------
st = game.state(gid)
assert st["level"]["id"] == 3
hs = st["honest_stats"]
print(f"\nL3 rival={st['level']['rival_time_s']}s honest elapsed={hs['elapsed_s']}s moving={hs['moving_s']}s")
calibrate(gid)

r = show("L3 overall juice 12% (history should flag)",
         game.upload(gid, [{"tool": "scale_time", "params": {"pct": 12}}]))
assert r["outcome"] == "caught", "overall juice should trip rider_baseline"

r = show("L3 descent juice 45% (speed sanity should flag)",
         game.upload(gid, [{"tool": "scale_time_range",
                            "params": {"pct": 45, "from_frac": 0.78, "to_frac": 1.0}}]))
assert r["outcome"] == "caught", "45% descent juice should trip max_speed"

r = show("L3 descent 30% + overall 5% (clean path)",
         game.upload(gid, [{"tool": "scale_time_range",
                            "params": {"pct": 30, "from_frac": 0.78, "to_frac": 1.0}},
                           {"tool": "scale_time", "params": {"pct": 5}}]))
print(f"  -> clean path outcome: {r['outcome']} "
      f"(elapsed {r['stats']['elapsed_s']} vs rival {r['rival_time_s']})")
assert r["outcome"] == "win", "descent 30% + overall 5% should win L3"

# ---- L4: The Phantom Ride — synthesis ---------------------------------------
st = game.state(gid)
assert st["level"]["id"] == 4
print(f"\nL4 rival={st['level']['rival_time_s']}s honest moving={st['honest_stats']['moving_s']}s")
calibrate(gid)

r = show("L4 naive synthesis (constant pace, clean signal, flat HR)",
         game.upload(gid, [{"tool": "synthesize",
                            "params": {"faster_pct": 3, "humanize": 0,
                                       "hr_mode": "flat", "terrain_aware": False}}]))
assert r["outcome"] == "caught", "naive synthesis should be caught"

r = show("L4 smart synthesis, forgot the noise",
         game.upload(gid, [{"tool": "synthesize",
                            "params": {"faster_pct": 3, "humanize": 10,
                                       "hr_mode": "modeled", "terrain_aware": True}}]))
assert r["outcome"] == "caught", "low-humanize synthesis should be caught by smoothness"

r = show("L4 full craft synthesis (clean path)",
         game.upload(gid, [{"tool": "synthesize",
                            "params": {"faster_pct": 2, "humanize": 80,
                                       "hr_mode": "modeled", "terrain_aware": True}}]))
assert r["outcome"] == "win", "crafted synthesis should win L4"

# ---- L5: The Crown — manual review + Time Travel ----------------------------
st = game.state(gid)
assert st["level"]["id"] == 5
hs = st["honest_stats"]
print(f"\nL5 rival={st['level']['rival_time_s']}s honest elapsed={hs['elapsed_s']}s moving={hs['moving_s']}s")
calibrate(gid)

greedy = [{"tool": "trim_stops", "params": {}},
          {"tool": "scale_time_range", "params": {"pct": 33, "from_frac": 0.88, "to_frac": 1.0}},
          {"tool": "scale_time", "params": {"pct": 6}}]
r = show("L5 greedy upload", game.upload(gid, greedy))
assert r["outcome"] == "under_review", "greedy L5 should pass audit then hit review"

r = show("L5 greedy -> EDIT the flagged file (Time Travel trap)",
         game.edit_upload(gid, [{"tool": "scale_time", "params": {"pct": 1}}]))
assert r["outcome"] == "caught", "editing under review must be caught by snapshot diff"
assert any(c["name"] == "snapshot_diff" and not c["passed"] for c in r["checks"]), \
    "snapshot_diff should be the killer"

clean = [{"tool": "trim_stops", "params": {}},
         {"tool": "scale_time_range", "params": {"pct": 24, "from_frac": 0.88, "to_frac": 1.0}},
         {"tool": "scale_time", "params": {"pct": 5}}]
r = show("L5 conservative upload", game.upload(gid, clean))
print(f"  -> conservative outcome: {r['outcome']} "
      f"(elapsed {r['stats']['elapsed_s']} vs rival {r['rival_time_s']})")
assert r["outcome"] == "under_review", "conservative L5 should reach review"

r = show("L5 conservative -> STAND PAT (survive tightened review)",
         game.review_action(gid, "stand"))
assert r["outcome"] == "win", "conservative file should survive review"
assert r.get("finished"), "winning L5 should finish the game"

print("\nSMOKE OK — all five levels")

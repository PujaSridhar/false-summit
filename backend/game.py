"""Game orchestration: state, preview, upload/audit flow."""
import uuid

from . import ai, db, detection, narrative, voice
from .cheats import apply_ops
from .detection import run_checks, tightened
from .levels import RIDER, level_cfg
from .physics import build_segment, simulate_ride, ride_stats

GAMES = {}


def _seed(gid, level):
    # Deterministic per level (independent of game id): the five rides are a
    # hand-calibrated, reliable scenario. Narrative variety comes from Gemini,
    # not from the physics — so the game plays identically every time while
    # still feeling fresh. Keeps clean paths robustly winnable across backends.
    return 4200 + level * 17


def _setup_level(game, level_id):
    cfg = level_cfg(level_id)
    if cfg is None:
        game["state"] = "finished"
        return
    seed = _seed(game["id"], level_id)
    segment = build_segment(cfg["segment_name"], cfg["profile"], seed=seed)
    honest = simulate_ride(segment, RIDER, seed=seed + 1, stop=cfg["stop"])
    stats = ride_stats(honest)
    rival_time = round(stats["moving_s"] * cfg["rival_factor"])
    game.update({
        "level": level_id,
        "segment": segment,
        "honest": honest,
        "honest_stats": stats,
        "rival_time_s": rival_time,
        "state": "playing",
    })
    db.insert_profile(game["id"], level_id, segment)
    # the honest ride IS the account's history — baselines self-calibrate
    hist_aid = uuid.uuid4().hex[:12]
    db.insert_activity(hist_aid, game["id"], level_id, "history", honest)
    game["history_wkg"] = detection.wkg_p98(hist_aid, RIDER["mass"])
    # generate the rival taunt + voice once (cached), not on every state poll
    taunt = ai.taunt(cfg["id"], cfg["segment_name"], narrative.RIVAL)
    game["taunt"] = taunt
    game["taunt_audio"] = voice.say(taunt, role="rival")


def create_game():
    gid = uuid.uuid4().hex[:12]
    game = {"id": gid, "wins": [], "flags": 0, "state": "playing", "dossier": []}
    GAMES[gid] = game
    _setup_level(game, 1)
    return state(gid)


def _record(game, cfg, ops, outcome, results):
    """Append this attempt to the case file that feeds the final report."""
    game["dossier"].append({
        "level": cfg["id"],
        "segment": cfg["segment_name"],
        "tools": [o["tool"] for o in ops],
        "outcome": outcome,
        "checks": [{"name": r["name"], "passed": r["passed"]} for r in results],
    })


def _series(points, every=5):
    """Downsampled series for the frontend charts/map."""
    pts = points[::every]
    cum = 0.0
    out = {"t": [], "lat": [], "lon": [], "ele": [], "v_kmh": [], "hr": [], "dist_km": []}
    from .physics import haversine_m
    prev = None
    for p in pts:
        if prev is not None:
            d = haversine_m(prev["lat"], prev["lon"], p["lat"], p["lon"])
            dt = p["ts"] - prev["ts"]
            cum += d
            out["v_kmh"].append(round(d / dt * 3.6, 1) if dt > 0 else 0.0)
        else:
            out["v_kmh"].append(0.0)
        out["t"].append(round(p["ts"], 1))
        out["lat"].append(round(p["lat"], 6))
        out["lon"].append(round(p["lon"], 6))
        out["ele"].append(round(p["ele"], 1))
        out["hr"].append(p["hr"])
        out["dist_km"].append(round(cum / 1000, 3))
        prev = p
    return out


def state(gid):
    game = GAMES[gid]
    if game["state"] == "finished":
        return {"id": gid, "state": "finished", "wins": game["wins"], "flags": game["flags"]}
    cfg = level_cfg(game["level"])
    return {
        "id": gid,
        "state": game["state"],
        "wins": game["wins"],
        "flags": game["flags"],
        "under_review": bool(game.get("pending_review")),
        "level": {
            "id": cfg["id"], "title": cfg["title"],
            "segment_name": cfg["segment_name"],
            "brief": cfg["brief"], "intel": cfg["intel"],
            "taunt": game.get("taunt") or narrative.taunt(cfg["id"]),
            "taunt_audio": game.get("taunt_audio"),
            "tools": cfg["tools"],
            "checks": [{"name": k} for k in cfg["checks"]],
            "rival": narrative.RIVAL,
            "rival_time_s": game["rival_time_s"],
            "length_m": round(game["segment"]["length_m"]),
        },
        "honest_stats": game["honest_stats"],
        "series": _series(game["honest"]),
    }


def _inject(game, ops):
    """Some tools need game context (the rival's time drives synthesis)."""
    for op in ops:
        if op["tool"] == "synthesize":
            op["params"].setdefault("rival_time_s", game["rival_time_s"])
    return ops


def _ctx(game, stats):
    canonical_len = game["segment"]["length_m"]
    total_len = stats["dist_m"] or canonical_len
    return {
        "game_id": game["id"],
        "level": game["level"],
        "mass": RIDER["mass"],
        "ftp": RIDER["ftp"],
        "history_wkg_p98": game.get("history_wkg"),
        "profile_scale": canonical_len / total_len,
    }


def preview(gid, ops):
    game = GAMES[gid]
    doctored = apply_ops(game["honest"], game["segment"], _inject(game, ops))
    return {
        "stats": ride_stats(doctored),
        "rival_time_s": game["rival_time_s"],
        "series": _series(doctored),
    }


def _advance_on_win(game, resp):
    game["wins"].append(game["level"])
    _setup_level(game, game["level"] + 1)
    resp["advanced"] = game["state"] == "playing"
    resp["finished"] = game["state"] == "finished"
    return resp


def upload(gid, ops):
    game = GAMES[gid]
    if game["state"] == "finished":
        raise ValueError("the season is over")
    cfg = level_cfg(game["level"])
    doctored = apply_ops(game["honest"], game["segment"], _inject(game, ops))
    stats = ride_stats(doctored)

    aid = uuid.uuid4().hex[:12]
    db.insert_activity(aid, gid, game["level"], "upload", doctored)
    db.insert_activity(aid, gid, game["level"], "upload", doctored, snapshot=True)

    ctx = _ctx(game, stats)
    results = run_checks(aid, cfg["checks"], ctx)
    db.record_audit(aid, results)

    caught = any(not r["passed"] for r in results)
    beat_rival = stats["elapsed_s"] < game["rival_time_s"]
    outcome = "caught" if caught else ("win" if beat_rival else "too_slow")

    resp = {
        "activity_id": aid,
        "outcome": outcome,
        "stats": stats,
        "rival_time_s": game["rival_time_s"],
        "checks": results,
        "verdict": narrative.verdict(caught, beat_rival),
    }
    if outcome == "caught":
        game["flags"] += 1
        _record(game, cfg, ops, "caught", results)
        return resp

    if outcome == "win" and cfg.get("review"):
        game["pending_review"] = {
            "activity_id": aid,
            "points": doctored,
            "stats": stats,
            "ops": ops,
            "results": results,
        }
        resp["outcome"] = "under_review"
        resp["verdict"] = narrative.UNDER_REVIEW
        return resp

    if outcome == "win":
        _record(game, cfg, ops, "win", results)
        _advance_on_win(game, resp)
    else:
        _record(game, cfg, ops, "too_slow", results)
    return resp


def review_action(gid, action):
    """L5 manual review: stand (tightened re-audit) or withdraw (walk away)."""
    game = GAMES[gid]
    pending = game.get("pending_review")
    if not pending:
        raise ValueError("no upload is under review")
    cfg = level_cfg(game["level"])
    aid = pending["activity_id"]

    if action == "withdraw":
        game.pop("pending_review")
        _record(game, cfg, pending["ops"], "withdrawn", pending["results"])
        return {
            "outcome": "withdrawn",
            "verdict": narrative.WITHDRAWN,
            "checks": [],
            "stats": pending["stats"],
            "rival_time_s": game["rival_time_s"],
        }

    # stand pat — the reviewer re-runs the sensory checks, tighter
    tight = tightened(cfg["checks"], cfg["review"]["tighten"])
    ctx = _ctx(game, pending["stats"])
    results = run_checks(aid, tight, ctx)
    db.record_audit(aid, results)
    caught = any(not r["passed"] for r in results)
    game.pop("pending_review")

    resp = {
        "activity_id": aid,
        "outcome": "caught" if caught else "win",
        "stats": pending["stats"],
        "rival_time_s": game["rival_time_s"],
        "checks": results,
        "verdict": narrative.REVIEW_CAUGHT if caught else narrative.REVIEW_SURVIVED,
    }
    _record(game, cfg, pending["ops"], resp["outcome"], results)
    if caught:
        game["flags"] += 1
    else:
        _advance_on_win(game, resp)
    return resp


def edit_upload(gid, ops):
    """Editing a file under review. The snapshot diff is waiting."""
    game = GAMES[gid]
    pending = game.get("pending_review")
    if not pending:
        raise ValueError("no upload is under review")
    cfg = level_cfg(game["level"])
    aid = pending["activity_id"]

    edited = apply_ops(pending["points"], game["segment"], _inject(game, ops))
    stats = ride_stats(edited)
    db.replace_activity_points(aid, edited)

    tight = tightened(cfg["checks"], cfg["review"]["tighten"])
    ctx = _ctx(game, stats)
    results = run_checks(aid, tight, ctx)
    db.record_audit(aid, results)
    caught = any(not r["passed"] for r in results)
    beat_rival = stats["elapsed_s"] < game["rival_time_s"]
    game.pop("pending_review")

    resp = {
        "activity_id": aid,
        "outcome": "caught" if caught else ("win" if beat_rival else "too_slow"),
        "stats": stats,
        "rival_time_s": game["rival_time_s"],
        "checks": results,
        "verdict": narrative.EDIT_CAUGHT if caught else narrative.REVIEW_SURVIVED,
    }
    _record(game, cfg, [{"tool": "edit_under_review"}], resp["outcome"], results)
    if caught:
        game["flags"] += 1
    elif resp["outcome"] == "win":
        _advance_on_win(game, resp)
    return resp


def report(gid):
    """The closing case file — generated from the dossier, optionally voiced."""
    game = GAMES[gid]
    if "report" in game:
        return game["report"]
    rep = ai.investigation_report(game.get("dossier", []), narrative.RIVAL)
    rep["audio"] = voice.say(voice.report_script(rep), role="auditor")
    rep["crowns"] = len(game["wins"])
    rep["flags"] = game["flags"]
    game["report"] = rep
    return rep

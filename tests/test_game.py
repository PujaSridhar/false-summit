"""Game orchestration: happy path, state machine, illegal transitions."""
import pytest

from backend import game

TRIM = [{"tool": "trim_stops", "params": {}}]
JUICE8 = [{"tool": "scale_time", "params": {"pct": 8}}]
L3_CLEAN = [{"tool": "scale_time_range", "params": {"pct": 30, "from_frac": 0.78, "to_frac": 1.0}},
            {"tool": "scale_time", "params": {"pct": 5}}]
L4_SYNTH = [{"tool": "synthesize", "params": {"faster_pct": 2, "humanize": 80,
                                              "hr_mode": "modeled", "terrain_aware": True}}]
L5_CLEAN = [{"tool": "trim_stops", "params": {}},
            {"tool": "scale_time_range", "params": {"pct": 24, "from_frac": 0.88, "to_frac": 1.0}},
            {"tool": "scale_time", "params": {"pct": 5}}]


def _new():
    return game.create_game()["id"]


def test_create_game_starts_at_level_one():
    st = game.create_game()
    assert st["state"] == "playing"
    assert st["level"]["id"] == 1
    assert st["wins"] == [] and st["flags"] == 0


def test_full_happy_path_to_finish():
    gid = _new()
    assert game.upload(gid, TRIM)["outcome"] == "win"
    assert game.upload(gid, JUICE8)["outcome"] == "win"
    assert game.upload(gid, L3_CLEAN)["outcome"] == "win"
    assert game.upload(gid, L4_SYNTH)["outcome"] == "win"
    assert game.upload(gid, L5_CLEAN)["outcome"] == "under_review"
    final = game.review_action(gid, "stand")
    assert final["outcome"] == "win"
    assert final["finished"] is True
    assert game.state(gid)["state"] == "finished"


def test_honest_upload_loses_level_one():
    gid = _new()
    assert game.upload(gid, [])["outcome"] == "too_slow"


def test_greedy_juice_is_caught():
    gid = _new()
    game.upload(gid, TRIM)  # advance to L2
    r = game.upload(gid, [{"tool": "scale_time", "params": {"pct": 25}}])
    assert r["outcome"] == "caught"
    assert game.state(gid)["flags"] == 1


def test_edit_trap_caught_by_snapshot():
    gid = _new()
    for ops in (TRIM, JUICE8, L3_CLEAN, L4_SYNTH):
        game.upload(gid, ops)
    game.upload(gid, L5_CLEAN)  # -> under_review
    r = game.edit_upload(gid, [{"tool": "scale_time", "params": {"pct": 1}}])
    assert r["outcome"] == "caught"
    assert any(c["name"] == "snapshot_diff" and not c["passed"] for c in r["checks"])


def test_dossier_accumulates():
    gid = _new()
    game.upload(gid, TRIM)
    game.upload(gid, JUICE8)
    assert len(game.GAMES[gid]["dossier"]) == 2


def test_review_without_pending_raises():
    gid = _new()
    with pytest.raises(ValueError):
        game.review_action(gid, "stand")


def test_edit_without_pending_raises():
    gid = _new()
    with pytest.raises(ValueError):
        game.edit_upload(gid, TRIM)


def test_upload_after_finished_raises():
    gid = _new()
    for ops in (TRIM, JUICE8, L3_CLEAN, L4_SYNTH):
        game.upload(gid, ops)
    game.upload(gid, L5_CLEAN)
    game.review_action(gid, "stand")  # finishes
    with pytest.raises(ValueError):
        game.upload(gid, TRIM)


def test_report_is_generated_after_finish():
    gid = _new()
    for ops in (TRIM, JUICE8, L3_CLEAN, L4_SYNTH):
        game.upload(gid, ops)
    game.upload(gid, L5_CLEAN)
    game.review_action(gid, "stand")
    rep = game.report(gid)
    assert rep["generated_by"] == "canned"  # no Gemini key in tests
    assert len(rep["findings"]) >= 5
    assert rep["crowns"] == 5


def test_withdraw_returns_to_play_without_flag():
    gid = _new()
    for ops in (TRIM, JUICE8, L3_CLEAN, L4_SYNTH):
        game.upload(gid, ops)
    game.upload(gid, L5_CLEAN)  # under_review
    r = game.review_action(gid, "withdraw")
    assert r["outcome"] == "withdrawn"
    assert game.state(gid)["flags"] == 0
    assert game.state(gid)["level"]["id"] == 5  # still on L5

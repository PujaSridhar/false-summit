"""HTTP layer: every endpoint, happy path and error path."""
import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

TRIM = {"ops": [{"tool": "trim_stops", "params": {}}]}


def _new_game():
    return client.post("/api/games").json()["id"]


def test_config():
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["storage"] == "duckdb"
    assert body["gemini"] is False and body["voice"] is False


def test_create_and_get_state():
    r = client.post("/api/games")
    assert r.status_code == 200
    gid = r.json()["id"]
    st = client.get(f"/api/games/{gid}")
    assert st.status_code == 200
    assert st.json()["level"]["id"] == 1


def test_get_unknown_game_404():
    assert client.get("/api/games/deadbeef").status_code == 404


def test_preview():
    gid = _new_game()
    r = client.post(f"/api/games/{gid}/preview", json=TRIM)
    assert r.status_code == 200
    assert "stats" in r.json()


def test_upload_happy():
    gid = _new_game()
    r = client.post(f"/api/games/{gid}/upload", json=TRIM)
    assert r.status_code == 200
    assert r.json()["outcome"] == "win"


def test_upload_unknown_tool_is_400():
    gid = _new_game()
    r = client.post(f"/api/games/{gid}/upload", json={"ops": [{"tool": "hax", "params": {}}]})
    assert r.status_code == 400
    assert "unknown tool" in r.json()["detail"]


def test_upload_unknown_game_404():
    assert client.post("/api/games/nope/upload", json=TRIM).status_code == 404


def test_review_without_pending_409():
    gid = _new_game()
    r = client.post(f"/api/games/{gid}/review", json={"action": "stand"})
    assert r.status_code == 409


def test_edit_without_pending_409():
    gid = _new_game()
    r = client.post(f"/api/games/{gid}/edit", json=TRIM)
    assert r.status_code == 409


def test_report_unknown_game_404():
    assert client.get("/api/games/nope/report").status_code == 404


def test_empty_ops_preview_ok():
    gid = _new_game()
    r = client.post(f"/api/games/{gid}/preview", json={"ops": []})
    assert r.status_code == 200


def test_malformed_body_422():
    gid = _new_game()
    # ops must be a list of objects with a 'tool' field
    r = client.post(f"/api/games/{gid}/upload", json={"ops": [{"params": {}}]})
    assert r.status_code == 422


def test_frontend_is_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "FALSE" in r.text

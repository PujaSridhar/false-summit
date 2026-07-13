"""FastAPI app — thin HTTP layer over game.py."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai, db, game, voice
from .cheats import TOOLS


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[false-summit] storage={db.BACKEND}  "
          f"gemini={'on' if ai.enabled() else 'off (canned)'}  "
          f"voice={'on' if voice.enabled() else 'off (silent)'}")
    yield


app = FastAPI(title="False Summit", lifespan=lifespan)


@app.get("/api/config")
def config():
    return {"storage": db.BACKEND, "gemini": ai.enabled(), "voice": voice.enabled()}


class Op(BaseModel):
    tool: str
    params: dict | None = None


class OpsBody(BaseModel):
    ops: list[Op] = []


def _ops(body: OpsBody):
    for o in body.ops:
        if o.tool not in TOOLS:
            raise HTTPException(400, f"unknown tool: {o.tool}")
    return [{"tool": o.tool, "params": o.params or {}} for o in body.ops]


@app.post("/api/games")
def new_game():
    return game.create_game()


@app.get("/api/games/{gid}")
def get_state(gid: str):
    if gid not in game.GAMES:
        raise HTTPException(404, "no such game")
    return game.state(gid)


@app.post("/api/games/{gid}/preview")
def preview(gid: str, body: OpsBody):
    if gid not in game.GAMES:
        raise HTTPException(404, "no such game")
    return game.preview(gid, _ops(body))


@app.post("/api/games/{gid}/upload")
def upload(gid: str, body: OpsBody):
    if gid not in game.GAMES:
        raise HTTPException(404, "no such game")
    try:
        return game.upload(gid, _ops(body))
    except ValueError as e:
        raise HTTPException(400, str(e))


class ReviewBody(BaseModel):
    action: str  # "stand" | "withdraw"


@app.post("/api/games/{gid}/review")
def review(gid: str, body: ReviewBody):
    if gid not in game.GAMES:
        raise HTTPException(404, "no such game")
    try:
        return game.review_action(gid, body.action)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/games/{gid}/edit")
def edit(gid: str, body: OpsBody):
    if gid not in game.GAMES:
        raise HTTPException(404, "no such game")
    try:
        return game.edit_upload(gid, _ops(body))
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.get("/api/games/{gid}/report")
def report(gid: str):
    if gid not in game.GAMES:
        raise HTTPException(404, "no such game")
    return game.report(gid)


FRONTEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="static")

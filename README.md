# False Summit

*Every crown has a price.*

A narrative game about passion curdling into fraud: your rival took your
Strava-style segment crown, and you — armed with a GPX editor and bad
intentions — are going to take it back. Each level you doctor your ride
data a little deeper (trim the coffee stop, Digital-EPO the timestamps,
synthesize the whole effort). After every upload, a deterministic
**integrity audit** runs real forensic checks against your file:

- **Power-to-weight forensics** — physics inversion of speed + gradient
- **Signal noise analysis** — real GPS jitters; generated files don't
- **Cardiac response coupling** — hearts respond to hills
- **Terrain cross-reference** — the track must sit on the real mountain
- **Historical record comparison** — edit a flagged file and the
  database remembers (Snowflake Time Travel)

Get caught and you see the auditor's case file: the exact query and the
exact evidence. You learn what fraud detection catches by trying to
beat it — red-teaming for data forensics.

Inspired by real-world "digital doping": Digital EPO, doctored GPX
uploads, and motor-assisted KOM theft are documented problems Strava
polices with ML-based integrity checks.

## Run it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn backend.main:app --port 8000
# open http://127.0.0.1:8000
```

Smoke test / threshold calibration:

```bash
.venv/bin/python scripts/smoke.py
```

## Architecture

- `backend/physics.py` — rider power model; honest rides simulated with
  natural noise (power variation, GPS jitter, HR lag)
- `backend/cheats.py` — the player's tools; mirror real techniques
- `backend/detection.py` — audit suite as SQL over trackpoints
  (window-function kinematics, Snowflake-compatible dialect)
- `backend/db.py` — DuckDB in dev, Snowflake in prod; snapshot tables
  stand in for Time Travel locally
- `backend/levels.py` — each level has a designed clean path and many
  ways to get caught; rival targets derive from the honest ride, so
  levels are provably winnable
- `frontend/` — Leaflet map + Chart.js telemetry + the toolkit

## Tech (DEV Weekend Challenge: Passion Edition)

- **Snowflake** — evidence store; Time Travel powers the final audit
- **Google AI (Gemini)** — narrative generation: rival persona, taunts,
  investigation report
- **ElevenLabs** — voiced rival messages and inner monologue

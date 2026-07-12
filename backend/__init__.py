"""Load .env into the process environment before any submodule reads it.

The storage dispatcher (db.py), ai.py, and voice.py all decide their
behaviour from environment variables at import time, so this has to run
first — importing the `backend` package triggers it."""
import os

_env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(_env):
    with open(_env) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and val and key not in os.environ:
                os.environ[key] = val

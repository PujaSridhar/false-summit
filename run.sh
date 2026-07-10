#!/bin/sh
cd "$(dirname "$0")"
exec .venv/bin/uvicorn backend.main:app --port 8000 "$@"

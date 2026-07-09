#!/usr/bin/env bash
cd "$(dirname "$0")"
URL="${1:-http://127.0.0.1:8765}"
if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python multiplayer/selftest.py "$URL"
fi
exec python3 multiplayer/selftest.py "$URL"

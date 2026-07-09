#!/usr/bin/env bash
# Start SevenBox multiplayer server
set -euo pipefail
cd "$(dirname "$0")"
PORT="${PORT:-8765}"

if [[ ! -x .venv/bin/python ]]; then
  echo "Creating venv…"
  python3 -m venv .venv
  .venv/bin/pip install -q websockets
fi

# If port is busy, free it (old SevenBox instance)
if fuser "${PORT}/tcp" >/dev/null 2>&1; then
  echo "Port ${PORT} busy — stopping old server…"
  fuser -k "${PORT}/tcp" >/dev/null 2>&1 || true
  sleep 0.5
fi

echo "Starting SevenBox on http://127.0.0.1:${PORT}/chipbox.html"
echo "Press Ctrl+C to stop."
exec .venv/bin/python multiplayer/server.py --host 0.0.0.0 --port "${PORT}"

#!/usr/bin/env bash
# Open the SevenBox button launcher (GUI)
cd "$(dirname "$0")"
export DISPLAY="${DISPLAY:-:0}"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -q websockets
fi
exec python3 SevenBox-Launcher.py

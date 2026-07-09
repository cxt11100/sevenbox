@echo off
title SevenBox
cd /d "%~dp0"
wsl -e bash -lc "cd /home/seven/projects/nyx-agent && export DISPLAY=:0 && python3 SevenBox-Launcher.py"
if errorlevel 1 pause

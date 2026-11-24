@echo off
title Dual-Bot Command Center
cd /d "%~dp0"

echo ===========================================================
echo  🤖 Starting Dual-Bot Command Center & Telegram Engines
echo ===========================================================

set PY_EXE=C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe

if not exist "%PY_EXE%" (
    set PY_EXE=python
)

echo Starting Server on http://localhost:8080 ...
start "" "http://localhost:8080"
"%PY_EXE%" app.py

pause

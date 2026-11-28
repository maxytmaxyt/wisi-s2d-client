@echo off
title WISI OR S2D 24/7 Web Control Center
echo ======================================================================
echo   WISI OR S2D – DVB-over-IP 24/7 Web Control Center & Streaming Server
echo ======================================================================
echo.

cd /d "%~dp0\.."

:: Starte den Server auf 0.0.0.0 Port 8888 ohne autom. Browser-Pop-up
echo Starte Server im Hintergrund...
set PYTHONPATH=%~dp0..\src
python -m wisi_s2d.cli.ui --host 0.0.0.0 --port 8888 --no-browser

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Server beendet mit Fehlercode %ERRORLEVEL%.
    pause
)

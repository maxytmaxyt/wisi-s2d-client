@echo off
title WISI OR S2D Web Control Center
echo ======================================================================
echo   WISI OR S2D – DVB-over-IP Web Control Center
echo ======================================================================
echo.
cd /d "%~dp0"
python start_ui.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Fehler beim Starten des Web-Servers.
    pause
)

@echo off
REM Double-click this to launch the TAHMO live dashboard.
REM It starts the local proxy and opens your browser automatically.
cd /d "%~dp0"
python tahmo_server.py
pause

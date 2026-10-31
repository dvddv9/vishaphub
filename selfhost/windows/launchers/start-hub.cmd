@echo off
title VishapHub
if not exist "%USERPROFILE%\.vishaphub\config.env" (
  echo No settings yet - running setup first.
  call "%~dp0setup.cmd"
)
start "" "http://127.0.0.1:8080"
echo VishapHub is running. Close this window to stop it.
"%~dp0python\python.exe" -m hub.cli serve
pause

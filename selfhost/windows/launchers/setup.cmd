@echo off
title VishapHub setup
echo VishapHub setup. Your answers are saved in %USERPROFILE%\.vishaphub\config.env
echo.
"%~dp0python\python.exe" -m hub.cli init --force
if errorlevel 1 (echo. & echo Setup did not finish.) else ("%~dp0python\python.exe" -m hub.cli doctor)
echo.
pause

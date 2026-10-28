@echo off
cd /d "%~dp0"
set PYTHONPATH=src

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python 3.11+ not found: https://www.python.org/downloads/
    pause
    exit /b 1
)

if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

echo vishap-generator: http://127.0.0.1:8787/
start "" http://127.0.0.1:8787/
python -m generator serve
pause

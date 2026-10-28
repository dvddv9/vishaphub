@echo off
cd /d C:\AI\conveyor_app

echo ========================================
echo   Vishap V6.4.0 - Starting
echo   Security analysis for engineering materials
echo ========================================
echo.

REM --- Download Prerequisites ---
echo === Prerequisites (if not installed) ===
echo   Python 3.11+:    https://www.python.org/downloads/
echo   Node.js 18+:     https://nodejs.org/en/download/
echo   Docker Desktop:  https://www.docker.com/products/docker-desktop/
echo   Ollama (LLM):    https://ollama.com/download
echo   Git:             https://git-scm.com/downloads
echo.

REM --- Check Python ---
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python found.
echo.

REM --- Check venv ---
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] .venv not found. Run: python -m venv .venv
    pause
    exit /b 1
)

REM --- Start API ---
echo [1/3] Starting FastAPI (port 5001)...
start "Vishap API" cmd /k "cd /d C:\AI\conveyor_app && .venv\Scripts\activate.bat && python -m src.main"

timeout /t 4 /nobreak >nul

REM --- Start UI ---
echo [2/3] Starting Streamlit (port 8501)...
start "Vishap UI" cmd /k "cd /d C:\AI\conveyor_app && .venv\Scripts\activate.bat && streamlit run src/ui/streamlit_app.py"

timeout /t 6 /nobreak >nul

REM --- Open browser ---
echo [3/3] Opening browser...
start http://localhost:8501

echo.
echo ========================================
echo   Vishap V6.4.0 started!
echo ========================================
echo.
echo API:      http://localhost:5001/docs
echo UI:       http://localhost:8501
echo Grafana:  http://localhost:3001 (if docker compose up)
echo.
echo Two windows opened (API + UI).
echo Close them to stop Vishap.
echo.
pause

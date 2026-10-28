@echo off
REM Vishap dev launcher: backend (5050) + Next.js UI (3000)
setlocal

set VISHAP_HOME=C:\Users\dvddv\projects\vishap
set PROJECT=%VISHAP_HOME%
set VENV=%PROJECT%\.venv\Scripts\python.exe
set UI=%PROJECT%\ui-next

REM 1) Backend (FastAPI on 5050)
start "Vishap Backend" cmd /k "cd /d %PROJECT% && %VENV% -m src.main"

REM 2) Next.js dev server (UI on 3000)
start "Vishap UI" cmd /k "cd /d %UI% && npm run dev"

REM 3) Open browser after a short delay
timeout /t 5 /nobreak >nul
start "" http://localhost:3000

endlocal

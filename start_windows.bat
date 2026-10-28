@echo off
setlocal
cd /d "%~dp0"
echo =====================================
echo  StoryBridge - Local MVP Setup
 echo =====================================
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3.12 -m venv .venv >nul 2>&1
    if not exist ".venv\Scripts\python.exe" py -3.13 -m venv .venv >nul 2>&1
    if not exist ".venv\Scripts\python.exe" py -3.11 -m venv .venv >nul 2>&1
  )
  if not exist ".venv\Scripts\python.exe" python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Python 3.11 or 3.12 or 3.13 is required.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
 echo ERROR: pip package installation failed.
 pause
 exit /b 1
)
echo.
echo Open browser at http://127.0.0.1:8765
start "" "http://127.0.0.1:8765"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8765
pause

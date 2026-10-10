@echo off
TITLE VYBE - Your mood. Your trip. Your VYBE.
cd /d %~dp0
setlocal

REM --- Check Python (prefer py launcher; avoids MS Store stub) ---
set PYCMD=
py --version >nul 2>nul
if not errorlevel 1 (
  set PYCMD=py
) else (
  python --version >nul 2>nul
  if not errorlevel 1 (
    set PYCMD=python
  ) else (
    python3 --version >nul 2>nul
    if not errorlevel 1 set PYCMD=python3
  )
)
if "%PYCMD%"=="" (
  echo [ERROR] Python not found on PATH. Install Python 3.11+ from https://www.python.org/downloads/
  echo         Make sure "Add python.exe to PATH" is checked during install.
  echo         Or install from Microsoft Store, or use the 'py' launcher.
  pause
  exit /b 1
)
echo Using Python: %PYCMD%
%PYCMD% --version

REM --- Create venv on first run ---
if not exist .venv\Scripts\python.exe (
  echo Creating virtual environment...
  %PYCMD% -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
  )
)

set PY=.venv\Scripts\python.exe

REM --- Copy env template on first run ---
if not exist .env (
  if exist .env.example (
    echo Copying .env.example to .env...
    copy .env.example .env >nul
  ) else (
    echo [WARN] .env.example missing, skipping .env creation.
  )
)

REM --- Install dependencies ---
echo Installing dependencies...
%PY% -m pip install --upgrade pip
if errorlevel 1 echo [WARN] pip upgrade failed, continuing...
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip install failed. Check your internet connection.
  pause
  exit /b 1
)

echo.
echo Starting VYBE at http://127.0.0.1:5000 ...
echo Demo logins: traveler@vybe.demo / traveler123 ^| operator@vybe.demo / operator123 ^| admin@vybe.demo / admin123
echo Press Ctrl+C to stop.
echo.
%PY% app.py
if errorlevel 1 (
  echo.
  echo [ERROR] VYBE exited with an error. See output above.
  pause
  exit /b 1
)

pause

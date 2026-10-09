@echo off
TITLE VYBE - Your mood. Your trip. Your VYBE.
cd /d %~dp0

REM Create venv on first run
IF NOT EXIST .venv (
  echo Creating virtual environment...
  python -m venv .venv
)

call .venv\Scripts\activate

REM Copy env template on first run
IF NOT EXIST .env (
  echo Copying .env.example to .env...
  copy .env.example .env
)

echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Starting VYBE at http://127.0.0.1:5000 ...
echo Demo logins: traveler@vybe.demo / traveler123
echo.
python app.py

pause

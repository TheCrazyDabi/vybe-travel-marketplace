@echo off
title VYBE Mobile Dev Server
echo ========================================================
echo    VYBE Mobile Development Launcher
echo ========================================================
echo.

set "ADB_PATH=%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"

if exist "%ADB_PATH%" (
    echo [1/2] Connecting to phone over USB...
    "%ADB_PATH%" reverse tcp:5000 tcp:5000
    if %ERRORLEVEL% equ 0 (
        echo [OK] USB port forward active! Phone can access http://localhost:5000
    ) else (
        echo [!] Phone not detected. Ensure USB cable is plugged in and USB debugging is enabled.
    )
) else (
    echo [!] ADB not found at default Android SDK location.
)

echo.
echo [2/2] Starting VYBE Flask server...
echo Open the VYBE app on your phone once the server starts.
echo Press Ctrl+C to stop the server.
echo.

.\.venv\Scripts\python.exe app.py
pause

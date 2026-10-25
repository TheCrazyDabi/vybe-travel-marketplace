Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "    VYBE Mobile Development Launcher" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

$adbPath = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"

if (Test-Path $adbPath) {
    Write-Host "[1/2] Connecting to phone over USB..." -ForegroundColor Yellow
    & $adbPath reverse tcp:5000 tcp:5000
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] USB port forward active! Phone can access http://localhost:5000" -ForegroundColor Green
    } else {
        Write-Host "[!] Phone not detected. Ensure USB cable is plugged in and USB debugging is enabled." -ForegroundColor Magenta
    }
} else {
    Write-Host "[!] ADB not found at $adbPath" -ForegroundColor Red
}

Write-Host "`n[2/2] Starting VYBE Flask server..." -ForegroundColor Yellow
Write-Host "Open the VYBE app on your phone once the server starts." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop.`n" -ForegroundColor Gray

& .\.venv\Scripts\python.exe app.py

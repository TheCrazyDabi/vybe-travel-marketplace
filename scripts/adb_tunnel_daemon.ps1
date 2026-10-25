$adb = "C:\Users\vasud\AppData\Local\Android\Sdk\platform-tools\adb.exe"
Write-Host "Starting persistent ADB reverse port tunnel..."

while ($true) {
    try {
        $devs = & $adb devices 2>$null
        if ($devs -match '1592608198000B6\s+device') {
            $revList = & $adb -s 1592608198000B6 reverse --list 2>$null
            if ($revList -notmatch 'tcp:5000') {
                & $adb -s 1592608198000B6 reverse tcp:5000 tcp:5000 2>$null
                Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Re-established reverse tcp:5000 -> tcp:5000"
            }
        }
    } catch {
        # ignore transient adb restart exceptions
    }
    Start-Sleep -Seconds 2
}

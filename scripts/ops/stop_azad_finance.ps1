# stop_azad_finance.ps1 - kill all Python processes spawned by Azad-Finance.

$ErrorActionPreference = "Stop"
$TmpDir  = "C:\Users\azad1\AppData\Local\Temp\opencode"
$PidFile = Join-Path $TmpDir "app.pid"

if (Test-Path $PidFile) {
    $rawPid = Get-Content -Path $PidFile -Raw -ErrorAction SilentlyContinue
    if ($rawPid) {
        $proc = Get-Process -Id ([int]$rawPid) -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "Stopping Azad-Finance server PID=$rawPid"
            Stop-Process -Id $proc.Id -Force
            Start-Sleep -Seconds 1
        }
    }
    Remove-Item -Path $PidFile -Force
}

# Fallback safety net: kill any leftover python processes.
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
Write-Host "all python residue cleared"
Start-Sleep -Seconds 2
$bound = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
if ($bound) {
    Write-Host "still bound on port 5000:"
    $bound | Format-List LocalAddress, OwningProcess
} else {
    Write-Host "port 5000 is free"
}
